# Pilot Playbook

## Goal and eligibility

Run five consented pilots for at least two monthly closes. Do not publish aggregate claims until the underlying pilot records are complete and reviewed. Select a mix of retail, services and multi-client accounting users who can provide a ledger export, bank statement, opening/closing balances and prior manual closing time.

## Exact onboarding steps for each pilot

1. Obtain written consent, data-processing expectations, testimonial preference, named owner/accountant and supported currency.
2. Create the user's account; have the owner create the workspace. Invite only the assigned accountant/manager and verify roles with a second login.
3. Download `/api/v1/accountant/pilot/sample-template.csv`. Complete the readiness checklist: ledger export, bank statement, chart/category context, opening balance, closing balance, receivables/payables aging, currency, period, prior-close timing, and backup retained by customer.
4. Record setup start/end and the customer's independently reported manual closing minutes. Never estimate missing values.
5. Upload one client at a time. For XLSX, put the intended financial sheet first or upload sheets separately. Confirm mapping, currency, signs, dates, missing COGS and source totals before approval.
6. Clean only through reviewed corrections; preserve original values. Reconcile bank to ledger and record matched, possible and unmatched counts. Review duplicates, missing deposits, refunds/reversals and all exceptions.
7. Run calculation and validation. Independently compare revenue, COGS, expenses, profit, cash movement, AR/AP and trial balance. Resolve or document every failure; do not close through a blocker.
8. Start monthly close, complete its checklist, generate the report, inspect evidence links, and visually review any Bengali/Arabic web report. Do not deliver localized PDF until manual QA passes.
9. Record Ledgerly closing minutes, validation failures, corrections, report completion and feedback with `PUT /api/v1/accountant/workspaces/{workspace_id}/pilot/{YYYY-MM}`.
10. Export/review `GET /api/v1/accountant/workspaces/{workspace_id}/pilot`; obtain separate testimonial permission. Repeat next month and mark repeated usage only after it occurs.

## Stop conditions

Stop and escalate on cross-workspace visibility, unexplained balance variance, altered originals/audit history, wrong currency, unvalidated calculations, backup failure, or a report containing another client's data.
