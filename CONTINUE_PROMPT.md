# CONTINUE_PROMPT.md — single paste-ready handover

This file is the only handover prompt. The old `Prompt.md` reset runbook has been
consolidated here and removed; the original product specification is still in git
as `e7966d4:Prompt.md`. Copy the block below verbatim into a fresh OpenCode
session after clearing its data/cache. It is self-contained: do not re-read
`PROJECT_MEMORY.md`, `ROADMAP.md`, `CHANGELOG.md` or the per-task progress files
just to recover context. `AGENTS.md` is loaded automatically by OpenCode; follow
it, and open another document only if a specific approved task needs its detail.

```text
Continue DocuRebuild from the state below. This is the authoritative handover as
of 2026-11-28; do not reconstruct context by re-reading the rest of the docs.

FRESH SESSION CHECKS
- Working directory: C:\Users\minkh\OneDrive\Desktop\DocuRebuild
- Run git status -sb and git log --oneline -10. At handover: branch main, HEAD
  b7761bd ("feat: add read-only cross-page region review"), origin/main in sync.
  The only expected uncommitted change is this handover consolidation
  (CONTINUE_PROMPT.md replaces Prompt.md, plus its references in AGENTS.md,
  README.md, PROJECT_MEMORY.md and docs/roadmap.md). Treat unfamiliar work as
  the owner's; do not discard it.
- Do not create a new project or re-initialise git.
- AGENTS.md should already be in your context. If it is absent, read it once;
  otherwise do not re-open the other status documents.

SCOPE (non-negotiable)
- Windows x64 Electron shell + bundled Python sidecar, local-first.
- No mobile, PWA, Tauri, camera, cloud account, collaboration or telemetry work.
- Loopback-only API, per-launch bearer token, same-origin SPA, sandboxed
  renderer, no generic IPC bridge, no secrets in the bundle, logs or frontend.
- Optional BYOK AI only; paid calls require explicit one-action approval; every
  OCR/AI result stays a reviewable proposal; imported originals are immutable.

CURRENT VERIFIED STATE
- Version 1.1.1 is published from commit 486688e. Work after that tag is on main
  but unreleased; do not publish it.
- Latest checks: 456 backend tests, 60 web files / 368 tests, typecheck, lint and
  production build clean.
- Published 1.1.1 installer: DocuRebuild-1.1.1-setup.exe, 204.19 MB, SHA-256
  9CC17F7EDF0138A7FC452844C89B0F2EC653970258F3888A661AB3773FAC13CB.
- Unreleased locale-trimmed installer: 195.92 MB, SHA-256
  BABE4B5949BF996701BC5BD3FB6F707D59FA33D1746B7E2E7FF4839ED484F649; it passed
  12/12 npm run smoke:desktop but must not be published as 1.1.1.

BASELINE COMMANDS (run before changing behaviour)
  backend\.venv\Scripts\python.exe -m pytest backend/tests -q   # 456 passed
  npm run test:web                                             # 368 tests / 60 files
  npm run typecheck
  npm run lint
  npm run build                 # UI changes
  npm run desktop:dist          # packaged-build changes
  npm run smoke:desktop         # after a new packaged build

COMPLETED PROMPT-PACK WORK (do not redo)
- 01_MUST_HAVE: 01 real-scan OCR baseline (8cb208c), 02 accessibility audit
  (09b5f99), 03 performance/cancellation (09b5f99), 04 desktop E2E smoke
  (ad7809d).
- 02_SHOULD_HAVE: 01 figure detection (04f0b5f), 02 equation proposals
  (0708826), 03 nested tables (25ffbc7), 04 opaque PDF drawings (0d2aa0e).
- 04_QUICK_WINS: 01 audit - seven requests all verified working, no code change.
- 03_OPTIONAL_FUTURE: 01 done - proposals stay derived/non-persisted; the owner
  approved a read-only cross-page review, implemented in b7761bd as
  GET /projects/{id}/region-proposals (bounded 100 pages/request, 200 max,
  resumable, no batch accept). 03 quota introspection and 05 macOS/Linux study
  are report-only evaluations. 04 locale trimming is applied in 419f492 and
  verified. 02 PaddleOCR is deferred.

REMAINING WORK
- Only candidate: PaddleOCR adapter evaluation, deferred because it needs a heavy
  local install and a measured real-scan benchmark. Do not start it without an
  explicit owner decision. If approved, read its prompt file in
  C:\Users\minkh\Downloads\Telegram Desktop\DocuRebuild_Remaining_Work_Prompts\DocuRebuild_Prompt_Pack\03_OPTIONAL_FUTURE\02_PaddleOCR_Adapter_Evaluation.md
  and follow its acceptance criteria.
- No other prompt-pack work is pending. Mobile/PWA/camera/cloud are out of scope,
  not backlog.

KNOWN GAPS (recorded, not tasks unless approved)
- Windows x64 only, no code signing; interactive NVDA/Narrator pass blocked.
- OCR cancellation and stale-run recovery; larger real-scan corpus; text-only
  merged-cell detection; bundled offline LaTeX typesetter; OMML edge cases;
  automatic update checking; account-level provider quota verification.
- Provider quota remains report-only; macOS/Linux remains a feasibility report.

DURABLE INVARIANTS
- Region proposals are derived from the latest successful OCR run plus current
  source asset and rotation; never persist them. Accepted regions are elements.
- Imports are serialised per project; PDF documents are closed through
  pdf.close_document() to release native memory.
- Use design tokens for all UI values; no hardcoded colours, sizes or spacing.
- Every user-facing string needs keys in both en and my; key-parity tests pass.
- Alembic migrations are never rewritten after users apply them.
- User data lives outside the repo; never commit projects, PDFs, images, dist/,
  databases, .env or credentials.
- Preserve review-before-insert semantics: no silent extraction, AI accepts or
  paid calls.

WORKING RULES
- One task per session. Stop after it and report what remains.
- Use disposable test data; never touch real user projects or originals.
- Never fabricate test, accuracy, accessibility, performance, download, build or
  release results.
- Update docs/optional-future/PROGRESS.md (or the relevant series progress file),
  ROADMAP.md, CHANGELOG.md and this file with exact commands, results,
  limitations and changed files.
- Commit only the approved task. Do not push unless the owner explicitly asks;
  if asked, use `git -c http.version=HTTP/1.1 push origin main`.
- Do not publish a release or claim one succeeded without explicit approval and
  verified checksum evidence.

SESSION LOG (most recent first; append after each approved task)
- 2026-11-28 b7761bd: read-only cross-page region review; 456 backend / 60 web
  files / 368 tests; proposals remain derived; no release published.
- 2026-11-28 419f492: Chromium locales trimmed to en-US; installer 195.92 MB,
  12/12 smoke; unreleased.
- 2026-11-28 9d115b0: optional quota/footprint/platform evaluations; PaddleOCR
  deferred; no application code change.

Start by reporting the git state and baseline results, then wait for the owner's
task decision.
```
