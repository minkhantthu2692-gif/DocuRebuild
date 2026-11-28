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
- Run git status -sb and git log --oneline -10. At handover: branch `main`, HEAD
  is the 1.1.2 version/docs commit on top of `3243e91`, `origin/main` in sync and
  the working tree clean. Treat unfamiliar work as the owner's; do not discard
  it.
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
  but has not been published as a GitHub release; do not publish it without an
  explicit owner request.
- Version 1.1.2 is built, smoke-tested and pushed to main but is **not** published
  as a GitHub release. The published release remains v1.1.1.
- Latest checks: 456 backend tests, 60 web files / 368 tests, typecheck, lint and
  production build clean. The packaged 1.1.2 win-unpacked build passed 12/12
  npm run smoke:desktop steps in 14 s.
- Published 1.1.1 installer: DocuRebuild-1.1.1-setup.exe, 204.19 MB, SHA-256
  9CC17F7EDF0138A7FC452844C89B0F2EC653970258F3888A661AB3773FAC13CB.
- Locally built 1.1.2 installer: DocuRebuild-1.1.2-setup.exe, 205,436,086 bytes
  (195.92 MB), SHA-256
  56BEA0EB38B7017D2EAB143A31DE31CFF917875F1C4030216334B86D15588117. The
  earlier locale-trimmed file named DocuRebuild-1.1.1-setup.exe in dist/ is
  195.92 MB, SHA-256
  BABE4B5949BF996701BC5BD3FB6F707D59FA33D1746B7E2E7FF4839ED484F649, is
  byte-identical to before the 1.1.2 build and must not be published as 1.1.1.

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
  resumable,   no batch accept). 03 quota introspection and 05 macOS/Linux study
  are report-only evaluations. 04 locale trimming is applied in 419f492 and
  verified. 02 PaddleOCR was evaluated with the owner's approval on the
  real-scan corpus: no Burmese model, case-specific accuracy, ~8x sidecar
  footprint and 13-16x slower pages; decision not to implement.

REMAINING WORK
- No prompt-pack work is pending. The PaddleOCR adapter evaluation is complete
  with a benchmark-backed decision not to implement; Tesseract remains the sole
  default engine. Mobile/PWA/camera/cloud are out of scope, not backlog.
- Other recorded items are known gaps, not tasks unless the owner approves one:
  OCR cancellation/stale-run recovery, a larger real-scan corpus, text-only
  merged-cell detection, a bundled offline LaTeX typesetter, OMML edge cases,
  automatic update checking and account-level provider quota verification.

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
- 2026-11-28 (uncommitted at handover): version bump to 1.1.2 across all
  manifests, clean npm run desktop:dist producing the separate
  DocuRebuild-1.1.2-setup.exe (195.92 MB, 56BEA0EB...88117), 12/12 packaged
  smoke, 456 backend / 368 web tests, typecheck/lint clean; docs and handover
  refreshed; pushed to main, no GitHub release published and the 1.1.1 asset
  untouched.
- 2026-11-28 3243e91: PaddleOCR adapter evaluation; no Burmese model, v4 mobile
  16.35% vs Tesseract 22.64% overall CER but prose/mixed regressions, 137-162 s
  vs 10.31 s, ~842 MB packages; decision not to implement, no application code
  change; no release published.
- 2026-11-28 b7761bd: read-only cross-page region review; 456 backend / 60 web
  files / 368 tests; proposals remain derived; no release published.
- 2026-11-28 419f492: Chromium locales trimmed to en-US; installer 195.92 MB,
  12/12 smoke; later carried into the locally built 1.1.2 installer.
- 2026-11-28 9d115b0: optional quota/footprint/platform evaluations; PaddleOCR
  deferred; no application code change.

Start by reporting the git state and baseline results, then wait for the owner's
task decision.
```
