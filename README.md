# DocuRebuild

**A local-first, AI-assisted document reconstruction workspace.**

DocuRebuild turns scans, photographs and PDF documents into accurate, structured
and editable documents. It keeps original source files immutable, keeps project
data on your device, and treats every AI result as a reviewable proposal.

> **Project status — early development (Phase 6 of 12).**
> The workspace, local project storage, image and PDF import, non-destructive
> image adjustments, the rich-text editor, local Tesseract OCR, manual region
> extraction, an optional local-AI OCR text cleanup, optional vision region
> proposals, local Markdown/TXT/Word document export and document version history
> are implemented. Imports run
> as background jobs with page-level progress, cancellation and localized failures.
> PDF pages are rendered locally and embedded text layers are stored as reviewable
> proposals; image-only PDF pages can be processed with OCR. OCR and PDF import are
> only advertised when their local dependencies actually work. The AI workflow only
> talks to an Ollama or OpenAI-compatible server that the user configures and tests;
> loopback addresses are the default, and any other host needs explicit remote
> consent. Every result is a proposal that must be accepted or rejected. Cloud
> providers, free-tier adapters, paid usage, image generation and structured
> table/figure/equation reconstruction are **not implemented yet** and are clearly
> marked as unavailable in the UI. Nothing in this
> repository fakes those features.

---

## Current capabilities

### Working today

- **Local project management** — create, rename, reopen and delete projects. Deleted
  projects are moved to a local trash folder rather than destroyed.
- **Per-project storage** — each project gets its own SQLite database, manifest,
  source files, processed copies, thumbnails, exports and working folders, plus a
  shared local vault for verified backup copies.
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
- **Optional local AI text cleanup** — connect an Ollama server or an
  OpenAI-compatible local server (for example LM Studio) in Settings, test the
  connection, discover installed models and choose a text model. In the OCR dialog,
  "Ask local AI" sends only the selected text block to that configured local URL and
  stores the reply as an `ai_suggestion` with provider, model, base URL and original
  text. The proposal is shown beside the current OCR text and can be accepted or
  rejected. Accepting is refused when the block changed after the proposal was
  created, and OCR text changes are refused if the run is stale. No cloud provider
  or paid API is used, and AI output never becomes document content automatically.
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
  When a vision model is saved in Settings, "Ask AI for regions" sends only the
  current page image to that configured local server and shows its figure, table
  and equation proposals as clearly marked low-confidence regions. Nothing is
  saved automatically; each proposal goes through the same review and extraction
  dialog, and every request counts toward the AI usage limit.
- **Document editor** — Tiptap rich text with headings, paragraphs, lists,
  blockquotes, code blocks, alignment, inline formatting, links, undo/redo, word
  and character counts, debounced autosave, and find/replace with match-case and
  replace-all. Matches can span inline formatting but never jump between
  paragraphs or hard breaks. Selecting a figure lets you correct its caption and alt
  text while the image and its source note stay untouched, and you can give a figure
  an optional generated number. Numbered figures can be cited from the text; the
  citation shows the figure's live number and follows it when it moves.
- **Local Markdown, TXT and Word export** — the editor header downloads the saved
  document as Markdown, plain text or a Word file. The export is generated on this
  device by the backend from the same document the editor autosaves; unsaved changes
  are flushed first, and the download is refused if that save fails. Extracted text
  is escaped so it can never turn into Markdown structure, and equations are written
  as their LaTeX source with any numbering kept after the equation. Word output
  embeds the project's own figure images and converts equations to native Word
  equations, keeping the LaTeX as a visible fallback when a formula cannot be
  converted.
- **Document versions** — the editor header keeps a local version history. Automatic
  versions are captured when the document changes, a manual checkpoint can be saved
  at any time, restoring a version always keeps the state it replaces, so a restore
  is itself reversible, and a read-only line comparison shows what differs from the
  text on screen.
- **Project backup and restore** — download a verified `.zip` of a whole project
  (manifest, a consistent database snapshot, source and processed images,
  thumbnails, exports) from the dashboard or the workspace. Restoring a backup
  always creates a new project and never overwrites existing work. Everything is
  written and read on this device; nothing is uploaded.
