# Payment Reconciliation Pipeline: Testing Summary

**Scope:** automated testing of the gateway-to-bank reconciliation pipeline (`payment-reconciliation-pipeline`, commit e48ef63).
**Data:** the repository's synthetic dataset (25,000 transactions, 24,750 bank settlements). No real payment data and no live systems were used, so dollar figures below are test-data figures.

## Bottom line
The pipeline applies its documented rules correctly at every boundary we tested, but **it does not guarantee that one bank settlement pays only one transaction**. The same bank payment can be counted against several transactions. Until that is fixed, the "matched" totals and the missing-money figures cannot be relied on as a financial control.

## Results at a glance
| | |
|---|---|
| Automated checks | **135** |
| Passed | **119** |
| Failed unexpectedly | **0** |
| Checks that demonstrate a confirmed defect | **16** (covering 8 defects) |
| Existing project tests not run through their own tool | 14 (needs BigQuery; see below) |
| Application code changed | **None** |

A repeat run gave identical results. To check the tests can catch mistakes, we deliberately broke the pipeline's rules 16 different ways on temporary copies. All 16 were detected.

## Defects found
| ID | Severity | What it means |
|---|---|---|
| PAYREC-001 | **Critical** | A bank settlement can be assigned to multiple transactions. Matched settlement dollars total $6,258,100.98 against $6,203,402.33 actually received, an excess of **$54,698.65**. This also helps explain why the pipeline finds only 106 of the 1,000 missing payments planted in the test data. |
| PAYREC-002 | High | 16 negative bank amounts (−$173.26 total, such as refunds or reversals) are silently dropped. The project's own "no negative amounts" test passes only because the records are removed before it looks. |
| PAYREC-003 | Medium | About 1,385 bank settlements (about $357,600) appear in no output. We need you to confirm whether this is intended. |
| PAYREC-004 | Medium | When two candidates tie, the choice is arbitrary. Two identical runs picked different settlements for 104 transactions, so results are not reproducible at settlement level. |
| PAYREC-005 to 008 | Low | A credential-file path is hard-coded in 13 scripts (no secret is exposed). One root-level script breaks a bare `pytest`. The README describes ranking the SQL doesn't do. One model is unused. |

## Not tested or blocked
- **dbt and BigQuery were not available.** The 14 existing dbt tests were re-run as equivalent SQL and all passed, but that is not the same as running dbt. The local test engine reproduces your committed BigQuery export's results exactly (same counts in every category), which gives good, not complete, confidence.
- **Not implemented in the pipeline, so not testable:** currencies, fees, taxes, refunds, chargebacks, split settlements, run IDs and audit logs.
- The README's accuracy figures (95.82%, $267,169 exposure) rely on private files that aren't in the repository and could not be verified.

## Decisions needed
1. **Confirm that one settlement may pay at most one transaction.** If yes, PAYREC-001 is the top fix.
2. **Decide how negative settlements should be treated.**
3. **Decide whether unmatched bank settlements should be reported.**
4. **Approve the small, low-risk fix for PAYREC-004** (add a deterministic tiebreaker). It leaves classifications unchanged.

No fixes were applied because 1–3 change business behaviour and need an owner's decision.

## Where to find detail
`docs/claude_testing/`: `final_testing_report.html` (full report, opens in any browser), `defect_report.md` (reproduction steps per defect), `recommended_fixes.md`, `execution_report.md` (exact commands and counts).
To rerun: activate `.venv`, then `python -m pytest tests`.
