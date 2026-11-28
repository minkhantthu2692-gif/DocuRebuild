# ROADMAP.md — DocuRebuild status and next work

This is the short, current roadmap for the Windows x64 desktop release.
`docs/roadmap.md` keeps the detailed phase-by-phase implementation history;
`PROJECT_MEMORY.md` records architecture and handover context.

Last updated: 2026-11-28 (v1.1.1 released; all `01_MUST_HAVE` and
`02_SHOULD_HAVE` prompt-pack tasks complete; the quick-win regression audit is
done with no confirmed defect and no code change; status docs and the
paste-ready handover refreshed in `CONTINUE_PROMPT.md`).

## Release status

**DocuRebuild 1.1.1 is the current release for the Windows x64 desktop scope
(published 28 November 2026).** The installer, bundled OCR, local
database/storage, BYOK AI, backup/restore and export are implemented and
verified. Everything below labelled *Complete* ships in
`DocuRebuild-1.1.1-setup.exe`.

**1.1.1** is a maintenance release over 1.1.0. It adds bounded PDF memory,
per-project import serialisation, a real-scan OCR baseline, an accessibility
audit, a large-document performance/cancellation drill and the automated
desktop E2E smoke suite (`npm run smoke:desktop`). No schema migration;
upgrading keeps existing projects. It supersedes `DocuRebuild-1.1.0-setup.exe`.

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

**Opaque PDF drawing extraction (28 November 2026).** A PDF page that exposes no
usable embedded image and no vector drawing is now analysed from its rendered
page, so artwork stored as opaque page/form content (for example a scanned page)
can produce a low-confidence figure proposal instead of nothing. Raster analysis
runs only when exact PDF geometry is absent, which avoids offering the same figure
twice and keeps the cost off vector-rich pages. The proposal keeps the page's
display-pixel geometry and the existing crop path uses source pixels without
upscaling; nothing is saved automatically, so review and manual selection remain
the fallback. Rotated or edited PDF pages use the same rendered-page path. The
limitation is explicit: a mixed page with one exact figure and one opaque drawing
may propose only the exact figure, and light or very small drawings can be missed.
Backend 450 tests and web 364 tests pass.

**Nested table separation (28 November 2026).** A table drawn wholly inside one
cell of a larger drawn table is now offered as a separate proposal linked to its
parent cell, instead of being flattened into the parent or duplicated. The
page-wide table endpoint returns a stable candidate key, the child's parent key
and 1-based cell, and the parent's nested count; the child's words are removed
from the parent cell so the two proposals never repeat content. The review dialog
badges both sides, explains the relationship, and writes the parent/cell into the
inserted source note. True nested editor tables are not supported by Tiptap, so
the child is inserted as a separate table with a clear note, which is the
non-destructive fallback the task allowed. Detection is limited to closed
drawn-rule grids; OCR word-box nesting without drawn rules remains a manual crop.
DOCX and PDF exports keep both grids and the parent structure. Backend 448 tests
and web 364 tests pass.

**Page-wide equation proposals (28 November 2026).** Equation blocks from the
latest OCR layout are now listed for a page through
`GET /projects/{id}/pages/{page_id}/equation-proposals`, ordered top-to-bottom and
left-to-right with source coordinates, block ids, confidence and the OCR text as a
LaTeX starting point. Only blocks the layout classifier labelled `equation` are
proposed, so tables and paragraphs are never offered, and inline math inside a
paragraph is not guessed at. A new **Detect equations** dialog lists the
candidates; reviewing one saves its crop and opens the existing equation dialog,
where the KaTeX preview must pass before anything is inserted. Transcription stays
optional and user-confirmed. Backend 444 tests and web 361 tests pass.

