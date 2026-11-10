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
| `services.documents` | Document row, Tiptap JSON persistence, timestamps |
| `services.settings` | Persisted appearance, language and editor settings |
| `services.ocr` | Tesseract detection, language packs, bounded OCR jobs, block persistence, corrections, staleness |
| `api.routes.*` | HTTP surface (`/api/...`) |

### Storage model

The application database (`app.db`) contains only global state:

- `projects` — id, name, description, directory, timestamps
- `app_settings` — key/value JSON (appearance, language, editor)
- `schema_migrations` — created by Alembic

Each project owns a portable folder and its own `project.db`:

- `documents` — Tiptap JSON content and plain text
- `assets` — relative path, MIME type, size, checksum, dimensions
- `pages` — page order, source/display/thumbnail asset references, rotation,
  `pdf_page_number` for PDF pages, status, and an `edits` JSON document holding the
  ordered geometry steps plus filter settings
- `history_events` — append-only local event log
- `jobs` — background import jobs: status, progress, total/imported pages, current file, payload (file counts/names), error code/message and timestamps
- `ocr_runs` — page extraction attempts: status, engine/version, languages, source asset, rotation, mean confidence, error, timestamps; embedded PDF text uses `engine = pdf-text` and a null confidence
- `ocr_blocks` — reviewable text blocks with bbox, confidence, kind, line/word counts, correction and verification flags
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
  backups/      future backups
  trash/        per-project runtime trash
```

Relative asset references are stored in SQLite so a project folder can be moved
without rewriting paths. `resolve_within` rejects path traversal.

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
GET    /api/settings
PATCH  /api/settings
GET    /api/projects
POST   /api/projects
GET    /api/projects/{id}
PATCH  /api/projects/{id}
DELETE /api/projects/{id}
POST   /api/projects/{id}/open
GET    /api/projects/{id}/document
PUT    /api/projects/{id}/document
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
  components/workspace/   SourcePanel, EditorPanel, OcrDialog, workspace actions
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
- A best-effort flush runs when leaving the workspace; it is not a substitute for
  revision history.
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
- No secrets are stored in the frontend. No AI provider keys exist yet.
- OCR and PDF rendering run entirely on the local machine. Page images and PDF
  files are never uploaded; the backend reads the project's own source/display
  assets and invokes local libraries. Missing engine/language packs are reported,
  never bypassed with a cloud fallback.
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