- **Local backup vault** — keep verified copies of a project on this device from the
  workspace project menu. Copies are created when you ask, or after opening a project
  when you opt in and the newest copy is older than the configured interval. The
  number kept is configurable (five by default) and the oldest is pruned after a new
  copy is written. Any copy can be downloaded again, restored as a new project, or
  deleted explicitly; downloading never removes it. Deleting a project moves its
  vault copies to the local trash. The vault is not encrypted and is not synced
  anywhere.
- **Manual tables** — insert an empty table from the editor toolbar with 1–10
  rows and columns and an optional header row, then add or delete rows and columns,
  toggle the header, or delete the table. Every cell is typed by hand; no cell text
  is generated from a source image. Tables are part of the saved document, version
  history, backups and Markdown/TXT/Word export.
- **Equations** — insert a display equation or an inline formula from the toolbar
  dialog and check the local KaTeX preview before inserting it. Empty or invalid
  LaTeX is refused rather than saved. Display equations can be given an optional
  number: the editor shows it from document order, and Markdown/TXT/Word export
  writes the same `(n)` label after the equation, while the saved LaTeX never
  contains it. A numbered display equation can be cited from the text; the
  citation shows `Equation (n)` and follows the equation when it moves.
  Only the LaTeX source is stored, so equations work offline and are part of the
  document, versions, backups, Markdown (`$$` blocks and `$...$` formulas), plain
  text and Word export (native equations). Equations are typed by you; OCR or AI
  equation recognition is not implemented.
- **Footnotes** — insert a footnote from the toolbar and type its text in the
  dialog. Footnotes are numbered in document order, so inserting or deleting one
  renumbers the rest automatically; the number is never stored in the note. Export
  keeps the text: Markdown writes GitHub-flavoured `[^n]` markers with definitions,
  plain text appends a `Notes:` section, and Word writes native footnotes. Footnotes
  are never detected from the source automatically, and an empty note is refused.
- **Project activity log** — the workspace project menu lists local events newest
  first: imports, page processing, region extraction, OCR, document exports and
  backups. Entries are metadata only (counts, formats, sizes, ids and timestamps);
  document text and OCR output are never copied into the log. The list can be
  filtered, searched and exported as CSV or JSON without uploading anything.
- **Appearance and language** — light/dark/system themes, accent colours, radius,
  blur, density, text size, reduced motion, and live English/Burmese switching.
- **Local-only defaults** — no account, no cloud database, no telemetry, and no
  outbound request unless you explicitly test or use a local AI server you
  configured. The app remains usable without any AI provider.

### Not available yet

Structured element reconstruction (automatic table-cell extraction, automatic
equation transcription, generative figure detection), cloud/free-tier AI providers,
image-generation profiles, selective restore from an
archive, backup encryption, PDF layout export, desktop packaging and PWA install
support are planned but not implemented. OCR extracts text blocks,
reading order and conservative layout hints; it does not build table structure or
transcribe equations. Region extraction produces exact pixel crops and can read
their plain text locally; it does not build structured table cells or equation
markup. Deterministic region suggestions are heuristics over the OCR text layout,
not a vision model: they cover OCR table/equation blocks and the empty band above a
figure-like caption, and they are skipped when no suitable layout exists. The
optional vision path only proposes rectangles for review; it does not read their
text, invent content or change the document. The local AI workflow does not switch
providers silently or use any remote service without consent.
See [`docs/roadmap.md`](docs/roadmap.md).

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
| Equations | KaTeX (bundled locally, MIT) |
| Word export | python-docx, latex2mathml, mathml2omml (all run locally) |
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
- Optional: Ollama or an OpenAI-compatible local server (for example LM Studio)
  for reviewable AI text cleanup. No API key or account is required.

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

### Optional local AI cleanup

AI cleanup is optional and free to run locally. It is not needed to use the
application, and OCR review works without it.

1. Start a local server:
   - **Ollama** — default `http://127.0.0.1:11434`; pull a text model such as
     `ollama pull qwen2.5:7b`.
   - **OpenAI-compatible** — for example LM Studio's local server; the default
     address is `http://127.0.0.1:1234/v1`.
