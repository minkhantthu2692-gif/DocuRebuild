# OPTIONAL FUTURE task series — resumable progress

Durable record for the `03_OPTIONAL_FUTURE` prompts in
`DocuRebuild_Remaining_Work_Prompts/DocuRebuild_Prompt_Pack`. Read this with
`AGENTS.md`, `CONTINUE_PROMPT.md` and `ROADMAP.md`.

Scope guard (unchanged): Windows x64 Electron + bundled Python sidecar,
local-first. No mobile/PWA/Tauri/camera/cloud/accounts/collaboration work.
`03_OPTIONAL_FUTURE` must not delay the Windows x64 release.

Working rules applied: verified the current working tree instead of trusting the
dated report, used only disposable test data, implemented only this task, made
no unrelated refactors or new dependencies, did not publish a release, and did
not claim any unverified result.

## Status

| # | Task | Status | Outcome |
| --- | --- | --- | --- |
| 01 | Persisted region proposals and batch review | evaluated | Design + stale-safety trade-off documented; **no persistence change** (see decision); two regression tests lock the invariants |
| 02 | PaddleOCR adapter evaluation | deferred | Needs a heavy local install + a measured real-scan benchmark; plan documented, no result claimed |
| 03 | Provider quota introspection | evaluated | Capability matrix delivered; report-only, no provider calls implemented |
| 04 | Windows installer footprint optimisation | done | Applied `electronLanguages: ["en-US"]`; verified rebuild + 12/12 smoke; installer 204.19 -> 195.92 MB, installed 646.64 -> 598.39 MB |
| 05 | macOS/Linux feasibility study | evaluated | Platform matrix, risks and effort estimate; report only, no implementation |

---

## Task 01 — Persisted region proposals and batch review

**Prompt:** `03_OPTIONAL_FUTURE/01_Persisted_Region_Proposals_Batch_Review.md`

### Prompt requirement

> Evaluate persisting OCR-derived region proposals for cross-page batch review.
> - The report says proposals are intentionally regenerated rather than
>   persisted; document the safety trade-off before changing it.
> - Design stable identity/versioning so source edits, rotation, or OCR reruns
>   invalidate stale proposals.
> - Batch review must never silently accept or insert content.
> - Preserve provenance, confidence, and user decisions.
>
> Acceptance: documented design and implementation only if it adds clear value
> without weakening review safety or stale-state handling.

### Current behaviour (verified in this tree)

All region suggestions are **derived on demand and never persisted**. There is no
proposal table in either database; the proposal is a pure function of the latest
OCR run plus the current page source and the extracted elements.

- `backend/app/services/regions.py:504` `propose_regions()` reads the page, the
  latest `ocr_runs` row (`ORDER BY created_at DESC LIMIT 1`, line 523), its
  `ocr_blocks`, the page's current `display_asset_id`/`original_asset_id`,
  rotation and any saved `elements`, and returns a computed list. The docstring
  (lines 514-517) states proposals are not persisted and never become elements
  on their own.
- Status values are `ready`, `no_ocr_run`, `ocr_not_ready`, `ocr_failed`,
  `ocr_stale`, `no_geometry` (`backend/app/schemas/regions.py:7-14`). The frontend
  treats anything other than `ready` as "show a status, offer no suggestions".
- Staleness is already enforced (`regions.py:598-602`): a proposal list is
  returned only when the OCR run's `source_asset_id` equals the page's current
  display/original asset **and** the run's `rotation` equals the page rotation.
  Otherwise the endpoint returns `ocr_stale` with no proposals.
- Proposal identity is deterministic: `key = "{kind}-{x}-{y}-{width}-{height}"`
  (`regions.py:387`); AI proposals use `"ai-{kind}-{x}-{y}-{width}-{height}"`
  (`backend/app/services/ai_vision.py:125-128`). Keys are stable within one
  response only.
- Provenance is carried per proposal: `reason`, `confidence` (high/medium/low),
  `caption`, `block_ids` (`regions.py:377-397`); AI proposals additionally carry
  `provider`/`model` at the response level (`ai_vision.py:148-155`).
- Deduplication and "already extracted" suppression happen at derivation time:
  `already_extracted()` (element coverage >= 0.9 and IoU >= 0.5,
  `regions.py:360-374`), IoU dedupe at 0.85, and `MAX_PROPOSALS = 20`
  (`regions.py:25,698-707`).
