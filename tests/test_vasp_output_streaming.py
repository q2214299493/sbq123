from __future__ import annotations

from pathlib import Path

from scripts.neb_agent.utils_vasp import parse_oszicar, parse_outcar


def test_oszicar_is_parsed_in_one_stream_without_read_text(
    tmp_path: Path, monkeypatch
) -> None:
    oszicar = tmp_path / "OSZICAR"
    oszicar.write_text(
        " DAV:  1\n"
        " RMM:  2\n"
        " 1 F= -.10000000E+02 E0= -.1001E+02 mag= 2.5000\n"
        " CGA:  1\n"
        " 2 F= -.11000000E+02 E0= -.1101E+02 mag= 2.2500\n"
        " DAV:  1\n",
        encoding="ascii",
    )

    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("streaming parser must not call Path.read_text")
        ),
    )

    assert parse_oszicar(oszicar) == {
        "exists": True,
        "ionic_steps": 2,
        "energies": [-10.0, -11.0],
        "scf_iterations": [2, 1],
        "current_scf_iterations": 1,
        "magnetization_history_muB": [2.5, 2.25],
    }


def test_outcar_is_parsed_in_one_stream_and_keeps_last_local_magnetization(
    tmp_path: Path, monkeypatch
) -> None:
    outcar = tmp_path / "OUTCAR"
    outcar.write_text(
        " FORCES: max atom, RMS  0.8000  0.3000\n"
        " NEB: forces: par spring, perp REAL, dneb  0.1000  0.7000\n"
        " energy(sigma->0) = -100.125\n"
        " number of electron 10.0 magnetization 2.5000\n"
        " magnetization (x)\n"
        " # of ion       s       p       d       tot\n"
        " 1 0.1 0.2 0.3 0.6\n"
        " tot 0.1 0.2 0.3 0.6\n"
        " FORCES: max atom, RMS  0.2000  0.0500\n"
        " NEB: forces: par spring, perp REAL, dneb  0.0500  0.1500\n"
        " energy(sigma->0) = -101.250\n"
        " number of electron 10.0 magnetization 2.2500\n"
        " magnetization (x)\n"
        " # of ion       s       p       d       tot\n"
        " 1 0.2 0.3 0.4 0.9\n"
        " 2 0.1 0.1 0.2 0.4\n"
        " tot 0.3 0.4 0.6 1.3\n"
        " aborting loop because EDIFF is reached\n"
        " reached required accuracy\n"
        " BRMIX: very serious problems\n"
        " General timing and accounting informations for this job\n",
        encoding="ascii",
    )

    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("streaming parser must not call Path.read_text")
        ),
    )

    assert parse_outcar(outcar) == {
        "exists": True,
        "atomic_force_history": [0.8, 0.2],
        "atomic_force_rms_history": [0.3, 0.05],
        "neb_force_history": [0.7, 0.15],
        "sigma0_energies": [-100.125, -101.25],
        "electronic_convergence_reached": True,
        "reached_required_accuracy": True,
        "normal_completion": True,
        "total_magnetization_history_muB": [2.5, 2.25],
        "local_magnetization_last_muB": [0.9, 0.4],
        "fatal_keywords": ["BRMIX"],
    }


def test_missing_vasp_outputs_keep_existing_empty_contract(tmp_path: Path) -> None:
    assert parse_oszicar(tmp_path / "OSZICAR") == {
        "exists": False,
        "ionic_steps": 0,
        "energies": [],
        "scf_iterations": [],
    }
    assert parse_outcar(tmp_path / "OUTCAR") == {
        "exists": False,
        "atomic_force_history": [],
        "atomic_force_rms_history": [],
        "neb_force_history": [],
    }
