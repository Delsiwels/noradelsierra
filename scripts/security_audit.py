#!/usr/bin/env python3
"""
Run comprehensive security audit on the codebase.
Usage: python scripts/security_audit.py
"""

import subprocess
import sys


def run_command(name, cmd):
    print(f"\n{'='*60}")
    print(f"Running: {name}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, shell=True, capture_output=False)
    return result.returncode == 0


def main():
    checks = [
        ("Ruff Lint", "ruff check webapp/"),
        ("Bandit Security", "bandit -r webapp/ -ll"),
        ("MyPy Types", "mypy webapp/ --ignore-missing-imports"),
        ("Pytest", "pytest tests/ -v"),
        ("Gitleaks Secrets", "gitleaks detect --source webapp/ --source tests/ --source scripts/ --no-git"),
    ]

    failed = []
    for name, cmd in checks:
        if not run_command(name, cmd):
            failed.append(name)

    print(f"\n{'='*60}")
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
