"""Control totals on the full committed dataset. Expected values come from pandas over the raw CSVs, not from the SQL."""
import pandas as pd
import pytest
import yaml

from tests.conftest import REPO, _sha
from tests.harness import dbt_local as h

pytestmark = pytest.mark.local_data
D = REPO / "data"


@pytest.fixture(scope="module")
def gw():
    return pd.read_csv(D / "gateway_transactions.csv")


@pytest.fixture(scope="module")
def bk():
    return pd.read_csv(D / "bank_settlements.csv")


@pytest.fixture(scope="module")
def mart(full_run):
    return full_run.execute("select * from mart_reconciliation").df()


def test_CT001_one_mart_row_per_gateway_transaction(mart, gw):
    assert len(mart) == len(gw) == 25000
    assert mart.txn_id.is_unique and set(mart.txn_id) == set(gw.txn_id)


def test_CT002_category_counts_sum_to_total(mart):
    allowed = {"matched", "missing_settlement", "amount_mismatch", "duplicate", "delayed", "needs_manual_review"}
    counts = mart.discrepancy_type.value_counts()
    assert set(counts.index) <= allowed and counts.sum() == 25000, counts.to_dict()


def test_CT003_gateway_amount_total_preserved(mart, gw):
    assert round(float(mart.gateway_amount.astype(float).sum()), 2) == round(gw.amount.sum(), 2)


def test_CT004_amount_diff_signed_equals_gateway_minus_settled(mart):
    m = mart.assign(g=mart.gateway_amount.astype(float), s=mart.settled_amount.astype(float).fillna(0))
    expected = (m.g - m.s).round(2)
    off = m[(expected - m.amount_diff_signed.astype(float)).abs() > 0.005]
    assert off.empty, off.txn_id.head().tolist()


def test_CT005_local_run_reproduces_committed_bigquery_export_categories(mart):
    exp = pd.read_csv(D / "mart_reconciliation_export.csv")
    merged = exp.merge(mart, on="txn_id", suffixes=("_bq", "_loc"))
    assert len(merged) == 25000
    diff = merged[merged.discrepancy_type_bq != merged.discrepancy_type_loc]
    assert diff.empty, f"{len(diff)} classification differences, e.g. {diff.txn_id.head().tolist()}"
    assert exp.discrepancy_type.value_counts().to_dict() == mart.discrepancy_type.value_counts().to_dict()
    conf = merged[merged.match_confidence_bq.fillna("x") != merged.match_confidence_loc.fillna("x")]
    assert conf.empty


def test_CT006_review_queue_matches_committed_export(full_run):
    exp = pd.read_csv(D / "mart_review_queue_export.csv")
    q = full_run.execute("select txn_id, review_priority, estimated_exposure from mart_review_queue").df()
    assert len(q) == len(exp) == 142
    m = exp.merge(q, on="txn_id", suffixes=("_bq", "_loc"))
    # membership can legitimately differ on equal gateway_amount ties at the cap; priority per txn must agree for overlap
    assert (m.review_priority_bq == m.review_priority_loc).all()
    assert (m.estimated_exposure_bq.astype(float) - m.estimated_exposure_loc.astype(float)).abs().max() < 0.005
    assert len(m) >= 140, f"only {len(m)}/142 queue rows overlap with the committed export"


def test_CT007_queue_tier_caps_and_exposure_rules(full_run):
    tiers = h.rows(full_run, "select review_priority, count(*) from mart_review_queue group by 1 order by 1")
    assert all(n <= 30 for _, n in tiers) and [t for t, _ in tiers] == [1, 2, 3, 4, 5], tiers
    bad = h.rows(full_run, """select txn_id from mart_review_queue where
        (review_priority = 1 and estimated_exposure <> gateway_amount) or (review_priority = 4 and estimated_exposure <> 0)
        or (review_priority = 5 and (amount_diff < 5 or estimated_exposure <> amount_diff))""")
    assert not bad, bad[:5]


def test_CT008_queue_coverage_is_partial_and_quantified(full_run):
    """Quantifies (does not pass/fail on a threshold, none is specified): share of missing-settlement dollars visible in the queue."""
    tot, n = h.rows(full_run, "select sum(gateway_amount), count(*) from mart_reconciliation where discrepancy_type='missing_settlement'")[0]
    seen, k = h.rows(full_run, "select sum(estimated_exposure), count(*) from mart_review_queue where review_priority=1")[0]
    print(f"\n[CT008] missing_settlement: {n} txns / {float(tot):.2f}; queue shows {k} txns / {float(seen):.2f} ({float(seen)/float(tot):.1%})")
    assert k == 30 and n == 138 and 0 < float(seen) < float(tot)


