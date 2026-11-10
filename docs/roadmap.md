# Roadmap and current status

This roadmap follows the phased plan in `Prompt.md`. A phase is only marked
complete when its own acceptance checks pass; later-phase functionality is not
presented in the UI until it actually works.

## Status summary

| Phase | Status | Notes |
| --- | --- | --- |
| 0. Foundation and architecture | **Complete** | Monorepo, tokens, contracts, API scaffold, migrations, tests |
| 1. Local storage and project management | **Complete** | App/project DBs, folders, manifest, CRUD, trash |
| 2. Main UI and workspace | **Complete** | Header navigation, dashboard, two-panel workspace, settings, i18n |
| 3. Import and image processing | **Complete** | Image + PDF import, background jobs with progress/cancellation, rotation and non-destructive image adjustments |
| 4. Local OCR and layout detection | **In progress** | Tesseract adapter, review UI and insertion done; table/figure detection pending |
| 5. Element extraction | **In progress** | Manual region crop, local region text extraction, heuristic region suggestions, library, verification and figure/text insertion done; structured table/equation reconstruction pending |
| 6. AI integration and free usage first | Planned | Depends on elements and review model |
| 7. Table, figure and equation reconstruction | Planned | Depends on Phase 5/6 |
| 8. Document editor and export | Partially started | Core editor exists; full model/export pending |
| 9. History, backup and recovery | Planned | Event table exists; no restore UI |
| 10. Desktop, PWA and mobile distribution | Planned | Web app is responsive; no Tauri/PWA yet |
| 11. Final QA and production release | Planned | Requires all previous phases |

---

## Phase 0 — Foundation and architecture (complete)

**Delivered**

- npm-workspaces monorepo with `apps/web`, `backend`, `packages/shared-types`
  and `packages/design-tokens`.
- React + TypeScript + Vite + Tailwind with Radix-based primitives.
- FastAPI app factory, typed error envelopes, security headers, CORS.
- SQLAlchemy project registry and Alembic migrations for the app database.
- Shared TypeScript contracts for settings, projects, pages, documents and meta.

**Verification** — typecheck, lint, unit tests and production build pass.

---

## Phase 1 — Local storage and project management (complete)

**Delivered**

- Local data directory with `app.db`, `projects/` and `trash/`.
- Per-project `project.db`, `manifest.json`, and `source`, `processed`,
  `thumbnails`, `exports`, `backups`, `trash` folders.
- Create, list, open, rename and delete projects; deletion moves folders to trash.
- Project integrity checks when a folder is missing; clear error codes.
- Atomic manifest writes and per-project migration versioning.
- Project creation history event and document bootstrap row.

**Verification** — Pytest CRUD, reopen, deletion and manifest coverage.

---

## Phase 2 — Main UI and workspace (complete)

**Delivered**

- Header-based navigation (no permanent left drawer), dashboard, settings and 404.
- Resizable/collapsible two-panel workspace with persisted split.
- Source viewer controls, thumbnail rail, page navigation and empty states.
- Rich-text editor panel with formatting toolbar, document typeface, counts,
  autosave status and load-error handling.
- Mobile segmented Source/Document workflow.
- Theme, accent, radius, blur, density, text size and motion settings.
- English/Burmese localization with live switching and key-parity tests.
- Reusable empty, skeleton, spinner, dialog, menu, select and segmented controls.

**Verification** — Vitest for layout/appearance/formatting/i18n, browser checks
for theme/language switching and mobile panel switching.

---

## Phase 3 — Import and image processing (complete)

**Delivered**

- Drag/drop and file-picker import for JPG, JPEG, PNG, WebP, BMP and TIFF.
- Backend-provided size and batch limits, client-side pre-validation, localized
  rejection feedback.
- EXIF orientation, checksums, immutable originals, browser-safe display copies.
- WebP thumbnails, page ordering (drag), page deletion and non-destructive
  rotation with reset.
- Zoom, fit, actual size and page navigation; responsive thumbnail rail.
- Asset streaming with content-type and path containment.
- PDF import for text-based, image-based and mixed PDFs, with one page per PDF
  page, immutable original storage, 150 DPI local rendering and WebP thumbnails.
- Embedded PDF text extraction into the existing review model (`pdf-text`,
  null confidence), so text can be corrected, verified or inserted without a
  second extraction UI.
