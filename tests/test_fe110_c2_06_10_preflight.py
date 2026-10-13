"""Exact additional compositions of the reviewed C2 06--10 batch."""
import json

import pytest

from scripts.adsorption.preflight_fe110_adsorption import preflight
from scripts.vasp_inputs import build_fe110_adsorption_relaxation


@pytest.mark.parametrize("symbols,counts,passed", [
    ("Fe O C H", "45 1 2 2", True),
    ("Fe C H", "45 2 3", True),
    ("Fe O C H", "45 1 2 3", False),
    ("Fe C H", "45 2 4", False),
])
def test_exact_c2_compositions(tmp_path, symbols, counts, passed):
    number = sum(map(int, counts.split()))
    coordinates = ["0 0 0 F F F"] * 18 + ["0.2 0.2 0.6 T T T"] * (number - 18)
    (tmp_path / "POSCAR").write_text(
        "composition fixture\n1.0\n10 0 0\n0 10 0\n0 0 20\n"
        + symbols + "\n" + counts + "\nSelective dynamics\nDirect\n"
        + "\n".join(coordinates) + "\n", encoding="ascii",
    )
    build_fe110_adsorption_relaxation(tmp_path)
    (tmp_path / "candidate_manifest.json").write_text(
        json.dumps({"candidate": "composition_fixture"}), encoding="ascii",
    )
    report = preflight(tmp_path)
    assert report["passed"] is passed
    if not passed:
        assert "POSCAR_COMPOSITION_OR_ORDER_MISMATCH" in report["errors"]
