# DocuRebuild - Project Completion Report

**Original report date:** 26 November 2026
**Original snapshot:** v1.1.0 release verification at commit `b0c139d`, following
the 1.0/1.1 desktop delivery recorded in section 13 and `PROJECT_MEMORY.md`
**Current state:** 28 November 2026, `main` after `bbf1449` (the 1.1.3
version/docs commit): version **1.1.4** built, smoke-tested and pushed, carrying
OCR cancellation and stale-run recovery, but not published as a GitHub release.
v1.1.1 remains the published release from `486688e`. The post-release quality,
prompt-pack and reliability work is carried by the locally built 1.1.4
installer. The current status, completed prompt-pack
tasks and remaining work are in **sections 16-19** and in `CONTINUE_PROMPT.md`.
**Scope of this report:** audit of implemented behaviour, not a plan for new features

**How to read the historical sections:** sections 1-13 describe the v1.1.0
snapshot. Statements there about missing real-scan OCR evidence, accessibility
evidence, sustained-load measurement, desktop E2E automation or page-wide
reconstruction describe that earlier state; sections 14-16 record what changed
afterwards. If a status statement conflicts with section 16,
`CONTINUE_PROMPT.md`, `ROADMAP.md` or the shipped code, those current sources win.

**Practical supplied-file check:** on 27 November 2026, the normal workflow
imported 8 PDF pages and 5 attached JPG scans. Source rendering and PDF text
were usable; editing, autosave/reopen and plain-text export were verified.
Burmese schedule OCR retained recognizable structure but required manual
correction of dates/numbers and low-confidence blocks. Mixed handwriting and
English/Burmese annotations remained unreliable OCR proposals. No code or source
file change was required. The brief evidence record is `PROGRESS.md`.

**Desktop E2E smoke suite:** on 28 November 2026, a repeatable one-command
automated smoke suite (`npm run smoke:desktop`) was verified against the
packaged `dist/desktop-installer/win-unpacked` build. It exercises the complete
user journey: launch/sidecar health, create project, import PDF, render source
pages, OCR/review/insert, edit/save/reopen, export (Markdown/TXT/DOCX/PDF),
backup/restore, and clean shutdown with sidecar stop verification. Uses
disposable data directories, deterministic CDP-driven steps, and writes a JSON
report (`docs/smoke/desktop-smoke.json`). Total runtime ~11-12 s on the
reference machine (Intel N100, 16 GB RAM).

---

## 1. Executive summary

DocuRebuild is a substantial, working local-first application, not a prototype.
The core loop - create a project, import images or PDFs, process pages, OCR,
extract regions, reconstruct tables/figures/equations, edit, version and export -
is implemented end to end, with automated coverage on both sides of the stack.

**Estimated completion (as of v1.1.0)**

| Measure | Estimate | Basis |
| --- | --- | --- |
| Overall project (all 12 phases incl. distribution and final QA) | **approx. 92%** | Phase-weighted, see section 3, revised after section 13 |
| Core local-first MVP scope (phases 0-9) | **approx. 95%** | Functional coverage, verified by tests and code inspection |
| Production-release readiness (Windows x64) | **approx. 88%** | Desktop packaging, licensing, the synthetic and real-scan OCR baselines, installed-app QA, performance and security drills and the desktop E2E smoke suite are delivered; interactive assistive-technology certification and code signing remain |

The application is usable today as an installed Windows application. After the
post-1.1.0 evidence work (real-scan OCR baseline, accessibility audit,
large-document performance/cancellation drill and desktop E2E smoke suite), the
remaining production gaps are an interactive screen-reader certification pass
(blocked by unavailable tooling) and code signing. None of them require
re-architecting the product.

**Status after v1.1.1:** all four `01_MUST_HAVE` and all four `02_SHOULD_HAVE`
prompt-pack tasks are complete. The page-wide figure/equation/nested-table/opaque
PDF work described in section 13.10 as deferred is delivered and recorded in
section 16. Remaining optional work is tracked in `CONTINUE_PROMPT.md`.

**Strongest areas:** project/storage model, import pipeline (including PDFs and
background jobs), non-destructive image editing, editor/export (now with full
typography: font families, superscript/subscript, Justify, font embedding),
version history and backup/restore, the bring-your-own-key AI platform with
encrypted keys, and the packaged desktop shell with a private local API.
**v1.1.0 adds:** layout-aware OCR paragraph/list/heading reconstruction at
insertion time, prose-column splitting, and per-line PDF text measurement.

**Weakest areas (at the v1.1.0 snapshot):** interactive assistive-technology
certification (phase 11, blocked here), page-wide equation/figure reconstruction,
and the small real-scan OCR corpus (three pages, one transcriber). Real-scan
accuracy is now measured in `docs/ocr-benchmark.md`; page-wide figure and
equation proposals were added after the snapshot (section 16).

---

## 2. Verification performed (v1.1.0)

All checks were run against the current working tree, not inferred from docs.
This section records the final numbers after the 1.1.0 release verification.

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `backend\.venv\Scripts\python.exe -m pytest backend/tests -q` | **437 passed**, 1 third-party deprecation warning, ~230 s |
| Frontend tests | `npm run test:web` | **56 files, 356 tests passed**, ~74 s |
| TypeScript | `npm run typecheck` | Passed (no output) |
| ESLint | `npm run lint` | Passed (no output) |
| Production build | `npm run build` | Passed; Vite bundle with KaTeX fonts and CSS emitted |
| i18n parity | Included in Vitest (`i18n.test.ts`) | Namespace and key parity for English/Burmese, no empty strings, every proposal reason labelled |
| Stub/TODO scan | Ripgrep over `apps/web/src` and `backend/app` (excluding tests) | No `TODO`, `FIXME`, `HACK`, `NotImplementedError`, "coming soon" or mock production paths |
| CI configuration | `.github/workflows/ci.yml`, `codeql.yml` | Backend tests plus web typecheck/tests/build; CodeQL analysis |
| Desktop payload build | `npm run desktop:build` | Web + PyInstaller sidecar + bundled Tesseract verified |
| Installer build | `npm run desktop:dist` | NSIS installer `DocuRebuild-1.1.0-setup.exe` (214 MB) created |
| Packaged sidecar drill | `backend\.venv\Scripts\python.exe drill.py` | 30 checks passed (project, import, OCR 96.5% confidence, exports, backup/restore) |
| Installer smoke test | Silent install → launch → uninstall → reinstall | Exit 0, data preserved, registry correct, version 1.1.0 |
| Anonymous download verification | `Invoke-RestMethod` from GitHub Releases | 214,082,110 bytes, SHA-256 `EC1DF483F539A0DE40DD862A820FD653E1C406AE12921B58D9B5069131A325F4` |
| **Desktop E2E smoke suite** | `npm run smoke:desktop` | **12/12 steps passed**, ~11 s; launch/sidecar → create project → import PDF → render → OCR/review/insert → edit/save/reopen → export (MD/TXT/DOCX/PDF) → backup/restore → clean shutdown; disposable profiles, JSON report at `docs/smoke/desktop-smoke.json` |

At the v1.1.0 snapshot, these were not yet automated: real-document OCR
accuracy, screen-reader and keyboard-only journeys, mobile device rendering,
large-document performance, and a full backup/restore drill on a clean machine.
Since then, the real-scan OCR baseline (section 13.10 and `docs/ocr-benchmark.md`),
the large-document performance/cancellation drill (section 14), and the desktop
E2E smoke suite including backup/restore (section 15) were completed. The
interactive screen-reader/keyboard-only journey remains blocked by unavailable
assistive tooling. Mobile rendering is out of scope for the Windows x64 release.

**Latest verification (28 November 2026, at `0d2aa0e`):** after the four
`02_SHOULD_HAVE` tasks, `backend\.venv\Scripts\python.exe -m pytest backend/tests -q`
reports **450 passed**, `npm run test:web` reports **59 files / 364 tests passed**,
and `npm run typecheck` / `npm run lint` are clean. These results supersede the
v1.1.0 numbers in the table above for the current tree; they do not change the
installer that was published for v1.1.1.

---

## 3. Completion by phase (v1.1.0)

Weighting is equal per phase for a transparent overall figure. Percentages are
judgement calls based on delivered scope versus the phase definition in
`docs/roadmap.md`, with item-level evidence below.