- Review is always explicit. A suggestion opens `ElementsDialog` with a pending
  proposal (`apps/web/src/components/workspace/source-panel.tsx:484-493`); the
  dialog pre-fills coordinates/caption but the user still confirms the crop and
  insert. `create_element` stores the crop with `source='manual'`, the current
  `source_asset_id`, and `verified=0`
  (`backend/app/services/elements.py:194-215`). An element reports `stale` when
  its `source_asset_id` no longer matches the current page
  (`elements.py:56`).
- The renderer caches proposals with `staleTime: 0` and invalidates the list
  whenever an element is created or deleted
  (`apps/web/src/hooks/use-elements.ts:24-32,43-54,67-73,121-131`).
- A rerun never reuses or deletes the previous run; `start_ocr` inserts a new
  `ocr_runs` row (`backend/app/services/ocr.py:396-418`) and the latest by
  `created_at` wins. A source edit or rotation rebuilds the display asset with a
  **new** asset id (`backend/app/services/pages.py:846-865,903-915`), so the run
  no longer matches the page and proposals become `ocr_stale`.

### Why proposals are intentionally regenerated (the safety trade-off)

The current design chooses **no second source of truth**. The proposal is always
recomputed from (a) the latest successful OCR run, (b) the current source/render,
(c) the current rotation, and (d) the already-saved elements. That gives these
properties for free:

1. **No stale cache.** A rotation, crop/deskew/colour edit, or a fresh OCR run
   changes the inputs; the next request either recomputes or reports
   `ocr_stale`. There is no stored geometry that can drift from the page.
2. **No decision corruption.** Because nothing is stored, there is no
   "accepted/dismissed" flag that can outlive the evidence it referred to.
3. **No unbounded growth.** Proposals are not written per page per run, so the
   project database does not accumulate superseded rectangles.
4. **No provenance ambiguity.** Accepted content is stored exactly once, as an
   `elements` row with its own `source_asset_id` and stale flag; a proposal is
   never mistaken for verified content.

The cost is that there is **no cross-page queue and no remembered dismissal**:
the user reviews one page at a time, and a dismissed suggestion reappears on the
next fetch. For the 1.x single-page workspace that cost has been acceptable.

### What persistence would add, and what it would cost

Value it could add:
- A project-wide "review queue" of pending regions across pages.
- Remembered `dismissed`/`accepted` decisions that survive sessions.
- Progress counts ("12 of 30 regions reviewed").

Costs and risks:
- A new project-DB table + migration (schema version bump) and backup/restore
  compatibility.
- A second source of truth that must be invalidated on every source edit,
  rotation and OCR rerun, or it silently serves wrong geometry — exactly the
  failure the current design avoids.
- New API surface (list/aggregate/update-decision) and a new multi-page review UI
  with English **and** Burmese strings.
- Persisting AI-vision proposals would also persist paid-call output and provider
  metadata, extending cost/privacy and consent considerations
  (`ai_vision.py:54-59`).
- Acceptance still cannot be silent: batch "accept" would have to open the
  existing crop/insert review for each item, so the main saving is navigation,
  not approval.

### Design for stable identity/versioning (if persistence is ever approved)

A persisted proposal must be valid only while every input that produced it is
unchanged. The identity/versioning rule:

- **Row identity:** `(page_id, proposal_key)` where `proposal_key` is the
  existing `kind-x-y-width-height` (or `ai-kind-x-y-width-height`) string.
- **Provenance/version tuple stored on every row:**
  `ocr_run_id`, `source_asset_id`, `rotation`, `page_updated_at`, and for AI rows
  `provider`, `model`. `source_asset_id` is the page's display asset at derivation
  time (falling back to the original), matching the existing stale rule.
- **Validity check (read path):** a row is current only if
  `ocr_run_id == latest_succeeded_run(page)` **and**
  `source_asset_id == (page.display_asset_id or page.original_asset_id)` **and**
  `rotation == page.rotation`. Any mismatch marks it `stale` and hides it from the
  review queue; it is never offered and never auto-accepted.
- **Invalidation triggers:**
  - OCR rerun → prior rows for that page become `superseded` (kept for audit only
    if retention is explicitly chosen, otherwise deleted for that page).
  - Source edit / rotation / reset → `source_asset_id` changes → rows become
    `stale` automatically via the read-path check (no write needed).
  - Page delete → rows cascade with the page.
