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
  is the 1.1.4 commit (OCR cancellation/stale-run recovery, version bump and
  docs) on top of `bbf1449`, `origin/main` in sync and the working tree clean.
  v1.1.4 is published as a GitHub release from tag `v1.1.4` at `6d17b57`; the
  release asset was re-downloaded and its checksum matched.
  Treat unfamiliar work as the owner's; do not discard it.
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
- Version 1.1.4 is published as the v1.1.4 GitHub release from tag `v1.1.4` at
  commit `6d17b57`. v1.1.1 remains available. Do not publish any newer work
  without an explicit owner request.
- Latest checks: 475 backend tests, 60 web files / 369 tests, typecheck, lint and
  production build clean. `npm run smoke:desktop` passed 12/12 packaged steps on
  the win-unpacked build in 15 s; the installed 1.1.4 build passed 12/12 in 13 s
  (Tesseract 5.4.0, 4 OCR blocks, 95.1 confidence, backup/restore, sidecar
  stopped). Install → smoke → uninstall (project data retained) → reinstall was
  verified; one first installed-smoke attempt timed out on import and passed on
  rerun. The smoke does not exercise the Cancel button; cancellation is covered
  by backend tests.
- Published 1.1.4 installer: DocuRebuild-1.1.4-setup.exe,
  205,449,910 bytes (195.93 MB), SHA-256
  38F29388F64DF555BF9C46DBDBC094CE2868FE4DE84BE619B212FD9837758DD6; re-downloaded
  anonymously from the release with a matching size and hash.
- Published 1.1.1 installer: DocuRebuild-1.1.1-setup.exe, 204.19 MB, SHA-256
  9CC17F7EDF0138A7FC452844C89B0F2EC653970258F3888A661AB3773FAC13CB.
- Locally built 1.1.3 installer: DocuRebuild-1.1.3-setup.exe, 205,444,142 bytes
  (195.93 MB), SHA-256
  BCB80868CF88EE9A8581BB12CA84FB2B798CFC137E77D082640B62FD7D687E20. The earlier
  locale-trimmed file named DocuRebuild-1.1.1-setup.exe in dist/ is 195.92 MB,
  SHA-256
  BABE4B5949BF996701BC5BD3FB6F707D59FA33D1746B7E2E7FF4839ED484F649, is
  byte-identical to before the 1.1.2/1.1.3 builds and must not be published as
  1.1.1. The 1.1.2 installer (56BEA0EB...88117) also remains in dist/ unchanged.

BASELINE COMMANDS (run before changing behaviour)
  backend\.venv\Scripts\python.exe -m pytest backend/tests -q   # 475 passed
  npm run test:web                                             # 369 tests / 60 files
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
- OCR cancellation and stale-run recovery are done (see the session log).
- Other recorded items are known gaps, not tasks unless the owner approves one:
  a larger real-scan corpus, text-only merged-cell detection, a bundled offline
  LaTeX typesetter, OMML edge cases, automatic update checking and account-level
  provider quota verification.

KNOWN GAPS (recorded, not tasks unless approved)
- Windows x64 only, no code signing; interactive NVDA/Narrator pass blocked.
- Larger real-scan corpus; text-only merged-cell detection; bundled offline
  LaTeX typesetter; OMML edge cases; automatic update checking; account-level
  provider quota verification. A hard kill can still leave one OCR preparation
  PNG in the data folder's tmp/ (the run itself now recovers as
  ocr_interrupted).
- Provider quota remains report-only; macOS/Linux remains a feasibility report.

DURABLE INVARIANTS
- Region proposals are derived from the latest successful OCR run plus current
  source asset and rotation; never persist them. Accepted regions are elements.
- Imports are serialised per project; PDF documents are closed through
  pdf.close_document() to release native memory.
- OCR cancellation is cooperative: a per-run event stops the engine process,
  only a running row can become succeeded, and active rows without a live worker
  recover as ocr_interrupted (or cancelled while cancelling).
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
- 2026-11-28: 1.1.4 published. Annotated tag `v1.1.4` at `6d17b57` pushed and a
  non-draft GitHub release created with DocuRebuild-1.1.4-setup.exe
  (205,449,910 bytes, SHA-256 38F29388...58DD6). Installer QA on Windows 11 x64:
  silent per-user install, installed-build smoke 12/12 in 13 s, quiet uninstall
  with %LOCALAPPDATA%\DocuRebuild retained, then reinstall; the first installed
  smoke attempt timed out on import and passed on rerun. The release asset was
  downloaded anonymously and matched size and hash exactly. v1.1.1 remains
  available; nothing newer was published.
- 2026-11-28: OCR cancellation and stale-run recovery.
  New POST /projects/{id}/ocr/runs/{run_id}/cancel and a Cancel text extraction
  button in the dialog; queued/running -> cancelling -> cancelled with an
  ocr_cancelled activity event, the engine process is terminated and partial
  output discarded, finished runs are refused with ocr_not_running, and only a
  running row can become succeeded. Registry recovery marks orphaned
  queued/running rows failed with ocr_interrupted and orphaned cancelling rows
  cancelled, from get/latest OCR and the region/equation proposals; graceful
  shutdown records active runs interrupted. Proposals gained ocr_cancelled in
  en/my. Version bumped to 1.1.4; 475 backend / 60 web files / 369 tests,
  typecheck, lint and build clean; clean desktop:dist produced
  DocuRebuild-1.1.4-setup.exe (205,449,910 bytes, SHA-256 38F29388...58DD6) and
  npm run smoke:desktop passed 12/12 packaged steps in 15 s (Tesseract 5.4.0, 4
  blocks, 343 characters, sidecar stopped). Earlier installers untouched.
  Committed and pushed to main; no release published.
- 2026-11-28 (1.1.3 version/docs commit): version bump to 1.1.3 across all
  manifests, clean npm run desktop:dist producing the separate
  DocuRebuild-1.1.3-setup.exe (205,444,142 bytes / 195.93 MB,
  BCB80868...87E20), 12/12 packaged smoke in 17 s, 468 backend / 369 web tests,
  typecheck/lint clean; docs and handover refreshed; pushed to main, no GitHub
  release published and the 1.1.1 asset untouched. Note: the packaged smoke needs
  no other DocuRebuild instance running (the installed app shares
  %APPDATA%\DocuRebuild and holds the single-instance lock).
- 2026-11-28 aefc5ed: equation extraction starts from normalised LaTeX instead
  of raw OCR text; new `backend/app/services/equation_latex.py` rebuilds the
  source from the stored OCR word boxes (superscripts/subscripts) and maps
  Unicode math to commands (`cos²(2θ)` -> `\cos^2(2\theta)`), never guessing a
  misread character, and the optional AI equation prompt now preserves
  fractions/scripts/brackets/pre-equals terms; proposal `latex` field added
  through schema, shared type and the review dialog; 468 backend / 60 web files
  / 369 tests, typecheck, lint and build clean; pushed to main, no release
  published. Known gap unchanged: `_is_equation` needs >=2 math symbols, so
  `I(2θ) =` alone stays a paragraph and is excluded from the region.
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
