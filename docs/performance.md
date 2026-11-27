# Large-document performance and cancellation - 27 November 2026

This report closes **MUST HAVE 03** from `PROJECT_COMPLETION_REPORT.md`. It
measures the installed-equivalent Windows x64 application - the packaged
Electron shell and the PyInstaller Python sidecar, not the Vite/FastAPI
development servers - with progressively larger raster PDFs, a 145k-character
editor document, repeated cancellations, a simulated crash and shutdowns.

All projects, PDFs and settings were created in disposable temporary folders.
No real user project was opened, changed or deleted.

## Environment

| Item | Value |
| --- | --- |
| Machine | Intel N100, 4 logical cores, 15.7 GB RAM |
| OS | Windows 11 (build 10.0.26300), x64 |
| Python | 3.12.10 (backend virtual environment) |
| Shell | Packaged `DocuRebuild.exe` from `dist/desktop-installer/win-unpacked` (1.1.0) |
| Sidecar | `docurebuild-backend.exe` rebuilt from this working tree with `backend/pyinstaller.spec` |
| OCR | Bundled Tesseract 5.4, `eng` |
| Disposable data | `%TEMP%\docurebuild-perf-*` and `%TEMP%\docurebuild-editor-*`, removed after each run |
| Working tree | Base commit `69ca683` plus the two fixes recorded below |
| Lighting / power | Plugged in, normal Windows power plan; no other heavy work was running |

The only backend/runtime changes present while measuring are the two fixes
described below. Measurement scripts:

- `scripts/performance-drill.py` - sidecar API drill.
- `scripts/performance-editor-drill.mjs` - Electron editor drill over the
  DevTools protocol.

Raw evidence:

- `docs/performance/sidecar-drill.json`
- `docs/performance/editor-drill.json`

## Method

The sidecar drill starts the packaged executable with
`DOCUREBUILD_API_TOKEN`, a disposable `DOCUREBUILD_DATA_DIR` and the bundled
Tesseract paths, then uses the same authenticated HTTP API as the renderer. It
creates one project per PDF size, uploads a generated raster-only PDF through
`POST /api/projects/{id}/imports`, polls the job every 100 ms and samples the
sidecar working set every 100 ms from Windows process counters. Import time
includes the HTTP upload and every per-page commit.

Fixtures are 150 DPI US Letter pages rendered to JPEG and embedded in a PDF with
PyMuPDF, so they have no text layer and exercise PDF rendering, PNG display-copy
writing, thumbnail generation and the database commit path. The pages are
deliberately text-dense (roughly 900 KB PNG per page), which makes the per-page
figure conservative compared with a sparsely printed scan.

The editor drill launches the packaged shell with isolated `APPDATA`,
`LOCALAPPDATA` and project data, obtains the preload token from the page,
creates a project through the real API, opens the workspace, and inserts
120 chunks of 1,200 characters through CDP `Input.insertText`. Each chunk's
latency is measured from the protocol call until the editor DOM reflects the
text. Autosave is observed by polling the document endpoint, reopen by a full
page reload, and shutdown by closing the window and counting processes.

## Startup and idle

| Measurement | Result |
| --- | --- |
| Sidecar cold start to healthy `/api/health` | 3.43 s |
| Sidecar idle working set | 149.8 MB |
| Electron spawn to loaded page with preload token | 4.00 s |
| Project route to editable workspace | 0.50 s |
| Electron shell working set at start (4 processes) | 105 / 153 / 49 / 95 MB |
| Sidecar working set at editor start | 150.6 MB |

## Import and rendering

| Pages | Total | Per page | Peak working set | Working set 1 s after | Project storage |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.49 s | 0.494 s | 163.2 MB | 156.0 MB | 1.3 MB |
| 10 | 2.82 s | 0.282 s | 192.1 MB | 154.5 MB | 11.1 MB |
| 50 | 12.95 s | 0.259 s | 193.7 MB | 154.7 MB | 46.4 MB |
| 200 | 52.38 s | 0.262 s | 196.1 MB | 156.4 MB | 178.8 MB |
| 400 | 106.68 s | 0.267 s | 197.3 MB | 157.2 MB | 355.3 MB |

Per-page import time is flat from 10 to 400 pages (0.259-0.267 s), so there is
no page-count-dependent slowdown and no queue growth inside one import. A single
1-page import carries a fixed startup cost, which is why its per-page figure is
higher. Storage is dominated by the 150 DPI PNG display copy (~0.89 MB/page in
this deliberately dense fixture).

Rendering the stored display copy over the authenticated asset route took
15-17 ms for 0.89 MB pages at indexes 0, 200 and 399, so opening pages does not
re-read or re-render the PDF.

## Memory stability

Ten consecutive 10-page imports into the same project, sampled half a second
after each job:

