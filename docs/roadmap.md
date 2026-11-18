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
| 4. Local OCR and layout detection | **In progress** | Tesseract adapter, review UI, layout hints, overlay, reviewable word-box table proposals (single block and page-level cross-block candidates), deterministic figure suggestions from embedded PDF images and vector drawings, and a local CER/WER benchmark harness done; measured real-document accuracy pending |
| 5. Element extraction | **In progress** | Manual region crop, local region text extraction, OCR-layout, embedded-PDF-image, vector-drawing and raster-page ink region suggestions with a named source in the extraction dialog, library, verification and figure/text insertion, reviewed equation crops inserted as real equations, and on-demand AI transcription of one equation crop into reviewable LaTeX done; structured table reconstruction pending |
| 6. AI integration and free usage first | **In progress** | Local Ollama/OpenAI-compatible adapter, model discovery, settings with independent text and vision task profiles, encrypted per-task API keys, remote-consent boundary, user-declared local/free/paid cost classes with per-action approval, request limits, usage-history browser, bulk AI proposal review, reviewable persisted OCR text cleanup, optional vision region proposals and optional equation-crop transcription done; verified pricing/quotas and spending caps pending |
| 7. Table, figure and equation reconstruction | **In progress** | Manual editable tables with empty-cell insertion, row/column/header tools and merge/split, reviewable automatic table proposals from OCR word boxes including page-level grouping of row blocks, per-cell alignment and pre-insert cell correction, merged cells from a PDF's drawn rules, editable figure captions with optional generated figure numbers and prose cross-references, user-typed display and inline equations with local KaTeX preview, optional equation numbering and prose cross-references, inserting a reviewed equation crop as a real numbered equation, optional vision-model transcription of one saved equation crop into reviewable LaTeX, and faithful Markdown/TXT/Word/PDF export; vision tables, merged-cell detection for text-only tables and automatic page-wide equation recognition pending |
| 8. Document editor and export | **Complete** | Core editor plus manual tables, figures, display and inline equations, multi-line Word equations, footnotes, per-project page headers/footers, and local Markdown, TXT, Word and A4/Letter PDF export with configurable margins, native Word equations/footnotes, embedded figures, links and notes |
| 9. History, backup and recovery | **Complete** | Document versions with manual checkpoints, restore and read-only comparison, a filterable and exportable local project activity log for imports, processing, OCR, exports and backups, verified project backup download (plain or password-encrypted), additive (new-project) restore from an upload or a stored vault copy, page-scoped selective restore, page-image and region-crop repair and reversible document-version restore into the current project, a local backup vault with opt-in automatic copies on project open and configurable retention, and an optional one-pass scheduled-backup command for external schedulers |
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
- Reviewable table proposals from stored OCR word boxes: a block labelled as a
  table is clustered into rows and whitespace column bands, and the resulting cells
  carry their OCR text, confidence and uncertainty flags. A page-level detector also
  groups vertically contiguous paragraph blocks when the merged visual rows still
  pass the same deterministic layout classifier, which makes PDF tables stored one
  block per row reviewable. The proposal is refused for stale runs, capped at 20
  candidates per page and 60 rows / 20 columns / 600 cells per candidate, and never
  inserted without explicit review.
- Local accuracy benchmark (`python -m app.ocr_benchmark`): CER and WER against
  checked reference transcripts, either by running the local Tesseract adapter on
  a page image or by scoring a stored transcript. Results are grouped by category
  and weighted by reference length; a case that cannot be scored is reported and
  excluded instead of aborting the run. Nothing is uploaded.
- Backend tests for persistence, correction, verification, stale detection,
  missing language data and unavailable engines, deterministic classification and
  TSV layout wiring; frontend tests for coordinate scaling/clamping and i18n
  parity.

**Remaining before completion**

- Figure (image region) detection inside the OCR layout. The classifier never
  guesses a figure; Phase 5 approximates the band above a figure-like caption, but
  this phase does not mark figures itself.
- Nested tables and vision-based table reading. Cross-block grouping covers
  vertically contiguous row blocks, and a PDF page's drawn rules provide exact
  merged-cell spans, but a word-box candidate remains a plain grid, a nested table
  is not separated from its parent, and a hand-corrected block is a barrier instead
  of being bridged. Equation transcription is still pending.
- OCR accuracy benchmarks (CER/WER) for English, Burmese and mixed pages using
  fixtures from real documents. The local harness exists and is tested, but no
  fixtures are shipped and no accuracy figures are claimed yet.
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
  Manual transcription and correction work without OCR. An equation region's
  reviewed text can also be inserted as a real display equation: the dialog shows
  the saved crop beside a local KaTeX render, refuses empty or unrenderable source
  and writes only the LaTeX the user confirmed, optionally numbered, with the same
  provenance note. When a vision model is configured, the dialog can also ask it to
  transcribe the saved crop; the reply only prefills the review field, is shown as
  unverified model output and is never inserted automatically.
