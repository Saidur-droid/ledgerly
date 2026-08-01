# Pilot Metrics Template

Use one row per workspace and closing month. Blank means unknown—not zero.

| Field | Definition |
|---|---|
| Workspace / period | Tenant ID/name and `YYYY-MM` close |
| Setup minutes | Elapsed human time from onboarding start to ready-to-upload |
| Manual close minutes | Customer-reported comparable close before Ledgerly |
| Ledgerly close minutes | Elapsed human time from upload start through delivered report |
| Matched / possible / unmatched | Final reconciliation classifications |
| Accuracy % | `matched / (matched + possible + unmatched) × 100`; not a claim of accounting correctness |
| Validation failures | Count of failed/blocking validations |
| Corrections required | Human-approved corrections made during close |
| Report completed | Delivered report exists and was reviewed |
| Repeated monthly usage | True only after a later monthly close is completed |
| Feedback | User's own words; do not rewrite into a testimonial |
| Testimonial permission | Explicit separate permission, default false |

Time saved is calculated as `manual close minutes − Ledgerly close minutes`. Do not fill unknown times, extrapolate results, or average incomparable periods.
