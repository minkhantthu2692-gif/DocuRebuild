# Progress log - 2026-11-27

## Large-document performance and cancellation - 2026-11-27

### Scope and environment

Exercised the installed-equivalent Windows x64 build: the packaged Electron
shell from `dist/desktop-installer/win-unpacked` plus a
`docurebuild-backend.exe` rebuilt from this working tree with
`backend/pyinstaller.spec`. Tested base commit `69ca683` plus the two fixes
below.

- Windows 11 (10.0.26300), x64
- Intel N100, 4 logical cores, 15.7 GB RAM
- Python 3.12.10, bundled Tesseract 5.4 (`eng`), PyMuPDF 1.28.2
- Disposable projects under `%TEMP%\docurebuild-perf-*` and
  `%TEMP%\docurebuild-editor-*`; deleted after the run. No real project was
  opened or changed.

Full methodology, tables and reproduction commands: `docs/performance.md`.
Raw measurements: `docs/performance/sidecar-drill.json` and
`docs/performance/editor-drill.json`.

### Results

- Import stayed linear from 10 to 400 raster PDF pages: 0.259-0.267 s/page,
  400 pages in 106.7 s, peak sidecar working set 197 MB, 355 MB project storage.
  Serving a stored 150 DPI page took 15-17 ms.
- OCR of pages 0/200/399 of the 400-page project took 2.26-2.48 s each at
  96.1-96.2 mean confidence; no temp files or Tesseract children remained.
- A 1,015,143-character document saved in 0.17 s, read in 0.04 s and exported to
  PDF in 0.95 s. In the packaged editor, 144,753 typed characters took 4.70 s
  (median 37 ms per 1,200-character input, p95 60 ms, longest 75 ms), autosave
  persisted 0.99 s after the last input, and a full reload restored the text in
  0.57 s.
- Ten consecutive 10-page imports stayed between 156.5 MB and 158.8 MB, and the
  whole 1-400-page sequence returned to 154.5-157.2 MB after each import.
- Three repeated cancellations of a 400-page import reached the `cancelled`
  state in 0.14-0.27 s, rolled the in-flight PDF back to zero pages/files, left
  no temp files and left the project usable (a 20-page import then succeeded).
- Two 50-page jobs ran together: one cancelled, one succeeded with 50 pages.
- A hard kill after 3 committed pages of a 200-page import produced a
  `failed`/`import_interrupted` job after restart, kept the 3 pages, left no temp
  upload, and the next import succeeded (23 pages total).
- Closing the editor window exited the shell in 3.35 s with no remaining shell,
  backend or Tesseract processes. Stopping the sidecar during OCR also left no
  child processes.

### Fixes (measured, not speculative)

1. **Unbounded sidecar memory from PDF imports/exports.** PyMuPDF retained native
   buffers for closed documents in its process-wide store. Before the fix the
   drill grew from 149.8 MB idle to 235.9 MB after the 400-page import, and
   repeated 10-page imports added about 19 MB each. `app.services.pdf` now
   exposes `close_document()`/`release_store()` and every PDF close (import,
   re-render, artwork/table analysis, PDF export) releases the store. Memory is
   now flat across ten imports.
2. **Concurrent imports in one project failed.** Two jobs allocated the same
   page number and the second failed with
   `UNIQUE constraint failed: pages.page_number`. Imports are now serialised per
   project directory; different projects still run in parallel. Regression test
   added in `backend/tests/test_import_jobs.py`.

### Commands and results

```text
backend/.venv/Scripts/python.exe -m pytest tests -q
439 passed, 1 third-party deprecation warning, 386.74 s

backend/.venv/Scripts/python.exe scripts/performance-drill.py \
  --sidecar dist/desktop/backend/docurebuild-backend.exe \
  --sizes 1,10,50,200,400 --cancel-pages 400 --queue-pages 50 \
  --recovery-pages 200 --ocr-samples 3 --memory-repeats 10 \
  --out docs/performance/sidecar-drill.json
completed; see the JSON for every import, cancellation, queue and recovery record

node scripts/performance-editor-drill.mjs --out docs/performance/editor-drill.json
completed; shell/backend/Tesseract processes: 0 after window close
```