- Password/empty PDF rejection, configurable page limit, honest PDF capability
  reporting, and reference-counted deletion of a PDF shared by many pages.
- PDF rotation re-renders from the original PDF and marks any embedded text run
  stale instead of reusing mismatched text.
- Background import jobs for image and PDF files: persisted job status, page-level
  progress, current filename, cancellation and localized failure codes.
- Imports commit per file and per PDF page, so progress survives long batches.
  Cancelling rolls back the file in progress while keeping files that already
  finished; interrupted jobs are detected after a restart instead of staying
  "running" forever.
- Non-destructive image adjustments stored as JSON on the page: drag-to-select
  crop, four-corner perspective correction, automatic skew estimation and deskew,
  grayscale, contrast, brightness, sharpness, denoise, threshold (B&W), shadow
  removal and background cleanup. Every change is re-rendered from the immutable
  source; the original asset is never modified.
- Before/after preview against the rotated unprocessed page, per-step removal and
  one-click reset, so the processed version is fully reversible.

**Acceptance** — non-destructive imports and edits, visible and localized import
progress/cancellation/failures, and tests covering images, PDFs, cancellation,
failures and Burmese filenames all pass.

**Dependencies** — PyMuPDF for PDF rendering (installed and verified); advanced
image processing uses Pillow with no OpenCV dependency.

---

## Phase 4 — Local OCR and layout detection (in progress)

**Delivered**

- Provider-agnostic OCR service with a Tesseract adapter, runtime engine and
  language-pack detection, and honest unavailable states.
- Persistent `ocr_runs` and `ocr_blocks` tables with status, engine version,
  languages, source asset, rotation, confidence, bounding boxes and reading
  order.
- Bounded local worker pool; OCR never runs on the UI thread and never contacts a
  remote service.
- Source-panel OCR dialog with English, Burmese and mixed-language choices,
  progress polling, confidence badges, editable blocks, per-block verification,
  correction persistence and stale-result detection after page changes.
- Stored results remain reviewable and insertable when Tesseract becomes
  unavailable; the setup state and the existing run are shown together.
- Insert selected blocks into the editor as paragraphs with a localized source
  note; unverified text is visibly marked.
- Capability reporting in `/api/meta`, `/api/ocr/capabilities` and Settings, with
  Tesseract path and language-data setup guidance.
- PDF pages with an embedded text layer are stored as reviewable `pdf-text` runs
  in the same dialog as OCR, clearly labelled with no confidence score and
  invalidated on rotation; image-only PDF pages fall back to local OCR.
- Deterministic layout hints shared by OCR and embedded PDF text: heading, list
  item, caption, equation candidate, table-like grid, running header/footer and
  page number. Labels are review candidates only — they never change extracted
  text, confidence or geometry, and ambiguous blocks stay paragraphs.
- Source-viewer layout overlay: measured bounding boxes for the latest
  successful, non-stale run, a per-kind legend with counts, and explicit
  loading, empty, running, stale and failure states. No box is drawn from a stale
  or incomplete result.
- Backend tests for persistence, correction, verification, stale detection,
  missing language data and unavailable engines, deterministic classification and
  TSV layout wiring; frontend tests for coordinate scaling/clamping and i18n
  parity.

**Remaining before completion**

- Figure (image region) detection inside the OCR layout. The classifier never
  guesses a figure; Phase 5 approximates the band above a figure-like caption, but
  this phase does not mark figures itself.
- Real table structure (rows, cells, merged spans) and equation transcription.
  A table label only marks a text grid; it does not build a table.
- OCR accuracy benchmarks (CER/WER) for English, Burmese and mixed pages using
  fixtures from real documents.
- Optional richer engines (for example PaddleOCR) behind the same adapter, only
  if they can preserve the same review and verification guarantees.

**Current limitation** — Tesseract must be installed locally with `eng` and/or
`mya` traineddata. OCR is not advertised as available otherwise, and Burmese
accuracy depends on scan quality, fonts and language data. No engine is
described as universally free or universally accurate.

---

## Phase 5 — Element extraction (in progress)

**Delivered**

- Manual region selection on the source page: drag a rectangle, or type source
  coordinates directly, then crop the current page image into an immutable PNG in
  `processed/elements/`.
- Persistent `elements` table with page, kind (figure, table, equation), asset,
  source rectangle, caption, manual source, verification and timestamps.
- Per-page region library with insert, verify/unverify and delete. Deletion moves
  the crop to the project's local trash folder.
