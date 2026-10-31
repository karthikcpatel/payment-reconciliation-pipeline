"""Failure injection on COPIES of models/ (never on repo files). Usage: python docs/claude_testing/evidence/mutation_run.py"""
import os, re, shutil, subprocess, sys, tempfile, pathlib
REPO = pathlib.Path(__file__).resolve().parents[3]
MUT = [
 ("M01 tolerance floor 5.0 -> 6.0", "intermediate/int_candidate_matches.sql", "greatest(5.0,", "greatest(6.0,"),
 ("M02 tolerance pct 5% -> 6%", "intermediate/int_candidate_matches.sql", "* 0.05", "* 0.06"),
 ("M03 window 15d -> 16d", "intermediate/int_candidate_matches.sql", "interval 15 day", "interval 16 day"),
 ("M04 window start allows pre-txn settlement", "intermediate/int_candidate_matches.sql", "between g.txn_timestamp and", "between timestamp_sub(g.txn_timestamp, interval 1 day) and"),
 ("M05 mismatch threshold 0.01 -> 0.05", "marts/mart_reconciliation.sql", "amount_diff > 0.01", "amount_diff > 0.05"),
 ("M06 delayed threshold 3 -> 4", "marts/mart_reconciliation.sql", "days_to_settle > 3", "days_to_settle > 4"),
 ("M07 confidence medium upper 4 -> 5", "marts/mart_reconciliation.sql", "between 2 and 4", "between 2 and 5"),
 ("M08 ranking amount_diff asc -> desc", "intermediate/int_candidate_matches.sql", "order by amount_diff asc", "order by amount_diff desc"),
 ("M09 true_duplicate requires only same amount", "intermediate/int_match_selection.sql", "s.distinct_amounts_top2 = 1 and s.distinct_dates_top2 = 1", "s.distinct_amounts_top2 = 1"),
 ("M10 queue cap 30 -> 25", "marts/mart_review_queue.sql", "<= 30", "<= 25"),
 ("M11 queue amount_mismatch threshold >=5 -> >5", "marts/mart_review_queue.sql", "amount_diff >= 5", "amount_diff > 5"),
 ("M12 queue matched low-confidence >=5 -> >=6", "marts/mart_review_queue.sql", "num_candidates >= 5", "num_candidates >= 6"),
 ("M13 exposure for missing uses 0", "marts/mart_review_queue.sql", "in ('missing_settlement', 'needs_manual_review') then gateway_amount", "in ('missing_settlement', 'needs_manual_review') then 0"),
 ("M14 delayed outranks amount_mismatch", "marts/mart_reconciliation.sql", "when amount_diff > 0.01 then 'amount_mismatch'\n            when days_to_settle > 3 then 'delayed'", "when days_to_settle > 3 then 'delayed'\n            when amount_diff > 0.01 then 'amount_mismatch'"),
 ("M15 crosswalk ignores manual corrections", "intermediate/int_final_merchant_crosswalk.sql", "coalesce(c.corrected_merchant, d.discovered_merchant)", "d.discovered_merchant"),
 ("M16 staging amount cast to int", "staging/stg_gateway_transactions.sql", "cast(amount as numeric)", "cast(cast(amount as int64) as numeric)"),
]
rows = []
for name, rel, old, new in MUT:
    d = pathlib.Path(tempfile.mkdtemp(prefix="payrec_mut_")) / "models"
    shutil.copytree(REPO / "models", d)
    f = d / rel; s = f.read_text()
    if old not in s:
        rows.append((name, "MUTATION NOT APPLIED", "")); continue
    f.write_text(s.replace(old, new, 1))
    env = dict(os.environ, PAYREC_MODELS_DIR=str(d))
    r = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:warnings", "-p", "no:cacheprovider", "--tb=no", "-rf"], cwd=REPO, env=env, capture_output=True, text=True)
    tail = r.stdout.strip().splitlines()[-1]
    failed = sorted({re.search(r"::(test_\w+)", l).group(1).split("_")[1] for l in r.stdout.splitlines() if l.startswith("FAILED")})
    rows.append((name, tail, ",".join(failed)))
    shutil.rmtree(d.parent)
w = max(len(r[0]) for r in rows)
for n, t, f in rows: print(f"{n:<{w}} | {t} | detecting test ids: {f or 'NONE'}")
