# Changelog

All notable changes to DocuRebuild are recorded here. This project follows
[Semantic Versioning](https://semver.org/) and the desktop application is the
supported 1.0 distribution.

## [Unreleased]

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
