# Reliability of `amount_mismatch` Classifications: An Evidence-Based Investigation Without Ground Truth

**Author's note on scope:** This analysis was deliberately conducted as if no answer key existed — because in a real production environment, one never does. Every piece of evidence below comes from signals a working analyst would actually have access to: aggregate rates, distribution shapes, the pipeline's own matching logic, and cross-category comparisons. A postscript at the end compares this evidence-only conclusion against a synthetic ground truth that was available *only* because this is a portfolio project — that comparison is not something a real analyst would ever get to see, and is included purely to validate the methodology, not as part of the investigation itself.

---

## 1. The Starting Question

The reconciliation pipeline classifies transactions into six categories, one of which is `amount_mismatch` — a transaction whose settled amount differs from the expected gateway amount by more than one cent. At current volume, this category accounts for roughly **7.4% of all transactions (1,857 of 25,000)** and is presented on the dashboard as a distinct, trustworthy label.

**The question:** should `amount_mismatch` be trusted at face value, or is there reason to believe some fraction of it is actually something else — misclassified?

No ground-truth answer key is assumed to exist for this section. Every claim below is built from what the pipeline itself outputs, plus reasoning about how the matching logic was designed.

---

## 2. Evidence

### 2.1 — Merchant-level rate concentration (a live case study)

Early in this project, a routine check — average `amount_mismatch` rate by merchant — surfaced one clear outlier: **Smith-Mcguire at 35.2%, against a dataset-wide baseline of ~15%** (unclean-transaction rate at the time). No ground truth was used to notice this; it was a simple `GROUP BY merchant` aggregation.

Investigating further (still without ground truth), it was noted that one specific bank descriptor (`TST*SMI`) had been left deliberately unclassified in the merchant directory during manual QA, due to genuine ambiguity between two similarly-named merchants ("Smith Inc" and "Smith-Mcguire"). Since the matching pipeline requires an *exact* merchant match to consider a settlement as a candidate, every settlement carrying that unclassified descriptor was structurally invisible to matching — meaning any transaction that should have matched against it had no way to do so, and would be forced onto a different, inferior candidate instead.

**Resolution, without ground truth:** the ambiguity was resolved by cross-referencing amount and date evidence — checking which of the two candidate merchants' real transactions better lined up (by amount and settlement timing) against the settlements carrying that descriptor. This produced a confident, evidence-based resolution: `TST*SMI` → Smith-Mcguire.

**Result:** after applying the fix, Smith-Mcguire's anomaly rate dropped from 35.2% to approximately 12.2% — back in line with the dataset baseline. This was measurable and directly observable, with no ground truth required at any point in the diagnosis or the fix.

**What this establishes:** the pipeline's classifications are demonstrably sensitive to gaps in the merchant directory, and at least one entire merchant's `amount_mismatch` rate was artificially inflated by a directory gap rather than reflecting real payment behavior. This raises the question of whether other, less obvious directory or matching gaps could be doing the same thing elsewhere, just without an outlier obvious enough to notice by eye.

### 2.2 — The matching logic itself lacks a disambiguating anchor for this category

This is not a statistical finding — it's architectural, and fully knowable just by reading the pipeline's own rules.

For a transaction to be classified `matched` or `delayed`, the settled amount must equal the gateway amount **exactly** (`amount_diff <= $0.01`). Combined with an exact merchant match, this is an extremely strong constraint — it is very difficult for two *different* real transactions from the same merchant to coincidentally land on the identical amount to the cent.

For `amount_mismatch`, by definition, **no such exact-amount constraint applies** — the whole point of the category is that the amount differs. This means that within a pool of same-merchant, similarly-dated, similarly-priced transactions, there is no strong signal left to distinguish "the real settlement for this specific transaction" from "a different transaction's settlement that merely looks close enough."

**Implication:** any category requiring exact-amount matching should be structurally reliable regardless of how many other candidates exist nearby. Any category *without* that constraint should be expected to degrade as the candidate pool grows — because the tie-breaking signal (closest amount) becomes arbitrary once several candidates are all imperfect matches.

### 2.3 — Candidate pool size scales with transaction amount, compounding the risk

A direct query of `num_candidates` (how many settlements plausibly matched a transaction on merchant + amount tolerance + date window) against transaction amount shows a clear, monotonic relationship:

| Amount bucket | Avg. candidate pool size |
|---|---|
| $5–25 | 2.2 |
| $25–50 | 2.3 |
| $50–100 | 2.5 |
| $100–250 | 3.3 |
| $250–500 | 5.7 |

This is explained by the matching tolerance rule itself (`greater of $5 or 5% of amount`), which produces a **wider absolute dollar window** as transaction amount grows — a $500 transaction has a ±$25 net to catch coincidental look-alikes, versus ±$5 for a low-value one.

**Why this matters for the question at hand:** if `amount_mismatch` reliability degrades as candidate pools grow (per 2.2), and candidate pools are systematically larger for higher-value transactions (per 2.3), then **the highest-dollar transactions — the ones with the most financial consequence if misclassified — are structurally the least reliably classified.** This is the opposite of what you'd want from a risk-detection system, and it's fully derivable without any ground truth.

### 2.4 — Pervasiveness of ambiguity across the whole pipeline

