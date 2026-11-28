# Detailed phase history

This document keeps the long-form, phase-by-phase implementation record that
follows the original plan (archived in git as `e7966d4:Prompt.md`). A phase is
only marked complete when its own
acceptance checks pass; later-phase functionality is not presented in the UI
until it actually works.

The current release status, remaining work and deferred features are summarised
in the root `ROADMAP.md`. If the two disagree, `ROADMAP.md` and the shipped code
win.

## Status summary

| Phase | Status | Notes |
| --- | --- | --- |
| 0. Foundation and architecture | **Complete** | Monorepo, tokens, contracts, API scaffold, migrations, tests |
| 1. Local storage and project management | **Complete** | App/project DBs, folders, manifest, CRUD, trash |
| 2. Main UI and workspace | **Complete** | Header navigation, dashboard, two-panel workspace, settings, i18n |
| 3. Import and image processing | **Complete** | Image + PDF import, background jobs with progress/cancellation, rotation and non-destructive image adjustments |
| 4. Local OCR and layout detection | **Complete for Windows 1.1.x** | Tesseract adapter, review UI, layout hints, overlay, reviewable word-box table proposals (single block and page-level cross-block candidates), deterministic figure suggestions from embedded PDF images, vector drawings and opaque rendered pages, page-wide figure proposals evaluated in `docs/figure-detection.md`, a local CER/WER benchmark with synthetic and real-scan fixtures in `docs/ocr-benchmark.md`, and user-selectable page segmentation; a larger real-scan corpus remains optional |
| 5. Element extraction | **Complete for Windows 1.1.x** | Manual region crop, local region text extraction, OCR-layout, embedded-PDF-image, vector-drawing and raster-page ink suggestions with a named source, library, verification and insertion, reviewed equation crops, on-demand one-crop AI transcription, and structured table reconstruction from one saved crop locally or with AI; page-wide table, nested drawn-table, equation and opaque-PDF proposals are now available for review |
| 6. AI integration and free usage first | **In progress** | Unified BYOK provider platform with local Ollama, custom OpenAI-compatible and 12 cloud adapters, dynamic model discovery, multiple connections and encrypted keys, key rotation/cooldown/failover, per-task routing with fallbacks, remote-consent and HTTPS boundary, daily/task/connection limits, verified-cost budget, metadata-only usage ledger and history, reviewable OCR cleanup, optional vision region proposals, equation-crop transcription and table-crop reading done; account-level billing/quota verification pending |
| 7. Table, figure and equation reconstruction | **Complete for the supported scope** | Manual editable tables with merge/split, reviewable page-wide table proposals from word boxes and drawn rules, nested drawn grids linked as separate tables with a provenance note, per-cell alignment and correction, merged cells from drawn borders, local/AI reading of one saved crop, figure captions/numbers/citations, typed LaTeX with KaTeX preview and numbering/citations, page-wide equation and figure proposals for review, one-crop transcription on request, and faithful Markdown/TXT/Word/PDF export; merged-cell inference for text-only tables and automatic AI acceptance remain out of scope |
| 8. Document editor and export | **Complete** | Core editor plus manual tables, figures, display and inline equations, multi-line Word equations, footnotes, per-project page headers/footers, and local Markdown, TXT, Word and A4/Letter PDF export with configurable margins, native Word equations/footnotes, embedded figures, links and notes |
| 9. History, backup and recovery | **Complete** | Document versions with manual checkpoints, restore and read-only comparison, a filterable and exportable local project activity log for imports, processing, OCR, exports and backups, verified project backup download (plain or password-encrypted), additive (new-project) restore from an upload or a stored vault copy, page-scoped selective restore, page-image and region-crop repair and reversible document-version restore into the current project, a local backup vault with opt-in automatic copies on project open and configurable retention, and an optional one-pass scheduled-backup command for external schedulers |
| 10. Desktop distribution | **Complete for Windows** | Electron shell with a bundled PyInstaller sidecar, loopback-only API with a per-launch bearer token, bundled Tesseract with `eng`/`mya`, per-user NSIS installer, and smoke tests for the packaged backend. Mobile, PWA and device pairing are out of scope for 1.0 |
| 11. Final QA and production release | **Complete for Windows 1.1.2 build; v1.1.1 remains published** | Versioned v1.1.1 GitHub Release, AGPL-3.0 licensing, third-party notices, changelog, reproducible OCR and figure baselines, installer QA, security/performance drills and the desktop E2E smoke suite are done; a locally verified 1.1.2 installer exists but is not published. Wider-release gaps are tracked in the root `ROADMAP.md` |

