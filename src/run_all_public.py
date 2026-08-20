#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys

STEPS = [
    "src/analysis/01_reproduce_public_core.py",
    "src/analysis/02_run_bdcc_robustness.py",
]

for script in STEPS:
    print(f"\n=== Running {script} ===", flush=True)
    subprocess.run([sys.executable, script], check=True)

print("\nPublic-data reproduction completed successfully.")
