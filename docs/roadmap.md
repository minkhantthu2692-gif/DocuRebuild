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
| 3. Import and image processing | **In progress** | Image import/rotation/reorder done; PDF import pending |
| 4. Local OCR and layout detection | **Next** | Engine adapters and review UI not started |
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

**Remaining before completion**

- PDF import, page rendering, embedded text extraction and mixed-PDF handling.
- Crop, deskew, perspective correction, contrast, sharpening, denoising,
  thresholding, shadow removal and background cleanup.
- Processed-version comparison/restore UI.
- Large-file and batch progress reporting.

**Dependencies** — PyMuPDF for PDFs, OpenCV for advanced image processing.

---

## Phase 4 — Local OCR and layout detection (next)

**Objectives**

- Add a provider-agnostic OCR engine interface with at least one local engine.
- Detect text blocks, paragraphs, headings, lists, tables, figures, captions,
  equations, headers/footers and page numbers where the engine supports them.
- Preserve bounding boxes, confidence, language, reading order and processing
  metadata.
- Provide a review UI for uncertain results; never auto-approve uncertain text.
- Keep manual entry available for every OCR output.
- Benchmark English, Burmese and mixed-language pages independently.

**Planned tasks**

1. Define OCR/layout result schemas in `packages/shared-types` and the project DB.
2. Implement engine adapters (Tesseract and/or PaddleOCR) with runtime capability
   detection, language-pack checks and clear “unavailable” states.
3. Add persistent job rows and a bounded background worker (no UI-thread work).
4. Add OCR controls to the source panel and a confidence/review surface.
5. Add insert-to-editor actions with source references and verification status.
6. Add fixtures and accuracy tests (CER/WER) for English, Burmese and mixed text.

**Open decision** — Tesseract is lighter and easier to package but Burmese quality
depends on installed language data; PaddleOCR can be stronger but brings a large
dependency footprint. The engine must remain replaceable behind the adapter.
Do not advertise either as universally free or universally accurate.

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
- **Large documents need streaming.** Current imports load individual images;
  future PDF/OCR work must stay page-batched and cancellable.
- **SQLite on network shares is unsafe.** Connected devices must use the local
  API, not direct database access.
- **Dependency audit.** ESLint/TypeScript-ESLint currently pull a vulnerable
  `minimatch` (moderate, development-only). Runtime dependencies are clean of
  critical advisories after the Tiptap 3 and Vitest 5 upgrades.
- **No revision history yet.** Autosave reduces loss but does not replace
  backups. Do not use this build as the only copy of important work.

## Definition of done for the next milestone

1. PDF import can render and extract text page-by-page without blocking the UI.
2. Image processing operations are non-destructive and reversible.
3. Import progress, cancellation and failures are visible and localized.
4. Backend and frontend tests cover the new paths, including Burmese filenames.
5. Documentation and capability flags match the implemented behaviour.
