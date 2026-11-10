# DocuRebuild

**A local-first, AI-assisted document reconstruction workspace.**

DocuRebuild turns scans, photographs and PDF documents into accurate, structured
and editable documents. It keeps original source files immutable, keeps project
data on your device, and treats every AI result as a reviewable proposal.

> **Project status — early development (Phase 5 of 12).**
> The workspace, local project storage, image and PDF import, non-destructive
> image adjustments, the rich-text editor, local Tesseract OCR and manual region
> extraction are implemented. Imports run as background jobs with page-level
> progress, cancellation and localized failures. PDF pages are rendered locally and
> embedded text layers are stored as reviewable proposals; image-only PDF pages can
> be processed with OCR. OCR and PDF import are only advertised when their local
> dependencies actually work. AI providers, structured table/figure/equation
> reconstruction, export and history are **not implemented yet** and are clearly
> marked as unavailable in the UI. Nothing in this repository fakes those features.

---

## Current capabilities

### Working today

- **Local project management** — create, rename, reopen and delete projects. Deleted
  projects are moved to a local trash folder rather than destroyed.
- **Per-project storage** — each project gets its own SQLite database, manifest,
  source files, processed copies, thumbnails, exports and backups folders.
- **Image import** — drag and drop or file picker; JPG, PNG, WebP, BMP and TIFF.
  Limits and validation errors come from the backend, not hardcoded UI values.
- **PDF import** — text-based, image-based and mixed PDFs. The original PDF is
  stored once as an immutable source asset, and every page is rendered locally at
  150 DPI into a display copy with a thumbnail. Embedded text is stored as a
  reviewable extraction run, so image-only pages can be OCR'd separately.
  Password-protected PDFs are rejected with a clear message.
- **Background import jobs** — every batch is processed by a bounded local worker.
  The workspace shows page-level progress, the current filename and a cancel
  action. Cancelling keeps files that already finished, rolls back the file in
  progress and reports failures with localized messages. Jobs interrupted by a
  restart are reported instead of appearing stuck.
- **Source viewer** — page navigation, thumbnail rail, zoom, fit, actual size,
  rotation with non-destructive display copies, page reordering and page deletion.
  PDF pages are re-rendered from the original PDF when rotated, so repeated
  rotations do not accumulate resampling artifacts.
- **Non-destructive image adjustments** — drag-to-select crop, four-corner
  perspective correction, straighten with automatic skew estimation, grayscale,
  contrast, brightness, sharpness, denoise, threshold (B&W), shadow removal and
  background cleanup. Edits are stored on the page and re-rendered from the
  immutable source, with a before/after comparison and one-click reset.
- **Local OCR (optional)** - Tesseract runs on the local machine when installed.
  English and Burmese language data are supported. Results include text blocks,
  confidence values and source bounding boxes; each block can be corrected,
  marked verified, copied or inserted into the document with a source note.
  Deterministic layout hints (heading, list, caption, equation, table-like grid,
  running header/footer, page number) are attached to blocks as review
  candidates, and a measured bounding-box overlay can be shown on the source
  image. OCR is never advertised as available unless the engine and language
  data are actually detected.
- **Region extraction (manual + suggestions)** — drag a rectangle on the source page
  or type its source-pixel coordinates, then crop a figure, table or equation
  region. Crops are stored as immutable project assets, can be captioned, verified
  and inserted into
  the document as figures with an optional source note. Saved crops can also be
  read with the local OCR engine; the text, confidence and engine/language metadata
  are stored as an unverified proposal that can be reviewed, corrected, typed
  manually or inserted. The per-page region library supports reinsertion and
  deletion to local trash. If the page was changed after extraction, the region is
  marked stale; the saved crop is never silently treated as matching a newer page.
  A "Suggest regions" overlay derives reviewable figure, table and equation
  suggestions from the latest local OCR layout. Suggestions are never saved on
  their own: choosing one only prefills the normal extraction dialog.
- **Document editor** — Tiptap rich text with headings, paragraphs, lists,
  blockquotes, code blocks, alignment, inline formatting, undo/redo, word and
  character counts, and debounced autosave.
- **Appearance and language** — light/dark/system themes, accent colours, radius,
  blur, density, text size, reduced motion, and live English/Burmese switching.
- **Local-only defaults** — no account, no cloud database, no telemetry, no network
  request unless you explicitly add a future provider integration.

### Not available yet

