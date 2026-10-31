# Defect Report

All defects reproduced locally with the repository's unmodified SQL (harness: `tests/harness/dbt_local.py`). **No application source was changed**; all fixes are proposals (see recommended_fixes.md) because each one alters matching semantics that need owner confirmation.
Monetary impact is stated only where computed from test evidence on the committed synthetic dataset (not real money).

## PAYREC-001 — A bank settlement can be assigned to multiple gateway transactions (double counting)
| Field | Value |
|---|---|
| Severity / Priority | **Critical** (causes double counting of settlement dollars; undetected by any repo test) / P1 |
| Stage / component | Matching — `models/intermediate/int_candidate_matches.sql`, `int_match_selection.sql` (rank is per `txn_id` only) |
| Preconditions | ≥2 gateway txns, same merchant, amounts within tolerance of the same settlement, inside its window |
| Input | Synthetic: T1 100.00 @ t0, T2 100.00 @ t0+1h, one settlement S1 100.00 @ t0+1d, merchant Acme |
| Reproduce | `pytest tests/reconciliation/test_matching_rules.py::test_RC016_a_settlement_is_not_assigned_to_two_transactions --runxfail`; at scale `…::test_RG001… --runxfail` |
| Expected | A settlement funds at most one transaction; T2 → `missing_settlement` (RC016b). Matched settlement dollars can never exceed bank dollars. |
| Actual | Both T1, T2 → `matched`/S1. Full data: 6,258,100.98 settled dollars attributed in `mart_reconciliation` vs 6,203,402.33 positive bank dollars → **$54,698.65 more than exists**; ~1,445–1,455 settlements reused (varies per run, PAYREC-004), ≈ $412–414k counted more than once (settlement amount × extra assignments). |
| Business / data impact | Matched/“clean” counts are overstated; the true shortfall is hidden — injected-missing recall is only 106 of 1,000 (CT015), 862 missing txns are labelled amount_mismatch because they take another payment’s settlement; README’s “$267k vs $21k” exposure gap is consistent with this root cause. |
| Evidence | evidence/runxfail_output.txt; tests RC016, RC016b, RG001, RG002, RG003 |
| Root cause (confirmed) | `row_number() over (partition by txn_id …)` – no exclusivity constraint across transactions on `settlement_id`. |
| Proposed fix | Greedy/global one-to-one assignment (rank all candidate pairs globally by amount_diff, days, ids; accept a pair only if both txn and settlement are unassigned; iterate). Requires owner confirmation of A1. |
| Fix status | **Not fixed** (semantic change; expectation requires confirmation; no scoped SQL-only fix without altering every downstream metric) |
| Regression test | RC016, RC016b, RG001, RG002 (strict xfail → will fail loudly when fixed so xfail markers get removed) |
| Retest | Still failing (expected) |

## PAYREC-002 — Negative settlements silently dropped; repo’s non-negative test is vacuous
| Severity / Priority | **High** (refund/reversal-like bank records omitted without a trace; a control reports a false pass) / P2 |
|---|---|
| Component | `tests/assert_settled_amount_not_negative.sql` (evaluates the mart, after the join already excluded negatives), `int_candidate_matches.sql` tolerance join |
| Input | `data/bank_settlements.csv`: 16 rows, total −173.26 (e.g. STL003051, STL021258, STL006121); fixture: T1 10.00 vs S1 −10.00 |
| Expected | The rule “settled_amount must never be negative” flags them (or they are routed to an exception output). |
| Actual | dbt test returns 0 rows; the negative settlements appear in no output (RG004: 16 in source, 0 flagged). Repo semantics for refunds/reversals/chargebacks are undefined. |
| Impact | −$173.26 of bank movement unexplained in this dataset; in real data an unhandled refund/chargeback feed. |
| Evidence | DQ007, RC020, RG004 |
| Proposed fix | Run the non-negative test on `stg_bank_settlements`; add an explicit exception category for negative/zero settlements. Requires A2 confirmation. Fix status: Not fixed. |

