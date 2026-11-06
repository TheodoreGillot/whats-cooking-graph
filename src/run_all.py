"""Run the full analysis pipeline in order.

Usage: python src/run_all.py

Runs prepare -> structure -> centrality -> communities -> sensitivity.
fetch_data.py and validate_data.py are one-time setup steps (see README).
"""
import runpy
import time
from pathlib import Path

HERE = Path(__file__).parent

STEPS = [
    "prepare_data.py",
    "structure.py",
    "centrality.py",
    "communities.py",
    "sensitivity.py",
]


def main() -> None:
    for step in STEPS:
        print(f"\n===== {step} =====")
        started = time.time()
        runpy.run_path(str(HERE / step), run_name="__main__")
        print(f"({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
