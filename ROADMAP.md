# ROADMAP.md — DocuRebuild status and next work

This is the short, current roadmap for the 1.0 Windows desktop release.
`docs/roadmap.md` keeps the detailed phase-by-phase implementation history;
`PROJECT_MEMORY.md` records architecture and handover context.

Last updated: 2026-11-23.

## Release status

**DocuRebuild 1.0.0 is complete for the Windows x64 desktop scope.** The
installer, bundled OCR, local database/storage, BYOK AI, backup/restore and
export are implemented and verified. Everything below labelled *Complete* is
shipped in `DocuRebuild-1.0.0-setup.exe`.

**1.0.1 (unreleased installer)** fixes image/thumbnail/figure loading in the
installed build and adds the factory reset and dashboard multi-select bulk
delete. The code and tests are in the repository; the 1.0.1 installer is built
and smoke tested locally before publishing.

## Completed — 1.0 MUST HAVE

| Area | Delivered |
| --- | --- |
| Foundation | npm-workspaces monorepo, React/Vite/Tailwind client, FastAPI backend, SQLite + Alembic, shared contracts, design tokens, typed errors |
| Projects and storage | Local app/project databases, project folders, manifest, create/open/rename/delete-to-trash, dashboard multi-select bulk delete, integrity checks |
| Import | Images (JPG/PNG/WebP/BMP/TIFF) and PDFs, immutable originals, EXIF, checksums, 150 DPI PDF rendering, background jobs with progress and cancellation, PDF text-layer extraction |
| Image processing | Non-destructive crop, perspective, deskew, grayscale, contrast, brightness, sharpness, denoise, threshold, shadow/background cleanup, before/after preview, reset |
| OCR | Bundled Tesseract 5.4 `eng`/`mya`/`osd`, page segmentation choice, confidence, editable/verifiable blocks, stale detection, layout hints and overlay, local CER/WER benchmark |
| Tables | Editable tables, merge/split, word-box proposals, page-level row grouping, drawn-rule grids with merged cells, per-cell alignment and correction, local/AI reading of a saved crop |
| Figures and equations | Manual crops, local text extraction, PDF/raster region proposals, inline images, captions, numbering, cross-references, LaTeX equations with KaTeX, Word OMML, optional vision transcription |
| Editor and export | Tiptap editor with links, find/replace, tables, figures, equations, footnotes and headers/footers; Markdown, TXT, DOCX and PDF export with configurable page/margin |
| History and backup | Document revisions with compare/restore, activity log with CSV/JSON export, verified zip and password-encrypted `.drbz` backup, additive and selective restore, local vault with retention, opt-in scheduled copies |
| AI (BYOK) | Local Ollama, custom OpenAI-compatible and 12 cloud adapters, dynamic discovery, encrypted key vault, rotation/failover, per-task routes, limits and budget, remote consent, metadata-only usage ledger, reviewable proposals |
| Desktop release | Electron shell, PyInstaller sidecar, loopback-only token-protected API (including API subresource requests), strict CSP and sandbox, bundled OCR, per-user NSIS installer, data-preserving uninstall, AGPL licensing and third-party notices |
| Data management | Typed-confirmation factory reset that removes only app-owned data and keeps the application installed |
| Internationalization | English and Burmese, live switching, key-parity tests, Unicode-safe layout |

## Remaining MUST HAVE before a wider (non-Windows) production release

These are quality/reach gaps, not missing 1.0 features. They are deliberately
**not** implemented in this archived state.

1. **Real-scan OCR validation.** Build a redacted corpus of real English,
   Burmese and mixed documents and publish CER/WER alongside the synthetic
   baseline.
2. **Accessibility certification.** Keyboard-only and screen-reader passes on the
   installed application; contrast is already automated.
3. **Desktop end-to-end automation.** A repeatable installed-app smoke suite
   (install → launch → import → OCR → export → backup/restore → uninstall).
4. **Sustained-load and cancellation measurement** on large projects and long
   OCR/import batches.
5. **Code signing.** A certificate and signed installer/release process.
6. **macOS/Linux packaging** if those platforms become supported.

## Deferred — SHOULD HAVE

- Page-wide automatic equation and figure recognition as reviewable proposals.
- Nested-table detection and automatic page-wide table detection beyond the
  current row-block/drawn-rule/crop paths.
- A bundled offline LaTeX typesetter for PDF export (equations currently export
  as LaTeX source).
- Remaining OMML edge cases (colour, accent semantics).
- Provider-specific AI parameters beyond temperature/timeout, and proactive
  quota prediction.
- Installer footprint reduction (Chromium locales, Tesseract build, sidecar).
- Automatic update checking and delta updates.
- Additional OCR engines behind the existing adapter, only if they preserve the
  review/verification guarantees.

## Deferred — OPTIONAL

- Additional interface languages.
- PaddleOCR or other heavier local engines.
- More export templates and page-layout reconstruction from source geometry.
- Team/shared-project workflows (would require a separate local/self-hosted
  design; no cloud account is planned).
- Plugins or scripting for custom reconstruction rules.

## Explicitly out of scope for 1.0

- Mobile application, PWA install, camera import and device pairing.
- Cloud accounts, mandatory cloud storage or telemetry.
- Automatic Zawgyi/Unicode conversion.
- Silent or automatic paid AI usage.

## Known limitations

See `PROJECT_MEMORY.md` §12 and `CHANGELOG.md` §1.0.0. The headline limits are:
Windows x64 only, ~202 MB installer / ~643 MB installed, synthetic-only OCR
benchmark, incomplete page-wide equation/figure recognition, no code signing,
no desktop E2E suite, and one accepted low-severity KaTeX advisory.
