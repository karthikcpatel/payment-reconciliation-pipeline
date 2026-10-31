---
name: pipeline-test-reporting
description: Produce auditable Markdown and self-contained HTML test reports from actual pytest output - counts, commands, exit codes, defects with severity, blocked and not-executed items.
allowed-tools: Read, Grep, Glob, Write, Edit, Bash(python -m pytest:*), Bash(.venv/bin/python:*)
---
# Pipeline test reporting

## Rules
1. Report numbers only from a command that actually ran; store its raw output under `docs/claude_testing/evidence/`.
2. Statuses: passed, failed, xfailed (confirmed defect, expected failure), blocked (needs unavailable infra), skipped (documented reason), not executed.
3. Never count blocked/not-executed as passed. Unknown values display "Not verified".
4. Distinguish code defects from environment/test defects; give severity per the project guide (Critical/High/Medium/Low) and reproduction steps.
5. HTML is one file with embedded CSS, no JS/network.

## Verification
Generate counts programmatically from the pytest junit XML or output and assert the report totals equal them (`tests` run + a final check script); grep reports for "passed" next to blocked items.