2. Open **Settings → Local AI**, keep or change the provider, and use **Test
   connection** to discover installed models.
3. Choose a text model and select **Save AI settings**. Localhost and loopback URLs
   need no extra approval. If the server is on another host or IP that you control,
   enable **Remote endpoint consent** first; until you do, the backend refuses to
   contact that URL for either a connection test or a cleanup.
4. Optionally set a rolling 24-hour **Request limit**. Zero means unlimited.
   Connection tests are not counted.
5. Optionally add a **Vision model** name (for example `llava:7b`) if the same
   server has one installed. Leave it empty to keep image AI disabled.
6. Open **Extract text** on a page and select **Ask local AI** on one text block.
   For region proposals, use **Ask AI for regions** in the source viewer.

Only that block's text is sent, to the URL you configured. The reply is stored as an
unverified proposal with provider, model, URL and the original text. The OCR text
does not change until you accept the proposal, and accepting is blocked if the block
changed after the proposal was created. Rejecting keeps the OCR text unchanged.
Pending proposals are read back from the project database when the dialog opens, so
closing and reopening it does not discard an unreviewed proposal. Accepted and
rejected proposals remain available in the block's read-only **Proposal history**,
including the original and proposed text, provider, model and decision time. That
record is kept even if the block is corrected again later. The source toolbar's
**Review AI proposals** dialog lists pending proposals from every page so they can
be accepted or rejected without reopening each OCR dialog.

Region proposals use the same saved connection and the optional vision model. Only
the current page image is resized locally and sent; the reply is shown as
low-confidence figure, table and equation rectangles. Nothing is saved until you
choose a rectangle and confirm the normal extraction dialog, so the proposal can
never silently become a document element.

Each cleanup or region-proposal attempt is recorded in the local application database
as metadata only: provider, model, task, outcome, error code and time. The selected
document text, page image and model output are never written to that usage history.
Settings shows the requests from the last 24 hours and the most recent entries; when
a configured limit is reached, the backend refuses the next request before contacting
the server.

The URL is only contacted when you press **Test connection**, **Ask local AI** or
**Ask AI for regions**; nothing is downloaded, loaded or generated in the background.
There is no cloud provider, API key or paid call in this phase. A model name can also
be typed manually when discovery is unsupported by the server.

### Document tables

Tables are reconstructed manually, cell by cell:

- The table button in the editor toolbar inserts an **empty** table. Choose 1–10
  rows and columns and whether the first row is a header. Nothing is filled in,
  copied or guessed from the source page.
- With the cursor inside a table the same menu adds a row above/below or a column
  left/right, deletes the current row or column, toggles the header row, or deletes
  the whole table. The picker limit only applies to the initial insert; rows and
  columns can be added afterwards.
- Select more than one cell to **merge** them into a single cell, and **split** the
  current merged cell back apart. The stored `colspan`/`rowspan` attributes are
  exported faithfully instead of being flattened.
- Tables are ordinary Tiptap nodes in the saved document. Autosave, version
  history and project backups treat them like any other content, and they never
  contain local asset URLs.
- Column resizing is deliberately disabled: stored pixel widths would make the
  layout depend on the screen that typed them, and Markdown cannot preserve them.
  Cells are typed from the source and remain the user's responsibility; the app
  does not mark them verified.

### Document export

Markdown, plain-text and Word export are local and need no provider, account or
extension:

- Open the workspace and use the download button in the document header, then
  choose **Markdown (.md)**, **Plain text (.txt)** or **Word document (.docx)**.
- Unsaved editor changes are saved first. If that save fails, nothing is
  downloaded and the editor shows the usual save error, so the file cannot
  silently lag behind the screen.
- Markdown keeps headings, lists, blockquotes, code blocks, rules, bold, italic,
  strikethrough, underline, links (http/https/mailto only) and hard breaks.
  Extracted text is escaped, so a line that happens to look like `# heading` or
  `- list` stays literal text.
- Figures are written as an explicit `[Figure: <caption>]` marker plus their
  source note in Markdown and plain text; a numbered figure becomes
  `[Figure n: <caption>]`. The image itself is not embedded there, because it
  remains a local project asset that has no meaning outside the app. Word export
  embeds the image instead, with the caption below it and the source note kept as
  recorded; a numbered caption gains a `Figure n.` prefix.