## Post-1.1.1 status

The four `01_MUST_HAVE` and four `02_SHOULD_HAVE` prompt-pack tasks are complete,
along with the quick-win audit and all optional evaluations. `main` is at the
1.1.2 version/docs commit with 456 backend tests, 60 web files / 368 tests,
typecheck, lint and production build clean. Evidence, commands and limitations
are in `PROJECT_COMPLETION_REPORT.md` §§13-17, `docs/should-have/PROGRESS.md`,
`docs/quick-wins/PROGRESS.md` and `docs/optional-future/PROGRESS.md`. All
prompt-pack work is done; remaining items are recorded gaps, not tasks unless
approved. `CONTINUE_PROMPT.md` is the single paste-ready handover. The locally
built installer is `DocuRebuild-1.1.2-setup.exe` (195.92 MB, SHA-256
`56BEA0EB38B7017D2EAB143A31DE31CFF917875F1C4030216334B86D15588117`), smoke
tested 12/12 on the packaged build but not published as a GitHub release;
v1.1.1 remains the published release.

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
- Theme, accent, radius, blur, density, text size and motion settings.
- English/Burmese localization with live switching and key-parity tests.
- Reusable empty, skeleton, spinner, dialog, menu, select and segmented controls.

**Verification** — Vitest for layout/appearance/formatting/i18n, desktop checks
for theme and language switching.

---

## Phase 3 — Import and image processing (complete)

**Delivered**

- Drag/drop and file-picker import for JPG, JPEG, PNG, WebP, BMP and TIFF.
- Backend-provided size and batch limits, client-side pre-validation, localized
  rejection feedback.
- EXIF orientation, checksums, immutable originals, browser-safe display copies.
- WebP thumbnails, page ordering (drag), page deletion and non-destructive
  rotation with reset.
- Zoom, fit, actual size and page navigation; resizable thumbnail rail.
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

- Figure (image region) detection. Completed after v1.1.1: figure proposals are
  assembled from OCR layout, embedded PDF images, vector drawings, raster-page ink
  and opaque rendered pages, scored with IoU in `docs/figure-detection.md`, and
  always reviewed before insertion. A caption band is still an estimate.
- Nested tables and page-wide automatic table reading. Completed after v1.1.1 for
  drawn grids: page-wide candidates group row blocks, read PDF/raster/crop rules for
  merged spans, and link a drawn child grid to its parent cell as a separate table.
  A candidate with no drawn or usable rules remains a plain grid, OCR-only nesting
  stays manual, and a hand-corrected block is still a barrier instead of being
  bridged. Page-wide equation candidates are now listed from OCR equation blocks;
  automatic transcription and acceptance are deliberately not performed.
- OCR accuracy benchmarks (CER/WER) for English, Burmese and mixed pages. A
  local harness, committed synthetic fixtures and a measured baseline now exist
  in `docs/ocr-benchmark.md`. A three-page public-domain real-scan corpus with
  typed transcripts adds measured real-world numbers (0.47% CER on English
  prose, 22.43% on a table, 36.77% on a mixed page at PSM 11) and records its
  limits, including the absence of a scored Burmese-only case. The corpus is
  evidence, not a population estimate, and a larger set would still be needed
  before generalising. The page-segmentation comparison (Burmese PSM 3 versus
  PSM 11) is reproducible with `--segmentation-mode`.
- On 27 November 2026, a lightweight supplied-file practical check imported 8
  PDF pages and 5 JPG scans through the normal workflow. Source rendering, PDF
  text extraction, OCR review, editing, autosave/reopen and server-side TXT
  export were exercised. The PDF text was usable, Burmese schedule OCR retained
  recognizable structure but needed date/number and low-confidence manual
  review, and handwriting/mixed-script OCR remained unreliable. No code fix or
  original-file modification was required; `PROGRESS.md` records the check.
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
- Structured table reconstruction from one saved crop. **Read locally (OCR)** runs
  the same local engine over the crop, then uses the table's visible cell borders
  when they form a closed grid (keeping exact columns and merged cells) and falls
  back to grouping its words into rows and whitespace column bands otherwise. Both
  paths keep per-cell confidence; **Read with AI** is an optional second method when
  a vision route is configured. Everything feeds the normal review grid, and nothing
  is written to the element or document before insertion. The grid rules and limits
  are described under Phase 7.
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
- Unsaved region proposals and page-wide automatic table detection. A saved table
  crop can already be read into a structured grid, locally or with a vision model,
  and that delivery is described under Phase 7.

