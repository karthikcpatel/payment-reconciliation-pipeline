"""H-group: failure behaviour and idempotency of the SQL pipeline (the repo has no file writers/loaders runnable offline)."""
import duckdb
import pytest

from tests.conftest import T0, stl, txn
from tests.harness import dbt_local as h


def test_FI001_rerun_is_idempotent_for_unambiguous_data():
    t = [txn(f"T{i}", 100.0 + i, merchant="Acme") for i in range(5)]
    s = [stl(f"S{i}", 100.0 + i) for i in range(5)]
    q = "select * from mart_reconciliation order by txn_id"
    assert h.rows(h.build(t, s), q) == h.rows(h.build(t, s), q)


def test_FI002_missing_raw_table_raises():
    con = duckdb.connect()
    with pytest.raises(duckdb.Error):
        con.execute(f"create table x as {h.model_sql('stg_bank_settlements')}")


def test_FI003_source_tables_not_mutated_by_pipeline():
    t, s = [txn("T1", 10.0)], [stl("S1", 10.0)]
    con = h.build(t, s)
    assert h.rows(con, "select count(*) from raw_gateway_transactions")[0][0] == 1
    assert h.rows(con, "select count(*) from raw_bank_settlements")[0][0] == 1


def test_FI004_repeated_ingestion_of_same_settlement_row_is_treated_as_duplicate_payout():
    """Duplicate ingestion of one bank row (same id twice) looks like a duplicate payout: classified 'duplicate', not de-duplicated by id."""
    r = h.mart(h.build([txn("T1", 10.0)], [stl("S1", 10.0), stl("S1", 10.0)], upto="mart_reconciliation"), "T1")
    assert r["discrepancy_type"] == "duplicate", r