- **Decision states:** `proposed`, `accepted`, `dismissed`, `superseded`,
  `stale`. `accepted` is set only after the normal crop+insert flow creates the
  element, and records the resulting `element_id`; a batch action may select or
  navigate but must never set `accepted` without the per-item review.
- **Provenance preservation:** keep `reason`, `confidence`, `caption`,
  `block_ids`, and (for AI) `provider`/`model` on the row; record the deciding
  user and timestamp for `accepted`/`dismissed`. Note the current gap that
  `elements.source` is always `'manual'` (`elements.py:199`), so the proposal
  `reason` is not carried into the accepted element today; a persistence design
  should add an explicit `source_reason` to elements rather than overload
  `source`.
- **Batch-review safety:** the queue is read-only aggregation plus explicit
  per-item "review" that opens the existing `ElementsDialog`; there is no
  "accept all" and no silent insert. Dismissal is a user action on a specific,
  currently-valid row.

### Evaluation and decision

**Decision: do not persist region proposals in this task, and do not build batch
review yet.** Persisting does not clear the acceptance bar of "adds clear value
without weakening review safety or stale-state handling":

1. The only durable state batch review really needs already exists: an accepted
   region is an `elements` row with its own `source_asset_id` and stale flag, and
   a dismissed region is cheap to re-derive. Storing proposals would duplicate
   evidence that is already reproducible.
2. A proposal table introduces a second source of truth that must be invalidated
   on every source edit, rotation and OCR rerun. The current derived model makes
   stale geometry structurally impossible; persistence would reintroduce the
   exact class of bug the regeneration design avoids, for a navigation-only
   benefit (approval still must be per item).
3. This is an optional task that must not delay the Windows x64 release, and it
   touches schema/migration, API, UI, i18n and backup compatibility — a large,
   risky surface for a navigation convenience.

**Recommended next step if the owner wants cross-page review:** implement a
**read-only derived aggregation first** — a project-level endpoint that calls the
existing `propose_regions` per page and returns items tagged with the same
`ocr_run_id` + `source_asset_id` + `rotation` identity, rendered in a queue where
each item still opens the existing single-item review. That delivers cross-page
visibility with **no new table and no stale cache**. Persist only *user
dismissals* later, and only if demand is demonstrated. Persisting full proposal
rows should require an explicit owner decision and a migration plan.

### Invariants locked by regression tests

Because the decision keeps the derived model, the safety behaviour that any future
persistence must preserve is now pinned by tests in
`backend/tests/test_regions.py`:

- `test_region_proposals_become_stale_after_a_source_edit` — a geometry edit
  rebuilds the display asset; proposals must return `ocr_stale` and an empty
  list even though a successful OCR run exists.
- `test_region_proposals_follow_a_new_ocr_run` — a second OCR run with a
  different layout replaces the derived proposals; the response carries the new
  `ocr_run_id` and nothing from the first run is served as current.
- Existing `test_region_proposals_report_a_stale_ocr_run` (rotation) and
  `test_region_proposals_skip_regions_already_extracted` continue to guard the
  other invalidation paths.

### Files changed

- `docs/optional-future/PROGRESS.md` (new — this record)
- `backend/tests/test_regions.py` (two regression tests; no production code
  change)
- `ROADMAP.md`, `CHANGELOG.md`, `CONTINUE_PROMPT.md`, `PROJECT_MEMORY.md`
  (status/decision records)

No application source, schema, migration, API, UI, locale or dependency changed.
Proposals remain derived and non-persisted.

### Limitations and open questions

- No persistence means no cross-page queue and no remembered dismissals yet;
  that is an accepted trade-off, not a defect.
- The design above is not implemented, so none of its row/version rules are
  enforced by code today; the regression tests pin the *current* derived
  behaviour instead.
- The accepted-element provenance gap (`elements.source` is always `'manual'`,
  proposal `reason` not stored) is noted for a future change; it is out of scope
  here.
- AI-vision proposals remain ephemeral and paid; any persistence design must
  treat them separately from free local proposals.

### Verification commands and results