Structured element reconstruction (table cells, equation transcription, generative
figure detection), AI providers, DOCX/TXT export, revision history, backups/restore
UI, desktop packaging and PWA install support are planned but not implemented. OCR
extracts text blocks, reading order and conservative layout hints; it does not build
table structure or transcribe equations. Region extraction produces exact pixel
crops and can read their plain text locally; it does not build structured table
cells or equation markup. Region suggestions are deterministic heuristics over the
OCR text layout, not a vision model: they cover OCR table/equation blocks and the
empty band above a figure-like caption, and they are skipped when no suitable
layout exists. See [`docs/roadmap.md`](docs/roadmap.md).

---

## Core principles

1. **Local-first** — documents and assets stay on the user's device.
2. **Free usage first** — the core app must work without paid APIs or accounts.
3. **User-controlled** — processing methods, providers and appearance are selectable.
4. **Accuracy first** — originals are immutable; uncertain content is never invented.
5. **Manual + AI** — every AI-assisted workflow will have a manual alternative.
6. **Modular** — storage, processing engines and providers use explicit adapters.
7. **Production quality** — accessibility, security, tests and honest limitations.

---

## Technology

| Layer | Technology |
| --- | --- |
| Web client | React 18, TypeScript, Vite, Tailwind CSS, Radix UI primitives |
| Editor | Tiptap 3 (ProseMirror) |
| i18n | i18next / react-i18next (English default, Burmese secondary) |
| Local API | Python, FastAPI, SQLAlchemy, Alembic, SQLite |
| Image processing | Pillow |
| PDF rendering | PyMuPDF (AGPL, runs locally; no external service) |
| Tests | Pytest, Vitest, Testing Library |

The repository is an npm-workspaces monorepo. `packages/shared-types` holds the
contracts shared by the client and API, and `packages/design-tokens` holds the
design tokens and Tailwind preset.

---

## Repository layout

```text
apps/
  web/                  React client (Vite dev server on :5173)
backend/
  app/                  FastAPI application and services
  alembic/              Application-database migrations
  tests/                Pytest suite
packages/
  design-tokens/        CSS variables, Tailwind preset, theme tokens
  shared-types/         Shared TypeScript contracts
docs/
  architecture.md       Modules, storage layout, data model, API surface
  roadmap.md            Phase status, limitations and next steps
start-docurebuild.bat   Windows one-click launcher for the local app
AGENTS.md               Permanent instructions for AI coding agents
Prompt.md               Product specification and phased roadmap source
```

