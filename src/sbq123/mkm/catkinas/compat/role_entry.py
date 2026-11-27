"""Run the verified MKM point reader with an isolated import root."""
from pathlib import Path
import runpy
import sys

if __name__ == "__main__":
    if not sys.flags.isolated:
        raise ValueError("MKM replay requires an isolated interpreter")
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    sys.argv = ["scripts.kinetic_data.comparison_point", sys.argv[1]]
    runpy.run_module("scripts.kinetic_data.comparison_point", run_name="__main__")
