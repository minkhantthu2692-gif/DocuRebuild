# Contributing to DocuRebuild

Thanks for helping. DocuRebuild is a local-first document reconstruction workspace, so
every change must keep user data on the user's machine and keep AI output reviewable.

## Before you start

- Read [`AGENTS.md`](AGENTS.md) for the permanent product and engineering rules, and
  [`docs/architecture.md`](docs/architecture.md) for the current module layout.
- Inspect the existing code before changing an area. Follow the surrounding naming,
  style and patterns instead of introducing a parallel implementation.
- Open an issue first for a large change, a new dependency, a database migration or
  anything that affects stored user data.

## Setup

```bash
npm install
python -m venv backend/.venv
# Windows
backend\.venv\Scripts\activate
# macOS / Linux
source backend/.venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
npm run dev
```

Tesseract 5 with `eng` and/or `mya` traineddata is optional but needed for local OCR.
No AI provider or credential is required to develop or test the application.

## Checks

Run these before opening a pull request:

```bash
npm run typecheck
npm run lint
npm run test:web
npm run test:api
npm run build
```

The same checks run in GitHub Actions. Backend AI tests use a loopback stub server and
never contact a real provider, so CI needs no API key.

## Rules that are not negotiable

- **No secrets or user data in Git.** Never commit API keys, `.env` files, the
  encrypted vault, databases, imported documents, page images, backups or exports.
  Report a credential leak through [`SECURITY.md`](SECURITY.md), not a public issue.
- **Local-first.** Do not add a mandatory cloud database, storage service or account.
  Remote AI is optional, user-configured and consent-gated.
- **Free usage first.** Local Ollama or a local OpenAI-compatible server must keep the
  AI features usable without payment. A paid or remote action needs explicit approval;
  never claim a provider or model is free without verification.
- **Proposals, not facts.** AI and heuristic results stay unverified until a person
  accepts them. Never invent a table cell, equation symbol, figure label or number,
  and never silently overwrite original content.
- **Design system.** Use tokens and shared components; do not hardcode colours,
  spacing, radii, sizes or blur values.
- **Internationalization.** English is the default language and Burmese is supported.
  Add every user-facing string to `en` and `my` locale files and keep the namespaces
  in sync; do not concatenate translated fragments.
- **Migrations and compatibility.** Change the database with an Alembic migration,
  keep existing rows, and make a migration safe to run on an existing data folder.
- **Documentation.** Update `README.md`, `docs/architecture.md` and
  `docs/roadmap.md` when behaviour, settings, storage or the API changes.

## Pull requests

- Keep a pull request focused; describe the problem, the change and its limits.
- List the checks you ran and any behaviour you could not verify.
- Add or update tests for new behaviour, including failure paths and review safety.
- Use synthetic or redacted content in screenshots.
- Do not push to the authoritative remote, rewrite history or force-push without the
  owner's explicit authorization.
