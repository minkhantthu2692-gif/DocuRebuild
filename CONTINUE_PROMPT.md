# DocuRebuild — Continue Prompt (new chat / new agent)

Read this file first in any new chat that continues DocuRebuild work. It is the
durable handover for the remaining prompt pack. `AGENTS.md` contains the rules
that must not be broken; `PROJECT_COMPLETION_REPORT.md` is the historical QA
record; `docs/should-have/PROGRESS.md` holds the per-task evidence for the
`02_SHOULD_HAVE` series.

**State at this update:** 2026-11-28, branch `main` at `0d2aa0e`, version
`1.1.1` released (28 November 2026). The post-release task work is committed on
`main` but is **not** a published release. Verify with `git status -sb` and
`git log --oneline -10` before starting; do not discard unfamiliar work.

## Paste-ready prompt

Copy the block below into a new chat. It deliberately asks for one task only.

```text
Continue DocuRebuild from the documented state. First read AGENTS.md,
CONTINUE_PROMPT.md, docs/should-have/PROGRESS.md, ROADMAP.md and
PROJECT_COMPLETION_REPORT.md section 16. Run git status -sb and git log --oneline
-10; treat unfamiliar work as the owner's work. Do not redo completed tasks.

The supported scope stays Windows x64 Electron + bundled Python sidecar,
local-first. Do not add mobile/PWA/Tauri/camera/cloud/collaboration work, do not
publish a release, and do not claim any test, build, download or release result
without evidence.

Verify the baseline before changing code:
  backend\.venv\Scripts\python.exe -m pytest backend/tests -q
  npm run test:web
  npm run typecheck
  npm run lint

All four 01_MUST_HAVE and all four 02_SHOULD_HAVE prompt-pack tasks are done
(see the tables in CONTINUE_PROMPT.md). Pick exactly ONE unfinished item from
the "Remaining work" table in CONTINUE_PROMPT.md, read its prompt file in
C:\Users\minkh\Downloads\Telegram Desktop\DocuRebuild_Remaining_Work_Prompts\DocuRebuild_Prompt_Pack,
and follow that prompt's acceptance criteria. Use disposable test data; keep
originals and user projects untouched. Add or update tests and both English and
Burmese locale keys for any UI string. Update docs/should-have/PROGRESS.md or a
new docs/<series>/PROGRESS.md, ROADMAP.md, CHANGELOG.md and CONTINUE_PROMPT.md
(status table and session log) with exact commands, results, limitations and
files changed. Commit only that task. Stop after it and report what remains.
```

## Completed — 01_MUST_HAVE

| # | Task | Evidence | Commit / record |
| --- | --- | --- | --- |
| 01 | Real-scan OCR accuracy baseline | `backend/tests/fixtures/ocr-real/`, `docs/ocr-benchmark.md`, `PROJECT_COMPLETION_REPORT.md` §13.10 | `8cb208c` |
| 02 | Accessibility keyboard/screen-reader audit | `PROGRESS.md`, §13.9, `apps/web/src/test/accessibility.test.tsx`, `form-controls.test.tsx` | `09b5f99` (audit); interactive NVDA/Narrator pass still blocked by unavailable tooling |
| 03 | Large-document performance/cancellation | `docs/performance.md`, `docs/performance/sidecar-drill.json`, `docs/performance/editor-drill.json`, §14 | `09b5f99` plus two measured fixes |
| 04 | Automated desktop E2E smoke tests | `scripts/desktop-smoke.mjs`, `npm run smoke:desktop`, `docs/smoke/desktop-smoke.json`, §15 | `ad7809d` |

The audit was completed; WCAG certification is **not** claimed. OCR cancellation
and stale-run recovery were identified as gaps by task 03 and remain known gaps.

## Completed — 02_SHOULD_HAVE

