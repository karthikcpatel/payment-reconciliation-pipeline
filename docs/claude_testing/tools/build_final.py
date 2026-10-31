import html, json, pathlib, re, subprocess, platform, sys
REPO = pathlib.Path(__file__).resolve().parents[3]; DOC = REPO / "docs/claude_testing"; EV = DOC / "evidence"
S = json.loads((EV / "_summary.json").read_text()); C = S["C"]; rows = S["rows"]
cmds = json.loads((EV / "commands.json").read_text())
mut = (EV / "mutation_output.txt").read_text().strip().splitlines()
git = lambda *a: subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True).stdout.strip()
commit, branch = git("rev-parse", "HEAD"), git("branch", "--show-current")
files = [l for l in git("status", "--short", "--untracked-files=all").splitlines()]
untracked = git("ls-files", "--others", "--exclude-standard").splitlines()
modified = git("diff", "--name-only").splitlines()
T = C["total"]; P, X, F = C["passed"], C["xfailed"], C["failed"] + C["error"]
assert P + X + F + C["skipped"] == T
runx = next(c for c in cmds if "runxfail" in c["name"])["counts"]
assert runx["failed"] == X, "runxfail failures must equal xfail count"
py = sys.version.split()[0]
def pv(m):
    try: return __import__(m).__version__
    except Exception: return "Not verified"
vers = f"Python {py}; pytest {pv('pytest')}; duckdb {pv('duckdb')}; sqlglot {pv('sqlglot')}; pandas {pv('pandas')}"
DEFECTS = [("PAYREC-001","Critical","Settlement assigned to multiple transactions (double counting): mart settled $6,258,100.98 vs bank $6,203,402.33 (+$54,698.65)","RC016, RC016b, RG001, RG002, RG003"),
 ("PAYREC-002","High","Negative settlements (16, −$173.26) silently dropped; repo non-negative dbt test vacuous","DQ007, RC020, RG004"),
 ("PAYREC-003","Medium","Bank-side orphans (~1,383–1,387, ≈$357.6k) reported nowhere (needs confirmation)","RC019, RG005"),
 ("PAYREC-004","Medium","Non-deterministic selection among equal-rank candidates (104 diffs between identical runs; 403 vs BigQuery export)","RC017, RG003b, RG006"),
 ("PAYREC-005","Low","Hard-coded credential-file path/project id in 13 scripts","SEC004"),
 ("PAYREC-006","Low","Root test_composite_score.py collected by bare pytest (needs BigQuery)","SEC006"),
 ("PAYREC-007","Low","README ranking description ≠ SQL","SEC008"),
 ("PAYREC-008","Low","Orphan model int_merchant_classification","SEC009")]
BLOCKED = ["14 pre-existing dbt tests via `dbt test` (dbt not installed, no BigQuery project/credentials) — their logic was re-executed as equivalent SQL (CT009 ×4, CT010 ×10): all passed, but that is not a dbt run",
           "load_to_bigquery.py, export_for_*.py, validate_*.py, spot_check/compare/measure/check/review scripts (BigQuery credentials)",
           "Private ground-truth validations (files git-ignored, absent); README accuracy figures not verifiable",
           "Exit-code, rollback, checkpoint, output-write-failure tests (no writers/services exist in repo or need BigQuery)"]
