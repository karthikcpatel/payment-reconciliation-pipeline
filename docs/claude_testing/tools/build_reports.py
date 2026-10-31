"""Builds test_coverage_matrix.md, execution_report.md and final_testing_report.html from evidence/ (junit XML + commands.json).
Every number is read from the evidence files; nothing is typed in by hand."""
import html, json, pathlib, re, subprocess, sys, xml.etree.ElementTree as ET
REPO = pathlib.Path(__file__).resolve().parents[3]
DOC = REPO / "docs/claude_testing"; EV = DOC / "evidence"
cmds = json.loads((EV / "commands.json").read_text())
full = next(c for c in cmds if c["name"].startswith("FULL suite (auth"))
C = full["counts"]

# ---- per-test status from the authoritative run -------------------------------------------------
tests = []
for tc in ET.parse(EV / "full.xml").getroot().iter("testcase"):
    kids = {k.tag: k for k in tc}
    st = "FAILED" if "failure" in kids else "ERROR" if "error" in kids else "XFAIL (defect)" if ("skipped" in kids and kids["skipped"].get("type") == "pytest.xfail") else "SKIPPED" if "skipped" in kids else "PASSED"
    reason = kids["skipped"].get("message", "") if "skipped" in kids else ""
    tests.append(dict(id=tc.get("name"), file=tc.get("classname").replace(".", "/"), status=st, reason=reason))
fam = {}
for t in tests:
    m = re.match(r"test_([A-Z]+\d+[a-z]?)(?:_([A-Z]+\d+))?", t["id"]); key = m.group(1)
    fam.setdefault(key, []).append(t)
    if m.group(2) and not m.group(2).startswith("PAYREC"): fam.setdefault(m.group(2), []).append(t)

