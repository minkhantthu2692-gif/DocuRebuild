# SHOULD HAVE task series — resumable progress

This file is the durable handover record for the four `02_SHOULD_HAVE` prompts in
`DocuRebuild_Remaining_Work_Prompts/DocuRebuild_Prompt_Pack`. Read this first if
the chat history is lost or another agent takes over. Each completed task has a
section below with: what changed, exact commands and results, measured numbers,
limitations, and the commit that contains it.

Scope guard (unchanged): Windows x64 Electron + bundled Python sidecar, local
first. No mobile/PWA/Tauri/camera/cloud/accounts/collaboration work.

Working rules for every task (from the prompt pack):
- Verify current code and tests; the dated report is a baseline, not proof.
- Implement only the task; avoid unrelated refactors and new dependencies.
- Never fabricate test/accuracy/accessibility/performance results.
- Use disposable data; never risk real user projects.
- Update `PROGRESS.md`/`ROADMAP.md` with evidence and files changed;
  `PROJECT_MEMORY.md` only for durable decisions.
- Commit only that task. Do not publish a release. Stop after the task.

## Status

| # | Task | Status | Commit |
| --- | --- | --- | --- |
| 01 | Page-wide figure detection | done | this task commit |
| 02 | Page-wide equation proposals | not started | — |
| 03 | Nested table separation | not started | — |
| 04 | Opaque PDF drawing extraction | not started | — |

## How to resume

1. Read this file and `AGENTS.md`.
2. Run the baseline checks:
   `backend\.venv\Scripts\python.exe -m pytest backend/tests -q`
   `npm run test:web` and `npm run typecheck` / `npm run lint`.
3. Pick the first task whose status is not `done`, read its prompt in the pack,
   and continue from its "Plan" notes.
4. When done, record evidence here, update `ROADMAP.md`/`CHANGELOG.md`, and
   commit only that task.

---

## Task 01 — Page-wide figure detection

**Prompt:** `02_SHOULD_HAVE/01_Page_Wide_Figure_Detection.md`

### Findings before changing code

The pipeline already exists and is substantial:
- `backend/app/services/regions.py` `propose_regions` assembles figure evidence
  from PDF embedded images (`pdf.image_regions`), PDF vector drawings
  (`pdf.drawing_regions`), raster ink clusters (`artwork.artwork_regions`) and
  caption bands (`_figure_rects`), then dedupes (IoU 0.85), suppresses regions
  already extracted as elements, and returns reviewable, non-persisted proposals.
- Proposals are never auto-inserted; the user reviews and saves a crop.
- Existing tests cover single image/vector figures, captions, background, logo,
  shaded backing, rotation staleness and raster artwork.

Missing vs the acceptance criteria:
- No precision/recall evaluation against ground truth.
- No explicit multi-column fixture/test for figure proposals.
- No multi-figure page fixture/test.

### Plan

1. Extract a behavior-preserving pure `assemble_figures` helper from
   `propose_regions` so the figure assembly can be evaluated in isolation.
2. Add `backend/tests/figure_eval.py` with IoU matching + precision/recall.
3. Add `backend/tests/test_figure_eval.py` with representative ground-truth
   cases (image, vector, captioned, duplicate shading, background, logo, raster
   chart, text-only, multi-column, two-figure) and thresholds.
4. Record measured precision/recall in `docs/figure-detection.md`.
5. Update `CHANGELOG.md`, `ROADMAP.md`, and this file.

### Result

- Extracted a behavior-preserving pure `assemble_figures(...)` from
  `propose_regions` (`backend/app/services/regions.py`) so the figure assembly
  can be evaluated in isolation. Existing region tests still pass unchanged.
- Added `backend/tests/figure_eval.py`: IoU, greedy one-to-one box matching, and
  precision/recall/F1 (per page and micro-averaged).
- Added `backend/tests/test_figure_eval.py`: 10 representative ground-truth cases
  (embedded image, vector chart, captioned image, shaded backing, full-page
  background, logo, multi-column, two figures, raster chart, text-only raster).
- Fixed a real duplicate-proposal defect the evaluation exposed: a short caption
  under a wide image produced two figures because area overlap alone fell below
  the merge threshold. Added `regions._caption_band_matches` (the band must share
  most of the smaller box on both axes) and used it in the caption merge.
- Added `docs/figure-detection.md` with the method, results and limitations.

Files changed: `backend/app/services/regions.py`,
`backend/tests/figure_eval.py` (new), `backend/tests/test_figure_eval.py` (new),
`docs/figure-detection.md` (new), `docs/should-have/PROGRESS.md` (new),
`CHANGELOG.md`, `ROADMAP.md`, `PROJECT_MEMORY.md`.

### Commands / evidence

- `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_figure_eval.py -q -s`
  -> `1 passed`. Overall TP=8, FP=0, FN=0, precision 1.00, recall 1.00, F1 1.00
  across the 10 cases (per-case table in `docs/figure-detection.md`).
- `... -m pytest backend/tests/test_regions.py backend/tests/test_artwork.py backend/tests/test_figure_eval.py -q`
  -> `23 passed` (refactor and merge fix preserve existing behaviour).
- `... -m pytest backend/tests -q` -> `440 passed in 446.70s` (was 439 before
  this task; the new evaluation test is the +1).

### Limitations

- The caption-band heuristic still proposes the band above a caption even when no
  artwork is present (intentional; reviewable, can be a false positive).
- Raster ink detection is capped at 5 regions and runs on a 480 px grayscale copy.
- PDF image/drawing evidence is skipped on rotated/edited pages.
- Proposals require an OCR run; opaque PDF figures with no vector paths and no
  embedded image are deferred to Task 04.
- The corpus is controlled/synthetic; it is not a general accuracy claim.
