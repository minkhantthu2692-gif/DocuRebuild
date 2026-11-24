# Changelog

All notable changes to DocuRebuild are recorded here. This project follows
[Semantic Versioning](https://semver.org/) and the desktop application is the
supported 1.0 distribution.

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