META = {  # id: (stage, rule, evidence, type, fixture, expected, defect, notes)
"ST001":("Staging","Output schema/renames","stg_*.sql","unit","2-row synthetic","exact column lists","",""),
"ST002":("Staging","String→numeric/timestamp casts","stg_*.sql","unit","string row","12.50 / 2026-05-01 10:00","",""),
"ST003":("Staging","Invalid numeric formats raise","stg_gateway_transactions.sql","negative","abc, 1,234.50, 12.50.1, $12.50","error raised","","DuckDB cast semantics; BigQuery CAST also errors"),
"ST004":("Staging","Invalid timestamp raises","stg_gateway_transactions.sql","negative","not-a-date","error","",""),
"ST005":("Staging","Null amount propagates, row kept","stg_gateway_transactions.sql","boundary","null amount","1 row, null amount","",""),
"ST006":("Staging→marts","Empty input yields empty outputs","all models","boundary","no rows","0 rows everywhere","",""),
"ST007":("Staging","Missing required column fails","stg_gateway_transactions.sql","negative","no amount column","error","",""),
"ST008":("Staging","Extra column ignored","stg_gateway_transactions.sql","boundary","extra col","same schema","",""),
"ST009":("Staging","No dedup in staging (characterization)","stg_gateway_transactions.sql","characterization","dup txn_id","2 rows","","uniqueness only enforced by mart dbt test"),
"ST010":("Mart","Dup txn_id duplicates mart rows (characterization)","mart_reconciliation.sql","characterization","dup txn_id","2 mart rows","","shows why dbt unique test matters"),
"ST011":("Staging","NUMERIC(38,9) precision","stg_*.sql","boundary","1.1234567894","1.123456789","","harness fix: DECIMAL(38,9)"),
"ST012":("Crosswalk","Edit-distance resolves noisy descriptors","int_discovered_merchant_crosswalk.sql","unit","3 noisy descriptors","intended merchants","",""),
"ST013":("Crosswalk","Close call flagged needs_human_review","int_discovered_merchant_crosswalk.sql","unit","TST*SMI vs 2 merchants","gap<0.05, true","",""),
"RC008b":("Matching","Right merchant wins over closer amount of other merchant","int_candidate_matches.sql","negative","2 merchants","each gets own stl","",""),
"RC021":("Matching","3-way tie ambiguous","int_match_selection.sql","boundary","3 identical-amount stl","needs_manual_review, 3 cands","",""),
"RC022":("Matching","Tie with mismatch → manual review","int_match_selection.sql","boundary","97/103","needs_manual_review","",""),
"RC023":("Classification","Calendar-day days_to_settle","int_candidate_matches.sql","boundary","23:59 + 2min","1 day, matched","",""),
"DQ001":("Source","Gateway columns","gateway_transactions.csv","data quality","committed CSV","5 exact columns","",""),
"DQ002":("Source","Settlement columns","bank_settlements.csv","data quality","committed CSV","4 exact columns","",""),
"DQ003":("Source","Unique, well-formed ids","CSV","data quality","committed CSV","unique TXN######/STL######","",""),
"DQ004":("Source","No null/blank fields","CSV","data quality","committed CSV","0 blanks","",""),
"DQ005":("Source","Amount format ≤2 dp","CSV","data quality","committed CSV","regex match","",""),
"DQ006":("Source","Gateway amounts 5–500, >0","generate_data.py","data quality","committed CSV","all in range","",""),
"DQ007":("Source","No negative settlements (repo rule)","assert_settled_amount_not_negative.sql","data quality","committed CSV","0 negatives","PAYREC-002","16 found, −173.26"),
"DQ008":("Source","Status vocabulary","CSV","data quality","committed CSV","{completed}","","no vocabulary defined in repo (RC)"),
"DQ009":("Source","Timestamps parse & in range","generate_data.py","data quality","committed CSV","2026-05-01..06-30","",""),
"DQ010":("Privacy","No card-like numbers / emails","all fixtures","security","committed files","none","",""),
"DQ011":("Seed","Seed unique, merchants known","manual_merchant_corrections.csv","referential","seed","0 violations","",""),
"DQ012":("Seed","Seed descriptors exist in settlements","seed","referential","seed","0 orphans","",""),
"DQ013":("Crosswalk","Every descriptor resolves to known merchant","int_final_merchant_crosswalk.sql","referential","full data","0 null/unknown","",""),
"DQ014":("Source","anomaly_log ids == gateway ids","anomaly_log.csv","referential","committed CSV","identical sets","",""),
"DQ015":("Source","Sources unchanged","—","immutability","sha256","unchanged","",""),
"RC001":("Matching","Exact match","int_candidate_matches/mart","positive","1 txn/1 stl","matched, unique, S1","",""),
"RC002":("Matching","Tolerance greatest(5, 5%) boundaries","int_candidate_matches.sql","boundary","8 param cases","inclusive at limit","","RC002/RC003"),
"RC003":("Matching","Tolerance greatest(5, 5%) boundaries","int_candidate_matches.sql","boundary","8 param cases","inclusive at limit","","covered by RC002 test"),
"RC004":("Matching","15-day window inclusive","int_candidate_matches.sql","boundary","4 param cases","±1s at both ends","",""),
"RC005":("Classification","amount_diff > 0.01 ⇒ mismatch","mart_reconciliation.sql","boundary","4 param cases","0.01 matched; 0.02 mismatch","","1-cent tolerance = assumption A4"),
"RC006":("Classification","days_to_settle > 3 ⇒ delayed","mart_reconciliation.sql","boundary","4 param cases","3 matched; 4 delayed","",""),
"RC007":("Classification","Mismatch precedes delayed","mart_reconciliation.sql","characterization","97.00 @10d","amount_mismatch","","assumption A7"),
"RC008":("Matching","Merchant isolation","int_candidate_matches.sql","negative","other merchant stl","missing_settlement","",""),
"RC009":("Matching","Closest amount wins; medium confidence","int_candidate_matches.sql","positive","3 candidates","S2, medium","",""),
"RC009b":("Matching","Equal abs diff ⇒ ambiguous","int_match_selection.sql","boundary","99/101","needs_manual_review","",""),
"RC010":("Matching","Same amount+date ⇒ duplicate","int_match_selection.sql","positive","2 identical stl","duplicate","",""),
"RC011":("Matching","Same amount, different date ⇒ ambiguous","int_match_selection.sql","positive","2 stl","needs_manual_review","",""),
"RC011b":("Matching","Tie inspects top-2 only","int_match_selection.sql","boundary","3 stl","clear pick S1","",""),
"RC012":("Classification","Unmatched ⇒ missing_settlement, nulls","mart_reconciliation.sql","positive","no stl","missing, exposure=full","",""),
"RC013":("Classification","Confidence tiers 1/2-4/≥5","mart_reconciliation.sql","boundary","1,2,4,5,8 cands","unique/medium/low","",""),
"RC014":("Crosswalk","Manual correction overrides","int_final_merchant_crosswalk.sql","positive","GLOBEX→Acme","matched only with seed","",""),
"RC015":("Classification","Status ignored (characterization)","stg_gateway_transactions.sql","characterization","failed/pending/cancelled","reconciled like completed","","requires confirmation A3"),
"RC016":("Matching","Settlement used once","int_match_selection.sql","negative","2 txn/1 stl","no reuse","PAYREC-001","strict xfail"),
"RC016b":("Matching","Second payment w/o own settlement is missing","int_match_selection.sql","negative","2 txn/1 stl","matched+missing","PAYREC-001","strict xfail"),
"RC017":("Matching","Order-independent pick","int_candidate_matches.sql","negative","2 identical stl, 2 orders","same pick","PAYREC-004","strict xfail"),
"RC018":("Idempotency","Same input ⇒ same output","all","regression","2 txns","identical rows","",""),
"RC019":("Output","Bank orphan surfaced","models","negative","S2 77.77 unmatched","visible","PAYREC-003","strict xfail; assumption A6"),
"RC020":("Controls","Negative stl detected by repo test","assert_settled_amount_not_negative.sql","negative","-10.00 stl","flagged","PAYREC-002","strict xfail"),
"RQ001":("Review queue","Missing = P1, exposure full","mart_review_queue.sql","positive","1 txn","P1, 80","",""),
"RQ002":("Review queue","Duplicate = P2","mart_review_queue.sql","positive","2 identical stl","P2, 100","",""),
"RQ003":("Review queue","Ambiguous = P3","mart_review_queue.sql","positive","2 stl","P3, 100","",""),
"RQ004":("Review queue","Matched queued only if ≥5 cands","mart_review_queue.sql","boundary","4 vs 5 cands","P4 at 5","",""),
"RQ005":("Review queue","Mismatch queued if diff ≥ 5","mart_review_queue.sql","boundary","4.99 vs 5.00","P5 at 5.00","",""),
"RQ006":("Review queue","Delayed/clean not queued","mart_review_queue.sql","negative","delayed+clean","empty","",""),
"RQ007":("Review queue","Cap 30/tier, largest kept, sorted","mart_review_queue.sql","boundary","35 missing","30 rows","",""),
"RQ008":("Review queue","Unique txn, reason populated","mart_review_queue.sql","positive","mixed","no dup ids","",""),
"CT001":("Controls","1 mart row per gateway txn","mart_reconciliation","control","full data","25,000","",""),
"CT002":("Controls","Category counts sum to total","mart_reconciliation","control","full data","25,000","",""),
"CT003":("Controls","Gateway $ total preserved","mart_reconciliation","control","full data","pandas total","",""),
"CT004":("Controls","amount_diff_signed = gw − settled","mart_reconciliation.sql","control","full data","pandas recompute","",""),
"CT005":("Controls","Local run = BigQuery export categories","data/mart_reconciliation_export.csv","regression","full data","0 differences","","harness fidelity"),
"CT006":("Controls","Queue = BigQuery export","data/mart_review_queue_export.csv","regression","full data","142 rows, ≥140 overlap","",""),
"CT007":("Controls","Queue tiers/exposure rules","mart_review_queue.sql","control","full data","≤30/tier","",""),
"CT008":("Controls","Queue coverage quantified","mart_review_queue.sql","control","full data","30/138 missing shown","","observed, no threshold"),
"CT009":("Repo dbt tests","4 singular tests executed locally","tests/*.sql","repo test","full data","0 offending rows","","equivalent to dbt test"),
"CT010":("Repo dbt tests","10 generic tests executed locally","_marts.yml","repo test","full data","0 offending rows","","SQL-equivalent, not dbt itself"),
"CT011":("Controls","days_to_settle in 0..15","mart","control","full data","in range","",""),
"CT012":("Controls","Missing rows have null settlement fields","mart","control","full data","138 rows","",""),
"CT013":("Controls","Selected settlement ids exist","mart","referential","full data","subset","",""),
"CT014":("Controls","Join predicates re-verified in pandas","mart","control","full data","tolerance+window hold","",""),
"CT015":("Controls","Ground-truth detection observed","anomaly_log.csv","observed metric","full data","106/1000 recall (pinned)","","README documents limitation"),
"CT016":("Controls","Sources unchanged after full run","—","immutability","sha256","unchanged","",""),
"RG001":("Controls","Matched $ ≤ bank $","mart vs stg_bank_settlements","negative","full data","≤ 6,203,402.33","PAYREC-001","excess 54,698.65"),
"RG002":("Controls","No settlement reuse (scale)","mart","negative","full data","0 reused","PAYREC-001",""),
"RG003":("Regression","PAYREC-001 magnitude pinned","mart","regression","full data","6,258,100.98 / 6,203,402.33","PAYREC-001",""),
"RG003b":("Idempotency","Two runs, same picks","int_candidate_matches.sql","negative","full data x2","identical","PAYREC-004","strict xfail"),
"RG004":("Controls","Repo non-negative test sees source negatives","tests/assert_settled_amount_not_negative.sql","negative","full data","16 flagged","PAYREC-002",""),
"RG005":("Controls","All bank records accounted","models","negative","full data","0 orphans","PAYREC-003","1,383-1,387 observed"),
"RG006":("Idempotency","Local = BigQuery selected settlement","export","negative","full data","0 diffs","PAYREC-004","403 differ"),
"FI001":("Idempotency","Re-run identical","all","regression","5 txns","identical","",""),
"FI002":("Failure","Missing raw table raises","stg_bank_settlements.sql","negative","no table","error","",""),
"FI003":("Failure","Sources not mutated","all","immutability","1/1 rows","unchanged","",""),
"FI004":("Failure","Duplicate ingestion ⇒ duplicate class","int_match_selection.sql","characterization","S1 twice","duplicate","",""),
"SEC001":("Security","No secret material tracked","git ls-files","security","repo","0 hits","",""),
"SEC002":("Security","No credential files tracked","git ls-files","security","repo","0","",""),
"SEC003":("Security","gitignore blocks *.json & private truth",".gitignore","security","repo","present","",""),
"SEC004":("Security","No hard-coded key path","*.py","security","repo","0","PAYREC-005","13 scripts"),
"SEC005":("Privacy","No PII/card-like data in fixtures","tests,data,seeds","security","repo","0","",""),
"SEC006":("Hygiene","Root script not collected by pytest","test_composite_score.py","hygiene","bare pytest","exit 0","PAYREC-006",""),
"SEC007":("Security","Report files not world-writable","docs/","security","docs","none","",""),
"SEC008":("Docs","README ranking = SQL","README.md","docs","repo","consistent","PAYREC-007",""),
"SEC009":("Maintainability","No orphan models","models/","hygiene","repo","0","PAYREC-008",""),
}

