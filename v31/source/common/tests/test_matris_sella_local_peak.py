"""Local analytic tests; no MatRIS weights, GPU, VASP or TS acceptance."""
from pathlib import Path
import shutil

import numpy as np
import pytest
from ase.calculators.calculator import Calculator, all_changes
from ase.io import read

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.dual_model_ml_neb import _refine_path_peak
from scripts.matris_sella_local_peak import prepare_request, run, validate_request
from scripts.ml_sella_candidate import BudgetCalculator, SellaBudgetExhausted
from scripts.prepare_ml_candidate_active_learning import prepare_candidate_round
from scripts.prepare_ml_candidate_rerun import _sella_followup
from scripts.dual_model_ts_force_prediction_batch import run_batch
from scripts.select_dual_model_ts_vasp_labels import select_samples
from tests.test_ml_sella_candidate import POLICY, _path_run


class MultiPeakCalculator(Calculator):
    implemented_properties = ["energy", "forces"]

    def calculate(self, atoms=None, properties=("energy", "forces"), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        reference = np.array([[1, 1, 1], [4, 4, 4], [5.4, 4, 4], [6.6, 4, 4], [3, 4.01, 4], [0, 4.01, 4.01]])
        delta = atoms.positions - reference
        delta[5, 0] = 0
        phase = 4 * np.pi * (atoms.positions[5, 0] - 7.57)
        forces = -2 * delta
        forces[5, 0] = -4 * np.pi * np.sin(phase)
        self.results = {"energy": float((delta**2).sum() - np.cos(phase)), "forces": forces}


def _entry(tmp_path, monkeypatch):
    source, checkpoint, secondary, parent_path, _, parent = _path_run(tmp_path, monkeypatch, sella=False)
    parent["optimizer"]["final_converged"] = False
    parent["single_strict_internal_peak"] = False
    parent["strict_internal_peak_images"] = ["02", "06"]
    for row in parent["images"]:
        atoms = read(parent_path.parent / row["structure_path"])
        atoms.calc = MultiPeakCalculator()
        row["predicted_energy_eV"] = float(atoms.get_potential_energy())
    write_json_atomic(parent_path, parent)
    review_path = tmp_path / "local_review.json"
    review = {"document_kind": "sella_local_peak_work_review", "reviewer": "analytic-test-fixture",
              "decision": "accepted_for_bounded_local_search", "single_event_review_passed": True,
              "reaction_event": "synthetic local event; not a real chemical review",
              "source_request_sha256": sha256_file(source), "parent_manifest_sha256": sha256_file(parent_path),
              "segment": {"start_image": 0, "peak_image": 2, "end_image": 4},
              "settings": {"fmax_eV_per_A": 1e-4, "max_steps": 30, "delta0_A": 0.02},
              "limits": {"maximum_evaluations": 200, "maximum_wall_seconds": 60, "maximum_displacement_A": 0.15}}
    write_json_atomic(review_path, review)
    entry_path = tmp_path / "early_request.json"
    entry = prepare_request(source, parent_path, review_path, entry_path)
    entry["execution_authorized"] = True  # Only authorizes this in-process analytic test.
    write_json_atomic(entry_path, entry)
    return entry_path, checkpoint, secondary, source, parent_path


def _change_reviewed(entry_path, field, value):
    entry = load_json_object(entry_path)
    review_path = entry_path.parent / entry["review"]["path"]
    review = load_json_object(review_path)
    entry[field] = value
    review[field] = value
    write_json_atomic(review_path, review)
    entry["review"]["sha256"] = sha256_file(review_path)
    write_json_atomic(entry_path, entry)


def test_real_sella_starts_from_unconverged_multi_peak_path_and_joins_labels(tmp_path, monkeypatch):
    pytest.importorskip("sella")
    entry, checkpoint, secondary, source, parent_path = _entry(tmp_path, monkeypatch)
    before = {path: sha256_file(path) for path in (entry, checkpoint, source, parent_path)}
    parent = load_json_object(parent_path)
    # The unchanged old route still refuses an unconverged/multi-peak parent.
    assert _refine_path_peak([], None, {}, parent, tmp_path)["status"] == "blocked"
    output = tmp_path / "early"
    manifest = run(entry, checkpoint, output, device="cpu", calculator_loader=lambda *args: MultiPeakCalculator())
    assert manifest["optimizer"]["final_converged"] is False
    assert manifest["strict_internal_peak_images"] == ["02", "06"]
    assert manifest["sella_refinement"]["status"] == "needs_work_review"
    result = load_json_object(output / "sella/candidate_manifest.json")
    final = read(output / "sella" / result["last_valid_structure"]["path"])
    assert final.positions[5, 0] == pytest.approx(8.32, abs=1e-4)
    assert result["optimizer_steps"] > 0
    assert result["scientifically_validated_ts"] is False
    assert all(sha256_file(path) == digest for path, digest in before.items())
    manifest_path = output / "dual_model_gpu_ml_neb_path_manifest.candidate.json"
    review_path = tmp_path / "returned_review.json"
    write_json_atomic(review_path, {"document_kind": "dual_model_candidate_work_review", "reviewer": "test",
                                   "candidate_manifest_sha256": sha256_file(manifest_path),
                                   "decision": "accepted_for_force_diagnosis_only"})
    state = prepare_candidate_round(source, manifest_path, review_path, POLICY, tmp_path / "al", method="ml_neb_sella")
    assert "local_peak_entry" in state["source_bindings"]
    prediction = run_batch(Path(state["prediction_batch"]["path"]), checkpoint, secondary, tmp_path / "prediction.json",
                           device="cpu", calculator_loader=lambda *args: MultiPeakCalculator())
    selected = select_samples(prediction["predictions"], boundary_pairs=[], minimum=5, maximum=7)
    assert "sella_final" in {row["sample_id"] for row in selected}
    followup = _sella_followup(state, load_json_object(source))
    assert followup["status"] == "requires_new_path_and_segment_review"
    assert followup["segment"]["peak_image"] == 2
    # An edited old review cannot be reused during a later handoff.
    entry.write_text(entry.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="changed or missing"):
        prepare_candidate_round(source, manifest_path, review_path, POLICY, tmp_path / "bad_al", method="ml_neb_sella")


@pytest.mark.parametrize("segment", [
    {"start_image": 0, "peak_image": 2, "end_image": 8},  # Multiple events/peaks.
    {"start_image": 0, "peak_image": 0, "end_image": 4},  # Endpoint.
    {"start_image": 0, "peak_image": 1, "end_image": 4},  # Not the local peak.
    {"start_image": 0, "peak_image": True, "end_image": 4},
])
def test_invalid_local_segment_is_rejected(tmp_path, monkeypatch, segment):
    entry, *_ = _entry(tmp_path, monkeypatch)
    _change_reviewed(entry, "segment", segment)
    with pytest.raises(ValueError):
        validate_request(entry)


@pytest.mark.parametrize("field,value", [("maximum_evaluations", 0), ("maximum_wall_seconds", True),
                                        ("maximum_displacement_A", float("nan"))])
def test_invalid_limits_rejected(tmp_path, monkeypatch, field, value):
    entry, *_ = _entry(tmp_path, monkeypatch)
    limits = load_json_object(entry)["limits"]
    _change_reviewed(entry, "limits", {**limits, field: value})
    with pytest.raises(ValueError):
        validate_request(entry)


def test_stale_review_and_missing_authority_fail_before_model_load(tmp_path, monkeypatch):
    entry, checkpoint, *_ = _entry(tmp_path, monkeypatch)
    payload = load_json_object(entry)
    payload["execution_authorized"] = False
    write_json_atomic(entry, payload)
    validate_request(entry)  # Preparation/preflight grants no authority.
    with pytest.raises(ValueError, match="authorization"):
        run(entry, checkpoint, tmp_path / "unauthorized", calculator_loader=lambda *args: pytest.fail("loaded model"))
    assert not (tmp_path / "unauthorized").exists()
    payload["settings"]["max_steps"] += 1
    write_json_atomic(entry, payload)
    with pytest.raises(ValueError, match="bind settings"):
        validate_request(entry)


@pytest.mark.parametrize("evaluation_limit, displacement", [(1, 0.15), (200, 0.001)])
def test_budget_or_geometry_stop_preserves_last_valid_seed(tmp_path, monkeypatch, evaluation_limit, displacement):
    pytest.importorskip("sella")
    entry, checkpoint, *_ = _entry(tmp_path, monkeypatch)
    limits = load_json_object(entry)["limits"]
    _change_reviewed(entry, "limits", {**limits, "maximum_evaluations": evaluation_limit,
                                       "maximum_displacement_A": displacement})
    output = tmp_path / "bounded"
    run(entry, checkpoint, output, device="cpu", calculator_loader=lambda *args: MultiPeakCalculator())
    result = load_json_object(output / "sella/candidate_manifest.json")
    assert result["status"] == ("budget_exhausted" if evaluation_limit == 1 else "failed")
    assert result["last_valid_structure"]["path"] == "step_0000.vasp"
    assert result["model_error_assumed"] is False
    receipt = load_json_object(output / "run_record.json")
    assert receipt["model_evaluations"] <= evaluation_limit
    with pytest.raises(FileExistsError):
        run(entry, checkpoint, output, device="cpu", calculator_loader=lambda *args: pytest.fail("loaded model"))


def test_wall_budget_is_checked_after_slow_model_call(monkeypatch):
    from tests.test_ml_sella_candidate import SaddleCalculator, _seed
    times = iter([0, 0, 2])
    monkeypatch.setattr("scripts.ml_sella_candidate.time.monotonic", lambda: next(times))
    atoms = _seed()
    calculator = BudgetCalculator(SaddleCalculator(), 10, 1)
    atoms.calc = calculator
    with pytest.raises(SellaBudgetExhausted, match="after model"):
        atoms.get_forces()
    assert calculator.evaluations == 1


def test_input_bundle_can_move_without_editing_reviewed_sources(tmp_path, monkeypatch):
    entry, *_ = _entry(tmp_path, monkeypatch)
    relocated = tmp_path / "relocated"
    relocated.mkdir()
    shutil.copy2(entry, relocated / entry.name)
    shutil.copytree(entry.parent / "early_request_inputs", relocated / "early_request_inputs")
    payload, paths, *_ = validate_request(relocated / entry.name)
    assert all(relocated in path.parents for path in paths.values())
    assert sha256_file(paths["review"]) == payload["review"]["sha256"]
    assert sha256_file(paths["source_request"]) == payload["source_request"]["sha256"]


def test_checkpoint_and_saved_geometry_are_rechecked_before_loading(tmp_path, monkeypatch):
    entry, checkpoint, *_ = _entry(tmp_path, monkeypatch)
    checkpoint.write_bytes(b"changed-test-model")
    with pytest.raises(ValueError, match="checkpoint SHA-256"):
        run(entry, checkpoint, tmp_path / "new", calculator_loader=lambda *args: pytest.fail("loaded model"))
    payload, paths, _, manifest, *_ = validate_request(entry)
    structure = paths["parent_manifest"].parent / manifest["images"][2]["structure_path"]
    structure.write_bytes(structure.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="structure hash mismatch"):
        validate_request(entry)
    assert payload["execution_authorized"] is True