The packaged sidecar was rebuilt with:

```text
cd backend
.venv/Scripts/python.exe -m PyInstaller pyinstaller.spec --noconfirm --clean \
  --log-level WARN --distpath ../dist/desktop --workpath build/pyinstaller
```

### Remaining issues / unverified items

- A hard kill during import can leave one unreferenced processed PNG from the
  in-flight page. Page rows and assets stay consistent, and the next import
  succeeds; no startup sweep was added.
- OCR has no cancel action, and an OCR run interrupted by a crash remains
  `running` after restart (imports are recovered as interrupted). A crashed OCR
  preparation leaves one PNG in `tmp/`.
- Only 400 of the configured 1,000-page maximum was measured, on one N100/16 GB
  machine. Low-memory machines, network drives and GPU/thermal differences were
  not profiled.
- Typing used direct CDP text insertion, not a physical keyboard, IME or Burmese
  shaping.
- The Electron drill used `win-unpacked` with
  `DOCUREBUILD_DESKTOP_RESOURCES=dist/desktop`; the NSIS package was not
  reinstalled for this task.

### Files changed

- `backend/app/services/pdf.py`, `pages.py`, `regions.py`, `table_structure.py`,
  `document_export.py` (store release and per-project import serialisation)
- `backend/tests/test_import_jobs.py` (concurrency regression test)
- `scripts/performance-drill.py`, `scripts/performance-editor-drill.mjs` (new)
- `docs/performance.md`, `docs/performance/*.json` (new report and raw data)
- `PROGRESS.md`, `ROADMAP.md`, `PROJECT_MEMORY.md`, `CHANGELOG.md`,
  `PROJECT_COMPLETION_REPORT.md` (status and evidence)

## Installed-app accessibility audit - 2026-11-27

### Environment

- Windows: Microsoft Windows NT 10.0.26300.0
- Architecture: Windows x64
- Node: v24.21.0
- npm: 12.2.0
- Python: 3.12.10
- Installed executable:
  `C:\Users\minkh\AppData\Local\Programs\DocuRebuild\DocuRebuild.exe`
- Installed executable size: 238.4 MB
- Tested commit: 69ca683
- NVDA: unavailable/not running
- Windows Narrator: unavailable/not running

The installed executable was launched successfully and remained visible as
`DocuRebuild`; no browser automation or screen-reader tooling was available for
a reliable keyboard-only or assistive-technology journey.

### Desktop journey matrix

| Journey | Automated evidence | Installed-app manual status |
| --- | --- | --- |
| Open/create project | Dialog and routing tests; create dialog accepts labelled inputs | Not manually completed |
| Import | Existing source-panel/import tests | Not manually completed |
| Page navigation | Existing source thumbnail and workspace tests | Not manually completed |
| OCR review | Existing OCR/table review tests | Not manually completed |
| Edit | Form-control and localization tests | Not manually completed |
| Save/reopen | Existing document and revision tests | Not manually completed |
| Export | Existing download/export tests | Not manually completed |
| Tab/Shift+Tab and visible focus | Radix and native-control primitives; not a full desktop pass | Not manually completed |
| Escape/dialog focus trapping/restoration | Added automated dialog Escape/restoration test | Not screen-reader verified |
| Keyboard activation/menu state | Native controls plus Radix menus; existing tests | Not manually completed |
| NVDA/Narrator pass | Not available | Blocked by unavailable tooling |

### Confirmed fixes

- Added a visible-on-focus skip link and `main` landmark target so keyboard users
  can bypass repeated header controls.
- Added `role="toolbar"` and the localized accessible name "Editor toolbar"
  (Burmese equivalent included) to the editor formatting controls.
- Added `accessibility.test.tsx` covering the skip link/main landmark and
  Radix dialog Escape dismissal with trigger-focus restoration.
- Existing native `Checkbox`, `Switch` and `Radio` controls retain native
  keyboard/form semantics and labelled roles; this is covered by
  `form-controls.test.tsx`.

### Commands and results