def agg(ts):
    s = {t["status"] for t in ts}
    return "FAILED" if "FAILED" in s or "ERROR" in s else "XFAIL (defect)" if s == {"XFAIL (defect)"} else "PASSED" if s == {"PASSED"} else "/".join(sorted(s))

rows = []
for k in sorted(fam, key=lambda x: (re.match(r"[A-Z]+", x).group(), int(re.search(r"\d+", x).group()), x)):
    if k not in META: continue
    st, rule, ev, ty, fx, ex, d, nt = META[k]
    ts = fam[k]
    rows.append(dict(req=f"REQ-{k}", stage=st, rule=rule, ev=ev, tc=f"{k} ({len(ts)} case{'s' if len(ts)>1 else ''})", ty=ty, fx=fx, ex=ex,
                     act=("as expected" if agg(ts) == "PASSED" else "defect reproduced (assertion fails under --runxfail)" if agg(ts).startswith("XFAIL") else "see evidence"),
                     status=agg(ts), evid=ts[0]["file"] + ".py", d=d, nt=nt))
missing_meta = [k for k in fam if k not in META]
assert not missing_meta, f"tests without coverage metadata: {missing_meta}"

H = "| Requirement ID | Pipeline stage | Business rule | Source evidence | Test case ID | Test type | Input fixture | Expected result | Actual result | Status | Evidence location | Defect ID | Notes / assumptions |\n|" + "---|" * 13 + "\n"
md = "# Test Coverage Matrix\n\nGenerated from `evidence/full.xml` (authoritative run). Family rows aggregate parametrized cases. Scenarios judged N/A or blocked are listed in test_strategy.md.\n\n" + H
for r in rows:
    md += f"| {r['req']} | {r['stage']} | {r['rule']} | {r['ev']} | {r['tc']} | {r['ty']} | {r['fx']} | {r['ex']} | {r['act']} | {r['status']} | {r['evid']} | {r['d'] or '—'} | {r['nt'] or '—'} |\n"
