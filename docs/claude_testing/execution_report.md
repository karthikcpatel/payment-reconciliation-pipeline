# Execution Report

| Item | Value |
|---|---|
| Repository | payment-reconciliation-pipeline |
| Root | /home/labuser/payment-reconciliation-pipeline |
| Branch / commit | main / e48ef635061900c168b1e6891174eaec1e379754 (working tree otherwise unchanged: **0 tracked files modified**) |
| Environment | Linux (Ubuntu, kernel 7.0.0-1003-gcp); Python 3.14.4; pytest 9.1.1; duckdb 2.0.0; sqlglot 30.24.0; pandas 3.1.0; Claude Code 2.1.310 |
| Stack (confirmed) | dbt Core + BigQuery SQL, Python scripts (pandas/Faker/google-cloud-bigquery), CSV, seed CSV |
| Stages analysed | raw → staging → merchant crosswalk (edit distance + manual seed) → candidate match → match selection → mart_reconciliation → mart_review_queue → CSV export |
| Inputs / outputs | gateway_transactions.csv (25,000), bank_settlements.csv (24,750), manual_merchant_corrections.csv (60); mart_reconciliation, mart_review_queue, exports |
| Reconciliation model | gateway-driven, single-stage, rule-based: merchant (crosswalk) + amount within greatest($5, 5%) + settlement in [txn, txn+15d]; rank amount_diff, days; top-2 tie typing; no one-to-one constraint |
| Business rules (confirmed from code) | classification precedence missing → ambiguous → duplicate → mismatch(>0.01) → delayed(>3d) → matched; confidence tiers 1 / 2–4 / ≥5; queue priorities 1–5, cap 30/tier |

## Result totals (authoritative run `evidence/full.xml`)
| Passed | Failed | XFail (confirmed defects, strict) | Skipped | Blocked | Not executed |
|---|---|---|---|---|---|
| **119** | **0** | **16** | 0 | 14 pre-existing dbt tests (+4 capability groups, see below) | 0 within the suite |

Total pytest items: 135. `--runxfail` run: 16 failed / 119 passed — the 16 failures are exactly the strict-xfail defect tests. A repeat run produced identical counts.

## Commands
| Group / command | Exit | Passed | Failed | XFail | Skipped | Total | Sec |
|---|---|---|---|---|---|---|---|
| G0 baseline: pre-existing dbt tests (dbt CLI)<br>`dbt --version` | 127 | n/a | n/a | n/a | n/a | n/a | 0.0 |
| G0 baseline: bare pytest collection of root script<br>`.venv/bin/python -m pytest --collect-only -q -p no:cacheprovider test_composite_score.py` | 2 | n/a | n/a | n/a | n/a | n/a | 1.0 |
| G1 unit (staging)<br>`.venv/bin/python -m pytest tests/unit -q -p no:warnings -p no:cacheprovider` | 0 | 16 | 0 | 0 | 0 | 16 | 2.4 |
| G2 data_quality<br>`.venv/bin/python -m pytest tests/data_quality -q -p no:warnings -p no:cacheprovider` | 0 | 14 | 0 | 1 | 0 | 15 | 3.7 |
| G3 reconciliation<br>`.venv/bin/python -m pytest tests/reconciliation -q -p no:warnings -p no:cacheprovider` | 0 | 51 | 0 | 5 | 0 | 56 | 7.3 |
| G4 controls<br>`.venv/bin/python -m pytest tests/controls -q -p no:warnings -p no:cacheprovider -s` | 0 | 28 | 0 | 0 | 0 | 28 | 2.8 |
| G5 regression<br>`.venv/bin/python -m pytest tests/regression -q -p no:warnings -p no:cacheprovider` | 0 | 5 | 0 | 6 | 0 | 11 | 5.1 |
| G6 security<br>`.venv/bin/python -m pytest tests/security -q -p no:warnings -p no:cacheprovider` | 0 | 5 | 0 | 4 | 0 | 9 | 3.5 |
| FULL suite (authoritative)<br>`.venv/bin/python -m pytest tests -q -p no:warnings -p no:cacheprovider -s` | 0 | 119 | 0 | 16 | 0 | 135 | 15.7 |
| FULL suite repeat (repeatability)<br>`.venv/bin/python -m pytest tests -q -p no:warnings -p no:cacheprovider` | 0 | 119 | 0 | 16 | 0 | 135 | 16.0 |
| FULL suite --runxfail (defect evidence)<br>`.venv/bin/python -m pytest tests -q -p no:warnings -p no:cacheprovider --runxfail` | 1 | 119 | 16 | 0 | 0 | 135 | 15.6 |

