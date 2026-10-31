# Independent Test Review (Phase 8)

## How it was performed
1. **Delegated review.** A subagent was spawned (type `general-purpose`, because the project `.claude/agents/*` definitions are not loaded in an already-running session; it was instructed to follow `.claude/agents/test-reviewer.md`). It read the suite, ran 23 of its own mutations on `/tmp` copies of `models/` (via `PAYREC_MODELS_DIR`) and reported without editing repo files. 22/23 were caught; the survivor (tie test `=` → `>= second−0.001`) is near-equivalent because amounts have 2 dp.
2. **Primary-session failure injection** (`evidence/mutation_run.py`, output `evidence/mutation_output.txt`): 16 mutations on temp copies of models/ (tolerance floor/pct, window length/start, mismatch/delay thresholds, confidence tiers, ranking order, duplicate rule, queue cap/thresholds/exposure, precedence, crosswalk override, staging cast). **16/16 detected**; each was caught by at least one targeted fixture test (RC/RQ/ST), not only by data-pinned tests. Note: this run executed against the suite as it was *before* the review fixes below (113 passed + 16 xfailed baseline); it was not repeated after the fixes (Not re-verified).
3. Strict-xfail tests were additionally run with `--runxfail` to prove each fails for the intended assertion (evidence/runxfail_output.txt): 16/16 failed on their assertion message.

## Findings and what was done
| Finding (reviewer) | Action |
|---|---|
| xfail tests would also "pass" on harness/SQL errors | **Fixed**: all 16 now `xfail(strict=True, raises=AssertionError)` |
| ST002 redundant `or` clause, type unchecked | **Fixed**: asserts `Decimal("12.50")` and exact datetime |
| FI003 trivially true | **Fixed**: compares full raw rows |
| SEC001/002 scanned only tracked files | **Fixed**: `git ls-files --cached --others --exclude-standard` (own scanner excluded) |
| RC008 one-directional | **Added** RC008b |
| No direct tests for discovered crosswalk | **Added** ST012, ST013 |
| Only 2-way ties covered | **Added** RC021 (3-way), RC022 (tie+mismatch), RC023 (midnight/calendar-day) |
| Pytest.raises(duckdb.Error) accepts any error (ST003/4/7, FI002) | **Open** – error text differs across engines; accepted risk, documented |
| RG003, CT015, CT008, CT006 pin data-specific values / arbitrary 140/142 tolerance; will fail "for the wrong reason" after a legitimate fix | **Open / by design**: they are regression pins; they must be re-baselined with the PAYREC-001/004 fixes |
| RG003b, RG006 rely on tie nondeterminism (strict xfail could turn red if two runs coincide) | **Open risk**: observed 104 and 403 differences, probability of coincidence negligible but not zero |
| RC018/FI001 use tie-free data (cannot detect PAYREC-004) | Accepted; RC017/RG003b cover ties |
| Queue gaps: cap on tiers other than 1, ties at cap boundary, review_reason text per tier, delayed + ≥5 candidates | **Open** |
| Staging: whitespace/case in merchant, null merchant/txn_id, tz-aware timestamps | **Open** (tz not in scope: no tz field) |
| Per-merchant settlement-side conservation control | **Open** |
| Repo singular dbt tests lack negative controls (only non-negative has one) | **Open** |
| DQ015 vs CT016 duplicate | Accepted (different scope) |

## Remaining untested / unverifiable behaviour
BigQuery-native behaviour (dbt run/test, `edit_distance`, NUMERIC overflow, load autodetect), all lifecycle/fee/refund/chargeback/currency/FX scenarios (not implemented in the repository), exit codes of dbt, export-script behaviour, private ground-truth accuracy figures (README: 95.82%, $267,169) — **not verifiable here**.

## False-positive / false-negative risk summary
- False positives: engine difference (DuckDB vs BigQuery) could make a green local test not green in BigQuery; mitigated by CT005 (categories identical on 25,000 rows), not eliminated.
- False negatives: weaker `pytest.raises(duckdb.Error)`; data-pinned controls inherit PAYREC-004 variance (only invariants — categories, totals — are pinned, not settlement ids).