# ---- repository dbt tests, executed locally against the harness output ---------------------------------------
@pytest.mark.parametrize("name", ["assert_days_to_settle_reasonable", "assert_no_txn_id_overlap_across_priority",
                                  "assert_review_priority_valid_range", "assert_settled_amount_not_negative"])
def test_CT009_repo_singular_dbt_tests_pass_locally(full_run, name):
    assert h.run_dbt_singular_test(full_run, name) == [], name


def _generic_tests():
    spec = yaml.safe_load((REPO / "models" / "marts" / "_marts.yml").read_text())
    out = []
    for model in spec["models"]:
        for col in model.get("columns", []):
            for t in col.get("tests", []):
                out.append((model["name"], col["name"], t))
    return out


@pytest.mark.parametrize("model,col,t", _generic_tests(), ids=lambda v: v if isinstance(v, str) else (next(iter(v)) if isinstance(v, dict) else "?"))
def test_CT010_repo_generic_dbt_tests_pass_locally(full_run, model, col, t):
    """Executes the 10 generic tests declared in _marts.yml with equivalent SQL (dbt itself is not installed)."""
    if t == "unique":
        sql = f"select {col} from {model} group by 1 having count(*) > 1"
    elif t == "not_null":
        sql = f"select * from {model} where {col} is null"
    elif "accepted_values" in t:
        vals = ",".join(f"'{v}'" for v in t["accepted_values"]["arguments"]["values"])
        sql = f"select * from {model} where {col} is not null and {col} not in ({vals})"
    elif "relationships" in t:
        to = t["relationships"]["to"].split("'")[1]
        fld = t["relationships"]["field"]
        sql = f"select {col} from {model} where {col} is not null and {col} not in (select {fld} from {to})"
    else:
        pytest.fail(f"unsupported generic test {t}")
    assert full_run.execute(sql).fetchall() == [], f"{model}.{col} {t}"


def test_CT011_days_to_settle_within_window_and_nonnegative(mart):
    d = mart.days_to_settle.dropna()
    assert d.between(0, 15).all(), (d.min(), d.max())


def test_CT012_missing_settlement_rows_have_no_settlement_fields(mart):
    m = mart[mart.discrepancy_type == "missing_settlement"]
    assert len(m) == 138 and m.settlement_id.isna().all() and m.num_candidates.isna().all() and m.match_confidence.isna().all()


def test_CT013_every_selected_settlement_id_exists_in_source(mart, bk):
    ids = set(mart.settlement_id.dropna())
    assert ids <= set(bk.settlement_id), sorted(ids - set(bk.settlement_id))[:5]


def test_CT014_selected_settlements_belong_to_the_transactions_merchant_window_and_tolerance(mart, gw, bk):
    """Independent re-verification of the join predicates with pandas (not SQL)."""
    m = mart.dropna(subset=["settlement_id"]).merge(bk, on="settlement_id")
    g_amt, s_amt = m.gateway_amount.astype(float), m.settled_amount_y.astype(float)
    tol = pd.concat([pd.Series(5.0, index=m.index), g_amt * 0.05], axis=1).max(axis=1)
    assert ((g_amt - s_amt).abs() <= tol + 1e-9).all()
    ts, sd = pd.to_datetime(m.txn_timestamp).dt.tz_localize(None), pd.to_datetime(m.settlement_date_y)
    assert ((sd >= ts) & (sd <= ts + pd.Timedelta(days=15))).all()


def test_CT015_ground_truth_detection_observed_not_graded(mart):
    """Grades against the committed anomaly_log (generator labels). Observed figures are reported, no threshold is invented."""
    log = pd.read_csv(D / "anomaly_log.csv")
    j = log.merge(mart[["txn_id", "discrepancy_type"]], on="txn_id")
    missing = j[j.anomaly_type == "missing"]
    caught = (missing.discrepancy_type == "missing_settlement").sum()
    print(f"\n[CT015] injected missing={len(missing)} detected={caught} recall={caught/len(missing):.1%}")
    flagged = (mart.discrepancy_type == "missing_settlement").sum()
    print(f"[CT015] missing_settlement labels={flagged}, of which true injected-missing={caught}, false alarms={flagged - caught}")
    # pin current behaviour: README documents ~11% recall as a known limitation
    assert (len(missing), caught, flagged) == (1000, 106, 138)


def test_CT016_source_files_unchanged_by_full_run(full_run, source_hashes_at_start):
    for p, before in source_hashes_at_start.items():
        assert _sha(p) == before, f"{p} modified"