- Reviewable region suggestions derived from the latest local OCR layout. Table
  and equation blocks are clustered into suggestions, and a figure band is
  suggested above figure-like captions. On imported PDF pages, raster images
  embedded in the page are proposed as uncaptioned figures from their actual
  placement; full-page backgrounds and tiny images are skipped, and a caption
  covering the same artwork is merged into the image proposal. Vector artwork the
  PDF draws itself (charts, diagrams) is proposed the same way: a filled shape or a
  curve is artwork, while the axis-aligned rules of a table, an underline or a page
  frame are not. A photographed page has no PDF layer, so the current render is
  analysed locally: ink outside every OCR text block that forms a large connected
  cluster becomes a low-confidence figure, with nearby parts joined and page frames,
  thin rules, dark pages and page-sized areas skipped. A caption covering that ink
  is merged into the proposal. Suggestions are read-only, never saved automatically,
  and prefill the normal extraction dialog. Expected states such as no OCR run,
  stale, failed or missing geometry are reported in the response.
- `element_extraction` and `region_proposals` capability flags, plus English and
  Burmese interface strings.

**Remaining**

- Drawings the PDF stores as an opaque page or form rather than readable paths;
  these currently require manual selection.
- Structured table cells, which belong to Phase 7.

## Phase 6 — AI integration and free usage first (in progress)

**Delivered**

- Provider catalog with two local adapter kinds: `ollama` (default
  `http://127.0.0.1:11434`) and `openai_compatible` (default
  `http://127.0.0.1:1234/v1`). No cloud account, paid subscription or automatic paid
  call is involved.
- Settings → Local AI with an explicit, saved text profile (provider, base URL,
  model, remote consent). Empty model keeps AI actions disabled. URL drafts are
  validated and only saved on request, and the provider default is shown as a
  placeholder.
- Optional per-task provider API keys for a server that requires bearer
  authentication. Each profile stores one key encrypted with Fernet in
  `<data_dir>/secrets/ai_keys.enc`; the master key is generated locally. The key is
  write-only: `PATCH /api/settings` accepts `api_key` or `clear_api_key`, the API
  returns only `has_api_key`, and the value never enters `app.db`, the usage ledger,
  logs or exports. A stored key is sent only when the request keeps the saved
  provider and URL, so a per-request server override never receives it. A connection
  test can reuse the saved key or test an unsaved one.
- Loopback-only network boundary by default. `localhost`, `*.localhost` and loopback
  IPs need no approval; any other host or IP returns `403 ai_remote_not_allowed` for
  probes, cleanups and per-request overrides until the user enables remote endpoint
  consent. Consent is stored with the profile and is never inferred from the URL.
- User-triggered connection test and model discovery through Ollama `/api/tags` and
  `/api/version`, or OpenAI-compatible `/models`. Discovered models populate a
  manual-entry datalist; a typed model name always remains possible.
- Reviewable OCR text cleanup. `POST .../ocr/blocks/{block_id}/ai-suggestions` sends
  only that block's text to the configured server and stores an unverified
  `ai_suggestion` with original text, proposed text, provider, model and base URL.
- `GET .../pages/{page_id}/ai-suggestions?status=pending` exposes stored proposals.
  The OCR dialog reloads pending proposals when it opens, so closing and reopening
  the dialog no longer hides an unreviewed proposal. Proposals tied to an older OCR
  run stay in the database but are not shown for the current run.
- Per-block proposal history in the OCR dialog. Accepted and rejected proposals keep
  their original text, proposed text, provider, model and decision time, so the AI's
  influence stays auditable after later manual corrections. History is read-only and
  does not change OCR text. The page list endpoint accepts `status` and `limit`
  (default 200, maximum 500).
- Project-wide review queue for pending cleanup proposals.
  `GET /api/projects/{project_id}/ai-suggestions` returns proposals across every page
  with `page_number`, newest first, and accepts the same `status`/`limit` filters.
  The source toolbar opens a "Review AI proposals" dialog that shows the current and
  proposed text side by side, with page, provider, model and time, and accept/reject
  actions that reuse the existing decision endpoint. Accepting still revalidates the
  block, so a proposal made stale by a later edit is refused rather than applied.
- Local AI usage ledger in the application database. Every cleanup request that
  actually contacts a provider is recorded with provider, model, task, outcome,
  error code, project/page/block ids and a timestamp. Document text and model output
  are never stored in this ledger. Validation failures and connection tests are not
  counted.
- Configurable rolling 24-hour request limit (`0` = unlimited, maximum 10,000),
  enforced before the provider is contacted with `429 ai_request_limit_reached`.
  Settings shows requests used in the last 24 hours and the five most recent
  metadata-only entries through `GET /api/ai/usage`. **View full history** opens a
  read-only ledger browser with 25-row pages and outcome/task filters through
  `GET /api/ai/usage/history`; rows name their project and survive project deletion
  with no name, so the ledger can be audited across projects and pages.
- Accept/reject decisions through `PATCH .../ai-suggestions/{id}`. Accepting writes
  the proposal through the normal OCR correction path, marks the block corrected
  (not verified) and refuses when the block text changed after the proposal was
  created. Rejecting keeps the OCR text and still works after the page changes.
