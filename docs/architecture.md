# Architecture

This document describes the DocuRebuild architecture as implemented. It is
intentionally honest about what is still a placeholder for later phases.

## System overview

```text
┌─────────────────────────────┐        ┌──────────────────────────────────┐
│ Web client (apps/web)       │  /api  │ Local API (backend/app)          │
│ React + Vite + Tailwind     │ ─────► │ FastAPI + SQLAlchemy             │
│ Tiptap document editor      │        │ Pillow + PyMuPDF                 │
│ i18next (en / my)           │        │ SQLite (app + per-project)       │
└─────────────────────────────┘        └───────────────┬──────────────────┘
                                                       │
                                       ┌───────────────▼──────────────────┐
                                       │ Local data directory            │
                                       │ app.db + projects/<id>/...      │
                                       └──────────────────────────────────┘
```

Both processes run on the user's machine. Vite proxies `/api` to the FastAPI
server during development. The production web build is a static bundle that talks
to the same local API; the API is not intended to be exposed publicly.

## Backend modules

| Module | Responsibility |
| --- | --- |
| `app.main` | App factory, CORS, security headers, route registration, migrations |
| `core.config` | Environment-driven settings, data paths, import limits |
| `core.errors` | Typed application errors and JSON error envelopes |
| `core.handlers` | Global exception handlers |
| `core.storage` | Atomic JSON writes, safe relative path resolution |
| `db.models` | Application database: project registry and settings |
| `db.project_schema` | Per-project SQLite schema and migrations |
| `db.session` | SQLAlchemy engine/session and Alembic migration runner |
| `services.projects` | Project CRUD, manifest, directory layout, trash, history |
| `services.pages` | Import validation, per-file/per-page import execution with progress and cancellation, image processing, display copies, thumbnails, PDF page records, rotation, ordering, stored-edit rendering, reference-counted deletion |
| `services.imports` | Import job lifecycle: bounded worker, persisted progress, cooperative cancellation, interrupted-job recovery, localized failure codes |
| `services.image_edits` | Canonical edit validation, geometry pipeline (crop/perspective/deskew), filter pipeline (grayscale, contrast, brightness, sharpness, denoise, threshold, shadow/background cleanup) and skew estimation |
| `services.pdf` | PDF open/validation, page rendering, embedded text extraction, capability detection |
| `services.layout` | Shared deterministic block classification (heading, list, caption, equation, table-like grid, running header/footer, page number) for OCR and embedded PDF text |
| `services.documents` | Document row, Tiptap JSON persistence, timestamps, coalesced revision snapshots, manual checkpoints and restore |
| `services.document_export` | Deterministic Tiptap-to-Markdown/TXT/DOCX/PDF rendering, escaping, OMML equations, figure embedding, native footnotes, PDF layout and download names |
| `services.project_backup` | Verified local zip creation, safe validation/extraction and additive restore as a new project |
| `services.backup_crypto` | Optional `.drbz` container for downloaded backups: scrypt key derivation, chunked AES-256-GCM, password and corruption errors |
| `services.local_backups` | Local backup vault: verified copy creation, retention pruning, safe name resolution and opt-in automatic copies |
| `services.page_restore` | Page-scoped selective restore: staged archive inspection, short-lived selection tokens and additive page/asset/OCR/element copying |
| `services.elements` | Manual region extraction: source-pixel validation, immutable crops, element verification, staleness and trash-safe deletion |
| `services.regions` | Deterministic, read-only region suggestions from the latest OCR layout |
| `services.settings` | Persisted appearance, language, editor, AI profile, vision model and request-limit settings |
| `services.ocr` | Tesseract detection, language packs, bounded OCR jobs, block persistence, corrections, staleness |
| `services.ai` | Local provider catalog, URL and remote-consent validation, Ollama/OpenAI-compatible probe and model discovery, OCR cleanup proposals, vision region requests, listing and review decisions |
| `services.ai_vision` | Page-image encoding, normalized-to-source rectangle mapping and filtering for optional vision region proposals |
| `services.ai_usage` | Local AI request metadata, rolling-window request counting and usage summaries |
| `app.scheduled_backup` | Optional one-pass CLI entry point for external schedulers: creates due automatic copies, respects saved preferences and reports failures |
| `api.routes.*` | HTTP surface (`/api/...`) |

### Storage model

The application database (`app.db`) contains only global state:

- `projects` — id, name, description, directory, timestamps
- `app_settings` — key/value JSON (appearance, language, editor, export layout, local AI profile, vision model, request limit and local backup preferences)
- `ai_usage` — local AI request metadata: provider, model, task, outcome, error code, project/page/block ids and timestamp; never document text
- `schema_migrations` — created by Alembic

Each project owns a portable folder and its own `project.db`:

- `documents` — Tiptap JSON content and plain text
- `document_revisions` — previous document states: exact Tiptap JSON, plain text, capture source (`autosave`/`manual`) and timestamp; newest 100 kept per project
- `assets` — relative path, MIME type, size, checksum, dimensions
- `pages` — page order, source/display/thumbnail asset references, rotation,
  `pdf_page_number` for PDF pages, status, and an `edits` JSON document holding the
  ordered geometry steps plus filter settings
- `history_events` — append-only local activity log: event type, human summary, small JSON metadata payload (counts, formats, sizes, ids) and timestamp; read by the project activity dialog
- `jobs` — background import jobs: status, progress, total/imported pages, current file, payload (file counts/names), error code/message and timestamps
- `ocr_runs` — page extraction attempts: status, engine/version, languages, source asset, rotation, mean confidence, error, timestamps; embedded PDF text uses `engine = pdf-text` and a null confidence
- `ocr_blocks` — reviewable text blocks with bbox, confidence, kind, line/word counts, correction and verification flags
- `elements` — extracted regions: page, kind, immutable crop asset, source asset id, source-pixel rectangle, caption, manual/acquisition source, verification, extracted text with confidence/engine/language provenance, correction flag and timestamps
- `ai_suggestions` — unverified AI proposals: page, OCR block, task (`ocr_cleanup`), original and proposed text, provider, model, base URL, status (`pending`/`accepted`/`rejected`) and timestamps
- `schema_migrations` — per-project migration versions

Project folder layout:

```text
projects/<project-id>/
  manifest.json
  project.db
  source/       immutable originals
  processed/    browser-safe display copies
  thumbnails/   WebP thumbnails
  exports/      future exports
  backups/      reserved; archives live in the shared backup vault
  trash/        per-project runtime trash
```

The data directory also holds `app.db`, a shared `trash/` for deleted projects, a
shared `backups/<project_id>/` vault for verified copies and a short-lived `tmp/`
folder used only while building or restoring a backup. Relative asset references are
stored in SQLite so a project folder can be moved without rewriting paths.
`resolve_within` rejects path traversal.

### Import rules

Images:

- Accepted: JPG, JPEG, PNG, WebP, BMP, TIFF.
- Files are validated by extension, size limit and Pillow decode.
- EXIF orientation is applied once at import.
- Browser-safe formats are stored as immutable originals.
- BMP/TIFF originals are preserved and a PNG display copy is written to
  `processed/`.
- Rotations create a new display copy; the original is never modified.
- Thumbnails are WebP, bounded by a maximum edge, and cached by asset id.

PDFs:

- Accepted when PyMuPDF is importable; `/api/meta.capabilities.import_pdf`
  reflects the real state and the client hides/rejects PDF selection otherwise.
- The uploaded PDF is moved once into `source/` and never rewritten. All pages of
  that PDF reference the same `original_asset_id`.
- Every page is rendered at `pdf_render_dpi` (default 150) into
  `processed/<page-id>-page.png`; rendering happens one page at a time inside a
  backend threadpool.
- `pages.pdf_page_number` records the 1-based index inside the source PDF.
- Embedded text (`page.get_text("dict", sort=True)`) is converted from PDF points
  to rendered pixels and stored as an `ocr_runs` row with `engine = pdf-text`,
  `mean_confidence = NULL` and block confidence `NULL`. These runs use the display
  asset id as their source so they are not stale immediately.
- Password-protected, empty and over-limit PDFs are rejected before any project
  files are written. `pdf_max_pages` defaults to 1,000.
- Rotation re-renders the page from the immutable PDF and rotates that render;
  it never rotates/resamples the previous display copy.
