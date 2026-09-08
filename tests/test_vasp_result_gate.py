from pathlib import Path

from scripts.vasp_result_gate import final_scf_status


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