```text
npm run test -w @docurebuild/web -- src/test/accessibility.test.tsx src/test/form-controls.test.tsx src/test/i18n.test.ts
3 test files passed, 19 tests passed

npm run typecheck
passed

npm run lint
passed
```

No full WCAG conformance, keyboard certification or screen-reader certification
is claimed. The remaining installed-app keyboard and NVDA/Narrator steps require
an interactive Windows session with those tools and disposable test projects.

Tested commit: `8cb208c` (the repository is currently on `main` at that commit).

## Automated desktop E2E smoke suite - 2026-11-28

### Scope

Implemented and verified a repeatable one-command smoke suite for the shipped
Windows x64 Electron app (`npm run smoke:desktop`). The suite exercises the
complete user journey against the packaged `dist/desktop-installer/win-unpacked`
build:

1. Launch the Electron shell and wait for the bundled Python sidecar to become
   healthy (token-authenticated `/api/health`).
2. Create a project via the API.
3. Navigate the workspace and verify the editor and import input are present.
4. Import a small generated PDF through the UI (file input + change event).
5. Verify source page rendering (full image + thumbnail).
6. Run OCR with the bundled Tesseract engine, mark all blocks reviewed.
7. Open the OCR review dialog and insert the verified text into the editor.
8. Edit the document (append a unique marker), wait for autosave persistence.
9. Reload the page and confirm the marker is restored.
10. Export the document as Markdown, TXT, DOCX and PDF; validate content and
    format magic bytes.
11. Back up the project (ZIP), restore into a new project, verify pages and
    document text survive.
12. Close the app via CDP and verify the Electron process and the backend
    sidecar both stop.

### Results

- **One-command execution**: `npm run smoke:desktop` (defaults to the local
  unpacked build; `--app` overrides for an installed executable).
- **Deterministic disposable profiles**: The suite creates an isolated temporary
  directory tree (`%TEMP%\docurebuild-smoke-*`) for `APPDATA`, `LOCALAPPDATA`,
  `TEMP`, and `DOCUREBUILD_DATA_DIR`. It never touches the user's real data.
  On pass, the tree is deleted automatically; `--keep` retains it for inspection.
- **Useful diagnostics**: The JSON report (`docs/smoke/desktop-smoke.json`)
  includes per-step timings, health/engine versions, OCR block counts and
  confidence, export sizes, sidecar PIDs, console errors, uncaught exceptions,
  backend/electron log tails, and a failure screenshot when a step fails.
- **Clean shutdown verified**: The final step enumerates the sidecar PIDs before
  closing, then polls until they are gone. Runs stopped sidecar PIDs within 2
  seconds each.
- **Shutdown-step robustness fix**: an initial run failed intermittently at the
  final step with `DevTools connection closed`. Closing the window tears down
  the DevTools socket, so the in-flight `window.close()` evaluation can reject
  with a connection-closed error — the expected result of a successful close.
  The step now tolerates `DevTools connection closed` / `not open` for that one
  call and relies on `waitForChildExit` plus the sidecar PID poll as the real
  assertion. Three consecutive runs passed after the fix.
- **CI-friendly**: No external services, no paid APIs, no hardcoded paths. The
  suite requires Node 22+ (global `WebSocket`) and the packaged desktop payload.
  Total runtime ~12 seconds on the reference machine (Intel N100, 16 GB RAM).

### Commands and results

```text
npm run smoke:desktop
[smoke] pass launch and authenticate
[smoke] pass create project
[smoke] pass open workspace
[smoke] pass import PDF through the UI
[smoke] pass render source page
[smoke] pass run OCR and mark blocks reviewed
[smoke] pass review and insert OCR in the dialog
[smoke] pass edit and autosave
[smoke] pass reopen and restore saved text
[smoke] pass export Markdown, text, Word and PDF
[smoke] pass back up and restore into a new project
[smoke] pass close the app and stop the sidecar
[smoke] report docs/smoke/desktop-smoke.json
[smoke] passed in 12s
```

Three consecutive runs after the shutdown-step fix all passed in ~12 s each.

### Files changed

- `scripts/desktop-smoke.mjs` (pre-existing suite; verified end-to-end against
  the packaged build and hardened the shutdown step against the expected
  DevTools connection-close race)
