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
| `services.pdf` | PDF open/validation, page rendering, embedded text extraction, embedded raster-image boxes, vector-artwork boxes, axis-aligned table rule extraction, capability detection |
| `services.layout` | Shared deterministic block classification (heading, list, caption, equation, table-like grid, running header/footer, page number) for OCR and embedded PDF text |
| `services.documents` | Document row, Tiptap JSON persistence, timestamps, coalesced revision snapshots, manual checkpoints and restore |
| `services.document_layout` | Per-project page header/footer text for paginated exports: stored layout row, default page-number choice and token-ready plain text |
| `services.document_export` | Deterministic Tiptap-to-Markdown/TXT/DOCX/PDF rendering, escaping, OMML equations, figure and inline-image embedding, native footnotes, PDF layout, page header/footer rendering and download names |
| `services.project_backup` | Verified local zip creation, safe validation/extraction and additive restore as a new project |
| `services.backup_crypto` | Optional `.drbz` container for downloaded backups: scrypt key derivation, chunked AES-256-GCM, password and corruption errors |
| `services.local_backups` | Local backup vault: verified copy creation, retention pruning, safe name resolution and opt-in automatic copies |
| `services.page_restore` | Selective restore: staged archive inspection, short-lived selection tokens, additive page/asset/OCR/element copying, page-image and region-crop repair and reversible document-version restore |
| `services.artwork` | Deterministic locator for large ink clusters that the OCR text layout does not explain on a photographed page: grayscale grid, text masking, cluster joining and size filters; returns boxes only |
| `services.elements` | Manual region extraction: source-pixel validation, immutable crops, element verification, staleness and trash-safe deletion |
| `services.regions` | Deterministic, read-only region suggestions from the latest OCR layout, raster-page ink, and embedded PDF raster-image placement and vector-drawing geometry |
| `services.settings` | Persisted appearance, language, editor, export and backup settings, plus global AI limits (`ai_preferences`) |
| `services.ocr` | Tesseract detection, language packs, bounded OCR jobs, block persistence with per-word boxes, corrections, staleness, and word-box extraction from a standalone crop |
| `services.table_structure` | Reviewable table proposals: word-box row clustering and whitespace column bands, plus exact merged-cell grids from a PDF's drawn rules; cell text/confidence/flags/alignment, page-level grouping of vertically contiguous row blocks, local reading of one saved crop, vector/OCR de-duplication, source pixel box, size caps and typed refusal errors |
| `app.ocr_benchmark` | Local CER/WER measurement against checked reference transcripts, by running the OCR adapter or scoring a stored transcript; validates fixtures and never uploads |
| `services.ai_providers` | Modular provider registry and adapters (Ollama, OpenAI-compatible and 12 cloud APIs), model discovery, model metadata/pricing normalization, URL/HTTPS/SSRF and remote-consent validation, bounded requests and typed provider errors |
| `services.ai_store` | Connection, key, model and task-route persistence; capability checks; task status; encrypted-secret wiring and connection health state |
| `services.ai_router` | Unified task router: route/fallback selection, key ordering and rotation, cooldowns, capability checks, paid approval, global/task/connection limits, cost estimation, usage recording and optional reply validation |
| `services.ai` | Reviewable OCR cleanup proposals, suggestion listing and accept/reject decisions; delegates all provider work to the router |
| `services.ai_vision` | Page and region image encoding, normalized-to-source rectangle mapping and filtering, one-crop equation transcription and one-crop table reading through routed tasks |
| `services.ai_usage` | Metadata-only AI request ledger: rolling counts, token totals, verified cost, task/connection breakdowns and history |
| `services.ai_secrets` | Encrypted, write-only arbitrary secret IDs (`connkey:<uuid>`) in the local data folder, with a generated master key; never returns the plain value |
| `services.ai_migrate` | One-time, explicit migration of legacy text/vision profiles and encrypted keys into the connection platform, keeping the old JSON as a backup |
| `app.scheduled_backup` | Optional one-pass CLI entry point for external schedulers: creates due automatic copies, respects saved preferences and reports failures |
| `api.routes.*` | HTTP surface (`/api/...`) |

### Storage model

The application database (`app.db`) contains only global state:

- `projects` — id, name, description, directory, timestamps
- `app_settings` - key/value JSON (appearance, language, editor, export layout, backup preferences and global `ai_preferences`: daily request limit and monthly budget)
- `ai_connections` — named provider connections: provider, endpoint, remote consent, cost class, enabled state, rotation strategy, attempt cap, request/spend limits and health state
- `ai_connection_keys` — key metadata per connection: label, priority, limits, enabled/authentication/cooldown state; the secret itself lives only in the encrypted vault
- `ai_models` — discovered or manually entered models per connection, with normalized modality, context, tool/streaming and pricing metadata; discovery is the source of truth, not a shipped catalog
- `ai_model_preferences` — per-model favorite flag and last-use metadata
- `ai_task_routes` — one row per task (`default`, `ocr_cleanup`, `region_proposals`, `equation_transcription`, `table_structure`) with connection/model, fallback, temperature, timeout and request limit
- `ai_usage` — local AI request metadata: provider, model, task, connection/key, outcome, error code, reported tokens, verified cost/source, project/page/block ids and timestamp; never document text or replies
- `schema_migrations` — created by Alembic

Each project owns a portable folder and its own `project.db`:

