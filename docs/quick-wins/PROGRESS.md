# QUICK WINS task series — regression audit

Durable record for
`04_QUICK_WINS_AND_REGRESSION_CHECKS/01_Audit_Previously_Requested_Fixes.md`.
Read this with `AGENTS.md`, `CONTINUE_PROMPT.md` and `ROADMAP.md`.

Scope guard (unchanged): Windows x64 Electron + bundled Python sidecar,
local-first. No mobile/PWA/Tauri/camera/cloud/accounts/collaboration work.

Working rules applied: verified the current working tree rather than relying on
the v1.1.0 report, used only disposable data, implemented one task, made no
unrelated refactors, and did not publish a release or claim unverified results.

## Result

All seven earlier requests are **VERIFIED WORKING**. No confirmed defect was
found, so **no application, test or locale changes were made**, as the prompt
requires when everything passes. The only changes in the task commit are
documentation records.

| # | Earlier request | Classification | Code change |
| --- | --- | --- | --- |
| 1 | Source PDF/image/page-thumbnail rendering, including after restart | VERIFIED WORKING | none |
| 2 | Dialog stability: checkbox/filter/slider changes must not close, remount, flicker or reset dialogs | VERIFIED WORKING | none |
| 3 | Global checkbox/switch consistency and correct control semantics | VERIFIED WORKING | none |
| 4 | Factory reset with explicit irreversible confirmation; safe local data clearing without uninstalling | VERIFIED WORKING | none |
| 5 | Project multi-select and safe bulk deletion | VERIFIED WORKING | none |
| 6 | OCR-to-editor paragraph reconstruction preserving headings, lists, columns and boundaries | VERIFIED WORKING | none |
| 7 | Editor fonts, superscript/subscript and Justify, including save/reopen and DOCX/PDF export | VERIFIED WORKING | none |

## Baseline and focused verification