- `docs/smoke/desktop-smoke.json` (run artifact, git-ignored)
- `ROADMAP.md` (updated "Desktop end-to-end automation" to ✅ Completed)
- `CHANGELOG.md` (Unreleased → Verified)
- `PROJECT_COMPLETION_REPORT.md` (section 15)
- `PROJECT_MEMORY.md` (limitations updated)
- `PROGRESS.md` (this entry)

### Limitations

- The test uses a generated single-page PDF fixture; it does not exercise
  multi-page imports, image imports, table/figure/equation workflows or AI
  features.
- It drives the UI via CDP and the preload bridge token; it does not test
  native OS-level keyboard shortcuts, menu items or system dialogs.
- The devtools WebSocket connection requires Node 22+ (global `WebSocket`);
  older runtimes will fail fast with a clear message.
- Only the unpacked `win-unpacked` layout was exercised; an installed NSIS
  executable can be targeted with `--app <path>` but was not re-verified in
  this session.

The acceptance criteria are met: a documented one-command smoke test
(`npm run smoke:desktop`), repeatable clean-profile pass, and CI integration
where supported (the script exits non-zero on failure and writes a JSON report).

## Real File Practical Check - 2026-11-27

### Files tested

- `MET-51051 for exam.pdf`: 8 pages
- 5 attached JPG files:
  - `photo_2026-11-27_17-47-53.jpg`
  - `photo_2026-11-27_17-47-47.jpg`
  - `photo_2026-11-27_17-34-14.jpg`
  - `photo_2026-11-27_17-34-00.jpg`
  - `photo_2026-11-27_17-33-43.jpg`

The normal application import workflow created a test project and imported all 13
pages: 8 PDF pages and 5 image pages.

### Findings

- Page rendering worked for the PDF and image imports. Source thumbnails and the
  full source view showed the supplied pages correctly.
- Embedded PDF text on PDF page 1 was reasonably accurate and preserved the page
  headings, paragraphs, figure caption, and page number. It was presented as an
  editable OCR proposal and did not claim OCR confidence.
- The printed schedule image (page 10) rendered with usable Burmese text. Burmese
  OCR with sparse-text layout produced 49 text blocks and an average reported
  confidence of 71%. Most headings and longer Burmese labels were recognizable,
  but dates, numbers, and several low-confidence words contained OCR errors.
- The mixed English/Burmese open-book image (page 11) rendered, and English OCR
  ran successfully. It reported 56% average confidence; the handwritten margin
  notes and mixed scripts were not reliably recognized, so manual review is
  necessary.
- OCR results retained the unverified/source-note treatment and could be inserted
  into the editor.
- Editing, autosave, and reopen persistence were verified with a practical review
  note appended to the inserted schedule OCR text. The note remained in the
  document after a browser reload.
- The plain-text export API returned HTTP 200 and a 2,106-byte
  `Real-File-Practical-Check.txt` attachment containing the edited Burmese text
  and source note.

### Major layout and reading-order observations

- PDF text page 1 kept paragraph and heading structure recognizable.
- The schedule table was fragmented into individual OCR blocks rather than
  reconstructed as a single table. Reading order was mostly understandable, but
  dates and table rows require manual correction.
- Mixed English/Burmese handwriting and overlaid annotations produced poor or
  fragmented recognition. The source image remains more reliable than OCR for
  those areas.
- The PDF and images were not modified.

### Fixes

- No application code changes were needed for these files. The imported pages,
  OCR proposals, editing, persistence, and export output all worked without a
  reproducible application defect that could be corrected safely within this
  lightweight check.

### Remaining issues / unverified items

- OCR accuracy for handwritten annotations, mixed-script scans, dates, and dense
  table numbers should remain treated as manual-review work.
- The browser automation download event did not fire for the in-app plain-text
  export action. The server-side export itself was verified directly and returned
  HTTP 200. A desktop-build end-to-end browser download check remains pending.
- The initial project route returned the dashboard immediately after creation in
  development mode; direct navigation to the project route opened the workspace
  correctly. This was not changed because it was not reproducible enough to
  isolate from the development navigation/test setup.
