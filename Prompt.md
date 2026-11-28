# Reset OpenCode CLI, then resume DocuRebuild

Short runbook + paste-ready prompt. Replaces the old 1,196-line product spec,
which is still recoverable from git:

```powershell
git show e7966d4:Prompt.md
```

No new project is created. This repository already exists; the work resumes from
the committed state.

## 1. Reset (PowerShell)

Stops the background service first so the session database is not held open:

```powershell
opencode service stop
Remove-Item -Recurse -Force "$env:USERPROFILE\.local\share\opencode"   # sessions, opencode.db, logs
Remove-Item -Recurse -Force "$env:USERPROFILE\.cache\opencode"         # cache, models.json
Remove-Item -Recurse -Force "$env:USERPROFILE\.local\state\opencode"   # service registration, prompt history
```

Kept on purpose: `~/.config/opencode` (your `opencode.jsonc`, service config,
plugins). That is why the next start has no configuration errors. Delete it too
only if you also want to lose your global settings.

Verify:

```powershell
opencode debug paths      # shows the recreated data/cache/config/state paths
opencode service status
```

Then run `opencode` from `C:\Users\minkh\OneDrive\Desktop\DocuRebuild`.

**Effect:** all previous OpenCode sessions are gone, so there is no conversation
to resume. The DocuRebuild work itself is untouched — git and the handover docs
carry it.

## 2. Paste this into the new session

```text
Continue DocuRebuild from the documented state. Read AGENTS.md, CONTINUE_PROMPT.md
and PROJECT_MEMORY.md; opencode.jsonc already loads the progress files. Do not start
a new project and do not re-initialise the repository.

Run git status -sb and git log --oneline -10 first; the tree is clean, main is 2
commits ahead of origin/main, and e7966d4 is a docs/config commit. Treat unfamiliar
work as the owner's work.

Verify the baseline before changing code:
  backend\.venv\Scripts\python.exe -m pytest backend/tests -q   # 450 passed
  npm run test:web                                             # 364 tests / 59 files
  npm run typecheck
  npm run lint

Then pick exactly ONE item from the "Remaining work" table in CONTINUE_PROMPT.md.
Next is 03_OPTIONAL_FUTURE/01_Persisted_Region_Proposals_Batch_Review.md; read that
prompt file in the prompt pack and follow its acceptance criteria. That task is
design/evaluation first — no persistence change until the design and stale-safety
trade-off are written down.

Use disposable test data. Add tests and both English and Burmese locale keys for any
UI string. Update the progress docs, ROADMAP.md, CHANGELOG.md and CONTINUE_PROMPT.md
with exact commands, results and limitations. Commit only that task, stop after it,
and report what remains. Do not publish a release and do not claim any test, build or
push result without evidence.
```