**Page-wide figure detection evaluation (28 November 2026).** The figure
proposal pipeline is now scored against hand-labelled boxes with IoU matching
across ten representative layouts (embedded image, vector chart, captioned image,
shaded backing, background, logo, multi-column, two figures, raster chart,
text-only raster). Measured precision 1.00 and recall 1.00 (TP=8, FP=0, FN=0) on
the controlled corpus. The evaluation exposed and fixed a duplicate-proposal
defect: a short caption under a wide image produced two boxes; the caption band
now merges with the artwork when the two share most of the smaller box on both
axes. Method, results and limitations are in `docs/figure-detection.md`; the
resumable record is `docs/should-have/PROGRESS.md`.

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

**Installed-app accessibility audit (27 November 2026).** Documented test matrix
for the desktop journey, with contrast automation, component keyboard/focus
tests, a skip link/main landmark, a labelled editor toolbar and dialog
Escape/restoration checks. The installed executable launched on Windows NT
10.0.26300.0. NVDA and Narrator were unavailable in this environment, so the
interactive screen-reader pass is recorded as a blocked, not-certified item; see
`PROGRESS.md` and `PROJECT_COMPLETION_REPORT.md` section 13.9.

**Automated desktop E2E smoke suite (28 November 2026).** `npm run smoke:desktop`
runs a deterministic, disposable-profile smoke suite against the packaged
`win-unpacked` build: launch/sidecar → create project → import PDF → render
source pages → OCR/review/insert → edit/save/reopen → export
(Markdown/TXT/DOCX/PDF) → backup/restore → clean shutdown with sidecar stop
verification. It writes a JSON report (`docs/smoke/desktop-smoke.json`, ignored),
and the shutdown step tolerates the expected DevTools connection-close race.

**Quick-win regression audit (28 November 2026).** The seven earlier requests
(source rendering after restart, dialog stability, checkbox/switch semantics,
factory reset, bulk delete, OCR paragraph reconstruction and typography) were
audited against the current tree and the packaged `win-unpacked` build. All
seven are VERIFIED WORKING, so no defect was fixed and no application/test/locale
code changed, per the prompt. Evidence: 450 backend tests, 59 web files /
364 web tests, focused re-runs of 120 backend and 69 web tests, the packaged
1.1.1 smoke report, and a disposable DOCX/PDF justification probe. Full audit
matrix and limitations: `docs/quick-wins/PROGRESS.md`.

## Completed prompt-pack tasks (MUST HAVE and SHOULD HAVE)

All eight tasks in `01_MUST_HAVE` and `02_SHOULD_HAVE` of the remaining-work
prompt pack are complete. Each task has a detailed evidence section in
`PROJECT_COMPLETION_REPORT.md` §§13-16 and `docs/should-have/PROGRESS.md`.

| Series | Tasks | Evidence | Commits |
| --- | --- | --- | --- |
| 01 MUST HAVE | Real-scan OCR baseline, accessibility audit, large-document performance/cancellation, desktop E2E smoke suite | `docs/ocr-benchmark.md`, `docs/performance.md`, `npm run smoke:desktop`, report §§13-15 | `8cb208c`, `09b5f99`, `ad7809d` |
| 02 SHOULD HAVE | Page-wide figure detection, page-wide equation proposals, nested table separation, opaque PDF drawing extraction | `docs/figure-detection.md`, `docs/should-have/PROGRESS.md`, report §16 | `04f0b5f`, `0708826`, `25ffbc7`, `0d2aa0e` |

Current tree verification: 450 backend tests, 59 web files / 364 tests,
typecheck and lint clean. These commits are on `main` after the v1.1.1 release
tag; no installer has been published from them.

## Known gaps for a wider (non-Windows) production release

These are quality/reach gaps, not missing 1.x features. They are deliberately
**not** implemented in this release. The originally listed MUST HAVE items are
all addressed; the residual gaps below and the optional prompt-pack work are
what remain.

1. **Accessibility certification (audit done; screen-reader pass blocked).**
   The 27 November 2026 audit delivered the test matrix, contrast automation,
   component keyboard/focus tests, a skip link/main landmark, a labelled editor
   toolbar and dialog Escape/restoration checks. The remaining item is an
   interactive NVDA/Narrator pass on the installed application, which was not
   possible here because neither screen reader was available. This is not
   claimed as WCAG certification.