| Phase | Status | Completion | Evidence / remaining gap |
| --- | --- | --- | --- |
| 0. Foundation and architecture | Complete | 100% | Monorepo, design tokens, shared types, FastAPI app, SQLite, migrations 0001-0003 |
| 1. Local storage and project management | Complete | 100% | Per-project DB/folders, CRUD, trash, manifest, integrity checks |
| 2. Main UI and workspace | Complete | 100% | Resizable/collapsible panels, mobile Source/Document switch, themes, i18n |
| 3. Import and image processing | Complete | 100% | Images + PDFs, background jobs, non-destructive adjustments, rotation, reordering |
| 4. Local OCR and layout detection | **Complete** | **95%** | OCR, review, layout hints, table proposals, CER/WER harness; **v1.1.0 adds layout-aware paragraph/list/heading reconstruction at insertion, prose-column splitting, per-line PDF text measurement**; real fixtures/figures and richer engines still pending |
| 5. Element extraction | Complete | 95% | Manual crops, region library, local/AI text, heuristic + PDF artwork proposals, insertion; opaque PDF drawings and proposal persistence pending |
| 6. AI integration and free usage first | Complete | 95% | 14 provider entries (local plus 12 cloud), connections/keys, routing/fallback, limits/budget, consent, ledger; account billing/quota verification and advanced params pending |
| 7. Tables, figures and equations | In progress | 80% | Manual tables, proposals, merges from rules, figure numbering/citations, equations; nested tables, page-wide equation recognition pending |
| 8. Document editor and export | Complete | 100% | Rich text, tables, figures, equations, footnotes; Markdown/TXT/Word/PDF export with settings; **v1.1.0 adds font families, superscript/subscript, Justify, font embedding** |
| 9. History, backup and recovery | Complete | 100% | Versions/diff/restore, activity log, verified backups, encrypted downloads, selective restore, vault, scheduled one-pass |
| 10. Desktop distribution (Windows x64) | Complete | 90% | Electron shell, PyInstaller sidecar, bundled OCR, NSIS installer, data-preserving uninstall; macOS/Linux/PWA/camera not in scope |
| 11. Final QA and production release | In progress | 15% | Tests, CI, release notes, version tag, upgrade drill delivered; full accessibility/performance pass, code signing, sustained-load automation pending |

**Weighted total:** `(9 x 100 + 95 + 95 + 95 + 80 + 90 + 15) / 12 = approx. 92%`

Two caveats on that number:

1. Nine phases are fully complete (0-3, 5-6, 8-9), so the remaining work is concentrated in three areas plus final QA.
2. "In progress" does not mean half-built. Phases 4, 7, 11 contain working, reviewable implementations; their percentages reflect missing breadth (real-scan accuracy, page-wide equations/figures, accessibility pass, code signing), not missing foundations.

These percentages are the v1.1.0 assessment. The page-wide figure, equation,
nested-table and opaque-PDF gaps listed for phases 4, 5 and 7 were closed after
that snapshot; see section 16.

---

## 4. What is fully complete and verified

### Storage and projects
- Local data root with per-project SQLite database, immutable source assets,
  processed/thumbnail/export/backup/trash folders and atomic manifests.
- Create, list, open, rename, delete (to trash), integrity checks and migration
  versioning.
- Original imports are never rewritten; image adjustments re-render from the
  immutable source.

### Import and source handling
- JPG, PNG, WebP, BMP, TIFF and PDF import with backend-owned limits and
  localized validation.
- Text-based, image-based and mixed PDFs; 150 DPI local rendering; embedded text
  stored as unverified proposals; password/empty PDF rejection; page limits.
- Background import jobs with page-level progress, cancellation, per-file
  commits, restart recovery and localized failures.
- Source viewer: navigation, thumbnails, zoom/fit/actual size, rotation,
  reorder, delete; PDF rotation re-renders and invalidates stale text.
- Non-destructive crop, perspective correction, deskew, grayscale, contrast,
  brightness, sharpness, denoise, threshold, shadow/background cleanup, with
  before/after preview, per-step removal and reset.

### Editing and export
- Tiptap editor with formatting, document typeface, counts, autosave state,
  error handling and persisted page layout (margins/tokens/page numbers).
- Manual tables with row/column/header tools, merge/split and resize constraints.
- Figures as block or inline nodes, captions/alt text, optional numbering and
  stable cross-references.
- Display and inline LaTeX equations with offline KaTeX preview, optional
  numbering and cross-references; invalid input refused.
- Footnotes with generated numbering that survives edits.
- Markdown, plain text, Word and PDF export; PDF page size/margins from
  settings, embedded figures, links, native tables, merged cells and footnotes.

### History and recovery
- Document versions with checkpoints, read-only diff/compare and reversible
  restore into the current project.
- Filterable, exportable activity log.
- Verified project backup download (plain or password-encrypted `.drbz` using
  scrypt + AES-256-GCM), additive restore as a new project, selective page and
  document restore, page-image and region-crop repair.
- Local backup vault with opt-in automatic copies on open, configurable
  retention, and an optional scheduled one-pass command for OS schedulers.

### AI platform
- Unified BYOK platform: local Ollama, custom OpenAI-compatible endpoint and 12
  cloud adapters, with dynamic provider/model discovery (no hardcoded model
  lists in the frontend).
- Multiple named connections and keys; keys encrypted at rest (Fernet vault),
  write-only through the API, never logged or exported.
- Per-task routing (`ocr_cleanup`, `region_proposals`,
  `equation_transcription`, `table_structure`, `default`) with fallback,
  temperature, timeout and rolling limits.
- Key rotation/failover, cooldowns, auth/rate-limit classification, bounded
  attempts and honest 429 handling.
- HTTPS/loopback rules, SSRF/metadata host rejection, redirect refusal, explicit
  remote consent, global/per-task/per-connection limits, verified-spend budget.
- Metadata-only usage ledger and history UI; prompts, documents, crops and
  replies are not stored.
- Reviewable workflows: OCR cleanup suggestions, unpersisted region proposals,
  dialog-only equation transcription, acknowledged table grids.

### Local OCR and tables
- Tesseract adapter with runtime detection, language packs, honest unavailable
  states, persisted runs/blocks, confidence, geometry, reading order and
  verification.
- PDF text layers and OCR share one review dialog; stale results are detected
  after rotation or page edits.
- Reviewable page-level table proposals: single blocks, vertically contiguous
  groups, and page-wide detection via `/pages/{page_id}/table-proposals`.
- Drawn-rule merged cells for PDF vector rules, scanned-page raster rules and
  saved table crops; per-cell confidence, alignment inference, manual correction
  and source comparison.
- Optional AI table reading and equation transcription, always as review
  material that requires confirmation.

### Quality infrastructure
- 401 backend tests and 282 frontend tests, typecheck, lint and build all green.
- CI for backend tests, web checks and CodeQL; Dependabot and security policy.
- Design tokens package; no raw design values introduced by the audit.
- English/Burmese key parity enforced by tests; locale-aware formatting helpers.

---

## 5. Partially complete - exact remaining gaps

### Phase 4 - OCR and layout (approx. 75%)
- **Figure detection inside the OCR layout is absent.** Figures are proposed by
  a caption-band heuristic, PDF raster/vector artwork analysis and photographed
  ink clustering, not by the layout classifier.
- **No shipped accuracy fixtures or measured CER/WER.** The local benchmark
  harness exists and is tested, but no real-document pages or accuracy figures
  are committed, so "accuracy first" is unproven for English, Burmese and mixed
  pages.
- **No richer OCR engine adapter** (e.g. PaddleOCR) behind the same contract.
- Burmese quality depends on the installed traineddata, scan quality and fonts;
  this is documented but unmeasured.

### Phase 5 - Element extraction (approx. 85% at v1.1.0)
- **Opaque PDF drawings** (page/form content without readable paths) still
  require manual selection. *Completed after v1.1.1:* a low-confidence proposal
  is now made from the rendered page when no exact PDF geometry exists (§16).
- **Region proposals are intentionally not persisted**; they are regenerated
  from the latest OCR run and prefills the manual dialog. That is a deliberate
  safety choice, not a bug, but it limits batch review across pages. Persistence
  remains an optional future task.
- Docs listed page-wide table detection as pending even though the page-wide
  endpoint existed (section 10). That documentation was corrected; the current
  status is in §16.

### Phase 6 - AI (approx. 85%)
- **No account-level billing or quota verification.** The app records reported
  tokens/cost and enforces a local budget; it cannot read remaining provider
  quota or confirm a charge.
