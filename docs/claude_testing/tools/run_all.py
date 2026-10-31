"""Runs every documented command, recording command, cwd, start/end, exit code and counts (from junit XML) into evidence/commands.json."""
import datetime as dt, json, pathlib, subprocess, sys, xml.etree.ElementTree as ET
REPO = pathlib.Path(__file__).resolve().parents[3]
EV = REPO / "docs/claude_testing/evidence"; EV.mkdir(exist_ok=True)
PY = str(REPO / ".venv/bin/python")

def counts(xml):
    p = EV / xml
    root = ET.parse(p).getroot()
    c = dict(passed=0, failed=0, xfailed=0, skipped=0, error=0)
    for tc in root.iter("testcase"):
        kids = {k.tag: k for k in tc}
        if "failure" in kids: c["failed"] += 1
        elif "error" in kids: c["error"] += 1
        elif "skipped" in kids:
            c["xfailed" if kids["skipped"].get("type") == "pytest.xfail" else "skipped"] += 1
        else: c["passed"] += 1
    c["total"] = sum(c.values()); return c

CMDS = [
 ("G0 baseline: pre-existing dbt tests (dbt CLI)", ["dbt", "--version"], None, "BLOCKED: dbt/BigQuery not available"),
 ("G0 baseline: bare pytest collection of root script", [PY, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "test_composite_score.py"], None, "pre-existing test file; needs BigQuery (PAYREC-006)"),
 ("G1 unit (staging)", [PY, "-m", "pytest", "tests/unit", "-q", "-p", "no:warnings", "-p", "no:cacheprovider"], "g1_unit.xml", ""),
 ("G2 data_quality", [PY, "-m", "pytest", "tests/data_quality", "-q", "-p", "no:warnings", "-p", "no:cacheprovider"], "g2_dq.xml", ""),
 ("G3 reconciliation", [PY, "-m", "pytest", "tests/reconciliation", "-q", "-p", "no:warnings", "-p", "no:cacheprovider"], "g3_rec.xml", ""),
 ("G4 controls", [PY, "-m", "pytest", "tests/controls", "-q", "-p", "no:warnings", "-p", "no:cacheprovider", "-s"], "g4_ctl.xml", ""),
 ("G5 regression", [PY, "-m", "pytest", "tests/regression", "-q", "-p", "no:warnings", "-p", "no:cacheprovider"], "g5_reg.xml", ""),
 ("G6 security", [PY, "-m", "pytest", "tests/security", "-q", "-p", "no:warnings", "-p", "no:cacheprovider"], "g6_sec.xml", ""),
 ("FULL suite (authoritative)", [PY, "-m", "pytest", "tests", "-q", "-p", "no:warnings", "-p", "no:cacheprovider", "-s"], "full.xml", ""),
 ("FULL suite repeat (repeatability)", [PY, "-m", "pytest", "tests", "-q", "-p", "no:warnings", "-p", "no:cacheprovider"], "full_repeat.xml", ""),
 ("FULL suite --runxfail (defect evidence)", [PY, "-m", "pytest", "tests", "-q", "-p", "no:warnings", "-p", "no:cacheprovider", "--runxfail"], "full_runxfail.xml", "failures here are the confirmed defects"),
]
out = []
for name, cmd, xml, note in CMDS:
    full = cmd + ([f"--junitxml={EV/xml}"] if xml else [])
    t0 = dt.datetime.now()
    try:
        r = subprocess.run(full, cwd=REPO, capture_output=True, text=True); code, so = r.returncode, r.stdout + r.stderr
    except FileNotFoundError as e:
        code, so = 127, str(e)
    t1 = dt.datetime.now()
    rec = dict(name=name, command=" ".join(c.replace(str(REPO) + "/", "") for c in cmd), cwd=str(REPO), start=t0.isoformat(timespec="seconds"),
               end=t1.isoformat(timespec="seconds"), seconds=round((t1 - t0).total_seconds(), 1), exit_code=code, note=note)
    if xml and (EV / xml).exists(): rec["counts"] = counts(xml)
    else: rec["counts"] = None; rec["output_tail"] = so.strip().splitlines()[-3:]
    if xml: (EV / xml.replace(".xml", ".txt")).write_text(so)
    out.append(rec); print(name, code, rec["counts"])
(EV / "commands.json").write_text(json.dumps(out, indent=1))