- Optional vision region proposals. `app_settings.ai.vision` is a separate task
  profile with its own provider, base URL, model and remote-consent decision, so
  image analysis can run on a different local server or device than text cleanup.
  An empty model keeps image AI disabled and returns `409 ai_vision_not_configured`
  before any request; settings stored by an older build are migrated from the
  single `ai.vision_model` value on read. `POST .../pages/{page_id}/ai-region-proposals`
  sends only the current page image (resized locally to a bounded JPEG) to the
  configured Ollama or OpenAI-compatible vision server and asks for normalized
  figure, table and equation rectangles. The backend validates and clamps the
  coordinates, applies the same padding and dedupe rules as heuristic proposals,
  drops regions that already have an extracted element, and returns low-confidence
  proposals. Nothing is persisted: the source viewer overlays them for review, and
  choosing one only prefills the normal extraction dialog. Per-request
  provider/base URL/model overrides follow the same remote-consent rules, and each
  attempt is recorded in the usage ledger with task `region_proposals`.
- On-demand equation transcription. The equation-region formula dialog can send only
  that saved crop to the saved vision profile and fills its LaTeX field with
  the reply. Non-equation regions and missing crops are refused before any request;
  code fences, math delimiters and wrapping quotes are stripped but the expression is
  never rewritten, and an empty reply is reported instead of guessed at. The reply is
  not persisted as a suggestion and is never inserted automatically; the dialog names
  the proposing model, marks it unverified and keeps the manual typing path available
  without a vision model. Each attempt is recorded with task `equation_transcription`.
- Per-block review UI showing the current OCR text beside the proposal, provider and
  model badges, explicit accept/reject actions, a stale-proposal warning and a link
  to Settings when no model is configured. The source viewer shows the vision
  proposal count, provider/model and a review warning, and clears the overlay when
  the page changes or rotates.
- Multi-select batch review in the project-wide queue. Checkboxes and a select-all
  control choose pending proposals, and **Accept selected** / **Reject selected**
  require a confirmation that names the count. The backend decides each proposal
  separately with the same stale/run checks and reports per-item failures, so a stale
  proposal is skipped while the rest still change; the list refreshes afterwards and
  skipped proposals stay pending.
- User-declared cost classes with per-action paid approval. Each profile is stored as
  `local`, `free` or `paid`. Loopback inference is always local and a remote URL can
  never stay marked local: saving one turns a `local` or unspecified class into paid,
  and a profile saved by an older build is classified on read (loopback local,
  anything else paid). Cleanup, region proposals and equation transcription on a paid
  profile require `confirm_paid: true` and otherwise return
  `409 ai_paid_confirmation_required` before the usage limit is checked and before any
  network request, so a refused action costs nothing and leaves the ledger untouched.
  A declared free tier is not asked again; connection tests never need approval. The
  dialog names the model and server URL, states that DocuRebuild does not estimate
  provider pricing, and sends nothing until the user confirms that one action.
- SSRF guards for the configured URL: `http`/`https` only, no embedded credentials,
  and the well-known cloud metadata addresses are rejected. Requests use short
  connect/probe timeouts, bounded response size and no automatic paid fallback.
- Provider error clarity without automatic retry. An HTTP 429 becomes
  `ai_rate_limited`, 401/403 become `ai_auth_failed`, and any other status stays
  `ai_http_error`. An integer `Retry-After` header is capped at 24 hours and shown as
  an advisory wait on the connection test; HTTP-date values are ignored. A failed
  generation is recorded in the usage ledger with the same code, still returns `502`,
  and is never re-sent, slept on or rerouted to another provider.
- Capability reporting: `ai` is `true` because the adapter and review workflow
  exist, while Settings still requires a working local server and model before any
  action can run. Backend tests use a loopback stub server and cover discovery,
  timeouts, unreachable servers, invalid responses, remote consent, cost-class
  inference and normalization, paid refusal without network access, free-tier
  passthrough, provider rate-limit/auth classification and Retry-After parsing,
  usage recording, rolling-limit enforcement, stale runs, stale text, rejection and
  validation. Frontend tests cover the cost-class settings, the paid confirmation
  dialog, free-tier passthrough, the rate-limit hint, URL escalation and i18n key
  parity.

**Remaining**

- Table structure assistance on top of the region proposals, with the same proposal
  and verification guarantees.
- Text/reasoning profile separation beyond OCR cleanup, plus task routing.
- Optional free-tier and paid providers behind the same adapter, with dynamic
  model metadata, verified pricing/quotas and clearly marked costs. Remote profiles
  can be classified today, but the app neither verifies a provider's current pricing
  nor detects quota exhaustion beyond the provider's own error reply.
- Spending limits, cost estimation, proactive quota tracking and provider
  fallbacks. A provider 429 or 401/403 is classified and explained today, but the app
  does not track quota over time, retry or switch providers, and a monetary cap needs
  verified pricing data that it does not collect yet.