## Phase 6 — AI integration and free usage first (in progress)

**Delivered**

- One unified bring-your-own-key platform replaced the earlier separate text and
  vision profiles, local-only adapter, consent flags, per-task keys and probe
  endpoint. The provider registry in `services.ai_providers` covers local Ollama, a
  custom OpenAI-compatible server, and the OpenAI, Anthropic, Google Gemini,
  OpenRouter, Groq, Mistral, DeepSeek, xAI, Together, Fireworks, Cerebras and
  Perplexity APIs through modular adapters. `GET /api/ai/providers` is the source of
  truth; the frontend does not hardcode providers or models.
- Named connections in `ai_connections` store the provider, endpoint, remote consent,
  cost class, enabled state, rotation strategy, attempt cap and optional request and
  spend limits. Multiple connections can exist per provider, and each can hold
  several API keys in `ai_connection_keys`.
- Encrypted credential storage uses arbitrary vault ids (`connkey:<uuid>`) in
  `<data_dir>/secrets/ai_keys.enc`, with a generated Fernet master key in
  `secrets/ai_keys.key`. Keys are write-only: the API returns only metadata, and the
  value never enters `app.db`, logs, exports, the usage ledger or Git. Keys can be
  enabled, disabled, relabelled, limited, replaced or deleted without deleting the
  connection.
- Dynamic model discovery with the user's own credential through Ollama `/api/tags`
  and `/api/version` or each provider's documented listing endpoint. Normalized model
  metadata (input/output modalities, context, tools, streaming and reported pricing)
  is cached in `ai_models`; discovery is refreshed on request. Providers without a
  listing endpoint report `ai_model_discovery_unsupported` and allow manual model IDs
  (`source = manual`). Model search, favorites and recent-use clearing are supported;
  favorites survive a refresh.
- Unified task routing in `ai_task_routes` for `ocr_cleanup`, `region_proposals`,
  `equation_transcription` and `table_structure`, plus a `default` route. A route
  stores its connection/model, optional fallback connection/model, temperature,
  timeout and rolling 24-hour request limit. Saving a route validates the model
  against the connection catalog and the task capability; unknown modality metadata
  is allowed and flagged instead of blocking an otherwise usable model.
- Key rotation and health handling in `services.ai_router`: `priority`, `failover`,
  `round_robin`, `least_recent` and `least_usage` strategies; disabled, failed and
  cooling-down keys are skipped; `max_attempts` bounds provider requests; a rate limit
  puts the key into a cooldown; a fallback is tried only after the primary fails; a
  connection with no usable key never sends an unauthenticated request.
- Honest limit handling: a global daily request limit, per-task and per-connection
  limits, and a verified-spend monthly budget. Provider quotas, prices and reset times
  are never invented. A 429 is reported with the provider's advisory wait (capped at
  24 hours) and is not bypassed; 401/403 marks the key as failed.
- Remote-endpoint safety: HTTPS is required for remote hosts, HTTP is accepted only
  for loopback, embedded credentials and cloud-metadata hosts are rejected, redirects
  are not followed, and explicit remote consent is required when a connection is
  created or updated. Provider defaults that point at a remote host also require
  consent. Requests use bounded timeouts and response sizes.
- Metadata-only usage ledger extended with connection/key labels, reported
  input/output/total tokens, verified cost and cost source. Settings shows the rolling
  window, token totals, cost, unpriced count, per-task and per-connection breakdowns
  and recent entries; **View full history** pages the ledger with outcome/task
  filters and project names. Document text, prompts, images, crops and replies are
  never stored.
- Reviewable workflows preserved: OCR cleanup is stored as an `ai_suggestion` and
  accepted only when the block and run still match; region proposals remain
  unpersisted low-confidence rectangles; equation transcription stays in the dialog;
  table reading requires acknowledgement of every unscored cell. Every paid route asks
  for one-action approval before sending anything.
