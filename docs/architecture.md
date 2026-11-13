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
| `services.document_export` | Deterministic Tiptap-to-Markdown/TXT rendering, escaping and download names |
| `services.elements` | Manual region extraction: source-pixel validation, immutable crops, element verification, staleness and trash-safe deletion |
| `services.regions` | Deterministic, read-only region suggestions from the latest OCR layout |
| `services.settings` | Persisted appearance, language, editor, AI profile, vision model and request-limit settings |
| `services.ocr` | Tesseract detection, language packs, bounded OCR jobs, block persistence, corrections, staleness |
| `services.ai` | Local provider catalog, URL and remote-consent validation, Ollama/OpenAI-compatible probe and model discovery, OCR cleanup proposals, vision region requests, listing and review decisions |
| `services.ai_vision` | Page-image encoding, normalized-to-source rectangle mapping and filtering for optional vision region proposals |
| `services.ai_usage` | Local AI request metadata, rolling-window request counting and usage summaries |
| `api.routes.*` | HTTP surface (`/api/...`) |

### Storage model

The application database (`app.db`) contains only global state:

- `projects` — id, name, description, directory, timestamps
- `app_settings` — key/value JSON (appearance, language, editor, local AI profile, vision model, request limit and local backup preferences)
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
shared `backups/<project_id>/` vault for user-created copies and a short-lived `tmp/`
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
GET    /api/projects/{id}/backups
POST   /api/projects/{id}/backups
GET    /api/projects/{id}/backups/{filename}
DELETE /api/projects/{id}/backups/{filename}
POST   /api/projects/restore
GET    /api/projects/{id}/document
PUT    /api/projects/{id}/document
GET    /api/projects/{id}/document/export?format=markdown|txt
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
  cursor), writes only the `caption` and `alt` attributes, and leaves `src`, `note`,
  `width` and `height` untouched, so provenance cannot be rewritten by a caption
  correction. The change is ordinary document content: autosave, versions, backups
  and Markdown/plain-text export all see the corrected caption without special
  handling. Applying re-reads the stored position first, so a figure removed while
  the dialog was open is never replaced by whichever node now sits there.
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

- `BlockMath` and `InlineMath` from `@tiptap/extension-mathematics` add
  `blockMath` and `inlineMath` atoms with one `latex` attribute each. Only the
  LaTeX source is stored in the document; the editor renders it with KaTeX in a
  node view. KaTeX and its stylesheet are bundled locally, so rendering works
  offline and makes no request.
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

### Document export

- The document is exported by the backend from the stored Tiptap JSON, not by the
  browser, so the file matches what autosave persisted and no second editor
  serializer can drift from it.
- `GET /api/projects/{project_id}/document/export?format=markdown|txt` reads the
  document row and returns a UTF-8 attachment. `format` is a required enum with a
  `markdown` default; unknown values are rejected by request validation (`422`).
  The response uses `text/markdown` or `text/plain` with `charset=utf-8` and a
  `Content-Disposition` header containing both an ASCII fallback filename and an
  RFC 5987 `filename*` for Unicode project names.
- `services.document_export` maps every known node deterministically: doc,
  paragraph, heading (levels 1–6, clamped), bullet/ordered lists (including
  `start`), listItem, blockquote, codeBlock (fence widened when the code contains
  backticks), horizontalRule, hardBreak, table, text marks, the custom `figure`
  atom and the math nodes.
- Markdown output escapes `` \ ` * _ [ ] < > `` and line-start markers (`#`,
  `-`, `+`, `>`, `1.`/`1)` and `---`), so extracted OCR text cannot become
  structure or raw HTML. Code spans are built from raw text so their content stays
  literal. Links are emitted only for `http`, `https` and `mailto`; any other
  target is dropped while the link text is kept.
- Figures never export their `src`. The local asset URL is meaningless outside the
  project, so the node becomes `[Figure: <caption>]` plus the source note. The
  project asset itself remains untouched and reinsertable.
- Equations export as source, never as rendered HTML: a block equation becomes a
  fenced `$$` block, an inline equation `$...$`, and plain text keeps the exact
  LaTeX. Backslashes are not escaped as prose, and an equation without source is
  skipped. The export depends only on the saved JSON, so it stays deterministic and
  offline.
- Tables render as GFM tables. Literal `|` is escaped, multi-block cells are joined
  with `<br>`, and a missing header row gets a blank structural one because GFM
  requires a separator. When `colspan`/`rowspan` greater than 1 are present, the
  whole table is written as HTML so merged content is not duplicated or dropped.
  Plain text joins cells with ` | ` and inserts a `--- | ---` line after a real
  header row.
- The editor downloads through a temporary anchor. Before that it awaits the same
  save path used by autosave and aborts the download when the save fails, so a
  stale file is never produced. `export` in `/api/meta` advertises the feature.
- A successful export also records a `document_exported` activity entry with the
  format and byte size. The exported text is not stored in the log.

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
  contains prose but not LaTeX. An equation-only change is still snapshotted and
  restores correctly, but the text preview and diff may not show it; the stored
  content always does.
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
  as fallback. The restore dialog checks `.zip` and `max_backup_mb` before uploading
  and explains that a new project will be created.
- The local backup vault (`app/services/local_backups.py`) is separate from the
  one-off download: `create_copy()` builds the same verified archive through
  `project_backup.create_backup()` and moves it to
  `backups/<project_id>/<unicode-name>.zip` instead of streaming it. Nothing is
  written until `POST /projects/{id}/backups` is called or an opted-in automatic copy
  runs. Retention is `backups.keep_copies` (default 5, backend range 1–50), and the
  oldest archives are unlinked after a successful move. Same-second copies get `-2`,
  `-3`, … suffixes, so a create never overwrites an existing copy. Listing is
  newest-first by `st_mtime_ns`. Downloads stream the stored file and never delete it.
- Automatic copies are opt-in (`backups.auto_on_open`, default `false`) and only run
  after `POST /projects/{id}/open`. The route checks the setting, then schedules
  `auto_copy_for_project()` as a FastAPI background task, so opening never waits for
  an archive. That task opens its own session, re-reads `backups.interval_hours`
  (1–720, default 24) and `keep_copies`, and skips the copy unless the newest vault
  copy is at least that old. A process-wide lock re-checks due state, so two
  simultaneous opens cannot write duplicate snapshots. An import in progress makes
  `create_backup()` refuse; the failure is logged and the project still opens. There
  is no background scheduler: a copy is attempted only as part of an open request,
  and no setting change triggers a copy by itself.
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
- Markdown and TXT export run in the local backend from the project database. The
  generated file contains no asset URLs, credentials or provider metadata and is
  only sent to the browser that requested it.
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
  itself; it is not encrypted by the app.
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
