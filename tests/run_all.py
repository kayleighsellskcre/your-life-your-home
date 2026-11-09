"""Run every check in this folder, each against its own temporary database (your real data is never touched).

    python tests/run_all.py

Prints one line per check; any FAIL or crash is listed at the end and the exit code is 1.
"""
import pathlib
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parent.parent
bad = []
total = 0
for f in sorted(pathlib.Path(__file__).parent.glob("*_test.py")):
    r = subprocess.run([sys.executable, str(f)], cwd=root, capture_output=True, text=True, timeout=600)
    lines = [l for l in r.stdout.splitlines() if l.startswith(("PASS", "FAIL"))]
    total += len(lines)
    fails = [l for l in lines if l.startswith("FAIL")]
    crashed = r.returncode != 0 and "Traceback" in r.stderr
    print(f"{f.name}: {len(lines) - len(fails)}/{len(lines)} passed" + ("  CRASHED" if crashed else ""))
    bad += [f"{f.name}: {l}" for l in fails] + ([f"{f.name}: crashed"] if crashed else [])
print(f"\n{total} checks, {len(bad)} problems")
for b in bad:
    print("  " + b)
sys.exit(1 if bad else 0)