Baseline on the clean tree before the audit (branch `main`, HEAD `0ef502d`,
version `1.1.1`; no user files touched):

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests -q
npm run test:web
npm run typecheck
npm run lint
git status -sb
git log --oneline -10
```

Results: **450 backend tests passed** in 279.20 s (1 Starlette deprecation
warning); **59 web files / 364 tests passed** in 96.00 s; `tsc --noEmit` and
ESLint both clean; working tree clean before the documentation edits.

Focused re-run for the seven audited areas:

```powershell
npm run test -w @docurebuild/web -- src/test/form-controls.test.tsx src/test/document-layout-dialog.test.tsx src/test/settings-factory-reset.test.tsx src/test/dashboard-bulk-delete.test.tsx src/test/ocr-reconstruction.test.ts src/test/ocr-reconstruction-editor.test.ts src/test/ocr-reconstruction-fixtures.test.ts src/test/ocr-reconstruction-pdf.test.ts src/test/typography.test.ts src/test/accessibility.test.tsx
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_projects.py backend/tests/test_factory_reset.py backend/tests/test_desktop.py backend/tests/test_fonts.py backend/tests/test_docx_export.py backend/tests/test_pdf_export.py backend/tests/test_document_export.py -q
```

Results: **10 web files / 69 tests passed** in 17.89 s; **120 backend tests
passed** in 43.22 s (same one deprecation warning).

## Packaged-build evidence

- `dist/desktop-installer/win-unpacked/resources/app.asar` was built at
  12:25-12:27 on 2026-11-28, after HEAD `0ef502d` (12:18), from the clean tree;
  `DocuRebuild-1.1.1-setup.exe` was produced at 12:27.
- Extracted `src/main.cjs` from that asar contains
  `installApiAuthorization` (lines 316-329) and its startup call (line 443),
  matching `apps/desktop/src/main.cjs`. The per-launch token is injected into
  `${origin}/api/*` subresource requests, and the token is not part of the
  client bundle (`backend/tests/test_desktop.py::test_the_token_is_not_part_of_the_client_bundle`).
- `docs/smoke/desktop-smoke.json` (recorded 2026-11-28T05:58:15Z, result
  `passed`, 13.4 s) ran against that `win-unpacked` build: source render
  1275x1650 with `thumbnail_present: true`, OCR with 4 reviewed blocks,
  review/insert (343 characters), edit/autosave/reopen (381 characters),
  Markdown/TXT/DOCX/PDF exports, backup/restore and clean shutdown with the
  sidecar stopped; `console_errors` and `uncaught_exceptions` were empty.
- This is existing evidence from the day's release build; the audit did not
  rebuild or reinstall the application.

## Audit matrix

### 1. Source PDF/image/page-thumbnail rendering, including after restart — VERIFIED WORKING

- Desktop `<img>` subresources cannot set headers, so the shell injects the
  bearer token for every `${origin}/api/*` request in
  `apps/desktop/src/main.cjs:316-329`, installed at startup at line 443. This is
  re-established on every launch, so an app restart cannot lose it.
- `apps/web/src/lib/api.ts:82` keeps `API_BASE = "/api"` (same origin as the
  SPA); `desktopAuthHeaders()` at lines 89-92 handles renderer `fetch` calls,
  and `assetUrl()` at lines 687-691 adds an `updated_at` cache buster.
- The source panel keys the page image by page id and uses the display asset
  with the same version, so a refetch does not remount or show stale pixels.
- `backend/tests/test_desktop.py::test_page_images_require_the_launch_token`
  and the same-origin client test cover the token boundary; the packaged smoke
  report records `thumbnail_present: true` and a rendered source page.
- Limitation: the smoke suite exercises one imported PDF page; it is not a
  matrix of every image format after every possible restart path.

### 2. Dialog stability — VERIFIED WORKING

- All 25 `*dialog*.tsx` components are mounted persistently with an `open`
  prop; none is conditionally unmounted on a checkbox/filter/slider change.
- Shared themed controls are native inputs, so toggling a control is local React
  state and does not remount the dialog.
- State-syncing effects were inspected in every dialog with query-driven state.
  They are guarded by open/id/key checks: `edits-dialog.tsx:239-255` keeps a
  private copy with `pageRef`, `savedEditsRef` and `generationRef`;
  `ocr-dialog.tsx:154-170` keys block-draft resets on run id/status/count;
  `page-tables-dialog.tsx:82-96` and `table-proposal-dialog.tsx:72-78` reset only
  on open or candidate change, with `useTableDraft` keyed by candidate
  (`hooks/use-table-draft.ts:82`); `ai-review-dialog.tsx:144-149` clears
  selection only on close; `factory-reset-dialog.tsx:40-42` clears confirmation
  only on close.
- `accessibility.test.tsx::traps dialog focus and restores it after Escape`,
  `form-controls.test.tsx` and the focused dialog suites pass.
- Candidate investigated and dismissed: `document-layout-dialog.tsx:49-54`
  syncs header/footer from `layoutQuery.data`. React Query v5 structural
  sharing keeps the previous object reference when a refetch returns identical
  JSON (`useDocumentLayout` at `hooks/use-document.ts:39-48`), so a window-focus
  refetch does not re-run the effect or wipe unsaved edits. A server-side layout
  change would intentionally re-sync. No reproducible defect.

### 3. Checkbox/switch consistency and semantics — VERIFIED WORKING

- Only `components/ui/checkbox.tsx`, `switch.tsx` and `radio.tsx` render raw
  checkbox/radio inputs. `Checkbox` is a native input with an optional
  `indeterminate` property (`:19-69`); `Switch` is a native checkbox with
  `role="switch"` (`:18-51`); `Radio` keeps native radio group semantics.
- `form-controls.test.tsx` asserts checkbox role/label behaviour, mixed state
  without losing the checkbox role, switch semantics and native radios.
- No hardcoded raw checkbox/radio remained in feature components.

### 4. Factory reset — VERIFIED WORKING

- `factory-reset-dialog.tsx:40-44` requires the exact word `DELETE`
  (`CONFIRMATION`), disables the action until it matches, and clears the field
  when the dialog closes. `settings-factory-reset.test.tsx` covers the gate and
  the request.
- `backend/app/services/factory_reset.py:27-37` removes only app-owned data
  entries (`projects`, `trash`, `tmp`, `backups`, `fonts`, `secrets`, `app.db`,
  `app.db-wal`, `app.db-shm`); `_guard_data_dir` at lines 69-82 refuses drive
  roots, home and files; workers are stopped and the engine disposed before
  deletion, then the layout and schema are recreated (`:94-140`).
- `client-caches.ts:13-20` clears the three renderer localStorage keys;
  `settings-factory-reset.test.tsx` verifies appearance/language/workspace
  layout are cleared. `backend/tests/test_factory_reset.py` confirms projects,
  settings, keys and backups are removed, unrelated files survive, and a second
  reset succeeds. The app remains installed; this is separate from project
  deletion to trash.
- Candidate investigated and dismissed: `app.db-journal` is not listed, but the
  app sets `PRAGMA journal_mode=WAL` (`backend/app/db/session.py:32`), so a
  rollback journal is not created by normal operation. No confirmed defect.

### 5. Multi-select and safe bulk deletion — VERIFIED WORKING

- `pages/dashboard-page.tsx` enters selection mode, turns each card into a
  button (so it cannot navigate while selecting) and passes the selected ids to
  `bulk-delete-projects-dialog.tsx`; deletion requires confirmation.
- `backend/app/api/routes/projects.py:417-436` handles `/bulk-delete` and moves
  each project plus its backup vault to the local trash, reporting failures
  per project instead of aborting the batch.
- `backend/tests/test_projects.py` covers moving each project to trash,
  refusing a folder outside the data dir, requiring at least one id and
  continuing past a missing project. `dashboard-bulk-delete.test.tsx` covers
  select-all, accessible pressed state, confirmed deletion of only selected
  projects and keeping the selection on partial failure.

### 6. OCR-to-editor paragraph reconstruction — VERIFIED WORKING

- `apps/web/src/lib/ocr-reconstruction.ts:638` builds real paragraph/list/
  heading/quote nodes from reviewed blocks; `editor-panel.tsx:309` inserts that
  content when an OCR insertion carries blocks.
- `ocr-dialog.tsx:154-170` initialises editable drafts from the run while
  keeping user edits across identical refetches, and passes blocks, note and
  geometry on insert.
- Tests: `ocr-reconstruction.test.ts` (wrapped lines, vertical gaps, columns,
  headings, numbered/bulleted lists, table-like blocks, Burmese joining),
  `ocr-reconstruction-fixtures.test.ts` (PSM 3 vs 11 agreement),
  `ocr-reconstruction-pdf.test.ts` (multi-page embedded PDF), and
  `ocr-reconstruction-editor.test.ts` (flowing paragraphs, Justify,
  save/reopen, verbatim table). All pass. The packaged smoke report records a
  real OCR run with 4 reviewed blocks and a 343-character insertion.

### 7. Fonts, superscript/subscript and Justify — VERIFIED WORKING

- `lib/fonts.ts` registers imported faces through the authenticated FontFace
  API; `editor-panel.tsx:819-830` loads the families used by the document on
  mount/reopen, and `:843-862` applies a chosen family. `font-library-dialog`
  also loads imported faces when opened.
- `typography.test.ts` covers superscript/subscript application and removal,
  round-trip through document JSON, font marks, family sanitisation/collection,
  shortcut registration, and Justify plus save/reload.
- Export evidence: `document_export.py:817-821` maps `justify` to
  `WD_ALIGN_PARAGRAPH.JUSTIFY` for DOCX and `:2553-2555` emits
  `text-align: justify` for the PDF story. `test_fonts.py` covers system font
  listing, import/deduplication, WOFF2 conversion, deletion, and DOCX/PDF
  embedding; `test_docx_export.py` and `test_pdf_export.py` cover headings,
  tables, footnotes and Unicode text.
- Additional disposable probe (not committed): rendered a long justified and a
  long left-aligned paragraph through the shipped `render_docx`/`render_pdf`.
  DOCX reported `JUSTIFY` and `LEFT` correctly; PDF body-line right edges were
  544.9-545.1 pt for justified text (0.2 pt spread) versus 504.3-544.0 pt for
  left-aligned text (39.7 pt spread), confirming PyMuPDF Story honours
  justification. The packaged smoke report confirms edit/autosave/reopen and
  all four exports.

## Limitations and open gaps

- The packaged GUI was not interactively driven for the seven specific items in
  this session. The packaged smoke suite covers the main journey; factory
  reset, bulk delete, each dialog's controls and typography-specific export
  assertions are verified from source and automated tests instead.
- No NVDA/Narrator pass (tooling unavailable) and no new performance or OCR
  accuracy measurement were attempted; those remain recorded elsewhere.
- The Justify export probe was a disposable script under
  `%TEMP%\opencode`, not a committed regression test, because the prompt
  requires no code changes when all items pass. A future task may add a
  permanent export-alignment assertion if desired.
- The audit itself published nothing; the audited behaviour now ships in the
  published 1.1.4 installer.

## Files changed

- `docs/quick-wins/PROGRESS.md` (new — this audit record)
- `ROADMAP.md`
- `CONTINUE_PROMPT.md`
- `CHANGELOG.md`

No application source, tests, locale files, migrations or dependencies changed.

## Next tasks

The quick-win audit row is done. Next, run one task at a time from the
`CONTINUE_PROMPT.md` "Remaining work" table, starting with persisted region
proposals/batch review (design/evaluation first).
