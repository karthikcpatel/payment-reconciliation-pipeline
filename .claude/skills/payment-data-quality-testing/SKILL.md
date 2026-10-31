---
name: payment-data-quality-testing
description: Test payment source data and staging outputs for required fields, nulls, duplicates, types, amount precision, dates, statuses, sign conventions, orphans, control totals and source immutability. Uses synthetic data only.
allowed-tools: Read, Grep, Glob, Write, Edit, Bash(python -m pytest:*), Bash(.venv/bin/python:*)
---
# Payment data-quality testing

## Inputs
Committed CSVs in `data/` (read-only) and synthetic frames built in tests. Harness: `tests/harness/dbt_local.py`.

## Checks
Required columns/schema; null and empty values; duplicate txn_id/settlement_id; amount numeric format and <=2 decimals; positive/negative sign rules; allowed status values; timestamp parseability and range; orphan settlements/transactions; row counts; SHA-256 of source files before/after to prove they are unmodified.
Currency, fee, tax and refund checks apply only if those columns exist - currently they do not (document as not applicable).

## Boundaries
Never write to `data/` or `seeds/`. Use `tmp_path` for generated files. No real card, bank, or customer data - use ids like `TXN_T001`.
Known defects are encoded as `xfail(strict=True, reason="PAYREC-nnn")`, never as weakened assertions.

## Output
Tests under `tests/data_quality/`; findings with counts and example ids.

## Verification
Run `.venv/bin/python -m pytest tests/data_quality -q`; confirm each negative fixture fails the check it targets.
