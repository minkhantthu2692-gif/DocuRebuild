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
| 02 | Page-wide equation proposals | done | this task commit |
| 03 | Nested table separation | done | this task commit |
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
**Status:** done.

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

### Result

- Added `regions.propose_page_equations` (`backend/app/services/regions.py`),
  reusing the existing `_cluster`, `clamp_rect`, `already_extracted` and `iou`
  helpers plus the same OCR status/staleness checks as `propose_regions`. It
  returns `status`, `page_id`, page dimensions, OCR run/engine and proposals with
  `key`, `x/y/width/height`, `text`, `display`, `confidence`, `reason`,
  `block_ids` and `reading_index`. Only OCR blocks labelled `equation` are
  proposed, so tables and paragraphs are never offered as equations.
- Nearby equation blocks are merged with the region gap ratio (0.35). After
  filtering, `reading_index` is assigned top-to-bottom, left-to-right. Candidates
  covered by an existing element (>=90% coverage and IoU >=0.5) are skipped, the
  same rule region proposals use.
- `display` is always `true` for an equation OCR block because it is a standalone
  block. Inline math inside a paragraph is not a block of its own, so it is never
  guessed at.
- Added schemas `PageEquationProposalOut`/`PageEquationProposalsOut`
  (`backend/app/schemas/equations.py`), route
  `GET /projects/{id}/pages/{page_id}/equation-proposals`
  (`backend/app/api/routes/equations.py`), registered in `backend/app/main.py`.
- Added shared types `PageEquationProposal`/`PageEquationProposals`
  (`packages/shared-types/src/index.ts`), API client `getPageEquationProposals`
  (`apps/web/src/lib/api.ts`) and hook `usePageEquationProposals`
  (`apps/web/src/hooks/use-equation-proposals.ts`).
- Added `PageEquationsDialog`
  (`apps/web/src/components/workspace/page-equations-dialog.tsx`): lists
  candidates with reading index, display/confidence badges and an OCR text
  preview, plus loading/error/empty/status states. Selecting one saves an
  equation crop with `useCreateElement` and hands it to the existing
  `RegionFormulaDialog`, where the user edits/previews the LaTeX and confirms the
  insert. Added an optional `initialLatex` prop to `RegionFormulaDialog` so the
  OCR text pre-fills the editor without changing the manual crop flow.
- Wired a "Detect equations" button and both dialogs into
  `apps/web/src/components/workspace/ocr-dialog.tsx`.
- Added `ocr.equation.*` keys to both `en` and `my` workspace locales.
- Tests: `backend/tests/test_equation_proposals.py` (4 cases: reading order and
  non-equation false positives, stacked-block clustering, missing OCR run,
  saved-element filtering) and
  `apps/web/src/test/page-equations-dialog.test.tsx` (3 cases: review flow
  creates the crop and calls `onReview`, stale OCR status, empty state). Invalid
  LaTeX rejection is already covered by
  `apps/web/src/test/equation-node.test.ts:177-186`; `RegionFormulaDialog` still
  blocks insert while `renderEquationPreview` reports an error (KaTeX
  `trust: false`).

Files changed: `backend/app/services/regions.py`,
`backend/app/schemas/equations.py` (new),
`backend/app/api/routes/equations.py` (new), `backend/app/main.py`,
`backend/tests/test_equation_proposals.py` (new),
`packages/shared-types/src/index.ts`, `apps/web/src/lib/api.ts`,
`apps/web/src/hooks/use-equation-proposals.ts` (new),
`apps/web/src/components/workspace/page-equations-dialog.tsx` (new),
`apps/web/src/components/workspace/region-formula-dialog.tsx`,
`apps/web/src/components/workspace/ocr-dialog.tsx`,
`apps/web/src/test/page-equations-dialog.test.tsx` (new),
`apps/web/src/i18n/locales/en/workspace.json`,
`apps/web/src/i18n/locales/my/workspace.json`, `CHANGELOG.md`, `ROADMAP.md`,
`docs/should-have/PROGRESS.md`.

### Commands / evidence

- `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_equation_proposals.py -q`
  -> `4 passed in 10.82s`.
- `... -m pytest backend/tests -q` -> `444 passed in 401.57s` (was 440; +4 new).
- `npm run test:web` -> `58 files / 361 tests passed` (was 57/358; +1 file,
  +3 tests).
- `npm run typecheck` and `npm run lint` -> exit 0.

### Limitations

- Proposals depend on the OCR layout labelling a block `equation`; inline math in
  a paragraph is not proposed (manual crop remains available).
- Reviewing a candidate saves an equation crop element immediately (an explicit
  user action). Cancelling the formula dialog leaves that crop in Elements, the
  same behaviour as saving a manual crop before inserting it.
- AI transcription stays optional and requires a configured vision model; the
  list itself works fully offline.
- `display` is always `true` for equation blocks; the inline/display distinction
  is not guessed from geometry.
- Candidates covered by an existing element are hidden, so a re-review means
  editing or deleting that element first.

---

## Task 03 — Nested table reconstruction

**Prompt:** `02_SHOULD_HAVE/03_Nested_Table_Separation.md`
**Status:** done.

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

### Result

- Confirmed the editor has no nested-table node: Tiptap `TableKit` and
  `table-insertion.ts` emit a flat grid, and the DB has no nested-table model.
  Implemented the prompt's explicit fallback: the inner grid is a **separate
  linked proposal** tied to the parent cell, never a flattened parent.