Working directory for all commands: repository root.

## Skills and agents
- 6 skills in `.claude/skills/*/SKILL.md`: YAML frontmatter validated with PyYAML (name, description, allowed-tools). Recognition: the session's loaded-skill list later included all 6 (observed after reload; no CLI list command exists, so not verified by a command).
- 7 agents in `.claude/agents/*.md`: frontmatter validated (name matches filename; two descriptions needed quoting and were fixed). Recognition: the session's available-agent list later included all 7 (observed after reload, not verified by a command; `claude agents` manages background sessions, not definitions).
- Delegation actually performed: one `general-purpose` subagent as stand-in for `test-reviewer` (read-only on repo, mutations on /tmp copies; report reviewed and acted on, see test_review.md). No other agent was delegated; analysis, test authoring, control validation and reporting were done in the primary session.

## Defects
| ID | Severity | Summary | Tests |
|---|---|---|---|
| PAYREC-001 | Critical | Settlement assigned to multiple transactions (double counting): mart settled $6,258,100.98 vs bank $6,203,402.33 (+$54,698.65) | RC016, RC016b, RG001, RG002, RG003 |
| PAYREC-002 | High | Negative settlements (16, −$173.26) silently dropped; repo non-negative dbt test vacuous | DQ007, RC020, RG004 |
| PAYREC-003 | Medium | Bank-side orphans (~1,383–1,387, ≈$357.6k) reported nowhere (needs confirmation) | RC019, RG005 |
| PAYREC-004 | Medium | Non-deterministic selection among equal-rank candidates (104 diffs between identical runs; 403 vs BigQuery export) | RC017, RG003b, RG006 |
| PAYREC-005 | Low | Hard-coded credential-file path/project id in 13 scripts | SEC004 |
| PAYREC-006 | Low | Root test_composite_score.py collected by bare pytest (needs BigQuery) | SEC006 |
| PAYREC-007 | Low | README ranking description ≠ SQL | SEC008 |
| PAYREC-008 | Low | Orphan model int_merchant_classification | SEC009 |

Defects fixed: **none** — no source change was made (fixes need semantic confirmation; see recommended_fixes.md).