| Repeat | Working set |
| --- | --- |
| 1 | 156.8 MB |
| 2 | 156.5 MB |
| 3 | 158.3 MB |
| 4 | 157.0 MB |
| 5 | 157.0 MB |
| 6 | 156.7 MB |
| 7 | 158.8 MB |
| 8 | 157.3 MB |
| 9 | 157.2 MB |
| 10 | 157.2 MB |

The working set stays within 2.3 MB of its starting point across ten imports
and across the 1-400-page sequence. The transient peak (197 MB) belongs to the
largest import and is released afterwards.

**Fixed defect: PyMuPDF store retention.** Before the fix, the same drill showed
the working set climbing from 149.8 MB to 235.9 MB after the 400-page import, and
repeated imports added roughly 19 MB each until the process reached ~445 MB. A
direct reproduction (open, render, close one PDF thirteen times) grew committed
memory from 48.9 MB to 103.1 MB, about 4.2 MB per cycle;
`pymupdf.TOOLS.store_shrink(100)` returned it to baseline. PyMuPDF 1.28.2 keeps native buffers for closed documents in its
process-wide store. `app.services.pdf.close_document()` now closes the document
and releases that store after imports, page re-rendering, PDF artwork/rule
analysis and PDF export.

## OCR

English pages at indexes 0, 200 and 399 of the 400-page project, automatic
segmentation (PSM 3):

| Page index | Time | Mean confidence | Blocks | Peak working set |
| --- | --- | --- | --- | --- |
| 0 | 2.38 s | 96.2 | 16 | 174.0 MB |
| 200 | 2.26 s | 96.2 | 16 | 174.1 MB |
| 399 | 2.48 s | 96.1 | 16 | 174.2 MB |

Idle working set after the OCR samples: 158.1 MB. OCR temporary files: none
left. Tesseract children after each run: none.

OCR is the dominant cost for a full book: ~2.4 s per page single-page runs means
about 16 minutes of CPU for 400 pages. The UI starts one run per page on demand
rather than a batch of 400; that behavior is unchanged by this task.

## Document save, reopen and export

Through the sidecar API, with Tiptap-shaped paragraphs:

| Document | Characters | Save | Read | Markdown | TXT | DOCX | PDF |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 300 paragraphs | 253,744 | 0.05 s | 0.02 s | 0.07 s | 0.02 s | 0.10 s | 0.24 s |
| 1,200 paragraphs | 1,015,143 | 0.17 s | 0.04 s | 0.12 s | 0.03 s | 0.37 s | 0.95 s |

PDF export in the editor drill (145k characters, 79 KB result) took 173 ms
including the renderer round trip; DOCX 95 ms and Markdown 57 ms. The editor's
reopen after a full page reload rendered the stored 144,753 characters in
0.57 s.

## Editor typing

| Measurement | Result |
| --- | --- |
| Inserted characters | 144,753 |
| Input chunks | 120 x 1,200 characters |
| Total measured input time | 4.70 s |
| Median per chunk | 37 ms |
| 95th percentile | 60 ms |
| Longest chunk | 75 ms |
| Editor characters after typing | 144,753 |
| Autosave after last input | 0.99 s (900 ms debounce + commit) |
| Stored characters after autosave | 144,753 |

Renderer JS heap grew from 10.5 MB to 35.1 MB while typing 145k characters, with
DOM nodes staying at 487. After the reload the heap was 46.2 MB with 957 nodes,
which reflects the newly mounted workspace, not a per-keystroke leak. Typing
latency stays well below a frame at the tested size and does not degrade as the
document grows within this range.

## Cancellation

A 400-page import was cancelled three times in the same project, then a 20-page
import succeeded in that project.

| Repeat | Progress at cancel | Cancel to terminal state | Final state | Pages kept | Files vs pages | Temp files |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 7 pages | 0.21 s | cancelled | 0 | consistent (0/0/0) | 0 |
| 2 | 7 pages | 0.14 s | cancelled | 0 | consistent (0/0/0) | 0 |
| 3 | 8 pages | 0.27 s | cancelled | 0 | consistent (0/0/0) | 0 |

Cancellation boundaries are per PDF file: the file being imported is rolled back
completely (the shared source PDF, its display copies and thumbnails), so a
single cancelled 400-page PDF leaves no partial pages. With a multi-file batch,
files that already completed are kept, matching the documented behavior. After
the three cancellations the project imported 20 pages normally and has exactly
20 page rows.

Queue check: two 50-page jobs were started together; the first was cancelled and
the second completed with 50 page rows. Before this task the second job failed
with `UNIQUE constraint failed: pages.page_number`.

**Fixed defect: concurrent imports collided on page numbers.** Both jobs read
the highest existing page number before either committed and then tried to
insert the same `page_number`. `app.services.pages.import_uploads()` now
serialises imports per project directory. Different projects still import in
parallel, and the per-page work inside one import is unchanged. A regression
test starts two 12-page jobs in one project and asserts 24 unique, contiguous
page numbers.

## Crash recovery

The sidecar was killed without a graceful shutdown after 3 pages of a 200-page
import had committed, then restarted on the same data folder.