Even setting `amount_mismatch` aside, a check of confidence within the `matched` category (built specifically to test this) found that **88.5% of "matched" transactions came from a candidate pool of 2 or more**, and **40.7% came from a pool of 5 or more**. Since `matched` has the strongest possible disambiguating signal (exact amount) and still shows this much structural ambiguity in its candidate pools, it stands to reason that `amount_mismatch` — with a strictly weaker signal — sits inside pools of at least comparable, likely greater, ambiguity.

### 2.5 — Distribution shape suggests truncation, not a true fee profile

A histogram of `amount_diff` for `amount_mismatch` transactions shows a sharp concentration near $0–5, tapering to almost nothing by $15–20. On its own this might look like a plausible real-world fee distribution (most fees are small). But the cutoff point closely tracks the pipeline's own matching tolerance parameter (~5%/$5 max). **A distribution that stops exactly where your own filter stops is a red flag that you are looking at the shape of your filter, not the shape of reality** — any true discrepancy larger than the tolerance would never have entered this population at all; it would have been excluded from candidacy entirely and forced into a different category (most plausibly `missing_settlement`, since no settlement within range would exist to match against).

---

## 3. Synthesized Hypothesis

**Amount_mismatch classifications should not be trusted at face value, particularly for transactions drawn from large candidate pools (high-value transactions especially) or for merchants with any known directory ambiguity.** The mechanism is architectural (loss of exact-amount disambiguation) and is indirectly supported by observed rate concentration, distribution shape, and the demonstrated sensitivity to directory gaps in the Smith-Mcguire case.

**Confidence level:** moderate-to-high on the *direction* of the finding (amount_mismatch is less reliable than matched/delayed); low on the *magnitude* without further verification. This evidence cannot say what fraction of amount_mismatch is actually misclassified — only that there is a well-reasoned, multi-signal case for suspecting it is meaningful, not negligible.

---

## 4. What This Evidence Cannot Tell Us

To be explicit about the limits of an analysis without ground truth:
- We cannot state a precise error rate for `amount_mismatch`.
- We cannot confirm whether misclassified transactions are landing as false `amount_mismatch` labels for truly `missing` transactions, truly `delayed` ones, or something else entirely — only that the mechanism (no exact-amount anchor) would plausibly cause confusion with any nearby category.
- We cannot rule out that the pattern is simply a property of this dataset and wouldn't generalize.

---

## 5. Recommended Verification Plan

Since no answer key exists in a real setting, the next step is a **manual sampling exercise**, not a further data query:

1. Draw a stratified random sample of ~50 `amount_mismatch` transactions, stratified by candidate-pool-size bucket (roughly even split of small/medium/large pools) to ensure the sample can speak to whether risk really does concentrate in crowded pools.
2. For each sampled transaction, manually trace it against the original source system of record (e.g., the bank's actual settlement file or a secondary confirmation channel), independent of this pipeline's own output.
3. Record whether the pipeline's chosen settlement match was actually correct.
4. Compute an empirical error rate with a confidence interval appropriate to the sample size, and check whether error rate correlates with candidate-pool size as hypothesized.
5. If the sample confirms meaningful misclassification, escalate as a scoped finding — with the dollar exposure this implies — rather than a vague concern.

This is the honest, real-world equivalent of what ground truth would have told us instantly, and it is the actual deliverable a data analyst produces when no such shortcut exists.

---

## 6. Interim Business Recommendation (Before Verification Completes)

Even without a confirmed error rate, the evidence above is strong enough to justify two immediate, low-cost actions:
- **Deprioritize dollar-value confidence in `amount_mismatch` totals** shown on any dashboard until verified — flag it as a lower-bound / directional figure, not a precise one.
- **Route `amount_mismatch` transactions from large candidate pools (5+) into the manual review queue at higher priority**, since this is exactly where the architectural risk concentrates, per Section 2.3.

---

## Postscript: Retrospective Validation (Only Possible in This Portfolio Context)

Because this is a synthetic dataset built specifically for this project, a true ground-truth answer key existed and was used — strictly after the fact, and strictly for validating the above methodology, never for informing it. In a real job, this step would not exist; the sampling plan in Section 5 would be the actual endpoint.

For transparency and to validate the investigative approach: when checked against ground truth, `amount_mismatch` transactions drawn from candidate pools of 5+ were found to be correct only **5.4% of the time** — a severe, real reliability problem, confirming the hypothesis in Section 3 not just directionally but in magnitude far beyond what the evidence-only analysis could claim to know. This is presented here only to demonstrate that the evidence-based methodology above pointed in the right direction using signals alone — not as a substitute for the verification plan a real analyst would still need to run.

---

## Addendum: Where These Recommendations Landed

The interim recommendations from Section 6 were carried through into the final dashboard, not left as a suggestion on paper:
- The dollar-value metric is explicitly labeled a **known lower bound** in the tile title itself, matching the "deprioritize dollar-value confidence until verified" recommendation.
- The `match_confidence` column and review-queue prioritization directly implement "route large-candidate-pool transactions to review at higher priority" — extended, in practice, across the whole pipeline rather than only `amount_mismatch`.

A related but distinct reliability question came up separately for the `matched` category specifically, whose accuracy at large candidate pools came back at a clean 100%. Since a suspiciously perfect number invites exactly the kind of scrutiny this document is about, that finding was stress-tested the same way: checked for possible leakage, generator bias, and selection effects, and confirmed to be a genuine property of the exact-amount matching mechanism rather than an artifact. That investigation is recorded in `project_log.md` under "Interviewer-Proofing the Suspiciously Clean 100% Finding."