```powershell
# Baseline before any change
backend\.venv\Scripts\python.exe -m pytest backend/tests -q   # 450 passed in 270.69s
npm run test:web                                             # 59 files / 364 tests in 95.96s
npm run typecheck                                            # exit 0
npm run lint                                                 # exit 0

# Focused run for the new invariants
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_regions.py -q -k "stale or rerun or new_ocr_run or source_edit"
# 3 passed, 19 deselected in 5.54s (rotation stale + 2 new tests)

# Full suite after adding the two tests
backend\.venv\Scripts\python.exe -m pytest backend/tests -q   # 452 passed in 253.48s
npm run typecheck; npm run lint                               # both exit 0
```

Baseline and full-suite results are recorded in the session log below.

---

## Task 02 — PaddleOCR adapter evaluation (deferred)

Status: **deferred, not started.** PaddleOCR needs a large local install
(PaddlePaddle runtime plus models) and a benchmark environment. The prompt
requires a measured comparison against the real-scan corpus before any adapter
work, and availability alone is not justification. Running it here would consume
significant download/CPU/time without a controlled baseline, and this optional
task must not delay the release.

Plan when scheduled:
1. Install PaddleOCR in a throwaway virtual environment.
2. Run `backend/tests/fixtures/ocr-real/` through the existing benchmark harness
   with English and Burmese models, at the same modes used for Tesseract.
3. Record CER/WER, model size, CPU/RAM, licence, and offline-packaging cost.
4. Keep Tesseract as the default unless a repeatable, measured gain justifies the
   installer size and maintenance.

No benchmark result is claimed. The real-scan baseline in `docs/ocr-benchmark.md`
(Tesseract PSM 11: 22.64% overall CER) is the comparison target.

---

## Task 03 — Provider quota/billing introspection

**Inventory (verified):** `backend/app/services/ai_providers.py` defines 14
providers — Ollama (local), custom OpenAI-compatible, OpenAI, Anthropic, Gemini,
OpenRouter, Groq, Mistral, DeepSeek, xAI, Together, Fireworks, Cerebras and
Perplexity. The usage ledger already stores metadata only and separates a local
estimate via `estimated_cost_usd` + `cost_source`
(`backend/app/services/ai_usage.py`); it never claims provider-verified quota.

**Capability matrix** (official documented APIs only; endpoints verified
2026-11-28):

| Provider | Official usage/quota/billing API | Credential required | What it returns | Usable in-app? |
| --- | --- | --- | --- | --- |
| OpenAI | `GET /v1/organization/usage/*`, `GET /v1/organization/costs` | **Admin** key, not a normal project key | Token-usage buckets and daily costs (USD) | Only with an admin key; otherwise unavailable |
| Anthropic | `GET /v1/organizations/usage_report/messages` + `/v1/organizations/cost_report` (legacy), or `/v1/organizations/analytics/{usage,cost}` | **Admin/Analytics** key | Organisation usage and cost (USD) | Only with an admin/analytics key; otherwise unavailable |
| OpenRouter | `GET /api/v1/credits` (management key) and `GET /api/v1/key` (per-key limit/remaining) | Management key for credits; the normal key for `/key` | Total credits/usage; per-key limit and remaining | Narrowly usable via `/key` with the configured key |
| DeepSeek | `GET /user/balance` | Normal API key | Balance in CNY/USD (total/granted/topped-up) | Narrowly usable with the configured key |
| Gemini | No simple per-key usage API identified; usage comes from Google Cloud billing/quotas | Google Cloud credentials | Cloud billing/quota | Unavailable in-app |
| Ollama (local) | None (local server) | n/a | No billing; local ledger only | Show local ledger; never a quota |
| Custom OpenAI-compatible | Provider-dependent, not guaranteed | Provider-dependent | Unknown | Unavailable unless the server documents an endpoint |
| Groq, Mistral, xAI, Together, Fireworks, Cerebras, Perplexity | No simple documented per-key usage/billing endpoint identified in this pass | Console/dashboard | Console-only | Unavailable; do not scrape dashboards or infer from token history |

**Decision: report-only, no provider calls implemented.** The reliable endpoints
need admin/management keys that differ from the key the app already stores, the
rest have no verified official endpoint, and the task must not block the release.
If implemented later, keep it read-only and explicit: run only on user action,
use the user's own key, label data as **provider-reported**, **local estimate** or
**unavailable**, never scrape dashboards or infer quota from incomplete history,
and degrade to "unavailable" on any error. Start with DeepSeek `/user/balance`
and OpenRouter `/api/v1/key` (they work with the configured key); OpenAI and
Anthropic require an explicit admin-key opt-in. No code, dependency or test
changed.