ASSUME = ["A1 a settlement should satisfy at most one transaction","A2 negative settlements are invalid","A3 non-'completed' statuses should (not) be reconciled","A4 a 1-cent difference is 'matched' by design","A5 tie-breaks must be deterministic","A6 bank-side orphans must be reported","A7 amount_mismatch should outrank delayed"]
RERUN = """cd payment-reconciliation-pipeline
python3 -m venv .venv && . .venv/bin/activate && pip install pytest pandas duckdb sqlglot pyyaml pytz
python -m pytest tests                       # full suite (expected: %d passed, %d xfailed)
python -m pytest tests/unit                  # staging / crosswalk
python -m pytest tests/data_quality          # source CSV + seed
python -m pytest tests/reconciliation        # matching rules + review queue
python -m pytest tests/controls -s           # control totals, repo dbt tests as SQL
python -m pytest tests/regression            # defect evidence at scale, idempotency
python -m pytest tests/security              # static scans
python -m pytest tests --runxfail            # shows the %d confirmed-defect failures
python docs/claude_testing/tools/run_all.py && python docs/claude_testing/tools/build_reports.py && python docs/claude_testing/tools/build_final.py   # regenerate evidence+reports
python docs/claude_testing/evidence/mutation_run.py   # failure injection on temp copies (~8 min)""" % (P, X, X)

tbl = "| Group / command | Exit | Passed | Failed | XFail | Skipped | Total | Sec |\n|---|---|---|---|---|---|---|---|\n"
for c in cmds:
    k = c["counts"]; tbl += f"| {c['name']}<br>`{c['command']}` | {c['exit_code']} | " + (" | ".join(str(k[x]) for x in ("passed","failed","xfailed","skipped","total")) if k else "n/a | n/a | n/a | n/a | n/a") + f" | {c['seconds']} |\n"
dtab = "| ID | Severity | Summary | Tests |\n|---|---|---|---|\n" + "".join(f"| {a} | {b} | {c} | {d} |\n" for a,b,c,d in DEFECTS)
inv = "\n".join(f"- `{f}`" for f in sorted(set(untracked)))

md = f"""# Execution Report

| Item | Value |
|---|---|
| Repository | payment-reconciliation-pipeline |
| Root | {REPO} |
| Branch / commit | {branch} / {commit} (working tree otherwise unchanged: **0 tracked files modified**) |
| Environment | Linux (Ubuntu, kernel 7.0.0-1003-gcp); {vers}; Claude Code 2.1.310 |
| Stack (confirmed) | dbt Core + BigQuery SQL, Python scripts (pandas/Faker/google-cloud-bigquery), CSV, seed CSV |
| Stages analysed | raw → staging → merchant crosswalk (edit distance + manual seed) → candidate match → match selection → mart_reconciliation → mart_review_queue → CSV export |
| Inputs / outputs | gateway_transactions.csv (25,000), bank_settlements.csv (24,750), manual_merchant_corrections.csv (60); mart_reconciliation, mart_review_queue, exports |
| Reconciliation model | gateway-driven, single-stage, rule-based: merchant (crosswalk) + amount within greatest($5, 5%) + settlement in [txn, txn+15d]; rank amount_diff, days; top-2 tie typing; no one-to-one constraint |
| Business rules (confirmed from code) | classification precedence missing → ambiguous → duplicate → mismatch(>0.01) → delayed(>3d) → matched; confidence tiers 1 / 2–4 / ≥5; queue priorities 1–5, cap 30/tier |

## Result totals (authoritative run `evidence/full.xml`)
| Passed | Failed | XFail (confirmed defects, strict) | Skipped | Blocked | Not executed |
|---|---|---|---|---|---|
| **{P}** | **{F}** | **{X}** | {C['skipped']} | 14 pre-existing dbt tests (+4 capability groups, see below) | 0 within the suite |

Total pytest items: {T}. `--runxfail` run: {runx['failed']} failed / {runx['passed']} passed — the {X} failures are exactly the strict-xfail defect tests. A repeat run produced identical counts.

## Commands
{tbl}
Working directory for all commands: repository root.

## Skills and agents
- 6 skills in `.claude/skills/*/SKILL.md`: YAML frontmatter validated with PyYAML (name, description, allowed-tools). Recognition: the session's loaded-skill list later included all 6 (observed after reload; no CLI list command exists, so not verified by a command).
- 7 agents in `.claude/agents/*.md`: frontmatter validated (name matches filename; two descriptions needed quoting and were fixed). Recognition: the session's available-agent list later included all 7 (observed after reload, not verified by a command; `claude agents` manages background sessions, not definitions).
- Delegation actually performed: one `general-purpose` subagent as stand-in for `test-reviewer` (read-only on repo, mutations on /tmp copies; report reviewed and acted on, see test_review.md). No other agent was delegated; analysis, test authoring, control validation and reporting were done in the primary session.

## Defects
{dtab}
Defects fixed: **none** — no source change was made (fixes need semantic confirmation; see recommended_fixes.md).

## Source-code / test-code changes
Application source: **none**. New/untracked files (inventory):
{inv}

`.git/info/exclude` (local, untracked-by-design) got `.venv/`, `__pycache__/`, `.pytest_cache/`.

## Control-total results
CT001 25,000 mart rows = gateway rows ✔ · CT002 categories sum to 25,000 ✔ (matched 21,232; amount_mismatch 1,800; delayed 1,003; duplicate 805; missing_settlement 138; needs_manual_review 22) · CT003 gateway $ preserved ✔ · CT004 signed diff ✔ ·
CT005 local = BigQuery export categories ✔ · **RG001 matched settlement dollars exceed bank dollars by $54,698.65 ✘ (PAYREC-001)** · RG005 ~1,383–1,387 bank settlements ($357.6k) unaccounted ✘ (PAYREC-003) · CT015 missing-settlement recall 106/1,000 with 32 false alarms (observed, no threshold specified).

## Failure injection
{chr(10).join('- ' + l for l in mut)}

(Run against the suite before review fixes; not repeated afterwards — Not re-verified. The reviewer's own 23 mutations: 22 caught.)

## Blocked / limitations
{chr(10).join('- ' + b for b in BLOCKED)}
- Performance: no requirement or baseline; full suite wall time {next(c for c in cmds if c['name'].startswith('FULL suite (auth'))['seconds']} s (observed, ungraded).
- Harness translates BigQuery SQL to DuckDB; unproven for BigQuery-only semantics (mitigated by CT005 category equality).

## Assumptions requiring confirmation
{chr(10).join('- ' + a for a in ASSUME)}

## Reproduce / rerun
```
{RERUN}
```
"""
(DOC / "execution_report.md").write_text(md)