- `documents` — Tiptap JSON content and plain text
- `document_revisions` — previous document states: exact Tiptap JSON, plain text, capture source (`autosave`/`manual`) and timestamp; newest 100 kept per project
- `document_layout` — one row per project with single-line header and footer text, the page-number choice and a timestamp; it lives in the project database, so backups and restored copies keep it, and it never changes the document itself
- `assets` — relative path, MIME type, size, checksum, dimensions
- `pages` — page order, source/display/thumbnail asset references, rotation,
  `pdf_page_number` for PDF pages, status, and an `edits` JSON document holding the
  ordered geometry steps plus filter settings
- `history_events` — append-only local activity log: event type, human summary, small JSON metadata payload (counts, formats, sizes, ids) and timestamp; read by the project activity dialog
- `jobs` — background import jobs: status, progress, total/imported pages, current file, payload (file counts/names), error code/message and timestamps
- `ocr_runs` — page extraction attempts: status, engine/version, languages, source asset, rotation, mean confidence, error, timestamps; embedded PDF text uses `engine = pdf-text` and a null confidence
- `ocr_blocks` — reviewable text blocks with bbox, confidence, kind, line/word counts, correction and verification flags, plus a `words` JSON array holding each word's text, confidence, box and line index
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

The data directory also holds `app.db`, a `secrets/` folder for encrypted provider
keys, a shared `trash/` for deleted projects, a
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
GET    /api/ai/connections
POST   /api/ai/connections
GET    /api/ai/connections/{connection_id}
PATCH  /api/ai/connections/{connection_id}
DELETE /api/ai/connections/{connection_id}
POST   /api/ai/connections/{connection_id}/test
GET    /api/ai/connections/{connection_id}/keys
POST   /api/ai/connections/{connection_id}/keys
PATCH  /api/ai/connections/{connection_id}/keys/{key_id}
DELETE /api/ai/connections/{connection_id}/keys/{key_id}
GET    /api/ai/connections/{connection_id}/models
POST   /api/ai/connections/{connection_id}/models
POST   /api/ai/connections/{connection_id}/models/refresh
POST   /api/ai/connections/{connection_id}/models/favorite
GET    /api/ai/models
POST   /api/ai/models/clear-recent
GET    /api/ai/routes
PUT    /api/ai/routes/{task}
GET    /api/ai/tasks
GET    /api/ai/preferences
PATCH  /api/ai/preferences
GET    /api/ai/overview
GET    /api/ai/migration
GET    /api/ai/usage
GET    /api/ai/usage/history
DELETE /api/ai/usage
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
POST   /api/projects/{id}/backup/selection/{token}/document
POST   /api/projects/{id}/backup/selection/{token}/page-assets
POST   /api/projects/{id}/backup/selection/{token}/element-assets
POST   /api/projects/restore
GET    /api/projects/{id}/document
PUT    /api/projects/{id}/document
GET    /api/projects/{id}/document/layout
PUT    /api/projects/{id}/document/layout
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
GET    /api/projects/{id}/pages/{page_id}/ocr/blocks/{block_id}/table-proposal
GET    /api/projects/{id}/pages/{page_id}/table-proposals
GET    /api/projects/{id}/pages/{page_id}/ai-suggestions
POST   /api/projects/{id}/pages/{page_id}/ocr/blocks/{block_id}/ai-suggestions
PATCH  /api/projects/{id}/ai-suggestions/{suggestion_id}
POST   /api/projects/{id}/ai-suggestions/bulk
GET    /api/projects/{id}/pages/{page_id}/elements
POST   /api/projects/{id}/pages/{page_id}/elements
GET    /api/projects/{id}/pages/{page_id}/region-proposals
POST   /api/projects/{id}/pages/{page_id}/ai-region-proposals
PATCH  /api/projects/{id}/elements/{element_id}
POST   /api/projects/{id}/elements/{element_id}/text
PATCH  /api/projects/{id}/elements/{element_id}/text
POST   /api/projects/{id}/elements/{element_id}/ai-equation
POST   /api/projects/{id}/elements/{element_id}/ai-table
POST   /api/projects/{id}/elements/{element_id}/table-proposal
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
  the inline-image node, the block and inline equation nodes, the placeholder and
  `TableKit` live there.
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
- A `table` block can produce a reviewable cell-grid proposal through
  `GET .../ocr/blocks/{block_id}/table-proposal`. `services.table_structure` reads
  the stored `words` JSON, clusters words into rows by vertical overlap, derives
  column bands from gaps no row occupies, filters unsupported bands and builds
  cells with text, confidence and flags. Only a non-stale block whose kind is
  `table` is accepted; a corrected block is refused because its words no longer
  match the edited text. Caps are 60 rows, 20 columns and 600 cells, with typed
  errors for unusable or oversized grids.
- PDF word boxes come from PyMuPDF `get_text("words")` and are attached to a block
  by centre containment, so embedded-text blocks also carry geometry. PyMuPDF
  often emits one block per row, so a single block is rarely labelled `table`.
- `GET .../pages/{page_id}/table-proposals` therefore returns every reviewable
  table on a page. Single blocks already labelled `table` are built directly.
  Vertically contiguous paragraph blocks are grouped when their merged visual rows
  still pass the same deterministic classifier (`classify_text_block` plus the
  wide-gap test) used for one block, and only a `table` label is accepted. Visual
  rows are rebuilt from word boxes rather than stored line indices, because
  PyMuPDF splits same-row words into separate lines. A hand-corrected block is a
  barrier, so a candidate never bridges across a row whose stored words no longer
  match its text. At most 20 candidates are returned per page; each candidate keeps
  the 60 rows / 20 columns / 600 cells caps.