- One-time legacy migration converts the old text/vision profiles into connections,
  copies their encrypted keys vault-to-vault, imports model names and creates task
  routes. The legacy JSON stays as a backup, a failed migration retries later, and a
  new database skips the migration. Migration `0003_ai_byok.py` adds the normalized
  tables and usage columns without dropping existing data.
- Backend tests cover provider adapters and discovery, remote consent and HTTPS,
  URL/SSRF rules, cost classes, paid refusal, rate-limit/auth classification and
  cooldowns, key rotation and failover, connection/task/global limits, budget
  enforcement, token/cost accounting, capability validation, route persistence,
  legacy migration, OCR cleanup review and stale checks, suggestion decisions and
  bulk review, vision coordinate mapping, equation wrapper reduction and table-grid
  parsing. Frontend tests cover the new Settings UI, connection/key flows, model
  selection, route saving, usage breakdown, paid confirmation, dialog task status and
  i18n key parity.

**Remaining**

- Account-level billing and quota verification. The app records what a provider
  reports and stops at the configured local budget, but it cannot read an account's
  remaining quota or verify a charge.
- Proactive quota tracking and provider-specific advanced parameters. A 429 is
  handled correctly, but the app does not predict a quota from historical usage, and
  provider-specific knobs beyond temperature/timeout are not exposed.
- Page-wide automatic equation/figure reconstruction and image generation remain out
  of scope for this phase.
- The cost class is a user declaration. A provider can still bill outside the app, and
  a declared free tier can change without notice.
- AI output can be wrong. Accepting an OCR proposal marks it corrected, not verified;
  every vision and table reply still needs manual review.

**Current limitation** — the core application works without any provider, and local
Ollama or a local OpenAI-compatible server keeps AI free and offline. A cloud
connection requires the user's own key, an explicit remote-consent decision and a
correct cost class. Model quality, availability, context limits and licence terms
come from the provider. A saved key is protected by local file permissions and
encryption, not by a remote account: anyone who can read the data folder can use it.
Provider pricing and free-tier availability are not verified permanently; the app
never claims a provider is free and never estimates a price it cannot support.

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
- Merged-cell table proposals from drawn rules. On a PDF page the endpoint extracts
  axis-aligned strokes and thin filled or stroked rectangles from the immutable PDF;
  on a scanned page and in a saved crop it finds long straight horizontal and vertical
  strokes in the raster image, measured inside the candidate's own region so a small
  table on a full page still has measurable borders. Either source is grouped into
  drawn grids, and a missing internal separator becomes a `colspan`/`rowspan`. The
  same PDF rules are tried for a single block labelled as a table, so a merge inside
  that block is not lost to its word boxes. The review grid renders the merge, and
  insertion writes the same spans into an ordinary Tiptap table. A rotated page, a
  geometry edit or a stale run falls back to the
  word-box grid; rules are ignored when they would leave a detected word outside the
  grid, so text is never dropped. A contiguous paragraph group that the layout
  classifier refuses is still offered when its drawn borders form a closed grid,
  because the borders describe the cells more reliably than the spacing; prose outside
  the grid keeps its own block. A closed, mostly filled grid is required so a chart's
  axis frame is not offered, and a vector grid replaces an OCR candidate that lies at
  least 85% inside it.
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
  injected into the stored document. Numbered figures can be cited from the text as
  described below.
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
- A saved table crop can be read into the normal review grid. **Read locally (OCR)**
  runs the local engine on the crop and prefers its drawn cell borders: when they
  form a closed grid that holds every word, columns and merged cells come from that
  geometry instead of the whitespace between words. Otherwise it clusters its own
  word boxes into rows and whitespace column bands, so a borderless table still
  works. Both paths keep per-cell confidence so a weak cell is flagged without AI.
  **Read with AI** remains an optional second method when a vision route is
  configured: it sends only the crop and requires acknowledgement of every unscored
  cell. Every path accepts only a complete grid within the same row, column and cell
  caps, refuses an empty or non-table result instead of padding it, and keeps empty
  source cells empty. The inserted table credits the chosen method in its source note
  and says so when cells were corrected by hand; the region itself is never modified.
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

**Completed after v1.1.1**