# ---------------- HTML ----------------
e = html.escape
def badge(s):
    cls = {"PASSED":"p","FAILED":"f","XFAIL (defect)":"x","SKIPPED":"s","BLOCKED":"b","NOT EXECUTED":"n"}.get(s,"n")
    return f'<span class="b {cls}">{e(s)}</span>'
cov = "".join(f"<tr><td>{e(r['req'])}</td><td>{e(r['stage'])}</td><td>{e(r['rule'])}</td><td>{e(r['ev'])}</td><td>{e(r['tc'])}</td><td>{e(r['ty'])}</td><td>{e(r['fx'])}</td><td>{e(r['ex'])}</td><td>{badge(r['status'])}</td><td>{e(r['d'] or '—')}</td><td>{e(r['nt'] or '—')}</td></tr>" for r in rows)
cmdrows = "".join(f"<tr><td>{e(c['name'])}</td><td><code>{e(c['command'])}</code></td><td>{c['exit_code']}</td>" + (f"<td>{c['counts']['passed']}</td><td>{c['counts']['failed']}</td><td>{c['counts']['xfailed']}</td><td>{c['counts']['skipped']}</td><td>{c['counts']['total']}</td>" if c['counts'] else "<td colspan=5>"+badge("BLOCKED" if c['exit_code']==127 else "NOT EXECUTED")+" Not verified</td>") + "</tr>" for c in cmds)
sev = {}
for a,b,c,d in DEFECTS: sev[b] = sev.get(b,0)+1
sevrow = "".join(f"<td>{sev.get(k,0)}</td>" for k in ("Critical","High","Medium","Low"))
defrows = "".join(f"<tr><td>{a}</td><td><span class='sev {b}'>{b}</span></td><td>{e(c)}</td><td>{e(d)}</td><td>Not fixed (strict xfail)</td></tr>" for a,b,c,d in DEFECTS)
H = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Payment Reconciliation Pipeline - Testing Report</title>
<style>
body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1d2330;margin:0;background:#f5f6f8}}
header{{background:#1f3a5f;color:#fff;padding:24px 40px}} main{{max-width:1200px;margin:auto;padding:20px 40px}}
section{{background:#fff;border:1px solid #dde1e8;border-radius:8px;padding:16px 24px;margin:16px 0}} h2{{margin-top:0;color:#1f3a5f;font-size:18px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}} th,td{{border:1px solid #dde1e8;padding:5px 8px;text-align:left;vertical-align:top}} th{{background:#eef1f6}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap}} .k{{flex:1;min-width:130px;padding:12px;border-radius:8px;border:1px solid #dde1e8;text-align:center}} .k b{{display:block;font-size:26px}}
.b{{padding:1px 8px;border-radius:10px;font-size:11.5px;font-weight:600;white-space:nowrap}}
.p{{background:#d9f2e0;color:#14622b}} .f{{background:#fbd9d9;color:#8c1a1a}} .x{{background:#fde8c8;color:#8a4b00}} .s{{background:#e5e5e5;color:#444}} .b-{{}} .n{{background:#e8e0f5;color:#4b2a8c}}
.b.b{{background:#ffe9a8;color:#6b5100}}
.sev{{padding:1px 8px;border-radius:4px;color:#fff;font-weight:600}} .Critical{{background:#a3141e}} .High{{background:#d9541e}} .Medium{{background:#d9a21e}} .Low{{background:#5b7aa6}}
pre{{background:#101826;color:#dfe6f2;padding:12px;border-radius:6px;overflow:auto;font-size:12px}} code{{font-size:12px}}
</style></head><body>
<header><h1>Payment Reconciliation Pipeline &mdash; Testing Report</h1><div>{e(branch)} @ {commit[:10]} &middot; generated from evidence/full.xml</div></header><main>
<section><h2>1. Executive summary</h2><p>The pipeline's own dbt SQL was executed locally (BigQuery&rarr;DuckDB) against {T} automated checks:
<b>{P} passed, {F} failed, {X} confirmed-defect checks (strict expected failures)</b>, {C['skipped']} skipped. Eight defects were confirmed; none was fixed because every fix changes matching semantics and needs owner confirmation.
The most serious: <b>one bank settlement can be assigned to many transactions</b> &mdash; matched settlement dollars ($6,258,100.98) exceed the bank's positive dollars ($6,203,402.33) by $54,698.65 (PAYREC-001, Critical). The 14 pre-existing dbt tests could not be run through dbt (no dbt/BigQuery); their logic was re-executed as SQL equivalents and passed.</p>
<div class="kpis"><div class="k p"><b>{P}</b>Passed</div><div class="k f"><b>{F}</b>Failed</div><div class="k x"><b>{X}</b>XFail (defects)</div><div class="k s"><b>{C['skipped']}</b>Skipped</div><div class="k b"><b>14</b>Blocked (dbt tests via dbt)</div><div class="k n"><b>0</b>Not executed (in suite)</div></div></section>
<section><h2>2. Repository and environment</h2><table><tr><th>Root</th><td>{e(str(REPO))}</td></tr><tr><th>Branch / commit</th><td>{e(branch)} / {commit}</td></tr><tr><th>Runtime</th><td>{e(vers)}; Claude Code 2.1.310; Linux x86_64</td></tr><tr><th>Stack</th><td>dbt Core + BigQuery SQL; Python scripts; CSV</td></tr></table></section>
<section><h2>3. Architecture summary</h2><p>Raw gateway and bank CSVs (no shared ID) &rarr; staging casts &rarr; merchant crosswalk (edit distance + 60 manual corrections) &rarr; candidate join &rarr; rank/tie typing &rarr; <code>mart_reconciliation</code> &rarr; <code>mart_review_queue</code> (+ CSV exports for Tableau).</p></section>
<section><h2>4. Source-to-target data flow</h2><pre>gateway_transactions.csv -&gt; stg_gateway_transactions --------\\
bank_settlements.csv     -&gt; stg_bank_settlements -&gt; int_discovered_merchant_crosswalk -&gt; int_final_merchant_crosswalk (+ seed)
                                                          \\-&gt; int_candidate_matches -&gt; int_match_selection
                                                                 -&gt; mart_reconciliation -&gt; mart_review_queue -&gt; data/mart_*_export.csv</pre></section>
<section><h2>5. Reconciliation model</h2><p>Gateway-driven, single-stage, rule-based; tolerance + time-window; one chosen settlement per transaction but <b>no exclusivity across transactions</b>. Precedence: missing &rarr; ambiguous &rarr; duplicate &rarr; amount_mismatch (&gt;0.01) &rarr; delayed (&gt;3 calendar days) &rarr; matched.</p></section>
<section><h2>6. Matching-rule summary</h2><table><tr><th>Rule</th><th>Value</th></tr><tr><td>Merchant</td><td>exact on crosswalk-resolved merchant</td></tr><tr><td>Amount</td><td>|gateway&minus;settled| &le; greatest($5.00, 5% of gateway)</td></tr><tr><td>Window</td><td>txn_ts &le; settlement_date &le; txn_ts + 15 days (inclusive)</td></tr><tr><td>Rank</td><td>amount_diff asc, days_to_settle asc (no final tiebreaker)</td></tr><tr><td>Ties</td><td>top-2 equal amount_diff &rarr; duplicate (same amount+date) else ambiguous</td></tr><tr><td>Confidence</td><td>1 unique; 2&ndash;4 medium; &ge;5 low</td></tr></table></section>
<section><h2>7. Test-scope summary</h2><p>Applicable: staging contracts, source data quality, matching/classification boundaries, review queue, control totals, idempotency, static security. Not applicable (not implemented): currency/FX, fees, tax, refunds, reversals, chargebacks, split/combined settlements, batch/merchant totals, run IDs/audit log. See test_strategy.md.</p></section>
<section><h2>8&ndash;9. Results dashboard</h2><table><tr><th>Passed</th><th>Failed</th><th>XFail (defect)</th><th>Skipped</th><th>Blocked</th><th>Not executed</th><th>Total items</th></tr><tr><td>{badge('PASSED')} {P}</td><td>{badge('FAILED')} {F}</td><td>{badge('XFAIL (defect)')} {X}</td><td>{badge('SKIPPED')} {C['skipped']}</td><td>{badge('BLOCKED')} 14 dbt tests</td><td>{badge('NOT EXECUTED')} 0</td><td>{T}</td></tr></table>
<h3>Commands</h3><table><tr><th>Group</th><th>Command</th><th>Exit</th><th>Passed</th><th>Failed</th><th>XFail</th><th>Skipped</th><th>Total</th></tr>{cmdrows}</table></section>
<section><h2>10. Test coverage matrix</h2><p>Families aggregate parametrized cases (a test named for two ids appears under both).</p><table><tr><th>Req</th><th>Stage</th><th>Rule</th><th>Evidence</th><th>Test</th><th>Type</th><th>Fixture</th><th>Expected</th><th>Status</th><th>Defect</th><th>Notes</th></tr>{cov}</table></section>
<section><h2>11. Data-quality findings</h2><ul><li>25,000 gateway / 24,750 settlement rows: ids unique and well-formed, no nulls, amounts &le;2 dp, gateway amounts 5.02&ndash;500.00, all status = completed.</li><li><b>16 negative settlements (&minus;$173.26) violate the repo's own non-negative rule</b> (PAYREC-002).</li><li>All 258 descriptors resolve to known merchants; seed unique and referentially valid; no card-like or e-mail values in any fixture.</li></ul></section>
<section><h2>12. Reconciliation-control results</h2><table><tr><th>Control</th><th>Result</th></tr><tr><td>mart rows = gateway rows (25,000)</td><td>{badge('PASSED')}</td></tr><tr><td>category counts sum to total</td><td>{badge('PASSED')}</td></tr><tr><td>gateway $ preserved</td><td>{badge('PASSED')}</td></tr><tr><td>local run = committed BigQuery export (categories)</td><td>{badge('PASSED')}</td></tr><tr><td>matched settlement $ &le; bank $</td><td>{badge('XFAIL (defect)')} excess $54,698.65</td></tr><tr><td>every bank settlement accounted for</td><td>{badge('XFAIL (defect)')} ~1,383&ndash;1,387 / ~$357.6k unreported</td></tr><tr><td>injected-missing recall (observed)</td><td>106 / 1,000; 32 false alarms</td></tr></table></section>
<section><h2>13. Defects by severity</h2><table><tr><th>Critical</th><th>High</th><th>Medium</th><th>Low</th></tr><tr>{sevrow}</tr></table></section>
<section><h2>14. Detailed defects</h2><table><tr><th>ID</th><th>Severity</th><th>Summary</th><th>Tests</th><th>Fix status</th></tr>{defrows}</table><p>Full reproduction, expected/actual, impact and proposed fix: defect_report.md.</p></section>
<section><h2>15. Changes made</h2><p>Application source: none. Added: tests/, pytest.ini, .claude/skills (6), .claude/agents (7), docs/claude_testing/. Tracked files modified: {len(modified)}.</p></section>
<section><h2>16. Risks and limitations</h2><ul>{''.join('<li>'+e(b)+'</li>' for b in BLOCKED)}<li>Local engine is DuckDB via sqlglot, not BigQuery.</li><li>Skills/agents: files validated; all 6 skills and 7 agents later appeared in the session's loaded lists (observed, not command-verified).</li><li>Mutation run predates review-driven test additions.</li></ul><h3>Assumptions needing confirmation</h3><ul>{''.join('<li>'+e(a)+'</li>' for a in ASSUME)}</ul></section>
<section><h2>17. Recommended fixes</h2><ol><li>Deterministic tiebreaker (settlement_id) &mdash; PAYREC-004.</li><li>One-to-one assignment &mdash; PAYREC-001.</li><li>Test non-negativity on staging; define negative-amount handling &mdash; PAYREC-002.</li><li>Unmatched-settlement model &mdash; PAYREC-003.</li><li>Run IDs, timestamps, rule codes, run summary.</li><li>Credential handling, README, orphan model hygiene &mdash; PAYREC-005..008.</li></ol></section>
<section><h2>18. Rerun instructions</h2><pre>{e(RERUN)}</pre></section>
<section><h2>19. Evidence references</h2><ul><li>docs/claude_testing/evidence/full.xml, full.txt, full_repeat.xml, full_runxfail.xml, runxfail_output.txt, commands.json, mutation_output.txt</li><li>Markdown: workspace_baseline, initial_assessment, environment_setup, test_strategy, test_coverage_matrix, test_review, execution_report, defect_report, recommended_fixes</li></ul></section>
<section><h2>20. Conclusion</h2><p>The pipeline classifies and ranks as documented at the boundaries tested ({P} checks pass, categories reproduce the BigQuery export exactly), but its reconciliation is <b>not one-to-one</b>, so matched volumes and settlement-level outputs cannot be trusted as a control until PAYREC-001 and PAYREC-004 are resolved. Nothing was run against BigQuery.</p></section>
</main></body></html>"""
(DOC / "final_testing_report.html").write_text(H)
print("built", P, F, X, len(files))