- Drawn PDF rules take precedence over word-box whitespace. `services.pdf.table_lines`
  extracts axis-aligned strokes and thin filled or stroked rectangles from the
  immutable PDF in rendered-pixel coordinates; curves, diagonals and wide filled
  areas are ignored. `services.table_structure` clusters segments into row and
  column boundaries, groups touching rules into separate tables, requires a closed
  outer boundary with at least two rows and two columns, and treats a missing
  internal separator as a merged cell. Rectangles are built by claiming every base
  coordinate exactly once; a stepped or overlapping shape is refused instead of
  being approximated. Words are assigned by centre to exactly one rectangle and
  re-lined per cell, because PDF line numbers are block-local. A candidate must
  contain at least two filled cells and a conservative share of filled cells, so an
  empty chart frame is not proposed.
- Vector candidates are built before word-box candidates and sorted by source
  position. An OCR candidate whose source box is at least 85% inside a vector grid
  is dropped, because the vector grid already describes the same table with exact
  spans. Rules are used only for a page whose `source_kind` is `pdf`, whose rotation
  is zero, whose immutable original is still present and whose `edits` contain no
  geometry change; anything else keeps the word-box path. Merged anchors carry
  `rowspan`/`colspan`; covered coordinates are not repeated. The review grid renders
  the anchors with those spans and insertion skips the covered coordinates, so the
  saved Tiptap table uses the same ordinary cell attributes as a manual merge.
- A saved table crop can be read on this device through
  `POST .../elements/{element_id}/table-proposal`.
  `services.ocr.extract_image_content` runs the same Tesseract path as page OCR
  but returns the crop's word boxes instead of only text. `services.table_structure`
  clusters them into rows and whitespace column bands, rebases each visual row's
  line number so words from different OCR blocks join correctly, and replaces the
  source box with the saved region rectangle so the dialog can cut that region from
  the page image. The region's `table` kind is the user's own declaration of intent;
  the builder still requires at least two rows and two columns and applies the same
  row/column/cell caps. The crop image and the element stay untouched. A vision
  model remains an optional second reader through `POST .../ai-table`.
- The proposal dialogs show the grid and its per-cell flags before anything is
  inserted. A single-block proposal, a page candidate, a locally read crop and an
  AI-read table share one `TableReview` component, so a cell is presented identically
  in all of them. The API
  also returns the proposal's `source` pixel box and the page dimensions; the dialog
  crops the page
  image to that box by positioning it with percentages, so the source can be
  compared side by side without measuring the DOM or loading extra images.
  Insertion uses the same workspace actions context as other document edits and
  builds a normal Tiptap table. The first row becomes a header only when the user
  selects it, and an acknowledgement checkbox is required when any cell is
  uncertain or has no confidence. The proposal is never saved on its own.
- `useTableDraft` holds manual cell corrections beside the proposal: it keeps a
  per-cell edit map for one proposal key, derives the insertable matrix from the
  proposal plus those edits, and recomputes the changed count against the
  proposal so a reverted cell stops counting. Insert reads the draft's rows, the
  proposal cells are untouched (the badges still describe what the engine read),
  and a different block or candidate key starts with no edits. The dialog resets
  the draft when it opens or switches proposal, so a discarded draft cannot leak
  into the next table.
- Cell alignment is inferred in `services.table_structure` from each cell's word
  boxes: the gaps to its column band edges are compared with a tolerance derived
  from the typical word height and band width. A line that fills the band is
  ignored, because left, centre and right look identical there, and all lines in a
  cell must agree or the cell reports no alignment. Each proposed cell carries
  `alignment`; `proposalAlignments` builds a matrix beside `proposalRows`, the
  review grid shows it, and insertion sets the paragraph's `textAlign` attribute
  only for centre and right (left is the default). The document therefore uses
  ordinary paragraph alignment, with no new node or schema.
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
- Accuracy is measured with `app/ocr_benchmark.py`, a separate local CLI rather
  than an API endpoint, because it scores fixtures on demand and has no project or
  user state. A fixtures folder holds `manifest.json` plus reference transcripts;
  each case either names a page image, which is run through the same
  `extract_image_text` adapter, or a stored transcript, which lets a result be
  re-scored without Tesseract. CER and WER are Levenshtein edit counts over NFC
  text with collapsed whitespace, computed with Myers' bit-parallel algorithm, and
  aggregate as total edits over total reference units so long pages carry
  proportional weight. An empty reference is reported as `n/a` in the table and
  never as a perfect score. Fixture paths are resolved inside the fixtures folder,
  and a case that cannot be scored is reported and excluded rather than aborting
  the run. No fixture, transcript or result is uploaded, and no accuracy figure is
  published before real-document fixtures are measured.

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
- The extraction dialog also offers an inline placement. `inlineImage` is a separate
  paragraph-level atom that stores only `src` and `alt`, so the picture stays in the
  current sentence and no caption, note or figure number is invented. The same
  dialog and the saved-region library both expose it ("Insert inline"), and both use
  the existing project asset URL. One picture can be selected and deleted without
  touching the surrounding text. Markdown and plain text write an explicit
  `[Image: alt]` marker, while Word and PDF embed the asset at a smaller size cap;
  a missing asset leaves the same visible marker.
- An equation region's reviewed text can become a real display equation instead of
  a picture. The dialog shows the saved crop beside a local KaTeX render of the
  LaTeX being edited, refuses empty or unrenderable source, and inserts only the
  source the user confirmed as a `blockMath` node (optionally numbered) plus the
  usual provenance blockquote. The stored crop and the element's extracted text are
  unchanged, so the formula is a separate, reviewable reconstruction rather than a
  claim about the OCR text.