- Deletion is reference-counted: the shared PDF asset file is moved to project
  trash only when the last page that references it is deleted.

Batch imports:

- Uploads are streamed to the local temp folder and validated before a job starts,
  so unsupported, oversized, empty, unreadable or encrypted files are rejected
  synchronously without creating project files.
- A job row is persisted before work begins. The executor commits each file (and
  each PDF page) in its own transaction, updating `imported_pages`, `progress` and
  `current_file` as it goes.
- Cancellation is cooperative and checked between files and pages. A cancelled or
  failed file is rolled back with its pages, assets and files; files that already
  completed are kept for jobs. The synchronous `/pages/import` wrapper keeps
  all-or-nothing semantics for simple clients.
- In-memory cancellation events identify live workers. A persisted job with an
  active status but no live event is treated as interrupted and marked failed with
  `import_interrupted` instead of staying "running" after a restart.

### API surface (current)

```text
GET    /api/health
GET    /api/meta
GET    /api/ocr/capabilities
GET    /api/ai/providers
GET    /api/ai/usage
POST   /api/ai/probe
GET    /api/settings
PATCH  /api/settings
GET    /api/projects
POST   /api/projects
GET    /api/projects/{id}
PATCH  /api/projects/{id}
DELETE /api/projects/{id}
POST   /api/projects/{id}/open
GET    /api/projects/{id}/backup
POST   /api/projects/{id}/backup
GET    /api/projects/{id}/backups
POST   /api/projects/{id}/backups
GET    /api/projects/{id}/backups/{filename}
DELETE /api/projects/{id}/backups/{filename}
POST   /api/projects/{id}/backups/{filename}/restore
POST   /api/projects/{id}/backup/selection
POST   /api/projects/{id}/backups/{filename}/selection
POST   /api/projects/{id}/backup/selection/{token}/pages
POST   /api/projects/restore
GET    /api/projects/{id}/document
PUT    /api/projects/{id}/document
GET    /api/projects/{id}/document/export?format=markdown|txt|docx|pdf
GET    /api/projects/{id}/document/revisions?limit=50
POST   /api/projects/{id}/document/revisions
GET    /api/projects/{id}/document/revisions/{revision_id}
POST   /api/projects/{id}/document/revisions/{revision_id}/restore
GET    /api/projects/{id}/history?limit=50
GET    /api/projects/{id}/pages
POST   /api/projects/{id}/pages/import
POST   /api/projects/{id}/imports
GET    /api/projects/{id}/imports
GET    /api/projects/{id}/imports/{job_id}
POST   /api/projects/{id}/imports/{job_id}/cancel
POST   /api/projects/{id}/pages/{page_id}/rotate
PATCH  /api/projects/{id}/pages/{page_id}/edits
POST   /api/projects/{id}/pages/{page_id}/edits/reset
GET    /api/projects/{id}/pages/{page_id}/edits/base
GET    /api/projects/{id}/pages/{page_id}/deskew-estimate
DELETE /api/projects/{id}/pages/{page_id}
PUT    /api/projects/{id}/pages/order
GET    /api/projects/{id}/pages/{page_id}/ocr
POST   /api/projects/{id}/pages/{page_id}/ocr
GET    /api/projects/{id}/ocr/runs/{run_id}
PATCH  /api/projects/{id}/pages/{page_id}/ocr/blocks/{block_id}
GET    /api/projects/{id}/pages/{page_id}/ai-suggestions
POST   /api/projects/{id}/pages/{page_id}/ocr/blocks/{block_id}/ai-suggestions
PATCH  /api/projects/{id}/ai-suggestions/{suggestion_id}
GET    /api/projects/{id}/pages/{page_id}/elements
POST   /api/projects/{id}/pages/{page_id}/elements
GET    /api/projects/{id}/pages/{page_id}/region-proposals
PATCH  /api/projects/{id}/elements/{element_id}
POST   /api/projects/{id}/elements/{element_id}/text
PATCH  /api/projects/{id}/elements/{element_id}/text
DELETE /api/projects/{id}/elements/{element_id}
GET    /api/projects/{id}/assets/{asset_id}/file
```

Errors use `{ "detail": { "code": "...", "message": "..." } }`; the client maps
codes to localized messages.

## Frontend architecture

```text
src/
  App.tsx                 routes, providers, lazy pages
  pages/                  Dashboard, Workspace, Settings, 404
  components/layout/      header, shell, status bar, brand
  components/projects/    project dialogs and cards
  components/workspace/   SourcePanel, EditorPanel, OcrDialog, ElementsDialog, workspace actions
  components/ui/          reusable Radix-based primitives
  hooks/                  React Query data hooks and breakpoints
  lib/                    API client, formatting, appearance, layout, validation
  providers/              appearance/language synchronization
  i18n/                   namespaces and locale resources
```

### Workspace behaviour

- Two-panel layout with a persisted, resizable split.
- Panels can be collapsed; the split ratio is stored locally.
- Below the `lg` breakpoint, a segmented control switches between Source and
  Document as a single-panel mobile workflow.
- The editor loads the document once (`staleTime: Infinity`), enables editing
  without emitting a synthetic update, and autosaves 900 ms after the last
  change.
- A single save is in flight at a time; failures show a retry action and the
  dirty state remains visible. `Ctrl/Cmd+S` saves immediately.
- Find/replace works on ProseMirror document positions from
  `lib/editor-search.ts`. A run is a sequence of contiguous text nodes, so a match
  can span bold/italic boundaries but not paragraphs or hard breaks. Replace and
  replace-all use transactions that keep the marks at the matched position, and
  replace-all applies from the end of the match list so earlier positions stay
  valid. Both stay in the editor undo history. `Ctrl/Cmd+F` opens the bar and
  preselects the current single-line selection when there is one.
- Links use the StarterKit link mark with `openOnClick: false` so clicking a link
  does not leave the app while editing. `lib/link.ts` normalises the address before
  the mark is set: only `http`, `https` and `mailto` are accepted, a bare domain
  gains `https://`, and unsafe or ambiguous values are rejected with an inline
  error. The same validator is passed to the extension as `isAllowedUri`, so
  auto-detected and pasted links cannot bypass the dialog. The link dialog can
  edit or remove an existing link, and `Ctrl/Cmd+K` opens it; the shortcut is
  ignored while the dialog is open or the editor is read-only.
- The editor extension list is defined once in `lib/editor-extensions.ts` and used
  by both the React editor and the tests, so a node cannot work in a test while
  being absent from the real editor. StarterKit, text alignment, the figure node,
  the block and inline equation nodes, the placeholder and `TableKit` live there.
- A best-effort flush runs when leaving the workspace. It complements the document
  version history but is not a substitute for a project backup.
- Imports start a job and poll it every 500 ms while active. The progress panel
  shows completed/total pages, the current filename and a cancel action. The page
  list is refreshed when the job settles, so a cancelled file cannot leave
  thumbnails pointing at rolled-back assets. An active job found on load is
  reattached rather than duplicated.

### Image adjustment workflow

- The edits dialog sends the complete ordered edit document to
  `PATCH /api/projects/{id}/pages/{page_id}/edits`; the backend validates and
  normalizes it before storing it on the page row.
- Rendering always starts from the immutable source: rotation is applied first,
  then geometry steps in order (crop, perspective, deskew), then filters. The
  result becomes the page display copy; the source asset is never rewritten.
- `GET .../edits/base` renders the rotated page without processing for
  comparison. `POST .../edits/reset` clears stored edits. Removing a step
  re-renders from the source, so geometry changes stay reversible.
- Deskew estimation scans a Pillow-rendered copy for the dominant skew angle and
  returns the correction angle; the dialog applies it as a normal geometry step,
  not as an irreversible transform.
- Each save or reset appends a local history event and updates the page timestamp,
  which the client uses to invalidate cached display images.

### Text extraction workflow

- The source panel starts extraction for the active page. For image pages and
  image-only PDF pages this is local OCR. For PDF pages with an embedded text
  layer, import already created a reviewable `pdf-text` run, and the same dialog
  opens it.
- The dialog calls `GET /api/ocr/capabilities` and shows an honest setup state
  when Tesseract or a requested language pack is missing; no request is sent to a
  cloud service.
