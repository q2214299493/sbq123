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