- Figure citations are exported as their resolved label, `Figure n`, at the place
  in the sentence where they appear. A citation whose figure was deleted or is no
  longer numbered is written as `Figure (missing)` rather than silently becoming a
  different number. The stored document keeps only the target id, so renumbering a
  figure updates every citation in every format.
- Equation citations use the same rule: a numbered display equation is written as
  `Equation (n)` where it is cited, or `Equation (missing)` when the target was
  deleted, unnumbered or was inline math. The LaTeX itself is never rewritten to
  carry a citation number.
- Footnotes export their stored text. Markdown writes `[^n]` at the citation point
  and a matching `[^n]: text` definition (continuation lines indented); plain text
  writes `[n]` and a `Notes:` section; Word writes a native footnote part, so the
  note is editable in Word rather than pasted into the sentence.
- Tables export as GitHub-flavoured Markdown. A literal `|` is escaped, multiple
  paragraphs in one cell are joined with `<br>`, and a table without a header gets
  a blank structural header row. If merged cells are present, the table is written
  as HTML instead so `colspan`/`rowspan` content is neither duplicated nor dropped.
  Plain-text export keeps every cell with ` | ` separators. Word export uses a
  native table and reproduces merged cells, so its columns stay editable.
- Equations export as native Word equations in DOCX: the LaTeX is converted
  locally to MathML and then to Office Math, so Word can edit the formula. If a
  formula cannot be converted, its LaTeX source is written in italics instead of
  being dropped. Inline formulas stay inside their sentence, and a numbered display
  equation keeps its `(n)` label after the equation.
- The download name comes from the project name. Burmese names are sent with
  RFC 5987 encoding and get a safe ASCII fallback.

PDF layout export is not implemented yet. Word export follows the saved document
flow; it does not reconstruct the original page layout.

### Document versions

The editor header also opens the local version history:

- A version is captured automatically when the saved document changes. Automatic
  versions are coalesced to at most one every five minutes so a long typing session
  does not fill the history with near-identical entries; an untouched new document
  is not versioned. **Save version** creates a
  checkpoint of the current document immediately.
- **Restore** replaces the document with the selected version. The version being
  replaced is stored first, even inside the coalescing window, so a restore can be
  undone from the same list. Before confirming, the dialog loads and shows the full
  stored text of that version, so the choice is not based on a short preview alone.
- **Compare** shows a read-only line diff between that version and the text
  currently on screen, including unsaved typing. Added and removed lines are
  labelled and counted, long unchanged stretches are collapsed, and nothing is
  saved or replaced by looking at the comparison.
- Before either action, unsaved editor changes are saved. If that save fails, the
  version history is left unchanged and the usual save error is shown.
- Each project keeps up to 100 versions in its own `project.db`. Version content is
  the exact stored Tiptap document, never a re-typed summary. Nothing is uploaded.
- Editor undo/redo is separate from version history; a restore starts a fresh
  editor undo stack but leaves both states available as versions.
- Comparison is line by line and text only: it does not show formatting, images or
  table structure changes, and it is not a side-by-side editor. A very large change
  reports that it is too large to compare instead of building an unbounded diff.
  Version history is a recovery aid for the same project database; it is not a
  backup.

### Project activity

Open **Project activity** from the workspace project menu to review what happened
in this project:

- The list is newest first and covers project creation, imports (including a
  cancelled import), page processing and deletion, region extraction and text
  corrections, local OCR runs, Markdown/TXT/Word exports, backups and restores.
- Each entry shows a localized event label, a local timestamp and, when relevant,
  the recorded detail: page count, export format and size, backup archive size, OCR
  languages, mean confidence, block count or error code.
- Only metadata is stored in the project's own database. Page images, document
  text and OCR output are not duplicated into the activity log, and nothing is
  uploaded.
- Filter the list by event category (project and backups, imports, pages, regions,
  text extraction, exports, or other events) and search the localized labels,
  formats, codes and metadata values. Filtering is local and read-only; clearing
  the filters restores the newest 100 entries. Unknown event types remain visible
  under **Other events** instead of disappearing.