- OCR runs are executed by the backend in a bounded `ThreadPoolExecutor`; the
  client polls the run until it reaches `succeeded` or `failed`. For PDF pages the
  backend reads the rendered display copy, not the original PDF bytes.
- Each run stores engine, version, requested languages, source asset id, page
  rotation and timestamps so the result can be audited and invalidated.
- Embedded PDF runs display `Embedded PDF text`, the PyMuPDF version and
  `No OCR confidence score`; they never borrow a fake confidence value. The
  action button says `Run OCR` (not `Run OCR again`) because OCR is a different
  method from the embedded layer.
- Results are split into reviewable blocks with bounding boxes and confidence.
  Low-confidence blocks are flagged; every block can be edited and marked as
  verified, and corrections are persisted in `ocr_blocks`.
- Layout classification is deterministic and conservative. Page numbers and
  running headers/footers require page-margin geometry, captions and equations
  need a label or a math-symbol pattern, and a table label requires at least two
  lines with aligned wide inter-word gaps. Ambiguous blocks stay `paragraph`.
  Labels are review candidates: they never change the text, geometry or
  confidence, and nothing is marked verified on the user's behalf.
- The source viewer draws a measured bounding-box overlay for the latest
  successful, non-stale run. Source coordinates are scaled to the rendered image
  (fit, zoom, actual size and centring), clamped to the image edges, and blocks
  with incomplete geometry are skipped. Loading, empty, running, stale and failed
  runs show an explanatory state instead of boxes. The overlay is visual only and
  never edits the document.
- Existing results stay reviewable and insertable even when the engine is later
  unavailable or a language pack is missing; the dialog shows the setup banner
  and the stored run together instead of hiding the user's prior work.
- A run becomes stale when the page image or its rotation changes after
  completion; the UI surfaces this instead of silently reusing stale text. This
  also applies to embedded PDF text after a rotation.
- Selected blocks are appended to the Tiptap document through the workspace
  actions context. The insertion is a normal document edit and is autosaved; an
  optional localized source note records the page and verification status.
- OCR settings are environment-driven: `DOCUREBUILD_TESSERACT_CMD`,
  `DOCUREBUILD_TESSDATA_DIR`, timeout, maximum edge and worker limits. PDF
  rendering uses `DOCUREBUILD_PDF_RENDER_DPI` and `DOCUREBUILD_PDF_MAX_PAGES`.
  These are reported through capabilities rather than exposed as arbitrary UI
  controls.
- The engine command is resolved in a fixed order: the explicit
  `DOCUREBUILD_TESSERACT_CMD` value, then `tesseract` on `PATH`, then standard
  install locations (`C:\Program Files\Tesseract-OCR` on Windows and common
  Unix prefixes). The resolved path is used for both detection and OCR, and is
  returned in capabilities so a fallback is never silent. The Windows installer
  does not add Tesseract to `PATH`, so this fallback is what makes a normal
  installation usable without extra configuration.
- Tesseract is invoked with `-c tessedit_create_tsv=1` rather than the optional
  `tsv` config file, so a minimal custom `tessdata` directory works as long as it
  contains the required traineddata files. If the engine returns plain text
  instead of structured TSV, the run fails explicitly instead of reporting an
  empty success.

### Region extraction workflow

- A toolbar toggle turns the source viewer into a marquee. Pointer positions are
  mapped from the rendered image through the measured `ImageFrame` to source
  pixels, clamped to the page and rejected below 8 × 8 pixels. The extraction
  dialog also exposes numeric X/Y/width/height fields, so the same workflow works
  without a mouse.
- `POST .../elements` validates the rectangle against the actual page asset, crops
  it with Pillow and writes `processed/elements/<element-id>.png`. The crop is an
  immutable asset; the page original and display copies are never modified.
- `elements.source_asset_id` records which page asset produced the crop. If the
  page is rotated or re-rendered later, the element is marked stale instead of
  silently assumed to match the new page.
- Elements remain proposals until the user marks them verified. The per-page
  library can insert, edit the caption, verify/unverify and delete them; deletion
  moves the crop to `trash/elements/<id>/` and leaves the page untouched.
- `POST .../elements/{id}/text` runs the same local Tesseract adapter on the stored
  crop, synchronously because crops are small. It stores the text, mean confidence,
  engine, engine version, language list and timestamp on the element. The result is
  an unverified proposal; the user can correct it with `PATCH .../text` or type text
  manually. No external service is called, and an unavailable engine returns a
  localized `ocr_unavailable` error instead of empty text.
- Corrected text keeps its OCR provenance (`text_engine`, `text_languages`) and is
  marked `text_corrected`, so the library does not present manual edits as raw OCR.
- Insertion uses a custom atom `figure` Tiptap node rendered as
  `figure/img/figcaption`. The caption and localized source note are stored on the
  node, so they survive document saves. The document references the project asset
  by URL; the crop itself is not embedded or re-encoded. Extracted text is inserted
  through the normal text insertion path with a provenance note.
- A selected figure can be edited through the toolbar caption dialog. Editing
  applies only to a real node selection (`selectedFigure` ignores a collapsed
  cursor), writes only the `caption`, `alt` and optional `numbered` attributes, and
  leaves `src`, `note`, `width` and `height` untouched, so provenance cannot be
  rewritten by a caption correction. The change is ordinary document content:
  autosave, versions, backups and Markdown/plain-text/Word export all see the
  corrected caption without special handling. Applying re-reads the stored position
  first, so a figure removed while the dialog was open is never replaced by whichever
  node now sits there.
- A figure can carry an optional display-only number. The flag is stored on the
  node, a `data-figure-label` span is rendered in the caption, and the visible
  `Figure n.` prefix comes from a CSS counter that resets on the editor root and
  increments only on numbered figures. The caption text is never rewritten, so a
  figure that already has a typed number keeps it exactly; the dialog says so. The
  label cannot be selected or edited as content, and numbering follows document
  order across inserts, deletes and moves.
- A numbered figure can be cited from prose with the inline atom `figureReference`.
  The node stores only `targetId`, the stable figure id generated on insertion. The
  visible `Figure n` label is resolved on every transaction by
  `numberedFigureTargets`, which walks the document, counts numbered figures and
  maps each id to its current number. Moving or renumbering a figure therefore
  updates every citation without touching stored text, and the number is never
  written into the citation node. A target that was deleted, unnumbered or is
  otherwise absent renders as `Figure (missing)` (localized) with a destructive
  style instead of silently becoming a different figure's number. The id is stored
  on the figure attrs; a numbered figure created before ids existed still consumes a
  number, so ids and numbers cannot drift apart.
- No external detector or AI model is invoked. Region text uses the same local
  Tesseract adapter as page OCR; `element_extraction` in `/api/meta` reports the
  manual region and local text paths.
- `GET .../pages/{id}/region-proposals` returns deterministic suggestions derived
  from the latest local OCR run. It is read-only, computes everything on request
  and persists nothing.

### Region suggestions

- Suggestions reuse the OCR text layout instead of a vision model, so they stay
  free, local and explainable. Three signals are recognised:
  `table_text_grid` (merged OCR `table` blocks), `equation_text` (OCR `equation`
  blocks) and `figure_caption_gap` (the empty band above a `caption` block whose
  text starts with figure/diagram/chart/plate/photo/image/illustration).
- Clustering merges vertically adjacent blocks of the same kind only when their
  columns overlap and the gap is small relative to their height, so a table split
  into several blocks becomes one suggestion. Rectangles are padded by 0.8 % of
  the page, clamped to the page, deduplicated by IoU 0.85, capped at 20 and
  dropped when an existing element already covers them.
- The response reports a status rather than an error for expected states:
  `ready`, `no_ocr_run`, `ocr_not_ready`, `ocr_failed`, `ocr_stale`,
  `no_geometry`. A run is stale when its `source_asset_id` or `rotation` no longer
  matches the page.
- The frontend draws the suggestions as dashed buttons over the measured image
  frame. Choosing one opens the normal extraction dialog prefilled with the kind,
  caption and rectangle and marked as a suggestion; nothing is saved until the
  user confirms through the existing crop path.
- Limitations: uncaptioned figures, artwork separated from its caption and regions
  OCR did not read are not suggested, and no cell or equation structure is
  derived. `region_proposals` in `/api/meta` advertises the feature.

### Document tables

