import hashlib
import json

import pytest
import numpy as np
from ase import Atoms

from archive.fe110_adsorption_calibration_20261018.prepare_current_trajectories import (
    check_inputs,
    read_collection,
    reader_source,
    restore_input_lattice,
)


@pytest.mark.parametrize("atom_count", [49, 50])
def test_reader_preserves_exact_atom_count_force_frames_and_source_hash(tmp_path, capsys, atom_count):
    for name in ("POSCAR", "CONTCAR", "INCAR", "KPOINTS", "OSZICAR", "XDATCAR", "POTCAR"):
        (tmp_path / name).write_text("synthetic input only\n")
    lines = []
    for step in range(1, 6):
        lines.extend([f"Iteration {step}( 3)\n", "aborting loop because EDIFF is reached\n",
                      "TOTAL-FORCE (eV/Angst)\n", "-----------------------\n"])
        lines.extend(["0.00000 0.00000 0.00000 0.0 0.0 0.0\n"] * atom_count)
        lines.extend(["-----------------------\n", f"free  energy   TOTEN  = {-step:.8f} eV\n"])
    lines.extend(["reached required accuracy\n", "General timing and accounting informations\n"])
    (tmp_path / "OUTCAR").write_text("".join(lines))
    exec(reader_source([{"name": "synthetic", "remote_dir": str(tmp_path), "atom_count": atom_count}]), {})
    result = json.loads(capsys.readouterr().out)
    assert result["OUTCAR_sha256"] == hashlib.sha256((tmp_path / "OUTCAR").read_bytes()).hexdigest()
    assert result["POTCAR_sha256"] == hashlib.sha256((tmp_path / "POTCAR").read_bytes()).hexdigest()
    assert [f["toten_eV"] for f in result["frames"]] == [-1, -2, -4, -5]
    assert all(len(f["forces_eV_per_A"]) == atom_count for f in result["frames"])


def make_inputs(tmp_path):
    (tmp_path / "INCAR").write_text("ENCUT=400\nISPIN=2\nISMEAR=1\nSIGMA=0.2\nEDIFF=1e-5\nEDIFFG=-0.02\nISIF=2\nGGA=PE\nLDIPOL=.FALSE.\nMAGMOM=45*2.2 5*0.0\n")
    (tmp_path / "KPOINTS").write_text("synthetic\n0\nGamma\n5 5 1\n0 0 0\n")
    (tmp_path / "POSCAR").write_text("synthetic input only\n")
    return {"workdir": str(tmp_path), "atom_count": 50}


def test_locked_compatibility_branch(tmp_path):
    check_inputs(tmp_path, make_inputs(tmp_path))


@pytest.mark.parametrize("before,after", [("SIGMA=0.2", "SIGMA=0.1"), ("ENCUT=400", "ENCUT=450"),
                                           ("45*2.2", "45*2.4"), ("LDIPOL=.FALSE.", "LDIPOL=.TRUE.")])
def test_branch_or_magnetic_change_rejected(tmp_path, before, after):
    record = make_inputs(tmp_path)
    path = tmp_path / "INCAR"
    path.write_text(path.read_text().replace(before, after))
    with pytest.raises(ValueError):
        check_inputs(tmp_path, record)


def test_xdatcar_rounding_is_not_a_physical_cell_change(tmp_path):
    cell = np.diag([8.4808451022, 5.996863081958339, 22.995817442611116])
    initial = Atoms("Fe", scaled_positions=[[.2, .3, .4]], cell=cell)
    atoms = Atoms("Fe", scaled_positions=[[.2, .3, .4]], cell=np.round(cell, 6))
    xdatcar = tmp_path / "XDATCAR"
    xdatcar.write_text("synthetic\n1.0\n8.480845 0.000000 0.000000\n0.000000 5.996863 0.000000\n0.000000 0.000000 22.995817\n")
    restore_input_lattice(atoms, initial, xdatcar)
    np.testing.assert_allclose(atoms.cell, cell, rtol=0, atol=0)
    np.testing.assert_allclose(atoms.get_scaled_positions(), [[.2, .3, .4]])


def test_real_cell_change_is_not_hidden_as_rounding(tmp_path):
    initial = Atoms("Fe", cell=np.eye(3) * 9)
    atoms = Atoms("Fe", cell=np.eye(3) * 8)
    xdatcar = tmp_path / "XDATCAR"
    xdatcar.write_text("synthetic\n1.0\n8.000000 0.000000 0.000000\n0.000000 8.000000 0.000000\n0.000000 0.000000 8.000000\n")
    with pytest.raises(ValueError, match="printed precision"):
        restore_input_lattice(atoms, initial, xdatcar)


def partial_collection(tmp_path, monkeypatch):
    import archive.fe110_adsorption_calibration_20261018.prepare_current_trajectories as module

    monkeypatch.setattr(module, "DEST", tmp_path)
    doc = {"record": {"name": "06_C"}, "normal_completion": True, "total_steps": 5,
           "frames": [{"ionic_step": step} for step in (1, 2, 4, 5)]}
    payload = (json.dumps(doc) + "\n").encode()
    (tmp_path / "remote_extraction.jsonl").write_bytes(payload)
    (tmp_path / "collection_receipt.json").write_text(json.dumps({"exit_code": 1,
        "output_sha256": hashlib.sha256(payload).hexdigest()}))
    return doc


def test_failed_batch_does_not_silently_pass(tmp_path, monkeypatch):
    partial_collection(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="unverified"):
        read_collection()


def test_reused_streaming_parser_matches_the_reviewed_snapshot():
    from archive.fe110_adsorption_calibration_20261018.reviewed_trajectory_helpers import REMOTE_READER

    assert hashlib.sha256(REMOTE_READER.encode()).hexdigest() == "8c932d0b0067ec959ebac35fc041c6b59730ccf042cfdad800273544831dd6f8"


def test_explicit_partial_recovery_reports_missing_jobs(tmp_path, monkeypatch):
    doc = partial_collection(tmp_path, monkeypatch)
    docs, missing = read_collection(allow_partial=True)
    assert docs == [doc]
    assert missing == ["07_B", "08_A", "08_B"]


def test_partial_recovery_still_requires_source_binding(tmp_path, monkeypatch):
    partial_collection(tmp_path, monkeypatch)
    with (tmp_path / "remote_extraction.jsonl").open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ValueError, match="unverified"):
        read_collection(allow_partial=True)
