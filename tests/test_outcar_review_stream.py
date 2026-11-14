"""Synthetic raw-file regressions: no model, scheduler or scientific job runs."""
from pathlib import Path
import sys

import pytest
import yaml

from scripts.adsorption import review_completed_batch as review
from scripts.adsorption.build_fe110_adsorption import generate_sites, read_poscar, write_poscar
from scripts.adsmind_lite.candidate_generation import compose_candidate_structure
from scripts.aqcat25_calibration import parse_final_outcar
from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent.utils_vasp import parse_outcar
from tests.test_b2_scientific_contract import osz_cycle, out_cycle

ROOT = Path(__file__).resolve().parents[1]


def force_output(count=2):
    return (out_cycle(1) + "free  energy   TOTEN  = -100 eV\nTOTAL-FORCE (eV/Angst)\n----\n"
            + "0 0 0 0.001 0 0\n" * count + "----\nreached required accuracy\n"
            + "General timing and accounting informations for this job\n")


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_hash_and_final_values_share_one_stream_and_keep_default_state(tmp_path, monkeypatch, newline):
    path = tmp_path / "OUTCAR"
    path.write_bytes(force_output().replace("\n", newline).encode() + b"\xff\n")
    expected_hash = sha256_file(path)
    state = parse_outcar(path)
    original_open = Path.open
    opens = []

    def counted(self, *args, **kwargs):
        if self == path:
            opens.append(args[0] if args else "r")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counted)
    parsed = parse_outcar(path, include_final_forces=True, include_sha256=True)
    assert opens == ["rb"]
    assert parsed["source_sha256"] == expected_hash
    assert {key: parsed[key] for key in state} == state
    opens.clear()
    labels = parse_final_outcar(path)
    assert len(opens) == 1
    assert labels == {"ionic_converged": True, "normal_completion": True,
                      "final_toten_eV": -100.0, "forces_eV_per_A": [[.001, 0., 0.]] * 2}


@pytest.mark.parametrize("tail", ["Iteration 2( 1)\n", "vasp.6\nIteration 1( 1)\n"])
def test_one_stream_never_inherits_completion_from_previous_cycle(tmp_path, tail):
    path = tmp_path / "OUTCAR"
    path.write_text(force_output() + tail)
    state = parse_outcar(path, include_final_forces=True, include_sha256=True)
    assert state["normal_completion"] is state["reached_required_accuracy"] is False
    assert state["final_target_complete"] is False
    assert parse_final_outcar(path)["normal_completion"] is False


@pytest.mark.parametrize("with_labels", [False, True])
def test_numbered_cycle_keeps_ediff_marker_after_sigma0(tmp_path, with_labels):
    path = tmp_path / "OUTCAR"
    path.write_text("Iteration 1( 5)\nenergy(sigma->0) = -100\n"
                    "aborting loop because EDIFF is reached\n"
                    "General timing and accounting informations for this job\n")
    state = parse_outcar(path, include_final_forces=with_labels, include_sha256=with_labels)
    assert len(state["electronic_cycles"]) == 1
    assert state["final_target_step"]["iteration"] == 5
    assert state["final_target_explicit_convergence"] is True


@pytest.mark.parametrize("text,message", [("free  energy   TOTEN  = -1 eV\n", "no TOTAL-FORCE"),
    ("TOTAL-FORCE (eV/Angst)\n----\n0 0 0 1 0 0\n----\n", "no TOTEN")])
def test_missing_force_or_energy_still_fails(tmp_path, text, message):
    path = tmp_path / "OUTCAR"
    path.write_text(text)
    with pytest.raises(ValueError, match=message):
        parse_final_outcar(path)


@pytest.fixture
def real_batch(tmp_path, monkeypatch):
    """Use the local slab as geometry only; every output and energy is synthetic."""
    monkeypatch.chdir(ROOT)
    slab_path = ROOT / "calculations/true_fe110_clean_20260629/POSCAR"
    slab = read_poscar(slab_path)
    sites, _ = generate_sites(slab)
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/adsorbate_rules.yaml").read_text())["adsorbates"]
    pose, _ = compose_candidate_structure(slab, next(iter(sites.values())), "CO", rules["CO"])
    source = tmp_path / "sources/case"
    source.mkdir(parents=True)
    for name in ("POSCAR", "CONTCAR"):
        write_poscar(source / name, pose)
    incar = {"GGA": "PE", "ENCUT": 400, "EDIFF": 1e-5, "EDIFFG": -.02,
             "ISPIN": 2, "ISMEAR": 1, "SIGMA": .20, "ISIF": 2}
    (source / "INCAR").write_text("\n".join(f"{key}={value}" for key, value in incar.items())
                                  + "\nNELM=60\nMAGMOM=45*2.2 2*0\n")
    (source / "KPOINTS").write_text("test\n0\nGamma\n5 5 1\n0 0 0\n")
    (source / "OUTCAR").write_text(force_output(47))
    (source / "OSZICAR").write_text(osz_cycle(1))
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    write_json(input_dir / "candidate_manifest.json", {"builder": {"incar": incar}})
    files = {path.name: {"sha256": sha256_file(path)} for path in source.iterdir()}
    files["POTCAR"] = {"sha256": "a" * 64}
    write_json(source / "collection.json", {"remote": {"files": files}, "submission": {
        "workdir": str(input_dir), "job_id": "synthetic", "species_id": "CO", "formula": "CO",
        "connectivity": "CO", "potcar_sha256": "a" * 64}})
    return source, slab_path


def test_real_cold_review_two_outcar_passes_warm_review_one(real_batch, tmp_path, monkeypatch):
    source, slab = real_batch
    original_open = Path.open
    opens = []

    def counted(self, *args, **kwargs):
        if self.resolve() == (source / "OUTCAR").resolve():
            opens.append(args[0] if args else "r")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counted)
    outputs = []
    for index, expected in enumerate((2, 1)):
        output = tmp_path / f"review_{index}.json"
        monkeypatch.setattr(sys, "argv", ["review", "--sources", str(source.parent), "--slab", str(slab), "--output", str(output)])
        opens.clear()
        review.main()
        assert len(opens) == expected
        outputs.append(load_json_object(output))
    assert outputs[0]["records"] == outputs[1]["records"]
    record = outputs[0]["records"][0]
    assert record["convergence"]["electronically_converged"] is True
    assert record["blockers"] == []
    assert outputs[1]["cache_hits"] == 1
    assert record["scientific_acceptance"] is False


def test_raw_change_after_parsing_publishes_no_cache_or_output(real_batch, tmp_path, monkeypatch):
    source, slab = real_batch
    original = review.mark_duplicates

    def changed(records, slab, rules):
        result = original(records, slab, rules)
        with (source / "OUTCAR").open("a") as handle:
            handle.write("changed after parse\n")
        return result

    monkeypatch.setattr(review, "mark_duplicates", changed)
    output = tmp_path / "review.json"
    monkeypatch.setattr(sys, "argv", ["review", "--sources", str(source.parent), "--slab", str(slab), "--output", str(output)])
    with pytest.raises(ValueError, match="collected source changed"):
        review.main()
    assert not output.exists()
    assert not list((tmp_path / "parsed").glob("*.json"))
