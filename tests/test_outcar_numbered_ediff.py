from pathlib import Path

from scripts.neb_agent.utils_vasp import parse_outcar
from scripts.vasp_result_gate import final_scf_status


def test_numbered_ediff_after_inner_energy_does_not_duplicate_cycles(tmp_path: Path):
    out = tmp_path / "OUTCAR"
    out.write_text("""Iteration 1( 1)
energy without entropy = -1 energy(sigma->0) = -1
Iteration 1( 2)
energy without entropy = -1 energy(sigma->0) = -1
aborting loop because EDIFF is reached
energy without entropy = -1 energy(sigma->0) = -1
Iteration 2( 1)
energy without entropy = -1 energy(sigma->0) = -1
Iteration 2( 2)
energy without entropy = -1 energy(sigma->0) = -1
aborting loop because EDIFF is reached
energy without entropy = -1 energy(sigma->0) = -1
General timing and accounting informations for this job
""", encoding="ascii")
    incar = tmp_path / "INCAR"
    incar.write_text("NELM=200\nEDIFF=1E-7\n", encoding="ascii")
    osz = tmp_path / "OSZICAR"
    osz.write_text("RMM: 1 -1 1E-3 1E-3 20 0.1\nRMM: 2 -1 1E-8 1E-8 20 0.1\n 1 F= -1 E0= -1\n"
                   "RMM: 1 -1 1E-3 1E-3 20 0.1\nRMM: 2 -1 1E-8 1E-8 20 0.1\n 2 F= -1 E0= -1\n", encoding="ascii")
    parsed = parse_outcar(out)
    assert parsed["final_target_step"]["cycle"] == 2
    assert parsed["final_target_step"]["iteration"] == 2
    assert final_scf_status(osz, incar, out)["electronically_converged"]
    with out.open("a", encoding="ascii") as handle:
        handle.write("Iteration 3( 1)\n")
    assert not final_scf_status(osz, incar, out)["electronically_converged"]
