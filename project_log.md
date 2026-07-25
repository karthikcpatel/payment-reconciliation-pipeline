# Payment Reconciliation Pipeline — Full Project Log

A chronological record of everything built, every question that came up, and how each was resolved. Intended as raw material for the README, interview prep, and your own reference.

---

## Shift 0 — Environment Setup

**Steps taken:**
- Created a Google Cloud project (`fintech-reconciliation`), enabled the BigQuery API
- Created a dedicated service account (`dbt-service-account`) with a JSON key — kept separate from personal Google login, standard practice for automated pipelines
- Set up a Python virtual environment, installed `dbt-bigquery`
- Ran `dbt init`, configured `profiles.yml` (service account auth, `australia-southeast1`/US location, 300s timeout)
- Initialized Git, set up `.gitignore` to exclude the service account key and venv

**Problems hit and how they were solved:**
- **SSL certificate error** during `pip install` — macOS Python wasn't trusting standard certificates. Fixed via Python's built-in `Install Certificates.command`.
- **`dbt` command resolving to the wrong install** — three separate `dbt` installations existed on the machine (Homebrew, python.org, venv), and a stale shell alias in `.zshrc` kept overriding the correct venv version even after `cd`-ing into the project. Diagnosed via `which dbt`, `type -a dbt`, found two `alias dbt=...` lines in `.zshrc`, removed them permanently with `sed`.
- **Nested/incorrect project path confusion** after `dbt init` — resolved by using `find` to locate the actual `dbt_project.yml` rather than guessing the path.

---

## Shift 1 — Synthetic Data Generation & Loading

**Steps taken:**
- Built a Python generator producing `gateway_transactions.csv` and `bank_settlements.csv`, with four injected anomaly types (missing, amount_mismatch, duplicate, delayed) at realistic rates (~4%/4%/3%/4%), plus 85% clean
- Loaded both as raw tables into BigQuery via a Python script using `WRITE_TRUNCATE` (safe to rerun)
- Validated the generated counts matched the designed anomaly rates exactly

**Question raised:** Would regenerating the data overwrite BigQuery automatically?
**Answer:** No — local CSV regeneration and the BigQuery load are two separate steps; both must be rerun manually.

---

## Shift 2 — First Matching Attempt (Clean Join, Then Rejected)

**Steps taken:**
- Built staging models and a first `mart_reconciliation` joining on a **shared `txn_id`**
- Validated 100% accuracy against the generator's ground truth

**Question raised:** "This seems too easy — are we actually solving a realistic problem?"
**Answer:** No — real gateway/bank systems don't share a transaction ID. The clean join was flagged as an artificial shortcut and scrapped in favor of realistic fuzzy matching.

---

## Shift 2 (continued) — Realistic Fuzzy Matching Redesign

**Redesign:** Removed `txn_id` from settlements entirely; replaced with a mangled `bank_descriptor` (simulating real bank statement text — processor prefixes, truncation, store codes).

**Exploration process (manual SQL detective work):**
- Amount alone → up to ~50 candidate settlements per transaction (too ambiguous)
- Amount + date window → still ~20 candidates
- Added merchant text similarity (`EDIT_DISTANCE`) → meaningfully narrowed ties, but ~1,139 transactions had genuine ties

**Question raised:** Should an LLM be used to do the matching instead of SQL?
**Answer:** No — chose SQL for auditability, cost/speed at scale, and determinism, all of which matter in regulated financial contexts. Documented as the deliberate, defensible choice.

**Composite scoring experiments:**
- Tested weighted blends of merchant-distance vs. amount-closeness — found **amount alone (90.7% top-1 hit rate) beat every blend**, and blending in any merchant weight made results *worse*, not better
- Switched to a **lexicographic ranking** (amount primary, merchant as tiebreaker only) — improved to 91.99%, later 95.41% overall accuracy

**Critical finding — the accuracy trap:**
- At 95.41% overall accuracy, **missing-settlement recall was 0%** (0 of 320 true missing transactions correctly flagged) — worse than the earlier 69% accuracy version, which at least caught 3.
- Framed as "if you were my boss" exercise: aggregate accuracy is a vanity metric when classes are imbalanced and the rare class is the costliest to miss. Reprioritized around **recall on `missing_settlement`**, not overall accuracy.
- Added a merchant-distance confidence threshold (>11 → `needs_manual_review`) — raised missing recall to ~79%, but flooded the review queue (73% of it was actually clean transactions wrongly flagged).