- The same dialog can ask the routed model for LaTeX. It posts to
  `POST .../elements/{element_id}/ai-equation`, which reads the element first, refuses
  anything that is not an equation region (`409 ai_equation_region_required`) and
  missing crops, then sends only the saved crop. The reply is reduced to its LaTeX
  content (code fence, `$$`/`\[`/`\(`/`$` delimiters and wrapping quotes are removed,
  never the expression itself); an empty reply is `502 ai_equation_empty`. The dialog
  fills the review field and shows the model plus an unverified warning, but does not
  persist an `ai_suggestions` row and never inserts on its own. The provenance note
  credits the model only while the field still matches its reply; any edit falls back
  to the manual note. Each attempt is recorded with task `equation_transcription`.
- A saved table region can be read the same way from the region library. Its dialog
  posts to `POST .../elements/{element_id}/ai-table`, which refuses a non-table
  region (`409 ai_table_region_required`), a missing crop and an unconfigured
  `table_structure` route before any request. Only a complete rectangle within the local table caps is
  accepted, every cell is unscored, and the reply is shown in the same `TableReview`
  grid as a local proposal. Nothing is written to the region; insertion writes the
  reviewed grid (with any manual corrections) and a note that names the model. Each
  attempt is recorded with task `table_structure`.
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

- Suggestions reuse the OCR text layout and, on PDF pages, the placement of
  embedded raster images and the geometry of vector drawings instead of a vision
  model, so they stay free, local and explainable. Six signals are recognised:
  `table_text_grid` (merged OCR `table` blocks), `equation_text` (OCR `equation`
  blocks), `figure_caption_gap` (the empty band above a `caption` block whose text
  starts with figure/diagram/chart/plate/photo/image/illustration),
  `pdf_image_region` (a raster image drawn on the PDF page),
  `pdf_drawing_region` (vector artwork drawn on the page) and
  `page_artwork_region` (large ink on a photographed page that the OCR layout does
  not explain).
- `services.pdf.image_regions` reads `Page.get_image_info()`, applies the page's
  own `/Rotate` matrix and converts PDF points to the stored page's pixel width.
  Boundaries are converted to the rendered page width, so a figure box stays in the
  same coordinate system as the displayed image and the OCR blocks. Only geometry
  is read; the pixels are not classified.
- `services.pdf.drawing_regions` reads `Page.get_drawings()` instead. A path is
  artwork when it is filled and thicker than a rule, or when it contains a curve or
  a diagonal; axis-aligned thin or unfilled paths are the same rules
  `table_lines` reads, so a drawn table grid, an underline or a page frame never
  becomes a figure. Paths are grouped when their boxes are within 12 px of each
  other, in rendered-page pixels. A group must contain at least two parts, or a
  single curved or diagonal one, because one filled rectangle is far more often
  shading than an illustration.
- An image box is proposed as a figure only when it is at least 5 % of the page
  wide and 3 % tall. A drawing needs 8 % width and 4 % height, since it has no
  caption to prove it is artwork. A region covering at least 80 % of both
  dimensions is treated as a scanned page background rather than artwork, and a
  caption band that covers most of the same area is merged into the proposal so the
  user sees one precise rectangle with the caption text. Image and drawing boxes are
  read from the immutable PDF only when the page has no rotation or geometry edit;
  a stale OCR run withholds every suggestion, so a box is never drawn against a
  different render.
- A drawing that describes the same area as an embedded image, or that lies mostly
  inside a detected table or equation, is dropped: those regions already have a
  better proposal, and a shaded cell or a frame around an image is not a second
  figure.
- `services.artwork.artwork_regions` handles a page without any PDF layer. The
  current render is converted to a grayscale copy 480 px wide, and the page's own
  background is measured from the 90th luma percentile. A page whose background is
  darker than 140 is not analysed, because ink and background cannot be separated.
  A grid cell is inked when at least 8 % of its pixels are clearly darker than that
  background. Cells whose centre lies inside an OCR block are removed, because the
  text is already explained by the layout; everything left is content the engine
  did not read as text. Touching cells are clustered, neighbouring clusters within
  3 % of the page are joined into one drawing, and a group becomes a figure only
  when it covers at least 15 % of the page width and 10 % of its height, is not
  page-sized in both directions, is not a thin rule, and does not touch three page
  edges (a frame or the background around the paper). At most five such regions are
  returned, largest first.
- Ink boxes are a weaker signal than PDF geometry, because a ruled table that the
  OCR engine did not classify, or an ornamental border the engine read as text,
  can look like artwork. They are therefore proposed as `low` confidence with no
  caption, unless a caption band covers the same area, in which case the caption
  is attached. A box that lies mostly inside a detected table or equation proposal
  is dropped. The region still only prefills the extraction dialog.
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
  frame. Low-confidence regions use the warning style. Choosing one opens the
  normal extraction dialog prefilled with the kind, caption and rectangle,
  marked as a suggestion and naming the signal it came from; nothing is saved
  until the user confirms through the existing crop path.
- Limitations: drawings the PDF stores as an opaque page or form rather than
  readable paths, artwork the OCR engine read as text, dark pages that cannot be
  separated from their content and page-sized backgrounds are not suggested, an
  embedded image on a page with no text run is not suggested, and no cell or
  equation structure is derived. `region_proposals` in `/api/meta` advertises the
  feature.

### Document tables

- `TableKit` from `@tiptap/extension-table` provides `table`, `tableRow`,
  `tableHeader` and `tableCell`. Column resizing is disabled on purpose: stored
  pixel widths are bound to one screen size, and Markdown cannot represent them. A
  shared `doc-table` class provides styling through existing design tokens.
