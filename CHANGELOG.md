# Changelog

All notable changes to DocuRebuild are recorded here. This project follows
[Semantic Versioning](https://semver.org/) and the desktop application is the
supported 1.0 distribution.

## [Unreleased]

## [1.1.3] - 2026-11-28

A Windows x64 maintenance build that carries the equation-extraction improvement
in a separately versioned installer. The published v1.1.1 release asset is not
modified or replaced. No schema migration; existing projects are unchanged.

### Changed

- **Equation extraction starts from normalised LaTeX.** The **Detect equations**
  candidates no longer hand the review dialog raw OCR text as the LaTeX source.
  Each proposal now carries a `latex` starting point rebuilt from the stored OCR
  word boxes, so superscripts and subscripts the boxes expose are kept
  (`I^{0}`, `x_{i}`) and Unicode math glyphs are mapped to their commands
  (`θ` → `\theta`, `²` → `^2`, `cos` → `\cos`, `×` → `\times`, `≤` → `\leq`),
  with stray `%`, `#`, `&` and `$` escaped so the local preview renders. The
  mapping is deterministic and never guesses: a character the engine misread
  stays exactly as read, the raw OCR text is still shown in the candidate list,
  and the KaTeX preview still decides what may be inserted. Blocks with no
  usable word boxes fall back to the same normalisation of their text.
- **Clearer equation transcription prompt.** The optional AI equation prompt now
  asks for visible structure to be preserved (`\frac{...}{...}`, `^{...}`,
  `_{...}`, `\left( ... \right)`, Greek and operator commands) and for every
  term before the first equals sign to be kept in order. It still forbids adding
  anything not clearly visible.
- **Version 1.1.3.** Root, web, desktop and shared package manifests plus
  `backend/app/__init__.py` and `backend/pyproject.toml` now read 1.1.3. A clean
  `npm run desktop:dist` produced `DocuRebuild-1.1.3-setup.exe` (205,444,142
  bytes, 195.93 MB, SHA-256
  `BCB80868CF88EE9A8581BB12CA84FB2B798CFC137E77D082640B62FD7D687E20`) without
  touching the earlier installers. The 12/12 `npm run smoke:desktop` suite passed
  on the packaged build in 17 s. This build is pushed to `main` but has **not**
  been published as a GitHub release.

## [1.1.2] - 2026-11-28

A Windows x64 maintenance build that carries the post-v1.1.1 work in a
separately versioned installer. The published v1.1.1 release asset is not
modified or replaced. No schema migration; existing projects are unchanged.

### Added

- **Cross-page region review.** A new **Review regions across pages** action
  lists the figure, table and equation suggestions from each page's latest OCR
  run in one read-only overview. Selecting one navigates to its page and opens
  the normal element review dialog, where the crop is still confirmed before
  anything is saved; there is no batch accept. The overview is derived on demand
  (nothing new is persisted), reuses the per-page staleness rules, and scans at
  most 100 pages per request (200 maximum), reporting where to continue when a
  project is larger.
- **Opaque PDF drawing proposals.** A PDF page with no usable embedded image and
  no vector drawing is now analysed from its rendered page, so artwork stored as
  opaque page/form content (for example a scanned page) can be proposed for
  review at low confidence. Raster analysis runs only when exact PDF geometry is
  absent, avoiding duplicate figures and unnecessary work; rotated or
  geometry-edited PDFs use the same rendered-page path. Crops keep source pixels
  (no upscaling) and nothing is saved automatically. Mixed pages with both exact
  and opaque artwork, and light or very small drawings, remain a documented
  limitation with manual selection.
- **Nested table separation.** A table drawn wholly inside one cell of a larger
  drawn table is now offered as a separate proposal linked to its parent cell
  rather than being flattened into the parent or duplicated. Page table
  candidates carry a stable key, the child's parent key and 1-based cell, and the
  parent's nested count; the child's words are removed from the parent cell so
  the two proposals never repeat content. The review dialog badges and explains
  the relationship and records the parent/cell in the inserted source note. The
  editor has no nested-table node, so the child is inserted as a separate table
  with that note, the non-destructive fallback the task allowed. DOCX and PDF
  exports keep both grids and the parent structure. Detection is limited to
  closed drawn-rule grids; OCR word-box nesting without drawn rules remains a
  manual crop.
- **Page-wide equation proposals.** A page's OCR equation blocks are now listed
  in reading order through `GET /projects/{id}/pages/{page_id}/equation-proposals`
  and a new **Detect equations** dialog. Each candidate carries its source
  rectangle, block ids, confidence and OCR text; reviewing one saves the crop and
  opens the existing equation dialog, where the KaTeX preview must pass before
  insert. Only blocks the layout classifier labelled as equations are proposed, so
  tables and paragraphs are not offered, and inline math is not guessed at.
  Transcription stays optional and user-confirmed.
- **Page-wide figure detection evaluation.** The figure proposal pipeline is now
  scored against hand-labelled boxes with IoU matching and precision/recall
  (`backend/tests/test_figure_eval.py`, `docs/figure-detection.md`). Ten
  representative cases cover embedded images, vector charts, captions, shaded
  backing, backgrounds, logos, multi-column pages, two-figure pages and raster
  ink. Measured result: precision 1.00, recall 1.00 (TP=8, FP=0, FN=0) on the
  controlled corpus. The figure assembly is now a pure `assemble_figures`
  helper.

### Fixed

- A short caption under a wide image no longer produces two figure proposals.
  The caption band is an estimate and can be narrower or shifted relative to the
  artwork, so it now merges with the artwork box when the two share most of the
  smaller box on both axes (`regions._caption_band_matches`).

### Changed

- **Version 1.1.2.** Root, web, desktop and shared package manifests plus
  `backend/app/__init__.py` and `backend/pyproject.toml` now read 1.1.2. A clean
  `npm run desktop:dist` produced `DocuRebuild-1.1.2-setup.exe` (205,436,086
  bytes, 195.92 MB, SHA-256
  `56BEA0EB38B7017D2EAB143A31DE31CFF917875F1C4030216334B86D15588117`) without
  touching `DocuRebuild-1.1.1-setup.exe`. The 12/12 `npm run smoke:desktop`
  suite passed on the packaged build in 14 s. This build is pushed to `main` but
  has **not** been published as a GitHub release.
- **Smaller Windows installer.** The packaged build now keeps only the `en-US`
  Chromium locale, removing 54 unused Electron locale files. The English/Burmese
  application UI and the `eng`/`mya`/`osd` OCR languages are unaffected because
  they come from the web bundle and bundled Tesseract. A full
  `npm run desktop:dist` rebuild and the 12/12 `npm run smoke:desktop` suite
  verified the trimmed build: installer 204.19 -> 195.92 MB, installed footprint
  646.64 -> 598.39 MB, Chromium locales 55 -> 1 file. This build ships in 1.1.2;
  the published 1.1.1 asset is unchanged.

### Documentation

- Extended `docs/optional-future/PROGRESS.md` with three report-only
  evaluations. **Provider quota/billing:** a capability matrix of all 14
  providers found verified official endpoints only for OpenAI and Anthropic
  (admin/analytics keys), OpenRouter (management/per-key) and DeepSeek (balance);
  the decision is to stay report-only and label any future data as
  provider-reported, local estimate or unavailable. **Installer footprint:**
  measured the existing 1.1.1 build (204.19 MB installer, 646.64 MB installed;
  Chromium locales 48.82 MB, Tesseract 178.10 MB) and identified ~48 MB of locale
  trimming plus a slimmer Tesseract build, but made no packaging change without a
  verified rebuild. **macOS/Linux:** a platform matrix and blocker list (build
  targets, per-platform Tesseract, hardcoded `tesseract.exe`/`icon.ico`,
  process-group shutdown, PyInstaller cross-compile limits, data-path
  reconciliation, signing/notarization) with a rough effort estimate and no
  implementation. The PaddleOCR evaluation was deferred at that point because it
  needed a heavy local install and a measured benchmark; it has since been
  completed (see below). No application behaviour, schema, API, UI or dependency
  changed.
- Added `docs/optional-future/PROGRESS.md` with the evaluation of persisting
  OCR-derived region proposals for cross-page batch review. It documents the
  current derived-on-demand model and its stale-safety trade-off, a stable
  identity/versioning design (`ocr_run_id` + `source_asset_id` + `rotation`) for
  any future persistence, and the decision to keep proposals derived and
  non-persisted. Two regression tests in `backend/tests/test_regions.py` lock the
  stale-after-source-edit and new-OCR-run regeneration invariants. No application
  behaviour, schema or API changed.
- Completed the PaddleOCR adapter evaluation and recorded it in
  `docs/optional-future/PROGRESS.md`. PaddleOCR 3.7.0 was measured on the
  real-scan corpus with the repository's own scorer: it has no Burmese model,
  its best configuration improved the statistical table (8.33% vs 22.43% CER)
  but regressed prose and the mixed page, took 13–16x longer than Tesseract and
  would add roughly 842 MB of runtime packages. The decision is not to implement
  the adapter; Tesseract remains the sole default engine. No application code,
  dependency or packaged build changed.
- Added `docs/quick-wins/PROGRESS.md` with the regression audit of seven earlier
  requests (source rendering, dialog stability, form controls, factory reset,
  bulk deletion, OCR reconstruction and typography). All seven are recorded as
  VERIFIED WORKING with code/test evidence, packaged-build evidence and
  limitations; no confirmed defect was found, so no application behaviour changed.
- Refreshed the status documentation after v1.1.1: all four `01_MUST_HAVE` and
  all four `02_SHOULD_HAVE` prompt-pack tasks are recorded as complete with
  evidence, commits and current test totals. Added `CONTINUE_PROMPT.md` with a
  paste-ready handover for the optional and quick-win tasks, and updated
  `README.md`, `ROADMAP.md`, `docs/roadmap.md`, `PROJECT_MEMORY.md`,
  `PROJECT_COMPLETION_REPORT.md` §16 and both progress logs. No application
  behaviour changed. For 1.1.2 the same status files were refreshed with the new
  version, the locally verified installer checksum and the pushed-but-unpublished
  distinction; `CONTINUE_PROMPT.md` remains the single paste-ready handover.

## [1.1.1] - 2026-11-28

A maintenance release for the Windows x64 desktop application. It ships the
post-1.1.0 quality work: bounded PDF memory and per-project import
serialisation, a real-scan OCR accuracy baseline, a documented accessibility
audit, a large-document performance/cancellation drill, and an automated desktop
E2E smoke suite. No schema migration; existing projects are unchanged.

### Fixed

- Importing many PDFs in one session no longer grows the local backend's memory
  without bound. PyMuPDF kept native buffers for closed documents; every PDF
  import, page re-render, artwork/table analysis and PDF export now releases
  them. Ten repeated imports kept the sidecar between 156.5 and 158.8 MB instead
  of climbing by about 19 MB per import.
- Two import jobs started in one project at the same time no longer collide on
  page numbers and fail with `UNIQUE constraint failed: pages.page_number`.
  Imports in the same project are serialised; different projects still import
  in parallel.
- The desktop E2E smoke suite's shutdown step no longer fails intermittently
  with `DevTools connection closed`. Closing the window tears down the DevTools
  socket, so the in-flight `window.close()` evaluation can reject with that
  expected error; the step now tolerates it and relies on the process-exit and
  sidecar-PID checks as the real assertion.

### Verified

- Added accessibility audit coverage for the installed Windows desktop scope:
  a skip link and labelled main landmark, a labelled editor toolbar, English
  and Burmese localization parity, and automated tests for dialog Escape
  dismissal/focus restoration and native checkbox/switch/radio semantics.
  NVDA and Narrator could not be exercised because neither tooling was active
  or available in this environment; this is not claimed as WCAG certification.
- **Real-scan OCR baseline.** Added three public-domain page scans (1905 English
  prose, 1975 English statistical table, 1898 English/Burmese glossary) with
  typed transcripts, provenance and SHA-256 in
  `backend/tests/fixtures/ocr-real`. Bundled Tesseract scores clean English prose
  at 0.47% CER; the printed table (50.78% to 22.43% CER) and mixed Burmese page
  (45.33% to 36.77% CER) improve with sparse-text mode but remain reconstruction
  problems. A Burmese-only page is stored but not scored because no trustworthy
  transcript exists.
- **Large-document performance and cancellation drill.** Measured on the
  packaged sidecar and editor: a 400-page raster PDF imports in 106.68 s at
  0.259-0.267 s/page with a 197.3 MB peak, memory stays flat at 156.5-158.8 MB
  across ten repeated imports, a 1,015,143-character document saves and reads in
  0.17 s / 0.04 s, and three cancellations of a 400-page import complete in
  0.14-0.27 s with no leftover temp files. Found and fixed unbounded PyMuPDF
  buffer retention and a same-project import page-number collision (imports are
  now serialised per project).
- Added a 27 November 2026 practical-file check covering 8 PDF pages and 5
  attached JPG scans. Import and source rendering were verified, PDF page 1's
  embedded text was usable, a Burmese schedule image preserved recognizable
  table structure with manual-correction needs, and an English/Burmese
  photographed page remained limited by handwriting and mixed-script OCR.
  Editing, autosave/reload, and server-side plain-text export were verified.
  No code fix or original-file change was needed.
- **Automated desktop E2E smoke suite** (`npm run smoke:desktop`). A repeatable
  one-command suite exercises the complete user journey against the packaged
  `win-unpacked` build: launch/sidecar health, create project, import PDF, render
  source pages, OCR/review/insert, edit/save/reopen, export (Markdown/TXT/DOCX/PDF),
  backup/restore, and clean shutdown with sidecar stop verification. Uses
  disposable data directories, deterministic CDP-driven steps, and writes a JSON
  report (`docs/smoke/desktop-smoke.json`) with timings, engine versions, export
  sizes, sidecar PIDs, console errors and log tails. Total runtime ~12 s on the
  reference machine (Intel N100, 16 GB RAM).

## [1.1.0] - 2026-11-26

A feature release for the Windows x64 desktop application. It adds document
typography controls - font families, superscript and subscript, and Justify -
and reconstructs reviewed OCR output as real paragraphs, lists and headings.
Existing projects need no migration.

### Added

- **Paragraph reconstruction from OCR layout.** Reviewed OCR blocks are now
  inserted as the document's real structure instead of one paragraph per line:
  wrapped lines flow into editable paragraphs (so Justify and reflow work),
  continuation blocks in the same column are joined, side-by-side columns stay
  apart and read in order, headings remain headings, numbered/bulleted markers
  become real lists, and table/equation blocks keep their line layout. Sparse
  Tesseract output (PSM 11) and automatic layout (PSM 3) reconstruct to the same
  document. Per-block review, correction and verification are unchanged.
- **Font family management in the editor.** A font picker on the toolbar and in
  Settings -> Editor lists installed Windows fonts and imported fonts, imports
  TTF/OTF/WOFF/WOFF2 (up to 20 MB), and removes imported faces. Imported fonts
  are stored locally, served through the authenticated font API and registered
  with the FontFace API so they work in the packaged desktop app.
- **Superscript and subscript.** Toolbar buttons and Mod-. / Mod-, shortcuts
  for scientific notation (x2, H2O), preserved through save, reopen, Markdown,
  Word and PDF export.
- **Justify alignment.** A new toolbar button aligns paragraphs evenly along
  both margins; preserved through save, reopen, Word and PDF export.
- **Font embedding.** Word export embeds up to four faces per family as
  obfuscated parts with w:embedTrueTypeFonts; PDF export emits @font-face
  rules per weight/style under generated aliases. Faces whose licence forbids
  embedding or that cannot be extracted are skipped gracefully.

### Changed

- The ImportedFont table (migration 0004) and fonts/ data directory store
  imported font faces; system fonts are still detected live.
- fonttools and brotli are now runtime dependencies for font parsing and
  WOFF/WOFF2 conversion.

### Verified

- 437 backend tests and 356 web tests pass; typecheck, ESLint and the production
  build are clean.
- The rebuilt packaged sidecar was started against an empty data folder: the
  database migrated from scratch, `/api/health` reported `version: 1.1.0`, an
  unauthenticated request returned `401`, the bundled client was served from the
  same origin, and bundled Tesseract 5.4 was detected.
- The packaged sidecar passed a 30-check drill: create a project, import a
  rendered page, run English OCR at 96.5 mean confidence (6 blocks, all with line
  geometry, both prose columns and the closing paragraph read), save and reopen a
  justified document, export Markdown/TXT/DOCX/PDF, and restore a local backup as
  a new project with its page.
- The installer was installed silently (exit 0); the executable and registry
  entry report 1.1.0; launching the installed application with an empty
  temporary data folder started its sidecar and created a new database there,
  leaving existing projects untouched. Uninstalling removed the program files
  and registry entry and kept the data folder; reinstalling restored the per-user
  install and the `DocuRebuild 1.1.0` registry entry.
- The `v1.1.0` GitHub Release was published with the installer and marked latest;
  an anonymous re-download matched 214,082,110 bytes and the SHA-256 below.
- Local installer `DocuRebuild-1.1.0-setup.exe`: 214,082,110 bytes (204.2 MB),
  SHA-256
  `EC1DF483F539A0DE40DD862A820FD653E1C406AE12921B58D9B5069131A325F4`.

## [1.0.2] - 2026-11-24

A maintenance release for the 1.0 desktop application. It modernises the form
controls across the workspace and stops the Edit Image dialog from refreshing,
resetting or flickering while adjustments are made. Existing projects need no
migration.

### Changed

- **Unified checkboxes, switches and radios.** Every checkbox in the workspace,
  settings, tables and dialogs now uses one shared themed control with matching
  sizing, hover, focus and disabled states. Standalone binary settings use a
  toggle switch; independent and multi-item selections keep checkbox semantics;
  radio groups stay native radios, so keyboard, label and screen-reader
  behaviour is unchanged.
- **Edit Image applies adjustments in place.** Filter changes are previewed
  immediately and saved after a short pause instead of on every slider tick.
  The preview image and the dialog itself stay mounted while a new render
  arrives, edits are serialised so an older response cannot overwrite a newer
  one, and a pending adjustment is still saved when the dialog closes. A loading
  badge and a footer status replace the previous toast on every change.

### Fixed

- The Edit Image dialog no longer closes, blanks or resets its controls when the
  page is refreshed after an adjustment.
- The source viewer no longer remounts its page image when the page render is
  updated, so scroll position and zoom stay put.

### Verified

- 423 backend tests and 304 web tests pass; typecheck, ESLint and the production
  build are clean.
- The rebuilt packaged sidecar was started against an empty data folder: a fresh
  database migrated to the current schema, `/api/health` reported
  `version: 1.0.2`, a request without the bearer token returned `401`, and the
  bundled client was served from the same origin.
- The installer was installed silently over 1.0.1 (per-user, no administrator
  rights); the registry entry and executable report 1.0.2. Launching the
  installed application with an empty temporary data folder started its sidecar
  and created a new project database there, leaving existing projects untouched.
- The installed sidecar then ran a functional drill against an empty data folder:
  create a project, import a synthetic English page, run bundled Tesseract OCR
  (95.8 mean confidence, 709 characters), save a document, export Markdown, TXT,
  DOCX and PDF, create a backup zip and restore it as a second project with the
  same page.
- Uninstalling removed the program files and kept the local data folder and its
  database files unchanged; reinstalling 1.0.2 restored the per-user install and
  the `DocuRebuild 1.0.2` registry entry.
- The `v1.0.2` GitHub Release was published with the installer, and an anonymous
  re-download matched 211,540,824 bytes and the SHA-256 above.
- Local installer `DocuRebuild-1.0.2-setup.exe`: 211,540,824 bytes (201.7 MB),
  SHA-256
  `E501B0427371ED64B185A56E67089945896B417C9B19057130802455A1A03F47`.

## [1.0.1] - 2026-11-23

A maintenance release for the 1.0 desktop application. It repairs image display
in the installed build and adds two data-management actions that were missing:
a full factory reset and multi-project deletion.

### Added

- **Factory reset.** Settings → Local storage now offers *Clear all data*. It
  permanently removes every project folder, source page, thumbnail, extracted
  figure, database row, saved preference, AI connection, encrypted key, backup
  copy and temporary file inside the data folder, then recreates an empty
  database. Background import and OCR workers are stopped and pooled database
  connections are closed first. The action warns that it cannot be undone and
  requires typing `DELETE`, checked in the interface and again by the API. Only
  files DocuRebuild itself owns are removed, so a custom data folder that also
  holds unrelated files keeps them, and the application stays installed.
- **Multi-select and bulk delete.** The dashboard has a *Select* mode with a
  per-card accessible toggle, a live selected count, *Select all* (respecting the
  current search), *Deselect all*, *Delete selected* and *Cancel*. Deletion uses
  the existing single-project behaviour — the folder and its stored backups move
  to the local trash folder — and reports per-project failures without rolling
  back projects that were already moved. A folder that resolves outside the
  configured data folder is never moved.

### Fixed

- **Broken images in the packaged application.** Thumbnails, source page
  previews and extracted figures were requested as plain `<img>`/HTML
  subresources, which cannot attach the per-launch bearer token. The Electron
  shell now adds the token to same-origin `/api/*` requests at the network layer
  when a request does not already carry `Authorization`. The token still never
  appears in a URL, page storage or the renderer bundle.
- **Delete refuses folders outside the data folder.** Each project row stores an
  absolute folder path. A copied or stale `app.db` could therefore make delete
  (or bulk delete) move a folder that belongs to another location. Deletion now
  fails with `project_storage_outside_data_dir` and leaves both the row and the
  folder untouched; a row whose folder is already missing can still be removed.

### Verified

- 423 backend tests and 297 web tests pass; typecheck, ESLint and the production
  build are clean.
- The packaged build was installed into a clean, empty data folder and driven
  over the DevTools protocol: all workspace asset images loaded (thumbnail and
  page preview responses carried real bytes), the Clear all data dialog stayed
  disabled until `DELETE` was typed, bulk delete moved a project to `trash/`, a
  row pointing outside the data folder was refused, and the factory reset left
  an empty project list, an empty database and an unrelated file untouched.
- Local installer `DocuRebuild-1.0.1-setup.exe`: 211,539,463 bytes, SHA-256
  `9729E2116DA4E2790314BF687A0AD2D81E70F1ABE18D9D7A246892145E9B5792`. Published
  as the `v1.0.1` GitHub Release and re-downloaded without credentials: the
  published asset is the same size and checksum.

## [1.0.0] - 2026-11-22

The first desktop release. DocuRebuild now installs as a Windows application
with no Node.js, Python, Tesseract or development tools required.

### Added

- **Windows desktop application.** An Electron shell starts a bundled Python
  sidecar on a free loopback port, waits for `/api/health`, and loads the built
  client from the same origin.
- **Local-only API boundary.** Each launch generates a random token that is
  passed to the backend through its environment and exposed to the renderer
  only through a context-isolated preload bridge. Every `/api` request needs
  `Authorization: Bearer <token>`, the server binds to loopback only, and the
  bundled SPA is served by the same process.
- **Bundled OCR.** Tesseract 5.4 with `eng` and `mya` language data, plus the
  `osd` data, is packaged with the application and configured automatically.
- **Per-user installer.** An NSIS installer creates Start menu and desktop
  shortcuts without administrator rights and keeps project data on upgrade.
- **Selectable OCR page layout.** The OCR dialog offers Automatic, Single
  column, Single block and Sparse text. The run request carries the choice, and
  unsupported values are rejected with `ocr_invalid_segmentation_mode`.
- **Burmese-aware default.** Choosing a language combination that includes
  `mya` preselects sparse-text segmentation, which is the setting that keeps
  Tesseract from merging Burmese lines.
- **OCR accuracy baseline.** Committed synthetic fixtures for English, Burmese
  and mixed pages, a `--segmentation-mode` option for the benchmark, and a
  reproducible report in `docs/ocr-benchmark.md`.
- **Licensing.** The application is licensed under AGPL-3.0 (required by the
  bundled PyMuPDF), with `LICENSE` and `THIRD_PARTY_NOTICES.md` shipped in the
  installer.
- **Desktop tests.** Coverage for token enforcement, SPA fallback, unknown API
  paths, path traversal, loopback-only binding, and the token not appearing in
  the interface bundle.

### Changed

- The health endpoint now reports the application version, and the web client
  reads the version from the API instead of a hardcoded literal.
- Backend, desktop shell and packages are versioned 1.0.0.
- The interface bootstraps the saved theme from an external script so the
  desktop window can enforce a strict Content-Security-Policy.
- `.gitignore` keeps the desktop icon resources while still ignoring build
  output and user data.

### Fixed

- **Contrast.** Light-theme warning badges (white on amber, 2.95:1), the blue,
  teal, emerald, amber and rose accent presets (3.07:1-4.16:1 with white
  labels), light-theme status badge text on its tint (3.19:1-4.06:1) and the
  dark-theme primary (4.36:1) did not meet WCAG AA for normal text. The token
  values were adjusted until every pair reaches at least 4.5:1, and
  `design-tokens.test.ts` now fails the suite if a future change regresses it.
- **Startup and crash handling.** The window background now follows the system
  theme instead of always painting light, a crash of the backend after startup or
  of the renderer opens an error dialog with the log tail instead of leaving a
  dead window, and the single-instance lock focuses the existing window.
- **Navigation guard.** The desktop window compared navigation URLs by string
  prefix, so a crafted `http://127.0.0.1:<port>@host` link could have kept the
  privileged window on another site. Navigation and redirects now compare parsed
  origins, and the preload bridge is installed only on the application origin.
- **Text encoding.** A double-encoded em dash in the equation dialog's page
  fallback was replaced with the correct character.
- **Version metadata.** `backend/pyproject.toml` and the bug-report template now
  report 1.0.0.

### Accessibility

- Status colours, accents, muted text and body text are checked against the real
  token file in both themes. A screen-reader pass is still outstanding.

### Performance

- Measured on the installed build: 24-page scanned PDF imports in 3.66 s
  (0.15 s/page) with a 193 MB peak working set, page OCR takes 0.9-1.7 s,
  168k characters save in 0.08 s, and DOCX/PDF export of that document takes
  0.18 s / 0.28 s.

### Removed

- The workspace no longer carries a mobile panel switch or breakpoint hooks;
  the 1.0 interface targets the desktop workspace window only.

### Verified

- 414 backend tests and 290 web tests pass; typecheck, ESLint and the production
  build are clean.
- The packaged sidecar imports a two-page PDF with PyMuPDF, renders 1240x1755
  pages, extracts text with the bundled Tesseract at 96% mean confidence, and
  serves the SPA and its assets with token enforcement.
- The installer (`DocuRebuild-1.0.0-setup.exe`, 201.7 MB) was installed,
  launched, driven over the DevTools protocol, used for OCR, export and
  backup/restore, uninstalled and reinstalled over existing project data on
  Windows 11. The installed dashboard rendered all existing projects with no
  console errors, and closing the window left no backend process behind.
- The final installer (211,528,811 bytes, SHA-256
  `7B444BF2B996C8EC1B4699D3C438747718D2DC665CDE0CFF31368311BB14A46C`) was
  published in the
  [v1.0.0 release](https://github.com/minkhantthu2692-gif/DocuRebuild/releases/tag/v1.0.0)
  and downloaded again anonymously; the downloaded file matches the published
  checksum.
- A fresh shallow clone installed with `npm ci`, passed 414 backend tests and
  290 web tests, typecheck, ESLint and the production build without local
  history or build artifacts.

### Known limitations

- English and Burmese OCR are measured on synthetic pages only; a redacted
  real-document corpus is still needed.
- Page-wide automatic table, figure and equation detection remains incomplete.
- Cloud AI is bring-your-own-key and optional; no model or credential ships
  with the application.
- Only Windows x64 is packaged in 1.0. Mobile, PWA and device pairing are out of
  scope.
- The installer is 201.7 MB and installs 643 MB, mostly Electron's Chromium
  locale set, the Tesseract build and the Python sidecar. Trimming these is a
  future optimisation.
- Keyboard-only and screen-reader testing of the installed application is still
  outstanding; colour contrast is automated.
