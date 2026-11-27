# ROADMAP.md — DocuRebuild status and next work

This is the short, current roadmap for the Windows x64 desktop release.
`docs/roadmap.md` keeps the detailed phase-by-phase implementation history;
`PROJECT_MEMORY.md` records architecture and handover context.

Last updated: 2026-11-27 (large-document performance drill and real-scan OCR
validation added after 1.1.0).

## Release status

**DocuRebuild 1.1.0 is the current release for the Windows x64 desktop scope
(published 26 November 2026).** The installer, bundled OCR, local
database/storage, BYOK AI, backup/restore and export are implemented and
verified. Everything below labelled *Complete* ships in
`DocuRebuild-1.1.0-setup.exe`.

**1.1.0** adds document typography controls (font family selection with custom
font import, superscript/subscript and Justify) and layout-aware paragraph
reconstruction: reviewed OCR blocks are inserted as flowing paragraphs, real
lists and headings while side-by-side columns stay apart. It supersedes
`DocuRebuild-1.0.2-setup.exe`; upgrading keeps existing projects.

**1.0.2** unified checkboxes, switches and radios across the workspace and fixed
the Edit Image dialog reloading, resetting its controls or flickering during
adjustments.

**1.0.1** fixed image/thumbnail/figure loading in the installed build and added
the factory reset, dashboard multi-select bulk delete and a guard that refuses
to delete a project folder outside the data folder.

## Completed — 1.x MUST HAVE

| Area | Delivered |
| --- | --- |
| Foundation | npm-workspaces monorepo, React/Vite/Tailwind client, FastAPI backend, SQLite + Alembic, shared contracts, design tokens, typed errors |
| Projects and storage | Local app/project databases, project folders, manifest, create/open/rename/delete-to-trash, dashboard multi-select bulk delete, integrity checks |
| Import | Images (JPG/PNG/WebP/BMP/TIFF) and PDFs, immutable originals, EXIF, checksums, 150 DPI PDF rendering, background jobs with progress and cancellation, PDF text-layer extraction |
| Image processing | Non-destructive crop, perspective, deskew, grayscale, contrast, brightness, sharpness, denoise, threshold, shadow/background cleanup, before/after preview, reset |
| OCR | Bundled Tesseract 5.4 `eng`/`mya`/`osd`, page segmentation choice, confidence, editable/verifiable blocks, stale detection, layout hints and overlay, layout-aware paragraph/list/heading reconstruction on insert, local CER/WER benchmark |
| Tables | Editable tables, merge/split, word-box proposals, page-level row grouping, drawn-rule grids with merged cells, per-cell alignment and correction, local/AI reading of a saved crop |
| Figures and equations | Manual crops, local text extraction, PDF/raster region proposals, inline images, captions, numbering, cross-references, LaTeX equations with KaTeX, Word OMML, optional vision transcription |
| Editor and export | Tiptap editor with links, find/replace, tables, figures, equations, footnotes and headers/footers; typography and scientific formatting: font family selection with Windows font detection and custom font import, superscript/subscript, text justification; Markdown, TXT, DOCX and PDF export with configurable page/margin, embedded fonts |
| History and backup | Document revisions with compare/restore, activity log with CSV/JSON export, verified zip and password-encrypted `.drbz` backup, additive and selective restore, local vault with retention, opt-in scheduled copies |
| AI (BYOK) | Local Ollama, custom OpenAI-compatible and 12 cloud adapters, dynamic discovery, encrypted key vault, rotation/failover, per-task routes, limits and budget, remote consent, metadata-only usage ledger, reviewable proposals |
| Desktop release | Electron shell, PyInstaller sidecar, loopback-only token-protected API (including API subresource requests), strict CSP and sandbox, bundled OCR, per-user NSIS installer, data-preserving uninstall, AGPL licensing and third-party notices |
| Data management | Typed-confirmation factory reset that removes only app-owned data and keeps the application installed |
| Internationalization | English and Burmese, live switching, key-parity tests, Unicode-safe layout |
| Interface polish | Shared themed checkbox/switch/radio controls; Edit Image and the source viewer update previews in place without remounting, flickering or losing dialog state |

## Completed after 1.1.0

**Practical-file validation (27 November 2026).** A lightweight normal-workflow
check imported 8 PDF pages and 5 supplied JPG scans. Source rendering,
PDF text extraction, Burmese and mixed-script OCR proposals, editing,
autosave/reopen, and plain-text export were exercised. The supplied PDF text
was usable, the Burmese schedule retained recognizable table structure with
manual date/number review, and handwriting/mixed-script areas remained
low-confidence OCR. No reproducible code defect or source-file change was
found. The brief record is in `PROGRESS.md`.