- The insert dialog is the only way an empty table enters the editor. It clamps the
  requested size with `lib/editor-table.ts` (`TABLE_MIN_SIZE = 1`,
  `TABLE_MAX_SIZE = 10`) and inserts empty cells plus an optional header row. The
  separate OCR table proposal is the only path that fills cells from extraction,
  and only after an explicit review and confirmation.
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
  the normal textarea. Equations are not recognised automatically; the only AI path
  is the explicit per-region transcription described above, whose result stays
  unverified until the user inserts it.
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
- Page header/footer text belongs to the project (`services.document_layout` in
  `document_layout`), not to app settings, because it describes the reconstructed
  document. Each field is one line after whitespace collapsing, capped at 200
  characters, and may contain `{page}`, `{pages}` and `{title}`; unknown braces stay
  literal. Word and PDF render it, while Markdown and plain text are not paginated
  and ignore it. An automatic page counter is added only when neither field already
  uses a page token, so a user-supplied counter is never duplicated. Saving the
  layout records a metadata-only `document_layout_updated` event; the text itself is
  not copied into the activity log.
- `services.document_export` maps every known node deterministically: doc,
  paragraph, heading (levels 1–6, clamped), bullet/ordered lists (including
  `start`), listItem, blockquote, codeBlock (fence widened when the code contains
  backticks), horizontalRule, hardBreak, table, text marks, the custom `figure` and
  `inlineImage`, `figureReference`, `equationReference` and `footnote` atoms and the
  math nodes. Markdown and TXT share that traversal; DOCX uses a separate
  `_DocxRenderer` and PDF a `_PdfRenderer`, both over the same JSON.
- Markdown output escapes `` \ ` * _ [ ] < > `` and line-start markers (`#`,
  `-`, `+`, `>`, `1.`/`1)` and `---`), so extracted OCR text cannot become
  structure or raw HTML. Code spans are built from raw text so their content stays
  literal. Links are emitted only for `http`, `https` and `mailto`; any other
  target is dropped while the link text is kept.
- Figures never export their `src`. The local asset URL is meaningless outside the
  project, so the node becomes `[Figure: <caption>]` plus the source note. A numbered
  figure becomes `[Figure n: <caption>]`, counted in document order with the same
  token approach as equations. The project asset itself remains untouched and
  reinsertable. An `inlineImage` is a prose atom rather than a block, so it becomes
  `\[Image: <alt>\]` in Markdown (alt text escaped) and `[Image: <alt>]` in plain
  text; an empty alt falls back to `Image`. No path or asset id is written.
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
- An inline image is embedded in its own paragraph run, so it keeps the sentence's
  flow. It is capped at 2.2 × 1.4 inches, and the stream/PNG fallback and drawing
  description are shared with block figures through `_fill_picture_run`. A missing
  asset leaves `[Image: <alt>]` in the sentence; no placeholder picture is created.
- Equations are converted locally: `latex2mathml` produces MathML,
  `mathml2omml` converts it to Office Math, and the `<m:oMath>` element is appended
  to the paragraph. The conversion output has no `m` namespace declaration, so it is
  parsed inside a temporary `<root xmlns:m="…">` wrapper. Display equations are
  centered and numbered with the same document-order counter used by Markdown/TXT;
  inline math stays inline. When either converter rejects the source, the LaTeX is
  written in italics so the formula is still readable.
- Multi-line equation environments (`aligned`, `align`, `alignat`, `flalign`,
  `gather`, `multline`, `split` and `eqnarray`, starred or not) are converted by
  `_equation_array_omml` before the generic converter runs. `latex2mathml` emits a
  bare `&` for an `aligned` body, which is invalid XML, and adds invented `(1)`,
  `(2)` labels for an unstarred `align`; both would either lose the equation or
  fabricate numbering. Instead the rows are split outside nested environments,
  optional row spacing is removed, escaped `\&` and `\{` stay literal, and each cell
  is converted on its own. A one-column array becomes a Word `<m:eqArr>`; alignment
  points become matrix columns with alternating right/left justification, so every
  symbol and row is kept. A failed cell falls back to the exact LaTeX rather than
  emitting a partial equation. Per-row numbers are never synthesized: DocuRebuild's
  own block-level numbering remains the only source of equation labels.
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
- The project's header and footer are written into the first section's header/footer
  parts using the `Header` and `Footer` styles. `{page}` and `{pages}` become real
  `w:fldSimple` `PAGE`/`NUMPAGES` fields, so Word updates them on open and when the
  document grows; `{title}` is written as the project title. A footer that also holds
  an automatic counter gets a right tab stop at the section's content width, otherwise
  the counter is centred. Turning page numbers off writes no field, but an explicit
  token is still honoured. The generated placeholders inside the field definitions are
  not treated as the real page count.
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
  as many pages as needed.
