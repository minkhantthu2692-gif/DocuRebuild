# PROJECT_MEMORY.md — DocuRebuild handover

This is the durable context file for DocuRebuild. A new AI agent (or a new human
developer) should be able to read this document and `AGENTS.md`, clone the
repository, run the checks and continue work without any previous conversation.

Last updated: 2026-11-28 (v1.1.1 released with desktop E2E smoke suite verified;
optional tasks evaluated: region proposals kept derived (§10 item 16), provider
quota report-only (§10 item 17), platform posture (§10 item 18); installer
footprint trimmed and verified (§10 item 19); PaddleOCR deferred).

## 1. What the product is

DocuRebuild is a local-first document reconstruction workspace. A user imports
scanned images or PDFs, reviews OCR text, reconstructs tables, figures and
equations, edits the result in a rich-text editor, and exports Markdown, plain
text, Word (`.docx`) or PDF. Optional bring-your-own-key AI can clean up OCR,
propose regions, transcribe an equation crop or read a table crop, but every AI
result is a reviewable proposal and the application works fully without AI.

The 1.0/1.1 distribution is a **Windows x64 desktop application**:

- Electron 45 shell (`apps/desktop`) with a context-isolated preload bridge.
- Python 3.12 FastAPI backend packaged as a PyInstaller one-folder sidecar.
- Bundled Tesseract 5.4 (`eng`, `mya`, `osd`) extracted into the installer.
- Per-user NSIS installer; no Node.js, Python, Tesseract or admin rights needed.
- SQLite databases and project folders stored under the user's local app data.

Mobile, PWA, camera import and device pairing are **out of scope for 1.x** and
were deliberately removed. Do not reintroduce them without an approved scope
change.

## 2. How to resume from a fresh clone

Requirements: Windows 10/11 x64, Node.js 20+ (24 is used locally), Python 3.11+
(3.12 is used locally), and `npm`. Tesseract is only needed for OCR tests and
for building the desktop payload; the build script downloads it.

```powershell
git clone https://github.com/minkhantthu2692-gif/DocuRebuild.git
cd DocuRebuild
npm ci

python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# Verify
backend/.venv/Scripts/python -m pytest backend/tests -q
npm run test:web
npm run typecheck
npm run lint
npm run build

# Run the development servers (API :8000, Vite :5173)
npm run dev

# Build the desktop payload and installer
npm run desktop:dist
# -> dist/desktop-installer/DocuRebuild-1.1.1-setup.exe
```

The desktop payload build (`scripts/build-desktop.mjs`) does three things:

1. Builds the web client into `dist/desktop/web`.
2. Runs PyInstaller with `backend/pyinstaller.spec` into `dist/desktop/backend`.
3. Downloads and extracts Tesseract into `dist/desktop/tesseract` (cached under
   `dist/.cache`). Pass `--skip-web`, `--skip-backend` or `--skip-tesseract` to
   reuse an existing step.

`npm run desktop:dist` then runs electron-builder. `dist/` is git-ignored.

## 3. Process model and request flow

```text
Electron main process (apps/desktop/src/main.cjs)
  ├─ single-instance lock, window state, theme-aware background
  ├─ generates a 32-byte hex token per launch
  ├─ picks a free loopback port
  ├─ spawns dist/desktop/backend/docurebuild-backend.exe --port <port>
  │    env: DOCUREBUILD_DATA_DIR, DOCUREBUILD_API_TOKEN,
  │         DOCUREBUILD_WEB_DIST, DOCUREBUILD_TESSERACT_CMD,
  │         DOCUREBUILD_TESSDATA_DIR, DOCUREBUILD_LOG_DIR
  ├─ polls GET /api/health with the bearer token until ready (45 s budget)
  └─ loads http://127.0.0.1:<port>/ in a sandboxed BrowserWindow

Renderer (apps/web)
  └─ preload exposes { apiToken, platform: "desktop", version }
     All API calls add Authorization: Bearer <token> from window.docurebuild.
     The shell's webRequest hook adds the same header to same-origin /api/*
     subresources (<img>, editor HTML) that cannot set one, so thumbnails,
     source pages and figures load without the token ever entering a URL.

FastAPI sidecar (backend/desktop_server.py -> backend/app/main.py)
  ├─ binds 127.0.0.1 only; rejects non-loopback --host
  ├─ token middleware protects every /api path
  ├─ serves the built SPA and static assets from DOCUREBUILD_WEB_DIST
  ├─ writes backend.log when DOCUREBUILD_LOG_DIR is set
  └─ SQLite + PyMuPDF + Pillow + Tesseract run in-process
```