**Large-document performance and cancellation (27 November 2026).** The
installed-equivalent Electron shell and packaged Python sidecar were profiled on
the N100/16 GB reference machine with raster PDFs from 1 to 400 pages, a
145k-character editor document, three repeated cancellations, concurrent import
jobs, a hard kill mid-import and shutdowns during OCR. Imports stayed linear at
0.259-0.267 s/page (400 pages in 106.7 s, peak 197 MB); ten repeated imports kept
the sidecar between 156.5 and 158.8 MB; the editor took 4.70 s for 144,753 typed
characters, autosaved 0.99 s after the last input and reopened in 0.57 s;
cancellation reached `cancelled` in 0.14-0.27 s with no temp files; and a crash
recovered 3 committed pages as `import_interrupted` before a clean import. Two
defects were found and fixed: PyMuPDF native stores accumulated ~19 MB per import
(now released after every PDF close/export) and concurrent imports in one
project collided on `page_number` (imports are now serialised per project). Full
evidence, limitations and reproduction commands are in `docs/performance.md`.

**Real-scan OCR validation (27 November 2026).** A three-page public-domain
corpus with transcripts typed from the page now lives in
`backend/tests/fixtures/ocr-real/`, and `docs/ocr-benchmark.md` publishes the
measured CER/WER next to the synthetic baseline.

| Case | Content | Mode 3 CER / WER | Mode 11 CER / WER |
| --- | --- | --- | --- |
| `english-prose` | 1905 letterpress novel page | 0.47% / 3.64% | 0.47% / 3.64% |
| `english-table` | 1975 US statistical table, 21 data rows | 50.78% / 96.40% | 22.43% / 92.54% |
| `burmese-mixed` | 1898 English/Burmese/transliteration page | 45.33% / 97.78% | 36.77% / 76.30% |
| **Overall** | 4,293 reference characters | **42.00% / 80.60%** | **22.64% / 73.66%** |

Reproduce from `backend/` with
`python -m app.ocr_benchmark tests/fixtures/ocr-real` and add
`--segmentation-mode 11` for the sparse-text run. Provenance, SHA-256 values,
crop boxes and transcription conventions are in
`backend/tests/fixtures/ocr-real/ACQUISITION.md`.

Recorded limits: one transcriber and no second proofreader (Burmese tone marks
are the least certain part of the reference); no scored Burmese-only case,
because the one suitable page has no trustworthy transcript and is kept in
`blocked/` as a qualitative observation; and no DPI metadata on any image,
because the adapter re-encodes without a resolution hint. The table and mixed
numbers are dominated by reconstruction (thousands separators, column leaders,
Burmese dot leaders), not by character recognition, so they describe the current
adapter rather than the engine's ceiling.

## Remaining MUST HAVE before a wider (non-Windows) production release

These are quality/reach gaps, not missing 1.x features. They are deliberately
**not** implemented in this release.

1. **Accessibility certification.** Contrast automation and component-level
   keyboard/focus tests are present, including a skip link, editor toolbar
   name and dialog Escape/restoration checks. An interactive keyboard-only
   journey and NVDA/Narrator pass on the installed application remain open
   because this environment has neither screen reader available.
2. **Desktop end-to-end automation.** A repeatable installed-app smoke suite
   (install → launch → import → OCR → export → backup/restore → uninstall).
3. **OCR cancellation and crash recovery.** OCR runs cannot be cancelled from
   the API or UI, and a run interrupted by a crash stays `running` after
   restart. Imports already recover as `import_interrupted`; OCR needs the same
   treatment. A hard kill during import can also leave one unreferenced
   processed image from the in-flight page.
4. **Code signing.** A certificate and signed installer/release process.
5. **macOS/Linux packaging** if those platforms become supported.

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

## Explicitly out of scope for 1.x

- Mobile application, PWA install, camera import and device pairing.
- Cloud accounts, mandatory cloud storage or telemetry.
- Automatic Zawgyi/Unicode conversion.
- Silent or automatic paid AI usage.

## Known limitations

See `PROJECT_MEMORY.md` §12 and `CHANGELOG.md` §1.1.0. The headline limits are:
Windows x64 only, ~204 MB installer / ~650 MB installed, a three-page real-scan
OCR corpus (not a population estimate, one transcriber, no scored Burmese-only
case), incomplete page-wide equation/figure recognition, no code signing, no
desktop E2E suite, no OCR cancellation or stale-run recovery, and one accepted
low-severity KaTeX advisory. Performance and memory were measured to 400 pages
on one N100/16 GB machine (`docs/performance.md`); a 1,000-page import,
low-memory hardware and low-power/thermal variations remain unmeasured.