- Header and footer text is drawn as one line inside the top and bottom margins, in
  the same grey as the generated page counter. A footer with extra text keeps the
  counter at the right edge; with no footer text the counter stays centred, which
  preserves the previous `n / total` output. Long text is measured with the active
  font and shortened with `...` rather than running past the margin. The header and
  footer strings participate in the Myanmar font check, so a Burmese running head
  cannot silently become replacement characters. If a field already supplies
  `{page}` or `{pages}`, no second counter is added, and the page-number setting can
  remove the automatic counter without disabling explicit tokens.
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
  asset ids and API paths never enter the file. An inline image is written as an
  `<img>` in the same paragraph and capped at 150 × 90 pt so it stays on the line;
  the archive cache is keyed by asset id plus both caps, so inline and block uses of
  one asset do not inherit each other's size. A missing asset leaves
  `[Image: <alt>]` text.
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
  document update path with a forced snapshot. `documents.replace_document()` exposes
  that forced snapshot for the backup restore path, so a restore from an archive always
  leaves the replaced text in the local version history.
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
- Selective restore (`app/services/page_restore.py`) reuses
  `project_backup.extract_validated()`, so an uploaded or stored archive passes the
  same path, size, format, SQLite and migration checks. `inspect()` extracts it once,
  lists the pages, damaged region crops and document versions read-only, writes
  `selection.json`, then renames the staging folder to `tmp/select-<token>/`. The
  current project database is opened read-only and best effort, so each page also
  carries `in_project`, `missing_slots` and `restorable_slots` for page-image repair;
  a missing or unreadable current database reports pages as not in the project
  instead of failing the inspection. A null display slot is normal for formats that
  use the original directly and is not reported as missing. Region inspection lists
  only elements that still exist in the project and whose crop file is missing, with
  a `restorable` flag; it is capped at `MAX_SELECTED_ELEMENTS` and sets
  `elements_truncated` when more damaged regions remain, so the payload stays bounded
  without hiding the fact. The token is a 32-hex UUID
  bound to the inspecting project and expires after one hour; `load()` returns
  `410 restore_selection_expired` for a missing, expired, malformed or other-project
  selection, so a stale dialog cannot apply a selection to a different project.
  `SELECTION_VERSION` is stored in the payload, so a selection written by an older
  build is treated as expired instead of being read with the wrong shape.
- `apply()` appends pages after `MAX(page_number)` with new ids. It copies each page's
  original, display and thumbnail assets under new file names and new asset rows, then
  copies the page's `ocr_runs`, `ocr_blocks`, `ai_suggestions` and `elements`,
  remapping run, block and source-asset references. An unmapped source asset becomes
  `NULL` rather than pointing at the wrong file. Copied files are tracked and removed
  if the transaction fails, and the selection folder is discarded after a successful
  apply. A `pages_restored` history event records the count, source name and new page
  numbers.
- `apply_document()` reads the backup's live document (`revision_id: null`) or one
  `document_revisions` row, validates that the stored content is a JSON object, and
  calls `documents.replace_document()`. That helper always force-snapshots the state
  being replaced, even inside the five-minute coalescing window, so a document restore
  is itself reversible from the local version history. The response carries the
  restored `DocumentOut`; the workspace actions context hands it to the editor, which
  keeps its own working copy and would otherwise ignore a query refetch. A
  `document_restored` event records the source name, `document_source`
  (`current`/`revision`), the revision id and the character count, but never the text.
  Page restore and document restore are independent: pages never touch the document,
  and a document restore never touches pages or assets.
- `apply_page_assets()` repairs one page in the current project. It recomputes the
  missing slots from the live database, so it never trusts the inspection snapshot
  for what to overwrite. A slot is missing when it has no id (except a null display,
  which is normal), its asset row is gone, its path is unsafe, or its file is missing
  or empty. Only missing slots whose backup asset and file are usable are copied.
  Before copying, a backup asset checksum is verified and a mismatch raises
  `422 backup_checksum_mismatch` instead of copying corrupt data. If the current
  asset row still exists the file is rewritten under the same asset id, so OCR
  `source_asset_id` and element references stay valid; if the row is gone, the file
  is copied under a new id and the page column is updated. A present image is never
  overwritten. Copied files are removed if the transaction fails, and a
  `page_assets_restored` event records the page id, number, slots and source. The
  inspection token is not discarded, so several pages can be repaired from one
  inspection.
- `apply_element_asset()` repairs one region crop in the current project. It also
  recomputes the live element and only copies when its crop is missing. A present
  crop is never overwritten, and the region's rectangle, caption, extracted text,
  verification state and `source_asset_id` are untouched. A surviving asset row is
  rewritten in place so OCR and editor references stay valid; otherwise the crop is
  copied under a new id and `elements.asset_id` is updated. Backup checksums are
  verified the same way. `updated_at` is refreshed because the crop URL is versioned
  by it, and an `element_asset_restored` event records the element, page, kind and
  source. The token survives here too, so several regions can be repaired from one
  inspection.
- Page restore is additive: it never replaces an existing page. At most 5000 pages are
  inspected or applied in one selection; empty or unknown ids are rejected with
  `page_selection_empty`/`page_selection_invalid`. A backup with no pages is still
  inspectable, because its document can be restored; selecting pages from it returns
  `page_selection_empty`, and an unknown document revision returns
  `422 backup_document_missing`.
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

### AI provider platform (BYOK)

- Phase 6 uses one platform for every AI task. `services.ai_providers` owns a
  registry of adapter specifications: local `ollama`, a custom `openai_compatible`
  server, and the `openai`, `anthropic`, `gemini`, `openrouter`, `groq`, `mistral`,
  `deepseek`, `xai`, `together`, `fireworks`, `cerebras` and `perplexity` APIs.
  `GET /api/ai/providers` returns the catalog and default endpoints; the frontend
  never hardcodes a provider or model list. A provider can opt out of model discovery
  and allow manual model IDs; a custom server requires the user to supply its URL.
- A **connection** is a named account/endpoint in `ai_connections`. It stores the
  provider, normalized base URL, explicit `allow_remote` consent, `cost_class`
  (`local`, `free` or `paid`), enabled flag, rotation strategy, maximum attempts and
  optional request/spend limits. Several connections can exist for the same provider,
  so a user can separate work and personal accounts or use different endpoints.