Security properties enforced by the shell:

- `contextIsolation: true`, `sandbox: true`, `nodeIntegration: false`,
  `devTools` only with `DOCUREBUILD_DEVTOOLS=1`.
- Strict CSP (`default-src 'self'`, no remote script/style origins).
- Permission requests are denied except sanitized clipboard writes.
- `will-navigate` and `will-redirect` compare parsed origins, and
  `setWindowOpenHandler` keeps navigation on the local origin; external
  `http(s)`/`mailto` links open in the system browser.
- The preload bridge is installed only when the page origin is the application
  origin, so a foreign page cannot read the launch token.
- Window close stops the sidecar process tree (Tesseract children included).
- A post-startup backend crash or renderer crash shows an error dialog instead of
  leaving a dead window.

## 4. Data layout

Defaults on Windows:

| Path | Contents |
| --- | --- |
| `%LOCALAPPDATA%\DocuRebuild\DocuRebuild\app.db` | Application database (projects, settings, AI connections/routes/usage) |
| `...\projects\<project_id>\project.db` | Per-project database (pages, assets, OCR, elements, document, revisions, history) |
| `...\projects\<project_id>\manifest.json` | Project metadata, written atomically |
| `...\projects\<project_id>\source\` | Immutable imported originals |
| `...\projects\<project_id>\processed\` | Rendered pages, crops, derived images |
| `...\projects\<project_id>\thumbnails\` | WebP thumbnails |
| `...\projects\<project_id>\exports\` | Reserved for exported files |
| `...\projects\<project_id>\backups\` | Project-local backups |
| `...\backups\<project_id>\` | Local backup vault copies |
| `...\trash\` | Deleted projects and assets (not automatically purged) |
| `...\secrets\ai_keys.enc` | Fernet-encrypted AI credential vault |
| `...\secrets\ai_keys.key` | Local Fernet master key (owner-only ACL best effort) |
| `...\tmp\` | Short-lived selective-restore workspaces (1 h TTL) |
| `%APPDATA%\DocuRebuild\window-state.json` | Window bounds and maximized state |
| `%APPDATA%\DocuRebuild\logs\backend.log` | Sidecar stdout/stderr |

`DOCUREBUILD_DATA_DIR` overrides the data root. Uninstalling the application
does **not** delete this data. The `start-docurebuild.bat` development launcher
uses the same folder, so projects created in browser development mode survive the
switch to the desktop app.

## 5. Databases and migrations

- Application DB: `backend/app/db/` with models for projects, settings, AI
  connections, keys, models, task routes and the metadata-only usage ledger.
- Project DB: pages, assets, OCR runs/blocks, elements, document, document
  revisions and activity history.
- Alembic migrations in `backend/alembic/versions/`: `0001_initial`,
  `0002_ai_usage`, `0003_ai_byok`. Runs automatically at startup; never edit an
  applied migration.
- SQLite is opened with foreign keys and WAL-friendly settings. Backup snapshots
  are taken transactionally; an in-progress import blocks a backup.
- Each project records its schema version in its manifest; restore validates the
  archive, SQLite integrity, required tables, migration version and every asset
  reference before registering a **new** project.

## 6. Feature status (1.0 MUST HAVE)

| Area | Status | Notes |
| --- | --- | --- |
| Project management | Complete | Create, list, open, rename, delete to trash, multi-select bulk delete, integrity checks |
| Image/PDF import | Complete | Images and PDFs, immutable originals, 150 DPI rendering, EXIF, checksums, background jobs with progress/cancel |
| Image processing | Complete | Non-destructive crop, perspective, deskew, grayscale, contrast, brightness, sharpness, denoise, threshold, shadow/background cleanup |
| Local OCR | Complete | Tesseract adapter, `eng`/`mya`/mixed, confidence, editable and verifiable blocks, stale detection, page segmentation choice |
| PDF text layer | Complete | Reviewable `pdf-text` runs in the same OCR review flow; invalidated on rotation |
| Layout hints and overlay | Complete | Deterministic heading/list/caption/equation/table/header/footer/page-number hints and measured overlay |
| Table proposals | Complete for the supported scope | Word-box grids, page-level row-block grouping, PDF/raster drawn rules with merged cells, nested drawn grids linked to a parent cell as separate reviewable tables, review/edit/acknowledge before insert |
| Element extraction | Complete | Manual crops, local region text, PDF image/vector and raster ink proposals (including opaque-PDF rendered-page figures), figure/table/equation insertion, verification, repair; page-wide figure proposals scored against ground truth (precision/recall 1.00 on the controlled corpus, `docs/figure-detection.md`); page-wide equation proposals from OCR equation blocks in reading order |
| Equations | Complete for the supported scope | Typed LaTeX with offline KaTeX, numbering, cross-references, Word OMML, reviewed equation-crop insertion and optional vision transcription |
| Editor and export | Complete | Headings, lists, quotes, code, links, find/replace, tables, figures, inline images, equations, footnotes, headers/footers; Markdown/TXT/DOCX/PDF export |
| History and backup | Complete | Revisions, restore/compare, activity log with CSV/JSON export, verified zip/drbz backup, additive and selective restore, local vault with retention, opt-in scheduled copies |
| AI (BYOK) | Complete for the supported scope | Local Ollama + custom OpenAI-compatible + 12 cloud adapters, dynamic models, encrypted keys, rotation/failover, per-task routes, limits/budget, consent, metadata-only usage |
| Desktop distribution | Complete for Windows | Electron + sidecar, token (including API subresource injection), CSP, bundled Tesseract, NSIS installer, data-preserving uninstall, typed-confirmation factory reset |
| i18n | Complete | English + Burmese, live switching, key parity tests, Unicode-safe |
| Form controls and dialogs | Complete | Shared native `Checkbox`/`Switch`/`Radio` primitives, one owner per open dialog, in-place image previews |

All four `01_MUST_HAVE` and all four `02_SHOULD_HAVE` prompt-pack tasks are
complete; per-task evidence is in `docs/should-have/PROGRESS.md`,
`PROJECT_COMPLETION_REPORT.md` §16 and `CONTINUE_PROMPT.md`. Deferred or partial
work is listed in `ROADMAP.md`. Notable gaps: a larger real-scan OCR corpus,
macOS/Linux packaging, code signing, an interactive screen-reader pass (the audit
itself is done), OCR cancellation/stale-run recovery and account-level AI billing
verification. A desktop E2E smoke suite is available (`npm run smoke:desktop`;
see section 11).

## 7. OCR details

- Engine: bundled Tesseract 5.4.0.20240606 with `eng`, `mya`, `osd`.
- Runner: `backend/app/services/ocr.py`, bounded worker pool, timeout, max image
  edge, no network.
- Page segmentation: user-selectable Tesseract PSM 3 (automatic), 4 (single
  column), 6 (single block) or 11 (sparse text). Unsupported values are rejected
  with `ocr_invalid_segmentation_mode`; they are never silently replaced.
- Burmese default: a language set containing `mya` preselects sparse text (11),
  because automatic layout merges Burmese rows.
- Paragraph reconstruction: stored blocks keep word boxes and one normalised
  line rectangle per text line. `_parse_tsv` splits a block that Tesseract
  merged across two prose columns only when both sides are prose-like; real
  table grids stay whole. At insertion, `apps/web/src/lib/ocr-reconstruction.ts`
  joins wrapped lines and continuation blocks by column, spacing, indentation
  and sentence continuation, keeps columns separate, and emits heading, list,
  paragraph and verbatim table/equation nodes. It never rewrites characters.
  `apps/web/src/test/ocr-reconstruction-fixtures.test.ts` locks the same
  document for real PSM 3 and PSM 11 output.
- Benchmark: `backend/app/ocr_benchmark.py` with two committed corpora:
  `backend/tests/fixtures/ocr-synthetic/` (regression baseline) and
  `backend/tests/fixtures/ocr-real/` (three public-domain scans with transcripts
  typed from the page). Run with `python -m app.ocr_benchmark --help`. Results
  and caveats are in `docs/ocr-benchmark.md`.
- Measured baseline: synthetic pages at PSM 11 give usable English and Burmese
  results; Burmese PSM 3 scored 85.60% CER versus 5.56% at PSM 11. Real scans at
  PSM 11 give 0.47% CER on English prose, 22.43% on a printed statistical table
  and 36.77% on an English/Burmese page (22.64% overall); automatic layout gives
  42.00% overall. The table and mixed figures measure reconstruction (separators,
  leaders, reading order) as much as recognition. The corpus is three pages from
  one transcriber with no scored Burmese-only case: it is evidence about this
  adapter, not a population estimate.
- Practical-file check (27 November 2026): normal development-workflow import
  verified 8 PDF pages and 5 attached JPG scans in one project. PDF embedded
  text, source rendering, Burmese schedule OCR, mixed-script OCR, editing,
  autosave/reopen and plain-text export were exercised. The schedule retained
  recognizable Burmese table structure but required date/number and low-
  confidence block corrections; the photographed mixed-script/handwriting page
  was also suitable only as an unverified OCR proposal. No source file or
  application code change was required. Details are in `PROGRESS.md`.

## 8. AI / BYOK details

- Providers: local Ollama, a custom OpenAI-compatible endpoint, and OpenAI,
  Anthropic, Google Gemini, OpenRouter, Groq, Mistral, DeepSeek, xAI, Together,
  Fireworks, Cerebras and Perplexity.
- `GET /api/ai/providers` is the source of truth; the frontend does not hardcode
  models. Discovery uses the user's key; providers without a listing endpoint
  allow manual model ids.
- Keys are write-only: encrypted with Fernet in `secrets/ai_keys.enc`, returned
  only as metadata, never logged, exported or written to the database.
- Task routes: `ocr_cleanup`, `region_proposals`, `equation_transcription`,
  `table_structure` and `default`, each with an optional fallback, temperature,
  timeout and 24-hour request limit.
- Rotation strategies: `priority`, `failover`, `round_robin`, `least_recent`,
  `least_usage`. Disabled/failed/cooling keys are skipped; `max_attempts` bounds
  requests; 429 triggers a cooldown; 401/403 fails the key.
- Remote endpoints require HTTPS (HTTP only for loopback), reject embedded
  credentials and metadata hosts, do not follow redirects, and require explicit
  remote consent. Paid routes require a one-action approval before sending.
- Usage ledger stores metadata only (provider, model, task, tokens, reported
  cost, outcome, timestamps). Prompts, images, crops, replies and document text
  are never stored there.

## 9. Configuration

Environment variables (see `.env.example`):

- `DOCUREBUILD_DATA_DIR`, `DOCUREBUILD_ENVIRONMENT`
- `DOCUREBUILD_API_TOKEN` (desktop only; unset in development/tests)
- `DOCUREBUILD_WEB_DIST` (desktop only; serves the SPA)
- `DOCUREBUILD_LOG_DIR` (desktop only)
- `DOCUREBUILD_TESSERACT_CMD`, `DOCUREBUILD_TESSDATA_DIR`
- `DOCUREBUILD_MAX_IMPORT_MB`, `DOCUREBUILD_MAX_UPLOAD_BATCH`,
  `DOCUREBUILD_MAX_BACKUP_MB`
- `DOCUREBUILD_PDF_RENDER_DPI`, `DOCUREBUILD_PDF_MAX_PAGES`,
  `DOCUREBUILD_PDF_FONT`
- `DOCUREBUILD_OCR_TIMEOUT_SECONDS`, `DOCUREBUILD_OCR_MAX_IMAGE_EDGE`
- `DOCUREBUILD_CORS_ORIGINS` (development only)
- `DOCUREBUILD_REPOSITORY_URL`
- `DOCUREBUILD_DEVTOOLS=1` (desktop development only)

AI credentials are configured in the application, not in environment files.

## 10. Important decisions and why

1. **Electron + Python sidecar, not Tauri.** The originally preferred Tauri shell
   required a Rust/MSVC toolchain that was not available in the build
   environment. Electron is heavier but reliably packages the Python sidecar and
   was approved. The installer size limitation is documented rather than hidden.
2. **Same-origin SPA served by the sidecar.** Avoids a CORS exception and keeps
   the loopback token meaningful. The renderer never talks to a second origin.
3. **Per-launch bearer token.** The backend must not be usable by other local
   processes or a browser tab. The token is generated in memory, passed by
   environment and exposed only through a narrow preload bridge.
4. **Bundled Tesseract.** Windows users should not install OCR separately. The
   build extracts the official UB-Mannheim installer without admin rights and
   ships only the engine, DLLs and `eng`/`mya`/`osd` data.
5. **Data-preserving uninstall.** `deleteAppDataOnUninstall: false`; projects are
   user data, not application cache.
6. **AGPL-3.0.** Required by the bundled PyMuPDF. Third-party notices are
   published and shipped in the installer.
7. **Synthetic plus real-scan OCR fixtures.** Synthetic pages stay the
   reproducible regression baseline because they remove scanning variables.
   Accuracy claims about paper come from `backend/tests/fixtures/ocr-real/`
   instead: three public-domain scans with transcripts typed from the page and a
   documented single-transcriber caveat. Synthetic numbers are never presented as
   real-world accuracy, and no reference transcript is generated by OCR.
8. **Mobile removed.** The 1.0 workspace is desktop-only. The segmented mobile
   panel switch, breakpoint hooks and camera/PWA concepts were removed rather
   than left as dead or misleading UI.
9. **No hidden AI spend.** Paid routes require explicit approval; free/local
   providers are the default path; the core app never calls AI automatically.
10. **Contrast fixed in tokens, not deferred.** The palette was adjusted until
    every checked pair reaches WCAG AA, guarded by a test.
11. **Native inputs behind themed controls.** `Checkbox`, `Switch` and `Radio`
    wrap real `<input>` elements and draw only the visual layer with tokens. This
    keeps labels, keyboard support, form semantics and testing roles real, and
    avoids a second implementation that could drift from the native behaviour.
12. **A dialog owns its working state while open.** Dialog-local edits are
    initialised on open and reset on close; a page cache write from a save must
    never re-initialise an open dialog. The Edit Image dialog keeps the preview
    node mounted, debounces expensive renders, and serialises commits so the last
    confirmed render always matches the newest local adjustment.
13. **Desktop accessibility is evidence-based.** The supported desktop shell
    provides a skip link and main landmark, and formatting controls are exposed
    as a labelled toolbar. Component tests cover native control roles and dialog
    Escape/restoration; contrast remains token-guarded. An installed-app
    keyboard or NVDA/Narrator result is recorded only after it is actually run,
    never inferred from component primitives.
14. **Imports are serialised per project.** Page numbers are allocated from the
    highest existing page, so two concurrent import jobs in one project used to
    read the same starting number and fail on the `pages.page_number` unique
    index. `pages.import_uploads()` holds a per-project lock for the whole
    import; different projects still import in parallel. Do not remove the lock
    without replacing page-number allocation with an atomic equivalent.
15. **PDF documents are closed through `pdf.close_document()`.** PyMuPDF keeps
    native buffers for closed documents in a process-wide store. The measured
    effect was ~19 MB of committed memory per import. The helper closes the
    document and calls `TOOLS.store_shrink(100)`; imports, re-renders, artwork
    and table analysis, and PDF export all use it. New PDF code must do the
    same instead of calling `document.close()` directly.
16. **Region proposals stay derived and non-persisted.** Region suggestions are
    recomputed on demand from the latest successful OCR run plus the current
    source asset, rotation and saved elements (`regions.propose_regions`). A
    proposal is returned only when the run's `source_asset_id`/`rotation` match
    the page, otherwise the endpoint reports `ocr_stale`; a source edit or
    rotation rebuilds the display asset and invalidates the run. This makes stale
    geometry structurally impossible and avoids a second source of truth that
    could diverge. Accepted regions are already persisted as `elements` (with
    their own `source_asset_id` stale flag); dismissed regions are cheap to
    re-derive. The optional batch-review task was evaluated on 2026-11-28 and
    deliberately did **not** add a proposal table. If cross-page review is later
    approved, start with a read-only derived aggregation that reuses
    `propose_regions` and carries the same `ocr_run_id` + `source_asset_id` +
    `rotation` identity; persist only user dismissals if demand is proven. Full
    design and the invariants any persistence must keep: `docs/optional-future/PROGRESS.md`.
17. **Provider quota is report-only until a verified, key-compatible feature is
    approved.** The optional task was evaluated on 2026-11-28 and deliberately
    added no provider calls. Verified official endpoints exist only for OpenAI
    and Anthropic (both need an admin/analytics key, not the normal project key),
    OpenRouter (management key for credits; the normal key for per-key limits)
    and DeepSeek (balance with the normal key). Gemini and the remaining
    providers have no verified simple per-key usage API, and scraping dashboards
    or inferring quota from incomplete history is forbidden. Any future feature
    must be user-triggered, use the user's own key, label data as
    **provider-reported**, **local estimate** or **unavailable**, and degrade to
    "unavailable" on error. Full matrix: `docs/optional-future/PROGRESS.md`.
18. **macOS/Linux remain out of scope; feasibility is documented, not built.** A
    study on 2026-11-28 recorded the blockers: only a Windows NSIS target exists,
    `prepare-tesseract.mjs` is Windows-only, `main.cjs` hardcodes `tesseract.exe`
    and `icon.ico`, POSIX shutdown lacks process-group handling, PyInstaller does
    not cross-compile (needs a CI matrix), the packaged data path would diverge
    from `platformdirs` on macOS/Linux, and macOS needs signing/notarization.
    Nothing is implemented until the owner approves a platform scope change.
19. **Chromium locales are trimmed; Tesseract slimming is still open.** The
    packaged build sets `electronLanguages: ["en-US"]`, keeping one Chromium
    locale instead of 55. This is safe because Electron's native UI is English
    and the app's English/Burmese UI plus the `eng`/`mya`/`osd` OCR data come from
    the web bundle and bundled Tesseract. A full `npm run desktop:dist` rebuild
    and the 12/12 `npm run smoke:desktop` suite verified the change: installer
    204.19 -> 195.92 MB, installed 646.64 -> 598.39 MB, locales 48.82 -> 0.56 MB.
    The installer shrinks less than the installed footprint because the dropped
    files compress well in the NSIS payload. The build is unreleased; the
    published 1.1.1 asset is unchanged. A slimmer Tesseract build (178.10 MB) is
    deferred until a compatible build can be benchmarked and smoke-tested.
    Details: `docs/optional-future/PROGRESS.md`.

## 11. Verification commands and current results

```powershell
backend/.venv/Scripts/python -m pytest backend/tests -q   # 452 passed
npm run test:web                                          # 364 tests / 59 files
npm run typecheck                                         # clean
npm run lint                                              # clean
npm run build                                             # production build
npm run smoke:desktop                                     # desktop E2E smoke (needs a packaged build)
```

`npm run smoke:desktop` drives the packaged `dist/desktop-installer/win-unpacked`
build over the DevTools protocol with a disposable data profile. It covers
launch/sidecar → create project → import PDF → render → OCR/review/insert →
edit/save/reopen → export → backup/restore → clean shutdown, and exits non-zero
on failure with a JSON report (`docs/smoke/desktop-smoke.json`, ignored). It
requires Node 22+ (global `WebSocket`).

Installed-build QA (1.0.0, Windows 11 x64, N100/16 GB) is recorded in
`PROJECT_COMPLETION_REPORT.md`: install/uninstall/reinstall with data retention,
8 existing projects rendered with no console errors, PDF import, OCR (English
96.4% confidence; Burmese PSM 11 82.3%), DOCX/PDF/Markdown/TXT export, vault
backup/restore with an MD5 check, token/401 checks, traversal and zip-slip
rejection, encrypted-backup password handling, performance measurements and a
secret scan.

## 12. Known limitations

- Windows x64 only; no macOS/Linux package, no code-signing certificate.
- Installer ~196 MB, installed footprint ~598 MB in the unreleased
  locale-trimmed build; the published 1.1.1 asset is ~204 MB / ~650 MB. Tesseract
  (178.10 MB) dominates the remaining size; a slimmer build is deferred.
- OCR accuracy is measured on synthetic pages and a three-page real-scan corpus;
  the latter has one transcriber, no scored Burmese-only case and is not a
  population estimate.
- Some OMML edge cases remain incomplete. Opaque PDF artwork is proposed from
  the rendered page at low confidence only when no exact PDF geometry exists, so
  a mixed page may still need manual selection. A nested table drawn inside a
  parent cell is linked as a separate table because the editor has no
  nested-table node; OCR word-box nesting without drawn rules stays a manual
  crop.
- Cloud AI depends on user keys and provider terms; quotas, prices and model
  availability are not guaranteed, and the app does not verify account billing.
- ✅ Automated desktop E2E smoke suite completed 28 November 2026: `npm run smoke:desktop`
  exercises launch/sidecar → create project → import PDF → render → OCR/review/insert
  → edit/save/reopen → export (MD/TXT/DOCX/PDF) → backup/restore → clean shutdown
  with sidecar stop verification. Uses disposable profiles, deterministic CDP-driven
  steps, JSON report at `docs/smoke/desktop-smoke.json`.
- Keyboard-only and screen-reader testing remain open.
- One low-severity KaTeX advisory (prototype pollution through `trust`) is
  accepted: the app renders only user-authored equations with `trust: false`.
- SQLite must not live on a network share.
- `app.db` stores **absolute** project directory paths. Copying the data folder
  does not relocate the projects, and the app refuses to delete a folder that
  resolves outside the active data folder (`project_storage_outside_data_dir`).
  For destructive verification, start the app with `DOCUREBUILD_DATA_DIR`
  pointing at an empty folder and create projects inside it; never test delete or
  factory reset against a copy of real data.
- The local vault is plaintext by design; only explicit downloads can be
  password-encrypted, and a forgotten password cannot be recovered.
- OCR has no cancel action, and an OCR run interrupted by a process crash stays
  `running` after restart. Import jobs are recovered as `import_interrupted`;
  OCR needs equivalent stale-state recovery. A crash during OCR also leaves one
  preparation PNG in `tmp/`, and a crash mid-import can leave one unreferenced
  processed image from the in-flight page. See `docs/performance.md`.

## 13. Release state

- Version 1.1.1 everywhere. License AGPL-3.0-or-later.
- Working tree after the release: `main` contains the four `02_SHOULD_HAVE`
  commits, the quick-win audit, the optional evaluations and the verified locale
  trimming on top of v1.1.1. Current suite: 452 backend / 364 web tests. The
  locale-trimmed installer (195.92 MB, SHA-256
  `BABE4B5949BF996701BC5BD3FB6F707D59FA33D1746B7E2E7FF4839ED484F649`) is
  **unreleased** and must not be published as 1.1.1; a future version should
  carry it. See `CONTINUE_PROMPT.md` for the next task.
- Repository: <https://github.com/minkhantthu2692-gif/DocuRebuild>
- Current release: <https://github.com/minkhantthu2692-gif/DocuRebuild/releases/tag/v1.1.1>,
  published 28 November 2026 from tag `v1.1.1` at commit `486688e`, and marked
  latest.
- 1.1.1 installer asset:
  <https://github.com/minkhantthu2692-gif/DocuRebuild/releases/download/v1.1.1/DocuRebuild-1.1.1-setup.exe>,
  214,103,864 bytes (204.19 MB), SHA-256
  `9CC17F7EDF0138A7FC452844C89B0F2EC653970258F3888A661AB3773FAC13CB`, built on
  28 November 2026 from the post-1.1.0 quality tree. The published asset was
  re-downloaded anonymously: same size and SHA-256; the packaged build passed the
  12/12 desktop E2E smoke suite in 13 s.
- 1.1.1 adds the post-1.1.0 quality work: bounded PDF memory and per-project
  import serialisation, a real-scan OCR baseline (`docs/ocr-benchmark.md`), an
  accessibility audit, a large-document performance/cancellation drill
  (`docs/performance.md`), and the automated desktop E2E smoke suite
  (`npm run smoke:desktop`). No schema migration.
- 1.1.0 history: tag `v1.1.0` at commit `a8baa1b`, published 26 November 2026;
  installer `DocuRebuild-1.1.0-setup.exe`, 214,082,110 bytes, SHA-256
  `EC1DF483F539A0DE40DD862A820FD653E1C406AE12921B58D9B5069131A325F4`. It added
  document typography and layout-aware OCR insertion; 437 backend and 356 web
  tests passed.
- 1.0.2 history: tag `v1.0.2` at commit `dae6ffd`, published 24 November 2026;
  installer `DocuRebuild-1.0.2-setup.exe`, 211,540,824 bytes, SHA-256
  `E501B0427371ED64B185A56E67089945896B417C9B19057130802455A1A03F47`, downloaded
  anonymously and verified. It unified checkboxes, switches and radios behind
  shared themed primitives and made Edit Image apply adjustments in place.
- 1.0.1 history: tag `v1.0.1` at commit `a6ca946`, published 23 November 2026;
  installer `DocuRebuild-1.0.1-setup.exe`, 211,539,463 bytes, SHA-256
  `9729E2116DA4E2790314BF687A0AD2D81E70F1ABE18D9D7A246892145E9B5792`, downloaded
  anonymously and verified. It fixed image loading in the installed build and
  added the typed-confirmation factory reset, dashboard bulk delete and the
  outside-data-folder delete guard.
- The installer is built locally and uploaded as a GitHub Release asset; it is
  deliberately not committed to Git.
- 1.0.0 history: <https://github.com/minkhantthu2692-gif/DocuRebuild/releases/tag/v1.0.0>,
  published 22 November 2026 from tag `v1.0.0` at commit `0a7af7f`; asset
  `DocuRebuild-1.0.0-setup.exe`, 211,528,811 bytes, SHA-256
  `7B444BF2B996C8EC1B4699D3C438747718D2DC665CDE0CFF31368311BB14A46C`,
  downloaded anonymously and verified on 22 November 2026.
- 1.0.0 rebuild verification: silent install exits 0 in 34 s; the installed app
  opens, lists the 7 existing projects, exposes a 64-character preload token,
  reports `1.0.0` in the status bar and passes the 12-point UI check with no
  console errors; the packaged sidecar passed a 61-check drill covering auth,
  OCR, export, backup/restore and vault restore.
- Fresh-clone verification: a shallow clone of `db44b44` ran `npm ci`, 290 web
  tests in 47 files, typecheck, lint, the production build, and 414 backend tests
  in 241 s, all clean, on 22 November 2026.

## 14. Handover checklist for the next agent

1. Read `AGENTS.md`, `CONTINUE_PROMPT.md`, this file, `ROADMAP.md` and
   `CHANGELOG.md`; use the paste-ready prompt in `CONTINUE_PROMPT.md` for a new
   chat and run only one remaining task per session.
2. Run `git status -sb` and `git log --oneline -10`; do not discard unfamiliar
   work.
3. Run the checks in section 11 before changing behaviour.
4. Make the smallest coherent change; update tests and both locale files.
5. Update `CHANGELOG.md` for user-visible changes and this file / `ROADMAP.md`
   for status or architectural changes.
6. Never commit user data, `dist/`, `.env` files, databases or credentials.
7. Do not publish a release without rebuilding, smoke testing and verifying the
   uploaded checksum.
