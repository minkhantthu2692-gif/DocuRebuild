# DocuRebuild — Continue Prompt (new chat / new agent)

Read this file first in any new chat that continues DocuRebuild work. It is the
durable handover for the remaining prompt pack. `AGENTS.md` contains the rules
that must not be broken; `PROJECT_COMPLETION_REPORT.md` is the historical QA
record; `docs/should-have/PROGRESS.md` holds the per-task evidence for the
`02_SHOULD_HAVE` series.

**State at this update:** 2026-11-28, branch `main` after the quick-win audit and
the optional-evaluation commits, version `1.1.1` released (28 November 2026). The
post-release task work is committed on `main` but is **not** a published release.
All `01_MUST_HAVE`, `02_SHOULD_HAVE` and `04_QUICK_WINS` tasks are complete;
optional tasks 01, 03 and 05 are evaluated, task 01's approved read-only
cross-page region review is implemented, task 04 (locale trimming) is applied and
verified, and task 02 (PaddleOCR) is deferred. Verify with `git status -sb`
and `git log --oneline -10` before starting; do not discard unfamiliar work.

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

All 01_MUST_HAVE, 02_SHOULD_HAVE and 04_QUICK_WINS prompt-pack tasks are done
(see the tables in CONTINUE_PROMPT.md). Optional tasks 01, 03 and 05 are
evaluated; task 01's approved read-only cross-page region review is implemented;
task 04 (locale trimming) is applied and verified; task 02 (PaddleOCR) is
deferred because it needs a heavy local install and a measured real-scan
benchmark. Do not implement a deferred or evaluated item without an explicit
owner decision.

If the owner approves further optional work, pick exactly ONE item from the
"Remaining work" table, read its prompt file in
C:\Users\minkh\Downloads\Telegram Desktop\DocuRebuild_Remaining_Work_Prompts\DocuRebuild_Prompt_Pack,
and follow that prompt's acceptance criteria. Prefer low-cost work: the footprint
task only needs a verified `npm run desktop:dist` + `npm run smoke:desktop`
rebuild before any size claim. Use disposable test data; keep originals and user
projects untouched. Add or update tests and both English and Burmese locale keys
for any UI string. Update docs/should-have/PROGRESS.md or a new
docs/<series>/PROGRESS.md, ROADMAP.md, CHANGELOG.md and CONTINUE_PROMPT.md
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
`docs/should-have/PROGRESS.md`. Latest verified totals: **456 backend tests**
(the four `02_SHOULD_HAVE` tasks took it to 450; the optional region-proposal
evaluation added two regression tests and the cross-page review added four),
**60 web files / 368 tests**, typecheck, lint and production build clean. The published v1.1.1 installer was built from `486688e`, before
these commits. The current unreleased build was rebuilt with the locale trim and
passed the 12/12 `npm run smoke:desktop` suite (installer 195.92 MB); it must not
be published as 1.1.1.

## Completed — 04_QUICK_WINS

| # | Task | Outcome | Record |
| --- | --- | --- | --- |
| 01 | Audit earlier requested fixes | all seven VERIFIED WORKING; no confirmed defect and no application/test/locale change | `docs/quick-wins/PROGRESS.md` |

The audit re-ran 450 backend tests, 59 web files / 364 web tests (all passing),
focused suites of 120 backend and 69 web tests, inspected the packaged 1.1.1
`win-unpacked` build and smoke report, and probed DOCX/PDF justification with a
disposable script. No release was published.

## Remaining work (one task per session)

These items must not delay the Windows x64 release. Do not implement a task that
has a `done` row above without an explicit owner decision.

| Order | Item | Prompt / record | Status |
| --- | --- | --- | --- |
| 1 | Audit earlier requested fixes; fix at most one confirmed defect | `04_QUICK_WINS_AND_REGRESSION_CHECKS/01_Audit_Previously_Requested_Fixes.md` | done — all verified; no code change |
| 2 | Persisted region proposals and batch review | `03_OPTIONAL_FUTURE/01_Persisted_Region_Proposals_Batch_Review.md` | done — evaluation kept proposals derived/non-persisted; the approved read-only cross-page aggregation is implemented (bounded to 100 pages/request, 200 max, resumable, no batch accept) with 4 backend + 4 web tests; `docs/optional-future/PROGRESS.md` |
| 3 | PaddleOCR adapter evaluation | `03_OPTIONAL_FUTURE/02_PaddleOCR_Adapter_Evaluation.md` | deferred — needs a heavy local install and a measured real-scan benchmark; plan documented, no result claimed |
| 4 | Provider quota/billing introspection | `03_OPTIONAL_FUTURE/03_Provider_Quota_Introspection.md` | evaluated — capability matrix; report-only, no provider calls; verified endpoints only for OpenAI/Anthropic (admin keys), OpenRouter and DeepSeek |
| 5 | Windows installer footprint optimisation | `03_OPTIONAL_FUTURE/04_Windows_Installer_Footprint_Optimisation.md` | done — `electronLanguages: ["en-US"]` applied; verified `desktop:dist` + 12/12 smoke; installer 204.19 -> 195.92 MB, installed 646.64 -> 598.39 MB; unreleased; `docs/optional-future/PROGRESS.md` |
| 6 | macOS/Linux feasibility study | `03_OPTIONAL_FUTURE/05_macOS_Linux_Feasibility.md` | evaluated — platform matrix, blockers and effort estimate; report only, no implementation |

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
| 2026-11-28 | Status documentation refresh | this handover created; docs aligned; no release published | `0ef502d` |
| 2026-11-28 | `04_QUICK_WINS` 01 audit | seven earlier requests all VERIFIED WORKING; no confirmed defect; no application/test/locale changes; audit record added | this commit |
| 2026-11-28 | `03_OPTIONAL_FUTURE` 01 evaluation | design + stale-safety trade-off documented; decision to keep proposals derived/non-persisted; two regression tests added; no production code change | `a933ff6` |
| 2026-11-28 | `03_OPTIONAL_FUTURE` 02-05 evaluation | 02 deferred (heavy install + benchmark); 03 provider-quota matrix, 04 footprint measurement, 05 macOS/Linux feasibility documented; report-only, no application code change | `9d115b0` |
| 2026-11-28 | `03_OPTIONAL_FUTURE` 04 applied | `electronLanguages: ["en-US"]`; full `desktop:dist` + 12/12 `smoke:desktop`; installer 204.19 -> 195.92 MB, installed 646.64 -> 598.39 MB; unreleased | `419f492` |
| 2026-11-28 | `03_OPTIONAL_FUTURE` 01 read-only review | project-level aggregation endpoint with bounded/resumable scan, review dialog, source-panel navigation, both locales, 4 backend + 4 web tests; proposals stay derived; 456 backend / 60 files / 368 web tests | this commit |
