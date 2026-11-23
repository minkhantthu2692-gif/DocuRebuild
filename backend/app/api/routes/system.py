from __future__ import annotations

from fastapi import APIRouter

from app.core.errors import AppError
from app.schemas.system import FactoryResetRequest, FactoryResetResult
from app.services.factory_reset import reset_application_data

router = APIRouter(prefix="/system", tags=["system"])

RESET_CONFIRMATION = "DELETE"


@router.post("/reset", response_model=FactoryResetResult)
def reset_local_data(payload: FactoryResetRequest) -> dict[str, object]:
    """Erase every project and setting and return to a fresh-install state.

    The frontend requires the user to type DELETE. The same check is enforced
    here so a mistaken or automated request cannot wipe local data.
    """
    if payload.confirm.strip() != RESET_CONFIRMATION:
        raise AppError(
            400,
            "reset_confirmation_required",
            f'Type "{RESET_CONFIRMATION}" to confirm the factory reset.',
        )
    return reset_application_data()
