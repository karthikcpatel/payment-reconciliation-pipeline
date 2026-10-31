"""Matching-rule tests: the repo's real SQL on minimal synthetic fixtures. Expected values are hand-computed from the
rules documented in docs/claude_testing/initial_assessment.md (section 7), not derived from the SQL."""
import datetime as dt
from decimal import Decimal as D

import pytest

from tests.conftest import T0, stl, txn
from tests.harness import dbt_local as h


def run(txns, stls, corrections=()):
    return h.build(txns, stls, corrections, upto="mart_reconciliation")


def kind(con, txn_id="T1"):
    return h.mart(con, txn_id)["discrepancy_type"]


# ---- RC-001 exact match -------------------------------------------------------------------------------------
def test_RC001_exact_match_single_candidate():
    con = run([txn("T1", 100.00)], [stl("S1", 100.00, days=1)])
    r = h.mart(con, "T1")
    assert (r["discrepancy_type"], r["settlement_id"], r["num_candidates"], r["match_confidence"], r["days_to_settle"]) == \
        ("matched", "S1", 1, "unique", 1), r
    assert r["amount_diff"] == 0 and r["amount_diff_signed"] == 0, r


# ---- RC-002/003 tolerance = greatest(5.00, 5% of gateway amount), inclusive -------------------------------
@pytest.mark.parametrize("amount,settled,expected", [
    (20.00, 15.00, "amount_mismatch"),   # diff 5.00 == $5 floor (5% would be 1.00) -> candidate
    (20.00, 14.99, "missing_settlement"),  # diff 5.01 -> outside floor
    (20.00, 25.00, "amount_mismatch"),   # symmetric (overpayment) at the floor
    (20.00, 25.01, "missing_settlement"),
    (400.00, 380.00, "amount_mismatch"),  # diff 20.00 == 5% of 400
    (400.00, 379.99, "missing_settlement"),
    (400.00, 420.00, "amount_mismatch"),
    (400.00, 420.01, "missing_settlement"),
])
def test_RC002_RC003_tolerance_boundaries(amount, settled, expected):
    con = run([txn("T1", amount)], [stl("S1", settled)])
    assert kind(con) == expected, f"gateway={amount} settled={settled}"


# ---- RC-004 window = [txn_ts, txn_ts + 15 days], inclusive ---------------------------------------------
@pytest.mark.parametrize("delta,expected_candidate", [
    (dt.timedelta(0), True),
    (dt.timedelta(seconds=-1), False),
    (dt.timedelta(days=15), True),
    (dt.timedelta(days=15, seconds=1), False),
])
def test_RC004_settlement_window_boundaries(delta, expected_candidate):
    con = run([txn("T1", 100.00)], [stl("S1", 100.00, delta=delta)])
    got = kind(con) != "missing_settlement"
    assert got is expected_candidate, f"settlement at txn_ts+{delta}: candidate={got}, expected {expected_candidate}"


# ---- RC-005 amount_mismatch threshold: diff > 0.01 -------------------------------------------------------------
@pytest.mark.parametrize("settled,expected", [(100.00, "matched"), (99.99, "matched"), (99.98, "amount_mismatch"), (100.02, "amount_mismatch")])
def test_RC005_mismatch_threshold_is_strictly_greater_than_one_cent(settled, expected):
    assert kind(run([txn("T1", 100.00)], [stl("S1", settled)])) == expected


# ---- RC-006 delayed threshold: calendar days > 3 --------------------------------------------------------
@pytest.mark.parametrize("days,expected", [(0, "matched"), (3, "matched"), (4, "delayed"), (15, "delayed")])
def test_RC006_delayed_threshold(days, expected):
    assert kind(run([txn("T1", 100.00)], [stl("S1", 100.00, days=days)])) == expected


# ---- RC-007 precedence: amount_mismatch is evaluated before delayed ---------------------------------------
def test_RC007_mismatch_masks_delay():
    r = h.mart(run([txn("T1", 100.00)], [stl("S1", 97.00, days=10)]), "T1")
    assert r["discrepancy_type"] == "amount_mismatch" and r["days_to_settle"] == 10, \
        "documented precedence: amount_mismatch wins; delay information is not reflected in the label (assumption, see strategy A7)"


# ---- RC-008 merchant isolation -----------------------------------------------------------------------------------
def test_RC008_settlement_of_other_merchant_is_not_matched():
    con = run([txn("T1", 100.00, merchant="Acme"), txn("T2", 500.00, merchant="Globex")],
              [stl("S1", 100.00, descriptor="Globex")])
    assert kind(con, "T1") == "missing_settlement"


