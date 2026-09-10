from __future__ import annotations

import ast
import csv
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.convergence import setup_alpha_fe_bulk_smearing as alpha
from scripts.neb_agent.utils_vasp import parse_outcar


COMPLETE = (
    "vasp.5.4.4\nIteration 1( 1)\naborting loop because EDIFF is reached\n"
    "free energy TOTEN = -10.0 eV\nenergy(sigma->0) = -9.9\n"
    "entropy T*S EENTRO = -0.02\n"
    "General timing and accounting informations for this job:\n"
)
INCOMPLETE = [
    COMPLETE + "vasp.5.4.4 restarted\n",
    COMPLETE + "Iteration 2( 1)\n",
    COMPLETE + "Iteration 2( ",
    COMPLETE.replace("General timing and accounting informations for this job:\n", ""),
    COMPLETE.replace("aborting loop because EDIFF is reached", "electronic loop exhausted"),
    COMPLETE + "VERY BAD NEWS\n",
    "General timing and accounting informations for this job:\n",
    "",
    None,
]


@pytest.fixture
def summary_case(tmp_path, monkeypatch):
    monkeypatch.setattr(alpha, "WORKDIR", tmp_path)
    monkeypatch.setattr(alpha, "CASES", [("tetra", -5, 0.05), ("metal", 1, 0.2)])
    for name in ("tetra", "metal"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "OUTCAR").write_text(COMPLETE, encoding="ascii")
        (folder / "OSZICAR").write_text("1 F= -10.0 mag= 4.4\n", encoding="ascii")

    def run():
        alpha.summary()
        with (tmp_path / "alpha_fe_bulk_smearing_summary.csv").open(encoding="ascii") as handle:
            return {row["case"]: row for row in csv.DictReader(handle)}

    return tmp_path, run


def test_current_static_summary_preserves_formula_without_ionic_requirement(summary_case, monkeypatch):
    root, run = summary_case
    spy = Mock(wraps=parse_outcar)
    monkeypatch.setattr(alpha, "parse_outcar", spy)
    rows = run()
    assert spy.call_count == 2
    assert {call.args[0] for call in spy.call_args_list} == {root / "tetra/OUTCAR", root / "metal/OUTCAR"}
    assert not parse_outcar(root / "metal/OUTCAR")["reached_required_accuracy"]
    assert all(row["finished"] == "True" for row in rows.values())
    assert float(rows["metal"]["delta_vs_tetra_meV_atom"]) == pytest.approx(abs((-9.9 - -10.) / 2 * 1000))
    assert float(rows["tetra"]["delta_vs_tetra_meV_atom"]) == 0
    assert float(rows["metal"]["abs_entropy_meV_atom"]) == 10
    assert float(rows["metal"]["mag_cell_uB"]) == 4.4
    assert all("scientific_acceptance" not in row for row in rows.values())


@pytest.mark.parametrize("text", INCOMPLETE)
@pytest.mark.parametrize("damaged", ["tetra", "metal"])
def test_incomplete_case_or_reference_never_produces_valid_comparison(summary_case, text, damaged):
    root, run = summary_case
    path = root / damaged / "OUTCAR"
    if text is None:
        path.unlink()  # Only this temporary test fixture.
    else:
        path.write_text(text, encoding="ascii")
    rows = run()
    assert rows[damaged]["finished"] == "False"
    assert rows[damaged]["delta_vs_tetra_meV_atom"] == ""
    assert rows[damaged]["abs_entropy_meV_atom"] == ""
    if damaged == "tetra":
        assert rows["metal"]["delta_vs_tetra_meV_atom"] == ""
    else:
        assert rows["tetra"]["finished"] == "True"
        assert float(rows["tetra"]["delta_vs_tetra_meV_atom"]) == 0
    if text and "free energy TOTEN" in text:
        assert float(rows[damaged]["toten_eV"]) == -10.0  # Available raw diagnostics retained.
    assert all("scientific_acceptance" not in row for row in rows.values())


def test_alpha_completion_has_one_parser_owner():
    assert alpha.parse_outcar is parse_outcar
    tree = ast.parse(Path(alpha.__file__).read_text(encoding="utf-8"))
    summary = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "summary")
    assert sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "parse_outcar" for n in ast.walk(summary)) == 1
    literals = [n.value for n in ast.walk(summary) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not any("General timing" in value or "reached required accuracy" in value for value in literals)
