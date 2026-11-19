"""Unified AI task router: routing, capability checks, key rotation and usage.

Every AI call in the application goes through :func:`complete`. The router owns
provider selection, credential use, limits and health state, so no feature
service performs HTTP requests or touches an API key itself.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import AiConnection, AiConnectionKey, AiModel, utcnow
from app.services import ai_providers, ai_secrets, ai_store, ai_usage

logger = logging.getLogger(__name__)

MAX_RETRY_AFTER_SECONDS = 86_400
DEFAULT_RATE_LIMIT_COOLDOWN = 60
# Failures that happened before a generation could plausibly be produced. A
# timeout is deliberately excluded: retrying it could bill the same request twice.
RETRYABLE_CATEGORIES = {"auth", "rate_limit"}
RETRYABLE_CODES = {"ai_unreachable", "ai_provider_unavailable", "ai_endpoint_not_found"}


class RoutedReply(NamedTuple):
    text: str
    provider: str
    model: str
    base_url: str
    connection_id: str
    connection_name: str
    key_id: str | None
    key_label: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None
    cost_source: str | None
    duration_ms: int
    data: Any = None


class _Candidate(NamedTuple):
    connection: AiConnection
    model_id: str
    route: Any


def _now() -> datetime:
    return utcnow()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _app_error(exc: ai_providers.ProviderError) -> AppError:
    status = 502
    if exc.category == "auth":
        status = 401
    elif exc.category == "rate_limit":
        status = 429
    elif exc.category == "config":
        status = 409
    message = exc.message
    if exc.retry_after_seconds:
        message = f"{message} Try again after {exc.retry_after_seconds} seconds."
    return AppError(status, exc.code, message)


def _connection_error(code: str, message: str) -> AppError:
    return AppError(409, code, message)


def _price_for(
    session: Session, connection: AiConnection, model_id: str
) -> tuple[float | None, float | None, str | None]:
    """Return per-million input/output prices only when they are verifiable."""
    manual = (connection.settings or {}).get("pricing", {})
    if isinstance(manual, dict):
        entry = manual.get(model_id)
        if isinstance(entry, dict):
            input_price = entry.get("input_per_million")
            output_price = entry.get("output_per_million")
            if isinstance(input_price, (int, float)) or isinstance(
                output_price, (int, float)
            ):
                return (
                    float(input_price)
                    if isinstance(input_price, (int, float))
                    else None,
                    float(output_price)
                    if isinstance(output_price, (int, float))
                    else None,
                    "manual",
                )
    model = session.execute(
        select(AiModel).where(
            AiModel.connection_id == connection.id, AiModel.model_id == model_id
        )
    ).scalar_one_or_none()
    pricing = model.pricing if model is not None else None
    if not isinstance(pricing, dict):
        return None, None, None
    prompt = pricing.get("prompt", pricing.get("prompt_tokens"))
    completion = pricing.get("completion", pricing.get("completion_tokens"))
    prompt_price = _per_million(prompt)
    completion_price = _per_million(completion)
    if prompt_price is None and completion_price is None:
        return None, None, None
    return prompt_price, completion_price, "provider_pricing"


def _per_million(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number < 0:
        return None
    # Provider catalogs that expose pricing use a per-token number.
    return round(number * 1_000_000, 6)


def _estimate_cost(
    session: Session,
    connection: AiConnection,
    model_id: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> tuple[float | None, str | None]:
    if input_tokens is None and output_tokens is None:
        return None, None
    input_price, output_price, source = _price_for(session, connection, model_id)
    if source is None:
        return None, None
    total = 0.0
    priced = False
    if input_tokens is not None and input_price is not None:
        total += input_tokens / 1_000_000 * input_price
        priced = True
    if output_tokens is not None and output_price is not None:
        total += output_tokens / 1_000_000 * output_price
        priced = True
    if not priced:
        return None, None
    return round(total, 8), source


def _key_eligible(key: AiConnectionKey) -> bool:
    cooldown = _as_utc(key.cooldown_until)
    return (
        key.enabled
        and not key.auth_failed
        and (cooldown is None or cooldown <= _now())
        and ai_secrets.has_secret(ai_store.secret_id_for_key(key.id))
    )


def _ordered_keys(
    session: Session, connection: AiConnection
) -> list[tuple[AiConnectionKey | None, str]]:
    keys = list(
        session.execute(
            select(AiConnectionKey).where(
                AiConnectionKey.connection_id == connection.id
            )
        )
        .scalars()
        .all()
    )
    eligible = [key for key in keys if _key_eligible(key)]
    strategy = connection.rotation_strategy
    if strategy in {"round_robin", "least_recent"}:
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        eligible.sort(
            key=lambda key: (
                _as_utc(key.last_used_at) or epoch,
                key.priority,
                key.created_at,
            )
        )
    elif strategy == "least_usage":
        def usage(key: AiConnectionKey) -> int:
            return ai_usage.count_attempts(session, key_id=key.id)

        eligible.sort(
            key=lambda key: (usage(key), _as_utc(key.last_used_at) or _now(), key.priority)
        )
    else:
        # "priority" and "failover" both use the explicit priority order.
        eligible.sort(
            key=lambda key: (key.priority, _as_utc(key.last_used_at) or _now())
        )
    return [(key, ai_store.resolve_key_secret(key) or "") for key in eligible]


def _candidates(session: Session, task: str) -> list[_Candidate]:
    route = ai_store.effective_route(session, task)
    if route is None:
        spec = ai_store.TASK_BY_ID.get(task)
        label = spec.label if spec else task
        raise _connection_error(
            "ai_task_not_configured",
            f"Choose a provider and model for {label} in AI settings first.",
        )
    result: list[_Candidate] = []
    primary = session.get(AiConnection, route.connection_id) if route.connection_id else None
    if primary is not None and route.model_id:
        result.append(_Candidate(primary, route.model_id, route))
    if route.fallback_connection_id and route.fallback_model_id:
        fallback = session.get(AiConnection, route.fallback_connection_id)
        if fallback is not None and fallback.id != (primary.id if primary else None):
            result.append(_Candidate(fallback, route.fallback_model_id, route))
    return result


def _check_capability(session: Session, connection: AiConnection, model_id: str, task: str) -> None:
    spec = ai_store.TASK_BY_ID.get(task)
    if spec is None:
        return
    model = session.execute(
        select(AiModel).where(
            AiModel.connection_id == connection.id, AiModel.model_id == model_id
        )
    ).scalar_one_or_none()
    if model is None:
        raise _connection_error(
            "ai_model_not_in_catalog",
            "The configured model is no longer in this connection's catalog. Refresh the model list.",
        )
    if not model.available:
        raise _connection_error(
            "ai_model_unavailable",
            "The provider no longer lists the configured model. Choose another model.",
        )
    if spec.capability == "vision":
        if model.input_modalities is not None and "image" not in model.input_modalities:
            raise _connection_error(
                "ai_model_missing_vision",
                "The configured model does not accept image input. Choose a vision-capable model.",
            )
    elif model.output_modalities is not None and "text" not in model.output_modalities:
        raise _connection_error(
            "ai_model_missing_text",
            "The configured model does not produce text. Choose a text-capable model.",
        )


def _check_limits(
    session: Session,
    *,
    connection: AiConnection,
    route: Any,
    task: str,
    preferences: ai_store.AiPreferences,
) -> bool:
    """Enforce global/task limits, and report whether this connection can run.

    Global and task caps are hard stops. A connection-level cap only skips that
    connection, so a configured fallback can still serve the request.
    """
    ai_usage.ensure_within_limit(session, preferences.daily_request_limit)
    if preferences.monthly_budget_usd is not None:
        spent = ai_usage.monthly_cost(session)
        if spent >= preferences.monthly_budget_usd:
            raise AppError(
                409,
                "ai_budget_exceeded",
                "The monthly AI spending limit has been reached. Raise the limit in AI settings to continue.",
            )
    if route.request_limit > 0 and ai_usage.count_attempts(session, task=task) >= route.request_limit:
        raise AppError(
            429,
            "ai_task_limit_reached",
            "The request limit for this AI task has been reached for the last 24 hours.",
        )
    if connection.request_limit > 0 and ai_usage.count_attempts(
        session, connection_id=connection.id
    ) >= connection.request_limit:
        return False
    if connection.monthly_budget_usd is not None:
        spent = ai_usage.monthly_cost(session, connection.id)
        if spent >= connection.monthly_budget_usd:
            return False
    return True


def _mark_failure(
    session: Session,
    connection: AiConnection,
    key: AiConnectionKey | None,
    model_id: str,
    exc: ai_providers.ProviderError,
) -> None:
    now = _now()
    status = {
        "auth": "auth_failed",
        "rate_limit": "rate_limited",
        "server": "unavailable",
        "network": "unavailable",
        "config": "configuration_required",
    }.get(exc.category, "error")
    if key is not None:
        key.last_used_at = now
        key.last_error_at = now
        key.last_error_code = exc.code
        if exc.category == "auth":
            key.auth_failed = True
        if exc.category == "rate_limit":
            cooldown = exc.retry_after_seconds or DEFAULT_RATE_LIMIT_COOLDOWN
            key.cooldown_until = now + timedelta(
                seconds=min(cooldown, MAX_RETRY_AFTER_SECONDS)
            )
    connection.last_status = status
    connection.last_error_code = exc.code
    connection.last_http_status = exc.http_status
    connection.retry_after_seconds = exc.retry_after_seconds
    connection.last_checked_at = now
    connection.updated_at = now
    _ = model_id


def _mark_success(
    session: Session,
    connection: AiConnection,
    key: AiConnectionKey | None,
    model_id: str,
) -> None:
    now = _now()
    if key is not None:
        key.last_used_at = now
        key.last_success_at = now
        key.last_error_code = None
        key.cooldown_until = None
        key.auth_failed = False
    connection.last_status = "connected"
    connection.last_error_code = None
    connection.last_http_status = None
    connection.retry_after_seconds = None
    connection.last_checked_at = now
    connection.updated_at = now
    ai_store.touch_model_use(session, connection.id, model_id)


def _record(
    session: Session,
    *,
    task: str,
    connection: AiConnection,
    key: AiConnectionKey | None,
    model_id: str,
    outcome: str,
    error_code: str | None,
    project_id: str | None,
    page_id: str | None,
    block_id: str | None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    estimated_cost_usd: float | None = None,
    cost_source: str | None = None,
    duration_ms: int | None = None,
) -> None:
    ai_usage.record_attempt(
        session,
        provider=connection.provider,
        model=model_id,
        task=task,
        outcome=outcome,
        error_code=error_code,
        project_id=project_id,
        page_id=page_id,
        block_id=block_id,
        connection_id=connection.id,
        connection_name=connection.name,
        key_id=key.id if key else None,
        key_label=key.label if key else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost_usd,
        cost_source=cost_source,
        duration_ms=duration_ms,
    )


def _commit_usage(session: Session) -> None:
    try:
        session.commit()
    except Exception:
        logger.exception("Could not persist local AI usage metadata.")
        session.rollback()


def complete(
    session: Session,
    task: str,
    *,
    system_prompt: str,
    user_text: str,
    image_b64: str | None = None,
    project_id: str | None = None,
    page_id: str | None = None,
    block_id: str | None = None,
    confirm_paid: bool = False,
    temperature: float | None = None,
    json_mode: bool = False,
    validator: Callable[[str], Any] | None = None,
) -> RoutedReply:
    """Run one text or vision request through the configured task route."""
    ai_store.task_spec(task)
    preferences = ai_store.get_preferences(session)
    ai_usage.ensure_within_limit(session, preferences.daily_request_limit)
    if preferences.monthly_budget_usd is not None and ai_usage.monthly_cost(
        session
    ) >= preferences.monthly_budget_usd:
        raise AppError(
            409,
            "ai_budget_exceeded",
            "The monthly AI spending limit has been reached. Raise the limit in AI settings to continue.",
        )

    candidates = _candidates(session, task)
    saw_rate_limit = False
    retry_after: int | None = None
    last_error: ai_providers.ProviderError | None = None
    paid_refused = False
    attempted = False
    limit_blocked = False
    capability_blocked = False

    for candidate in candidates:
        connection = candidate.connection
        if not connection.enabled:
            continue
        try:
            _check_capability(session, connection, candidate.model_id, task)
        except AppError:
            # A broken primary must not prevent a configured fallback from
            # serving the request; the reason is kept for the final error.
            capability_blocked = True
            continue
        if not _check_limits(
            session,
            connection=connection,
            route=candidate.route,
            task=task,
            preferences=preferences,
        ):
            limit_blocked = True
            continue

        if connection.cost_class == "paid" and not confirm_paid:
            paid_refused = True
            continue

        keys: list[tuple[AiConnectionKey | None, str]] = _ordered_keys(
            session, connection
        )
        spec = ai_providers.PROVIDER_BY_ID.get(connection.provider)
        if not keys:
            all_keys = list(
                session.execute(
                    select(AiConnectionKey).where(
                        AiConnectionKey.connection_id == connection.id
                    )
                )
                .scalars()
                .all()
            )
            if not all_keys and spec is not None and not spec.requires_api_key:
                # A loopback or self-hosted server may legitimately need no key.
                keys = [(None, "")]
            else:
                # Every configured key is disabled, cooling down or failed. Never
                # downgrade to an unauthenticated request just because a key was
                # rate limited.
                cooldowns = [
                    _as_utc(key.cooldown_until)
                    for key in all_keys
                    if _as_utc(key.cooldown_until) is not None
                    and _as_utc(key.cooldown_until) > _now()
                ]
                if cooldowns:
                    saw_rate_limit = True
                    seconds = int((min(cooldowns) - _now()).total_seconds())
                    retry_after = max(retry_after or 0, seconds, 1)
                continue
        # max_attempts bounds provider requests, not merely keys considered.
        attempts = 0
        for key, secret in keys:
            if attempts >= connection.max_attempts:
                break
            if key is not None and key.request_limit > 0 and ai_usage.count_attempts(
                session, key_id=key.id
            ) >= key.request_limit:
                continue
            attempts += 1
            attempted = True
            started = time.monotonic()
            try:
                reply = ai_providers.complete(
                    connection.provider,
                    base_url=connection.base_url,
                    model=candidate.model_id,
                    system_prompt=system_prompt,
                    user_text=user_text,
                    api_key=secret or None,
                    image_b64=image_b64,
                    temperature=(
                        temperature
                        if temperature is not None
                        else candidate.route.temperature
                    ),
                    timeout=float(candidate.route.timeout_seconds),
                    json_mode=json_mode,
                )
            except ai_providers.ProviderError as exc:
                duration_ms = int((time.monotonic() - started) * 1000)
                _mark_failure(session, connection, key, candidate.model_id, exc)
                _record(
                    session,
                    task=task,
                    connection=connection,
                    key=key,
                    model_id=candidate.model_id,
                    outcome="error",
                    error_code=exc.code,
                    project_id=project_id,
                    page_id=page_id,
                    block_id=block_id,
                    duration_ms=duration_ms,
                )
                _commit_usage(session)
                last_error = exc
                if exc.category == "rate_limit":
                    saw_rate_limit = True
                    retry_after = exc.retry_after_seconds or retry_after
                retryable = (
                    exc.category in RETRYABLE_CATEGORIES
                    or exc.code in RETRYABLE_CODES
                )
                if retryable:
                    continue
                raise _app_error(exc) from exc
            duration_ms = int((time.monotonic() - started) * 1000)
            cost, cost_source = _estimate_cost(
                session,
                connection,
                candidate.model_id,
                reply.input_tokens,
                reply.output_tokens,
            )
            _mark_success(session, connection, key, candidate.model_id)
            validated: Any = None
            if validator is not None:
                try:
                    validated = validator(reply.text)
                except AppError as exc:
                    # The provider answered, so its health is fine, but the
                    # reply could not be used. It is recorded as an error with
                    # the tokens it still consumed.
                    _record(
                        session,
                        task=task,
                        connection=connection,
                        key=key,
                        model_id=candidate.model_id,
                        outcome="error",
                        error_code=exc.code,
                        project_id=project_id,
                        page_id=page_id,
                        block_id=block_id,
                        input_tokens=reply.input_tokens,
                        output_tokens=reply.output_tokens,
                        total_tokens=reply.total_tokens,
                        estimated_cost_usd=cost,
                        cost_source=cost_source,
                        duration_ms=duration_ms,
                    )
                    _commit_usage(session)
                    raise
            _record(
                session,
                task=task,
                connection=connection,
                key=key,
                model_id=candidate.model_id,
                outcome="success",
                error_code=None,
                project_id=project_id,
                page_id=page_id,
                block_id=block_id,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                total_tokens=reply.total_tokens,
                estimated_cost_usd=cost,
                cost_source=cost_source,
                duration_ms=duration_ms,
            )
            _commit_usage(session)
            return RoutedReply(
                text=reply.text,
                provider=connection.provider,
                model=candidate.model_id,
                base_url=connection.base_url,
                connection_id=connection.id,
                connection_name=connection.name,
                key_id=key.id if key else None,
                key_label=key.label if key else None,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                total_tokens=reply.total_tokens,
                estimated_cost_usd=cost,
                cost_source=cost_source,
                duration_ms=duration_ms,
                data=validated,
            )

    if paid_refused:
        raise AppError(
            409,
            "ai_paid_confirmation_required",
            "This AI connection is marked as paid. Confirm the request before it is sent.",
        )
    if saw_rate_limit:
        message = "Every available API key is rate limited right now."
        if retry_after:
            message = f"{message} Try again after {retry_after} seconds."
        raise AppError(429, "ai_rate_limited", message)
    if last_error is not None:
        raise _app_error(last_error) from last_error
    if limit_blocked:
        raise AppError(
            429,
            "ai_connection_limit_reached",
            "The request or spending limit for every configured AI connection has been reached.",
        )
    if capability_blocked:
        raise AppError(
            409,
            "ai_task_model_incompatible",
            "The configured model cannot handle this task. Choose a compatible model in AI settings.",
        )
    if not attempted:
        raise AppError(
            409,
            "ai_no_available_key",
            "No enabled API key is available for this connection. Add a key or reset its health in AI settings.",
        )
    raise AppError(
        502,
        "ai_provider_unavailable",
        "The configured AI provider could not complete the request.",
    )


def task_status(session: Session) -> dict[str, Any]:
    """Return whether each task can run, used by workspace actions and the UI."""
    routes = {item["task"]: item for item in ai_store.list_routes(session)}
    result: dict[str, Any] = {}
    for task in ai_store.TASK_IDS:
        route = routes.get(task) or {}
        configured = bool(route.get("configured"))
        if not configured and routes.get(ai_store.DEFAULT_ROUTE_TASK, {}).get("configured"):
            default = routes[ai_store.DEFAULT_ROUTE_TASK]
            configured = True
            route = {**default, "task": task, "warnings": []}
        result[task] = {
            "configured": configured,
            "connection_id": route.get("connection_id"),
            "connection_name": route.get("connection_name"),
            "model_id": route.get("model_id"),
            "cost_class": route.get("cost_class"),
            "warnings": route.get("warnings", []),
        }
    return result