- **No proactive quota prediction** from history; 429s are handled, not
  anticipated.
- **Provider-specific advanced parameters** beyond temperature/timeout are not
  exposed.
- **Image generation is not implemented** and is not needed for reconstruction.
- Cost class remains a user declaration; a provider can bill outside the app.

### Phase 7 - Tables, figures, equations (approx. 75% at v1.1.0)
- **Nested tables** are not separated from their parent. *Completed after
  v1.1.1:* drawn child grids are linked to their parent cell as separate
  reviewable tables (§16).
- **Page-wide equation detection/transcription** is not implemented; only a
  single saved crop can be transcribed, on request. *Completed after v1.1.1:*
  page-wide OCR equation candidates are listed for review; transcription stays
  an explicit single-crop action (§16).
- **Borderless merged-cell inference** is limited; exact spans come from drawn
  rules or a saved crop, otherwise it is a plain word-box grid.
- **Structured figure reconstruction with approval** (beyond captions,
  numbering, citations and inline images) is not implemented. Page-wide figure
  *proposals* were added after v1.1.1, but no figure content is reconstructed
  automatically (§16).

### Phase 10 - Distribution (approx. 10%)
- No Tauri desktop shell with a Python sidecar.
- No PWA manifest/service worker/install flow.
- No camera capture (`getUserMedia` is not used) and no secure pairing to a
  user-owned processing host.
- The Windows launcher (`start-docurebuild.bat`) requires Node 20+, Python 3.11+
  and installs dependencies on first run; it is a local developer-style
  launcher, not an installer.

### Phase 11 - Final QA (approx. 5%)
- The contrast audit is automated and component-level keyboard/focus coverage
  now includes skip navigation, dialog Escape/restoration and native form
  controls. A full installed-app keyboard-only walkthrough and NVDA/Narrator
  pass remain open.
- No formal responsive device pass; breakpoints and a mobile panel switch exist
  and are tested at component level.
- No large-document performance/load profiling.
- No clean-machine install/upgrade/recovery drill.
- No release notes, changelog, version tag or signed build.

---

## 6. Not started (per specification, not defects)

- Packaged desktop distribution and PWA install.
- Mobile camera import and optional secure device pairing.
- Account billing/quota verification.
- Page-wide equation recognition.
- Nested table reconstruction.
- Image generation.
- Full offline-first sync between devices (also conflicts with the local-first
  SQLite model; not recommended).
- Additional UI languages beyond English and Burmese (architecture supports it).

---

## 7. Release blockers

Ordered by impact on an initial public release. "Blocker" means it prevents
calling the product production-ready, not that the app fails to run. The status
column records what section 13 delivered after the audit.

| # | Blocker | Impact | Evidence at audit | Status |
| --- | --- | --- | --- | --- |
| 1 | **No release vehicle.** No installer/packaged desktop build or installable PWA. | Non-technical users cannot install it; spec requires Web/PWA and desktop distribution. | Phase 10 planned; `start-docurebuild.bat` only; no `apps/desktop` | **Resolved.** Electron shell + PyInstaller sidecar + per-user NSIS installer in `apps/desktop` and `scripts/build-desktop.mjs` |
| 2 | **Unmeasured OCR accuracy.** No fixtures or CER/WER results. | The product's first principle is accuracy; shipping without a baseline risks silent quality failures, especially Burmese. | Roadmap phase 4 "Remaining"; no `backend/ocr-fixtures` content | **Partially resolved.** Committed synthetic English/Burmese/mixed fixtures and a reproducible baseline in `docs/ocr-benchmark.md`; a redacted real-scan corpus is still missing |
| 3 | **Final QA not performed.** Accessibility, responsiveness, performance, security and restore drills are unverified as end-to-end journeys. | Production-quality claims are unsupported; hidden regressions likely. | Phase 11 planned; no E2E/axe tooling | **Partially resolved.** Install/launch/OCR/export/backup/restore, performance, security and contrast audits are recorded in section 13; screen-reader testing and sustained-load drills remain |
| 4 | **Stale documentation contradicts code.** README and roadmap still call page-wide table detection pending. | Erodes trust and misleads contributors/reviewers. | README "Not available yet" and status table; roadmap phase 5 "Remaining" | **Resolved** (documentation truth pass, section 13) |
| 5 | **No release hygiene.** Version stays 0.1.0, no tag, changelog, release notes or upgrade test. | Users cannot identify builds or assess upgrade risk. | `package.json` 0.1.0; no CHANGELOG | **Resolved.** Version 1.0.0 across packages, `CHANGELOG.md`, upgrade test over an existing data folder |
| 6 | **Distribution licensing review.** PyMuPDF is AGPL/commercial dual-licensed. | Packaging a desktop build needs a licence decision or compliance work. | README licensing note; `backend/requirements.txt` uses PyMuPDF | **Resolved.** The project is licensed AGPL-3.0, `LICENSE` and `THIRD_PARTY_NOTICES.md` ship in the installer |
| 7 | **Tesseract is an external prerequisite** with language packs not bundled. | OCR is invisible until the user installs and configures it; Burmese adds traineddata setup. | Capability reporting and setup guidance exist, but no bundling | **Resolved.** Tesseract 5.4 with `eng`/`mya`/`osd` is bundled and auto-detected |

Non-blocking known issues at audit: a moderate, development-only `minimatch`
advisory via ESLint tooling (runtime dependencies were clean), and a low-severity
KaTeX prototype-pollution advisory in the production dependency tree. KaTeX is
used with `trust: false` and only ever renders user-entered equation source, so
the advisory is not reachable from imported document content; see section 13 for
the recorded decision.

---

## 8. Remaining work by priority

Effort is indicative for one experienced developer; it is not a commitment.

### MUST HAVE - required before a 1.0 release

| Task | Why | Acceptance criteria | Est. |
| --- | --- | --- | --- |
| Documentation truth pass | Docs currently understate delivered work | README, roadmap and architecture match code; page-wide table proposals described accurately; no stale "pending" claims | 0.5-1 day |
| OCR accuracy baseline | Accuracy-first principle | Committed redacted fixtures for English, Burmese and mixed pages; reproducible CER/WER report; documented limitations; no invented figures | 3-5 days |
| Accessibility and responsive QA | Production quality | Keyboard-only import -> OCR -> review -> export; visible focus; labelled controls; contrast check; 320 px to 1440 px layouts; fixes recorded | 3-5 days |
| Performance and reliability pass | Large documents are a stated risk | Import a large PDF and a long document; measure load, typing, save, export; no unbounded memory growth; cancellation still works | 2-3 days |
| Security review and restore drill | Local credentials and backups | Secret scan, dependency audit, path/zip traversal checks, backup -> wipe -> restore on a clean profile, documented result | 2-3 days |
| Distribution decision and implementation | Spec requires installable form | Either a Tauri shell with Python sidecar or an installable PWA with an honest capability boundary; install/upgrade docs | 5-10 days |
| Release hygiene | Traceability | Version bump, CHANGELOG/release notes, annotated tag, migration upgrade test from 0.1.0 data, clean-machine install test | 1-2 days |
| Licence review before packaging | Legal exposure | Written decision on PyMuPDF AGPL/commercial use for the chosen distribution | 0.5 day |

### SHOULD HAVE - valuable, but must not delay 1.0

| Task | Value | Est. |
| --- | --- | --- |
| Page-wide equation proposals | Completes the reconstruction loop for maths-heavy books | 3-5 days |
| Nested table separation | Real textbooks contain nested grids | 3-5 days |
| Persisted region proposals / batch review | Faster multi-page extraction | 2-4 days |
| Figure detection in the OCR layout | Reduces manual selection on scans | 3-5 days |
| Camera import and secure device pairing | Makes the mobile story real | 5-8 days |
| End-to-end browser smoke tests (Playwright) | Catches cross-feature regressions the unit suites miss | 2-4 days |
| Provider quota/billing introspection where APIs allow | Better free-tier honesty | 3-5 days |
| Optional PaddleOCR adapter | Better accuracy path without changing review rules | 4-7 days |

### OPTIONAL / FUTURE - explicitly out of 1.0

- Image generation or generative figure replacement (conflicts with
  accuracy-first; never required).
- Additional languages beyond English/Burmese.
- Cloud sync, accounts or multi-user collaboration (conflicts with local-first
  and the SQLite model).
- Plugin marketplace or third-party extension API.
- Automatic acceptance of AI output (should remain a reviewed proposal).