- `backend/app/services/table_structure.py`:
  - `_vector_candidates` now tags every drawn grid with a stable
    `key` (`table-<x>-<y>-<width>-<height>`), its `block_ids`, `nested_count: 0`
    and private `_geometry` (x/y boundary positions, merged rectangles, cell
    owner map, per-cell word buckets, typical word height).
  - `_candidate` (OCR path) also carries `key`, `block_ids` and
    `nested_count: 0`; `_table_key(source)` derives the key from the rectangle.
  - `_link_nested_candidates` links a child vector grid only when its own drawn
    rectangle sits wholly inside one parent cell with `NESTED_INSET = 2.0`; the
    smallest containing parent wins, and the child gets
    `nested = {parent_key, parent_row, parent_column}` while the parent's
    `nested_count` is incremented.
  - `_remove_child_words` clears the child's words from the parent cell (using
    the cell's merged-rectangle anchor) and recomputes `has_confidence`,
    `uncertain_cells`, `empty_cells` and `warnings`, so the nested content is
    not duplicated and the parent cell is visibly empty.
  - `propose_page_tables` truncates to `MAX_CANDIDATES` first, links only the
    returned set (a cut child never leaves a stale parent claim) and strips
    `_geometry` before returning.
- Schemas: added `TableNestedOut` and `TableCandidateOut.key/nested/nested_count`
  (`backend/app/schemas/tables.py`); shared types gained `TableNested` and the
  same candidate fields (`packages/shared-types/src/index.ts`).
- Frontend (`apps/web/src/components/workspace/page-tables-dialog.tsx`):
  candidate list shows "Nested in table N" on a child and "N nested table(s)"
  on a parent; the review view shows a hint naming the parent table and 1-based
  cell; inserting a child writes a `nestedSourceNote` that records the parent
  and cell. A parent keeps the existing page source note. Added
  `ocr.table.nestedIn/containsNested/nestedHint/nestedSourceNote` to both `en`
  and `my` workspace locales.
- Tests:
  - `backend/tests/test_table_structure.py`:
    `test_vector_candidates_link_a_nested_grid_to_its_parent_cell` (unit:
    parent 2x2 at 0-200 x 0-100, child 2x2 at 10-90 x 10-40; child linked to
    parent cell 0,0, parent cell emptied, sibling cells intact) and
    `test_page_candidates_link_a_nested_drawn_table` (PDF upload -> page
    endpoint -> exactly two candidates, linkage, no `_geometry` leakage).
  - `backend/tests/test_docx_export.py` and `test_pdf_export.py`: a parent
    table with an empty cell, the nested source note, then a separate child
    table; both grids survive export and the parent structure is not merged
    back.
  - `apps/web/src/test/page-tables-dialog.test.tsx`: badges, child hint, child
    insert note, and the unchanged parent note.

Files changed: `backend/app/services/table_structure.py`,
`backend/app/schemas/tables.py`, `packages/shared-types/src/index.ts`,
`apps/web/src/components/workspace/page-tables-dialog.tsx`,
`apps/web/src/i18n/locales/en/workspace.json`,
`apps/web/src/i18n/locales/my/workspace.json`,
`backend/tests/test_table_structure.py`, `backend/tests/test_docx_export.py`,
`backend/tests/test_pdf_export.py`,
`apps/web/src/test/page-tables-dialog.test.tsx` (new),
`apps/web/src/test/table-candidates.test.ts`,
`apps/web/src/test/table-review.test.tsx`,
`apps/web/src/test/use-table-draft.test.tsx`, `CHANGELOG.md`, `ROADMAP.md`,
`docs/should-have/PROGRESS.md`.

### Commands / evidence

- `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_table_structure.py -q`
  -> `36 passed in 44.74s`.
- `... -m pytest backend/tests/test_docx_export.py backend/tests/test_pdf_export.py -q -k nested_table`
  -> `2 passed`.
- `... -m pytest backend/tests -q` -> `448 passed in 439.87s` (was 444; +4).
- `npm run test:web` -> `59 files / 364 tests passed` (was 58/361; +1 file,
  +3 tests).
- `npm run typecheck` and `npm run lint` -> exit 0.

### Limitations

- True nested editor tables are unsupported; the child is inserted as a separate
  table with a note naming the parent and cell. This is the prompt's allowed
  non-destructive fallback.
- Only drawn-rule (vector PDF) nesting is detected. A nested table present only
  as OCR word boxes, with no drawn inner grid, is not linked; manual crop
  insertion remains available.
- A child is linked only when it fits wholly inside one parent cell with a 2 px
  inset. Partial or ambiguous nesting is left as independent proposals instead
  of being flattened into a misleading parent.
- The parent cell that held the nested grid is intentionally emptied and flagged
  `empty_cells`; the reviewer decides whether to keep the separate child and can
  edit either table.
- Detection requires the child's own closed rectangular rule grid; a nested
  table drawn without a complete border is not detected.

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
- 2026-11-28: Task 02 done (this task commit). Backend 444 passed; web 58 files /
  361 tests passed; typecheck/lint clean. Task 03 is next.
- 2026-11-28: Task 03 done (this task commit). Backend 448 passed; web 59 files /
  364 tests passed; typecheck/lint clean. Task 04 is next.