## Source-code / test-code changes
Application source: **none**. New/untracked files (inventory):
- `.claude/agents/data-quality-tester.md`
- `.claude/agents/payment-pipeline-analyst.md`
- `.claude/agents/reconciliation-control-reviewer.md`
- `.claude/agents/reconciliation-test-engineer.md`
- `.claude/agents/test-reporting-agent.md`
- `.claude/agents/test-reviewer.md`
- `.claude/agents/transformation-test-engineer.md`
- `.claude/skills/etl-test-automation/SKILL.md`
- `.claude/skills/payment-data-quality-testing/SKILL.md`
- `.claude/skills/payment-pipeline-analysis/SKILL.md`
- `.claude/skills/pipeline-test-reporting/SKILL.md`
- `.claude/skills/reconciliation-control-validation/SKILL.md`
- `.claude/skills/reconciliation-rule-testing/SKILL.md`
- `docs/claude_testing/defect_report.md`
- `docs/claude_testing/environment_setup.md`
- `docs/claude_testing/evidence/_exec_table.md`
- `docs/claude_testing/evidence/full.txt`
- `docs/claude_testing/evidence/full.xml`
- `docs/claude_testing/evidence/full_repeat.txt`
- `docs/claude_testing/evidence/full_repeat.xml`
- `docs/claude_testing/evidence/full_runxfail.txt`
- `docs/claude_testing/evidence/full_runxfail.xml`
- `docs/claude_testing/evidence/g1_unit.txt`
- `docs/claude_testing/evidence/g1_unit.xml`
- `docs/claude_testing/evidence/g2_dq.txt`
- `docs/claude_testing/evidence/g2_dq.xml`
- `docs/claude_testing/evidence/g3_rec.txt`
- `docs/claude_testing/evidence/g3_rec.xml`
- `docs/claude_testing/evidence/g4_ctl.txt`
- `docs/claude_testing/evidence/g4_ctl.xml`
- `docs/claude_testing/evidence/g5_reg.txt`
- `docs/claude_testing/evidence/g5_reg.xml`
- `docs/claude_testing/evidence/g6_sec.txt`
- `docs/claude_testing/evidence/g6_sec.xml`
- `docs/claude_testing/evidence/mutation_output.txt`
- `docs/claude_testing/evidence/mutation_run.py`
- `docs/claude_testing/evidence/runxfail_output.txt`
- `docs/claude_testing/execution_report.md`
- `docs/claude_testing/final_testing_report.html`
- `docs/claude_testing/initial_assessment.md`
- `docs/claude_testing/manager_summary.md`
- `docs/claude_testing/recommended_fixes.md`
- `docs/claude_testing/test_coverage_matrix.md`
- `docs/claude_testing/test_review.md`
- `docs/claude_testing/test_strategy.md`
- `docs/claude_testing/tools/build_final.py`
- `docs/claude_testing/tools/build_reports.py`
- `docs/claude_testing/tools/run_all.py`
- `docs/claude_testing/workspace_baseline.md`
- `pytest.ini`
- `tests/__init__.py`
- `tests/conftest.py`
- `tests/controls/test_control_totals.py`
- `tests/data_quality/test_source_data.py`
- `tests/harness/__init__.py`
- `tests/harness/dbt_local.py`
- `tests/reconciliation/test_matching_rules.py`
- `tests/reconciliation/test_review_queue.py`
- `tests/regression/test_defects_at_scale.py`
- `tests/regression/test_failure_and_idempotency.py`
- `tests/security/test_static_scan.py`
- `tests/unit/test_staging.py`

`.git/info/exclude` (local, untracked-by-design) got `.venv/`, `__pycache__/`, `.pytest_cache/`.

## Control-total results
CT001 25,000 mart rows = gateway rows ✔ · CT002 categories sum to 25,000 ✔ (matched 21,232; amount_mismatch 1,800; delayed 1,003; duplicate 805; missing_settlement 138; needs_manual_review 22) · CT003 gateway $ preserved ✔ · CT004 signed diff ✔ ·
CT005 local = BigQuery export categories ✔ · **RG001 matched settlement dollars exceed bank dollars by $54,698.65 ✘ (PAYREC-001)** · RG005 ~1,383–1,387 bank settlements ($357.6k) unaccounted ✘ (PAYREC-003) · CT015 missing-settlement recall 106/1,000 with 32 false alarms (observed, no threshold specified).

