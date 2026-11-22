# DocuRebuild - Project Completion Report

**Report date:** 22 November 2026
**Report state:** audit snapshot at `26b9263`, followed by the 1.0 desktop
delivery recorded in section 13 and the final stabilization described in
`PROJECT_MEMORY.md`
**Working tree:** the 1.0 delivery and stabilization changes are committed and
pushed to `main`
**Scope of this report:** audit of implemented behaviour, not a plan for new features

---

## 1. Executive summary

DocuRebuild is a substantial, working local-first application, not a prototype.
The core loop - create a project, import images or PDFs, process pages, OCR,
extract regions, reconstruct tables/figures/equations, edit, version and export -
is implemented end to end, with automated coverage on both sides of the stack.

**Estimated completion**

| Measure | Estimate | Basis |
| --- | --- | --- |
| Overall project (all 12 phases incl. distribution and final QA) | **approx. 90%** | Phase-weighted, see section 3, revised after section 13 |
| Core local-first MVP scope (phases 0-9) | **approx. 90%** | Functional coverage, verified by tests and code inspection |
| Production-release readiness | **approx. 84%** | Desktop packaging, licensing, the OCR baseline, installed-app QA, performance and security drills are delivered; real-scan accuracy and assistive-technology testing remain |

The application is usable today as an installed Windows application. The
remaining production gaps are a redacted real-document OCR corpus,
screen-reader testing, sustained-load measurement and code signing. None of them
require re-architecting the product.

**Strongest areas:** project/storage model, import pipeline (including PDFs and
background jobs), non-destructive image editing, editor/export, version history
and backup/restore, the bring-your-own-key AI platform with encrypted keys, and
the packaged desktop shell with a private local API.

**Weakest areas:** measured accuracy on real scans (phase 4), final QA
(phase 11), and the remaining page-wide reconstruction work.

---

## 2. Verification performed

All checks were run against the current working tree, not inferred from docs.
This section is the **pre-delivery snapshot** taken during the audit; section 13
records the final numbers after the 1.0 work (414 backend tests, 290 web tests,
the rebuilt installer and the installed-application drills).

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `backend\.venv\Scripts\python.exe -m pytest backend/tests -q` | **401 passed**, 1 third-party deprecation warning, 194 s |
| Frontend tests | `npm run test:web` | **45 files, 282 tests passed**, 79 s |
| TypeScript | `npm run typecheck` | Passed (no output) |
| ESLint | `npm run lint` | Passed (no output) |
| Production build | `npm run build` | Passed; Vite bundle with KaTeX fonts and CSS emitted |
| i18n parity | Included in Vitest (`i18n.test.ts`) | Namespace and key parity for English/Burmese, no empty strings, every proposal reason labelled |
| Stub/TODO scan | Ripgrep over `apps/web/src` and `backend/app` (excluding tests) | No `TODO`, `FIXME`, `HACK`, `NotImplementedError`, "coming soon" or mock production paths |
| CI configuration | `.github/workflows/ci.yml`, `codeql.yml` | Backend tests plus web typecheck/tests/build; CodeQL analysis |

Not verified by automation: real-document OCR accuracy, screen-reader and
keyboard-only journeys, mobile device rendering, large-document performance, and
a full backup/restore drill on a clean machine. These are phase 11 items, not
claims that the features are broken.

---

## 3. Completion by phase

Weighting is equal per phase for a transparent overall figure. Percentages are
judgement calls based on delivered scope versus the phase definition in
`docs/roadmap.md`, with item-level evidence below.

| Phase | Status | Completion | Evidence / remaining gap |
| --- | --- | --- | --- |
| 0. Foundation and architecture | Complete | 100% | Monorepo, design tokens, shared types, FastAPI app, SQLite, migrations 0001-0003 |
| 1. Local storage and project management | Complete | 100% | Per-project DB/folders, CRUD, trash, manifest, integrity checks |
| 2. Main UI and workspace | Complete | 100% | Resizable/collapsible panels, mobile Source/Document switch, themes, i18n |
| 3. Import and image processing | Complete | 100% | Images + PDFs, background jobs, non-destructive adjustments, rotation, reordering |
| 4. Local OCR and layout detection | In progress | 75% | OCR, review, layout hints, table proposals, CER/WER harness; figure detection in layout, real fixtures/figures, richer engines pending |
| 5. Element extraction | In progress | 85% | Manual crops, region library, local/AI text, heuristic + PDF artwork proposals, insertion; opaque PDF drawings and proposal persistence pending |
| 6. AI integration and free usage first | In progress | 85% | 14 provider entries (local plus 12 cloud), connections/keys, routing/fallback, limits/budget, consent, ledger; account billing/quota verification and advanced params pending |
| 7. Tables, figures and equations | In progress | 75% | Manual tables, proposals, merges from rules, figure numbering/citations, equations; nested tables, page-wide equation recognition pending |
| 8. Document editor and export | Complete | 100% | Rich text, tables, figures, equations, footnotes; Markdown/TXT/Word/PDF export with settings |
| 9. History, backup and recovery | Complete | 100% | Versions/diff/restore, activity log, verified backups, encrypted downloads, selective restore, vault, scheduled one-pass |
| 10. Desktop, PWA and mobile distribution | Planned | 10% | Responsive web UI and Windows launcher exist; no Tauri shell, PWA install, camera import or device pairing |
| 11. Final QA and production release | Planned | 5% | Tests and CI exist; no full accessibility/performance pass, release notes, version tag or upgrade drill |

