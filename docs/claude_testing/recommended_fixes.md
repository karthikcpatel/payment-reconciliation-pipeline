# Recommended Fixes (none applied in this session)

No application file was modified. Order by risk-adjusted value:

1. **PAYREC-004 (small, safe)** – add `settlement_id asc` to `row_number() … order by` in `int_candidate_matches.sql` and `txn_id asc` to the QUALIFY window in `mart_review_queue.sql`. Expected effect: categories unchanged, settlement picks reproducible. Flip tests RC017, RG003b, then RG006 expectations, and remove their `xfail` markers.
2. **PAYREC-001 (largest impact)** – introduce one-to-one assignment. Sketch: build all candidate pairs, rank globally `(amount_diff, days_to_settle, settlement_id, txn_id)`, keep a pair only if neither side was assigned earlier (iterative or via a seed-and-loop in dbt/BigQuery script). Re-measure: reused settlements must be 0, matched dollars ≤ bank dollars, and review the change in `missing_settlement` recall. Remove xfail from RC016/RC016b/RG001/RG002. Needs owner sign-off on assumption A1 and on the effect on dashboards/history.
3. **PAYREC-002** – move `assert_settled_amount_not_negative` to `stg_bank_settlements` (or add a `severity: error` source test); decide business handling for negative amounts (exception category vs. refund model).
4. **PAYREC-003** – add `mart_unmatched_settlements` (settlements not selected by any txn) and include its count/amount in a run summary.
5. **Audit gaps** – add run_id, processed_at, rule/reason code and lineage columns to marts; add a run-level control summary model (counts and dollars by category, reconciling to source).
6. **PAYREC-005/006/007/008** – use ADC/env var for credentials; rename `test_composite_score.py` (e.g. `explore_composite_score.py`); correct README ranking text; delete or wire up `int_merchant_classification`.
7. Add `dbt_utils.equal_rowcount`/expression tests: `sum(mart.settled_amount) <= sum(distinct settled)`; `unique settlement_id where not null` in the mart (this single test would have caught PAYREC-001).