**Scope guard:** none of the SHOULD items block a credible 1.0. Page-wide
equations, nested tables and camera import are the most tempting to pull
forward; they should ship after the release candidate is stable unless a
specific user segment requires them.

---

## 9. MVP roadmap to a credible 1.0

Assumes the current branch is stabilised, not re-architected. Total approx.
3-4 weeks of focused work.

### M0 - Truth and scope freeze (1 day)
- Correct README, roadmap and architecture claims (including page-wide table
  proposals and the table-crop pipeline).
- Declare 1.0 scope: phases 0-9, one distribution target, English + Burmese.
- Record known limitations as release notes input.

**Exit:** no document claims a pending feature that is delivered, or a delivered
feature as pending.

### M1 - Accuracy evidence (3-5 days)
- Add redacted real-document fixtures (English, Burmese, mixed; at least one
  table and one multi-column page).
- Run the existing CER/WER harness; store a reproducible report.
- Verify Burmese rendering/input and document the Zawgyi boundary.
- Fix any accuracy or preprocessing regressions found.

**Exit:** measured baseline published with methodology and limitations.

### M2 - QA hardening (1-2 weeks)
- Accessibility pass (axe plus manual keyboard/screen-reader spot checks).
- Responsive pass at mobile/tablet/desktop widths, including dialogs and tables.
- Performance pass on a large PDF and a long document; fix hot spots.
- Security review, dependency audit, path/zip checks and a backup/restore drill.
- Add a small Playwright smoke suite for the primary journey.

**Exit:** no severity-1/2 defects; QA checklist signed off.

### M3 - Distribution (1-2 weeks)
- Choose Tauri shell or PWA (or both with a clearly stated capability matrix).
- Implement install/launch, backend lifecycle, data-dir selection and update
  story; keep the local API private by default.
- Resolve PyMuPDF licensing for the chosen distribution.
- Write install, upgrade and recovery documentation.

**Exit:** a non-technical user can install, launch, upgrade and recover on a
clean machine.

### M4 - Release candidate (2-3 days)
- Freeze features, bump version, write release notes/changelog.
- Run full backend/frontend suites plus the new E2E smoke suite.
- Test upgrade from 0.1.0 data through migrations 0001-0003.
- Tag the release; publish only after explicit owner approval.

**Exit:** repeatable release checklist, tagged build, accurate docs.

### Suggested 1.0 exit criteria
- 401+ backend and 282+ frontend tests green, plus E2E smoke.
- Measured OCR baseline for English and Burmese.
- Accessibility and responsive checks complete.
- Clean install and upgrade verified.
- Backup/restore drill verified.
- Documentation matches behaviour; no stale status claims.
- No paid service required for the core workflow.

---

## 10. Documentation drift found during the audit

These are factual inconsistencies, not opinions. They should be fixed in M0.

1. **README "Not available yet"** says "page-wide table detection" is not
   implemented, but `GET /api/projects/{id}/pages/{page_id}/table-proposals`
   detects page-wide candidates and the OCR dialog offers them.
2. **README roadmap table, Phase 5** repeats "page-wide table detection
   pending" while Phase 7's delivered section describes page-wide proposals.
3. **`docs/roadmap.md` Phase 5 "Remaining"** lists "page-wide automatic table
   detection" as missing, contradicting the endpoint and UI.
4. **README phase status line** still says "Phase 6 of 12" near the top, while
   phases 0-3 and 8-9 are complete and 4-7 are in progress.
5. The audit did not find stale claims in the opposite direction (features
   described as delivered but absent); the drift is conservative, which is
   safer but still misleading.

---

## 11. Risks and technical limitations to keep visible

- **Burmese OCR** depends on fonts, diacritic order and traineddata; no
  automatic Zawgyi conversion is performed, by design.
- **Browser-only builds cannot run Python OCR/PDF engines.** Any PWA must
  disclose a reduced capability set rather than imply parity.
- **SQLite on network shares is unsafe.** Connected devices must use the API.
- **Cancellation is cooperative** between files/pages; a single very large page
  operation must finish before the job stops.
- **Version history is not a backup.** It lives in the project database; only
  explicit downloads and the vault provide recovery.
- **AI output can be wrong.** Accepting a proposal marks it corrected, not
  verified; vision/table replies always require review.
- **Provider pricing and free tiers are not permanent.** The app records only
  reported cost and never advertises a provider as permanently free.
- **Dependency and licence drift** should be re-checked before each release.

---

## 12. Recommendation

Do not add optional features before closing the release gaps. The fastest path
to a credible 1.0 is:

