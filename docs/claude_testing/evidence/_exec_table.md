| Group / command | Exit | Passed | Failed | XFail (confirmed defects) | Skipped | Error | Total | Seconds |
|---|---|---|---|---|---|---|---|---|
| G0 baseline: pre-existing dbt tests (dbt CLI)<br><code>dbt --version</code> | 127 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0 |
| G0 baseline: bare pytest collection of root script<br><code>.venv/bin/python -m pytest --collect-only -q -p no:cacheprovider test_composite_score.py</code> | 2 | n/a | n/a | n/a | n/a | n/a | n/a | 1.0 |
| G1 unit (staging)<br><code>.venv/bin/python -m pytest tests/unit -q -p no:warnings -p no:cacheprovider</code> | 0 | 16 | 0 | 0 | 0 | 0 | 16 | 2.4 |
| G2 data_quality<br><code>.venv/bin/python -m pytest tests/data_quality -q -p no:warnings -p no:cacheprovider</code> | 0 | 14 | 0 | 1 | 0 | 0 | 15 | 3.7 |
| G3 reconciliation<br><code>.venv/bin/python -m pytest tests/reconciliation -q -p no:warnings -p no:cacheprovider</code> | 0 | 51 | 0 | 5 | 0 | 0 | 56 | 7.3 |
| G4 controls<br><code>.venv/bin/python -m pytest tests/controls -q -p no:warnings -p no:cacheprovider -s</code> | 0 | 28 | 0 | 0 | 0 | 0 | 28 | 2.8 |
| G5 regression<br><code>.venv/bin/python -m pytest tests/regression -q -p no:warnings -p no:cacheprovider</code> | 0 | 5 | 0 | 6 | 0 | 0 | 11 | 5.1 |
| G6 security<br><code>.venv/bin/python -m pytest tests/security -q -p no:warnings -p no:cacheprovider</code> | 0 | 5 | 0 | 4 | 0 | 0 | 9 | 3.5 |
| FULL suite (authoritative)<br><code>.venv/bin/python -m pytest tests -q -p no:warnings -p no:cacheprovider -s</code> | 0 | 119 | 0 | 16 | 0 | 0 | 135 | 15.7 |
| FULL suite repeat (repeatability)<br><code>.venv/bin/python -m pytest tests -q -p no:warnings -p no:cacheprovider</code> | 0 | 119 | 0 | 16 | 0 | 0 | 135 | 16.0 |
| FULL suite --runxfail (defect evidence)<br><code>.venv/bin/python -m pytest tests -q -p no:warnings -p no:cacheprovider --runxfail</code> | 1 | 119 | 16 | 0 | 0 | 0 | 135 | 15.6 |
