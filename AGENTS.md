# DocuRebuild — permanent instructions for AI coding agents

This file is the working agreement for every AI agent that changes this
repository. Read it completely before editing code. It describes the product,
the architecture that actually ships, the rules that must not be broken, and how
to verify work.

DocuRebuild is a **local-first, AI-assisted document reconstruction workspace**.
Users import scanned pages or PDFs, review OCR text, reconstruct tables, figures
and equations, edit the document, and export Markdown, plain text, Word or PDF.
The supported 1.0 distribution is a **Windows desktop application** built with
Electron and a bundled Python sidecar. Mobile, PWA and device pairing are out of
scope for 1.0.

## Start here

| Document | Purpose |
| --- | --- |
| `PROJECT_MEMORY.md` | Current architecture, decisions, status and handover context |
| `ROADMAP.md` | Completed work, remaining gaps and deferred features |
| `CHANGELOG.md` | Release history and user-visible changes |
| `docs/architecture.md` | Modules, storage layout, data model and API surface |
| `docs/ocr-benchmark.md` | OCR accuracy methodology and measured results |
| `PROJECT_COMPLETION_REPORT.md` | Delivery and QA record; §§16-19 are the current post-v1.1.1 status and the 1.1.2/1.1.3/1.1.4 build verification |
| `CONTINUE_PROMPT.md` | Single paste-ready handover: completed tasks, remaining work and session rules (replaces `Prompt.md`) |
| `CONTRIBUTING.md` | Human contributor setup and checks |
| `SECURITY.md` | Vulnerability reporting and credential scope |

If this file and an older document disagree, the code and `PROJECT_MEMORY.md`
win; update the stale document in the same change.

## Repository map

```text
apps/web/            React + TypeScript + Vite client (Tiptap editor, i18n)
apps/desktop/        Electron main process, preload bridge, installer config
backend/             FastAPI application, services, Alembic migrations, Pytest
packages/            Design tokens and shared TypeScript contracts
scripts/             Desktop payload build and OCR fixture tooling
docs/                Architecture, benchmark and detailed phase history
CONTINUE_PROMPT.md   Paste-ready handover for a new chat or agent
dist/                Build output (git-ignored)
```

Key runtime files:

- `apps/desktop/src/main.cjs` — window, sidecar lifecycle, token, CSP, shutdown.
- `apps/desktop/src/preload.cjs` — exposes only the API token and build metadata.
- `backend/desktop_server.py` — sidecar entry point, loopback-only binding.
- `backend/app/main.py` — app factory, auth middleware, SPA serving.
- `backend/pyinstaller.spec` — one-folder sidecar packaging.
- `apps/desktop/package.json` — electron-builder/NSIS configuration.

## Product principles

1. **Local-first.** Projects, databases, documents and assets stay on the user's
   machine. Do not add Firebase, Supabase or mandatory third-party cloud
   storage/database services.
2. **Free usage first.** The application must remain useful without paid AI
   subscriptions or paid API keys.
3. **User-controlled.** Users choose processing methods, AI providers, models,
   workflows, preferences and behaviour.
4. **Accuracy first.** Preserve original information. Never silently invent,
   replace or approve uncertain extracted content.
5. **Manual + AI.** Every important AI-assisted workflow has a reasonable manual
   alternative.
6. **Modular architecture.** Keep features, services, processing engines and
   provider integrations independent and maintainable.
7. **Production quality.** Prioritise reliability, security, accessibility,
   maintainability and a polished experience.

## Free usage rules (mandatory)

- Support local/offline processing wherever technically practical.
- Prefer genuinely free and locally executable solutions before paid services.
- Optional free-tier API providers are allowed; paid providers are always
  optional.
- Never silently trigger a paid request or paid operation. Require explicit user
  approval before a paid service is used or a configured spending limit is
  exceeded.
- Let users configure usage limits, preferred providers, fallback providers and
  task-specific AI settings.
- Fail gracefully when an API is unavailable, rate-limited or out of quota.
- Do not advertise a provider or model as free unless its current pricing and
  limitations are verified. Free quotas are not permanent.
- The core application must work offline without AI credentials, subject to
  local processing capabilities.

## Accuracy and AI reliability

- AI output is a proposal until the user verifies it where accuracy matters.
- Preserve original values and track proposed changes.
- Record provider, model, task, timestamp and verification status.
- Never fabricate missing table cells, equation symbols, figure labels or
  numerical information.
- Identify uncertain results and allow manual correction.
- Prefer structured, deterministic reconstruction over generative image
  replacement when exact information must be preserved.
- OCR text, AI text and user corrections must stay distinguishable in storage,
  the UI and exports.

## Architecture rules

- Keep the frontend, backend, database, processing engines and AI providers
  separated. Use interfaces/adapters for interchangeable engines and providers.
- Never expose API keys or credentials in frontend code, logs, commits or
  plain-text storage. Desktop credentials live in the encrypted local vault.
- Preserve imported originals as immutable source assets. Every derived image is
  reproducible from the original plus stored edit parameters.
- Use Alembic migrations for schema changes; never rewrite an existing migration
  that a user database has already applied.
- Handle errors, cancellation, retries, large files and background processing.
- Keep application data and project data portable and outside the repository.
- Use dynamic provider/model discovery instead of hardcoded model catalogues.
- Avoid unnecessary dependencies and duplicated implementations.
- Update documentation and tests with every behaviour change.

### Desktop boundary

