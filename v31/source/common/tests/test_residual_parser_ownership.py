from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from scripts.aqcat25_calibration import parse_final_outcar
from scripts.neb_agent.utils_vasp import parse_outcar
from scripts.vasp_result_gate import read_incar_values


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/fe-vasp-incar-custodian/scripts/incar_custodian.py"
SPEC = importlib.util.spec_from_file_location("custodian_parser_test", SKILL)
CUSTODIAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CUSTODIAN)


@pytest.mark.parametrize("text", [
    "NELM=60; MAGMOM=3*2.0",
    "  nelm = 60 ; magmom = 3*2.0 ; encut = 400 ",
    "NELM=60; MAGMOM=3*2.0 # ignored ; MAGMOM=wrong\nEDIFF=1e-5",
    "NELM = 60 ! ignored\n  MAGMOM = 3*2.0 ! ignored",
    "ISPIN=2; MAGMOM=3*2.0; LREAL=.FALSE.; NELM=60",
    "MAGMOM=3*2.0; magmom=3*2.0",
])
def test_custodian_preserves_raw_magmom_through_canonical_reader(tmp_path, text):
    path = tmp_path / "INCAR"
    path.write_text(text)
    assert CUSTODIAN.raw_incar_value(path, "magmom") == "3*2.0"
    assert CUSTODIAN.read_incar_values is read_incar_values


def test_custodian_missing_values_preserve_none(tmp_path):
    path = tmp_path / "INCAR"
    assert CUSTODIAN.raw_incar_value(None, "MAGMOM") is None
    assert CUSTODIAN.raw_incar_value(path, "MAGMOM") is None
    path.write_text("NELM=60")
    assert CUSTODIAN.raw_incar_value(path, "MAGMOM") is None


@pytest.mark.parametrize("text", ["MAGMOM=3*2.0; MAGMOM=2*2.0", "NELM=60 MAGMOM=3*2.0", "MAGMOM="])
def test_custodian_inherits_canonical_invalid_assignment_policy(tmp_path, text):
    path = tmp_path / "INCAR"
    path.write_text(text)
    with pytest.raises(ValueError):
        CUSTODIAN.raw_incar_value(path, "MAGMOM")


FORCES = """free  energy   TOTEN  =       -10.5000 eV
 TOTAL-FORCE (eV/Angst)
 ---------------------------
 0 0 0  0.10 0.20 0.30
 1 0 0 -0.10 0.00 0.20
 ---------------------------
"""
COMPLETE = """ reached required accuracy - stopping structural energy minimisation
 General timing and accounting informations for this job:
"""


@pytest.mark.parametrize(("suffix", "completed"), [
    ("", True),
    ("vasp.5.4.4 restarted\n", False),
    (" Iteration 2( 1)\n", False),
    (" Iteration 2( ", False),
    ("vasp.5.4.4 restarted\n Iteration 1( 1)\n" + FORCES + COMPLETE, True),
])
def test_calibration_completion_uses_current_run_and_cycle(tmp_path, suffix, completed):
    path = tmp_path / "OUTCAR"
    path.write_text("vasp.5.4.4\n Iteration 1( 1)\n" + FORCES + COMPLETE + suffix)
    result = parse_final_outcar(path)
    state = parse_outcar(path)
    assert result["normal_completion"] is state["normal_completion"] is completed
    assert result["ionic_converged"] is state["reached_required_accuracy"] is completed
    # Retained force/energy diagnostics are not an acceptance claim.
    assert result["forces_eV_per_A"] == [[0.1, 0.2, 0.3], [-0.1, 0.0, 0.2]]
    assert result["final_toten_eV"] == -10.5


def test_calibration_uses_last_force_and_energy_values_without_promoting_them(tmp_path):
    path = tmp_path / "OUTCAR"
    last = FORCES.replace("-10.5000", "-11.2500").replace("0.10 0.20 0.30", "0.40 0.50 0.60")
    path.write_text(FORCES + COMPLETE + "vasp.5.4.4\n Iteration 1( 1)\n" + last)
    result = parse_final_outcar(path)
    assert result["final_toten_eV"] == -11.25
    assert result["forces_eV_per_A"][0] == [0.4, 0.5, 0.6]
    assert not result["normal_completion"]
    assert not result["ionic_converged"]


@pytest.mark.parametrize("text", ["", "free  energy   TOTEN  = -1 eV\n", FORCES.replace("free  energy   TOTEN", "not energy")])
def test_calibration_still_rejects_missing_force_or_energy(tmp_path, text):
    path = tmp_path / "OUTCAR"
    path.write_text(text)
    with pytest.raises(ValueError):
        parse_final_outcar(path)


@pytest.mark.parametrize(("path", "function", "delegate", "forbidden"), [
    (SKILL, "raw_incar_value", "read_incar_values", {"split", "splitlines", "read_text"}),
    (ROOT / "scripts/aqcat25_calibration.py", "parse_final_outcar", "parse_outcar", set()),
])
def test_residual_parser_facades_cannot_reclaim_validation(path, function, delegate, forbidden):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function)
    calls = [item.func for item in ast.walk(node) if isinstance(item, ast.Call)]
    assert any(isinstance(call, ast.Name) and call.id == delegate for call in calls)
    assert not any(isinstance(call, ast.Attribute) and call.attr in forbidden for call in calls)
    if function == "parse_final_outcar":
        literals = [item.value for item in ast.walk(node) if isinstance(item, ast.Constant) and isinstance(item.value, str)]
        assert not any("reached required accuracy" in value or "General timing" in value for value in literals)
