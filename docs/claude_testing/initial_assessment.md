# Initial Assessment (Phase 1)

Evidence base: files read in full at commit e48ef63 — README.md, project_log.md, dbt_project.yml, all 10 models, 4 dbt singular tests,
_marts.yml, _sources.yml, seeds/manual_merchant_corrections.csv, generate_data.py, build_corrections_seed.py and the BigQuery-bound helper scripts (headers/queries), plus
profiling of data/*.csv. No application source was modified.

## 1. Repository overview
A synthetic "gateway transactions vs bank settlements" reconciliation project. Gateway and bank records share **no common ID**; matching is by
resolved merchant + amount tolerance + settlement window. Primary deliverable is a dbt (BigQuery) project; the Python scripts are data generation,
BigQuery loading/export, and ad-hoc validation against a private ground truth (private files are git-ignored and **not present**).

## 2. Confirmed technology stack
| Technology | Evidence |
|---|---|
| dbt Core, BigQuery dialect (`edit_distance`, `date_diff`, `timestamp_add`, `qualify`, `numeric`) | dbt_project.yml, models/ |
| Python (pandas, numpy, Faker, google-cloud-bigquery) | *.py (no requirements file) |
| CSV files | data/, seeds/ |
| Tableau Public (consumer of exports) | README (not in repo) |
| **Not present**: Airflow/Prefect/Dagster, Kafka, Docker, CI workflows, Makefile, requirements/pyproject, .env | file inventory |

## 3. Pipeline components and entry points
Entry points (no orchestration; manual): `python generate_data.py` → `python load_to_bigquery.py` → `dbt seed && dbt run && dbt test` → `python export_for_dashboard_v2.py`.
Pre-existing tests: 14 dbt tests (10 generic in models/marts/_marts.yml, 4 singular in tests/*.sql). They require BigQuery + credentials → **blocked locally**.

## 4. Source-to-target flow
```
data/gateway_transactions.csv ─load_to_bigquery.py─▶ raw_gateway_transactions ─▶ stg_gateway_transactions ─┐
data/bank_settlements.csv     ─load_to_bigquery.py─▶ raw_bank_settlements     ─▶ stg_bank_settlements ──┬──┤
seeds/manual_merchant_corrections.csv ─dbt seed─▶ manual_merchant_corrections                           │  │
stg_bank_settlements ─▶ int_discovered_merchant_crosswalk (edit distance vs 85 merchants) ─┐            │  │
                        manual corrections override ─▶ int_final_merchant_crosswalk ◀──────┘            │  │
stg_gateway + stg_settlements + crosswalk ─▶ int_candidate_matches (join + rank) ◀───────────────────────┴──┘
int_candidate_matches ─▶ int_match_selection (rank 1 + tie_type) ─▶ mart_reconciliation ─▶ mart_review_queue ─▶ data/mart_*_export.csv
```
`int_merchant_classification` (per-settlement edit distance) is **not referenced** by any other model (orphan).

## 5. Inputs
| Source | Format | Columns (observed) | Key | Notes |
|---|---|---|---|---|
| gateway_transactions.csv | CSV, 25,000 rows | txn_id, amount, timestamp, merchant, status | txn_id (unique, TXN######) | status always `completed`; amounts 5.02–500.00; no nulls; no currency column |
| bank_settlements.csv | CSV, 24,750 rows | settlement_id, settled_amount, settlement_date, bank_descriptor | settlement_id (unique) | **16 negative amounts (sum −173.26)**; no currency, no batch ID, no txn reference |
| manual_merchant_corrections.csv | seed, 60 rows | bank_descriptor, corrected_merchant | bank_descriptor | overrides edit-distance guess |
| anomaly_log.csv | CSV, 25,000 | txn_id, merchant, anomaly_type | txn_id | generator ground-truth labels; usable only for grading |
Absent: currency, tax, fee, refund, chargeback, reversal, batch/settlement-run, payment-method, account identifiers.

## 6. Outputs
`mart_reconciliation` (one row per gateway txn: txn_id, merchant, gateway_amount, txn_timestamp, settlement_id, settled_amount, settlement_date, amount_diff, days_to_settle, num_candidates, tie_type, discrepancy_type, match_confidence, amount_diff_signed);
`mart_review_queue` (priority 1–5, reason, estimated_exposure; top 30 per tier); CSV exports in data/. **No run ID, processing timestamp, rule code or lineage columns; no run-level summary table.**

## 7. Reconciliation model (confirmed from SQL)
Gateway-driven, rule-based, tolerance + time-window, single-stage, **one gateway row → ≤1 chosen settlement**, but a settlement may be chosen by many gateway rows (no uniqueness constraint on settlement — see PAYREC-001).
- Candidate join: `gateway.merchant = crosswalk.final_merchant(settlement.bank_descriptor)` AND `|gw_amount − settled_amount| ≤ greatest(5.0, 5% × gw_amount)` AND `txn_ts ≤ settlement_date ≤ txn_ts + 15 days` (inclusive both ends).
- Rank: `amount_diff asc, days_to_settle asc` (no final deterministic tiebreaker; README claims merchant_distance is also used — it is not).
- Tie typing (top-2 only): equal best/second amount_diff → `true_duplicate` if same amount and same date else `ambiguous`.
- Classification precedence: no candidate → missing_settlement; ambiguous → needs_manual_review; true_duplicate → duplicate; amount_diff > 0.01 → amount_mismatch; days_to_settle > 3 → delayed; else matched.
- match_confidence: 1 candidate=unique, 2–4=medium, ≥5=low, null if none.
- Statuses confirmed: matched, missing_settlement, amount_mismatch, duplicate, delayed, needs_manual_review.
- Review queue priority: 1 missing, 2 duplicate, 3 needs_manual_review, 4 matched with ≥5 candidates, 5 amount_mismatch with diff ≥ 5; cap 30 rows per priority by gateway_amount desc.

## 8. Monetary handling
`cast(... as numeric)` (BigQuery NUMERIC, 9 dp); tolerance floor $5.00 / 5%; mismatch threshold 0.01 (a 1-cent difference is still "matched"); `amount_diff_signed = round(gw − coalesce(settled,0), 2)`. Single implicit currency; no currency validation, FX, fees, tax, refund or sign convention beyond abs().

## 9. Not implemented in the repository (scenario = not applicable / unsupported)
Currency mismatch/FX, fees/tax/net, refunds, partial refunds, reversals, chargebacks, authorization/capture lifecycle, split/combined settlement (one-to-many / many-to-one), batch/merchant-level settlement totals, run IDs, audit logs, idempotent re-run controls, checkpointing. `status` column is carried but never filtered or mapped.

## 10. Dependencies
- Local analysis/unit testing: Python ≥3.9 (3.14.4 present), pytest, pandas, duckdb, sqlglot, pyyaml (installed in .venv; none declared by repo).
- Integration: BigQuery project `fintech-reconciliation` + service-account key → **blocked** (not available, no authorization to use).
- Optional: dbt-core/dbt-bigquery (not installed; blocked without BigQuery), Faker (generate_data.py; not needed).

## 11. Security-sensitive areas (values not reproduced)
- 13 Python scripts hard-code an absolute local path to a GCP service-account JSON key and the GCP project ID (risk: credential-location disclosure; key itself not in repo). `*.json` is git-ignored, which prevents accidental commit of the key.
- No card/bank-account/PII data: names are Faker company names; descriptors are synthetic.
- No .env or secrets tracked (`git ls-files` scan by name).

## 12. Risks and unknowns requiring confirmation
1. Is a settlement allowed to satisfy more than one gateway transaction? (Evidence says impossible — see control test.)
2. Intended treatment of negative settlements (refund/reversal/chargeback?) — currently silently dropped.
3. Should non-`completed` gateway statuses be reconciled? 
4. Is a 1-cent difference intended as "matched"?
5. Tie-break rule for equally ranked candidates.
6. Should bank-side orphans (settlements without a gateway txn) be reported?
7. Precedence of delayed vs amount_mismatch when both apply.

## 13. Recommended testing priorities
1. Control totals (matched $ ≤ available settlement $; count conservation).
2. Candidate window/tolerance boundaries and classification precedence using the repository's real SQL on synthetic fixtures.
3. Settlement-reuse / one-to-one protection. 4. Negative/odd settlement handling. 5. Determinism. 6. Source-data contract checks. 7. Review-queue rules. 8. Static security scan.
