---
name: payment-pipeline-analysis
description: Analyze the payment reconciliation pipeline architecture from repository evidence - sources, transformations, matching rules, monetary handling, entry points, risks. Read-only; use before designing tests.
allowed-tools: Read, Grep, Glob, Bash(git status:*), Bash(git log:*), Bash(ls:*)
---
# Payment pipeline analysis

## Inputs
Repository root. Start from `dbt_project.yml`, `models/**`, `seeds/`, `tests/*.sql`, `README.md`, `generate_data.py`, `data/*.csv` headers.

## Procedure
1. List files; read every model and test in full. Never assume a processor, bank, DB or format - cite file:line for each claim.
2. Build the source-to-target map (raw -> staging -> intermediate -> marts -> exports).
3. Inventory: matching keys and their priority, tolerance/window constants, rank order, classification precedence, status values, monetary casts/rounding, sign handling.
4. Check for lifecycle handling (fees, tax, refunds, reversals, chargebacks, currency). If absent say "not implemented" - do not invent.
5. Compare README claims to SQL; record drift.
6. Separate **Confirmed** (code evidence) from **Assumption** (needs confirmation).

## Boundaries
Do not modify application source (models/, seeds/, *.py at root). Do not print secrets; report file + risk category only. May write only under `docs/claude_testing/`.

## Output
Architecture summary, source-to-target map, matching-rule inventory, transformation inventory, risk/ambiguity list (see `docs/claude_testing/initial_assessment.md` for the reference format).

## Verification
Every rule listed has a file reference; every "not implemented" claim was backed by a search (`grep -ri refund models/`).
