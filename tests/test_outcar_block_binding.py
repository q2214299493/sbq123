from pathlib import Path

import pytest

from scripts.aqcat25_calibration import parse_final_outcar
from scripts.neb_agent.outcar_blocks import read_force_blocks
from scripts.neb_agent.utils_vasp import last_positions
from scripts.research_assistant.catalog import Catalog
from scripts.research_assistant.tools import ToolRegistry


FIRST = """ NIONS = 2
 free  energy   TOTEN  = -10.0 eV
 POSITION TOTAL-FORCE (eV/Angst)
 -------------------
 0 0 0  0.1 0 0
 1 0 0  0.2 0 0
 -------------------
"""
HEADER = " POSITION TOTAL-FORCE (eV/Angst)\n -------------------\n"


@pytest.mark.parametrize("tail", [
    HEADER + " 9 0 0  0.4 0 0\n",
    HEADER + " 9 0 0  NaN 0 0\n 8 0 0  0.4 0 0\n -------------------\n",
    HEADER + " 9 0 0  broken 0 0\n 8 0 0  0.4 0 0\n -------------------\n",
    HEADER + " 9 0 0\n 8 0 0\n -------------------\n",
])
def test_partial_or_invalid_later_table_never_rebinds_earlier_forces(tmp_path, tail):
    path = tmp_path / "OUTCAR"
    path.write_text(FIRST + tail, encoding="utf-8")
    blocks = read_force_blocks(path)
    parsed = parse_final_outcar(path)
    assert not blocks["selected_is_latest_attempt"]
    assert blocks["selected"]["block_index"] == parsed["force_block"]["block_index"] == 1
    assert parsed["forces_eV_per_A"] == [[0.1, 0, 0], [0.2, 0, 0]]
    assert parsed["positions_A"] == last_positions(path, 2).tolist() == [[0, 0, 0], [1, 0, 0]]
    latest = blocks["latest_attempt"]
    assert latest["block_index"] == 2 and not latest["complete"]
    assert latest["coordinate_complete"] == (latest["observed_rows"] == 2)
    assert not latest["force_valid"]
    assert parsed["force_block"]["header_line"] == 3
    assert parsed["force_block"]["row_start_line"] == 5 and parsed["force_block"]["row_end_line"] == 6


def test_first_unknown_count_requires_closure_but_known_count_can_end_at_eof(tmp_path):
    path = tmp_path / "OUTCAR"
    path.write_text(HEADER + "0 0 0  0.1 0 0\n")
    assert read_force_blocks(path)["selected"] is None
    assert read_force_blocks(path, 1)["selected"]["complete"]


def test_force_parser_streams_and_reports_no_valid_table(tmp_path, monkeypatch):
    path = tmp_path / "OUTCAR"
    path.write_text("NIONS=2\n" + HEADER + "0 0 0 nan 0 0\n1 0 0 inf 0 0\n---\n")
    monkeypatch.setattr(Path, "read_text", lambda *a, **kw: pytest.fail("must stream"))
    result = read_force_blocks(path)
    assert result["selected"] is None and result["latest_attempt"]["coordinate_complete"]
    assert not result["latest_attempt"]["force_valid"]


@pytest.mark.parametrize("bad_structure,no_force", [(True, False), (False, True)])
def test_vasp_partial_component_errors_do_not_hide_other_observations(tmp_path, bad_structure, no_force):
    scope, output = tmp_path / "calculation", tmp_path / "output"
    scope.mkdir()
    output.mkdir()
    (scope / "OUTCAR").write_text(("NIONS=2\n" if no_force else FIRST) + " General timing and accounting informations for this job\n")
    (scope / "INCAR").write_text("NELM=100\nEDIFF=1e-5\n")
    (scope / "OSZICAR").write_text("RMM: 1 -10 1e-7 1e-8\n1 F= -10 E0= -10\n")
    (scope / "vasp.out").write_text("retained stdout after local failure\n")
    if bad_structure:
        (scope / "CONTCAR").write_text("malformed structure\n")
    catalog = Catalog([scope], output)
    tools = ToolRegistry(catalog, scope, output)
    result = tools.execute({"tool": "terminal.align", "target_ids": [catalog.listed(scope)], "query": "", "limit": 5})
    assert result["status"] == "PARTIAL"
    data = result["data"]
    assert data["outcar"]["normal_completion"] and data["oszicar"]["ionic_steps"] == 1
    assert "owner_scf_oszicar_only" in data and "retained stdout" in data["stdout_tail"]
    assert data["component_errors"]
    if bad_structure:
        assert data["last_complete_force_block"]["maximum_all_atoms_eV_per_A"] == 0.2
        assert data["component_status"]["saved_structure"] == "ERROR"
    else:
        assert data["force_block_observations"]["selected"] is None
