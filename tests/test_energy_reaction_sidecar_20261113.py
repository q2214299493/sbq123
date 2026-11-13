import contextlib
import copy
import hashlib
import io
import json

import pytest

from archive.fe110_energy_reaction_sidecar_20261113 import audit, pair_groups
from archive.fe110_energy_reaction_sidecar_20261113.finalize import unique_labels
from archive.fe110_energy_reaction_sidecar_20261113.remote_read import PROGRAM
from archive.fe110_grouped_qc_20261026.review import raw_frames


def ionic_block(step, moment, force, ediff=True):
    return (f"Iteration {step}( 7)\n"
            + ("aborting loop because EDIFF is reached\n" if ediff else "")
            + "magnetization (x)\n# of ion s p d tot\n----\n"
            + f" 1 0.0 0.0 0.0 {moment}\n 2 0.0 0.0 0.0 0.1\n----\n"
            + "POSITION TOTAL-FORCE (eV/Angst)\n----\n"
            + f"0.00000 0.00000 0.00000 {force} 0.0 0.0\n"
            + "1.00000 0.00000 0.00000 0.0 0.0 0.0\n----\n"
            + f"free  energy   TOTEN  = {-10.0-step} eV\n")


def run_read_parser(tmp_path, data, incar="NSW = 10\n", requested=(1, 2)):
    raw = data.encode()
    (tmp_path / "OUTCAR").write_bytes(raw)
    (tmp_path / "INCAR").write_text(incar)
    target = {"directory": str(tmp_path), "steps": list(requested), "sha256": hashlib.sha256(raw).hexdigest()}
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(PROGRAM, "<read-only-parser>", "exec"), {"TARGETS": [target]})
    return json.loads(output.getvalue())["results"][0]


def test_streaming_read_matches_canonical_frame_association(tmp_path):
    data = " NIONS = 2\n" + ionic_block(1, 2.2, .3) + ionic_block(2, -1.1, -.4, ediff=False)
    result = run_read_parser(tmp_path, data)
    expected = raw_frames(tmp_path / "OUTCAR", 2)
    assert result["expected_hash_matches"] is True
    assert result["remote_writes"] is False
    for observed, canonical in zip(result["frames"], expected, strict=True):
        for key in ["ionic_step", "forces_eV_per_A", "toten_eV", "local_moment_tables", "EDIFF_marker_before_force"]:
            assert observed[key] == canonical[key]
        start, end = observed["source_byte_range"]
        assert hashlib.sha256(data.encode()[start:end]).hexdigest() == observed["force_extraction_sha256"]


def test_static_DFT_step_does_not_inherit_ML_candidate_step(tmp_path):
    result = run_read_parser(tmp_path, "NIONS = 2\n" + ionic_block(1, 2.2, .3), "NSW = 0\n", requested=(4,))
    assert result["selected_DFT_steps"] == [1]
    assert result["frames"][0]["ionic_step"] == 1


def label(partition="train", energy=-11):
    return {"physical_label_key": "digest:1", "sample_id": partition, "partition": partition,
            "pool": "fixture", "E_TOTEN_eV": energy, "energy_force_evidence_ready_for_review": True}


@pytest.mark.parametrize("partition", ["development", "heldout", "final_test", "quarantine"])
def test_any_protected_alias_blocks_training_reuse(partition):
    record = unique_labels([label(), label(partition)])[0]
    assert record["train_and_protected_conflict"] is True
    assert record["future_energy_reuse_review_candidate"] is False
    assert record["training_admission"] is False


def test_conflicting_energy_for_one_raw_frame_is_rejected():
    with pytest.raises(ValueError, match="inconsistent stored energies"):
        unique_labels([label(), label(energy=-12)])


def test_original_nested_source_hash_adapter_does_not_mutate_source(monkeypatch, tmp_path):
    source = {"sample_id": "static", "structure_path": "POSCAR", "input_output_hashes": {"OUTCAR": "bound-hash"}}
    original = copy.deepcopy(source)
    monkeypatch.setattr(audit, "BASE", tmp_path)
    monkeypatch.setattr(audit, "PACKAGE", tmp_path)

    def load(path):
        if path.name == "training_manifest.json":
            return {"splits": {}, "quarantined_observed_heldout": []}
        return {"samples": [source]}

    monkeypatch.setattr(audit, "load_json_object", load)
    rows = audit.source_rows()
    assert len(rows) == 2
    assert all(row["row"]["source_OUTCAR_sha256"] == "bound-hash" for row in rows)
    assert source == original


def test_relative_groups_never_cross_potcar_or_protected_scope(monkeypatch, tmp_path):
    rows, catalog, remote = [], [], []
    for i, potcar in enumerate(["pot-A", "pot-A", "pot-B", "pot-B"]):
        digest = f"out-{i}"
        key = f"{digest}:1"
        rows.append({"physical_label_key": key, "source_OUTCAR_sha256": digest, "sample_id": str(i),
                     "family_id": "same-family", "composition": "C2H3", "E_TOTEN_eV": -10-i,
                     "energy_force_evidence_ready_for_review": True})
        catalog.append({"physical_label_key": key, "raw_E_F_local_magnetic_evidence_ready": True,
                        "future_energy_reuse_review_candidate": i != 3})
        remote.append({"OUTCAR_sha256": digest, "expected_hash_matches": True,
                       "input_sha256": {"INCAR": "inc", "KPOINTS": "kp"}, "POTCAR_sha256": potcar})
    inputs = {"energy_label_sidecar_final_v2.json": {"records": rows},
              "energy_reuse_catalog_v2.json": {"records": catalog}, "raw_source_index.json": {"entries": {}},
              "remote_raw_evidence.json": {"results": remote}, "remote_additional_evidence.json": {"results": []}}
    monkeypatch.setattr(pair_groups, "OUT", tmp_path)
    monkeypatch.setattr(pair_groups, "load_json_object", lambda path: inputs[path.name])
    pair_groups.run()
    groups = json.loads((tmp_path / "relative_energy_pair_candidates.json").read_text())["groups"]
    assert len(groups) == 2
    assert all(group["physical_frames"] == 2 for group in groups)
    assert sum(group["training_eligible_scope_after_review"] for group in groups) == 1
    assert all(len({m["signature"]["POTCAR_sha256"] for m in group["members"]}) == 1 for group in groups)