---

## Task 04 — Windows installer footprint optimisation

**Measured** from the existing packaged 1.1.1 build in `dist/desktop-installer/`:

| Component | Measured size |
| --- | --- |
| Installer `DocuRebuild-1.1.1-setup.exe` | 204.19 MB |
| NSIS payload `@docurebuilddesktop-1.1.0-x64.nsis.7z` | 203.63 MB |
| Installed `win-unpacked` total | 646.64 MB |
| `resources/` | 289.81 MB |
| `resources/backend` (PyInstaller sidecar) | 108.61 MB |
| `resources/tesseract` | 178.10 MB |
| `resources/web` | 2.93 MB |
| Chromium `locales/` (55 `.pak` files) | 48.82 MB |
| `DocuRebuild.exe` | 238.40 MB |

Tesseract breakdown: `libtesseract-5.dll` 96.77 MB, `libicudt75.dll` 29.32 MB,
`tessdata/osd` 10.07 MB, `tessdata/mya` 4.43 MB, `tessdata/eng` 3.92 MB, plus
supporting DLLs. All three required languages are present.

**Candidate optimisations (measured potential, not applied):**
1. **Chromium locales.** Keep `en-US.pak` (578 KB) and drop the other 54 `.pak`
   files: potential saving ~48.26 MB installed. Requires
   `electronLanguages: ["en-US"]` (or `["en-US","en-GB"]`) in
   `apps/desktop/package.json` plus a rebuild to verify. App-level English/Burmese
   comes from the web bundle, not Chromium `.pak` files, but a packaged build must
   still be smoke-tested.
2. **Tesseract build.** The bundled UB-Mannheim runtime is dominated by
   `libtesseract-5.dll` and ICU. A slimmer compatible build could shrink it, but
   `eng`, `mya` and `osd` must be re-verified with the OCR benchmark and the
   desktop smoke suite before any swap.

**Applied and verified (2026-11-28).** Added `electronLanguages: ["en-US"]` to
`apps/desktop/package.json`, then ran the full rebuild and smoke cycle:

- `npm run desktop:dist` -> success (web build 14.21 s, PyInstaller sidecar,
  bundled Tesseract reused, NSIS installer built).
- `npm run smoke:desktop` -> passed 12/12 steps in 14 s; 0 console errors, 0
  uncaught exceptions.

Measured result:

| Metric | Before | After | Change |
| --- | --- | --- | --- |
| Installer `DocuRebuild-1.1.1-setup.exe` | 204.19 MB (214,103,864 B) | 195.92 MB (205,432,372 B) | -8.27 MB |
| Installed `win-unpacked` | 646.64 MB | 598.39 MB | -48.25 MB |
| Chromium `locales/` | 55 files, 48.82 MB | 1 file (`en-US.pak`), 0.56 MB | -48.26 MB |

The installer shrinks less than the installed footprint because the dropped
locale `.pak` files compress well inside the NSIS 7z payload. The new installer's
SHA-256 is
`BABE4B5949BF996701BC5BD3FB6F707D59FA33D1746B7E2E7FF4839ED484F649`
(unpublished; the published v1.1.1 asset is unchanged).

**Why this is safe:** Electron's native UI strings are English; the
application's English/Burmese UI and all OCR languages (`eng`, `mya`, `osd`) come
from the web bundle and bundled Tesseract, not Chromium `.pak` files. The desktop
smoke suite exercised launch, project creation, PDF import, source rendering,
OCR/review, edit/save/reopen, all four exports, backup/restore and clean shutdown
on the trimmed build. No OCR language, feature or security property was removed.

**Remaining footprint work (not done):** a slimmer Tesseract build (178.10 MB,
dominated by `libtesseract-5.dll` and ICU) would need a compatible build plus a
re-run of the OCR benchmark and smoke suite; it is deferred.

**Decision:** the locale trimming is applied and verified. The unreleased build
must not be published as 1.1.1; a future release (for example 1.1.2) should carry
it.

---

## Task 05 — macOS/Linux feasibility study

Scope: assess, do not implement. Windows x64 remains the supported target.