- Account sign-in, server-side key validation against a provider account and
  per-provider spending caps. The encrypted key store and write-only API are in
  place, but a key is not verified against billing or quota.
- Batch actions currently cover OCR cleanup proposals in the project-wide queue;
  other future proposal types use their own review dialogs.

**Current limitation** — only an Ollama or OpenAI-compatible server that the user
configures is supported; loopback is the default and a non-loopback endpoint requires
explicit remote consent. Model quality, availability, memory use and licence terms
come from the user's installation; "free" is never assumed to be permanent, and a
free tier declared by the user is not verified against the provider's current terms.
The cost class is a local gate, not a billing system: the app never estimates a price,
never knows what the provider actually charges and cannot stop a provider from billing
outside the application. A saved API key is protected by local file permissions and
encryption, not by a remote account: anyone who can read the data folder can use it,
and the app does not verify its quota or billing status. AI text
can be wrong, so accepting a proposal does not mark it verified and manual review
remains the source of truth. Vision proposals are rectangles with no extracted
content and low confidence by design; their coordinates may still be imprecise, and
the user must review every region before extracting it.

## Phase 7 — Tables, figures and equations (in progress)

**Delivered**

- Manual editable tables in the document editor: insert an empty table with 1–10
  rows/columns and an optional header row, then add or delete rows and columns,
  toggle the header, or delete the table. Every cell is typed by the user; no
  content is generated from a source image.
- Cell merge and split from the table menu. Selecting multiple cells and choosing
  merge produces a single cell with stored `colspan`/`rowspan` without dropping the
  absorbed text; split restores the cells when the cursor is inside a merged cell.
  Both actions stay disabled outside a suitable table selection.
- Reviewable automatic table proposals from OCR word boxes. The OCR dialog can turn
  a block labelled as a table into a cell grid with per-cell text, confidence and
  uncertainty flags, or detect every table on the page and group vertically
  contiguous row blocks that still classify as a table. Either way the grid is
  inserted as a normal editable table only after the user confirms it (and
  acknowledges any uncertain or unscored cell). Nothing is generated for paragraphs
  outside an accepted group, corrected blocks or stale runs, and each candidate is
  capped at 60 rows / 20 columns / 600 cells.
- Merged-cell table proposals from a PDF's own vector rules. The page endpoint
  extracts axis-aligned strokes and thin filled or stroked rectangles from the
  immutable PDF, groups them into drawn grids, and treats a missing internal
  separator as a `colspan`/`rowspan`. The review grid renders the merge, and
  insertion writes the same spans into an ordinary Tiptap table. A rotated page, a
  geometry edit or a stale run falls back to the word-box grid, and a closed,
  mostly filled grid is required so a chart's axis frame is not offered. A vector
  grid replaces an OCR candidate that lies at least 85% inside it.
- Side-by-side source comparison in the table review dialog. The backend reports
  the proposal's pixel box and the page dimensions, and the dialog crops the page
  image to that box next to the grid. The crop can be hidden, and it is read-only:
  comparing or hiding it never changes the proposal or the document.
- Manual cell correction before insertion. The review grid can switch into editing
  mode, where every cell becomes a field with its own accessible label. Edited
  cells are highlighted and counted, and the edits can be reset. The inserted table
  uses the corrected text; the proposal and its confidence flags stay unchanged,
  so a manual fix is never presented as extracted text. Edits are discarded when
  the dialog is reopened or another proposal is opened.
- Per-cell alignment inferred from the stored word boxes. Text that leaves clear
  room inside its column band becomes a left, centred or right proposal, shown in
  the review grid and inserted as paragraph alignment inside the cell. A cell that
  fills its band, or whose lines disagree, keeps the default instead of claiming
  an alignment that cannot be observed. Word and PDF export keep the alignment;
  Markdown and plain text cannot express it.
- Tables are ordinary Tiptap nodes, so saving, version history and project backups
  need no special handling. Column resizing is disabled deliberately because pixel
  widths are screen-dependent and cannot survive Markdown.
- Markdown export renders GFM tables (escaped `|`, `<br>` for multiple blocks, a
  blank structural header when none exists) and falls back to HTML for merged
  cells so spans are not lost. Plain-text export keeps every cell; Word and PDF write
  native tables and reproduce merged cells.
- Figure captions and alt text can be corrected after insertion. Selecting the whole
  figure enables the caption tool; the image, its stored source note, its size and
  its position stay unchanged, and the corrected caption is what Markdown and
  plain-text export write. A collapsed cursor next to a figure never edits it.
- Optional figure numbering: the caption dialog stores a `numbered` flag, the editor
  shows `Figure n.` from a CSS counter in document order, and every export adds the
  same number after the marker (`[Figure 1: caption]`) or before the caption in Word
  (`Figure 1. caption`). The caption text is never rewritten, so no number is
  injected into the stored document. Cross-references to a figure are still pending.