- A connection holds zero or more **keys** in `ai_connection_keys`. The key secret is
  never in `app.db`: `services.ai_secrets` stores it under a generated
  `connkey:<uuid>` id in `<data_dir>/secrets/ai_keys.enc`, encrypted with Fernet and
  a generated 32-byte master key in `secrets/ai_keys.key`. The directory is created
  with user-only permissions where the platform supports it. The API returns only
  key metadata (`has_secret`, label, limits, status, cooldown) and never the value.
  An unreadable or missing vault degrades to "no key" with a warning instead of
  breaking Settings. Legacy per-task keys are copied vault-to-vault during the
  one-time migration.
- **Model discovery** is user-triggered by `POST /api/ai/connections/{id}/test`.
  The adapter uses the selected key, calls Ollama `/api/tags` and `/api/version`, or
  the provider's OpenAI-compatible `/models`, Anthropic, Gemini or other documented
  listing endpoint, with short timeouts and a bounded response. Results are cached in
  `ai_models` with normalized `input_modalities`, `output_modalities`, context,
  tool/streaming flags and pricing when the provider reports them. A provider with no
  listing endpoint returns `ai_model_discovery_unsupported`; the user can then add a
  model ID manually, marked `source = manual`. Favorites are stored separately so a
  refresh never loses them.
- A **task route** in `ai_task_routes` maps `ocr_cleanup`, `region_proposals`,
  `equation_transcription` and `table_structure` to a connection/model pair, with an
  optional fallback connection/model, temperature, timeout and rolling 24-hour
  request limit. `default` is used by any task without its own row. A route with a
  connection must have a model. Saving a route validates that the model is in the
  connection's catalog and that its discovered modalities fit the task: vision tasks
  need `image` input, text tasks need `text` output. Unknown modality metadata is
  allowed and marked unverified instead of blocking a model whose metadata is
  incomplete. Route payloads are always complete: omitting a field resets it to its
  default.
- `services.ai_router.complete` is the only generation path. It resolves the primary
  and optional fallback, applies global daily and monthly-budget limits, then
  per-task and per-connection limits. A paid connection requires `confirm_paid` for
  that action and otherwise returns `409 ai_paid_confirmation_required` before any
  network call or usage row. It selects eligible keys by rotation strategy
  (`priority`, `failover`, `round_robin`, `least_recent`, `least_usage`), skips
  disabled, failed or cooling-down keys, and bounds provider requests by the
  connection's `max_attempts`. A configured connection with no usable key never
  degrades to an unauthenticated request. A fallback is tried only after the primary
  fails, and only when it is a different configured connection.
- Provider HTTP errors are classified from the status code: 429 becomes
  `ai_rate_limited` and puts that key into a cooldown (the provider's `Retry-After`
  is capped at 24 hours; otherwise a short default), 401/403 become `ai_auth_failed`
  and mark the key failed, and other statuses stay `ai_http_error`. The router does
  not sleep or retry the same key indefinitely, does not bypass a provider limit, and
  reports quota exhaustion as the provider reports it. The UI shows the advisory wait
  and lets the user disable or replace a key.
- `normalize_base_url` accepts only `http`/`https`, rejects embedded credentials and
  the well-known cloud metadata hosts, and normalizes provider API paths. Remote
  endpoints require explicit `allow_remote` consent and HTTPS; loopback HTTP is
  allowed. Consent is checked when a connection is created or updated, so a remote
  connection cannot exist without it, and again at request time. Redirects are not
  followed. Provider defaults that point at a remote host also require consent.
- `ai_usage` records one row for every provider request, including failures. It stores
  provider, model, task, connection and key labels, outcome, error code, reported
  input/output/total tokens, estimated cost and its source, project/page/block ids
  and a timestamp. It never stores document text, images, crops, prompts, replies or
  raw provider responses. Costs are recorded only when the provider reports pricing
  or token counts the app can verify; otherwise the row is marked unpriced. The
  monthly budget is a local gate on verified recorded spend, not a provider billing
  control.
- `GET /api/ai/usage` returns the rolling 24-hour count, success/failure split,
  token totals, verified cost, unpriced count, attempts per task, per-connection
  totals and the recent entries. The task breakdown uses a stable order for known
  tasks and lists any other stored name alphabetically, so rows from another build
  still add up. `GET /api/ai/usage/history` pages the same ledger newest first with
  outcome/task filters and joins the project name; a row whose project was deleted
  stays visible with `project_name: null`. The ledger is read-only except for an
  explicit clear action.
- `POST .../ocr/blocks/{block_id}/ai-suggestions` loads the block and run, refuses
  missing, unfinished or stale OCR results, and sends the **block text only** through
  the `ocr_cleanup` route with a fixed correction prompt. The network call happens
  outside the SQLite transaction. Empty, non-text and oversized responses are
  rejected. The reply is inserted into `ai_suggestions` with `status = pending`;
  before insert the block text is read again, so a manual correction during the
  request refuses the proposal as stale instead of overwriting newer text.
- Accepting a proposal re-checks the OCR run and block text, then writes through
  `ocr.update_block`, which sets `corrected = true` and `verified = false`. An
  accepted proposal is therefore not a verification. Rejecting only updates the
  proposal status. The OCR dialog, the project-wide review queue and bulk decisions
  all use the same path; a stale item is skipped and reported per item while the rest
  of a batch still applies. Both review surfaces mark changed characters with a local
  `<del>`/`<ins>` diff and never contact a provider.
- Vision region proposals use the `region_proposals` route. `services.ai_vision`
  reads the page's display (or original) asset, resizes it to a bounded JPEG in
  memory and sends it as base64. The reply is validated as normalized 0–1
  rectangles, unsupported kinds and out-of-page origins are dropped, boxes are
  clamped, padded and de-duplicated, and regions that already have an element are
  removed. `POST .../pages/{page_id}/ai-region-proposals` returns low-confidence
  proposals and does not insert rows; choosing one only prefills the extraction
  dialog.
