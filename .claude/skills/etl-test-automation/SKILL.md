---
name: etl-test-automation
description: Build repeatable pytest automation for the payment pipeline - positive, negative, boundary and regression tests using temp dirs and synthetic data, no external systems.
allowed-tools: Read, Grep, Glob, Write, Edit, Bash(python -m pytest:*), Bash(.venv/bin/python:*), Bash(.venv/bin/pip list:*)
---
# ETL test automation

## Conventions
- pytest, configured by root `pytest.ini` (`testpaths = tests`) so root-level scripts such as `test_composite_score.py` (needs BigQuery) are not collected.
- `tests/harness/dbt_local.py` renders repo model SQL and transpiles BigQuery->DuckDB (sqlglot). `tests/conftest.py` holds fixtures.
- Layout: `data_quality/`, `reconciliation/`, `controls/`, `regression/`, `security/`, `harness/`.
- Fixtures: minimal, deterministic, synthetic; generated files only in `tmp_path`.
- Every assertion has a failure message with the offending ids/values.
- `xfail(strict=True, reason="PAYREC-nnn")` only for confirmed defects; `skip` only with a documented blocker.

## Boundaries
Never alter `data/`, `seeds/`, production configs. Do not install packages globally. Do not weaken an assertion to get green.

## Verification
`.venv/bin/python -m pytest -q` twice gives identical counts (repeatability); `--runxfail` shows the defect failures.