- Display and inline equations typed as LaTeX: a toolbar dialog previews the
  equation locally with KaTeX, refuses empty or invalid source, and inserts or
  updates a `blockMath` or `inlineMath` node that stores only the source. Inline
  math stays inside its paragraph, and the extension's automatic input rule is
  disabled so typed prose is never converted silently. Rendering is offline and
  bundled; Markdown export writes a `$$` block or a `$...$` formula, plain text
  keeps the LaTeX and PDF shows the exact LaTeX source. An equation-only change is
  stored in the document and versions, though the text-based version diff may not
  display it.
- Optional equation numbering for display equations: a checkbox in the dialog stores
  a `numbered` flag on the node, the editor shows `(n)` from a CSS counter in document
  order, and Markdown/TXT export appends the same label after the equation; Word
  export adds the same label next to the native equation and PDF after the LaTeX
  source. Numbers are never written into the LaTeX source, and inline formulas cannot
  be numbered.
- Equation regions can be inserted as real equations. An extracted equation region
  whose text the user reviewed can be opened in a formula dialog that shows the saved
  crop beside a local KaTeX render, lets the user correct the LaTeX, optionally
  numbers it and writes only the confirmed source (plus an optional provenance note).
  Empty or unrenderable source is refused, and the crop and OCR text stay unchanged.
- A saved equation crop can also be transcribed on request when a vision profile is
  configured. The dialog sends only the crop, fills the LaTeX field with the reply,
  shows the model and an unverified warning, and still requires the local KaTeX
  preview to pass before insertion. The provenance note credits the model only while
  the field matches its reply; an edited formula falls back to the manual note.
- Figure cross-references: a numbered figure gets a stable id, and the toolbar can
  insert an inline citation that stores only that id. The editor resolves the current
  `Figure n` label from document order, so moving or renumbering the figure updates
  every citation. A deleted or unnumbered target renders as `Figure (missing)` and
  exports the same marker instead of silently becoming another number.
- Equation cross-references: a numbered display equation also gets a stable id, and
  the toolbar can insert a citation that stores only that id. The live label
  `Equation (n)` is resolved from document order, so moving or renumbering the
  equation updates every citation; a deleted, unnumbered or inline target exports as
  `Equation (missing)`. Figure and equation citations share the same reference node
  implementation.
- Inline images in running text: an extracted crop can enter the document as a
  paragraph-level atom instead of a block figure, either when a new region is saved
  and inserted or from a saved region’s “Insert inline” action. The node stores only
  the project asset URL and alt text, so no caption, note or number is invented; the
  picture stays in its sentence, is capped in size and can be selected and deleted
  without touching the surrounding text. Markdown and plain text write
  `\[Image: alt\]`/`[Image: alt]` rather than an unusable local path, while Word and
  PDF embed the actual asset inline.

**Pending**

- Automatic table extraction beyond deterministic word-box grouping and drawn PDF
  rules: vision-based tables and nested tables, always as a reviewable proposal that
  is never inserted without approval. Cross-block grouping and merged-cell spans
  from a PDF's vector rules are delivered.
- Optional structured figure reconstruction with approval. Figure numbering, prose
  cross-references and inline images are delivered.
- Automatic equation recognition from OCR or vision across a page as a reviewable
  proposal. Word export now converts typed equations to native OMML, a reviewed
  equation region can be inserted as a real equation, and one saved crop can be
  transcribed on request; page-wide detection and automatic acceptance remain
  pending.
- Uncertain table cells are flagged in the proposal and must be acknowledged before
  insertion, and an empty source cell is never filled in. Equation symbols still
  have no automatic recognition, so they are never invented.

## Phase 8 — Document editor and export (complete)

**Delivered**

- Headings, paragraphs, lists, blockquotes, code, alignment, inline marks,
  undo/redo and debounced autosave.
- Find and replace in the editor toolbar (also `Ctrl/Cmd+F`). Matching works on
  document text positions, can span inline marks, and never crosses a paragraph or
  hard-break boundary. Match case, previous/next, replace and replace-all are
  available, and replacements keep the formatting of the matched text.
  Editor undo/redo still covers the change, and find state is not part of the
  document.
- Link editing (`Ctrl/Cmd+K`). A selected range can be linked to an `https://`,
  `http://` or `mailto:` target; a bare domain is upgraded to `https://`, and
  `javascript:`, `data:`, `file:`, protocol-relative and whitespace-containing
  targets are rejected. The same policy applies to auto-detected and pasted links.
  Existing links can be edited or removed, and links are included in Markdown
  export and become real hyperlinks in Word export (plain text keeps their text).
- Manual tables in the toolbar: an empty table (1–10 rows/columns, optional header),
  then contextual row/column insertion, deletion, header toggle and table delete.
  Cells are typed by hand and are part of the saved document.
- Local Markdown, plain-text, Word and PDF export from the editor header. Every format
  is rendered by the backend from the saved Tiptap document, so export works without
  an internet connection, AI provider or extra dependency beyond the pinned local
  libraries.
- `GET /api/projects/{project_id}/document/export?format=markdown|txt|docx|pdf` returns
  an attachment with a project-based filename. Unknown formats are rejected
  with `422`.
