# Payment Reconciliation Pipeline
### Matching gateway transactions to bank settlements without a shared ID, then finding out how much you can actually trust the result

---

## The number that started the real work

A first-pass version of this pipeline reported **$21,612** in unreconciled dollar exposure across 25,000 transactions: a clean, reassuring 0.34% of volume.

Independent verification found the true figure was **$267,169**, a **12x understatement** that was hidden entirely inside a category the pipeline was confidently labeling as something else.

That gap, and the process of finding it, is the actual subject of this project.

---

## TL;DR

- **Problem:** simulate the core reconciliation task every payments company faces, matching gateway transaction records to bank settlement records that share no common ID, and build a system that tells the business what's actually at risk, not just what looks clean.
- **Approach:** dbt + BigQuery pipeline; merchant identity resolved via reverse-engineered fuzzy matching (not a lookup table); transactions matched on merchant, amount tolerance, and settlement window; every classification backed by a confidence signal, not just a label.
- **Key finding:** the pipeline's own accuracy number was misleading in two different, dangerous ways. First it hid a 0% detection rate on the costliest failure mode behind a 95%+ headline accuracy, then it understated true dollar exposure 12x once that was fixed. Both were caught by refusing to trust the aggregate number and testing it directly.
- **Stack:** Python (synthetic data generation), dbt Core, Google BigQuery, Tableau Public.
- **Result:** a working, tested pipeline (14 passing dbt tests), a prioritized review queue ranked by real dollar risk, an interactive dashboard, and a companion methodology writeup on how this would be investigated in a real job, where no ground truth exists to check against.

---

## 1. The Business Problem

Every time a customer pays, two independent systems create a record of it: the payment gateway logs "we charged this customer $X," and the bank logs "we actually settled $Y, on this date." These records are created by different systems, at different times, and, critically, do not share a common identifier.

The business question this needs to answer, every day, at scale: **is the money we think we're owed actually the money we're getting, and if not, where exactly is the gap, and how much does it matter?**

Left unanswered, this creates three concrete failure modes: revenue quietly leaking through unpaid transactions nobody notices, fraud or processing errors going undetected because nothing flags them, and a review team drowning in noise because nothing tells them where to look first. A human checking this by spreadsheet works at fifty transactions a day. It falls apart completely at real volume.

---

## 2. Dataset & Scope

The dataset is synthetic, 25,000 gateway transactions across 85 merchants, matched against roughly 24,750 bank settlement records, generated specifically to reproduce the actual structural difficulty of this problem rather than a simplified version of it. Two design choices made that difficulty real rather than cosmetic:

- **No shared transaction ID.** Settlements carry only a bank statement descriptor (e.g. `TST*WILSON BAXT SYD`), mangled the way real processor statements are: truncated, prefixed, sometimes carrying a store code, with no reference back to the original transaction.
- **A known, injected ground truth**, used only for after-the-fact validation of the matching logic and never fed into it. This distinction matters: it let the accuracy of every technique below be measured precisely, but the actual investigative process (described in Section 5) was deliberately also carried out the way it would have to happen with no answer key at all, since that's the reality of the job.

---

## 3. Architecture

Raw data lands in BigQuery, then flows through a standard dbt layering pattern: staging (clean and cast) feeds intermediate models (merchant resolution, candidate matching) which feed the final marts (classification, review queue).

**Merchant identity was the first hard problem.** Since settlements carry no transaction ID, matching depends entirely on first knowing which merchant a settlement belongs to, and that had to be built, not assumed. Each of the 258 distinct bank descriptors in the dataset was classified against the known merchant list using length-normalized edit distance:

```sql
edit_distance(
    upper(regexp_replace(merchant, r'[^a-zA-Z0-9]', '')),
    upper(regexp_replace(bank_descriptor, r'[^a-zA-Z0-9]', ''))
) / greatest(length(merchant_clean), length(descriptor_clean), 1) as normalized_distance
```

Low-confidence classifications (45 of 258) were flagged and manually reviewed by hand against the real merchant list, not auto-accepted. One (`TST*SMI`) was deliberately left unresolved due to genuine ambiguity between two similarly-named merchants, and was later resolved through amount and date cross-referencing rather than guessed (Section 4.4).

**Matching itself** joins on resolved merchant, an amount tolerance (`greatest($5, 5% of amount)`), and a 15-day settlement window, then ranks candidates by amount closeness first, with merchant similarity as a tiebreaker:

```sql
row_number() over (
    partition by txn_id
    order by amount_diff asc, merchant_distance asc, days_to_settle asc
) as match_rank
```

**Classification** doesn't just label matched versus unmatched. Every transaction gets a `match_confidence` tier (`unique`, `medium`, or `low`) based on how many plausible candidates existed, so downstream consumers know not just what was decided but how contested the decision was:

```sql
case
    when num_candidates = 1 then 'unique'
    when num_candidates between 2 and 4 then 'medium'
    else 'low'
end as match_confidence
```

14 dbt tests cover uniqueness, referential integrity between marts and staging, accepted-value ranges on every categorical output, and business-rule sanity checks (no negative settlements, settlement timing within a plausible window).

---

## 4. Key Findings

This is the part of the project that mattered most, and it's presented in the order the findings actually happened, because the sequence itself is the point: each one only surfaced by refusing to accept the previous number at face value.

### 4.1: A 95%+ accurate pipeline can still be dangerously wrong

An early version of the matching logic reached 95.41% overall accuracy. On inspection, it was catching **0 of 320** true missing-settlement cases, the single costliest failure category, since it represents money that may never have arrived at all. A worse-looking 69.56%-accuracy version had actually caught more of them.

This is a textbook consequence of class imbalance: 85% of the dataset is naturally clean, so a metric that mostly reflects the easy majority can look excellent while completely failing on the 4% that matters most. The fix wasn't a better algorithm. It was changing what got optimized for: recall on the costly category, not aggregate accuracy.

### 4.2: The headline dollar number understated real exposure by 12x

Once missing-settlement detection improved, a dollar-based health metric was built: `gateway_amount minus settled_amount`, summed across all transactions. It reported **$21,612** in exposure.

Testing this against ground truth (used strictly for grading, not for building the metric) found the true gap was **$267,169**. The mechanism: any dollar formula can only be as accurate as the classification feeding it, and a large share of transactions labeled `amount_mismatch` were actually mislabeled `missing` cases carrying a small, misleading dollar difference instead of their true, much larger, exposure. Three formula variants were tested: a naive net gap, a gross non-matched total, and a category-aware hybrid. None came within an order of magnitude of the truth. The dashboard now reports the most defensible of the three, explicitly labeled as a known lower bound, not a precise figure.

### 4.3: "Matched" was hiding real uncertainty behind a flat number

A confidence-tier breakdown of the matched category (11.44% unique, 47.74% medium, 40.83% low) showed that only 11.44% of transactions labeled clean were an unambiguous pick; the rest came from a pool of two or more look-alike candidates. A single flat reconciliation-rate percentage was quietly averaging over that spread, presenting uniform confidence where none existed.

### 4.4: Tracing one merchant's inflated risk to a single root cause

A routine group-by found one merchant, Smith-Mcguire, sitting at a 35.2% anomaly rate against a roughly 15% dataset baseline. The cause traced back to a single deliberately unresolved bank descriptor (`TST*SMI`): settlements carrying it were structurally invisible to the matching join, so real Smith-Mcguire transactions were being forced onto worse alternative matches. It was resolved by cross-referencing amount and date evidence between the two candidate merchants (no ground truth used), and the fix was verified numerically: the rate normalized to **12.2%**, back in line with baseline.

### 4.5: Match reliability is entirely explained by one mechanism, not luck

Spot-checking transactions drawn from crowded candidate pools (5+ plausible matches) against ground truth produced a stark split:

| Category | Accuracy at 5+ candidates |
|---|---|
| `matched` | 100% (8,668 / 8,668) |
| `delayed` | 99.5% (406 / 408) |
| `duplicate` | 92.0% |
| `amount_mismatch` | **5.4%** (36 / 667) |

The mechanism: `matched` and `delayed` both require an exact-to-the-cent amount match, which, combined with an exact merchant match, is specific enough to uniquely identify the true transaction regardless of how many other candidates are nearby. `amount_mismatch`, by definition, has no such anchor, so once inside a crowded pool it degrades to close to a coin flip. This single mechanism, once identified, explained every reliability number found throughout the project. It didn't just describe the symptom, it explained the cause.

### 4.6: A wrong hypothesis, corrected in the open

Initial reasoning predicted low-value transactions would have larger candidate pools, since the $5 tolerance floor is relatively larger for small amounts. Tested directly, the data showed the opposite: candidate pool size increases with transaction amount (2.2 average candidates at $5 to $25, rising to 5.7 at $250 to $500), because the tolerance is a percentage of amount, so the absolute dollar window widens for larger transactions, giving them more room to coincidentally overlap with unrelated settlements. The takeaway matters operationally: the highest-value transactions are structurally the least reliably matched, the opposite of what you'd want.

