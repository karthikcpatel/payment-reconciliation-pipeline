"""Regression/evidence tests for confirmed defects, measured on the committed data. Strict xfail: they flip to
failures (and so must be reviewed) when the defect is fixed."""
import pandas as pd
import pytest

from tests.conftest import REPO
from tests.harness import dbt_local as h

pytestmark = pytest.mark.local_data


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-001: 1,448 settlements are selected by 2+ transactions; mart settled dollars exceed bank dollars")
def test_RG001_matched_settlement_dollars_cannot_exceed_bank_dollars(full_run):
    bank = float(h.rows(full_run, "select sum(settled_amount) from stg_bank_settlements where settled_amount > 0")[0][0])
    used = float(h.rows(full_run, "select sum(settled_amount) from mart_reconciliation")[0][0])
    assert used <= bank + 0.005, f"mart settled total {used:,.2f} > total positive bank settlements {bank:,.2f} (excess {used-bank:,.2f})"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-001: settlement reuse across transactions")
def test_RG002_each_settlement_selected_by_at_most_one_transaction(full_run):
    reused = h.rows(full_run, "select count(*), sum(c-1) from (select count(*) c from mart_reconciliation where settlement_id is not null group by settlement_id having count(*)>1)")[0]
    assert reused[0] in (0, None), f"{reused[0]} settlements reused, {reused[1]} extra assignments"


def test_RG003_PAYREC001_magnitude_pinned():
    """Pins the stable measurements of PAYREC-001 (observed 2026-10-24). The reused-settlement count itself varies by a few
    between runs (1447-1455 over 5 runs; PAYREC-004), so it is bounded rather than pinned; the dollar total is invariant."""
    con = h.build_from_csv()
    used = round(float(h.rows(con, "select sum(settled_amount) from mart_reconciliation")[0][0]), 2)
    bank_pos = round(float(h.rows(con, "select sum(settled_amount) from stg_bank_settlements where settled_amount > 0")[0][0]), 2)
    reused = h.rows(con, "select count(*) from (select 1 from mart_reconciliation where settlement_id is not null group by settlement_id having count(*)>1)")[0][0]
    assert (used, bank_pos, round(used - bank_pos, 2)) == (6258100.98, 6203402.33, 54698.65)
    assert 1400 <= reused <= 1500, reused


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-004: two runs of the same SQL on the same data in the same engine select different settlements")
def test_RG003b_two_runs_select_identical_settlements():
    a = dict(h.build_from_csv().execute("select txn_id, settlement_id from mart_reconciliation").fetchall())
    b = dict(h.build_from_csv().execute("select txn_id, settlement_id from mart_reconciliation").fetchall())
    diff = [t for t in a if a[t] != b[t]]
    assert not diff, f"{len(diff)} transactions resolved to different settlements across identical runs"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-002: negative settlements exist in source but the repo's non-negative test passes vacuously")
def test_RG004_repo_nonnegative_test_agrees_with_source(full_run):
    in_source = h.rows(full_run, "select count(*) from stg_bank_settlements where settled_amount < 0")[0][0]
    flagged = len(h.run_dbt_singular_test(full_run, "assert_settled_amount_not_negative"))
    assert flagged == in_source, f"{in_source} negative settlements in source, repo dbt test flags {flagged}"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-003: bank settlements not linked to any gateway transaction are not reported")
def test_RG005_every_bank_settlement_is_accounted_for(full_run):
    orphans = h.rows(full_run, "select count(*), sum(settled_amount) from stg_bank_settlements where settlement_id not in (select settlement_id from mart_reconciliation where settlement_id is not null)")[0]
    assert orphans[0] == 0, f"{orphans[0]} bank settlements (sum {float(orphans[1]):,.2f}) appear in no output"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-004: committed BigQuery export and local run disagree on selected settlement for tie cases")
def test_RG006_selected_settlement_matches_committed_export(full_run):
    exp = pd.read_csv(REPO / "data" / "mart_reconciliation_export.csv")[["txn_id", "settlement_id"]]
    cur = full_run.execute("select txn_id, settlement_id from mart_reconciliation").df()
    m = exp.merge(cur, on="txn_id", suffixes=("_bq", "_loc"))
    diff = m[m.settlement_id_bq.fillna("") != m.settlement_id_loc.fillna("")]
    assert diff.empty, f"{len(diff)} transactions resolved to a different settlement between engines"