- The frontend flushes unsaved editor state before downloading and refuses the
  download when that save fails, so the file always matches the visible document.
  The file is fetched as a blob, so a backend export error is shown as a message.
- Markdown escaping keeps extracted text literal (`#`, `-`, `+`, `>`, `1.`,
  `\`, `` ` ``, `*`, `_`, `[`, `]`, `<`, `>`), code spans stay verbatim, and links
  are limited to `http`, `https` and `mailto`. Plain-text output has no Markdown
  syntax.
- Figures export as an explicit `[Figure: <caption>]` marker with their source
  note in Markdown and plain text; a numbered figure uses `[Figure n: <caption>]`.
  Local asset URLs are never written into any file. Word export embeds the project
  image itself, keeps the caption and source note, prefixes a numbered caption with
  `Figure n.`, and falls back to the same marker when an asset is missing.
- Figure citations export as their resolved `Figure n` label at the position of the
  citation; a missing or unnumbered target becomes `Figure (missing)`. The stored
  node keeps only the target id, so a renumbered figure updates every format.
- Equation citations export as `Equation (n)` at the position of the citation; a
  missing, unnumbered or inline target becomes `Equation (missing)`. The LaTeX source
  is never rewritten to carry the citation.
- Tables export as GFM Markdown with escaped pipes and `<br>` inside multi-block
  cells; a missing header gets a structural blank header, and merged cells use an
  HTML table so no cell content is lost. Plain-text export keeps every cell. Word
  export writes a native `Table Grid` table and reproduces row/column spans.
- Equations export as source in Markdown/plain text: a `blockMath` node becomes a
  fenced `$$` block and an `inlineMath` node a `$...$` formula, while plain text
  keeps the exact LaTeX. Backslashes are not escaped as prose. Word export converts
  each equation through MathML to Office Math, so it stays editable in Word, and
  numbered equations keep their `(n)` label.
- Multi-line equation environments convert to native Word equations. `aligned`,
  `align`, `alignat`, `flalign`, `gather`, `multline`, `split` and `eqnarray`
  (starred or not, with an optional `\displaystyle` prefix) are split into rows and
  alignment cells by a brace- and environment-aware scanner. A one-column array
  becomes a Word equation array; alignment points become right/left matrix columns,
  so rows and every symbol are kept. Automatic `(1)`, `(2)` labels that the MathML
  converter would invent for an unstarred `align` are never written, because a
  project equation keeps its own single block-level number. A cell that cannot be
  converted falls back to the exact LaTeX source instead of a partial equation.
- Footnotes: the toolbar dialog inserts an inline atom that stores its own text and a
  stable id; the number is generated from document order, so inserting or deleting a
  note renumbers the rest without touching stored text. The node view shows a
  localized accessible label and the note text as a tooltip. Export keeps the text:
  Markdown writes `[^n]` markers plus `[^n]: text` definitions, plain text appends a
  `Notes:` section, and Word writes a native footnotes part. The stored plain text
  includes the notes, so version previews and diffs see footnote edits.
- `export` in `/api/meta`, English and Burmese labels, backend serializer and
  endpoint tests.
- PDF export: A4 or US Letter pages with a page-number footer, embedded project
  figures (block and inline), clickable links, native tables with merged cells, aligned
  headings and paragraphs, and a numbered **Notes** list for footnotes. **Settings → Export**
  chooses the page size and a narrow/normal/wide margin (36/50/72 pt); both are
  validated presets stored in app settings and applied to later downloads. The output
  is deterministic and carries only the project title plus `DocuRebuild` as
  creator/producer. Equations show their exact LaTeX source because no offline LaTeX
  typesetter is bundled. Burmese text uses an embedded Unicode Myanmar font found
  through `DOCUREBUILD_PDF_FONT`, known font names or a font-directory scan; if none
  is available the export fails with `pdf_font_missing` rather than writing
  replacement characters.
- Per-project page headers and footers for Word and PDF. The editor's export menu
  opens a dialog with single-line header and footer text, optional `{page}`,
  `{pages}` and `{title}` placeholders, and a page-number choice. The values are
  stored in the project's own database, survive backup and restore, and never change
  the document text. Word writes real `PAGE`/`NUMPAGES` fields in the header/footer
  parts; PDF draws the same text inside the margins, keeps a footer counter on the
  right, shortens over-long text instead of overflowing, and includes the header and
  footer in the Myanmar font check. Markdown and plain text are not paginated and
  ignore the layout. Saving the layout is recorded as a metadata-only activity event.

**Current limitation** — export covers headings, paragraphs, lists, blockquotes,
code blocks, rules, inline marks, tables, figures (block and inline), equations and
footnotes. Page layout is not part of the editor model yet. Word and PDF export follow
the document flow rather than the source page geometry, and a formula the local Word
converter cannot handle is written as its LaTeX source. PDF export keeps every
equation as LaTeX source by design.

**Pending** - source page layout, remaining OMML edge cases (for example
colour and accent semantics) and a bundled offline LaTeX typesetter.

