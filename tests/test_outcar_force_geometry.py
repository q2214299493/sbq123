"""Small synthetic GPU-format regressions; no production result fixtures."""
import pytest

from scripts.aqcat25_calibration import parse_final_outcar


HEADER = """TITEL = PAW_PBE Fe test
TITEL = PAW_PBE C test
ions per type = 1 1
direct lattice vectors reciprocal lattice vectors
10 0 0 0.1 0 0
0 10 0 0 0.1 0
0 0 20 0 0 0.05
"""
TABLE = """POSITION TOTAL-FORCE (eV/Angst)
-----------------
0 0 0 0.1 -0.2 0.3
1 2 3 0.4 0.5 -0.6
-----------------
free  energy   TOTEN  = -10.0 eV
General timing and accounting informations for this job
"""


def test_coordinates_and_forces_share_final_table_without_kpoint_parser(tmp_path):
    path = tmp_path / "OUTCAR"
    path.write_text(HEADER + "k-points in reciprocal lattice and weights\n\n" + TABLE)
    legacy = parse_final_outcar(path)
    assert set(legacy) == {"ionic_converged", "normal_completion", "final_toten_eV", "forces_eV_per_A"}
    parsed = parse_final_outcar(path, include_geometry=True)
    assert parsed["symbols"] == ["Fe", "C"]
    assert parsed["positions_A"] == [[0, 0, 0], [1, 2, 3]]
    assert parsed["forces_eV_per_A"] == [[0.1, -0.2, 0.3], [0.4, 0.5, -0.6]]
    assert parsed["cell_A"][2] == [0, 0, 20]


@pytest.mark.parametrize("header,table", [
    (HEADER.replace("ions per type = 1 1", "ions per type = 1 2"), TABLE),
    (HEADER.replace("TITEL = PAW_PBE C test\n", ""), TABLE),
    (HEADER, TABLE.replace("1 2 3 0.4 0.5 -0.6\n", "")),
    (HEADER, TABLE + "POSITION TOTAL-FORCE (eV/Angst)\n---\n"),
])
def test_incomplete_final_geometry_cannot_reuse_earlier_table(tmp_path, header, table):
    path = tmp_path / "OUTCAR"
    path.write_text(header + table)
    with pytest.raises(ValueError):
        parse_final_outcar(path, include_geometry=True)
