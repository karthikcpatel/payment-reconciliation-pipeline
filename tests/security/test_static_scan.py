"""Static security/privacy and repository-hygiene checks. Failures report file + category only, never the matched value."""
import pathlib
import re
import subprocess
import sys

import pytest

from tests.conftest import REPO


def tracked():
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split("\n")
    return [REPO / f for f in out if f]


SECRET_PATTERNS = {
    "private-key-block": re.compile(r"BEGIN (RSA |EC )?PRIVATE KEY"),
    "aws-access-key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "gcp-service-account-json": re.compile(r'"private_key_id"|"type":\s*"service_account"'),
    "generic-secret-assignment": re.compile(r"(?i)(password|secret|api[_-]?key|token)\s*=\s*['\"][^'\"]{8,}['\"]"),
}


def test_SEC001_no_secret_material_in_tracked_files():
    hits = []
    for f in tracked():
        if f.suffix in {".csv", ".pyc"} or not f.is_file() or f == pathlib.Path(__file__).resolve():
            continue
        text = f.read_text(errors="replace")
        hits += [f"{f.relative_to(REPO)}: {name}" for name, pat in SECRET_PATTERNS.items() if pat.search(text)]
    assert not hits, hits


def test_SEC002_no_credential_files_tracked():
    bad = [str(f.relative_to(REPO)) for f in tracked() if re.search(r"(^|/)(\.env.*|.*\.pem|.*\.p12|.*\.key|.*credentials.*|.*service[_-]?account.*\.json)$", f.name, re.I)]
    assert not bad, bad


def test_SEC003_gitignore_blocks_json_keys_and_private_ground_truth():
    text = (REPO / ".gitignore").read_text()
    assert "*.json" in text and "_private_" in text


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-005: scripts hard-code the absolute path of a GCP service-account key file and the project id")
def test_SEC004_no_hardcoded_credential_paths_in_scripts():
    offenders = [f.name for f in REPO.glob("*.py") if re.search(r"KEY_PATH\s*=\s*['\"]/", f.read_text())]
    assert not offenders, f"{len(offenders)} scripts hard-code a credential-file path: {sorted(offenders)}"


def test_SEC005_no_real_looking_pii_or_card_data_in_fixtures():
    card = re.compile(r"(?<![\d.\-:])\d{13,19}(?![\d.:])")
    email = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}")
    for f in list((REPO / "tests").rglob("*.py")) + list((REPO / "data").glob("*.csv")) + list((REPO / "seeds").glob("*.csv")):
        text = f.read_text(errors="replace")
        assert not card.search(text), f"{f.relative_to(REPO)}: card-like digit run"
        assert not email.search(text), f"{f.relative_to(REPO)}: email address"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-006: root-level test_composite_score.py is collected by a bare `pytest` and needs BigQuery credentials")
def test_SEC006_root_scripts_do_not_masquerade_as_pytest_tests():
    r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "test_composite_score.py"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, "pytest collection of test_composite_score.py fails (exit %s)" % r.returncode


def test_SEC007_generated_artifacts_are_not_world_writable():
    bad = [str(p.relative_to(REPO)) for p in (REPO / "docs" / "claude_testing").rglob("*") if p.is_file() and p.stat().st_mode & 0o002]
    assert not bad, bad


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-007: README says candidates are ranked with merchant_distance; the SQL does not use it")
def test_SEC008_readme_ranking_claim_matches_sql():
    readme = (REPO / "README.md").read_text()
    sql = (REPO / "models" / "intermediate" / "int_candidate_matches.sql").read_text()
    claims = "merchant_distance asc" in readme
    assert (not claims) or "merchant_distance" in sql, "README documents merchant_distance in the ranking; int_candidate_matches.sql does not"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="PAYREC-008: int_merchant_classification is not referenced by any model or test (orphan)")
def test_SEC009_no_orphan_models():
    corpus = "".join(p.read_text() for p in list((REPO / "models").rglob("*.sql")) + list((REPO / "tests").glob("*.sql")) + list((REPO / "models").rglob("*.yml")))
    orphans = [p.stem for p in (REPO / "models").rglob("*.sql") if f"ref('{p.stem}')" not in corpus and p.parent.name != "marts"]
    assert not orphans, orphans
