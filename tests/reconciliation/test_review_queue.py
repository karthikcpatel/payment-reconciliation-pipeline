"""mart_review_queue rules (README section 6, models/marts/mart_review_queue.sql)."""
import datetime as dt

from tests.conftest import T0, stl, txn
from tests.harness import dbt_local as h


def queue(txns, stls):
    con = h.build(txns, stls)
    cur = con.execute("select * from mart_review_queue order by review_priority, gateway_amount desc, txn_id")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def test_RQ001_missing_is_priority1_with_full_amount_exposure():
    q = queue([txn("T1", 80.00)], [])
    assert len(q) == 1 and q[0]["review_priority"] == 1 and q[0]["estimated_exposure"] == 80, q


def test_RQ002_duplicate_priority2_exposure_is_one_settlement_amount():
    q = queue([txn("T1", 100.00)], [stl("S1", 100.00, days=1), stl("S2", 100.00, days=1)])
    assert [(r["review_priority"], r["estimated_exposure"]) for r in q] == [(2, 100)], q


def test_RQ003_ambiguous_priority3_exposure_is_gateway_amount():
    q = queue([txn("T1", 100.00)], [stl("S1", 100.00, days=1), stl("S2", 100.00, days=2)])
    assert [(r["review_priority"], r["estimated_exposure"]) for r in q] == [(3, 100)], q


def test_RQ004_matched_enters_queue_only_with_five_or_more_candidates():
    four = queue([txn("T1", 100.00)], [stl(f"S{i}", 100.00 - i * 0.5) for i in range(4)])
    five = queue([txn("T1", 100.00)], [stl(f"S{i}", 100.00 - i * 0.5) for i in range(5)])
    assert four == [], four
    assert [(r["review_priority"], r["estimated_exposure"]) for r in five] == [(4, 0)], five


def test_RQ005_amount_mismatch_threshold_5_dollars_inclusive():
    below = queue([txn("T1", 200.00)], [stl("S1", 195.01)])   # diff 4.99
    at = queue([txn("T1", 200.00)], [stl("S1", 195.00)])      # diff 5.00
    assert below == [], below
    assert [(r["review_priority"], r["estimated_exposure"]) for r in at] == [(5, 5)], at


def test_RQ006_delayed_and_clean_matches_are_not_queued():
    assert queue([txn("T1", 100.00), txn("T2", 50.00, merchant="Globex")],
                 [stl("S1", 100.00, days=9), stl("S2", 50.00, descriptor="Globex", days=1)]) == []


def test_RQ007_cap_is_30_per_priority_tier_largest_gateway_amounts_kept():
    txns = [txn(f"T{i:03d}", 10.00 + i, ts=T0 + dt.timedelta(minutes=i)) for i in range(35)]
    q = queue(txns, [])
    assert len(q) == 30, len(q)
    kept = {r["txn_id"] for r in q}
    assert kept == {f"T{i:03d}" for i in range(5, 35)}, "the 5 smallest amounts (T000-T004) should be dropped"
    assert [r["gateway_amount"] for r in q] == sorted((r["gateway_amount"] for r in q), reverse=True)


def test_RQ008_txn_appears_at_most_once_and_has_reason():
    txns = [txn("T1", 90.00), txn("T2", 100.00, merchant="Globex")]
    q = queue(txns, [stl("S1", 100.00, descriptor="Globex", days=1), stl("S2", 100.00, descriptor="Globex", days=1)])
    ids = [r["txn_id"] for r in q]
    assert len(ids) == len(set(ids)) and all(r["review_reason"] for r in q), q
