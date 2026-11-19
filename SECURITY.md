# Security policy

## Supported versions

DocuRebuild is in early development. Security fixes target the current `main` branch;
there is no long-term-support release yet.

## Reporting a vulnerability

Report privately through
[GitHub Security Advisories](https://github.com/minkhantthu2692-gif/DocuRebuild/security/advisories/new).
Do not open a public issue that contains a working exploit, an API key, a private
document, a database file or personal data.

Please include:

- The affected area (API, web client, storage, AI provider layer, backup/restore or
  export).
- Steps to reproduce and the impact you expect.
- The version or commit, operating system and relevant dependency versions.
- A minimal, redacted proof of concept if one is needed.

Never send a real API key. Rotate any credential that may have been exposed before
reporting.

## Scope

In scope:

- Authentication or authorization weaknesses in the local API.
- Path traversal, unsafe archive extraction or asset-path escapes.
- Remote AI endpoint validation, HTTPS/consent bypass, SSRF or credential leakage.
- Plaintext API key exposure in the database, logs, API responses, exports or Git.
- Cross-site scripting, unsafe link handling or content injection in the web client.
- Data loss in project storage, backup, restore or migrations.
- Dependency vulnerabilities with a practical impact on the application.

Out of scope:

- Model quality, hallucinations or inaccurate OCR without a security consequence.
- Provider pricing, quota or billing disputes.
- Vulnerabilities that require an already-compromised machine or data folder.
- Social engineering and physical access.

## Local data and credentials

- API keys are stored in the local encrypted vault (`secrets/ai_keys.enc` plus
  `secrets/ai_keys.key`). Anyone who can read the data folder and master key can use
  them; file-system permissions are part of the security boundary.
- Project documents, databases, imported files, backups and exports are user data.
  They are never uploaded by the application and must not be committed to Git.
- The local API binds to loopback by default. Exposing it to a network requires the
  user's own reverse proxy, authentication and TLS; the project does not provide a
  public hosting configuration.

## Disclosure

Please allow time to investigate and release a fix before public disclosure. We will
credit reporters who want to be named, and we will not publish private data or
credentials from a report.