- `POST .../elements/{element_id}/ai-equation` uses the `equation_transcription`
  route, refuses a non-equation region and a missing crop, and sends only that crop.
  The reply is reduced to plain LaTeX (code fences, math delimiters and wrapping
  quotes are stripped, never rewritten) and returned as an unverified proposal; it is
  not persisted. `POST .../elements/{element_id}/ai-table` uses `table_structure`,
  refuses a non-table region, and accepts only a complete rectangle within the same
  60 × 20 × 600 limits as a local table proposal. A ragged, empty, oversized or
  non-text reply is refused rather than padded. Every cell is unscored
  (`no_confidence`), so the review grid requires acknowledgement before insertion;
  nothing is written back to the element.
- The one-time migration in `services.ai_migrate` runs from the AI routes and on
  startup. It converts legacy `app_settings.ai.text` and `ai.vision` profiles into
  connections, copies their encrypted keys vault-to-vault, imports their model names
  and creates task routes, then records a completion marker. The legacy JSON is kept
  as a backup, and a failed migration leaves the old values untouched and retries
  later. A new database does not need the migration.
- Tests use a loopback stub HTTP server, not a real model. They cover provider
  discovery, timeouts, unreachable servers, invalid responses, remote consent and
  HTTPS enforcement, cost-class normalization, paid refusal without network access,
  rate-limit/auth classification and cooldowns, key rotation and failover, global and
  per-connection/per-task limits, usage recording and token/cost accounting, task
  routing and capability validation, legacy migration, stale OCR runs and text,
  suggestion decisions and bulk review, vision coordinate mapping and filtering,
  equation wrapper reduction, table-grid parsing and the review-shaped responses.
  A separate migration test upgrades a database that already holds legacy usage rows
  from revision 0002 to head, checks the rows survive, and downgrades again.
  This verifies protocol handling and review safety, not model quality.

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
- No secret is persisted or logged by the frontend: a typed key lives only in
  component state until the user saves it, and the draft is cleared afterwards.
  Provider keys are optional and stored only in the encrypted local vault; the API
  returns metadata (`has_secret`, label, limits, state) and never the value. A key is
  decrypted in the backend only for the request that uses it and is sent only to that
  connection's endpoint. `app.db` stores connections, key metadata, cached model
  metadata and task routes, never a key.
- The cost class is a request gate, not a billing engine. Loopback inference is local;
  a remote connection cannot stay marked local, so a remote connection saved without
  an explicit class defaults to paid. A paid connection needs `confirm_paid: true` for
  OCR cleanup, region proposals, equation transcription and table reading, checked
  after URL/consent validation and before any limit check or network call, so a
  refused action sends nothing and records nothing. The app never invents provider
  prices, verifies a declared free tier or enforces a provider-side cap; the optional
  monthly budget only gates verified spend recorded in the local ledger.
- The encrypted key files live under the user data folder, not in a project or in
  Git. `.gitignore` excludes local data folders, databases and `*.key`/`*.enc`
  files; the repository contains no sample key and no default master key.
- AI usage history is metadata only: provider, model, task, connection/key labels,
  outcome, error code, reported token counts, verified cost and project/page/block ids
  with timestamps. It never stores sent text, page images, crops or model output, and
  request limits are enforced before a provider is contacted.
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
  one hour and deletes it after a successful page or document apply; page-image and
  region-crop repair keep it so several images can be repaired from one inspection,
  and the one-hour cleanup removes it afterwards. A forgotten dialog therefore does
  not leave a second copy of the project on disk indefinitely.
- Document links are validated to `http`, `https` or `mailto` before they enter the
  document, and Markdown export repeats that check. A stored `javascript:` or
  `data:` target is never emitted as a link; only its text is kept.
- AI requests are sent only when the user tests a connection or runs an action that
  has a route, and only to that route's saved connection. A cleanup sends one OCR text
  block; a region request sends the current page image only; an equation or table
  request sends one saved crop. The backend rejects non-HTTP(S) URLs, embedded
  credentials and well-known metadata hosts, requires HTTPS and explicit consent for
  remote hosts, does not follow redirects and bounds every response. The router never
  switches to a connection or key the user did not configure, never bypasses a
  provider limit and never sends an unauthenticated request in place of a configured
  key. A paid connection additionally needs a per-action confirmation in the UI before
  the request is sent. Cleanup replies are stored as reviewable proposals; region
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
  download, and are cheap to explain and test. Simple table structure can be
  derived from stored word boxes, including vertically contiguous row blocks, but
  without merged cells. Embedded PDF raster images supply precise figure boxes
  without a model; vector drawings and artwork in photographed pages still need
  manual selection or a later detector.
- **AI is optional and proposal-only** — the AI workflows correct one OCR block or
  propose reviewable page regions through a user-configured connection. Local Ollama or
  a local OpenAI-compatible server keeps the path free and offline; any remote host
  needs stored consent, HTTPS and a cost class, with provider/model/URL provenance and
  explicit review. The trade-off is that the app carries a provider abstraction and a
  credential vault, and that a user can still configure a paid provider the app cannot
  bill or audit.
- **Element extraction is manual first** — a crop is an exact pixel copy of the
  page, not inferred structure. This preserves accuracy and needs no model, at the
  cost of no automatic figure/equation detection. A table crop stays an image;
  editable cells come from the separate OCR table proposal, not from the crop.