- `TableKit` from `@tiptap/extension-table` provides `table`, `tableRow`,
  `tableHeader` and `tableCell`. Column resizing is disabled on purpose: stored
  pixel widths are bound to one screen size, and Markdown cannot represent them. A
  shared `doc-table` class provides styling through existing design tokens.
- The insert dialog is the only way cell content enters a new table. It clamps the
  requested size with `lib/editor-table.ts` (`TABLE_MIN_SIZE = 1`,
  `TABLE_MAX_SIZE = 10`) and inserts empty cells plus an optional header row. No
  OCR, AI or vision text is written into a cell.
- When the selection is inside a table, the menu enables `addRowBefore/After`,
  `addColumnBefore/After`, `deleteRow`, `deleteColumn`, `toggleHeaderRow` and
  `deleteTable`. Buttons use `editor.can()` so a command that the current schema
  cannot run stays disabled instead of failing silently.
- Cell merge and split use the `TableKit` commands with a ProseMirror cell
  selection: `mergeCells()` combines the selected rectangle into one cell with
  `colspan`/`rowspan`, and `splitCell()` restores the split cells when the cursor is
  inside a merged cell. Both entries are disabled outside a suitable table
  selection, and a short menu hint explains that a multi-cell selection is needed.
  Merging never discards text: the non-empty content of the absorbed cells is
  appended into the merged cell instead of being deleted.
- The stored shape is `table > tableRow > tableCell|tableHeader > paragraph >
  text`, with `colspan`, `rowspan` and `colwidth` attributes. It is ordinary Tiptap
  content, so document saves, revisions and project backups need no table-specific
  code.
- Export reads the stored spans rather than the screen. A table containing any
  `colspan`/`rowspan` greater than 1 is written as HTML so the merged structure and
  every cell's text survive. Per-cell vertical alignment and column resizing are
  still not implemented.

### Equations

- `NumberedBlockMath` (an extension of `BlockMath`) and `InlineMath` from
  `@tiptap/extension-mathematics` add the `blockMath` and `inlineMath` atoms.
  Block math stores `latex` plus an optional `numbered` flag; inline math stores only
  `latex`. Only source and the flag are stored in the document; the editor renders
  the source with KaTeX in a node view. KaTeX and its stylesheet are bundled locally,
  so rendering works offline and makes no request.
- The toolbar has one button for a display equation and one for an inline formula.
  The shared dialog is the only insertion path: it previews the typed source
  through `renderEquationPreview` with `throwOnError: true` and `trust: false`
  (`displayMode` follows the equation kind); blank or invalid LaTeX disables
  insertion instead of saving a broken equation. Pasting LaTeX is supported through
  the normal textarea, but the app does not recognise equations from OCR or AI yet.
- The inline extension's automatic `$$...$$` input rule is disabled, so typing
  dollars in prose is never silently converted into math. This keeps the dialog the
  single, explicit insertion path.
- A selected math node is edited in place with `updateBlockMath` or
  `updateInlineMath` at its stored position; otherwise the dialog inserts a new
  node. `selectedEquation` ignores a collapsed cursor, and applying re-reads the
  stored position through `equationAt` (bounds-checked because `nodeAt` throws
  outside the document), so a node removed while the dialog is open can never be
  replaced by another one.
- Because the nodes are ordinary document content, autosave, revisions, project
  backups and restore need no equation-specific handling. The dialog and node views
  use existing design tokens and locale strings; block and inline math have
  separate node-view styling.
- Equation numbers are display-only. A block equation stores `numbered: true` and
  the node view adds a `numbered-equation` class; the label comes from a CSS counter
  that resets on the editor root and increments only on numbered equations, so
  inserting, deleting or moving equations renumbers the document without touching
  any stored source. The label is `pointer-events-none`, so it cannot be selected or
  edited as content, and inline math never carries the flag.
- A numbered display equation also gets a stable `id` and can be cited from prose
  with the inline atom `equationReference`, which stores only `targetId`. It reuses
  the same `createReferenceNode` / `resolveReferenceLabel` implementation as figure
  references, so the two cannot drift. `numberedEquationTargets` walks the document,
  counts numbered display equations and maps each id to its current number; the
  visible `Equation (n)` label is resolved on every transaction. A deleted,
  unnumbered or inline target renders as `Equation (missing)` in a destructive style
  rather than silently becoming another number. A numbered equation created before
  ids existed still consumes a number, so ids and numbers cannot drift apart.
- Export preserves that numbering deterministically: while traversing, a numbered
  display equation emits a NUL-delimited token, and `render_markdown` /
  `render_text` replace the tokens in document order with `(1)`, `(2)`, … after the
  `$$` block or LaTeX line. Unnumbered equations export unchanged, and the token is
  resolved before the string is returned, so no control character reaches the file.
- Equation references are resolved the same way as figure references. A pre-pass
  (`_equation_number_map`) maps each numbered display equation id to its
  document-order number, traversal writes `\x00equation-ref:<id>\x00`, and the
  post-pass replaces each token with `Equation (n)` or `Equation (missing)`. Word
  export uses the same map through `_DocxRenderer.equation_numbers`. Inline math is
  never counted, so it cannot become a target.

### Footnotes

- A footnote is an inline atom `footnote` that stores its own `text` plus a stable
  `id`. The visible number is generated from document order by `footnoteNumberAt`,
  so inserting, deleting or moving a note renumbers the rest without rewriting any
  stored text. The number is never saved and never typed by the user.
- The toolbar dialog is the only insertion and editing path. Empty text is refused,
  and a selected note is re-read through `footnoteAt` before saving, so a node
  removed while the dialog is open cannot be replaced by another one. Removing a
  note deletes the atom.
- The node view renders the number as a superscript with a localized `aria-label`
  and the note text as its `title`; the stored text is not shown inline, so it
  cannot be mistaken for document prose. `translateWorkspace` is shared with the
  reference node views, so a node view that renders before i18n is initialized still
  interpolates its fallback instead of showing `{{n}}`.
- `footnoteTexts` and `footnoteNotesText` append a readable `Notes:` section to the
  stored `plain_text`, because `editor.getText()` cannot see atom attributes. Every
  note keeps its document-order slot, so the preview numbering matches the marker
  and the exported definition. That keeps version previews and diffs aware of
  footnote edits without changing the document content.
- Footnotes are not detected automatically: OCR and AI never create one, and the
  text is typed by the user from the source page.

### Document export

- The document is exported by the backend from the stored Tiptap JSON, not by the
  browser, so the file matches what autosave persisted and no second editor
  serializer can drift from it.
- `GET /api/projects/{project_id}/document/export?format=markdown|txt|docx|pdf` reads
  the document row and returns an attachment. `format` is a required enum with a
  `markdown` default; unknown values are rejected by request validation (`422`).
  Text formats use `text/markdown` or `text/plain` with `charset=utf-8`; DOCX uses
  the WordprocessingML content type and PDF `application/pdf`. Every response carries
  a `Content-Disposition` header containing both an ASCII fallback filename and an
  RFC 5987 `filename*` for Unicode project names.
- `export_document` returns `(bytes, filename, content_type)` for all formats, so the
  route can record the exact byte size and the response can serve a binary body.
- Export preferences live in `app_settings.export` as
  `{ pdf_page_size, pdf_margin }`. Both are closed enums (`a4|letter`,
  `narrow|normal|wide`), so an unknown value is rejected by request validation
  (`422`) instead of silently falling back. The values are presets rather than
  free-form measurements, which keeps the PDF geometry deterministic and testable;
  the frontend defaults mirror the backend defaults (`a4`, `normal`). Only PDF
  rendering reads them, so Markdown, TXT and DOCX output is unaffected.
- `services.document_export` maps every known node deterministically: doc,
  paragraph, heading (levels 1–6, clamped), bullet/ordered lists (including
  `start`), listItem, blockquote, codeBlock (fence widened when the code contains
  backticks), horizontalRule, hardBreak, table, text marks, the custom `figure`,
  `figureReference`, `equationReference` and `footnote` atoms and the math nodes.
  Markdown and TXT share that traversal; DOCX uses a separate `_DocxRenderer` and
  PDF a `_PdfRenderer`, both over the same JSON.
- Markdown output escapes `` \ ` * _ [ ] < > `` and line-start markers (`#`,
  `-`, `+`, `>`, `1.`/`1)` and `---`), so extracted OCR text cannot become
  structure or raw HTML. Code spans are built from raw text so their content stays
  literal. Links are emitted only for `http`, `https` and `mailto`; any other
  target is dropped while the link text is kept.