## Phase 9 — History, backup and recovery (complete)

**Delivered**

- Document revisions stored in each project database. A save snapshots the state it
  replaces; automatic snapshots are coalesced to one per five minutes, and manual
  checkpoints can be created at any time. Identical consecutive states are never
  duplicated and the newest 100 versions are retained.
- `GET /api/projects/{id}/document/revisions` returns newest-first summaries
  (`preview`, `character_count`, `source`, `created_at`);
  `POST` creates a manual checkpoint; `GET .../{revision_id}` returns the exact
  stored content; `POST .../{revision_id}/restore` makes it the live document and
  always snapshots the replaced state first.
- The editor's version dialog lists versions with source and time, requires an
  explicit confirmation before restoring, loads the full stored text of the
  selected version for review, and flushes unsaved editor state first. If that save
  fails, nothing is restored.
- Read-only line comparison between a version and the text on screen, including
  unsaved changes. Added and removed lines are labelled and counted, long unchanged
  runs collapse around two context lines, and very large changes are refused rather
  than building an unbounded diff. Nothing is saved by comparing.
- English and Burmese strings, backend tests for coalescing, pruning, exact restore,
  validation and not-found handling, unit tests for the diff, and component tests for
  the confirmation, save-guard and comparison flows.
- Project backup download: a verified zip of `manifest.json`, a transaction-consistent
  `project.db` snapshot, `source/`, `processed/`, `thumbnails/`, `exports/` and a
  `backup.json` header. Nested backup/trash folders are excluded. Integrity, required
  entries and every database asset reference are checked before the download starts;
  an import in progress blocks backup so the snapshot cannot race the import worker.
- Project restore: validates archive paths, symlinks, expanded size, format versions,
  SQLite integrity, required tables and migration version, then registers the archive
  as a **new** project with a new id and a unique `(restored)` name. Existing projects
  are never overwritten, so the operation is additive and reversible.
- Dashboard and workspace download entries, a download dialog that chooses plain
  `.zip` or a password-protected `.drbz`, a restore dialog with client-side
  `.zip`/`.drbz` and `max_backup_mb` checks and an optional password field,
  English/Burmese strings and error codes, plus backend round-trip, conflict-name,
  unsafe-path and invalid-archive tests and component tests for the download name,
  download dialog and restore dialog.
- Project activity log: `GET /api/projects/{id}/history?limit=50` returns newest-first
  local events with metadata-only payloads. Imports, page processing, region
  extraction, OCR start/completion/failure, exports, backups and restores record
  events; the workspace dialog labels known types in English and Burmese, formats
  counts, sizes and confidence values, and falls back to the stored summary for an
  unknown future event type.
- Client-side activity filtering and search: one category selector (project and
  backups, imports, pages, regions, text extraction, exports, other) plus a search
  box that matches localized labels, detail values, event types, summaries and scalar
  metadata. Unknown event types stay visible under **Other events**, the footer shows
  how many events match, and filters reset on close. No request or stored state is
  added.
- Activity export of the events currently matching the filters: CSV with RFC 4180
  quoting, a stable header, CRLF rows, spreadsheet-formula neutralisation and a UTF-8
  byte-order mark, or a versioned JSON archive that keeps the raw metadata and the
  active filters. Export is built in the browser, names the file from the project name
  and local date, and sends nothing.
- Backend tests for ordering, per-project scoping, limit validation, missing projects,
  import/export payloads and the absence of document text in the log, plus unit tests
  for the filter mapping/search and CSV/JSON building and component tests for labels,
  details, empty, error, unknown-event, filtered, no-match and export states.
- Local backup vault: `GET /api/projects/{id}/backups` lists verified copies newest
  first, `POST` creates one from the same validated archive builder,
  `GET .../backups/{filename}` streams a stored copy,
  `DELETE .../backups/{filename}` removes one copy after confirmation, and
  `POST .../backups/{filename}/restore` restores a stored copy as a new project.
  Copies live in
  `data_dir/backups/<project_id>/`, are created on request, and older copies are
  pruned after a successful write. Retention is configurable (`backups.keep_copies`,
  default 5, backend range 1–50; the UI offers 3, 5, 10 and 20) and applies to manual
  and automatic copies. Same-second collisions get a numeric suffix, unsafe filenames
  are rejected, and a vault download never deletes the copy. Deleting a project moves
  its vault folder to the local trash as `*-vault`, preserving the archives. The
  workspace project menu opens a dialog that lists time and size, creates a copy,
  downloads, restores or deletes one with confirmation, and shows empty, loading and
  error states. Creating a copy is recorded in the activity log.
- Opt-in automatic copies: a new Settings → Backups section controls
  `backups.auto_on_open` (default off), `interval_hours` (6 hours to 7 days in the UI,
  1–720 accepted) and `keep_copies`. When enabled, `POST /projects/{id}/open`
  schedules a background copy only if the newest vault copy is older than the
  interval. The task re-reads settings in its own session, a lock prevents duplicate
  snapshots from simultaneous opens, and a failed copy is logged without blocking the
  open.
