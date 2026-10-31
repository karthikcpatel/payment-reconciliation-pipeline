---
name: reconciliation-control-validation
description: Validate reconciliation control totals - counts and amounts source vs target, category conservation, settlement double counting, exposure totals, review-queue coverage - and quantify unexplained differences.
allowed-tools: Read, Grep, Glob, Write, Edit, Bash(python -m pytest:*), Bash(.venv/bin/python:*)
---
# Reconciliation control validation

## Controls that apply (this pipeline)
- count(mart_reconciliation) == count(gateway) and txn_id unique.
- sum of category counts == total; sum(gateway_amount) preserved across the mart.
- matched settlement dollars (distinct settlement_id) <= total bank settlement dollars; sum over mart rows == sum over distinct settlements (double-counting check).
- every settlement selected by at most one transaction.
- review queue: per-tier cap, exposure == rule-derived value, coverage vs full population.
- Compare local run to committed export `data/mart_reconciliation_export.csv` (categories exact).
Controls NOT applicable (no such fields): per-currency, fee/tax/net, debit/credit balance, per-batch.

## Procedure
Compute expected totals independently with pandas from the raw CSVs, compare with SQL output, report the **unexplained difference** in dollars and rows.

## Verification
Record the formula, both sides of each equation, and the residual; a nonzero residual is reported, never rounded away.