## Failure injection
- M01 tolerance floor 5.0 -> 6.0                | 8 failed, 105 passed, 16 xfailed in 15.26s | detecting test ids: CT005,CT008,CT012,CT014,CT015,RC002,RG003
- M02 tolerance pct 5% -> 6%                    | 9 failed, 104 passed, 16 xfailed in 13.78s | detecting test ids: CT005,CT006,CT008,CT012,CT014,CT015,RC002,RG003
- M03 window 15d -> 16d                         | 9 failed, 104 passed, 16 xfailed in 39.41s | detecting test ids: CT005,CT006,CT008,CT011,CT012,CT014,CT015,RC004,RG003
- M04 window start allows pre-txn settlement    | 10 failed, 103 passed, 16 xfailed in 67.80s (0:01:07) | detecting test ids: CT005,CT006,CT008,CT009,CT011,CT012,CT014,CT015,RC004,RG003
- M05 mismatch threshold 0.01 -> 0.05           | 3 failed, 110 passed, 16 xfailed in 28.87s | detecting test ids: CT005,RC005
- M06 delayed threshold 3 -> 4                  | 2 failed, 111 passed, 16 xfailed in 15.65s | detecting test ids: CT005,RC006
- M07 confidence medium upper 4 -> 5            | 2 failed, 111 passed, 16 xfailed in 14.05s | detecting test ids: CT005,RC013
- M08 ranking amount_diff asc -> desc           | 7 failed, 106 passed, 16 xfailed in 14.16s | detecting test ids: CT005,CT006,CT007,RC009,RC011b,RG003,RQ004
- M09 true_duplicate requires only same amount  | 4 failed, 109 passed, 16 xfailed in 14.13s | detecting test ids: CT005,CT006,RC011,RQ003
- M10 queue cap 30 -> 25                        | 3 failed, 110 passed, 16 xfailed in 14.33s | detecting test ids: CT006,CT008,RQ007
- M11 queue amount_mismatch threshold >=5 -> >5 | 1 failed, 112 passed, 16 xfailed in 14.10s | detecting test ids: RQ005
- M12 queue matched low-confidence >=5 -> >=6   | 2 failed, 111 passed, 16 xfailed in 32.03s | detecting test ids: CT006,RQ004
- M13 exposure for missing uses 0               | 5 failed, 108 passed, 16 xfailed in 42.42s | detecting test ids: CT006,CT007,CT008,RQ001,RQ003
- M14 delayed outranks amount_mismatch          | 3 failed, 110 passed, 16 xfailed in 37.07s | detecting test ids: CT005,CT006,RC007
- M15 crosswalk ignores manual corrections      | 8 failed, 106 passed, 15 xfailed in 34.52s | detecting test ids: CT005,CT006,CT008,CT012,CT015,RC014,RG001,RG003
- M16 staging amount cast to int                | 10 failed, 103 passed, 16 xfailed in 27.75s | detecting test ids: CT003,CT005,CT006,CT008,CT012,CT015,RC012,RG003,ST002,ST011

(Run against the suite before review fixes; not repeated afterwards — Not re-verified. The reviewer's own 23 mutations: 22 caught.)

## Blocked / limitations
- 14 pre-existing dbt tests via `dbt test` (dbt not installed, no BigQuery project/credentials) — their logic was re-executed as equivalent SQL (CT009 ×4, CT010 ×10): all passed, but that is not a dbt run
- load_to_bigquery.py, export_for_*.py, validate_*.py, spot_check/compare/measure/check/review scripts (BigQuery credentials)
- Private ground-truth validations (files git-ignored, absent); README accuracy figures not verifiable
- Exit-code, rollback, checkpoint, output-write-failure tests (no writers/services exist in repo or need BigQuery)
- Performance: no requirement or baseline; full suite wall time 15.7 s (observed, ungraded).
- Harness translates BigQuery SQL to DuckDB; unproven for BigQuery-only semantics (mitigated by CT005 category equality).

## Assumptions requiring confirmation
- A1 a settlement should satisfy at most one transaction
- A2 negative settlements are invalid
- A3 non-'completed' statuses should (not) be reconciled
- A4 a 1-cent difference is 'matched' by design
- A5 tie-breaks must be deterministic
- A6 bank-side orphans must be reported
- A7 amount_mismatch should outrank delayed

## Reproduce / rerun
```
cd payment-reconciliation-pipeline
python3 -m venv .venv && . .venv/bin/activate && pip install pytest pandas duckdb sqlglot pyyaml pytz
python -m pytest tests                       # full suite (expected: 119 passed, 16 xfailed)
python -m pytest tests/unit                  # staging / crosswalk
python -m pytest tests/data_quality          # source CSV + seed
python -m pytest tests/reconciliation        # matching rules + review queue
python -m pytest tests/controls -s           # control totals, repo dbt tests as SQL
python -m pytest tests/regression            # defect evidence at scale, idempotency
python -m pytest tests/security              # static scans
python -m pytest tests --runxfail            # shows the 16 confirmed-defect failures
python docs/claude_testing/tools/run_all.py && python docs/claude_testing/tools/build_reports.py && python docs/claude_testing/tools/build_final.py   # regenerate evidence+reports
python docs/claude_testing/evidence/mutation_run.py   # failure injection on temp copies (~8 min)
```