**Root cause diagnosis:** With only 25 merchant names shared across 8,000 transactions, merchant-text similarity was structurally unreliable — same-merchant collisions were common, and length bias in `EDIT_DISTANCE` unfairly penalized long merchant names.

**Redesign #2 — realistic merchant identity:** Real merchants have a small, *fixed* set of descriptor variants (different stores/processors), not a fresh random mangling every transaction. Rebuilt the generator accordingly, scaled up to **25,000 transactions across 85 merchants**.

**Merchant crosswalk — built without a cheat sheet:**
- Since settlements only have ~258 distinct descriptors (not 24,750), classified each distinct descriptor once via `EDIT_DISTANCE` against the 85 known merchant names — a reverse-engineering approach, not using the generator's true crosswalk
- Flagged 45 low-confidence classifications for manual human review
- **User manually reviewed all 45 by eye** against the real merchant list, corrected 26, left one (`TST*SMI`) deliberately unresolved due to genuine ambiguity (Smith Inc vs. Smith-Mcguire)
- Used the private ground-truth crosswalk **once, legitimately, purely to QA** the final result (not to build it) — found 15 additional "confident" auto-matches that were actually wrong (a real limitation of length-normalized edit distance), corrected those too

**Git hygiene:** Explicitly excluded the true answer-key crosswalk (`merchant_descriptor_crosswalk.csv`) from Git at every stage — verified via `git log --all` that it was never committed, preserving the "reverse-engineered without ground truth" integrity of the repo.

**Final matching result:** 95.82% overall accuracy; `clean`/`delayed`/`duplicate` near-perfect; `missing_settlement` recall remained the honest, documented weak point (~11%) due to same-merchant collisions within the amount/date tolerance window — a structural limit of matching without a shared ID, not a bug.

---

## Shift 3 — Dashboard (Tableau)

**Tooling decision:** Power BI Desktop doesn't run natively on macOS; confirmed via search that Tableau Public doesn't support a live BigQuery connection (file-based sources only). Solution: export `mart_reconciliation` to CSV, connect Tableau Public to the file — standard, legitimate practice.

