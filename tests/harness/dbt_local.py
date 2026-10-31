"""Run the repository's own dbt model SQL locally.

The models are BigQuery-dialect dbt SQL. This harness strips the Jinja (config/ref/source), transpiles
BigQuery -> DuckDB with sqlglot and executes the models in dependency order against caller-supplied data.
It does NOT re-implement any reconciliation logic; expected values in tests are written by hand.

PAYREC_MODELS_DIR / PAYREC_TESTS_DIR env vars point the harness at a mutated *copy* of the models (used for failure injection).
"""
import functools
import os
import pathlib
import re

import duckdb
import pandas as pd
import sqlglot

REPO = pathlib.Path(__file__).resolve().parents[2]
MODELS_DIR = pathlib.Path(os.environ.get("PAYREC_MODELS_DIR", REPO / "models"))
DBT_TESTS_DIR = pathlib.Path(os.environ.get("PAYREC_TESTS_DIR", REPO / "tests"))

# dependency order (verified against ref() calls in the models)
MODEL_ORDER = [
    "stg_gateway_transactions",
    "stg_bank_settlements",
    "int_discovered_merchant_crosswalk",
    "int_final_merchant_crosswalk",
    "int_candidate_matches",
    "int_match_selection",
    "mart_reconciliation",
    "mart_review_queue",
]

GATEWAY_COLS = ["txn_id", "amount", "timestamp", "merchant", "status"]
SETTLEMENT_COLS = ["settlement_id", "settled_amount", "settlement_date", "bank_descriptor"]
CORRECTION_COLS = ["bank_descriptor", "corrected_merchant"]


def render(sql: str) -> str:
    sql = re.sub(r"\{\{\s*config\(.*?\)\s*\}\}", "", sql, flags=re.S)
    sql = re.sub(r"\{\{\s*source\('[^']+',\s*'([^']+)'\)\s*\}\}", r"\1", sql)
    sql = re.sub(r"\{\{\s*ref\('([^']+)'\)\s*\}\}", r"\1", sql)
    assert "{{" not in sql, "unrendered Jinja left in SQL"
    return sql


def to_duckdb(sql: str) -> str:
    out = sqlglot.transpile(render(sql), read="bigquery", write="duckdb")[0]
    # sqlglot maps BigQuery NUMERIC to bare DECIMAL (= DECIMAL(18,3) in DuckDB); BigQuery NUMERIC is (38,9).
    return out.replace("AS DECIMAL)", "AS DECIMAL(38,9))")


@functools.lru_cache(maxsize=None)
def model_sql(name: str) -> str:
    matches = list(MODELS_DIR.rglob(f"{name}.sql"))
    assert len(matches) == 1, f"model {name}: expected exactly one file, found {matches}"
    return to_duckdb(matches[0].read_text())


def _frame(rows, cols):
    df = pd.DataFrame(rows, columns=cols)
    return df


def build(gateway, settlements, corrections=(), upto="mart_review_queue"):
    """Return a duckdb connection with raw tables + every model table built. Inputs are lists of dicts/tuples."""
    con = duckdb.connect()
    con.execute("set TimeZone='UTC'")  # BigQuery TIMESTAMP is UTC
    for tbl, rows, cols in (
        ("raw_gateway_transactions", gateway, GATEWAY_COLS),
        ("raw_bank_settlements", settlements, SETTLEMENT_COLS),
        ("manual_merchant_corrections", corrections, CORRECTION_COLS),
    ):
        df = _frame(rows, cols)
        con.register(f"_{tbl}", df)
        con.execute(f"create table {tbl} as select * from _{tbl}")
    for m in MODEL_ORDER:
        con.execute(f"create table {m} as {model_sql(m)}")
        if m == upto:
            break
    return con


def build_from_csv(data_dir=REPO / "data", seed=REPO / "seeds" / "manual_merchant_corrections.csv"):
    con = duckdb.connect()
    con.execute("set TimeZone='UTC'")
    con.execute(f"create table raw_gateway_transactions as select * from read_csv_auto('{data_dir}/gateway_transactions.csv')")
    con.execute(f"create table raw_bank_settlements as select * from read_csv_auto('{data_dir}/bank_settlements.csv')")
    con.execute(f"create table manual_merchant_corrections as select * from read_csv_auto('{seed}')")
    for m in MODEL_ORDER:
        con.execute(f"create table {m} as {model_sql(m)}")
    return con


def run_dbt_singular_test(con, name: str):
    """Execute tests/<name>.sql (a dbt singular test: returns offending rows) and return the rows."""
    sql = (DBT_TESTS_DIR / f"{name}.sql").read_text()
    return con.execute(to_duckdb(sql)).fetchall()


def rows(con, sql, *params):
    return con.execute(sql, list(params)).fetchall()


def mart(con, txn_id):
    """Return the mart_reconciliation row for txn_id as a dict."""
    cur = con.execute("select * from mart_reconciliation where txn_id = ?", [txn_id])
    cols = [d[0] for d in cur.description]
    r = cur.fetchall()
    assert len(r) == 1, f"expected exactly one mart row for {txn_id}, got {len(r)}"
    return dict(zip(cols, r[0]))
