# 5 · Integrity: can this field report be trusted?

**Role:** engineered · **Spec:** §6, §11 · **Status:** not started

The secure-field-system area has two halves:

- **Backend (already started):** authentication, roles, revocation, append-only audit log. Signed reports and the offline queue come next.
- **This module, the AI half:** spots field reports and accounts that *look* wrong even when the login is valid. A compromised account or a careless report still passes authentication.

## In → out

| In | Out |
|---|---|
| Field report + its account's history | Integrity flags for human review, e.g. `gps_jump`, `location_text_mismatch`, `submission_burst`, `media_reused`, `timestamp_skew` |
| | Per-account anomaly score (account-level only, no profiling of the public) |

## Planned checks

1. **Signature and hash verification** of submitted reports (with the backend)
2. **GPS plausibility:** impossible travel between consecutive reports, GPS far from the place named in the text
3. **Behaviour anomalies:** sudden bursts, unusual hours, report text copied from public posts
4. **Media checks:** reused or much older photos (shares hashing with `media/`)

Flags never block a report automatically. They mark it for human review.

## Done when

Each check has tests, and flag precision is measured on simulated compromised-account scenarios.
