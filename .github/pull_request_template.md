## Summary

Describe the change and the problem it solves.

## Scope

- [ ] Backend
- [ ] Web client
- [ ] Shared types or design tokens
- [ ] Documentation
- [ ] CI, security or repository configuration

## Verification

List the commands you ran and their results.

```text
npm run typecheck
npm run test:web
python -m pytest backend/tests -q
```

## Data and security checklist

- [ ] No API keys, tokens, private documents, database files or personal data are included.
- [ ] New user-facing strings exist in English and Burmese (or the change is not user-facing).
- [ ] Local-first behaviour is preserved; no mandatory cloud service was introduced.
- [ ] AI output still requires review and is never silently inserted.
- [ ] Paid or remote AI behaviour requires explicit consent or approval.
- [ ] Documentation is updated when behaviour, settings or architecture changed.

## Screenshots

Optional. Use synthetic content only.
