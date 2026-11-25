from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (
    ROOT / "scripts" / "neb_agent",
    ROOT / "scripts" / "convergence",
    ROOT / "scripts" / "adsorption",
    ROOT / "scripts" / "adsmind_lite",
    ROOT / "skills" / "catalysis-data-retrieval" / "scripts",
):
    sys.path.insert(0, str(path))


def pytest_addoption(parser):
    parser.addoption(
        "--catkinas-reviewed-run", nargs=2, metavar=("RUN", "DECISION"),
        help="Run the native closed-cycle test on this prepared RUN using its external reviewed DECISION.",
    )
