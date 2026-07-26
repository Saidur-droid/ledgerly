# Security policy

Ledgerly may process commercially sensitive information. Treat every upload as confidential.

## Reporting

Please report a suspected vulnerability privately to the repository owner. Include the affected surface, reproduction steps, impact, and any suggested mitigation. Do not open a public issue containing customer data, credentials, or exploit details.

## Supported version

Security fixes target the latest commit on `main`.

## Product boundary

This MVP includes encrypted transport at the hosting layer, Argon2 password hashing, server-side user isolation, bounded upload types, secret separation, and scoped AI context. A public launch should additionally complete malware scanning, rate limiting, audit logging, backup recovery tests, dependency scanning, and an independent security review.