- Optional scheduled copies while the app is closed:
  `python -m app.scheduled_backup` is a one-pass command for Windows Task Scheduler,
  cron or a systemd timer. It respects the same opt-in setting, interval and
  retention, creates at most one due copy per project, continues after a per-project
  failure, prints a summary and exits with code 1 when any project failed. It is not
  a daemon and makes no network request.
- Optional password-protected downloads: the download dialog can wrap the verified
  zip in a `.drbz` container (`services/backup_crypto.py`) using scrypt key
  derivation and chunked AES-256-GCM with a header key-check record. The password
  is sent in the request body, never stored or logged, and restore detects the
  container by content, asks for the password and reports wrong-password versus
  damage separately. Vault and automatic copies stay plaintext by design.
- Selective restore: the workspace project menu can inspect a local copy or an
  uploaded `.zip`/`.drbz` and list both its pages and its document versions. The
  archive is extracted once into a short-lived `tmp/select-<token>/` folder
  (one-hour TTL, bound to the inspecting project).
  - **Pages** are appended to the current project. Chosen pages get new ids and
    numbers after the last page, and their assets, OCR runs, blocks, AI proposals
    and extracted regions are copied with remapped references. The document and
    existing pages are never touched.
  - **Document** replaces the live document with the backup's current text or any
    stored version (`revision_id: null` means the current document). The replaced
    state is force-snapshotted as a local revision first, so the restore can be
    undone from the version history; pages and assets are not touched.
  - **Page image** repairs a page whose original, display or thumbnail file is
    missing. Inspection annotates each backup page with whether it is still in the
    project and which slots are missing and restorable. Only missing slots are
    copied; a present image is never overwritten. When the asset row still exists the
    file is rewritten under the same id, so OCR `source_asset_id` and element
    references stay valid; otherwise a new asset id is used. Backup checksums are
    verified before copying, and the page, its text and its elements are kept.
  - **Region image** repairs an extracted figure, table or equation whose crop file
    is missing. Inspection lists only regions that still exist in the project and
    whose crop is damaged, with whether the backup can supply the file; the list is
    capped and reports when more remain. Only a missing crop is copied, a present one
    is never overwritten, and the region, its rectangle, caption, extracted text and
    verification state are kept. A surviving asset row is rewritten under the same
    id, so OCR and editor references stay valid; otherwise a new asset id is used.
  Empty or unknown selections, a missing document revision, a page or region that is
  not in the current project, a corrupt backup image and expired tokens return typed
  errors. The dialog has page, document, page-image and region-image modes, select-all,
  a confirmation count and a password field for encrypted uploads. A backup with no
  pages can still have its document restored.
- Backend vault tests for create/list/download/delete/restore, retention pruning,
  missing projects, unsafe names, due checks, configurable retention, automatic-on-open
  (including the off-by-default and not-due paths) and moving a deleted project's
  vault to trash, plus encryption round-trip, wrong-password, short-password,
  tamper/truncation, plain-zip and vault-plaintext tests. Selective-restore tests
  cover a stored copy and an uploaded archive, OCR/AI/element remapping, document
  preservation for page restore, token expiry and project binding, document
  inspection, restoring the current document or one revision, the forced snapshot
  and unknown-revision rejection. Page-image tests cover inspection annotations,
  in-place repair that keeps OCR and elements, new-asset repair, present-image
  refusal, checksum mismatch, a page missing from the project and a missing backup
  file. Region-image tests cover in-place repair that keeps the region and its text,
  new-asset repair, present-crop refusal, a region missing from the project, a
  region the backup does not have, a missing backup crop and the capped list that
  reveals more after a repair. Component tests cover listing, downloading, deleting
  and restoring with confirmation, creating from the empty state, load errors, the
  download dialog's plain/protected validation, the restore password field,
  inspecting and applying pages, restoring a document version, page-image statuses,
  repairing one page image without closing the dialog, region-image statuses and
  repairing one region image without closing the dialog. Dialogs, settings and
  strings exist in English and Burmese.

**Scope note**

- Selective restore covers pages, the document, a page's original, display and
  thumbnail images and an extracted region's crop. Editor undo/redo stays separate
  from revision history: it is an editing convenience, not a stored backup.

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
- **Version history is not a backup.** Document versions live in the same project
  database, so deleting the project folder, disk failure or database corruption
  removes them too. Project backup download, additive restore and the local vault
  remain manual/opt-in safeguards: automatic copies run only after opening a project,
  the vault keeps a configurable limited number of copies, is not encrypted and is not
  synced off-device, so it is not a substitute for your own off-device backup. Only
  an explicit download can be password-protected, and a forgotten password cannot be
  recovered.

## Phase 3 definition of done (met)

1. Advanced image processing operations are non-destructive and reversible.
2. Import progress, cancellation and failures are visible and localized.
3. Backend and frontend tests cover the new paths, including Burmese filenames.
4. Documentation and capability flags match the implemented behaviour.
5. Phase 3 acceptance checks pass for images, PDFs and processed-version restore.
