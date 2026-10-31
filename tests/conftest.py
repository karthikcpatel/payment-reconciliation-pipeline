import datetime as dt
import hashlib
import pathlib

import pytest

from tests.harness import dbt_local

REPO = dbt_local.REPO
PROTECTED = [REPO / "data" / n for n in (
    "gateway_transactions.csv", "bank_settlements.csv", "anomaly_log.csv",
    "mart_reconciliation_export.csv", "mart_review_queue_export.csv")] + [REPO / "seeds" / "manual_merchant_corrections.csv"]


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


_BEFORE = {}


def pytest_sessionstart(session):
    for p in PROTECTED:
        _BEFORE[p] = _sha(p)


@pytest.fixture(scope="session")
def source_hashes_at_start():
    return dict(_BEFORE)


T0 = dt.datetime(2026, 5, 10, 12, 0, 0)


def txn(txn_id, amount, merchant="Acme", ts=T0, status="completed"):
    return (txn_id, amount, ts, merchant, status)


def stl(stl_id, amount, descriptor="Acme", days=1, base=T0, delta=None):
    when = base + (delta if delta is not None else dt.timedelta(days=days))
    return (stl_id, amount, when, descriptor)


@pytest.fixture(scope="session")
def full_run():
    """Repository SQL executed once on the committed data (read-only)."""
    return dbt_local.build_from_csv()