## PAYREC-003 — Bank-side orphans are not reported
| Severity / Priority | **Medium** (incomplete exception information; requires confirmation of intent) / P3 |
|---|---|
| Component | Output design: the pipeline is gateway-driven; no model lists settlements without a transaction |
| Actual | 1,383–1,387 settlements (≈ $357.6k) are linked to no transaction and appear in no output (RG005); partly the consequence of PAYREC-001/004 (second half of true duplicates, mis-assigned settlements). |
| Expected | Every bank record is accounted for (matched / duplicate / orphan). *Assumption A6.* |
| Proposed fix | Add `mart_unmatched_settlements` (anti-join). Fix status: Not fixed. Tests: RC019, RG005 |

## PAYREC-004 — Non-deterministic selection among equally ranked candidates
| Severity / Priority | **Medium** (changes which settlement/exposure is reported; categories stable) / P3 |
|---|---|
| Component | `int_candidate_matches.sql` rank `order by amount_diff asc, days_to_settle asc` (no final tiebreaker); also `mart_review_queue` qualify on `gateway_amount desc` |
| Evidence | Same SQL, same data, same engine, two runs → 104 transactions select different settlements (RG003b; reused-settlement count 1,444–1,455 across runs); input row order changes the pick (RC017); committed BigQuery export vs local run differ in 403 selected settlement_ids while all category labels agree (RG006). |
| Impact | Reports are not reproducible at settlement level; downstream joins on settlement_id vary. |
| Proposed fix | Append `settlement_id` (and `txn_id` for the queue) to the ORDER BYs. Low-risk and behaviour-preserving for categories → candidate for an immediate fix **after owner approval**; not applied in this session. |

## PAYREC-005 — Hard-coded credential-file path and project id in 13 scripts
| Severity | **Low** (path disclosure, no secret value in repo; `*.json` ignored by git) / P4 |
|---|---|
| Files | check_candidate_signal.py, compare_gap_approaches.py, export_for_dashboard.py, export_for_dashboard_v2.py, export_for_excel_analysis.py, load_to_bigquery.py, measure_queue_quality.py, review_discovered_crosswalk.py, spot_check_high_candidates.py, test_composite_score.py, validate_dollar_gap.py, validate_matches.py, validate_merchant_classification.py |
| Fix | Read from `GOOGLE_APPLICATION_CREDENTIALS`/ADC. Not fixed (touching 13 scripts; not exercisable offline). Test: SEC004 |

## PAYREC-006 — `test_composite_score.py` at repo root is collected by pytest and needs BigQuery
Severity **Low**. A bare `pytest` from the root errors at collection (exit 2). Mitigation applied in test infrastructure only (new `pytest.ini` restricts collection to `tests/`); the file was not renamed. Test: SEC006.

## PAYREC-007 — README ranking description does not match SQL
Severity **Low** (documentation). README §3 shows `order by amount_diff asc, merchant_distance asc, days_to_settle asc`; the model orders by `amount_diff asc, days_to_settle asc` (merchant_distance not computed in `int_candidate_matches`). Test: SEC008. Not changed.

## PAYREC-008 — Orphan model `int_merchant_classification`
Severity **Low** (maintainability): never referenced by any model/test; duplicates crosswalk logic at settlement grain. Test: SEC009.

## Observations that are **not** logged as defects (documented limitations / needing confirmation)
- Missing-settlement recall 10.6% (106/1,000) and 32 false alarms — README documents ~11% as known limitation; largely explained by PAYREC-001.
- `status` is carried but unused (RC015) — requires business confirmation.
- amount_mismatch masks delay (RC007); 1-cent tolerance (RC005); calendar-day (not 24h) delay measure.
- Review queue is capped at 30 per tier by design (CT008: 30 of 138 missing_settlement shown).
- No run id / timestamps / lineage / rule codes / run summary in outputs (G8–G11, G14–G15): requirement gap, no stated requirement.