- Insertion into the Tiptap document as a block figure with an optional caption and
  a localized source note; the crop remains stored in the project.
- Stale indicator when the page image or rotation changed after extraction. The
  saved crop is preserved, but it is never presented as matching the current page.
- Local text extraction from a saved crop through the same Tesseract engine used
  for page OCR. Text, confidence, engine, language and timestamp are stored on the
  element as an unverified proposal; the user can review, correct or insert it.
  Manual transcription and correction work without OCR.
- Reviewable region suggestions derived from the latest local OCR layout. Table
  and equation blocks are clustered into suggestions, and a figure band is
  suggested above figure-like captions. Suggestions are read-only, never saved
  automatically, and prefill the normal extraction dialog. Expected states such as
  no OCR run, stale, failed or missing geometry are reported in the response.
- `element_extraction` and `region_proposals` capability flags, plus English and
  Burmese interface strings.

**Remaining**

- Vision-based region proposals and AI-assisted detection paths (Phase 6).
- Uncaptioned figure detection and artwork separated from its caption; these
  currently require manual selection.
- Structured table cells and equation transcription, which belong to Phase 7.

## Phase 6 — AI integration and free usage first (planned)

- Local providers (Ollama, LM Studio, OpenAI-compatible local servers).
- Free-tier and paid providers behind one adapter with dynamic model discovery.
- Independent Vision, Text/Reasoning and Image Generation profiles.
- Explicit consent before external transmission, usage limits, cost guards,
  rate-limit handling, fallbacks and task routing.
- No paid call without user approval; no silent provider switch.

## Phase 7 — Tables, figures and equations (planned)

- Editable tables with merge/split, headers, alignment and comparison view.
- Structured figure representation and optional reconstruction with approval.
- LaTeX editing and live preview; validated OMML export for Word.
- Uncertain cells/symbols are marked for review, never invented.

## Phase 8 — Document editor and export (partially started)

**Current** — headings, paragraphs, lists, blockquotes, code, alignment, inline
marks, undo/redo and autosave.

**Pending** — tables, images, captions, equations, footnotes, links, page layout,
headers/footers, page numbers, find/replace, DOCX/TXT export and OMML validation.

## Phase 9 — History, backup and recovery (planned)

- Document revisions, processing/AI/export history and version comparison.
- Selective restore and export history.
- Project backup/restore with verification and conflict detection.
- Editor undo/redo stays separate from revision history.

## Phase 10 — Desktop, PWA and mobile distribution (planned)

- Tauri desktop shell with a Python sidecar and packaging limits documented.
- PWA install/offline shell where browser capabilities allow.
- Camera import and optional secure pairing to a user-owned processing host.
- No public backend exposure by default.

## Phase 11 — Final QA and production release (planned)

- Full accessibility, responsiveness and performance pass.
- Installation, upgrade and recovery documentation.
- Security review, dependency audit, backup/restore drill.
- Release notes and versioned migrations.

---

## Cross-cutting limitations and risks

- **Burmese OCR is hard.** Fonts, diacritic order and Zawgyi legacy text require
  careful benchmarking. No conversion is ever automatic.
- **Offline processing is bounded by hardware.** Browser-only PWA builds cannot
  run arbitrary Python/PyTorch stacks; capabilities must be reported honestly.
- **Large documents need streaming.** Imports stream uploads and PDFs are rendered
  one page at a time as background jobs with progress and cancellation. Cancellation
  is cooperative: it is checked between files and PDF pages, so one very large page
  render or image decode still has to finish before the job stops.
- **SQLite on network shares is unsafe.** Connected devices must use the local
  API, not direct database access.
- **Dependency audit.** ESLint/TypeScript-ESLint currently pull a vulnerable
  `minimatch` (moderate, development-only). Runtime dependencies are clean of
  critical advisories after the Tiptap 3 and Vitest 5 upgrades.
- **No revision history yet.** Autosave reduces loss but does not replace
  backups. Do not use this build as the only copy of important work.

## Phase 3 definition of done (met)

1. Advanced image processing operations are non-destructive and reversible.
2. Import progress, cancellation and failures are visible and localized.
3. Backend and frontend tests cover the new paths, including Burmese filenames.
4. Documentation and capability flags match the implemented behaviour.
5. Phase 3 acceptance checks pass for images, PDFs and processed-version restore.