- Page-wide table detection across row blocks and drawn rules, and nested drawn
  grids linked to a parent cell as separate reviewable tables. OCR word-box nesting
  and merged-cell inference for text-only tables remain manual.
- Page-wide figure proposals from embedded images, vector art, raster ink and opaque
  PDF pages, evaluated in `docs/figure-detection.md`; figure numbering, prose
  cross-references and inline images are delivered.
- Page-wide equation candidates from OCR equation blocks, listed in reading order.
  Word export converts typed equations to native OMML, a reviewed equation crop can
  be inserted as a real equation, and one saved crop can be transcribed on request;
  automatic transcription or acceptance is never performed.

**Still open**

- Uncertain table cells are flagged and must be acknowledged before insertion, and
  an empty source cell is never filled in. An AI-read grid has no confidence score,
  so it needs the same acknowledgement for every cell. A page-wide equation candidate
  supplies OCR text as a starting point, but no symbol enters the document without
  the user's own review.

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

## Phase 10 - Desktop distribution (complete for Windows)

**Delivered**

- Electron shell with a bundled PyInstaller one-folder Python sidecar.
- Loopback-only API with a per-launch bearer token delivered through a
  context-isolated preload bridge; `sandbox`, `contextIsolation`, no
  `nodeIntegration`, a strict CSP and origin-restricted navigation.
- Per-user NSIS installer with Start menu and desktop shortcuts, bundled
  Tesseract 5.4 with `eng`/`mya`/`osd`, and `LICENSE`/`THIRD_PARTY_NOTICES.md`.
- A data folder that matches the browser build's folder, so existing projects
  survive the upgrade; uninstalling keeps projects and backups.
- Build tooling (`scripts/build-desktop.mjs`) with cached downloads and
  `--skip-web`/`--skip-backend`/`--skip-tesseract`.

**Out of scope for 1.0:** PWA install, camera import, mobile layouts and device
pairing. The desktop window is the supported form.

## Phase 11 - Final QA and production release (complete for Windows 1.0)

**Delivered**

- Version 1.0.0 across packages, health endpoint and interface; `CHANGELOG.md`.
- AGPL-3.0 `LICENSE` and a complete `THIRD_PARTY_NOTICES.md`.
- Measured OCR baseline on committed synthetic English/Burmese/mixed pages,
  with the page-segmentation finding and `docs/ocr-benchmark.md`.
- Installed-application drills: install, launch, OCR, four export formats,
  vault backup and restore with an MD5 check, clean shutdown, uninstall with
  data retention, and reinstall over existing data.
- Performance drill on the installed build (24-page import, page OCR, 168k
  character save, DOCX/PDF export, memory sampling).
- Security drill: token enforcement, path traversal, zip slip, encrypted
  backup password handling, secret scan and dependency audit.
- Contrast audit with an automated token-contrast test.
- Final stabilization: theme-aware window background, post-startup backend and
  renderer crash handling, version metadata alignment, a repaired text encoding
  defect in the equation dialog, and a documented fresh-clone workflow.

**Remaining (tracked in `ROADMAP.md`):** a larger real-scan OCR corpus,
screen-reader and keyboard-only testing, sustained-load and cancellation
measurement, an automated end-to-end desktop smoke suite, code signing, and
macOS/Linux packaging.

---

## Cross-cutting limitations and risks

- **Burmese OCR is hard.** Fonts, diacritic order and Zawgyi legacy text require
  careful benchmarking. No conversion is ever automatic.
- **Offline processing is bounded by hardware.** The desktop build bundles
  Tesseract but no PyTorch-scale models; capabilities are reported at runtime
  instead of being implied.
- **Large documents need streaming.** Imports stream uploads and PDFs are rendered
  one page at a time as background jobs with progress and cancellation. Cancellation
  is cooperative: it is checked between files and PDF pages, so one very large page
  render or image decode still has to finish before the job stops.
- **SQLite on network shares is unsafe.** Connected devices must use the local
  API, not direct database access.
- **Dependency audit.** `npm audit --omit=dev` reports one low-severity KaTeX
  advisory (prototype pollution through `trust`). The editor renders only
  user-authored equations with `trust: false`, and the 0.19 upgrade is breaking,
  so it is accepted for 1.0. Development-only lint tooling is not part of the
  shipped application.
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
