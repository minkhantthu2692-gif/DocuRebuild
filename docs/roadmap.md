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
| 3. Import and image processing | **In progress** | Image + PDF import/rotation/reorder done; advanced image processing pending |
| 4. Local OCR and layout detection | **In progress** | Tesseract adapter, review UI and insertion done; table/figure detection pending |
| 5. Element extraction | Planned | Depends on Phase 4 |
| 6. AI integration and free usage first | Planned | Depends on elements and review model |
| 7. Table, figure and equation reconstruction | Planned | Depends on Phase 5/6 |
| 8. Document editor and export | Partially started | Core editor exists; full model/export pending |
| 9. History, backup and recovery | Planned | Event table exists; no restore UI |
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

## Phase 3 — Import and image processing (in progress)

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

**Remaining before completion**

- Crop, deskew, perspective correction, contrast, sharpening, denoising,
  thresholding, shadow removal and background cleanup.
- Processed-version comparison/restore UI.
- Large-file and batch progress reporting.
- Cancellable PDF import for very large documents (rendering is page-batched but
  currently runs to completion once started).

**Dependencies** — PyMuPDF for PDF rendering (installed and verified); OpenCV for
advanced image processing.

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
- Backend tests for persistence, correction, verification, stale detection,
  missing language data and unavailable engines; frontend i18n parity tests.

**Remaining before completion**

- Table, figure, caption, equation, header/footer and page-number detection.
  Current heading and list-item labels are conservative heuristics, not layout
  guarantees.
- OCR accuracy benchmarks (CER/WER) for English, Burmese and mixed pages using
  fixtures from real documents.
- A bounding-box overlay on the source viewer and block-to-image highlighting.
- Optional richer engines (for example PaddleOCR) behind the same adapter, only
  if they can preserve the same review and verification guarantees.

**Current limitation** — Tesseract must be installed locally with `eng` and/or
`mya` traineddata. OCR is not advertised as available otherwise, and Burmese
accuracy depends on scan quality, fonts and language data. No engine is
described as universally free or universally accurate.

---

## Phase 5 — Element extraction (planned)

- Select, crop and insert text, tables, figures and equations.
- Preserve source coordinates and page references.
- Manual and AI-assisted extraction paths.
- Confidence and verification indicators; original remains available.

## Phase 6 — AI integration and free usage first (planned)

- Local providers (Ollama, LM Studio, OpenAI-compatible local servers).
- Free-tier and paid providers behind one adapter with dynamic model discovery.
- Independent Vision, Text/Reasoning and Image Generation profiles.
- Explicit consent before external transmission, usage limits, cost guards,
  rate-limit handling, fallbacks and task routing.
- No paid call without user approval; no silent provider switch.

## Phase 7 — Tables, figures and equations (planned)

- Editable tables with merge/split, headers, alignment and comparison view.
- Structured figure representation and optional reconstruction with approval.
- LaTeX editing and live preview; validated OMML export for Word.
- Uncertain cells/symbols are marked for review, never invented.

## Phase 8 — Document editor and export (partially started)

**Current** — headings, paragraphs, lists, blockquotes, code, alignment, inline
marks, undo/redo and autosave.

**Pending** — tables, images, captions, equations, footnotes, links, page layout,
headers/footers, page numbers, find/replace, DOCX/TXT export and OMML validation.

## Phase 9 — History, backup and recovery (planned)

- Document revisions, processing/AI/export history and version comparison.
- Selective restore and export history.
- Project backup/restore with verification and conflict detection.
- Editor undo/redo stays separate from revision history.

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
  one page at a time, but a batch still completes synchronously from the client's
  point of view. Future work should add progress and cancellation for very large
  batches.
- **SQLite on network shares is unsafe.** Connected devices must use the local
  API, not direct database access.
- **Dependency audit.** ESLint/TypeScript-ESLint currently pull a vulnerable
  `minimatch` (moderate, development-only). Runtime dependencies are clean of
  critical advisories after the Tiptap 3 and Vitest 5 upgrades.
- **No revision history yet.** Autosave reduces loss but does not replace
  backups. Do not use this build as the only copy of important work.

## Definition of done for the next milestone

1. Advanced image processing operations are non-destructive and reversible.
2. Import progress, cancellation and failures are visible and localized.
3. Backend and frontend tests cover the new paths, including Burmese filenames.
4. Documentation and capability flags match the implemented behaviour.
5. Phase 3 acceptance checks pass for images, PDFs and processed-version restore.
