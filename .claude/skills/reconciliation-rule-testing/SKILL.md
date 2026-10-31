---
name: reconciliation-rule-testing
description: Test reconciliation matching rules by running the repository's real SQL on tiny synthetic fixtures - exact/tolerance/window boundaries, ranking, ties, classification precedence, unmatched handling, and one-settlement-one-transaction protection.
allowed-tools: Read, Grep, Glob, Write, Edit, Bash(python -m pytest:*), Bash(.venv/bin/python:*)
---
# Reconciliation rule testing

## Inputs
`models/intermediate/int_candidate_matches.sql`, `int_match_selection.sql`, `models/marts/mart_reconciliation.sql`, `mart_review_queue.sql`.

## Procedure
1. Only test modes that exist: merchant+amount-tolerance+time-window, waterfall-free single stage, gateway-driven. One-to-many, many-to-one, fee/refund/chargeback are NOT implemented - mark not applicable.
2. Build minimal fixtures (1-4 rows) with hand-computed expected `discrepancy_type`, `settlement_id`, `num_candidates`, `tie_type`.
3. Boundary pairs: exactly at / just beyond tolerance ($5 floor, 5%), window start/end (15 days), mismatch threshold 0.01, delayed threshold 3 days.
4. Reuse check: assert no `settlement_id` is selected by two transactions.
5. Expected values are written by hand in the test, never computed by the SQL under test.

## Boundaries
Do not edit models to make a test pass. A failing test that exposes a business-rule gap is recorded as a defect candidate and proposed to the user.

## Output
`tests/reconciliation/`, defect candidates with reproduction fixture.

## Verification
Mutate a fixture (shift date beyond window, add second candidate) and confirm the targeted test fails; restore.
