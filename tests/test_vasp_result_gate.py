from pathlib import Path

from scripts.vasp_result_gate import final_scf_status
from scripts.neb_agent.utils_vasp import parse_outcar


def test_outcar_ediff_termination_overrides_truncated_oszicar_delta(tmp_path: Path) -> None:
    incar = tmp_path / "INCAR"
    oszicar = tmp_path / "OSZICAR"
    outcar = tmp_path / "OUTCAR"
    incar.write_text("NELM = 200\nEDIFF = 1E-5\n", encoding="ascii")
    oszicar.write_text(
        "DAV: 56 -0.371865942528E+03 -0.22875E-04 -0.26508E-04\n",
        encoding="ascii",
    )
    outcar.write_text(
        "aborting loop because EDIFF is reached\n"
        "General timing and accounting informations for this job:\n",
        encoding="ascii",
    )

    status = final_scf_status(oszicar, incar, outcar)

    assert status["electronically_converged"] is True
    assert status["electronic_convergence_source"] == "OUTCAR_EDIFF_TERMINATION"


def test_gpu_energy_before_ediff_is_one_electronic_target(tmp_path):
    incar, oszicar, outcar = (tmp_path / name for name in ("INCAR", "OSZICAR", "OUTCAR"))
    incar.write_text("NELM=200\nEDIFF=1e-6\n")
    oszicar.write_text("RMM: 75 -10.0 -7.4337E-7 -4.1711E-9 20 1E-5\n1 F= -10.0 E0= -10.0\n")
    outcar.write_text(
        "Iteration 1(74)\nenergy(sigma->0) = -9.99\n"
        "Iteration 1(75)\nenergy(sigma->0) = -10.0\n"
        "aborting loop because EDIFF is reached\n"
        "General timing and accounting informations for this job\n")
    parsed = parse_outcar(outcar)
    assert len(parsed["electronic_cycles"]) == 1
    assert parsed["final_target_step"]["iteration"] == 75
    assert final_scf_status(oszicar, incar, outcar)["electronically_converged"]
    with outcar.open("a") as handle:
        handle.write("Iteration 2(1)\n")
    assert not final_scf_status(oszicar, incar, outcar)["electronically_converged"]
