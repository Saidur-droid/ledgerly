# Known Production Limitations

- Pilot release only; not a substitute for professional accounting review and not approved for tax filing, audit opinion, regulated advice, or autonomous journal posting.
- CSV/XLSX/JSON uploads are capped at 500 normalized rows; only the first XLSX sheet is ingested.
- PDF support requires extractable text. Scanned statements, complex tables, password-protected PDFs and OCR are unsupported.
- Bengali and Arabic web text is UTF-8/RTL-aware. PDF font embedding, Arabic shaping and bidi layout are not production-approved; perform visual QA or export XLSX/web.
- Currency conversion is not performed. Mixed-currency data must be separated or converted by the user with documented rates.
- Floating-point storage can produce edge rounding; compare source totals and trial balance before delivery.
- Automatic reconciliation is exact-rule oriented; duplicates, reversals, split payments, fees and date shifts require review.
- Rate limits are local to one API process. Share links are bearer links; use short expiry and revoke promptly.
- There is no self-service password reset, MFA, SSO, provider-managed retention policy, OCR, or automated disaster-recovery drill.
- Vercel/Render private-repository access and provider backup restoration require manual verification by the deployment owner.
