# Environment Setup (Phase 2)

| Item | Value |
|---|---|
| Python | 3.14.4 (system `python3`) ; repo declares no required version |
| Virtual env | `.venv/` created fresh (none existed); excluded from git via local `.git/info/exclude` (repo `.gitignore` only lists `venv/`; `.gitignore` untouched) |
| Installed (in .venv only) | pytest 9.1.1, pandas 3.1.0, numpy 2.5.4, duckdb 2.0.0, sqlglot 30.24.0, PyYAML 6.0.3, pytz (required by duckdb for TIMESTAMPTZ results) |
| Setup command | `python3 -m venv .venv && . .venv/bin/activate && pip install pytest pandas duckdb sqlglot pyyaml pytz` — exit 0 |
| Setup failures | none (one non-fatal pip warning: "Cache entry deserialization failed, entry ignored") |
| Nothing installed globally; no .env/credentials/config touched |

## Approach to the BigQuery-only pipeline
The pipeline's SQL is BigQuery dialect and its normal runtime (BigQuery + dbt) is unavailable. Rather than re-implementing the logic (which would test a copy),
the test harness (`tests/harness/dbt_local.py`) **renders the repository's own model files** (`{{ ref() }}`/`{{ source() }}`/`{{ config() }}` stripped),
**transpiles them BigQuery→DuckDB with sqlglot**, and executes them against synthetic or committed data. Validity of this approach was checked:
the local run reproduces the committed BigQuery export `data/mart_reconciliation_export.csv` exactly in per-category counts
(matched 21,232 / amount_mismatch 1,800 / delayed 1,003 / duplicate 805 / missing_settlement 138 / needs_manual_review 22) and review queue size (142).
Residual engine difference: for 400 of 25,000 transactions the selected settlement_id differs (equal-rank ties; see PAYREC-004).

## Capability classification
| Capability | Status |
|---|---|
| Local SQL-logic tests via DuckDB, synthetic fixtures | Runnable |
| Source CSV/seed data-quality tests | Runnable |
| Static security/config scans | Runnable |
| `dbt seed/run/test` against BigQuery (the 14 existing dbt tests) | **Blocked** — no dbt installed, no BigQuery project/credentials, not authorized |
| `python load_to_bigquery.py`, validate_*.py, export_*.py, *composite* scripts | **Blocked** — require BigQuery key |
| Private ground-truth validation (`data/_private_*.csv`) | **Blocked** — files git-ignored and absent (only committed anomaly_log.csv is used) |
| Docker/cloud/containers | Not required |

## Reproduce
```
cd payment-reconciliation-pipeline
python3 -m venv .venv && . .venv/bin/activate
pip install pytest pandas duckdb sqlglot pyyaml pytz
python -m pytest            # pytest.ini restricts collection to tests/
```