Local runtime data is **never** stored in this repository. See
[Data and privacy](#data-and-privacy).

---

## Requirements

- Node.js **20 or newer** (Node 24 tested) and npm 10+
- Python **3.11 or newer** (3.12 tested)
- Optional: Tesseract 5+ for local OCR, with `eng` and/or `mya` traineddata

PDF import needs no separate system package: PyMuPDF is installed with the
backend requirements and runs entirely on the local machine.

---

## Setup

```bash
# 1. Install JavaScript dependencies
npm install

# 2. Create the backend virtual environment
python -m venv backend/.venv

# Windows
backend\.venv\Scripts\activate
# macOS / Linux
source backend/.venv/bin/activate

# 3. Install backend dependencies
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt

# 4. Optional local configuration
cp .env.example .env
```

The backend creates its data directory automatically:

- Windows: `%LOCALAPPDATA%\DocuRebuild\DocuRebuild`
- macOS: `~/Library/Application Support/DocuRebuild`
- Linux: `~/.local/share/DocuRebuild`

Override it with `DOCUREBUILD_DATA_DIR`.

### One-click launch (Windows)

Double-click `start-docurebuild.bat`. It starts the local API and web client,
opens the app at <http://localhost:5173>, and keeps both servers in minimized
windows. Close those windows to stop them.

The first launch installs any missing dependencies and therefore needs an
internet connection; later launches work offline. On macOS and Linux, activate
the backend virtual environment and run `npm run dev` instead.

### Optional local OCR

OCR is free and local, but it needs a working Tesseract installation:

1. Install Tesseract (Windows builds are available from UB Mannheim; macOS and
   Linux packages are also available).
2. Make sure the `eng` and/or `mya` traineddata files are present in the
   Tesseract `tessdata` folder.
3. DocuRebuild finds the executable automatically: it tries
   `DOCUREBUILD_TESSERACT_CMD`, then `tesseract` on `PATH`, then the standard
   install locations (for example `C:\Program Files\Tesseract-OCR` on Windows).
   Only set the path explicitly if Tesseract lives somewhere unusual:

```bash
# Windows example
DOCUREBUILD_TESSERACT_CMD="C:/Program Files/Tesseract-OCR/tesseract.exe"
DOCUREBUILD_TESSDATA_DIR="C:/Program Files/Tesseract-OCR/tessdata"
```

The Settings page and the OCR dialog inspect the engine at runtime and report the
resolved executable path. If it cannot be found, they show setup guidance instead
of a fake OCR result. OCR jobs run in a bounded local worker and never contact a
remote service.

If the Tesseract install directory is read-only (for example `Program Files` on
Windows), keep a user-writable copy of the `tessdata` folder containing the
language files you need and point `DOCUREBUILD_TESSDATA_DIR` at it. The folder
must contain the required `*.traineddata` files; OCR returns an explicit error
instead of an empty success when the engine cannot produce structured output.

After a run finishes, the layers button in the source toolbar shows the measured
block boxes on the page with a per-kind legend. The overlay is hidden when the
stored result no longer matches the page (for example after a rotation) so stale
coordinates are never drawn.

### PDF import

PDF support is local and works without an AI provider or API key:

- Each imported PDF is stored once under `source/`; the file is never rewritten.
- Every page is rendered at import time (`DOCUREBUILD_PDF_RENDER_DPI`, default
  150) into `processed/<page-id>-page.png`, with a WebP thumbnail.
- An embedded text layer, when present, is stored as a normal reviewable
  extraction run with `engine = pdf-text` and no confidence score. It appears in
  the same Extract text dialog as OCR, so blocks can be corrected, verified or
  inserted into the document.
- Image-only pages simply have no embedded run; run local OCR on them when
  Tesseract is available.
- Rotation re-renders the page from the immutable PDF instead of rotating the PDF
  or repeatedly resampling the previous display copy.
- Password-protected and empty PDFs are rejected with a localized error. The
  default per-file limit is 1,000 pages (`DOCUREBUILD_PDF_MAX_PAGES`).

Embedded PDF text is exact source data, but it can still contain encoding errors,
missing glyphs or an incorrect reading order. The dialog marks it as a proposal
and offers no confidence score rather than pretending it was OCR-verified.

### Import progress and cancellation

Image and PDF batches are validated synchronously, then handed to a bounded local
worker (`DOCUREBUILD_IMPORT_MAX_WORKERS`, default 2). Progress is committed per
file and per PDF page, so the workspace can show how many pages are done, which
file is running and a cancel action without losing work on a long PDF.

Cancelling is cooperative and checked between files and pages. Files that already
finished stay imported; the file currently being processed is rolled back
completely, and its immutable source copy is removed. The same cleanup runs when
an import fails, so a failed PDF never leaves orphaned pages. Jobs interrupted by
an application restart are marked `import_interrupted` instead of polling forever.
The older synchronous `POST /pages/import` endpoint remains available for simple
clients and keeps all-or-nothing behaviour.

### Run in development

```bash
npm run dev        # API on http://127.0.0.1:8000 and web on http://localhost:5173
```

Or run each side separately:

```bash
npm run dev:api
npm run dev:web
```

The API exposes interactive documentation at `http://127.0.0.1:8000/api/docs`.
Vite proxies `/api` to the local backend.

### Checks

```bash
npm run typecheck  # TypeScript
npm run lint       # ESLint
npm run test:web   # Vitest
npm run test:api   # Pytest
npm run build      # typecheck + production build
```

On Windows, the root scripts call `python`; activate `backend/.venv` first (or pass
the interpreter explicitly) so backend dependencies are importable.

---

## Data and privacy

Everything below stays on the local machine and is excluded by `.gitignore`:

```text
<data dir>/
  app.db                 application database (project registry, settings)
  projects/<project-id>/
    project.db           project database (document, pages, assets, history, jobs)
    manifest.json        portable project manifest
    source/              immutable imported originals (images and PDFs)
    processed/           non-destructive display copies (rotations, PDF page renders)
    thumbnails/          cached WebP thumbnails
    exports/             future export output
    backups/             future project backups
    trash/               per-project runtime trash
  trash/                 deleted project folders
```

- API keys and user documents are never committed or uploaded by the application.
- Source images and PDFs are immutable; transformations write new display assets.
  Deleting a PDF page keeps the shared original until its last page is removed.
- Asset paths stored in databases are relative and validated against traversal.
- The local API binds to loopback by default and sends no telemetry.
- GitHub is used only for source code and documentation. User data is **not** a
  GitHub backup category. See [`AGENTS.md`](AGENTS.md).

---

## Internationalization

- English is the default and canonical fallback.
- Burmese is the secondary language and uses Unicode only. Zawgyi text is
  preserved exactly as imported; there is no automatic conversion.
- Interface strings live in `apps/web/src/i18n/locales/<language>/<namespace>.json`.
- Language changes apply immediately without a reload and do not alter document
  content.
- Adding a language means adding a locale folder and registering it in
  `apps/web/src/i18n/index.ts`; feature code does not need to change.

---

## Known limitations

- The editor covers core rich text, not the full target model (editable tables,
  equation nodes, footnotes, page layout and find/replace are pending). Figures are
  supported as block image nodes from the region library.
- Autosave is debounced and best-effort when leaving the page; there is no
  revision history yet, so destructive edits are not recoverable.
- `npm audit` reports moderate findings in the ESLint/TypeScript-ESLint toolchain
  (via `minimatch`). They are development-only and do not ship in the client
  bundle; no fixed upstream release is available yet.
- The web client currently requires the local API; browser-only OCR/PDF
  processing is not claimed.
- OCR quality depends on the installed Tesseract version, traineddata and page
  quality. Burmese text is especially difficult; layout labels are heuristics and
  are never presented as certain structure. Table labels only mark a text grid:
  cells, merged spans and reading order inside the table are not reconstructed,
  and equations are not transcribed.
- Region extraction does not use a vision model. Suggestions are deterministic
  heuristics over the latest OCR text layout: OCR table/equation blocks and the
  empty band above a figure-like caption. Uncaptioned figures, artwork separated
  from its caption, and regions OCR did not read are not suggested, so manual
  selection remains the fallback. A suggestion is never saved automatically; it
  only prefills the extraction dialog. The stored element is an exact pixel crop
  rather than cells or LaTeX. A crop is marked stale when the page is re-rendered
  after extraction, but the crop file itself remains unchanged.
- Region text extraction returns plain text from the crop through local Tesseract.
  It does not reconstruct table cells, merged spans, reading order inside tables or
  equation markup. The text is an unverified proposal and may omit or misread
  characters; manual correction is always available and never overwrites the crop.
- The bounding-box overlay only draws the latest successful run and is hidden
  when that run is stale, failed or lacks geometry. It shows where text was
  found; it is not a verified layout model.
- Embedded PDF text is not OCR and has no confidence score. Encoding problems,
  missing glyphs and unusual reading order are possible; text is never claimed to
  be verified until the user marks it.
- PDF import does not support password-protected files, forms, annotations,
  digital signatures or PDFs above the configured page limit. Page rendering uses
  a fixed DPI rather than per-page dynamic resolution.
- PyMuPDF (the PDF rendering library) is dual-licensed under AGPL-3.0 or a
  commercial Artifex licence. Running DocuRebuild locally is unaffected, but
  anyone distributing a packaged build should review those terms before release.
- OCR results and extracted regions become marked stale when the page image or
  rotation changes. They are never silently applied as if they matched the new
  page. The same applies to embedded PDF text after a page is rotated.
- npm install scripts for `esbuild` are blocked by the local npm policy; Vite
  still runs because its binary is already present. If a fresh install fails,
  review the blocked install script with `npm install-scripts ls`.

---

## Roadmap

| Phase | Status |
| --- | --- |
| 0. Foundation and architecture | Complete |
| 1. Local storage and project management | Complete |
| 2. Main UI and workspace | Complete |
| 3. Import and image processing | Complete |
| 4. Local OCR and layout detection | In progress: OCR + layout hints done; figures, table structure and benchmarks pending |
| 5. Element extraction | In progress: manual region crop, local region text extraction, heuristic region suggestions, library, verification and figure/text insertion done; structured table/equation reconstruction pending |
| 6. AI integration and free usage first | Planned |
| 7. Table, figure and equation reconstruction | Planned |
| 8. Document editor and export | Planned |
| 9. History, backup and recovery | Planned |
| 10. Desktop, PWA and mobile distribution | Planned |
| 11. Final QA and production release | Planned |

Detailed criteria and design decisions are in [`docs/roadmap.md`](docs/roadmap.md)
and [`docs/architecture.md`](docs/architecture.md).

---

## Source repository

The authoritative remote is configured by the project owner. Do not force-push,
rewrite history, or upload user data. Repository integration and backup rules are
documented in [`AGENTS.md`](AGENTS.md).