# ---- RC-009 ranking: smaller amount_diff wins, num_candidates counts all ---------------------------------------
def test_RC009_closest_amount_selected_and_confidence_medium():
    con = run([txn("T1", 100.00)], [stl("S1", 99.50, days=1), stl("S2", 100.00, days=2), stl("S3", 102.00, days=1)])
    r = h.mart(con, "T1")
    assert (r["settlement_id"], r["num_candidates"], r["match_confidence"], r["discrepancy_type"]) == ("S2", 3, "medium", "matched"), r


def test_RC009b_equal_abs_diff_either_side_is_ambiguous():
    # -1.00 and +1.00 have equal abs() diff but different amount and date -> classified ambiguous
    con = run([txn("T1", 100.00)], [stl("S1", 99.00, days=1), stl("S2", 101.00, days=2)])
    r = h.mart(con, "T1")
    assert (r["tie_type"], r["discrepancy_type"]) == ("ambiguous", "needs_manual_review"), r


# ---- RC-010/011 tie typing ---------------------------------------------------------------------------------
def test_RC010_identical_amount_and_date_is_true_duplicate():
    con = run([txn("T1", 100.00)], [stl("S1", 100.00, days=2), stl("S2", 100.00, days=2)])
    r = h.mart(con, "T1")
    assert (r["tie_type"], r["discrepancy_type"], r["num_candidates"]) == ("true_duplicate", "duplicate", 2), r


def test_RC011_same_amount_different_date_is_ambiguous():
    con = run([txn("T1", 100.00)], [stl("S1", 100.00, days=1), stl("S2", 100.00, days=2)])
    r = h.mart(con, "T1")
    assert (r["tie_type"], r["discrepancy_type"]) == ("ambiguous", "needs_manual_review"), r


def test_RC011b_tie_only_inspects_top_two_candidates():
    # best=exact; second=0.50 off, third=0.50 off -> top-2 differ so rank-1 is clear
    con = run([txn("T1", 100.00)], [stl("S1", 100.00), stl("S2", 99.50), stl("S3", 100.50)])
    r = h.mart(con, "T1")
    assert (r["tie_type"], r["discrepancy_type"], r["settlement_id"]) == ("unique_or_clear", "matched", "S1"), r


# ---- RC-012 unmatched ---------------------------------------------------------------------------------------------
def test_RC012_unmatched_classification_and_nulls():
    r = h.mart(run([txn("T1", 123.45)], []), "T1")
    assert r["discrepancy_type"] == "missing_settlement"
    assert r["match_confidence"] is None and r["settlement_id"] is None and r["num_candidates"] is None, r
    assert r["amount_diff_signed"] == D("123.45"), "unmatched exposure should equal the full gateway amount"


# ---- RC-013 confidence tiers -------------------------------------------------------------------------------------
@pytest.mark.parametrize("n,tier", [(1, "unique"), (2, "medium"), (4, "medium"), (5, "low"), (8, "low")])
def test_RC013_match_confidence_tiers(n, tier):
    stls = [stl(f"S{i}", 100.00 - i * 0.50) for i in range(n)]
    r = h.mart(run([txn("T1", 100.00)], stls), "T1")
    assert r["num_candidates"] == n and r["match_confidence"] == tier, r


# ---- RC-014 manual correction overrides the edit-distance guess ------------------------------------------------
def test_RC014_manual_correction_overrides_discovered_merchant():
    txns = [txn("T1", 100.00, merchant="Acme"), txn("T2", 7.00, merchant="Globex")]
    # descriptor 'GLOBEX' alone would resolve to Globex; the correction forces Acme
    con = run(txns, [stl("S1", 100.00, descriptor="GLOBEX")], corrections=[("GLOBEX", "Acme")])
    assert h.mart(con, "T1")["settlement_id"] == "S1"
    con2 = run(txns, [stl("S1", 100.00, descriptor="GLOBEX")])
    assert h.mart(con2, "T1")["discrepancy_type"] == "missing_settlement", "without the correction the descriptor resolves to Globex"


# ---- RC-015 characterization (requires confirmation): gateway status is ignored -----------------------------------
@pytest.mark.parametrize("status", ["failed", "pending", "cancelled"])
def test_RC015_characterization_non_completed_status_is_reconciled_like_completed(status):
    """CURRENT behaviour, not confirmed intent: status is never read. Unknown whether failed/pending should be excluded."""
    con = run([txn("T1", 100.00, status=status)], [stl("S1", 100.00)])
    assert kind(con) == "matched"
    con = run([txn("T1", 100.00, status=status)], [])
    assert kind(con) == "missing_settlement", "a failed payment with no settlement is reported as missing money (possible false exposure)"