- Figures never export their `src`. The local asset URL is meaningless outside the
  project, so the node becomes `[Figure: <caption>]` plus the source note. A numbered
  figure becomes `[Figure n: <caption>]`, counted in document order with the same
  token approach as equations. The project asset itself remains untouched and
  reinsertable.
- Figure references are resolved before the file is returned. A pre-pass maps every
  numbered figure id to its document-order number, then `\x00figure-ref:<id>\x00`
  tokens written during traversal are replaced with `Figure n`. A missing or
  unnumbered target becomes `Figure (missing)`; no token byte reaches the file.
- Equations export as source, never as rendered HTML: a block equation becomes a
  fenced `$$` block, an inline equation `$...$`, and plain text keeps the exact
  LaTeX. Backslashes are not escaped as prose, and an equation without source is
  skipped. A numbered display equation gains `(n)` after the block in both formats,
  numbered in document order. The export depends only on the saved JSON, so it stays
  deterministic and offline.
- Footnotes export their stored text, never a rendered marker alone. Traversal emits
  a NUL-delimited token in place of each atom; the post-pass replaces tokens with
  `[^n]` in Markdown and `[n]` in plain text, then appends the definitions. Markdown
  writes GitHub-flavoured `[^n]: text` definitions (continuation lines are indented),
  and plain text appends a `Notes:` section in the same shape as the editor preview.
  Markdown note text is escaped as literal prose, so it cannot become markup or a
  second footnote marker. Every footnote is counted, including one with empty text,
  so a marker and its definition cannot drift apart; no token byte reaches the file.
- Tables render as GFM tables. Literal `|` is escaped, multi-block cells are joined
  with `<br>`, and a missing header row gets a blank structural one because GFM
  requires a separator. When `colspan`/`rowspan` greater than 1 are present, the
  whole table is written as HTML so merged content is not duplicated or dropped.
  Plain text joins cells with ` | ` and inserts a `--- | ---` line after a real
  header row.
- The editor downloads through the export API and saves the returned blob through a
  temporary object URL. Before that it awaits the same save path used by autosave and
  aborts the download when the save fails, so a stale file is never produced. Fetching
  the file (instead of navigating to its URL) also lets a backend export error, such as
  a missing Myanmar font, surface as a message. `export` in `/api/meta` advertises the
  feature.
- A successful export also records a `document_exported` activity entry with the
  format and byte size. The exported text is not stored in the log.

#### Word (.docx) rendering

- `render_docx` builds the file with python-docx from the stored JSON and returns
  bytes. Headings keep their style names (`Heading 1`–`6`), lists are written with
  explicit `•`/`n.` markers and negative first-line indentation instead of a Word
  numbering definition, so a nested list restarts correctly and stays editable.
  Paragraph alignment, blockquotes, code blocks (shaded Consolas), horizontal rules,
  links (real hyperlink relationships), hard breaks, bold, italic, strike and
  underline are mapped one-to-one.
- Figure images are read from the project's own assets through
  `pages.get_asset_file`, so a document can only embed an asset that belongs to its
  own project. The bytes are passed to python-docx as a stream, which gives the
  media part a generic name and keeps local asset ids out of the package. Formats
  Word cannot read (for example WebP) are converted to PNG in memory with Pillow;
  the pixels are unchanged. Wide images are scaled to 6 inches, the caption is
  written as a centered `Caption` paragraph, the source note stays as recorded, and
  the alt text becomes the drawing description. A numbered figure gets a
  `Figure n.` prefix in its caption paragraph, counted in document order; the caption
  text itself is unchanged. A missing asset produces a visible
  `[Figure n: <caption>]` (or `[Figure: <caption>]`) marker instead of a silent gap.
  A figure reference in running text is written as the same resolved `Figure n`
  label (or `Figure (missing)`), using the precomputed id-to-number map; it is
  static text, not a Word cross-reference field.
- Equations are converted locally: `latex2mathml` produces MathML,
  `mathml2omml` converts it to Office Math, and the `<m:oMath>` element is appended
  to the paragraph. The conversion output has no `m` namespace declaration, so it is
  parsed inside a temporary `<root xmlns:m="…">` wrapper. Display equations are
  centered and numbered with the same document-order counter used by Markdown/TXT;
  inline math stays inline. When either converter rejects the source, the LaTeX is
  written in italics so the formula is still readable.
- Tables are native Word tables with the `Table Grid` style. Column spans and row
  spans are computed on a grid first, then the target cells are merged, so merged
  content is neither duplicated nor dropped. Header cells are bold and shaded.
- Footnotes are native Word footnotes. Each atom appends a `w:footnoteReference`
  run (with the `FootnoteReference` style) and its text is collected in document
  order. After the body is written, a `word/footnotes.xml` part is attached with the
  required separator notes, one `w:footnote` per atom, a `FootnoteText` paragraph
  style and the footnotes relationship. Multi-line note text becomes a real
  `w:br/` line break and is XML-escaped, so markup characters cannot leak into the
  package. A document without footnotes gets no footnotes part.
- Core properties keep the project title but clear author, last-modified-by and
  comments, so the exporting machine's identity is not written into the file.
- The Word file is produced only from local libraries and project data; no provider
  is contacted, and PDF page layout is not reconstructed.

#### PDF (.pdf) rendering

- `render_pdf` turns the stored JSON into escaped HTML and hands it to PyMuPDF's
  `Story` engine, which lays the content out locally on A4 or US Letter pages. The
  page size and margin are presets stored in app settings: `pdf_page_size` is `a4`
  or `letter`, `pdf_margin` is `narrow`, `normal` or `wide` (36, 50 or 72 pt). The
  route reads them from `get_app_settings` and passes them to `render_pdf`; text
  width and maximum figure height are derived from the chosen media box, and a
  zero body margin in the CSS makes the configured margin exact. The page is a
  document flow, not the original scan geometry: text reflows and the file grows to
  as many pages as needed. A footer writes `n / total` outside the text rectangle.
- The same node set as the other renderers is mapped to HTML: headings (levels 1–6),
  paragraphs with alignment, lists (including `start` and nesting), blockquotes, code
  blocks, rules, native tables with `colspan`/`rowspan`, bold, italic, strike,
  underline, links and hard breaks. Extracted text is HTML-escaped before it reaches
  the story, so a `<script>` or `<b>` in OCR output is printed literally.
- Links are safe-filtered with the same `http`/`https`/`mailto` rule as the text
  exports. `Story.write_with_links` turns them into clickable PDF annotations.
- Figures resolve through `pages.get_asset_file` for this project only, then are added
  to a `pymupdf.Archive` under a generated name. WebP and other formats MuPDF cannot
  read are converted to PNG in memory with Pillow; pixels are unchanged. Images are
  scaled to the 495 pt text width and capped in height so a tall scan still fits a
  page. The caption is centered below the image, the source note is kept, and a
  numbered figure gains a `Figure n.` prefix. A missing asset becomes an explicit
  `[Figure n: <caption>]` marker (or `[Figure: <caption>]` when unnumbered). Local
  asset ids and API paths never enter the file.
- Equations keep their exact LaTeX source in a monospace style with the optional `(n)`
  label, because no offline LaTeX typesetter is bundled; inventing a rendered formula
  would violate the accuracy rule. Inline math stays inside its sentence, and equation
  references resolve to `Equation (n)` / `Equation (missing)` through the same
  document-order map.
- Footnotes become a superscript marker in place and a numbered **Notes** list at the
  end of the document. The note text is escaped and newlines become line breaks.
- Burmese text needs a Unicode Myanmar font. `DOCUREBUILD_PDF_FONT` is checked first,
  then known Noto/Padauk/Myanmar Text file names in the platform font directories, then
  a font-directory scan filtered by name and by an actual `မ` glyph check. The font is
  embedded only when Myanmar text is present. If it is required and no usable font is
  found, the export fails with `422 pdf_font_missing` instead of writing replacement
  characters; English-only documents need no Myanmar font.
- Output is deterministic: the same document and project name produce byte-identical
  PDFs. Core metadata sets only the project title and `DocuRebuild` as creator/producer,
  clears author, subject, keywords and dates, and `tobytes(..., reproducible=True,
  no_new_id=True)` removes machine-specific ids.