2. **Desktop end-to-end automation.** ✅ Completed 2026-11-28. A repeatable
   one-command smoke suite (`npm run smoke:desktop`) exercises launch/sidecar,
   create project, import PDF, render source pages, OCR/review/insert,
   edit/save/reopen, export (Markdown/TXT/DOCX/PDF), backup/restore and clean
   shutdown with sidecar stop verification. Uses disposable data directories
   and deterministic CDP-driven steps. Report at `docs/smoke/desktop-smoke.json`.
3. **OCR cancellation and crash recovery.** OCR runs cannot be cancelled from
   the API or UI, and a run interrupted by a crash stays `running` after
   restart. Imports already recover as `import_interrupted`; OCR needs the same
   treatment. A hard kill during import can also leave one unreferenced
   processed image from the in-flight page.
4. **Code signing.** A certificate and signed installer/release process.
5. **macOS/Linux packaging** if those platforms become supported.

## Deferred — SHOULD HAVE

- Automatic table detection beyond the delivered row-block, drawn-rule,
  nested-drawn-grid, crop and AI-crop paths (all now implemented for review);
  text-only merged-cell inference is still manual.
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

## Remaining prompt-pack work (resumable)

The quick-win audit is complete; the optional series are not started. Run one
task per session and follow the paste-ready instructions in
[`CONTINUE_PROMPT.md`](CONTINUE_PROMPT.md); record evidence in
`docs/should-have/PROGRESS.md`, `docs/quick-wins/PROGRESS.md` or a new
series-specific progress file.

| Order | Task | Next action |
| --- | --- | --- |
| 1 | `04_QUICK_WINS_AND_REGRESSION_CHECKS/01_Audit_Previously_Requested_Fixes.md` | done — all seven VERIFIED WORKING; no confirmed defect, no code change; `docs/quick-wins/PROGRESS.md` |
| 2 | `03_OPTIONAL_FUTURE/01_Persisted_Region_Proposals_Batch_Review.md` | Document the design and stale-safety trade-off before changing persistence. |
| 3 | `03_OPTIONAL_FUTURE/02_PaddleOCR_Adapter_Evaluation.md` | Benchmark against the real-scan corpus before any adapter implementation. |
| 4 | `03_OPTIONAL_FUTURE/03_Provider_Quota_Introspection.md` | Official documented APIs only; report unavailable when data is not reliable. |
| 5 | `03_OPTIONAL_FUTURE/04_Windows_Installer_Footprint_Optimisation.md` | Measure components first; keep OCR languages, licences and upgrade reliability. |
| 6 | `03_OPTIONAL_FUTURE/05_macOS_Linux_Feasibility.md` | Report and platform matrix only; no implementation without approval. |

## Explicitly out of scope for 1.x

- Mobile application, PWA install, camera import and device pairing.
- Cloud accounts, mandatory cloud storage or telemetry.
- Automatic Zawgyi/Unicode conversion.
- Silent or automatic paid AI usage.

## Known limitations

See `PROJECT_MEMORY.md` §12 and `CHANGELOG.md` §1.1.0. The headline limits are:
Windows x64 only, ~204 MB installer / ~650 MB installed, a three-page real-scan
OCR corpus (not a population estimate, one transcriber, no scored Burmese-only
case), page-wide equation proposals depend on OCR equation blocks, nested tables
are inserted as separate linked tables because the editor has no nested-table
node, opaque PDF artwork is proposed from the rendered page at low confidence and
may still need manual selection, no code signing, no
interactive screen-reader certification, no OCR cancellation or stale-run
recovery, and one accepted low-severity KaTeX advisory. Performance and memory
were measured to 400 pages on one N100/16 GB machine (`docs/performance.md`); a
1,000-page import, low-memory hardware and low-power/thermal variations remain
unmeasured. An automated desktop E2E smoke suite is now available
(`npm run smoke:desktop`, section "Completed after 1.1.0"). Current prompt-pack
status and the one-task-per-session handover are in
[`CONTINUE_PROMPT.md`](CONTINUE_PROMPT.md).