- The backend binds `127.0.0.1` only and receives a random per-launch token.
- With `DOCUREBUILD_API_TOKEN` set, every `/api` request must present
  `Authorization: Bearer <token>`. Unset behaviour is for development and tests
  only.
- The renderer is sandboxed with `contextIsolation`, no Node integration and a
  strict CSP. Do not add a generic IPC bridge.
- The renderer loads the built client from the same origin as the API. Keep it
  that way: a separate origin would need a CORS exception and weakens the token
  boundary.
- The token is generated by the shell, passed to the sidecar through its
  environment, and exposed to the page only through the preload bridge. It must
  never be written to disk, a command line, a log or the bundle.

## UI and UX rules

- Use the design system in `packages/design-tokens` and the existing component
  primitives. Do not hardcode colours, font sizes, spacing, dimensions, radii or
  blur values; add or adjust tokens instead.
- Respect Light, Dark and System themes and the saved appearance settings.
- Keep the interface clean, minimal, polished and responsive.
- Use progressive disclosure for advanced settings and avoid meaningless
  options. Every setting must have a real effect, validation and persistence.
- Maintain consistent interactions and feedback, including loading, empty, error,
  disabled and success states.
- Support keyboard navigation, visible focus, accessible names and WCAG AA
  contrast. The token contrast test guards the current palette.
- The desktop workspace is the supported 1.0 layout. Do not reintroduce the
  mobile panel switch or camera/PWA flows without an approved scope change.

## Internationalization

- English is the default language; Burmese is supported.
- No hardcoded user-facing strings in components. Add keys to both
  `apps/web/src/i18n/locales/en` and `.../my`; key-parity tests must pass.
- Keep translations separate from logic. Language switching happens live.
- Ensure Burmese Unicode renders and is typed correctly. Never perform automatic
  Zawgyi/Unicode conversion.
- Use locale-aware dates, numbers and formatting. Layouts must tolerate longer
  translations and different scripts.
- Adding a language must not require redesigning the localization layer.

## Data, backup and GitHub safety

- Treat GitHub as source-code and documentation backup, **not** as storage for
  user documents. Never commit imported books, photographs, PDFs, extracted
  content, API keys, local databases, `dist/` output or personal assets.
- Keep `.gitignore` current; verify `git status --ignored` before a release.
- Never overwrite, delete, force-push or rewrite remote history without explicit
  user authorisation. Inspect branches, remotes and working-tree state first.
- Never assume a repository URL grants write permission. Use the credentials
  already configured in the environment and never print or commit them.
- Explain what will be uploaded before an externally visible or sensitive
  operation. Prefer reversible operations.
- User data lives in `%LOCALAPPDATA%\DocuRebuild\DocuRebuild` (or
  `DOCUREBUILD_DATA_DIR`); window state and logs live in
  `%APPDATA%\DocuRebuild`. Uninstalling must not delete projects.

## Development workflow

1. Inspect the repository and existing changes before editing. Treat unfamiliar
   work as potential user work; investigate before deleting or overwriting it.
2. Implement in small, coherent changes that follow existing patterns.
3. Do not replace real implementations with mocks, and do not skip unfinished
   functionality silently.
4. Run the relevant checks and verify actual behaviour before claiming success.
5. Keep code, documentation and observed behaviour synchronised.
6. Update `CHANGELOG.md` for user-visible changes and `PROJECT_MEMORY.md` /
   `ROADMAP.md` when status, architecture or decisions change.
7. Never commit or push unless the user asks. Never claim a push, release or
   download succeeded without verifying it.

### Commands

```powershell
# Install
npm ci
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# Develop (API :8000, Vite :5173)
npm run dev

# Checks
npm run test:web
backend/.venv/Scripts/python -m pytest backend/tests -q
npm run typecheck
npm run lint
npm run build

# Desktop payload and NSIS installer
npm run desktop:build      # web + PyInstaller sidecar + Tesseract
npm run desktop:dist       # adds electron-builder packaging
npm run desktop:start      # run the Electron shell against dist/desktop

# OCR benchmark
backend/.venv/Scripts/python -m app.ocr_benchmark --help
```

Bundled Tesseract is required for OCR tests and for `desktop:build`; the build
script downloads and extracts it without administrator rights. CI installs
Tesseract with apt.

## Release rules

- The version lives in the root, web, desktop and shared package manifests, in
  `backend/app/__init__.py` and `backend/pyproject.toml`. Keep them equal; the UI
  reads the version from `/api/health`.
- Build the installer from a clean tree, record its size and SHA-256, and smoke
  test install → launch → create/import → OCR → export → backup/restore →
  uninstall (data retained) → reinstall.
- Publish release notes that state the supported platform, install steps, what
  the build contains and every known limitation. Do not describe deferred work
  as shipped.
- A GitHub Release asset must be verified by downloading it and checking the
  published checksum. Never publish a different file from the one that was
  tested.

## UI reference

`mockup-reference-ui.png` communicates visual direction only. Do not reproduce
it literally. Evaluate every element against real functionality; add what is
missing, remove what is redundant or misleading, and preserve the intended
clean, professional, subtly glassy workspace feel. When the reference conflicts
with usability, accessibility, responsiveness or technical reality, the
application wins.

## Do not

- Introduce cloud databases or mandatory accounts.
- Add silent paid AI calls, hidden telemetry or background uploads.
- Hardcode secrets, credentials, user paths or design values.
- Store user content in Git, logs or the AI usage ledger.
- Break the local-only API boundary or the token check.
- Claim a test, build, push or release succeeded without evidence.