### Document versions

- Every document write compares the incoming Tiptap JSON with the stored one. When
  they differ, the stored (previous) state is snapshotted into
  `document_revisions` before the row is updated. The live document is never a
  revision, so pruning cannot remove current content.
- Automatic snapshots are coalesced: if the newest revision is younger than
  `REVISION_INTERVAL_SECONDS` (300 s), the intervening states are not stored. A
  consecutive duplicate of the newest revision is never inserted, and the pristine
  initial empty document is not versioned because it holds no user work. Manual
  checkpoints and restores force a snapshot regardless of the interval, so
  restoring a version always preserves the exact state it replaces.
- `REVISION_LIMIT` (100) prunes the oldest rows after each insert. This is an
  internal recovery history, not a backup: it lives in the same `project.db`, so
  disk failure, database corruption or deleting the project folder also removes it.
- `GET .../document/revisions` accepts `limit` (1–200, default 50) and returns
  newest-first summaries with a whitespace-collapsed 200-character preview,
  character count, source and timestamp; revision content is not sent for the list.
  `GET .../revisions/{id}` returns the exact stored content for the restore
  preview. Unknown ids return `revision_not_found` (404).
- Summaries and the read-only line comparison are built from `plain_text`, which
  contains prose but not LaTeX or generated figure labels. An equation-only change
  is still snapshotted and restores correctly, but the text preview and diff may not
  show it; the stored content always does. A figure citation is an inline atom with
  no text of its own, so a change that only adds or removes a citation is likewise
  saved and restorable but may not appear in the text diff.
- `POST .../document` creates a manual checkpoint of the current saved document and
  deduplicates against the newest revision. `POST .../revisions/{id}/restore`
  validates the id, writes the revision content and plain text through the same
  document update path with a forced snapshot.
- Comparison runs entirely in the browser and is read-only. `lib/text-diff.ts`
  compares the stored revision `plain_text` with the live editor text (so unsaved
  typing is included) using a longest-common-subsequence line diff. Common prefix and
  suffix lines are trimmed before the table is built, long unchanged runs collapse to
  a gap around two context lines, and changes above a fixed line/cell budget report
  `tooLarge` instead of allocating an unbounded table. Nothing is saved, sent or
  replaced until the user chooses restore.
- The editor flushes unsaved changes before saving a checkpoint or restoring. If the
  save fails, neither request is sent. On restore the returned document is applied
  with `setContent(..., { emitUpdate: true })`, the document cache is updated and
  the editor marks it saved; editor undo history restarts, while both states remain
  available as versions.

### Project activity

- `services.history.list_events` reads `history_events` for one project, newest
  first by `created_at` then `rowid`, and parses the stored JSON payload defensively.
  `GET /api/projects/{id}/history` accepts `limit` (1–200, default 50).
- Events are written by the service that does the work through
  `projects.record_history`: project creation, imports and cancellations, page
  processing/reset/deletion, region extraction and text corrections, OCR start and
  completion/failure, exports, backup creation and restore.
- Payloads are metadata only — page/element/run ids, counts, export format and byte
  size, backup filename and size, OCR languages, confidence and block count, or an
  error code. Document text, OCR output and image data are never copied into the log.
- The dialog labels known event types through the `workspace` i18n namespace and
  formats details with locale-aware date, number and file-size helpers. An event type
  written by a newer build is still listed, using its stored English summary as the
  fallback label.
- Filtering and search run entirely in the browser over the already-fetched newest
  events; they add no request and no stored state. `lib/activity-filter.ts` maps each
  event type to one category (`project`, `imports`, `pages`, `regions`, `text`,
  `export` or `other`) and unknown types fall into `other`, so a newer event never
  becomes invisible behind a filter. Search matches the localized label and computed
  detail text, the event type, the stored summary and scalar metadata payload values,
  case-insensitively; document text and OCR output are not available to search
  because they are never logged. Filters reset when the dialog closes.
- Export also runs locally and covers exactly the events currently matching the
  filters, so a filtered export cannot silently include other events. `lib/activity-export.ts`
  writes RFC 4180 CSV (quoted commas, quotes and line breaks, CRLF rows, a stable
  English header, details joined with `·`) or a versioned JSON archive that keeps the
  raw event records plus the localized label and details and records the active
  filters. CSV values that begin with `=`, `+`, `-` or `@` are prefixed with an
  apostrophe so a log value cannot execute as a spreadsheet formula; the download
  adds a UTF-8 byte-order mark so Burmese text opens correctly. Filenames use the
  sanitized project name, the local date and the chosen extension. No log data leaves
  the device.
- Writing a history event is best-effort: a logging failure is logged and never
  fails the import, export, OCR run or backup that produced it.

### Project backup and restore

- A backup is one zip archive built in `tmp/` and streamed to the browser as
  `application/zip`; it is deleted after the response. It contains `manifest.json`,
  `backup.json`, `project.db`, and every regular file under `source/`, `processed/`,
  `thumbnails/` and `exports/`. `backups/` and `trash/` are never included, so an old
  archive inside the project cannot nest itself into the next backup.
- `project.db` is copied through SQLite's backup API, not by file copy, so the
  snapshot is consistent even if a save is in progress, and WAL content is included.
- Creation is refused while an import job is queued, running or cancelling.
  After writing, the archive is reopened, `testzip()` is checked, required entries are
  verified, and every `assets.relative_path` in the snapshot must exist in the
  archive. A mismatch means files changed mid-write, so the download fails with
  `backup_incomplete` instead of shipping an incomplete archive.
- Restore is additive by design. The upload is streamed to `tmp/` while enforcing
  `max_backup_mb` (upload bytes and total expanded bytes), then handled in a
  threadpool: required entries, optional `testzip()`, per-member safety (rejects
  absolute paths, `..`, backslashes, drive letters, NUL bytes, symlinks and any root
  outside `manifest.json`, `backup.json`, `project.db`, `source|processed|thumbnails|exports`),
  extraction into a fresh staging folder, manifest/backup format versions, SQLite
  `integrity_check`, required tables and a migration version no newer than
  `MAX_MIGRATION_VERSION`.
- Finalization moves the staging folder to a new UUID project folder, creates the
  standard subfolders, rewrites `manifest.json` with the new id/name, ensures the
  document row, records a `project_restored` history event, inserts the registry row
  and deletes the staging copy of `backup.json`. On any failure the folder and the
  registry transaction are rolled back, so a bad archive never leaves a partial
  project behind.
- The restored name collides case-insensitively with existing names, so it becomes
  `<name> (restored)`, then `(restored) 2`, and so on. An existing project is never
  opened, renamed, replaced or deleted by a restore.
- The frontend downloads through `fetch` (so error codes can be shown) and saves the
  blob; the Unicode name comes from RFC 5987 `filename*`, with the ASCII `filename`
  as fallback. The restore dialog checks `.zip`/`.drbz` and `max_backup_mb` before
  uploading and explains that a new project will be created.
- An explicit download can be password-protected. `POST /projects/{id}/backup` with
  `{"password"}` wraps the verified zip in the `.drbz` container from
  `services/backup_crypto.py`. The container is `MAGIC` (`DRBZ`), a version byte, a
  16-byte salt and an 8-byte nonce prefix; a scrypt key (n=2^15, r=8, p=1) derives a
  32-byte AES-256-GCM key, and each 1 MiB record is sealed with the header and record
  index as associated data, followed by a zero-length terminator. A key-check record
  in the header separates a wrong password (`backup_wrong_password`) from damage
  (`backup_corrupt`). No extra compression is applied because the payload is already
  a deflated zip. The password travels in the request body, is used for one response
  and is never stored, logged or written into the archive.
- Restore detects encryption by reading the file magic, not by its extension, so a
  renamed `.drbz` still works and a plain zip is never decrypted. An encrypted upload
  without a password fails with `backup_password_required`; the decrypted zip goes to
  a second temporary file, and both temporary files are removed in `finally`. Vault
  and automatic copies never take a password: they run without a user present, so
  storing one would be worse than keeping them plaintext.
