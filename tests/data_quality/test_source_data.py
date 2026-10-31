"""Data-quality checks on the committed synthetic CSVs/seed. All read-only."""
import datetime as dt
import re

import pandas as pd
import pytest

from tests.conftest import PROTECTED, REPO, _sha
from tests.harness import dbt_local as h

D = REPO / "data"


@pytest.fixture(scope="module")
def gw():
    return pd.read_csv(D / "gateway_transactions.csv", dtype={"txn_id": str}, keep_default_na=False)


@pytest.fixture(scope="module")
def bk():
    return pd.read_csv(D / "bank_settlements.csv", dtype=str, keep_default_na=False)


@pytest.fixture(scope="module")
def seed():
    return pd.read_csv(REPO / "seeds" / "manual_merchant_corrections.csv", dtype=str, keep_default_na=False)


def test_DQ001_gateway_columns_exact(gw):
    assert list(gw.columns) == ["txn_id", "amount", "timestamp", "merchant", "status"]


def test_DQ002_settlement_columns_exact(bk):
    assert list(bk.columns) == ["settlement_id", "settled_amount", "settlement_date", "bank_descriptor"]


def test_DQ003_ids_unique_and_well_formed(gw, bk):
    assert gw.txn_id.is_unique, gw.txn_id[gw.txn_id.duplicated()].tolist()[:5]
    assert bk.settlement_id.is_unique, bk.settlement_id[bk.settlement_id.duplicated()].tolist()[:5]
    assert gw.txn_id.str.fullmatch(r"TXN\d{6}").all()
    assert bk.settlement_id.str.fullmatch(r"STL\d{6}").all()


def test_DQ004_no_null_or_blank_required_fields(gw, bk):
    for df, name in ((gw, "gateway"), (bk, "settlements")):
        blanks = {c: int((df[c].astype(str).str.strip() == "").sum()) for c in df.columns}
        assert not any(blanks.values()), f"{name} blank/missing values: {blanks}"


def test_DQ005_amount_format_numeric_max_two_decimals(gw, bk):
    pat = r"-?\d+(\.\d{1,2})?"
    bad_g = gw.loc[~gw.amount.astype(str).str.fullmatch(pat), "txn_id"].tolist()
    bad_b = bk.loc[~bk.settled_amount.str.fullmatch(pat), "settlement_id"].tolist()
    assert not bad_g and not bad_b, f"bad gateway amounts {bad_g[:5]}, bad settlement amounts {bad_b[:5]}"


def test_DQ006_gateway_amounts_positive_and_bounded(gw):
    assert (gw.amount > 0).all()
    assert gw.amount.between(5, 500).all(), "generator range is 5-500 (generate_data.py)"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-002: 16 negative settled_amount rows violate the repo's own rule (tests/assert_settled_amount_not_negative.sql)")
def test_DQ007_no_negative_settlement_amounts(bk):
    neg = bk[bk.settled_amount.astype(float) < 0]
    assert neg.empty, f"{len(neg)} negative settlements, total {neg.settled_amount.astype(float).sum():.2f}, e.g. {neg.settlement_id.head(3).tolist()}"


def test_DQ008_gateway_status_values(gw):
    assert set(gw.status) <= {"completed"}, set(gw.status)  # only value in the data; the repo defines no status vocabulary


def test_DQ009_timestamps_parse_and_fall_in_generator_range(gw, bk):
    t = pd.to_datetime(gw.timestamp, errors="raise")
    s = pd.to_datetime(bk.settlement_date, errors="raise")
    assert t.min() >= pd.Timestamp("2026-05-01") and t.max() <= pd.Timestamp("2026-06-30")
    assert s.min() >= t.min() and s.max() <= t.max() + pd.Timedelta(days=16)


def test_DQ010_no_card_like_or_email_values_anywhere():
    luhn_free = re.compile(r"(?<![\d.\-:])\d{13,19}(?![\d.:])")
    email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
    for p in PROTECTED:
        text = p.read_text(errors="replace")
        assert not luhn_free.search(text), f"{p.name}: 13-19 digit run (possible card number)"
        assert not email.search(text), f"{p.name}: email-like value"


def test_DQ011_seed_unique_descriptor_nonblank_and_merchant_known(gw, seed):
    assert seed.bank_descriptor.is_unique, seed.bank_descriptor[seed.bank_descriptor.duplicated()].tolist()
    assert (seed.corrected_merchant.str.strip() != "").all()
    unknown = set(seed.corrected_merchant) - set(gw.merchant)
    assert not unknown, f"corrections point to merchants absent from gateway data: {sorted(unknown)}"


def test_DQ012_seed_descriptors_exist_in_settlements(bk, seed):
    orphan = set(seed.bank_descriptor) - set(bk.bank_descriptor)
    assert not orphan, f"seed rows that correct descriptors never seen in settlements: {sorted(orphan)}"


def test_DQ013_every_settlement_descriptor_resolves_to_a_known_merchant(full_run, gw):
    unresolved = h.rows(full_run, "select bank_descriptor from int_final_merchant_crosswalk where final_merchant is null")
    assert not unresolved, unresolved[:5]
    unknown = h.rows(full_run, "select distinct final_merchant from int_final_merchant_crosswalk")
    assert {r[0] for r in unknown} <= set(gw.merchant)


def test_DQ014_anomaly_log_covers_exactly_the_gateway_ids(gw):
    log = pd.read_csv(D / "anomaly_log.csv", dtype=str)
    assert set(log.txn_id) == set(gw.txn_id) and log.txn_id.is_unique
    assert set(log.anomaly_type) == {"clean", "missing", "amount_mismatch", "duplicate", "delayed"}


def test_DQ015_source_files_unchanged_after_run(source_hashes_at_start):
    """Runs last in module order; the session-level check lives in tests/controls (CT-016)."""
    for p, before in source_hashes_at_start.items():
        assert _sha(p) == before, f"{p} changed during the test session"