**Visuals built:**
1. **Reconciliation Rate** (headline %, 84.66%)
2. **Dollar Value by Discrepancy Type** — deliberately excluded `matched` to avoid drowning out the problem categories
3. **Amount Mismatch Distribution** (histogram) — caveat identified and documented: distribution is artificially capped by the matching tolerance itself, so genuinely large mismatches never appear here
4. **Trend over Time** — found and explained a real pattern: `missing_settlement` catch rate rises near the end of the date range. **Verified via weekly cohort query**: a synthetic-data boundary artifact (fewer future same-merchant transactions exist to produce false-positive matches near the data's edge), not a real trend — explicitly documented as such.
5. **Top Merchants by Discrepancy** — hit a **Tableau filter-context bug**: Top N filter was computing on the full unfiltered dataset instead of after excluding `matched`, hiding the real #1 offender (Smith-Mcguire). Fixed via "Add to Context" on the discrepancy-type filter.

**Traced finding:** Smith-Mcguire's inflated mismatch rate was fully attributable to the one deliberately-unresolved `TST*SMI` descriptor (73 settlements) — quantified as a ~3x elevated rate (24.4% vs. 7.4% baseline).

---

## Reframing — What Business Problem Are We Actually Solving?

**Question raised:** "What's the point of this dashboard if it can't answer a business problem?"
**Answer worked out:** The real business problem is verifying that money the gateway believes was charged actually arrived, fast enough to catch revenue leakage, fraud signals, and errors before they compound — at a scale no human can check manually.

**Gap identified:** The existing dashboard showed the *shape* of the problem but didn't tell a human what to actually go look at. Redesigned around five real-question-driven visuals: a dollar-based health metric, an action queue, dollars-at-risk (fixed to be category-aware), dollars-at-risk by merchant, and an aging/staleness view.

---

## Dollar Health Metric — And Why It Was Wrong

**Built:** Total Gateway Amount ($6,278,640), Total Settled Amount ($6,257,028), Dollar Gap ($21,612), Dollar Reconciliation Rate (99.66%).

**Question raised:** "Is this calculation actually valid, given how many missing/mismatched transactions we have?"
**Investigation:** Tested three approaches — current net gap, gross non-matched total, and a category-aware hybrid — against the **true** ground-truth dollar gap.

**Major finding:**
| Approach | Value |
|---|---|
| Reported net gap (Approach A) | $21,612 |
| Gross non-matched (Approach B) | $967,367 |
| Category-aware hybrid (Approach C) | $30,313 |
| **True dollar gap (ground truth)** | **$267,169** |

Even the "correct" formula (C) captured only 11% of the true exposure, because the dollar metric can only be as accurate as the upstream classification — and 862 of 1,000 true `missing` transactions were mislabeled as `amount_mismatch` with tiny (wrong) dollar diffs. **Conclusion: any dollar metric built on this pipeline is a documented lower bound, not a true figure** — a stronger, more honest finding than a clean number would have been.

---

## Confidence Tier & Review Queue

**Steps taken:**
- Checked `num_candidates` distribution (11.5% unique / 47.6% 2-4 candidates / 40.9% 5+ candidates)
- Added `match_confidence` (`unique` / `medium` / `low`) as a first-class mart column
- **Finding:** 88.5% of "matched" transactions came from a pool of 2+ look-alikes; 40.7% from 5+ — the flat 84.66% headline was hiding this uncertainty entirely
- Built `mart_review_queue`: prioritized by real risk (missing → duplicate → ambiguous ties → low-confidence matches → material mismatches), top 30 per tier by dollar exposure, with human-readable `review_reason` per row

---

## TST\*SMI Fix (Root Cause → Resolution)

- Cross-referenced amount/date evidence (legitimate signal, not the cheat sheet) between the two candidate merchants — confirmed `TST*SMI` → Smith-Mcguire
- **Bug hit:** the correction seed was added but never took effect. Diagnosed via checking each layer (seed table → crosswalk table) and found a **hardcoded override** in `int_final_merchant_crosswalk.sql` (`when bank_descriptor = 'TST*SMI' then null`) that ignored the corrections table entirely. Removed it.
- **Confirmed fix:** Smith-Mcguire's anomaly rate normalized from 35.2% → ~12.2%, in line with the dataset's overall baseline.

---

## Spot-Checking Match Reliability (The Core Mechanism Finding)

Tested actual pick accuracy (against private ground truth, used only to grade) for transactions with 5+ candidates, broken out by category:

| Category | Accuracy (5+ candidates) |
|---|---|
| `matched` | 100% (8,668/8,668) |
| `delayed` | 99.5% (406/408) |
| `duplicate` | 92.0% |
| `amount_mismatch` | **5.4%** (36/667) |

**Mechanism identified and confirmed:** categories requiring an *exact-penny* amount match (`matched`, `delayed`) are essentially bulletproof regardless of candidate pool size, because merchant + exact amount uniquely identifies the true transaction. Categories without that constraint (`amount_mismatch`) have no reliable disambiguator once inside a crowded pool — explaining, mechanistically, why ~86% of `amount_mismatch`-labeled transactions were actually mislabeled `missing` cases.

**Correction made mid-analysis:** Initially hypothesized low-value transactions would have *more* candidates (reasoning from the $5 tolerance floor in relative terms). Tested it — found the **opposite**: candidate count rises with transaction amount, because the tolerance window (5% of amount) grows in *absolute* dollars as amount increases, giving high-value transactions a wider net. Corrected the reasoning rather than the data.

---

## Real-World Analyst Role — Two Framings

**With ground truth (what we did for validation):** used privately, after the fact, only to grade — never fed into the live matching logic.

**Without ground truth (what a real analyst actually has):** Discussed explicitly — a real analyst can't *know* an error rate directly. Their actual job is:
1. Notice a symptom (a business complaint, an oddly clean-looking number)
2. Build a case from **observable signals only** (merchant-level rate concentration, candidate-pool correlation, tolerance-boundary clustering in the data's shape)
3. State findings as a **hypothesis**, not a confirmed fact
4. Propose a **verification method** (manual sampling, cross-team confirmation, a controlled test batch) — since there's no answer key to check against
5. Extrapolate carefully from a small verified sample, with explicit humility about confidence

This became the basis for the planned "no-cheat-sheet" analysis writeup — the most differentiated part of the project, since most portfolio projects either skip validation entirely or use ground truth without acknowledging the difference from a real production scenario.

---

## dbt Testing (Completed)

Added 14 tests total: uniqueness and not-null on both marts, `accepted_values` on `discrepancy_type` and `match_confidence`, referential integrity (`relationships`) between `mart_reconciliation` and the staging sources, plus three singular business-rule tests — no negative settled amounts, `days_to_settle` within a sane 0–20 day range, `review_priority` restricted to 1–5. All 14 passing.

---

## No-Cheat-Sheet Analysis Writeup (Completed)

Produced a standalone document (`no_ground_truth_analysis.md`) demonstrating the amount_mismatch investigation as it would have to be conducted with no ground truth available: evidence built purely from observable signals (merchant-level rate concentration, the matching logic's own architecture, candidate-pool scaling by amount, distribution-shape truncation at the tolerance boundary), a hedged hypothesis, an explicit "what this evidence cannot tell us" section, a realistic manual sampling and verification plan, and an interim business recommendation. A clearly separated postscript compares the evidence-only conclusion against the private ground truth (available only because this is a portfolio project) — confirming the hypothesis's direction and, in the ground-truth check, its magnitude (5.4% accuracy at 5+ candidates).

---

## Dashboard Rebuild — Incorporating the Corrected Insights

With `match_confidence` and `mart_review_queue` now built, the original Tableau dashboard (built on the early 8,000-row dataset) was rebuilt from scratch on the current 25,000-row, 85-merchant, TST\*SMI-fixed data.

**Fresh export:** re-pulled `mart_reconciliation` and `mart_review_queue` to CSV via a dedicated export script, since Tableau Public cannot connect live to BigQuery (confirmed via search — this is a genuine platform limitation, not a workaround).

**New/rebuilt tiles:**
- **Match Confidence Breakdown** — replaces the flat reconciliation-rate number. Initially built across all discrepancy types at once (a design mistake, since confidence tiers only meaningfully apply within `matched`); corrected by filtering to `matched` only. Final split: 11.44% unique, 47.74% medium, 40.83% low — meaning under 12% of "clean" transactions were actually unambiguous.
- **Dollar Health Summary** — rebuilt using the category-aware hybrid formula (Approach C from the earlier dollar-gap investigation), explicitly labeled "Known Lower Bound" in the tile title itself, not just in a caption. Hit a real Tableau mechanic issue: setting one measure's mark type to Text didn't apply to the other two measures sharing the sheet — each measure pill needed its mark type set individually. Final numbers: $6,278,640 total gateway volume, $29,246 estimated exposure, 0.47% exposure rate.
- **Amount Mismatch Distribution** — rebuilt on the new data. **Bug caught:** the rebuilt chart initially totaled only 30 transactions instead of the expected 1,800+; traced to the sheet accidentally being connected to the `mart_review_queue` export (capped at top-30-per-priority-tier) instead of the full `mart_reconciliation` export. Fixed by switching data sources. Correct shape confirmed: ~1,450 transactions clustered at $0–5, tapering sharply by $15–20.
- **Trend over Time** — rebuilt on the new data; the late-June `missing_settlement` spike (the date-boundary artifact identified earlier) was even more visible this time, rising roughly 5x above its baseline in the final week — same explanation as before, confirmed again on the larger dataset.
- **Top Merchants by Dollar Exposure** — rebuilt with two deliberate changes: dollar-weighted instead of count-weighted ranking (via `Estimated Exposure`), and the `Discrepancy Type` filter added to Context *before* applying the Top N filter this time, avoiding the same filter-order bug hit in the original build. **Result, directly attributable to the TST\*SMI fix:** Smith-Mcguire no longer appears in the top 10 at all — a clean, provable before/after outcome from Shift 2's root-cause investigation.

**Design decision — Review Queue excluded from the dashboard canvas.** Built as its own worksheet (priority-sorted primary, dollar-exposure-sorted secondary within each tier — required fixing sort order twice, since the initial version sorted by `Review Reason` alphabetically and by `Txn Id` alphabetically rather than by the intended priority/exposure fields), but deliberately kept as a separate tab rather than added to the dashboard canvas itself, since the user judged five tiles already fully occupied the space without adding a long scrollable table.

**Dashboard notes tile:** a plain-language caveats panel added directly to the dashboard (not just in the README), covering: the confidence breakdown, the dollar-gap lower bound, the tolerance-capped histogram, and the trend-chart artifact — so the honest picture travels with the visual itself.

**Color-convention fix:** the Match Confidence chart initially had its colors backwards (red = `unique`, the *best* tier; green = `low`, the *worst* tier) — an easy-to-miss mistake that would make the chart read opposite to its intended meaning at a glance. Corrected to standard stoplight convention (green = safe/unique, red = needs attention/low).

---

## Interviewer-Proofing the "Suspiciously Clean" 100% Finding

**Question raised:** the 100% (8,668/8,668) match accuracy for crowded-candidate-pool `matched` transactions looks too clean — could this be generator bias, data leakage, or an artifact of a too-small effective sample?

**Answer, built and documented for interview readiness:**
- **Mechanism, not luck:** `matched` requires both an exact merchant match and an exact-to-the-cent amount match. Two different transactions from the same merchant coincidentally sharing an identical cent-amount within the matching window is rare given continuous amounts across a $5–$500 range and ~294 transactions per merchant on average.
- **Selection effect, not perfection:** whenever two candidates genuinely do tie on amount, the pipeline's tie-detection logic explicitly reroutes those cases to `duplicate` or `needs_manual_review`, never `matched`. The 100% figure describes a population that has already had its ambiguous cases removed by design — this is a property of the label definition, not proof the underlying heuristic never errs.
- **No leakage:** the private ground-truth file was confirmed (via `git log --all`) to have never been committed to the repository at any point, and was used only after classification to grade results, never inside the matching SQL itself.
- **No generator bias:** amounts are drawn independently at random per transaction with no dedup logic in the generator, so the rarity of exact-amount collisions is a natural consequence of the sampling range and volume, not an engineered outcome.
- **Corroborating evidence against rigging:** `delayed` transactions share the identical exact-amount constraint as `matched`, and came back at 99.5%, not 100% (406/408, 2 genuine misses) — a more organically imperfect number that supports the method producing real, if rare, errors rather than being artificially forced to report success everywhere.
- **A falsifiable, reproducible check was written** (a `GROUP BY merchant, gateway_amount HAVING COUNT(*) > 1` query) to find any real same-merchant, same-exact-amount collisions in the data and verify they were correctly routed to `duplicate`/`needs_manual_review` rather than silently misclassified as `matched` — kept ready to run live if challenged on this point in an interview setting.

---

## GitHub Publishing (In Progress)

Repo created at `github.com/gsudheesh/payment-reconciliation-pipeline`. Working through: local `git status` verification (checking no service account key, no true merchant crosswalk answer key, and no other `_private_*` files are staged), then `git add` / `commit` / `push` of the full project including the newly written `README.md`, `no_ground_truth_analysis.md`, and this log.

---

## Outstanding / Next Steps

1. ~~No-cheat-sheet analysis writeup~~ — done
2. ~~Dashboard rebuild~~ — done
3. ~~dbt tests~~ — done
4. ~~README~~ — done, full deep-dive version written, DA-weighted per request, all em-dash/double-hyphen punctuation removed for tone
5. **Push everything to GitHub** — in progress
6. **Optional stretch:** reconstruct and document key exploratory SQL queries that were run directly in the BigQuery console and never saved as files, since the README and this log both reference specific queries (the crosswalk discovery query, the confusion-matrix validation query, the candidate-pool-by-amount query, the exact-match collision check) that currently exist only as chat history, not as committed artifacts
7. **Optional stretch:** the manual sampling and verification exercise proposed in the no-cheat-sheet writeup's Section 5, actually carried out in miniature
