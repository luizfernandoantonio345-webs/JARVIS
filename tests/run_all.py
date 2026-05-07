"""
RUNNER GERAL — Executa todos os 5 testes em sequência e gera relatório JSON.

Uso:
    python tests/run_all.py
    python tests/run_all.py --url http://localhost:8000

Saída:
    tests/results/report_{timestamp}.json
    Resumo no terminal: X/5 testes passaram
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TESTS_DIR   = Path(__file__).parent
RESULTS_DIR = TESTS_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

TEST_FILES = [
    "test_autodev_smoke.py",
    "test_autodev_fixer.py",
    "test_autodev_ws.py",
    "test_agents_e2e.py",
    "test_autodev_resume.py",
]

TEST_LABELS = [
    "AutoDev Smoke Test",
    "AutoDev Fixer (intelligent retry)",
    "WebSocket Stream Events",
    "Multi-Agent E2E (endpoint analysis)",
    "Job Resume / Continuidade",
]


def run_test(test_file: str, base_url: str) -> dict:
    """Run a single pytest file and return a result dict."""
    cmd = [
        sys.executable, "-m", "pytest",
        str(TESTS_DIR / test_file),
        "-v",
        "--tb=short",
        "--no-header",
    ]
    env = os.environ.copy()
    env["JARVIS_TEST_URL"] = base_url

    t0 = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(TESTS_DIR))
    duration = round(time.monotonic() - t0, 2)

    passed = result.returncode == 0
    # Parse pytest output for individual test counts
    lines = result.stdout.splitlines()
    summary_line = next((l for l in reversed(lines) if "passed" in l or "failed" in l), "")

    return {
        "file": test_file,
        "passed": passed,
        "returncode": result.returncode,
        "duration_s": duration,
        "summary": summary_line.strip(),
        "stdout_tail": "\n".join(lines[-30:]),
        "stderr_tail": result.stderr[-2000:] if result.stderr else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run JARVIS integration tests")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend URL")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  JARVIS Integration Test Suite")
    print(f"  Backend: {args.url}")
    print(f"  Time:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    results = []
    passed_count = 0

    for i, (test_file, label) in enumerate(zip(TEST_FILES, TEST_LABELS), 1):
        print(f"[{i}/{len(TEST_FILES)}] {label}")
        print(f"  Running: {test_file} ... ", end="", flush=True)

        result = run_test(test_file, args.url)
        results.append({"label": label, **result})

        status = "PASS ✓" if result["passed"] else "FAIL ✗"
        print(f"{status}  ({result['duration_s']}s)")

        if not result["passed"]:
            # Show failing lines
            for line in result["stdout_tail"].splitlines():
                if "FAILED" in line or "ERROR" in line or "AssertionError" in line:
                    print(f"    {line.strip()}")

        if result["passed"]:
            passed_count += 1

    # ── Write report ───────────────────────────────────────────────────────────
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = RESULTS_DIR / f"report_{ts}.json"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backend_url": args.url,
        "summary": {
            "total": len(TEST_FILES),
            "passed": passed_count,
            "failed": len(TEST_FILES) - passed_count,
        },
        "tests": results,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # ── Final summary ──────────────────────────────────────────────────────────
    bar = "=" * 60
    print(f"\n{bar}")
    print(f"  RESULT: {passed_count}/{len(TEST_FILES)} tests passed")
    print(f"  Report: {report_path}")
    print(f"{bar}\n")

    sys.exit(0 if passed_count == len(TEST_FILES) else 1)


if __name__ == "__main__":
    main()
