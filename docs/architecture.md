# Architecture

This document describes the DocuRebuild architecture as implemented. It is
intentionally honest about what is still a placeholder for later phases.

## System overview

```text
┌─────────────────────────────┐        ┌──────────────────────────────────┐
│ Web client (apps/web)       │  /api  │ Local API (backend/app)          │
│ React + Vite + Tailwind     │ ─────► │ FastAPI + SQLAlchemy             │
│ Tiptap document editor      │        │ Pillow image processing          │
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
| `services.pages` | Image validation, import, EXIF orientation, display copies, thumbnails, rotation, ordering |
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
- `pages` — page order, source/display/thumbnail asset references, rotation, status
- `history_events` — append-only local event log
- `jobs` — reserved for general background processing
- `ocr_runs` — page OCR attempts: status, engine/version, languages, source asset, rotation, mean confidence, error, timestamps
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

### Import and image rules

- Accepted: JPG, JPEG, PNG, WebP, BMP, TIFF.
- Files are validated by extension, size limit and Pillow decode.
- EXIF orientation is applied once at import.
- Browser-safe formats are stored as immutable originals.
- BMP/TIFF originals are preserved and a PNG display copy is written to
  `processed/`.
- Rotations create a new display copy; the original is never modified.
- Thumbnails are WebP, bounded by a maximum edge, and cached by asset id.

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
POST   /api/projects/{id}/pages/{page_id}/rotate
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

### Local OCR workflow

- The source panel starts OCR for the active page. The dialog first calls
  `GET /api/ocr/capabilities` and shows an honest setup state when Tesseract or a
  requested language pack is missing; no request is sent to a cloud service.
- Runs are executed by the backend in a bounded `ThreadPoolExecutor`; the client
  polls the run until it reaches `succeeded` or `failed`.
- Each run stores engine, version, requested languages, source asset id, page
  rotation and timestamps so the result can be audited and invalidated.
- Results are split into reviewable blocks with bounding boxes and confidence.
  Low-confidence blocks are flagged; every block can be edited and marked as
  verified, and corrections are persisted in `ocr_blocks`.
- Existing results stay reviewable and insertable even when the engine is later
  unavailable or a language pack is missing; the dialog shows the setup banner
  and the stored run together instead of hiding the user's prior work.
- A run becomes stale when the page image or its rotation changes after
  completion; the UI surfaces this instead of silently reusing stale text.
- Selected blocks are appended to the Tiptap document through the workspace
  actions context. The insertion is a normal document edit and is autosaved; an
  optional localized source note records the page and verification status.
- OCR settings are environment-driven: `DOCUREBUILD_TESSERACT_CMD`,
  `DOCUREBUILD_TESSDATA_DIR`, timeout, maximum edge and worker limits. These are
  reported through capabilities rather than exposed as arbitrary UI controls.
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
- OCR runs entirely on the local machine. Page images are never uploaded; the
  backend reads the project's own display copy and invokes a local Tesseract
  binary. Missing engine/language packs are reported, never bypassed with a cloud
  fallback.
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
