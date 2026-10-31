# Test Strategy (Phase 5)

Approach: execute the repository's **own dbt SQL** locally (BigQuery→DuckDB via sqlglot, `tests/harness/dbt_local.py`), feed it hand-built synthetic fixtures
(1–5 rows, hand-computed expectations) and the committed synthetic CSVs, and verify controls independently with pandas. Fidelity check: categories reproduce the committed BigQuery export exactly (CT-005).
Confirmed defects are encoded as `xfail(strict=True)` tests that name their defect ID; `pytest --runxfail` shows the real failures (evidence/runxfail_output.txt).
Legend: **A** applicable (tested) · **N/A** not implemented in repository · **B** blocked (infra) · **RC** requires business confirmation.

## A. Input and contract
| # | Scenario | Status | Notes / tests |
|---|---|---|---|
| 1,2 | Input availability/readability | A | DQ001/002 read committed CSVs |
| 3 | File naming | N/A | no naming convention in repo (fixed names in load_to_bigquery.py) |
| 4,5,6,10 | Required columns / schema / missing column | A | DQ001-002, ST001, ST007 |
| 7,8,9 | Empty / header-only / empty dataset | A | ST006 (header-only == zero rows) |
| 11 | Extra column | A | ST008 |
| 12 | Column order | N/A | staging selects by name; order irrelevant (ST008 indirectly) |
| 13 | Delimiters/encodings | B | CSV parsing happens inside BigQuery load (autodetect); not runnable offline |
| 14 | Truncated/malformed records | A (partial) | ST003/ST004 malformed values; BigQuery load-level truncation B |
| 15,16 | Duplicate/reprocessed input files | A | ST010, FI004 (duplicate ingestion); no file-level dedup exists |
| 17 | Unsupported formats | N/A | CSV only |
| 18 | Invalid source-system identifiers | A | DQ003 id format |

## B. Transaction data quality
Applicable: B1 missing ids (DQ004), B2/B3 duplicate ids (DQ003, ST009/010), B4 null amounts (ST005, DQ004), B6 negative amounts (DQ006/DQ007), B7 excessive precision (ST011, DQ005), B8/B9 numeric formats (ST003),
B12/13 timestamps (ST004, DQ009), B16 status (DQ008, RC015 – **RC**), B17 missing merchant (DQ004), B19 whitespace (RC014 descriptor exactness), B23 date range (DQ009).
**N/A** (no field exists): B5 zero-value (no rule; amounts ≥5.02), B10/11 currency, B14/15 time zone/DST (cast to UTC timestamp, no tz field – RC), B18 payment method, B20/21 unicode/leading zeros, B22 extremely large values (generator max 500; BigQuery NUMERIC range not testable locally).

## C. Normalization / transformation
Applicable: C5 decimal conversion (ST002, ST011), C6 rounding (`amount_diff_signed` round 2: CT004), C16 defaults (null propagation ST005, unmatched nulls RC012), C17 source-field preservation (ST001/CT003), C18 output schema (ST001, CT-schema via export compare), C19 null propagation (ST005, RC012), C20 unexpected schema (ST007/008).
Merchant normalization = descriptor→merchant crosswalk (edit distance + manual override): RC014, DQ011-013.
**N/A**: currency/status/payment-method mapping, fee/tax/gross-to-net, refund/reversal/chargeback/sign normalization (not implemented; negative settlements are silently dropped → PAYREC-002).