# ---- RC-016 settlement reuse (PAYREC-001) -------------------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-001: one settlement can be selected by several gateway transactions (no one-to-one constraint)")
def test_RC016_a_settlement_is_not_assigned_to_two_transactions():
    con = run([txn("T1", 100.00), txn("T2", 100.00, ts=T0 + dt.timedelta(hours=1))], [stl("S1", 100.00)])
    used = h.rows(con, "select settlement_id, count(*) from mart_reconciliation where settlement_id is not null group by 1 having count(*) > 1")
    assert not used, f"settlement(s) assigned to more than one transaction: {used}"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-001: the second identical-amount transaction should surface as missing_settlement")
def test_RC016b_second_payment_without_own_settlement_is_missing():
    con = run([txn("T1", 100.00), txn("T2", 100.00, ts=T0 + dt.timedelta(hours=1))], [stl("S1", 100.00)])
    kinds = sorted(r[0] for r in h.rows(con, "select discrepancy_type from mart_reconciliation"))
    assert kinds == ["matched", "missing_settlement"], kinds


# ---- RC-017 determinism of equal-rank candidates (PAYREC-004) --------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-004: rank() ORDER BY lacks a final deterministic tiebreaker (settlement_id)")
def test_RC017_selected_settlement_independent_of_input_order():
    a, b = stl("S_A", 100.00, days=2), stl("S_B", 100.00, days=2)
    first = h.mart(run([txn("T1", 100.00)], [a, b]), "T1")["settlement_id"]
    second = h.mart(run([txn("T1", 100.00)], [b, a]), "T1")["settlement_id"]
    assert first == second, f"same data, different row order chose {first} vs {second}"


# ---- RC-018 repeatability ----------------------------------------------------------------------------------------
def test_RC018_identical_input_gives_identical_output():
    args = ([txn("T1", 100.00), txn("T2", 55.55)], [stl("S1", 100.00), stl("S2", 55.00)])
    q = "select * from mart_reconciliation order by txn_id"
    assert h.rows(run(*args), q) == h.rows(run(*args), q)


# ---- RC-019 bank-side orphans (PAYREC-003, requires confirmation) ---------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-003: settlements with no gateway transaction appear in no output (requires business confirmation of intent)")
def test_RC019_unmatched_bank_settlement_is_visible_in_an_output():
    con = h.build([txn("T1", 100.00)], [stl("S1", 100.00), stl("S2", 77.77)], upto="mart_review_queue")
    surfaced = {r[0] for r in h.rows(con, "select settlement_id from mart_reconciliation where settlement_id is not null")} | \
               {r[0] for r in h.rows(con, "select settlement_id from mart_review_queue where settlement_id is not null")}
    assert "S2" in surfaced, f"orphan bank settlement S2 (77.77) is not reported anywhere; surfaced={surfaced}"


# ---- RC-020 negative settlement (PAYREC-002) ------------------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-002: negative settlements are silently dropped by the join; the repo's own dbt test cannot see them")
def test_RC020_negative_settlement_is_detected_by_repo_singular_test():
    con = h.build([txn("T1", 10.00)], [stl("S1", -10.00)], upto="mart_reconciliation")
    offenders = h.run_dbt_singular_test(con, "assert_settled_amount_not_negative")
    assert offenders, "repo rule 'settled_amount must never be negative' did not flag a -10.00 settlement (test runs on the mart, after the join discarded it)"


def test_RC008b_right_merchant_wins_even_if_other_merchants_amount_is_closer():
    con = run([txn("T1", 100.00, merchant="Acme"), txn("T2", 100.00, merchant="Globex")],
              [stl("S_A", 98.00, descriptor="Acme"), stl("S_G", 100.00, descriptor="Globex")])
    assert (h.mart(con, "T1")["settlement_id"], h.mart(con, "T2")["settlement_id"]) == ("S_A", "S_G")


def test_RC021_three_way_tie_is_ambiguous_and_counts_all_candidates():
    con = run([txn("T1", 100.00)], [stl("S1", 100.00, days=1), stl("S2", 100.00, days=2), stl("S3", 100.00, days=3)])
    r = h.mart(con, "T1")
    assert (r["num_candidates"], r["tie_type"], r["discrepancy_type"]) == (3, "ambiguous", "needs_manual_review"), r


def test_RC022_tie_with_amount_mismatch_still_routes_to_manual_review():
    con = run([txn("T1", 100.00)], [stl("S1", 97.00, days=1), stl("S2", 103.00, days=1)])
    assert h.mart(con, "T1")["discrepancy_type"] == "needs_manual_review"


def test_RC023_calendar_day_not_24h_governs_days_to_settle():
    late = T0.replace(hour=23, minute=59)
    r = h.mart(run([txn("T1", 100.00, ts=late)], [stl("S1", 100.00, delta=dt.timedelta(minutes=2), base=late)]), "T1")
    assert r["days_to_settle"] == 1 and r["discrepancy_type"] == "matched", "2 minutes later across midnight counts as 1 calendar day"