- **Export** downloads exactly the events currently matching the filters, either as
  CSV for a spreadsheet or as JSON that keeps every metadata field. CSV values are
  quoted and escaped, spreadsheet formula prefixes are neutralised, and a UTF-8
  byte-order mark keeps Burmese text readable. The file is built in the browser
  from the loaded entries, so exporting sends nothing and the export states which
  filters were active.
- The newest 100 entries are shown. The log is a local record, not a backup, and it
  can be refreshed while the dialog is open. Unknown event types from a newer build
  still appear with their recorded summary instead of being hidden.

### Project backup and restore

Backups are local files, not a cloud service and not a GitHub upload:

- **Download backup** is available from the project card menu on the dashboard and
  from the project menu inside the workspace.
- The archive contains `manifest.json`, a transaction-consistent snapshot of
  `project.db`, every file under `source/`, `processed/`, `thumbnails/` and
  `exports/`, plus a small `backup.json` describing the archive format and the
  original project. Runtime trash and previous backup folders are excluded.
- Before the download starts, the backend re-opens the finished zip, tests its
  integrity, and confirms every asset path referenced by the database snapshot is
  present in the archive. A backup that changed mid-write is refused
  (`backup_incomplete`) rather than silently saved incomplete. Backup is also
  refused while an import job is queued or running.
- **Restore backup** on the dashboard accepts a `.zip` produced this way. The
  archive is validated before anything is registered: safe paths only (no absolute
  paths, `..`, drive letters or symlinks), a bounded total expanded size, required
  entries, project/backup format versions, SQLite integrity, required tables and a
  database migration version no newer than this build.
- A restore always creates a **new** project with a new id and a unique name
  (`<name> (restored)`, numbered on further conflicts). Existing projects are never
  replaced or modified, so a restore can be reviewed and the new copy deleted if it
  is unwanted.
- The archive size limit is `DOCUREBUILD_MAX_BACKUP_MB` (default 2048 MB, both
  upload and expanded size) and is reported to the UI through `/api/meta`.
- Archive reading, extraction and database checks run in a temporary folder under
  the local data directory and are cleaned up afterwards. Nothing leaves the device.
- **Local backup copies** keep verified archives in the data directory at
  `backups/<project_id>/<project-name>-YYYYMMDD-HHMMSS.zip`. The workspace project
  menu lists them newest first with time and size. A copy is created when you press
  **Create copy**, or automatically after opening a project if you enabled automatic
  copies in Settings and the newest copy is older than the chosen interval (6 hours to
  7 days). The copy is created after the project-open response. The number kept is set
  in Settings (presets from 3 to 20, 1–50 accepted by the backend; default 5), and the
  oldest archives are pruned after a successful new copy. The name is sanitised to a
  filesystem-safe stem (Unicode is kept), and same-second copies get a numeric suffix.
  A vault download streams the stored file without deleting it. Deleting a copy
  requires confirmation and removes only that archive. Restoring a stored copy also
  requires confirmation and creates a new project from it; the original project and
  the copy are left unchanged. Copies are excluded from new backups, so they can never
  nest archive inside archive; deleting a project moves its vault folder into the
  local trash rather than destroying it.

```text
GET    /api/projects/{project_id}/backup      # application/zip attachment
GET    /api/projects/{project_id}/backups     # ProjectBackupSummary[]
POST   /api/projects/{project_id}/backups     # create one verified copy → 201 summary
GET    /api/projects/{project_id}/backups/{filename}  # application/zip attachment
DELETE /api/projects/{project_id}/backups/{filename}  # delete one copy
POST   /api/projects/{project_id}/backups/{filename}/restore  # restore as new project
POST   /api/projects/restore                  # multipart field: file → 201 ProjectDetail
```

Restore error codes: `backup_invalid`, `backup_missing_files`,
`backup_unsafe_path`, `backup_database_invalid`, `backup_incompatible`,
`backup_too_large`, `backup_import_running`, `backup_incomplete`,
`backup_verification_failed`, `backup_restore_failed` and
`project_storage_incomplete`.

#### Optional scheduled copies

Automatic copies normally run after you open a project. To create them while the
app is closed, run the included command from your own scheduler:

```text
# Windows, from the backend folder
.venv\Scripts\python.exe -m app.scheduled_backup

# Linux or macOS, from the backend folder
.venv/bin/python -m app.scheduled_backup
```

The command is a single pass, not a daemon. It opens the local database, reads the
saved backup settings and creates at most one copy for each project whose newest
copy is older than the configured interval. It prints a summary and exits with code
1 if any project failed, so the scheduler can report the problem. It does nothing
unless **Automatic copies** is enabled in Settings, and it uses the same interval
and retention as opening a project. Set `DOCUREBUILD_DATA_DIR` for the command if
you run the app with a custom data folder. Schedule it with Windows Task Scheduler,
cron or a systemd timer, and run it while the app is closed so two processes do not
create a copy at the same moment. It makes no network request and copies nothing
outside the local data folder. Selective restore and backup encryption remain
unimplemented.

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
    exports/             reserved for server-side export output (current exports stream)
    backups/             reserved; archives live in the shared vault below
    trash/               per-project runtime trash
  backups/<project-id>/  verified backup copies (configurable retention)
  trash/                 deleted project folders and their vault copies
  tmp/                   short-lived backup archives and restore staging
```

- API keys and user documents are never committed or uploaded by the application.
- Source images and PDFs are immutable; transformations write new display assets.
  Deleting a PDF page keeps the shared original until its last page is removed.
- Asset paths stored in databases are relative and validated against traversal.
- The local API binds to loopback by default and sends no telemetry.
- The AI settings profile (provider, local base URL, text model, optional vision
  model, remote consent) is stored in `app.db`. No API keys exist in this phase.
  Project text sent for cleanup and the current page image sent for region
  proposals go only to the configured server URL; a non-loopback URL is refused
  unless remote consent is explicitly enabled. Cleanup responses are stored in the
  project database as reviewable proposals; region proposals are not stored at all.
- AI usage history lives in the application database and contains only provider,
  model, task, outcome, error code and timestamps. It never stores the selected
  document text, page images, model output or the full server response.
- The project activity log is stored in `project.db` and contains event type,
  summary, a small metadata payload (such as counts, format, byte size or OCR
  language), and a timestamp. It never stores document text, OCR output, image data
  or credentials.
- Project backups are ordinary files that you download and store yourself. They are
  built and verified locally, are never uploaded by the app, and are not synced to
  GitHub. Treat them like the project folder itself, because they contain the source
  documents and extracted text.
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

- The editor covers core rich text, manual tables, equations and footnotes, not the
  full target model (page layout is pending). Figures are supported as
  block image nodes from the region library; their caption and alt text can be
  edited, an optional figure number can be generated, and numbered figures can be
  cited from the text. A citation is a resolved `Figure n` label, not a clickable
  link or a Word cross-reference field, and only numbered figures can be cited. The
  number is a position-derived label, never written into the caption, so a caption
  that already contains a typed number keeps it and would show both; leave the
  number out of the caption when you enable it. Deleting or unnumbering a cited
  figure leaves an explicit `Figure (missing)` marker that can be fixed by hand or
  by restoring the figure.
- Equations are typed as LaTeX; OCR and AI do not transcribe or suggest them.
  Invalid LaTeX is refused before insertion, but the editor cannot verify that the
  equation matches the source page. Display equations can be numbered per equation;
  the number is a position-derived `(n)` label, and numbered display equations can be
  cited from the text. A citation is a resolved `Equation (n)` label, not a clickable
  link or a Word cross-reference field, and inline formulas cannot be numbered or
  cited. Markdown exports display equations as a `$$` block and inline formulas as
  `$...$`; plain text keeps the LaTeX source. The version preview and line diff are
  text-based, so an equation-only change is stored and restorable but may not appear
  in the comparison; the same applies to figure and equation citations, whose
  generated label is not part of the preview text.
- Footnotes are typed by hand; OCR and AI never create or transcribe one. The
  editor cannot verify that a note matches the source page, and a note is a single
  plain-text field with no rich formatting or nested notes. The number is derived
  from document order and cannot be set manually, so a typed number in the note text
  would appear twice. Markdown exports GitHub-flavoured footnote definitions, plain
  text a `Notes:` section, and Word a native footnote; PDF export is still pending.
- Table limits: inserting offers 1–10 rows and columns, and merged cells can be
  created by selecting multiple cells and choosing merge/split. There is no
  per-cell alignment beyond paragraph alignment and no column resizing. Automatic
  table structure from OCR or vision is still not produced. A table is only as
  accurate as the cell text you type.
- Word export converts equations locally through MathML, so a formula using LaTeX
  constructs that the converter does not support is written as its italic LaTeX
  source instead of a native equation. Figures are embedded from this project's
  assets and scaled to fit the page width; a figure whose asset is missing becomes a
  visible `[Figure: <caption>]` marker rather than disappearing. Word export keeps
  the document flow, not the original page geometry, and PDF layout export is not
  implemented.
- Autosave is debounced and best-effort when leaving the page. Document versions
  protect the saved document, but they live in the same project database and are
  not a backup. Use **Download backup** or **Local backups** for a complete copy;
  copies can be automatic after opening a project if you enable that setting, but
  scheduled/background backups are not implemented, and an archive is not encrypted,
  so it is only as safe as the folder you store it in. The vault keeps a configurable
  number of copies per project (five by default) and is not a substitute for an
  off-device backup.
- A backup can only be restored by the same or a newer DocuRebuild build that
  understands its format; a backup created by a newer build is rejected as
  `backup_incompatible`. Restore is whole-project only: individual pages, assets or
  versions cannot be merged from an archive into an existing project.
- The activity log shows the newest 100 events. It can be filtered, searched and
  exported from the dialog, but it cannot be pruned yet. Event labels are localized
  for known event types; an event written by a newer build falls back to its stored
  summary, which may be English.
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
- Local AI cleanup is proposal-only and limited to one OCR text block per request.
  The model can still paraphrase, translate, drop or invent text; accepting a
  proposal marks the block corrected but does not make it verified. Very long blocks
  are rejected instead of truncated. Only Ollama and OpenAI-compatible servers that
  the user configures are supported; loopback is the default, and any other host
  requires explicit remote consent before a request. Cleanup attempts are counted
  against an optional rolling 24-hour limit; connection tests are not. Cloud free
  tiers, paid providers, API keys, vision tasks, cost estimation, rate-limit handling
  and provider fallbacks are not implemented yet. A local server's "free" status
  depends on the user's own installation and hardware, so nothing is advertised as
  universally free.
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
- KaTeX and its fonts are bundled for offline equation rendering under the MIT
  licence. The stylesheet is served from the app bundle; no request is made to a
  math service.
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
| 6. AI integration and free usage first | In progress: local AI providers, remote-consent boundary, request limits, usage history, reviewable persisted OCR text cleanup and optional vision region proposals done; free-tier/paid adapters and cost controls pending |
| 7. Table, figure and equation reconstruction | In progress: manual editable tables with row/column/header tools, merge/split, editable figure captions with optional figure numbering and cross-references, and user-typed display and inline equations with local preview, optional equation numbering and cross-references, plus faithful table/equation export to Markdown, TXT and Word; automatic table/equation extraction pending |
| 8. Document editor and export | In progress: rich-text editor plus manual tables, figures, display and inline equations, footnotes and local Markdown, TXT and Word export; PDF page layout pending |
| 9. History, backup and recovery | In progress: local document versions with manual checkpoints, restore and read-only comparison, a filterable and exportable project activity log covering imports, processing, OCR, exports and backups, verified project backup download, additive restore from upload or a stored vault copy, a local backup vault with opt-in automatic copies on project open and configurable retention, and an optional one-pass scheduled-backup command for external schedulers; selective restore and encryption pending |
| 10. Desktop, PWA and mobile distribution | Planned |
| 11. Final QA and production release | Planned |

Detailed criteria and design decisions are in [`docs/roadmap.md`](docs/roadmap.md)
and [`docs/architecture.md`](docs/architecture.md).

---

## Source repository

The authoritative remote is configured by the project owner. Do not force-push,
rewrite history, or upload user data. Repository integration and backup rules are
documented in [`AGENTS.md`](AGENTS.md).