**Weighted total:** `(6 x 100 + 75 + 85 + 85 + 75 + 10 + 5) / 12 = approx. 78%`

Two caveats on that number:

1. Six phases are fully complete, so the remaining work is concentrated in four
   "in progress" areas plus distribution and QA.
2. "In progress" does not mean half-built. Phases 5-7 contain most of the
   feature surface and each has a working, reviewable implementation; their
   percentages reflect missing breadth (nested tables, page-wide equations,
   measured accuracy), not missing foundations.

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

### Phase 5 - Element extraction (approx. 85%)
- **Opaque PDF drawings** (page/form content without readable paths) still
  require manual selection.
- **Region proposals are intentionally not persisted**; they are regenerated
  from the latest OCR run and prefills the manual dialog. That is a deliberate
  safety choice, not a bug, but it limits batch review across pages.
- Docs still list page-wide table detection as pending even though the
  page-wide endpoint exists (section 10).

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

### Phase 7 - Tables, figures, equations (approx. 75%)
- **Nested tables** are not separated from their parent.
- **Page-wide equation detection/transcription** is not implemented; only a
  single saved crop can be transcribed, on request.
- **Borderless merged-cell inference** is limited; exact spans come from drawn
  rules or a saved crop, otherwise it is a plain word-box grid.
- **Structured figure reconstruction with approval** (beyond captions,
  numbering, citations and inline images) is not implemented.

### Phase 10 - Distribution (approx. 10%)
- No Tauri desktop shell with a Python sidecar.
- No PWA manifest/service worker/install flow.
- No camera capture (`getUserMedia` is not used) and no secure pairing to a
  user-owned processing host.
- The Windows launcher (`start-docurebuild.bat`) requires Node 20+, Python 3.11+
  and installs dependencies on first run; it is a local developer-style
  launcher, not an installer.

### Phase 11 - Final QA (approx. 5%)
- No full accessibility audit (keyboard-only flows, focus order, contrast,
  screen-reader labels beyond component-level ARIA).
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

### 13.6 Verification performed

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
measured; that stays on the open list instead of being claimed.

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

Not performed, and therefore still open: a keyboard-only walkthrough of the
installed application with focus-visibility screenshots, and a screen-reader
pass (NVDA or Narrator). Radix primitives supply labelled dialogs and controls,
but that is an argument, not a verified result. What *was* checked on the
installed build is that the dashboard paints, that the saved dark theme and teal
accent resolve to their token values, and that the rendered layout has no
horizontal overflow at 1426x779 — a rendering check, not an assistive-technology
one.

### 13.10 What is still open

These are the honest remaining gaps; none require re-architecting:

- A redacted real-scan OCR corpus (English, Burmese, mixed, at least one table
  and one multi-column page) scored with the existing harness.
- A keyboard-only and screen-reader accessibility pass on the installed
  application.
- A sustained large-document performance and cancellation drill (hundreds of
  pages, repeated cancelled imports).
- An automated end-to-end desktop smoke suite; the desktop checks above were run
  manually and are partly covered by backend tests.
- macOS and Linux packaging. Only Windows x64 is built and tested.
- Installer size and footprint. The installer is 202 MB and installs 643 MB,
  because it carries Electron's full Chromium locale set (49 MB), a 178 MB
  Tesseract build and a 105 MB Python sidecar. Trimming Chromium locales and
  shipping a slimmer Tesseract build are safe future optimisations, not 1.0
  blockers.
- Page-wide figure detection inside the OCR layout, page-wide equation
  proposals, and nested-table separation (SHOULD HAVE, not 1.0).

### 13.11 Revised completion

| Measure | Before | After |
| --- | --- | --- |
| Overall project | approx. 78% | **approx. 90%** |
| Production-release readiness | approx. 65% | **approx. 84%** |

The remaining gap is evidence on real scans, assistive-technology testing and
sustained-load measurement, not missing foundations. Calling 1.0 shipped is
defensible for a Windows desktop release; the open list above is the honest
release-note content.
