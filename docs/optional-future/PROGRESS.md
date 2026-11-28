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
| 02 | PaddleOCR adapter evaluation | not started | Benchmark report first |
| 03 | Provider quota introspection | not started | Capability matrix first |
| 04 | Windows installer footprint optimisation | not started | Measure first |
| 05 | macOS/Linux feasibility study | not started | Report only |

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

## Session log

- 2026-11-28: Task 01 evaluated. Documented the safety trade-off, the stable
  identity/versioning design, and the decision to keep proposals derived
  (no persistence, no batch-review UI). Added two regression tests that lock the
  stale/regeneration invariants. No production code changed. Baseline 450
  backend / 364 web tests passed; after the two new tests the backend suite is
  452 passed, web unchanged at 59 files / 364 tests, typecheck and lint clean.