| # | Task | Evidence | Commit |
| --- | --- | --- | --- |
| 01 | Page-wide figure detection | `backend/tests/figure_eval.py`, `test_figure_eval.py`, `docs/figure-detection.md`; precision 1.00, recall 1.00 on the controlled corpus | `04f0b5f` |
| 02 | Page-wide equation proposals | `regions.propose_page_equations`, `GET .../equation-proposals`, `PageEquationsDialog`, 4 backend + 3 web tests | `0708826` |
| 03 | Nested table separation | linked parent/child drawn grids, `TableNestedOut`, dialog badges, 4 backend + 3 web tests | `25ffbc7` |
| 04 | Opaque PDF drawing extraction | rendered-page raster fallback for opaque PDFs, 2 backend tests, `docs/figure-detection.md` | `0d2aa0e` |

Full per-task findings, commands, numbers, limitations and changed files are in
`docs/should-have/PROGRESS.md`. Latest verified totals: **450 backend tests**,
**59 web files / 364 tests**, typecheck and lint clean. The published v1.1.1
installer was built from `486688e`, before these four commits; the task work is
not yet in a release asset.

## Remaining work (one task per session)

These items must not delay the Windows x64 release. Do not implement a task that
has a `done` row above without an explicit owner decision.

| Order | Item | Prompt / record | Status |
| --- | --- | --- | --- |
| 1 | Audit earlier requested fixes; fix at most one confirmed defect | `04_QUICK_WINS_AND_REGRESSION_CHECKS/01_Audit_Previously_Requested_Fixes.md` | not started |
| 2 | Persisted region proposals and batch review | `03_OPTIONAL_FUTURE/01_Persisted_Region_Proposals_Batch_Review.md` | design/evaluation first |
| 3 | PaddleOCR adapter evaluation | `03_OPTIONAL_FUTURE/02_PaddleOCR_Adapter_Evaluation.md` | benchmark report first |
| 4 | Provider quota/billing introspection | `03_OPTIONAL_FUTURE/03_Provider_Quota_Introspection.md` | capability matrix first |
| 5 | Windows installer footprint optimisation | `03_OPTIONAL_FUTURE/04_Windows_Installer_Footprint_Optimisation.md` | not started |
| 6 | macOS/Linux feasibility study | `03_OPTIONAL_FUTURE/05_macOS_Linux_Feasibility.md` | report only; no implementation until approved |

Other honest gaps already recorded in `ROADMAP.md` and `PROJECT_MEMORY.md` §12:
interactive NVDA/Narrator pass and code signing (wider-release blockers); OCR
cancellation and stale-run recovery; larger real-scan OCR corpus; merged-cell
detection for text-only tables; bundled offline LaTeX typesetter for PDF export;
remaining OMML edge cases; automatic update checking; account-level provider
quota verification. Mobile, PWA, camera pairing, cloud accounts and telemetry
are out of scope, not pending.

## Working rules

- One prompt/task per session. Verify current code and tests; dated reports are
  a baseline, not proof of today's tree.
- Keep the desktop boundary: loopback-only API, per-launch token, same-origin
  SPA, sandboxed renderer, no generic IPC bridge and no secrets in the bundle.
- Never fabricate test, accuracy, accessibility or performance results. Use
  disposable data and never risk real user projects.
- Preserve local-first behaviour, immutable originals and review-before-insert
  semantics for every OCR/AI proposal.
- Update progress documentation for every task. Commit only that task; do not
  publish a release unless the owner explicitly asks.

## Verification commands

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests -q
npm run test:web
npm run typecheck
npm run lint
npm run build                 # UI changes
npm run desktop:dist          # packaged-build changes
npm run smoke:desktop         # after a new packaged build
```

## Session log

| Date | Session / task | Outcome | Commit |
| --- | --- | --- | --- |
| 2026-11-28 | `01_MUST_HAVE` 01-04 | all complete; v1.1.1 published | `8cb208c`, `09b5f99`, `ad7809d`, `486688e` |
| 2026-11-28 | `02_SHOULD_HAVE` 01-04 | all complete; 450 backend / 364 web tests | `04f0b5f`, `0708826`, `25ffbc7`, `0d2aa0e` |
| 2026-11-28 | Status documentation refresh | this handover created; docs aligned; no release published | uncommitted at this update |