## D. Matching (modes that exist: merchant + amount tolerance + 15-day window, single-stage, gateway-driven)
Applicable: D1-3 composite exact (RC001, RC009), D4 window (RC004), D5 tolerance (RC002/003), D7 one-to-one (RC016 **fails → PAYREC-001**), D10 partial = amount_mismatch (RC005, RQ005), D11 multiple candidates (RC009, RC013), D12 priority/ranking (RC009, RC009b), D13 ambiguous (RC011), D14/15 reuse & duplicate-match prevention (RC016, RG001/002), D16 missing internal txn (RC019 **PAYREC-003**), D17 missing external txn (RC012), D19 amount mismatch (RC005), D20 date mismatch (RC004/RC006), D22 late arriving = delayed (RC006), D26 reprocessed (FI004), D29 cross-day (RC006 calendar-day logic).
**N/A**: D6 fee-adjusted, D8 one-to-many, D9 many-to-one, D18 currency mismatch, D21 reference mismatch (no reference field), D23-25 pending/failed/cancelled (status ignored – RC015 characterization), D27 split, D28 combined settlement, D30 cross-month (no month logic; window arithmetic covered by RC004).

## E. Lifecycle — **N/A** entirely (no authorization/capture/refund/reversal/chargeback/fee/settlement-adjustment logic). E15 late settlement is the `delayed` class (RC006). E16 repeated events: duplicates (RC010).

## F. Monetary controls
Applicable: F1/F2 counts (CT001), F3-F6 category counts (CT002, CT005), F7 gross amount (CT003), F9 unmatched gross (CT008), F20 residual (RG001: excess $54,698.65 – **PAYREC-001**), equation source = matched + unmatched uses the repo's classification, plus double-counting (CT-RG001/002).
**N/A**: F10-14 fee/tax/refund/chargeback/net, F15 per-currency, F16 per-batch, F17 per-merchant totals (no such outputs), F18 per-settlement-date, F19 debit/credit.

## G. Output and audit
Applicable: G1 outputs exist (CT001, CT006), G2-5 schema/count (CT005/006), G6 status populated (CT-generic not_null/accepted_values), G7 reason populated (RQ008), G12 duplicate output (CT-generic unique), G13 ordering (RQ007 ordering inside queue), G14 summary vs detail (no summary exists), G17 sources unchanged (CT016, DQ015).
**Gap/N/A**: G8 rule id, G9 lineage, G10 run id, G11 processing timestamp, G15 audit log – **not produced by the pipeline** (reported as a gap, not a test failure; no requirement exists). G16 re-run does not corrupt prior output: dbt tables are rebuilt; export scripts overwrite CSVs (B – needs BigQuery).

## H. Failure/recovery/idempotency
Applicable: H1 missing input (FI002), H3 malformed (ST003/4), H4 invalid config (N/A – no config), H9/10 repeated/duplicate ingestion (FI001, FI004), H13 rollback (N/A), H17 exit codes (dbt behaviour; **B**).
**B/N/A**: H5-H8, H11-H12, H14-H16 (no services, writers, checkpoints in the repo; export/load scripts need BigQuery).

## I. Security/privacy
Applicable: I1/2 secrets in source (SEC001, SEC004 → PAYREC-005), I5/6/7 card/bank/PII (DQ010, SEC005), I8-9 temp/output permissions (SEC007), I10 secret files in git (SEC002/003), I11 sensitive values in reports (report scan in final verification). I3/I4 logs/traces: N/A (no logging).

## J. Regression & performance
J1 each defect has a regression test (RG*, RC016/17/19/20, SEC*); J2 deterministic output for fixed input: FI001 (unambiguous data passes) and RG003b (**fails for ties**, PAYREC-004); J5 repeat execution FI001.
J6-8 performance: no requirement or baseline exists → duration is recorded in the execution report, not graded.

## Assumptions needing business confirmation (all tests that depend on them are labelled)
A1 settlement should satisfy ≤1 transaction (evidence-backed by RG001, still needs owner confirmation) · A2 negative settlements are invalid (the repo's own dbt rule says so) · A3 non-completed statuses are reconcilable (RC015 is characterization only) ·
A4 1-cent tolerance intended (RC005) · A5 tie-break should be deterministic (RC017) · A6 bank-side orphans should be reported (RC019) · A7 amount_mismatch should take precedence over delayed (RC007 characterization).