---

## 5. Methodology: Investigating Without Ground Truth

Every finding above was validated against a private answer key, which is legitimate for this project since it was built specifically to test the approach and was never used to inform the matching logic itself. But a real analyst never gets that answer key.

A full parallel investigation was carried out treating `amount_mismatch` reliability as an open question with no ground truth available at all, using only signals a working analyst actually has: rate concentration by merchant, the matching logic's own design, candidate-pool scaling, and distribution shape (the mismatch histogram's sharp cutoff exactly matches the pipeline's own tolerance parameter, a strong sign the shape reflects the filter, not reality).

That investigation built a hedged, evidence-based hypothesis, explicitly stated what couldn't be known without further work, and proposed a manual sampling and verification plan: the real deliverable a data analyst produces when no shortcut exists.

The full writeup, including where the evidence-only hypothesis was later checked against ground truth and found directionally and substantively correct, is in [`no_ground_truth_analysis.md`](./no_ground_truth_analysis.md).

---

## 6. The Review Queue

A dashboard that shows problems isn't the same as a tool someone uses. `mart_review_queue` translates every finding above into a ranked, actionable list, highest real-world risk first, not highest row count:

1. **Missing settlements**: full transaction amount unaccounted for
2. **Duplicate payouts**: possible double payment
3. **Ambiguous ties**: two equally plausible settlements, no confident pick
4. **Low-confidence matches** (5+ candidates): spot-check the pick
5. **Material amount mismatches** ($5+ difference)

Each row carries a human-readable reason and a category-aware dollar exposure estimate, capped to the top 30 per tier by dollar value so the highest-stakes items surface first.

---

## 7. Dashboard

Built in Tableau Public, connected to a flat export (Tableau Public doesn't support a live BigQuery connection; a standard, legitimate limitation, not a workaround). Five tiles, each one a direct response to a finding above rather than a generic chart:

- **Dollar Health Summary**: exposure figures explicitly labeled as a validated lower bound
- **Match Confidence Breakdown**: replaces the flat reconciliation rate with the real unique/medium/low split
- **Amount Mismatch Distribution**: captioned with the tolerance-boundary caveat from Finding 4.2
- **Trend over Time**: captioned to explain the late-range spike as a synthetic-data boundary artifact, not a real trend
- **Top Merchants by Dollar Exposure**: dollar-weighted, not count-weighted, so the ranking reflects real risk

A companion notes panel on the dashboard itself states the four caveats above in plain language, so the honest picture travels with the visual, not just in a README someone might not read.

---

## 8. Known Limitations

Stated directly, not buried:

- **Missing-settlement recall remains around 11%.** This is a structural limit of matching without a shared ID, not a bug; same-merchant, similar-amount, nearby-date collisions are genuinely indistinguishable without more signal than this dataset provides.
- **Reported dollar exposure is a lower bound**, not a precise figure, for the reasons in Finding 4.2.
- **The merchant crosswalk assumes a knowable, bounded set of merchants** (85, with a small fixed set of descriptor variants each): a simplification that made reverse-engineering tractable within scope, but a real production system would need an ongoing, maintained merchant directory process.
- **No orchestration.** The pipeline runs on manual `dbt run` invocations; a production version would run on a schedule with monitoring and alerting.

---

## 9. What I'd Do Next

- Extend the confidence-tier logic specifically to `amount_mismatch`, where it's needed most and currently absent
- Run the manual sampling and verification plan proposed in Section 5 for real, rather than substituting ground truth
- Add a `needs_review` reason breakdown to the merchant chart; several merchants show a concentration of ambiguous ties worth checking isn't itself a pattern
- Move from manual re-runs to a scheduled orchestration layer

---

## Tech Stack

Python (Faker, pandas), dbt Core, Google BigQuery, Tableau Public, Git

## Repo Structure

```
models/
  staging/       # cleaned source tables
  intermediate/  # merchant crosswalk, candidate matching, match selection
  marts/         # mart_reconciliation, mart_review_queue
seeds/           # manual merchant corrections, QA'd, no ground truth
tests/           # singular dbt tests (business-rule checks)
data/            # generator scripts, exports (private ground-truth files excluded from git)
no_ground_truth_analysis.md   # standalone methodology writeup
project_log.md                # full chronological build log
```
