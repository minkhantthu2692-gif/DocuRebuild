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

---

## Task 02 — Page-wide equation proposals

**Prompt:** `02_SHOULD_HAVE/02_Page_Wide_Equation_Proposals.md`
**Status:** not started.

### Findings before changing code

- Page-wide equation *regions* already appear in
  `GET /projects/{id}/pages/{page_id}/region-proposals` as `kind="equation"`,
  `reason="equation_text"`, built in `backend/app/services/regions.py`
  (`propose_regions` -> `_cluster` over OCR blocks with `kind == "equation"`).
- There is **no dedicated page-wide equation endpoint** analogous to page tables
  (`table_structure.propose_page_tables`, `GET .../table-proposals`,
  `PageTablesDialog`).
- Single-crop transcription: `ai_vision.transcribe_equation`
  (`backend/app/services/ai_vision.py:169`), `ai.parse_equation_latex` /
  `ai.request_equation_latex` (`backend/app/services/ai.py:250,285`), route
  `POST /projects/{id}/elements/{element_id}/ai-equation`
  (`backend/app/api/routes/ai.py:462`), schemas `AiEquationRequest/Out`
  (`backend/app/schemas/ai.py:423,429`).
- LaTeX safety: `editor-equation.ts` renders KaTeX with `trust:false`;
  `region-formula-dialog.tsx` is the crop review/insert dialog;
  `formula-insertion.ts` builds the display equation; editor nodes
  `NumberedBlockMath` / `InlineMath` / `EquationReference` are registered in
  `editor-extensions.ts:100-116`.
- Equation OCR blocks are produced by `layout.classify_text_block`
  (`MATH_SYMBOLS`, `_is_equation`) in `backend/app/services/layout.py`.

### Plan

1. Add a page-wide equation proposals service + route
   `GET /projects/{id}/pages/{page_id}/equation-proposals` returning, per
   candidate: `page_id`, OCR run/engine, reading-order index, `x/y/width/height`,
   confidence, reason, caption, `block_ids`, and whether a crop transcription is
   available. Reuse `regions._cluster` on `kind == "equation"` blocks; do not
   invent regions with no evidence.
2. Distinguish inline vs display only when reliable (display by default for
   `equation` blocks; do not guess inline from OCR geometry).
3. Frontend: a `PageEquationsDialog` (mirror `page-tables-dialog.tsx` +
   `usePageTableProposals`) that lists candidates and lets the user select one,
   then opens the existing `RegionFormulaDialog` flow for optional
   transcription. Insertion remains user-confirmed; never auto-accept LaTeX.
4. Add i18n keys in both `en` and `my` (workspace namespace).
5. Tests: backend (no OCR, stale run, clustering, reading order, false
   positives); frontend (list/select, invalid LaTeX rejected, no auto-accept,
   manual crop unchanged). Verify `npm run test:web`, `npm run typecheck`,
   `npm run lint`, backend pytest.

### Acceptance

Users can review page-wide equation candidates and selectively
transcribe/insert them; tests cover false positives, invalid LaTeX and the
review flow; manual crop transcription still works.

### Risks

- Transcription requires a configured AI provider; the proposal list must work
  offline and transcription must stay optional.
- Do not duplicate the existing `equation_text` region proposals; either reuse
  the region endpoint or share the clustering helper.

---

## Task 03 — Nested table reconstruction

**Prompt:** `02_SHOULD_HAVE/03_Nested_Table_Separation.md`
**Status:** not started.

### Findings before changing code

- `backend/app/services/table_structure.py`: `_merged_rectangles` (L590)
  intentionally rejects non-rectangular/stepped spans; `_build_grid` (L436) has
  no nesting concept; `_vector_candidates` (L696) builds flat grids;
  `propose_page_tables` (L1367) is page-wide.
- Editor: Tiptap `TableKit` is a flat grid (`editor-extensions.ts:85`);
  `table-insertion.ts` emits flat `rowspan`/`colspan`; `table-candidates.ts`
  models flat proposals.
- Export: `document_export.py` `_table_html` (L523), `_table_markdown` (L547),
  DOCX span placement (L1728-1769), PDF `colspan`/`rowspan` (L2285-2290).
- No nested-table model in the DB; tables are inserted as flat editor content.

### Plan

1. Detect a nested structure only when geometry supports it: an inner grid fully
   inside a parent cell with consistent rules. Do not flatten uncertain
   structures into misleading output.
2. Prefer a conservative, reviewable representation. Tiptap tables likely do not
   support true nesting; if so, represent the inner grid as a separate linked
   table proposal tied to the parent cell (or a nested cell payload the editor
   can render), and expose a manual-correction fallback. Confirm Tiptap support
   before committing to a schema.
3. Preserve parent/child relationships, spans, cell content and reading order in
   the proposal schema (`backend/app/schemas/tables.py`) and shared types
   (`packages/shared-types/src/index.ts`).
4. Verify save/reopen and DOCX/PDF fidelity; add nested fixtures and tests.

### Acceptance

Nested-table fixtures survive review, editing, saving and supported exports
without corrupting the parent structure.

### Risks

- Largest task of the four. Nested editor tables may be unsupported; a separate
  linked table may be the honest, non-destructive fallback.
- Export (DOCX/PDF) nested tables need explicit handling; test both.

---

## Task 04 — Opaque PDF drawing extraction

**Prompt:** `02_SHOULD_HAVE/04_Opaque_PDF_Drawing_Extraction.md`
**Status:** not started.

### Findings before changing code

- `backend/app/services/regions.py` uses `pdf.image_regions` +
  `pdf.drawing_regions` for PDF pages, and runs
  `artwork.artwork_regions` **only when `source_kind != "pdf"`** (`elif
  raster_source`). An opaque/scanned PDF with no readable vector paths and no
  embedded raster image therefore gets no artwork box.
- `artwork.artwork_regions` already detects raster ink clusters from a rendered
  image and needs OCR blocks to mask text.
- The current display asset (`pages.display_asset_id`) is the rendered page, so
  it can be analyzed for PDF pages too, respecting rotation/edits.
- PDF vector/image evidence is skipped when `rotation != 0` or geometry edits
  exist (`regions.py:435-436`).

### Plan

1. For PDF pages, when vector/image evidence yields no figures (or as a
   complement), run `artwork.artwork_regions` on the current display asset with
   the OCR blocks. Label the reason `page_artwork_region` (low confidence) or a
   new `opaque_pdf_region`.
2. Preserve source resolution and crop geometry; do not upscale. The existing
   crop path already uses source pixels.
3. Keep uncertain regions available for manual selection; never auto-accept.
4. Add fixtures for opaque/form-based drawings and compare crops with the source
   page. Tests: opaque PDF figure proposed; text/background not misclassified;
   rotation/edits handled; manual fallback intact.

### Acceptance

Supported drawings extract reliably, or the limitation is clearly reported with
a dependable manual fallback.

### Risks

- Running raster analysis on every PDF page costs CPU; gate it on pages with no
  vector/image figure evidence.
- Avoid double-proposing a figure already found by vector/image signals.

---

## Verification commands (all tasks)

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests -q
npm run test:web
npm run typecheck
npm run lint
```

For UI work, also run `npm run build` and, when the packaged build changes,
`npm run desktop:dist` then `npm run smoke:desktop` (do not publish a release
unless the owner asks).

## Session log

- 2026-11-28: Task 01 done and pushed (`04f0b5f`). Tasks 02-04 not started.
  Add a dated line here after each task with the commit hash and test counts.