1. Fix the documentation drift (hours, not days).
2. Produce a measured OCR baseline (accuracy is the product's core promise).
3. Run the QA/security/restore pass and add a thin E2E smoke suite.
4. Ship one installable distribution with honest capability reporting.
5. Tag and document the release.

With those steps, the existing implementation is strong enough for an initial
production release. Page-wide equations, nested tables, camera import, richer
OCR engines and provider quota introspection are credible post-1.0 work and
should not delay it.

---

## 13. The 1.0 desktop delivery - what was actually done and verified

This section records the work performed after the audit above. Every claim here
was checked on this machine; anything that was not checked is listed as a
limitation instead of an achievement.

### 13.1 Scope decision

1.0 is a **Windows x64 desktop application**. Mobile, PWA and device pairing were
removed from scope: the workspace no longer carries a breakpoint hook or a mobile
panel switch, and nothing in the interface advertises a phone layout.

### 13.2 Release vehicle

| Piece | Implementation |
| --- | --- |
| Shell | Electron 45 with `sandbox`, `contextIsolation`, `nodeIntegration: false`, a strict CSP and a context-isolated preload bridge |
| Local API | The existing FastAPI app frozen with PyInstaller as a one-folder `docurebuild-backend.exe` |
| Web client | The Vite production build, served by the local API so desktop mode is same-origin |
| OCR | Tesseract 5.4.0 with `eng`, `mya` and `osd` traineddata, unpacked from the UB Mannheim installer at build time |
| Installer | electron-builder NSIS, per-user (no administrator rights), Start menu and desktop shortcuts |
| Build entry points | `npm run desktop:build` (web, sidecar, Tesseract, verify) and `npm run desktop:dist` (installer) |

The data folder is `%LOCALAPPDATA%\DocuRebuild\DocuRebuild`, which is exactly what
`platformdirs.user_data_dir("DocuRebuild", "DocuRebuild")` returns, so a source
checkout and the installed app read the same projects. Window state and logs live
in Electron's `%APPDATA%\DocuRebuild` directory and never mix with project data.

Uninstalling removes the application directory and shortcuts only. Projects,
backups and the vault stay in `%LOCALAPPDATA%`, and a reinstall picks them up
unchanged.

### 13.3 Keeping the local API private

- The shell asks the OS for a free port, generates a 32-byte random token, and
  passes it to the sidecar through the environment.
- The sidecar binds `127.0.0.1` only. With `DOCUREBUILD_API_TOKEN` set, every
  `/api` request must send `Authorization: Bearer <token>`; anything else gets
  `401`.
- The token reaches the renderer only through the preload bridge, and
  `apps/web/src/lib/api.ts` attaches it to each request.
- When the variable is unset (development, CI, the test suite) the API keeps its
  previous loopback-only behaviour, so existing workflows and tests are
  unaffected.
- The built client is scanned during verification to prove the token is not
  embedded in any asset.
- Path traversal, unknown `/api` paths, non-GET SPA routes and asset requests
  were exercised against the packaged sidecar: `404` JSON for unknown API paths,
  `404` for traversal attempts, and `index.html` for client routes.

### 13.4 OCR accuracy - measured, and what it changed

`backend/tests/fixtures/ocr-synthetic` holds three 300 DPI pages (English,
Burmese, mixed) rendered with Windows GDI+ shaping plus their exact reference
transcripts; `scripts/generate-ocr-fixtures.ps1` regenerates them.

The first measurement exposed a real defect, not a cosmetic one. With
Tesseract's automatic page segmentation (mode 3) the Burmese page scored **85.60%
CER** - the layout analyser merged text rows and read the band as noise. Sparse
text segmentation (mode 11) scores **5.56% CER** on the same page. Overall CER
across the three pages: 35.93% (mode 3) versus **2.19%** (mode 11).

That result drove a product change rather than a footnote:

- Tesseract page segmentation is now a user-visible setting (Automatic, Single
  column, Single block, Sparse text) carried as `page_segmentation_mode`.
- Unsupported values are rejected with `ocr_invalid_segmentation_mode` instead of
  being replaced silently.
- Choosing a language combination that includes Burmese preselects sparse text
  until the user changes it.
- The benchmark gained `--segmentation-mode` so the same comparison can be
  repeated.

Full methodology, per-case tables, reproduction commands and limitations are in
`docs/ocr-benchmark.md`. The limitations are explicit: the fixtures are synthetic
and deterministic, so they measure the engine and language data, **not** skew,
noise or faded print. A redacted real-document corpus is still the honest next
step and remains open work.

### 13.5 Licensing

PyMuPDF 1.28.2 is AGPL-3.0, so the application is licensed **AGPL-3.0**. `LICENSE`
holds the full text and `THIRD_PARTY_NOTICES.md` lists every bundled runtime
component - Electron/Chromium, the web dependencies, the Python packages
(including PyMuPDF), Tesseract, Leptonica and the traineddata files - with their
licences, plus the build-only tools that are not redistributed. Both files are
copied into the installed application by electron-builder's `extraResources`.

### 13.6 Verification performed (v1.0.0)

| Check | Result |
| --- | --- |
| Backend suite | 414 tests passed (desktop, OCR, segmentation and benchmark coverage included) |
| Web suite | 290 tests in 47 files passed, including the design-token contrast guard |
| Typecheck, ESLint, production build | clean |
| Packaged sidecar auth | `401` without a token and with a wrong token, `200` with the correct one |
| Packaged sidecar routing | SPA at `/`, hashed assets, client routes; `404` JSON for unknown `/api`; `404` for traversal |
| Packaged OCR | Bundled engine reports 5.4.0.20240606 with `eng`, `mya`, `osd`; a Burmese page returns 75.6 mean confidence |
| Packaged sidecar drill | 61 checks against `docurebuild-backend.exe` with a throwaway data folder: `401` without/wrong token, health and meta at 1.0.0, all capabilities, 14 AI providers, settings persistence, project and document round-trip through SQLite, image import, English OCR at 95.8 confidence, Markdown/TXT/DOCX/PDF export, zip backup/restore with a byte-identical source asset, vault copy and restore, and `404` for traversal and unknown projects |
| End-to-end PDF run | Two-page PDF imported, pages rendered 1240x1755, OCR text matched the reference apart from one capitalisation difference |
| Installer | Final rebuild `DocuRebuild-1.0.0-setup.exe`, 211,528,811 bytes (201.7 MB), SHA-256 `7B444BF2B996C8EC1B4699D3C438747718D2DC665CDE0CFF31368311BB14A46C`, built by electron-builder NSIS after the navigation-guard, theme and crash-handling fixes |
| Install | Silent per-user install exits 0 in 34 s; `%LOCALAPPDATA%\Programs\DocuRebuild` holds the shell, sidecar, web client and Tesseract, with `LICENSE` and `THIRD_PARTY_NOTICES.md` under `resources\`; Start menu and desktop shortcuts are created; no administrator prompt |
| Installed launch | The window opens, the sidecar listens on loopback, and `/api/health` reports `version: 1.0.0`, `database: ok` |
| Installed UI | Driven over the DevTools protocol: the document reaches `complete`, the dashboard renders the heading, **7 project cards**, the `v1.0.0` status bar, a 64-character preload token and `platform: desktop`; there is no horizontal overflow at 1536x794, and no console error or warning is logged |
| Existing data | The installed app listed every project that already existed in `%LOCALAPPDATA%\DocuRebuild\DocuRebuild` (7 at the final drill), so the upgrade keeps projects and schema |
| Installed API isolation | No token and a wrong token both return `401`; `/projects/abc` returns the SPA; the installed hashed asset returns `200` and a missing asset returns `404` |
| Installed OCR and export | Using the installed sidecar directly: Tesseract 5.4.0.20240606 with `eng`/`mya`/`osd`; English page OCR 96.4 confidence, Burmese page (mode 11) 82.3; Markdown, TXT, DOCX and PDF exports all return the document body (a 0-byte Markdown file only when the document itself is empty) |
| Installed backup and restore | A vault copy was created, then restored as a new project. The archived source PDF extracts with an identical MD5 to the original and opens as 2 pages, so the backup is byte-faithful |
| Clean shutdown | Closing the window ends the shell **and** the sidecar; no orphaned backend or Tesseract process remains |
| Uninstall | Removes the application directory, both shortcuts and the uninstall registry entry; the data folder and all 8 projects and `app.db` survive |
| Reinstall over existing data | Reinstalling from the same installer exits 0 in 25 s, recreates both shortcuts and the registry entry, and the launched app reads the same 8 projects |
| Installed footprint | 643 MB on disk (Electron 356 MB, Tesseract 178 MB, Python sidecar 105 MB, web client 3 MB). Size is the cost of bundling an offline OCR engine and a Python runtime |
| Version consistency | 1.0.0 in the root/web/desktop packages, the backend `__version__`, the health endpoint, the installer registry entry and the UI status bar |
| Fresh clone | A shallow clone of `db44b44` ran `npm ci`, 290 web tests, typecheck, lint, the production build and 414 backend tests without errors |
| GitHub Release | `v1.0.0` published at commit `0a7af7f` with the installer asset; an anonymous download returns 211,528,811 bytes and SHA-256 `7B444BF2B996C8EC1B4699D3C438747718D2DC665CDE0CFF31368311BB14A46C`, matching the release notes |

---

### 13.6b Verification performed (v1.1.0)

| Check | Result |
| --- | --- |
| Backend suite | 437 tests passed, 1 third-party deprecation warning, ~230 s |
| Web suite | 356 tests in 56 files passed, ~74 s |
| Typecheck, ESLint, production build | clean |
| Desktop payload build | `npm run desktop:build` — web + PyInstaller sidecar + bundled Tesseract verified |
| Installer build | `npm run desktop:dist` — NSIS installer `DocuRebuild-1.1.0-setup.exe` (214 MB) created |
| Packaged sidecar auth | `401` without a token and with a wrong token, `200` with the correct one |
| Packaged sidecar routing | SPA at `/`, hashed assets, client routes; `404` JSON for unknown `/api`; `404` for traversal |
| Packaged OCR | Bundled engine reports 5.4.0.20240606 with `eng`, `mya`, `osd` |
| Packaged sidecar drill | 30 checks passed: project creation, page import, English OCR at 96.5 mean confidence (6 blocks with line geometry, both prose columns read), justified document save/reopen, Markdown/TXT/DOCX/PDF export, local backup restore as new project |
| Installer | `DocuRebuild-1.1.0-setup.exe`, 214,082,110 bytes (204.2 MB), SHA-256 `EC1DF483F539A0DE40DD862A820FD653E1C406AE12921B58D9B5069131A325F4` |
| Install | Silent per-user install exits 0; `%LOCALAPPDATA%\Programs\DocuRebuild` holds shell, sidecar, web client, Tesseract, `LICENSE`, `THIRD_PARTY_NOTICES.md`; Start menu and desktop shortcuts created; no administrator prompt |
| Installed launch | Window opens, sidecar listens on loopback, `/api/health` reports `version: 1.1.0`, `database: ok` |
| Installed API isolation | No token and wrong token both return `401`; unknown `/api` paths return JSON `404`; traversal attempts return `404` |
| Installed OCR and export | Tesseract 5.4.0.20240606; English page OCR 96.5 confidence; Markdown, TXT, DOCX, PDF exports verified |
| Installed backup and restore | Local backup created and restored as new project; page preserved |
| Clean shutdown | Closing window ends shell and sidecar; no orphaned processes |
| Uninstall | Removes application directory, shortcuts, registry entry; data folder and projects survive |
| Reinstall over existing data | Reinstalling exits 0, recreates shortcuts and registry entry, reads existing projects |
| Version consistency | 1.1.0 in all packages, backend `__version__`, health endpoint, installer registry, UI status bar |
| GitHub Release | `v1.1.0` published at commit `a8baa1b` (tag `v1.1.0`); anonymous re-download verified: 214,082,110 bytes, SHA-256 `EC1DF483F539A0DE40DD862A820FD653E1C406AE12921B58D9B5069131A325F4` |

### 13.7 Desktop QA: performance and memory

Measured on the installed sidecar, the same build the installer ships, on the
N100 reference machine (4 cores, 16 GB RAM, Windows 11):

| Journey | Measurement |
| --- | --- |
| Sidecar cold start to healthy `/api/health` | 5.9 s |
| Idle backend working set | 147 MB |
| Import a 24-page scanned PDF (1240x1755 pages) | 3.66 s total, **0.15 s per page**, peak working set 193 MB |
| OCR one page (English) | 1.4 s cold, 0.9 s warm, 96.4 mean confidence |
| OCR one Burmese page, sparse text | 1.3 s, 78.2 mean confidence |
| OCR the same Burmese page, automatic layout | 1.7 s, 41.3 mean confidence (confirms the segmentation finding at 150 DPI too) |
| Write a 168,490-character document (300 paragraphs) | 0.08 s |
| Read the same document | 0.04 s |
| Export DOCX / PDF of that document | 0.18 s / 0.28 s (38 KB / 72 KB) |
| Project storage for 24 pages | 5.6 MB including rendered pages and thumbnails |

The backend stayed between 147 MB and 193 MB across the whole drill, so the
import and OCR paths do not leak unbounded memory for this document size. A
multiply-cancelled job and a much larger PDF (hundreds of pages) were not
measured at the time of this snapshot. Both are measured in section 14; that
drill found and fixed a native-memory accumulation on repeated imports.

### 13.8 Desktop QA: security review

| Check | Result |
| --- | --- |
| API authentication | Missing or wrong bearer token returns `401` on every `/api` route, in the packaged shell and in the installed application |
| SPA fallback | Client routes return `index.html`; a missing asset returns `404`; unknown `/api` paths return JSON `404` |
| Path traversal | `../` in backup filenames, asset ids and page ids returns `404`; no file outside the data folder was read |
| Zip slip | A crafted archive with `../escape.txt` is rejected (`422`) and no file is written outside the target directory; `test_project_backup.py` also asserts `backup_unsafe_path` |
| Encrypted backup | Backup with a password returns `200`; restore without a password returns `backup_password_required`, with a wrong password `backup_wrong_password`, with the right password `201` and the pages intact |
| Secret scan | No API keys, tokens, private keys or credentials in tracked files; `.env`, `*.db`, `.venv` and `*.enc` are ignored |
| Token leakage | The per-launch token is generated at runtime, passed by environment, and absent from the built client and the packaged `app.asar` |
| Dependency audit | Runtime tree reports one **low** advisory: KaTeX prototype pollution that can bypass `trust` restrictions. DocuRebuild renders only user-authored equation source with `trust: false` and never renders imported text as math, so the path is not reachable; the upgrade to KaTeX 0.19 is a breaking change and is deferred to a maintenance release |
| Electron hardening | `sandbox`, `contextIsolation`, no `nodeIntegration`, CSP, permission denial, navigation restricted to the local origin, external links in the system browser |

### 13.9 Desktop QA: accessibility and contrast

The interface is desktop-only, so the old viewport-driven layout checks were
removed. A token audit measured every text and UI pair used by the theme:

- Light theme warning badges put white text on amber at **2.95:1**, and the
  blue, teal, emerald, amber and rose accent presets reached only
  **3.07:1-4.16:1** with white labels. Light-theme success, warning and
  destructive badge text on its 12% tint reached **3.19:1-4.06:1**.
- Those pairs failed WCAG AA for normal-size text. The token values were adjusted
  (success 28%, warning 30%, destructive 43%, info 44%, and the affected accent
  presets) until every label, muted text, status badge and accent reached at
  least **4.5:1**, and the dark theme primary was raised from 4.36:1 to 5.07:1.
- `apps/web/src/test/design-tokens.test.ts` now parses the real token file and
  fails the suite if any of those pairs drops below its threshold, so the fix
  cannot silently regress.

Completed on 27 November 2026: the current web baseline now provides a
visible-on-focus skip link, main landmark target and labelled editor toolbar.
Automated tests verify dialog Escape dismissal and trigger-focus restoration,
native checkbox/switch/radio roles and English/Burmese key parity. The installed
`DocuRebuild.exe` launched successfully on Windows NT 10.0.26300.0.

Not performed: an interactive keyboard-only walkthrough and NVDA/Narrator pass
on the installed application. NVDA and Narrator were neither running nor
available in this environment, and no browser automation was available for a
reliable desktop assistive-technology pass. These remain open and are documented
without claiming full WCAG certification. Radix primitives supply labelled
dialogs and controls, but that is not a substitute for a verified screen-reader
result.

### 13.10 What is still open (v1.1.0)

These are the honest remaining gaps; none require re-architecting. The four
1.x MUST HAVE items below were closed after this snapshot; their status is
updated here and recorded in sections 14-15, `PROGRESS.md`, `ROADMAP.md` and
`docs/ocr-benchmark.md`.

- **✅ Real-scan OCR baseline — completed.** `backend/tests/fixtures/ocr-real/`
  holds three public-domain scans (English prose, a printed statistical table,
  an English/Burmese mixed page) with transcripts typed from the page and
  measured CER/WER in `docs/ocr-benchmark.md`. Documented limits remain: one
  transcriber, no scored Burmese-only case, and no multi-column scored page yet.
- **✅ Installed-app accessibility audit — documented.** Contrast automation,
  component keyboard/focus tests, a skip link/main landmark, a labelled editor
  toolbar and dialog Escape/restoration checks are in place (section 13.9 and
  `PROGRESS.md`). NVDA and Narrator were unavailable in this environment, so an
  interactive screen-reader pass remains a recorded blocker, not a WCAG
  certification claim.
- **✅ Large-document performance and cancellation drill — completed**
  (section 14): raster PDFs to 400 pages, three repeated cancellations, concurrent
  imports, a hard-kill recovery and shutdown-during-OCR, with two defects fixed.
- **✅ Desktop E2E smoke suite — completed 28 November 2026** (section 15).
  `npm run smoke:desktop` exercises launch/sidecar → create project → import PDF
  → render source pages → OCR/review/insert → edit/save/reopen → export
  (Markdown/TXT/DOCX/PDF) → backup/restore → clean shutdown with sidecar stop
  verification. Uses disposable data directories, deterministic CDP-driven
  steps, JSON report at `docs/smoke/desktop-smoke.json`.
- macOS and Linux packaging. Only Windows x64 is built and tested.
- Installer size and footprint. The installer is 204 MB and installs ~650 MB,
  because it carries Electron's full Chromium locale set (49 MB), a 178 MB
  Tesseract build and a 105 MB Python sidecar. Trimming Chromium locales and
  shipping a slimmer Tesseract build are safe future optimisations, not 1.x
  blockers.
- ~~Page-wide figure detection inside the OCR layout, page-wide equation
  proposals, and nested-table separation (SHOULD HAVE, not 1.x).~~ **Completed
  after v1.1.1; see section 16.** Opaque PDF drawing extraction was completed in
  the same series.

### 13.11 Revised completion (v1.1.0)

| Measure | v1.0.0 | v1.1.0 |
| --- | --- | --- |
| Overall project | approx. 90% | **approx. 92%** |
| Core local-first MVP scope (phases 0-9) | approx. 90% | **approx. 95%** |
| Production-release readiness (Windows x64) | approx. 84% | **approx. 88%** |

The remaining gap at v1.1.0 was evidence on real scans, assistive-technology
testing, sustained-load measurement, and code signing, not missing foundations.
Calling 1.1 shipped was defensible for a Windows desktop release; the open list
above was the honest release-note content at that time. Section 16 records the
current status after v1.1.1.

---

## 14. Addendum - large-document performance and cancellation (27 November 2026)

This closes the sustained-load measurement listed as open in section 13.10 and
the "Performance and reliability pass" MUST HAVE in section 8. The full
methodology, tables, limitations and reproduction commands are in
`docs/performance.md`; raw data is in `docs/performance/sidecar-drill.json` and
`docs/performance/editor-drill.json`.

Measured on the same N100/16 GB reference machine with the packaged Electron
shell and a PyInstaller sidecar rebuilt from this tree, using disposable data:

| Journey | Result |
| --- | --- |
| Import 1 / 10 / 50 / 200 / 400-page raster PDFs | 0.49 / 2.82 / 12.95 / 52.38 / 106.68 s (0.259-0.267 s/page from 10 pages) |
| Peak sidecar working set during the 400-page import | 197.3 MB, returning to 157.2 MB |
| Ten consecutive 10-page imports | 156.5-158.8 MB, no step growth |
| OCR sample pages 0/200/399 | 2.26-2.48 s each, 96.1-96.2 mean confidence |
| Save / read 1,015,143-character document | 0.17 s / 0.04 s |
| Export that document (DOCX / PDF) | 0.37 s / 0.95 s |
| Editor typing, 144,753 characters | 4.70 s total; median 37 ms per 1,200-character input, p95 60 ms |
| Autosave / reload | 0.99 s after last input / 0.57 s to restore the text |
| Three repeated cancellations of a 400-page import | 0.14-0.27 s to `cancelled`, no temp files, project still usable |
| Two concurrent 50-page imports | One cancelled, one succeeded with 50 pages |
| Hard kill after 3 pages of a 200-page import | Restart recovered the job as `failed`/`import_interrupted`, kept 3 pages, next import succeeded |
| Window close | Shell exited in 3.35 s; 0 shell, backend or Tesseract processes |

Two defects were found and fixed as part of the measurement:

1. PyMuPDF retained native buffers for closed documents in its process-wide
   store. Before the fix the drill grew from 149.8 MB idle to 235.9 MB after the
   400-page import, with about 19 MB added per repeated import. PDF closes now
   go through `pdf.close_document()`, which releases the store; memory is flat
   across repeated imports.
2. Two import jobs in one project allocated the same page number and the second
   failed with `UNIQUE constraint failed: pages.page_number`. Imports are now
   serialised per project (different projects still run in parallel), with a
   regression test in `backend/tests/test_import_jobs.py`.

Not fixed, and recorded as known gaps: OCR has no cancel action and an OCR run
interrupted by a crash stays `running` after restart; a crash can leave one
preparation PNG in `tmp/` or one unreferenced processed image from an in-flight
page. A 1,000-page import, low-memory hardware, network storage and thermal/
power variations remain unmeasured. The backend suite passes **439 tests** after
these changes.

---

## 15. Addendum - Automated Desktop E2E Smoke Suite (28 November 2026)

This closes the "Automated end-to-end desktop smoke suite" item listed as open in
section 13.10 and the MUST HAVE 04 requirement.

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
  closing, then polls until they are gone. Runs stopped the sidecar within 2
  seconds each.
- **Shutdown-step robustness fix**: an initial run failed intermittently at the
  final step with `DevTools connection closed`. Closing the window tears down
  the DevTools socket, so the in-flight `window.close()` evaluation can reject
  with that expected error. The step now tolerates `DevTools connection closed`
  / `not open` for that single call and relies on `waitForChildExit` plus the
  sidecar PID poll as the real assertion. Three consecutive runs passed after
  the fix (~12 s each).
- **CI-friendly**: No external services, no paid APIs, no hardcoded paths. The
  suite requires Node 22+ (global `WebSocket`) and the packaged desktop payload.
  Total runtime ~11-12 seconds on the reference machine (Intel N100, 16 GB RAM).

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
[smoke] passed in 11s
```

### Files changed

- `scripts/desktop-smoke.mjs` (pre-existing suite; verified end-to-end against
  the packaged build and hardened the shutdown step against the expected
  DevTools connection-close race)
- `docs/smoke/desktop-smoke.json` (run artifact, git-ignored)
- `ROADMAP.md` (updated "Desktop end-to-end automation" to ✅ Completed)
- `PROGRESS.md` (detailed verification entry)
- `CHANGELOG.md` (added to Unreleased section)
- `PROJECT_MEMORY.md` (limitations updated)
- `PROJECT_COMPLETION_REPORT.md` (this section)

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

---

## 16. Status after v1.1.1 (28 November 2026)

Sections 1-13 remain the historical v1.1.0 QA snapshot; sections 14-15 record
the post-snapshot MUST HAVE work. The prompt pack at
`C:\Users\minkh\Downloads\Telegram Desktop\DocuRebuild_Remaining_Work_Prompts\DocuRebuild_Prompt_Pack`
defines the remaining tasks. Its `01_MUST_HAVE` and `02_SHOULD_HAVE` series are
**complete**, as are the quick-win audit and all optional evaluations. The
published v1.1.1 installer was built at `486688e`; the task work below is
committed on `main` and carried by the locally built, unpublished 1.1.3
installer described in section 18.

### 16.1 Completed prompt-pack tasks

| Series | Task | Verified evidence | Commit |
| --- | --- | --- | --- |
| 01 MUST HAVE | 01 Real-scan OCR accuracy baseline | Three public-domain scans with typed transcripts; CER/WER in `docs/ocr-benchmark.md`; §13.10 | `8cb208c` |
| 01 MUST HAVE | 02 Accessibility keyboard/screen-reader audit | Skip link, main landmark, labelled editor toolbar, contrast automation and component keyboard/focus tests; §13.9 and `PROGRESS.md` | `09b5f99` |
| 01 MUST HAVE | 03 Large-document performance/cancellation | 400-page import, cancellation/concurrency/hard-kill drill, two fixes; `docs/performance.md` and §14 | `09b5f99` |
| 01 MUST HAVE | 04 Automated desktop E2E smoke tests | `npm run smoke:desktop`, 12/12 steps, disposable profiles; `docs/smoke/desktop-smoke.json` and §15 | `ad7809d` |
| 02 SHOULD HAVE | 01 Page-wide figure detection | `backend/tests/figure_eval.py`, `docs/figure-detection.md`; precision 1.00, recall 1.00 on a controlled corpus; caption duplicate fix | `04f0b5f` |
| 02 SHOULD HAVE | 02 Page-wide equation proposals | `GET .../equation-proposals`, `PageEquationsDialog`, 4 backend + 3 web tests; `docs/should-have/PROGRESS.md` | `0708826` |
| 02 SHOULD HAVE | 03 Nested table separation | Linked drawn parent/child grids, stable candidate keys, dialog badges, 4 backend + 3 web tests, DOCX/PDF export tests | `25ffbc7` |
| 02 SHOULD HAVE | 04 Opaque PDF drawing extraction | Rendered-page raster fallback when PDF geometry is absent, 2 backend tests; `docs/figure-detection.md` | `0d2aa0e` |

The real-scan corpus was committed in `8cb208c`; the accessibility audit and
large-document drill were part of the combined quality pass `09b5f99` together
with the import fixes. The accessibility audit is documented but is not a WCAG
certification: NVDA and Narrator were unavailable, so an interactive
screen-reader pass remains a known gap. Task 03 also identified OCR cancellation
and stale-run recovery as open gaps.

### 16.2 Verification of the current tree

| Check | Result at the 1.1.2 build |
| --- | --- |
| `backend\.venv\Scripts\python.exe -m pytest backend/tests -q` | **456 passed** (one Starlette deprecation warning) |
| `npm run test:web` | **60 files / 368 tests passed** |
| `npm run typecheck` | clean |
| `npm run lint` | clean |
| `npm run build` | production build clean (inside `npm run desktop:dist`) |
| `npm run smoke:desktop` | **12/12 steps passed** on the packaged 1.1.2 `win-unpacked` build in 14 s |

Across the four SHOULD HAVE tasks the backend count rose from 439 to 450
(+1 figure evaluation, +4 equation proposals, +4 nested tables, +2 opaque PDF)
and the web count from 358 to 364 (+3 equation dialog, +3 nested table dialog).
The read-only cross-page review later raised both suites to the current 456
backend / 368 web tests. Per-task commands, measured numbers, changed files and
limitations are recorded in `docs/should-have/PROGRESS.md`,
`docs/quick-wins/PROGRESS.md` and `docs/optional-future/PROGRESS.md`.

### 16.3 Prompt-pack status

| Priority | Item | Status / next action |
| --- | --- | --- |
| 1 | `04_QUICK_WINS_AND_REGRESSION_CHECKS/01_Audit_Previously_Requested_Fixes.md` | Done. All seven requests VERIFIED WORKING; no confirmed defect and no code change; `docs/quick-wins/PROGRESS.md`. |
| 2 | `03_OPTIONAL_FUTURE/01_Persisted_Region_Proposals_Batch_Review.md` | Done. Proposals stay derived and non-persisted; the approved read-only cross-page review is implemented in `b7761bd` (bounded, resumable, no batch accept); `docs/optional-future/PROGRESS.md`. |
| 3 | `03_OPTIONAL_FUTURE/02_PaddleOCR_Adapter_Evaluation.md` | Done. Benchmarked on the real-scan corpus; no Burmese model, mixed accuracy, ~8x sidecar footprint and 13-16x slower pages; decision not to implement; `docs/optional-future/PROGRESS.md`. |
| 4 | `03_OPTIONAL_FUTURE/03_Provider_Quota_Introspection.md` | Done. Capability matrix, report-only, no provider calls; only OpenAI/Anthropic (admin keys), OpenRouter and DeepSeek have verified official endpoints; `docs/optional-future/PROGRESS.md`. |
| 5 | `03_OPTIONAL_FUTURE/04_Windows_Installer_Footprint_Optimisation.md` | Done. `electronLanguages: ["en-US"]` applied and verified with a full rebuild plus 12/12 smoke; installer 204.19 -> 195.92 MB; carried into 1.1.2; `docs/optional-future/PROGRESS.md`. |
| 6 | `03_OPTIONAL_FUTURE/05_macOS_Linux_Feasibility.md` | Done. Feasibility matrix, blockers and effort estimate; report only, no implementation; `docs/optional-future/PROGRESS.md`. |

Also open, but not part of the prompt-pack series: interactive NVDA/Narrator
pass and code signing (wider-release blockers), OCR cancellation and stale-run
recovery, a larger real-scan OCR corpus, merged-cell detection for text-only
tables, a bundled offline LaTeX typesetter for PDF export, remaining OMML edge
cases, and automatic update checking. Mobile, PWA, camera pairing, cloud
accounts and telemetry are out of scope rather than pending.

### 16.4 Continue prompt and handover

`CONTINUE_PROMPT.md` is the canonical handover. It contains a paste-ready prompt
for a new chat, the completed/remaining tables, the verification commands and a
session log. Run **one task per session**, preserve the local-first desktop
scope, never fabricate results, update the progress docs and CHANGELOG with
exact evidence, commit only that task, and do not publish a release without an
explicit owner request and a newly built, verified installer.

## 17. 1.1.2 local build verification (28 November 2026)

Version 1.1.2 was bumped across the root, web, desktop and shared package
manifests, `package-lock.json`, `backend/app/__init__.py` and
`backend/pyproject.toml`. A clean `npm run desktop:dist` rebuilt the web client,
the PyInstaller sidecar and the NSIS payload with the existing bundled Tesseract
runtime. It produced a **separate** installer,
`dist/desktop-installer/DocuRebuild-1.1.2-setup.exe`, 205,436,086 bytes (195.92
MB), SHA-256
`56BEA0EB38B7017D2EAB143A31DE31CFF917875F1C4030216334B86D15588117`.

The pre-existing locale-trimmed `DocuRebuild-1.1.1-setup.exe` in `dist/` remained
205,432,372 bytes, SHA-256
`BABE4B5949BF996701BC5BD3FB6F707D59FA33D1746B7E2E7FF4839ED484F649`; it was not
overwritten and must not be published as 1.1.1. The **published** 1.1.1 asset is
a different, earlier file (214,103,864 bytes, SHA-256
`9CC17F7EDF0138A7FC452844C89B0F2EC653970258F3888A661AB3773FAC13CB`).

Verification after the version bump:

| Check | Result |
| --- | --- |
| `backend\.venv\Scripts\python.exe -m pytest backend/tests -q` | 456 passed, 1 warning in 300.92 s |
| `npm run test:web` | 60 files / 368 tests passed in 112.55 s |
| `npm run typecheck` | clean |
| `npm run lint` | clean |
| `npm run desktop:dist` | 1.1.2 installer built; no code signing certificate configured |
| `npm run smoke:desktop` | 12/12 steps passed in 14 s on the packaged `win-unpacked` build |

The smoke run covered launch/sidecar authentication, project creation, PDF
import, source rendering, OCR review/insert, edit/autosave/reopen,
Markdown/TXT/DOCX/PDF export, backup/restore and clean sidecar shutdown. The
1.1.2 installer itself was **not** installed on a clean machine and no GitHub
release was published from it. The published release remains v1.1.1; pushing
the version bump to `main` does not change that.

## 18. 1.1.3 local build verification (28 November 2026)

Version 1.1.3 was bumped across the root, web, desktop and shared package
manifests, `package-lock.json`, `backend/app/__init__.py` and
`backend/pyproject.toml`. It carries the equation-extraction LaTeX normalisation
described in `CHANGELOG.md`. A clean `npm run desktop:dist` rebuilt the web
client, the PyInstaller sidecar and the NSIS payload with the existing bundled
Tesseract runtime. It produced a **separate** installer,
`dist/desktop-installer/DocuRebuild-1.1.3-setup.exe`, 205,444,142 bytes (195.93
MB), SHA-256
`BCB80868CF88EE9A8581BB12CA84FB2B798CFC137E77D082640B62FD7D687E20`.

The earlier `DocuRebuild-1.1.1-setup.exe` (locale-trimmed, 195.92 MB,
`BABE4B59...F649`) and `DocuRebuild-1.1.2-setup.exe` (195.92 MB,
`56BEA0EB...88117`) in `dist/` were not overwritten and must not be published as
1.1.1. The **published** 1.1.1 asset is a different, earlier file (214,103,864
bytes, SHA-256
`9CC17F7EDF0138A7FC452844C89B0F2EC653970258F3888A661AB3773FAC13CB`).

Verification after the version bump:

| Check | Result |
| --- | --- |
| `backend\.venv\Scripts\python.exe -m pytest backend/tests -q` | 468 passed, 1 warning in 306.49 s |
| `npm run test:web` | 60 files / 369 tests passed |
| `npm run typecheck` | clean |
| `npm run lint` | clean |
| `npm run desktop:dist` | 1.1.3 installer built; no code signing certificate configured |
| `npm run smoke:desktop` | 12/12 steps passed in 17 s on the packaged `win-unpacked` build |

The smoke run covered launch/sidecar authentication, project creation, PDF
import, source rendering, OCR review/insert, edit/autosave/reopen,
Markdown/TXT/DOCX/PDF export, backup/restore and clean sidecar shutdown. The
packaged smoke must run with no other DocuRebuild instance open, because the
installed app shares `%APPDATA%\DocuRebuild` and holds the single-instance lock.
The 1.1.3 installer itself was **not** installed on a clean machine and no GitHub
release was published from it. The published release remains v1.1.1; pushing
the version bump to `main` does not change that.

## 19. 1.1.4 local build verification (28 November 2026)

Version 1.1.4 was bumped across the root, web, desktop, shared and design-token
package manifests (including the workspace pins in `apps/web`),
`package-lock.json`, `backend/app/__init__.py` and `backend/pyproject.toml`. It
carries the OCR cancellation and stale-run recovery described in
`CHANGELOG.md`. The change, the version bump, the rebuilt installer and these
docs are committed and pushed to `main`; nothing was published as a release.

A clean `npm run desktop:dist` rebuilt the web client, the PyInstaller sidecar and
the NSIS payload with the existing bundled Tesseract runtime. It produced a
**separate** installer, `dist/desktop-installer/DocuRebuild-1.1.4-setup.exe`,
205,449,910 bytes (195.93 MB), SHA-256
`38F29388F64DF555BF9C46DBDBC094CE2868FE4DE84BE619B212FD9837758DD6`. The 1.1.1,
1.1.2 and 1.1.3 installers in `dist/` were not overwritten.

Verification after the change:

| Check | Result |
| --- | --- |
| `backend\.venv\Scripts\python.exe -m pytest backend/tests -q` | 475 passed, 1 warning in 285.48 s |
| `npm run test:web` | 60 files / 369 tests passed |
| `npm run typecheck` | clean |
| `npm run lint` | clean |
| `npm run build` | production build clean |
| `npm run desktop:dist` | 1.1.4 installer built; no code signing certificate configured |
| `npm run smoke:desktop` | 12/12 steps passed in 15 s on the packaged `win-unpacked` build |

The smoke run covered launch/sidecar authentication, project creation, PDF
import, source rendering, OCR review/insert (Tesseract 5.4.0, 4 blocks, 343
characters inserted, 95.1 mean confidence), edit/autosave/reopen, all four
exports, backup/restore and clean sidecar shutdown. It does not click the new
Cancel button; cancellation is covered by seven backend tests. The packaged
smoke must run with no other DocuRebuild instance open because the installed app
shares `%APPDATA%\DocuRebuild` and holds the single-instance lock. The 1.1.4
installer itself was **not** installed on a clean machine and no GitHub release
was published from it.