| Check | Result |
| --- | --- |
| Job row after restart | `failed`, `import_interrupted` |
| Pages kept | 3 rows, 3 display files, 3 thumbnails |
| Temp uploads left | none |
| Import after restart | 20-page import succeeded; 23 total pages |
| Orphan sidecar process after kill | none |

The in-flight page had already written its display PNG but not its thumbnail or
page row, so the project folder contains one unreferenced processed image after
the hard kill. That is a bounded crash residue, not a data-loss path; the job,
page rows and remaining assets are consistent, and the next import succeeds.
Cleaning unreferenced processed/thumbnail files at startup is listed as a
follow-up rather than changed here.

## Shutdown and orphan processes

| Scenario | Result |
| --- | --- |
| Close the Electron window | Shell exited in 3.35 s; 0 shell, backend or Tesseract processes remained |
| Stop the sidecar during OCR | 0 Tesseract and 0 sidecar processes remained after 3 s |
| Stop the sidecar during import | No orphan worker processes (imports are threads) |
| End of entire drill | 0 `docurebuild-backend.exe`, 0 `tesseract.exe` |

Two non-process residues were observed during a hard shutdown rather than a
normal quit:

- One OCR preparation PNG remained in the data folder's `tmp/` directory,
  because the process could not run its `finally` cleanup. It is one file per
  interrupted OCR, not a growing queue in normal use.
- The interrupted OCR run row remains `status: running` after restart. Import
  jobs are recovered as interrupted, but OCR runs have no equivalent stale-state
  recovery, and OCR has no cancel action in the API or UI. This is recorded as an
  open reliability gap below; no OCR cancellation feature was added in this task.

## What changed

| File | Change |
| --- | --- |
| `backend/app/services/pdf.py` | `release_store()`/`close_document()` release PyMuPDF's native store after a PDF is closed |
| `backend/app/services/pages.py` | Per-project import lock; PDF close goes through `close_document()` |
| `backend/app/services/regions.py` | PDF close goes through `close_document()` |
| `backend/app/services/table_structure.py` | PDF close goes through `close_document()` |
| `backend/app/services/document_export.py` | PDF export closes the document and releases the store |
| `backend/tests/test_import_jobs.py` | Concurrent-import page-number regression test |
| `scripts/performance-drill.py` | Reproducible sidecar drill (added) |
| `scripts/performance-editor-drill.mjs` | Reproducible Electron editor drill (added) |

No behavior was changed to meet a target number. The two fixes remove a
correctness failure and an unbounded native-memory accumulation that the drill
measured; import/OCR throughput and output are otherwise unchanged.

## Remaining limitations

- Only the N100/16 GB reference machine was measured. Low-memory and
  many-core machines, a network drive and a 1,000-page (the configured maximum)
  import were not profiled.
- Import cost is dominated by rendering and PNG encoding; ~0.26 s/page means
  about 4.4 minutes for 1,000 dense pages. It scales linearly, so no hot spot was
  changed. Sparse scans are cheaper than this fixture.
- OCR is ~2.4 s per page and there is no batch-cancel or per-run cancel. A
  crash during OCR leaves the run row `running` and one preparation PNG in
  `tmp/`.
- A hard kill during import can leave one unreferenced processed image from the
  in-flight page. No startup sweep was added.
- Typing was measured with direct text insertion, not a real keyboard/IME or
  Burmese shaping, and only up to 145k characters.
- The drill uses the packaged shell from `win-unpacked` with
  `DOCUREBUILD_DESKTOP_RESOURCES` pointing at `dist/desktop`; it does not
  reinstall the NSIS package. The Electron and sidecar binaries are the same
  build inputs as the installer.
- No GPU acceleration comparison, battery/power-plan comparison or thermal
  throttling test was performed.

## Reproduction

```bash
# Rebuild the packaged sidecar from the current tree
cd backend
.venv/Scripts/python.exe -m PyInstaller pyinstaller.spec --noconfirm --clean \
  --log-level WARN --distpath ../dist/desktop --workpath build/pyinstaller

# Sidecar drill (about 4 minutes; disposable data under %TEMP%)
cd ..
backend/.venv/Scripts/python.exe scripts/performance-drill.py \
  --sidecar dist/desktop/backend/docurebuild-backend.exe \
  --sizes 1,10,50,200,400 --cancel-pages 400 --queue-pages 50 \
  --recovery-pages 200 --ocr-samples 3 --memory-repeats 10 \
  --out docs/performance/sidecar-drill.json

# Electron editor drill (requires a packaged win-unpacked shell)
node scripts/performance-editor-drill.mjs \
  --out docs/performance/editor-drill.json
```

Both scripts refuse to touch the default project data folder: the sidecar drill
always sets `DOCUREBUILD_DATA_DIR` to a new temporary directory, and the editor
drill also isolates `APPDATA` and `LOCALAPPDATA`. Pass `--keep` to inspect the
disposable folder; otherwise it is deleted.