- The local backup vault (`app/services/local_backups.py`) is separate from the
  one-off download: `create_copy()` builds the same verified archive through
  `project_backup.create_backup()` and moves it to
  `backups/<project_id>/<unicode-name>.zip` instead of streaming it. Nothing is
  written until `POST /projects/{id}/backups` is called or an opted-in automatic copy
  runs. Retention is `backups.keep_copies` (default 5, backend range 1–50), and the
  oldest archives are unlinked after a successful move. Same-second copies get `-2`,
  `-3`, … suffixes, so a create never overwrites an existing copy. Listing is
  newest-first by `st_mtime_ns`. Downloads stream the stored file and never delete it.
- Automatic copies are opt-in (`backups.auto_on_open`, default `false`) and normally
  run after `POST /projects/{id}/open`. The route checks the setting, then schedules
  `auto_copy_for_project()` as a FastAPI background task, so opening never waits for
  an archive. That task opens its own session, re-reads `backups.interval_hours`
  (1–720, default 24) and `keep_copies`, and skips the copy unless the newest vault
  copy is at least that old. A process-wide lock re-checks due state, so two
  simultaneous opens cannot write duplicate snapshots. An import in progress makes
  `create_backup()` refuse; the failure is logged and the project still opens.
- The app itself has no always-on scheduler. For copies while the app is closed,
  `python -m app.scheduled_backup` is an optional one-pass entry point for Windows
  Task Scheduler, cron or a systemd timer. It runs migrations if needed, reads the
  same opt-in setting, interval and retention, calls the same `auto_copy()` for each
  project, logs a failure per project without stopping the rest, prints a summary and
  exits with code 1 when any project failed. It is not a daemon, makes no network
  request and writes only inside the local data directory. The documentation tells
  the user to run it while the app is closed so two processes do not create a copy at
  the same moment.
- Selective page restore (`app/services/page_restore.py`) reuses
  `project_backup.extract_validated()`, so an uploaded or stored archive passes the
  same path, size, format, SQLite and migration checks. `inspect()` extracts it once,
  lists the pages read-only and writes `selection.json`, then renames the staging
  folder to `tmp/select-<token>/`. The token is a 32-hex UUID bound to the inspecting
  project and expires after one hour; `load()` returns
  `410 restore_selection_expired` for a missing, expired, malformed or other-project
  selection, so a stale dialog cannot apply a selection to a different project.
- `apply()` appends pages after `MAX(page_number)` with new ids. It copies each page's
  original, display and thumbnail assets under new file names and new asset rows, then
  copies the page's `ocr_runs`, `ocr_blocks`, `ai_suggestions` and `elements`,
  remapping run, block and source-asset references. An unmapped source asset becomes
  `NULL` rather than pointing at the wrong file. Copied files are tracked and removed
  if the transaction fails, and the selection folder is discarded after a successful
  apply. A `pages_restored` history event records the count, source name and new page
  numbers.
- Selective restore is additive and page-scoped: it never replaces an existing page
  and never reads or writes the document, so figure and equation references in the
  text are untouched. Document versions stay project-local and are not restored.
  At most 5000 pages are inspected or applied in one selection; empty or unknown ids
  are rejected with `page_selection_empty`/`page_selection_invalid`, and an archive
  with no pages returns `backup_no_pages`.
- Vault filenames are treated as untrusted input: the service rejects empty names,
  path separators, `..`, non-`.zip` suffixes, symlinks and non-files with
  `backup_not_found`. The route also sets an ASCII `filename` fallback derived with
  `re.sub` while the stored name keeps Unicode, and it adds
  `Cache-Control: private, no-store`. Creating a copy records a
  `project_backup_created` history event through `create_backup()`, so it appears in
  the activity log; downloads do not.
- `DELETE /projects/{id}/backups/{filename}` removes exactly one archive after
  passing the same name checks; a missing file returns `backup_not_found` and an OS
  failure returns `backup_delete_failed`. The frontend requires an explicit
  confirmation naming the archive. Deleting a project moves
  `backups/<project_id>/` to `trash/<project-folder-name>-vault`, so the copies are
  preserved but no longer appear under the project id. The move is best-effort: a
  failure is logged and never blocks or reverses the project deletion.
- `POST /projects/{id}/backups/{filename}/restore` restores a stored copy through the
  same `prepare_restore()`/`finalize_restore()` path as an upload, so the archive is
  validated, extracted into staging and registered as a **new** project with a new
  id and a `(restored)` name when needed. `prepare_restore()` only reads the archive,
  so the stored copy and its original project stay untouched. The stored file is
  size-checked against `max_backup_mb` before extraction, and the same expanded-size,
  unsafe-path, checksum and schema checks apply. A failed restore removes its staging
  folder and leaves both the copy and the original project in place.

### Local AI cleanup

- Phase 6 starts with the smallest useful AI workflow: correcting one OCR text
  block. The provider layer is deliberately local-only and adapter-based:
  `ollama` and `openai_compatible` share the same request, validation and review
  path. `GET /api/ai/providers` returns the catalog and default URLs; the frontend
  never hardcodes a provider list.
- `app_settings.ai.text` stores `{ provider, base_url, model, allow_remote }` in
  `app.db`. An empty `base_url` uses the provider default; an empty `model` keeps
  every AI action disabled. `allow_remote` defaults to `false` and is the user's
  explicit consent for a non-loopback endpoint. The Settings page edits a local draft
  and saves explicitly, so typing a URL does not trigger a PATCH or a network request.
- `app_settings.ai.vision_model` is a separate optional model name that reuses the
  same provider, base URL and remote-consent decision. An empty value keeps image AI
  disabled and `POST .../ai-region-proposals` returns
  `409 ai_vision_not_configured` before contacting the server or recording usage.
- `POST /api/ai/probe` is user-triggered. It reads Ollama `/api/tags` and
  `/api/version`, or OpenAI-compatible `/models`, with a short timeout and a
  1 MB response cap. Expected failures (`unreachable`, `timeout`, `http_error`,
  `invalid_response`) are returned as status plus a stable error code so Settings
  can explain them without pretending the server is ready.
- `normalize_base_url` accepts only `http`/`https`, rejects embedded credentials and
  the well-known cloud metadata hosts, and appends `/v1` for OpenAI-compatible
  servers when missing. It also enforces the consent boundary: `localhost`,
  `*.localhost` and loopback IPs are allowed by default, while any other host
  returns `403 ai_remote_not_allowed` unless `allow_remote` is enabled. This check
  runs for probes, cleanup requests and per-request overrides, after the metadata
  block. The backend calls only the configured URL, using Python's standard library;
  no new runtime dependency is introduced.
- `ai_usage` records one row for each cleanup request that actually leaves the app,
  including provider failures. Validation failures that never contact the server are
  not counted, and connection tests are excluded. The row stores provider, model,
  task, outcome, error code, project/page/block ids and a timestamp — never document
  text or the model reply. `GET /api/ai/usage` returns the rolling 24-hour count,
  success/failure split and the 20 most recent entries.
- `ai.request_limit` (0 = unlimited, maximum 10,000) is checked before each cleanup
  request. Reaching the cap returns `429 ai_request_limit_reached` without contacting
  the provider. The limit and usage summary are shown in Settings, and the recent
  request list is metadata only. The ledger lives in the application database, so it
  spans projects without copying project text into the app database.
- `POST .../ocr/blocks/{block_id}/ai-suggestions` loads the block and run, refuses
  missing, unfinished or stale OCR results, and sends the **block text only** with a
  fixed correction system prompt (`temperature: 0`). The network call happens
  outside the SQLite transaction. Empty, non-text and oversized responses are
  rejected rather than stored.
- The reply is inserted into `ai_suggestions` with `status = pending`. Before insert,
  the block text is read again; if a manual correction happened during the request,
  the proposal is refused as stale instead of overwriting newer text.
- Accepting a proposal re-checks that the OCR run and block text still match the
  original proposal, then writes through `ocr.update_block`, which sets
  `corrected = true` and `verified = false`. An accepted proposal is therefore not a
  verification. Rejecting only updates the proposal status, so it remains possible
  after the page changes.
- `GET .../pages/{page_id}/ai-suggestions?status=pending` lists the page's stored
  proposals in `created_at DESC` order. The OCR dialog queries pending proposals when
  it opens and after each change, so proposals survive closing and reopening the
  dialog. The UI only renders proposals whose `block_id` belongs to the current OCR
  run, which keeps proposals from an older run hidden; the database rows remain.
