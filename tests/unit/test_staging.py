"""Staging-layer contracts: schema, casts, and behaviour on malformed input (engine = DuckDB transpile of the repo SQL)."""
import duckdb
import pytest

from tests.conftest import T0, stl, txn
from tests.harness import dbt_local as h


def stage(gateway, settlements):
    return h.build(gateway, settlements, upto="stg_bank_settlements")


def cols(con, table):
    return [d[0] for d in con.execute(f"select * from {table} limit 0").description]


def test_ST001_output_schema_is_exact_and_renames_fields():
    con = stage([txn("T1", 10.0)], [stl("S1", 10.0)])
    assert cols(con, "stg_gateway_transactions") == ["txn_id", "gateway_amount", "txn_timestamp", "merchant", "status"]
    assert cols(con, "stg_bank_settlements") == ["settlement_id", "settled_amount", "settlement_date", "bank_descriptor"]


def test_ST002_string_amounts_and_timestamps_are_cast():
    con = stage([("T1", "12.50", "2026-05-01 10:00:00", "Acme", "completed")], [("S1", "12.50", "2026-05-02 10:00:00", "Acme")])
    amt, ts = h.rows(con, "select gateway_amount, txn_timestamp from stg_gateway_transactions")[0]
    from decimal import Decimal
    import datetime as dt
    assert isinstance(amt, Decimal) and amt == Decimal("12.50"), amt
    assert ts.replace(tzinfo=None) == dt.datetime(2026, 5, 1, 10, 0), ts


@pytest.mark.parametrize("bad", ["abc", "1,234.50", "12.50.1", "$12.50"])
def test_ST003_invalid_numeric_formats_fail_loudly(bad):
    """B7/B8/B9: malformed amounts must raise (not silently become null or 0)."""
    with pytest.raises(duckdb.Error):
        stage([("T1", bad, "2026-05-01 10:00:00", "Acme", "completed")], [])


def test_ST004_invalid_timestamp_fails_loudly():
    with pytest.raises(duckdb.Error):
        stage([("T1", "1.00", "not-a-date", "Acme", "completed")], [])


def test_ST005_null_amount_propagates_and_row_is_not_dropped():
    con = stage([("T1", None, "2026-05-01 10:00:00", "Acme", "completed")], [])
    assert h.rows(con, "select count(*), count(gateway_amount) from stg_gateway_transactions")[0] == (1, 0)


def test_ST006_empty_inputs_give_empty_outputs_without_error():
    con = h.build([], [])
    for t in ("stg_gateway_transactions", "mart_reconciliation", "mart_review_queue"):
        assert h.rows(con, f"select count(*) from {t}")[0][0] == 0, t


def test_ST007_missing_required_column_fails():
    con = duckdb.connect()
    con.execute("create table raw_gateway_transactions(txn_id varchar, timestamp timestamp, merchant varchar, status varchar)")  # no amount
    with pytest.raises(duckdb.Error):
        con.execute(f"create table x as {h.model_sql('stg_gateway_transactions')}")


def test_ST008_extra_source_column_is_ignored():
    con = duckdb.connect()
    con.execute("create table raw_gateway_transactions(txn_id varchar, amount double, timestamp timestamp, merchant varchar, status varchar, extra varchar)")
    con.execute("insert into raw_gateway_transactions values ('T1', 1.0, '2026-05-01', 'Acme', 'completed', 'x')")
    con.execute(f"create table x as {h.model_sql('stg_gateway_transactions')}")
    assert cols(con, "x") == ["txn_id", "gateway_amount", "txn_timestamp", "merchant", "status"]


def test_ST009_staging_does_not_deduplicate_or_filter():
    """Duplicate txn_id in source flows through staging (uniqueness is only enforced later by a dbt test)."""
    con = stage([txn("T1", 10.0), txn("T1", 10.0)], [])
    assert h.rows(con, "select count(*) from stg_gateway_transactions")[0][0] == 2


def test_ST010_duplicate_txn_id_in_source_duplicates_mart_rows():
    """Negative path: shows why the mart `unique` dbt test matters; mart is not self-protecting."""
    con = h.build([txn("T1", 10.0), txn("T1", 10.0)], [], upto="mart_reconciliation")
    assert h.rows(con, "select count(*) from mart_reconciliation where txn_id='T1'")[0][0] == 2


def test_ST011_amount_precision_beyond_9_decimals_is_rounded_by_numeric_cast():
    con = stage([("T1", "1.1234567894", "2026-05-01 10:00:00", "Acme", "completed")], [])
    v = h.rows(con, "select gateway_amount from stg_gateway_transactions")[0][0]
    assert str(v).startswith("1.123456789"), v


def test_ST012_discovered_crosswalk_resolves_noisy_descriptors():
    """Edit-distance merchant discovery: prefix/case/punctuation/truncation noise still resolves to the intended merchant."""
    merchants = ["Wilson, Baxter and Robinson", "Anderson PLC", "Black and Sons"]
    txns = [txn(f"T{i}", 10.0 + i, merchant=m) for i, m in enumerate(merchants)]
    descs = {"SQ *WILSON BAXT SYD": merchants[0], "PAYPAL *ANDERSON PLC #4258": merchants[1], "tst*black and sons": merchants[2]}
    con = h.build(txns, [stl(f"S{i}", 5.0, descriptor=d) for i, d in enumerate(descs)], upto="int_final_merchant_crosswalk")
    got = dict(h.rows(con, "select bank_descriptor, final_merchant from int_final_merchant_crosswalk"))
    assert got == descs, got


def test_ST013_discovery_flags_close_call_for_human_review():
    """A descriptor equidistant from two merchants has confidence_gap < 0.05 => needs_human_review true."""
    txns = [txn("T1", 10.0, merchant="Smith-Mcguire"), txn("T2", 10.0, merchant="Smith-Mcgill")]
    con = h.build(txns, [stl("S1", 5.0, descriptor="TST*SMI")], upto="int_discovered_merchant_crosswalk")
    gap, review = h.rows(con, "select confidence_gap, needs_human_review from int_discovered_merchant_crosswalk")[0]
    assert float(gap) < 0.05 and review is True, (gap, review)