**Already portable:** the React/Vite client and FastAPI backend are OS-neutral;
`backend/app/core/config.py` uses `platformdirs.user_data_dir`; the backend
executable already drops the `.exe` suffix off Windows
(`apps/desktop/src/main.cjs:66-69`); `scripts/build-desktop.mjs` already uses
`python`/`python3` and `npm` per platform.

**Blockers for a build today:**
- `apps/desktop/package.json` defines only a `win`/NSIS target — no `mac`/`linux`
  targets, icons or signing config.
- `scripts/prepare-tesseract.mjs` downloads and extracts the Windows NSIS
  Tesseract installer and is Windows-only; macOS/Linux need per-platform
  Tesseract binaries/data.
- `apps/desktop/src/main.cjs` hardcodes `tesseract.exe` (`:120`, `:140`) and
  `icon.ico` (`:347`); macOS needs `tesseract` + `.icns`, Linux `tesseract` + `.png`.
- `stopBackend()` uses `taskkill /t` on Windows and `backend.kill()` elsewhere,
  which can leave a Tesseract child alive on POSIX; needs process-group handling.
- PyInstaller does not cross-compile: the sidecar must be frozen on each target
  OS, so a CI matrix (Windows/macOS/Linux runners) is required.
- `getDataDirectory()` builds `app.getPath("appData")/DocuRebuild/DocuRebuild`,
  which matches `platformdirs` on Windows but would double-nest and diverge from
  the backend default on macOS/Linux; reconcile so dev and packaged agree.
- macOS needs codesigning + notarization; Linux packaging (AppImage/deb) and
  sandbox/permission behaviour need their own testing.

**Platform matrix:**

| Concern | Windows x64 (current) | macOS | Linux |
| --- | --- | --- | --- |
| Electron target | NSIS (shipped) | dmg/zip + hardened runtime | AppImage/deb |
| Sidecar freeze | PyInstaller one-folder (shipped) | PyInstaller on macOS runner | PyInstaller on Linux runner |
| OCR runtime | bundled Tesseract 5.4 (`eng`/`mya`/`osd`) | build/homebrew Tesseract + tessdata | distro/build Tesseract + tessdata |
| Data location | `%LOCALAPPDATA%\DocuRebuild\DocuRebuild` | `~/Library/Application Support/...` (reconcile) | `~/.local/share/...` (reconcile) |
| Signing | unsigned (known gap) | Developer ID + notarization | optional |
| CI | Windows runner | macOS runner | Linux runner |
| Risk | low (baseline) | medium-high (signing, OCR binaries) | medium (packaging, OCR binaries) |

**Effort estimate (rough, not a commitment):** CI + build scripts +
per-platform Tesseract sourcing + path/icon/binary-name fixes + process-group
shutdown ≈ a few focused sessions; macOS signing/notarization adds an Apple
account and certificate; full QA (install/upgrade/OCR/export/backup) per platform
is the largest cost. **Decision: report only; no implementation until separately
approved.**

## Session log

- 2026-11-28: Task 01 evaluated. Documented the safety trade-off, the stable
  identity/versioning design, and the decision to keep proposals derived
  (no persistence, no batch-review UI). Added two regression tests that lock the
  stale/regeneration invariants. No production code changed. Baseline 450
  backend / 364 web tests passed; after the two new tests the backend suite is
  452 passed, web unchanged at 59 files / 364 tests, typecheck and lint clean.
- 2026-11-28: Tasks 03, 04 and 05 evaluated (report-only). Provider
  quota/billing capability matrix verified against official docs; installer
  component sizes measured from the existing 1.1.1 build; macOS/Linux platform
  matrix and blockers documented. Task 02 (PaddleOCR) deferred with a plan
  because it needs a heavy local install and a measured benchmark. No application
  code, schema, API, UI, locale or dependency changed.
- 2026-11-28: Task 04 applied. Added `electronLanguages: ["en-US"]` to the
  electron-builder config and ran the full `npm run desktop:dist` +
  `npm run smoke:desktop` cycle. Installer 204.19 -> 195.92 MB; installed
  646.64 -> 598.39 MB; Chromium locales 55 -> 1. Smoke passed 12/12 in 14 s with
  0 console errors. Only `apps/desktop/package.json` changed in the application;
  the build is unreleased.