- The same endpoint without `status` returns every proposal for the page, capped by
  `limit` (default 200, maximum 500). The OCR dialog also reads this list and shows
  accepted and rejected proposals for the current run's blocks as a per-block
  history with status, provider, model, decision time and the preserved
  original/proposed text. History is read-only, never rewrites OCR text, and remains
  available after later manual corrections.
- `GET /api/projects/{project_id}/ai-suggestions` returns proposals across every page
  with the page number, newest first, using the same `status`/`limit` parameters. The
  project-wide review dialog shows pending proposals with the current and proposed
  text and calls the existing decision endpoint, so per-block stale/run checks still
  apply. The queue reads from the project database and never changes OCR text on its
  own.
- The OCR dialog shows the current text and the proposal side by side with provider
  and model badges. It disables **Accept** when the block changed after the proposal
  and shows a Settings link when no model is configured.
- Vision region proposals reuse the same provider resolution, consent boundary and
  usage ledger. `services.ai_vision` reads the page's display (or original) asset,
  resizes it to a bounded JPEG in memory and sends it as base64 to the configured
  vision model. The model returns normalized 0–1 rectangles; the backend validates
  the JSON, drops unsupported kinds, non-finite or out-of-page origins, clamps boxes
  to the page, adds the heuristic padding and removes duplicates or regions that
  already have an extracted element. Coordinates are mapped with the stored page
  width/height, so the source viewer can overlay them without extra geometry.
- `POST .../pages/{page_id}/ai-region-proposals` returns `status: ready`, page
  dimensions, provider, model and low-confidence `ai_vision` proposals. It does not
  insert rows in `elements` or `ai_suggestions`; choosing a rectangle only prefills
  the extraction dialog. Each request is recorded with task `region_proposals`.
- Tests use a loopback stub HTTP server, not a real model, and cover discovery,
  unreachable/timeout/HTTP/invalid probes, remote-consent refusal, both adapters,
  proposal listing and filtering, usage recording and rolling-limit enforcement,
  stale runs, stale text, rejection, validation, vision coordinate mapping and
  vision output filtering. This verifies protocol handling and review safety, not
  model quality.

### Design system

- All visual values come from CSS custom properties in
  `packages/design-tokens/src/tokens.css` and generated Tailwind utilities
  (`h-panel`, `size-icon-sm`, `text-2xs`, `rounded-pill`, etc.).
- Appearance settings update root data attributes (`accent`, `radius`, `blur`,
  `density`, `fontSize`, `motion`) and the `dark` class.
- The appearance is cached in `localStorage` and applied before React mounts to
  avoid theme flashes; the backend remains the source of truth.
- UI typography and document typography use separate variables
  (`--font-ui`, `--font-document`, `--font-document-sans`).

### Internationalization

- Namespaces: `common`, `dashboard`, `workspace`, `settings`, `errors`.
- English is the canonical fallback; missing keys are tested for parity.
- Language preference is persisted in settings, cached in `localStorage`, and
  applied through `AppearanceSync` without a reload.
- Burmese uses Unicode and `Noto Sans Myanmar` with system fallbacks.

## Security and privacy decisions

- No mandatory accounts, cloud database or cloud storage.
- API binds to loopback by default; CORS allows only the local Vite origins unless
  configured.
- Security headers (`nosniff`, `DENY`, `no-referrer`, `same-origin`) are applied
  to every response.
- No secrets are stored in the frontend. No AI provider keys exist in this phase;
  local providers require none. The AI profile stores only a local URL and model names.
- AI usage history is metadata only: provider, model, task, outcome, error code,
  project/page/block ids and timestamps. It never stores sent text, page images or
  model output, and a request limit is enforced before a provider is contacted.
- OCR and PDF rendering run entirely on the local machine. Page images and PDF
  files are never uploaded; the backend reads the project's own source/display
  assets and invokes local libraries. Missing engine/language packs are reported,
  never bypassed with a cloud fallback.
- Markdown, TXT, Word and PDF export run in the local backend from the project
  database. The generated file contains no asset URLs, credentials or provider
  metadata and is only sent to the browser that requested it. DOCX and PDF embed only
  this project's own figure bytes.
- Document versions are stored in the project database. Saving, listing and
  restoring them never contacts a provider or the network: no AI call is made and
  no text leaves the machine. Versions are not a substitute for an external backup.
- The project activity log is read and written on the local machine only. Entries
  contain metadata (counts, formats, sizes, ids, timestamps), never document text,
  OCR output or image bytes, and reading the log makes no provider or network call.
- Project backups are created and validated entirely on the local machine. The
  archive is written under the local data directory, streamed to the browser and
  deleted; restore files are staged there and removed after validation or failure.
  User-created copies in `backups/<project_id>/` stay on disk until pruned or deleted
  explicitly. Deleting a project moves its project folder to the local trash and also
  moves its vault folder beside it in the trash; neither is destroyed automatically.
  Opt-in automatic copies run in the same local backend process only after a project
  is opened, and no backup work happens while it is stopped. No backup content is
  uploaded, and the app does not sync archives to GitHub. An archive contains the
  original documents and extracted text, so it must be stored like the project folder
  itself. Only an explicit download can be password-protected (`.drbz`); vault and
  automatic copies stay plaintext, and the password is never persisted, so it cannot
  be recovered. Selective restore stages an extracted archive under `tmp/` for at most
  one hour and deletes it after a successful apply, so a forgotten dialog does not
  leave a second copy of the project on disk.
- Document links are validated to `http`, `https` or `mailto` before they enter the
  document, and Markdown export repeats that check. A stored `javascript:` or
  `data:` target is never emitted as a link; only its text is kept.
- AI requests are sent only when the user tests a connection, asks for a cleanup or
  asks for region proposals, and only to the URL saved or entered in Settings. A
  cleanup sends one OCR text block; a region request sends the current page image
  only. The backend rejects non-HTTP(S) URLs, embedded credentials and well-known
  metadata hosts; it never switches to a remote or paid provider on failure, and
  responses are bounded. Cleanup replies are stored as reviewable proposals; region
  proposals are not persisted.
- Uploaded file names are validated and generated asset names are independent of
  user input.
- The source repository URL is configuration (`DOCUREBUILD_REPOSITORY_URL`),
  exposed through `/api/meta`, not hardcoded in the UI.
- GitHub never receives user data by default; `.gitignore` excludes databases,
  assets, exports, backups and environment files.

## Deliberate trade-offs

- **Separate SQLite databases per project** keep projects portable and isolate
  corruption, at the cost of cross-project queries being explicit.
- **Custom lightweight SVG icons are not used**; Lucide is kept for consistency.
- **No state-management library** — React Query owns server state and local React
  state is sufficient for the current workspace.
- **No fake capability flags** — `/api/meta.capabilities` reports what actually
  exists, and the UI hides or explains unavailable features.
- **Browser-only mode is not claimed** — image decoding stays in the local Python
  service so BMP/TIFF and thumbnails behave consistently.
- **PDF pages are normalised at import** — each page becomes a rendered PNG plus
  metadata instead of a browser PDF viewer. This keeps one page model for images,
  PDFs and future OCR overlays, at the cost of fixed-DPI storage. Rotations always
  re-render from the immutable PDF so resampling does not compound.
- **Embedded PDF text reuses the OCR review model** instead of a second
  extraction UI. The trade-off is that confidence is `NULL` and only one latest
  extraction is shown in the dialog; earlier runs remain stored but are not yet
  listed.
- **Layout detection stays heuristic and deterministic** — no learned layout
  model is bundled, so labels can be wrong but never fabricated, require no model
  download, and are cheap to explain and test. The trade-off is that figure
  regions and table structures are not detected yet; those need a later
  engine adapter rather than more regexes.
- **AI starts local and proposal-only** — the AI workflows correct one OCR block
  or propose reviewable page regions through a user-configured server. Loopback is
  allowed by default and any other host needs stored remote consent, with
  provider/model/URL provenance and explicit review. This keeps the free-first,
  accuracy-first guarantees and needs no secret store, at the cost of no remote
  free tiers, batch review or automatic routing yet.
- **Element extraction is manual first** — a crop is an exact pixel copy of the
  page, not inferred structure. This preserves accuracy and needs no model, at the
  cost of no automatic figure/table/equation detection. A table crop stays an
  image until Phase 7 adds editable cells.
