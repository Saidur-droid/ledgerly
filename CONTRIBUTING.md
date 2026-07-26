# Contributing to Ledgerly

Ledgerly is explanation-first software. Changes should make business data easier to understand without overstating what the data proves.

1. Create a focused branch from `main`.
2. Keep domain logic out of route handlers and UI components.
3. Add tests for parsers, score changes, guardrails, and API behavior.
4. Run the full quality gate before committing.
5. Use Conventional Commits such as `feat(pulse): explain confidence factors`.

Do not introduce advice-generating prompts, hidden score factors, or logging of uploaded business rows. Security issues belong in the private process described in `SECURITY.md`, not a public issue.