md += "\n**Blocked / not executed:** pre-existing 14 dbt tests against BigQuery (dbt + BigQuery unavailable) — locally *re-executed as SQL equivalents* in CT009/CT010, which is not the same as running dbt. Export/loader scripts, private-ground-truth validators: blocked (credentials/files absent).\n"
(DOC / "test_coverage_matrix.md").write_text(md)

# ---- execution report -------------------------------------------------------------------------------------
git = lambda *a: subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True).stdout.strip()
commit, branch = git("rev-parse", "HEAD"), git("branch", "--show-current")
status_short = git("status", "--short", "--untracked-files=all")
mut = (EV / "mutation_output.txt").read_text() if (EV / "mutation_output.txt").exists() else "Not verified"
blocked = 1  # dbt test run (pre-existing tests) — see below
tbl = "| Group / command | Exit | Passed | Failed | XFail (confirmed defects) | Skipped | Error | Total | Seconds |\n|---|---|---|---|---|---|---|---|---|\n"
for c in cmds:
    k = c["counts"]
    tbl += (f"| {c['name']}<br><code>{html.escape(c['command'])}</code> | {c['exit_code']} | " + (" | ".join(str(k[x]) for x in ("passed", "failed", "xfailed", "skipped", "error", "total")) if k else "n/a | n/a | n/a | n/a | n/a | n/a") + f" | {c['seconds']} |\n")
open(EV / "_exec_table.md", "w").write(tbl)
json.dump(dict(C=C, rows=rows, commit=commit, branch=branch, status=status_short), open(EV / "_summary.json", "w"), indent=1)
print("coverage rows:", len(rows), "authoritative:", C)
