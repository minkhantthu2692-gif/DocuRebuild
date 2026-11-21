# Changelog

All notable changes to DocuRebuild are recorded here. This project follows
[Semantic Versioning](https://semver.org/) and the desktop application is the
supported 1.0 distribution.

## [1.0.0] - 2026-11-20

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
