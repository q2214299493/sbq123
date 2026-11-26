from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.constraints import FixAtoms, FixCartesian
from ase.io import read, write

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.ml_sella_candidate import refine_peak, validate_settings
from scripts.dual_model_ml_neb import _load_request, run_dual_model_request
from scripts.dual_model_ts_force_prediction_batch import run_batch
from scripts.prepare_ml_candidate_active_learning import prepare_candidate_round
from scripts.select_dual_model_ts_vasp_labels import prepare_vasp_labels, select_samples
from scripts.assess_dual_model_ts_vasp_errors import assess
from scripts.prepare_ml_candidate_rerun import prepare_rerun
from tests.test_dual_model_ml_neb import PathCalculator, _fixture

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "configs/dual_model_ts_active_learning.yaml"
SETTINGS = {"fmax_eV_per_A": 1e-5, "max_steps": 40, "delta0_A": 0.05}


class SaddleCalculator(Calculator):
    """Analytic test surface, not a material model or a DFT result."""
    implemented_properties = ["energy", "forces"]

    def calculate(self, atoms=None, properties=("energy", "forces"), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        x, y, z = atoms.positions[1] - [3, 1, 1]
        forces = np.zeros((2, 3))
        forces[0] = [5, 5, 5]  # Fixed atoms must not contaminate convergence.
        forces[1] = [2*x - 0.8*x**3, -2*y, -2*z]
        self.results = {"energy": -x*x + 0.2*x**4 + y*y + z*z, "forces": forces}


def _seed():
    atoms = Atoms("FeH", positions=[[0, 0, 0], [3.2, 1.1, 1.1]], cell=[10]*3, pbc=True)
    atoms.set_constraint(FixAtoms(indices=[0]))
    return atoms


def test_real_sella_finds_analytic_saddle_preserves_fixed_cell_and_restart(tmp_path):
    pytest.importorskip("sella")
    seed = _seed()
    before = seed.positions.copy()
    result = refine_peak(seed, SaddleCalculator(), SETTINGS, tmp_path / "sella", source={},
                         geometry_check=lambda atoms: {"passed": True})
    assert result["status"] == "needs_work_review", result
    assert result["optimizer_converged"] is True
    assert result["scientifically_validated_ts"] is False
    last = result["last_valid_structure"]
    final = read(tmp_path / "sella" / last["path"])
    assert np.allclose(final.positions[1], [3, 1, 1], atol=1e-4)
    assert np.array_equal(seed.positions, before)
    assert np.allclose(final.cell, seed.cell)
    assert final.constraints[0].get_indices().tolist() == [0]
    assert last["fmax_eV_per_A"] <= SETTINGS["fmax_eV_per_A"]
    # Resume coordinates in a new directory, never overwrite the earlier record.
    resumed = refine_peak(final, SaddleCalculator(), SETTINGS, tmp_path / "resumed", source={},
                          geometry_check=lambda atoms: {"passed": True})
    assert resumed["status"] == "needs_work_review"


def test_real_sella_records_geometry_failure_and_last_valid_iterate(tmp_path):
    pytest.importorskip("sella")
    result = refine_peak(_seed(), SaddleCalculator(), SETTINGS, tmp_path / "sella", source={},
                         geometry_check=lambda atoms: {"passed": bool(atoms.positions[1, 0] >= 3.19)})
    assert result["status"] == "failed"
    assert result["last_valid_structure"]["path"] == "step_0000.vasp"
    assert result["model_error_assumed"] is False
    assert result["failed_geometry"]["passed"] is False


@pytest.mark.parametrize("change", [{"max_steps": True}, {"delta0_A": float("nan")},
                                    {"fmax_eV_per_A": 0}, {"internal": True}, {"order": 0}])
def test_invalid_settings_rejected(change):
    with pytest.raises(ValueError):
        validate_settings({**SETTINGS, **change})


def test_partial_selective_dynamics_rejected_without_discarding_mask(tmp_path):
    pytest.importorskip("sella")
    atoms = _seed()
    atoms.set_constraint(FixCartesian(0, mask=[True, False, True]))
    with pytest.raises(ValueError, match="full-atom"):
        refine_peak(atoms, SaddleCalculator(), SETTINGS, tmp_path / "sella", source={},
                    geometry_check=lambda atoms: {"passed": True})
    assert not (tmp_path / "sella").exists()


def _path_run(tmp_path, monkeypatch, *, sella=True):
    request_path, primary, secondary = _fixture(tmp_path)
    request = load_json_object(request_path)
    request["reaction"]["reaction_id"] = "test-reaction"
    seed = read(tmp_path / request["images"][0]["path"])
    request["images"] = []
    for index in range(9):
        atoms = seed.copy()
        atoms.positions[5, 0] = 8.6 - index * 0.125
        path = tmp_path / "structures" / f"{index:02d}.vasp"
        write(path, atoms, format="vasp")
        request["images"].append({"image": f"{index:02d}", "path": f"structures/{index:02d}.vasp", "sha256": sha256_file(path)})
    for role in request["models"]:
        request["models"][role]["remote_checkpoint_path"] = f"/home/sbq/sbq/{role}.pt"
    if sella:
        request["sella_refinement"] = SETTINGS
    write_json_atomic(request_path, request)
    monkeypatch.setattr("scripts.dual_model_ml_neb.require_sella", lambda: None)

    def test_refinement(seed, calculator, settings, output, *, source, geometry_check):
        output.mkdir()
        atoms = seed.copy()
        atoms.positions[5, 0] += 0.02
        assert geometry_check(atoms)["passed"]
        assert isinstance(calculator, PathCalculator)
        write(output / "final.vasp", atoms, format="vasp")
        manifest = {"document_kind": "ml_sella_candidate_manifest", "source": source,
                    "status": "needs_work_review", "scientifically_validated_ts": False,
                    "last_valid_structure": {"path": "final.vasp", "sha256": sha256_file(output / "final.vasp")}}
        write_json_atomic(output / "candidate_manifest.json", manifest)
        return manifest

    monkeypatch.setattr("scripts.dual_model_ml_neb.refine_peak", test_refinement)
    output = tmp_path / "run"
    manifest = run_dual_model_request(request_path, primary, secondary, output, device="cpu",
                                      calculator_loader=lambda backend, path, device: PathCalculator(0))
    manifest_path = output / "dual_model_gpu_ml_neb_path_manifest.candidate.json"
    review_path = tmp_path / "review.json"
    write_json_atomic(review_path, {"document_kind": "dual_model_candidate_work_review", "reviewer": "test-fixture",
                                   "candidate_manifest_sha256": sha256_file(manifest_path),
                                   "decision": "accepted_for_force_diagnosis_only"})
    return request_path, primary, secondary, manifest_path, review_path, manifest


@pytest.mark.parametrize("method", ["ml_neb", "ml_neb_sella"])
def test_both_candidates_join_existing_prediction_and_selection(tmp_path, monkeypatch, method):
    request, primary, secondary, manifest, review, payload = _path_run(tmp_path, monkeypatch, sella=method.endswith("sella"))
    destination = tmp_path / "learning"
    state = prepare_candidate_round(request, manifest, review, POLICY, destination, method=method)
    assert state["automatic_submission"] is False
    assert state["round_trigger"]["model_error_assumed"] is False
    result = run_batch(Path(state["prediction_batch"]["path"]), primary, secondary, tmp_path / "predictions.json",
                       device="cpu", calculator_loader=lambda backend, path, device: PathCalculator(0))
    selected = select_samples(result["predictions"], boundary_pairs=[], minimum=5, maximum=7)
    assert 5 <= len(selected) <= 7
    if method.endswith("sella"):
        assert "sella_final" in {row["sample_id"] for row in selected}
        assert payload["sella_refinement"]["status"] == "needs_work_review"
    else:
        assert "sella_refinement" not in payload


def test_optional_dependency_fails_before_loading_calculators(tmp_path, monkeypatch):
    request, primary, secondary = _fixture(tmp_path)
    payload = load_json_object(request)
    payload["sella_refinement"] = SETTINGS
    write_json_atomic(request, payload)
    def missing():
        raise RuntimeError("Sella unavailable")
    monkeypatch.setattr("scripts.dual_model_ml_neb.require_sella", missing)
    with pytest.raises(RuntimeError, match="unavailable"):
        run_dual_model_request(request, primary, secondary, tmp_path / "run", device="cpu",
                              calculator_loader=lambda *args: pytest.fail("model must not load"))
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("mutation", ["checkpoint", "geometry", "review", "file"])
def test_candidate_bridge_rejects_stale_or_failed_evidence(tmp_path, monkeypatch, mutation):
    request, _, _, manifest, review, payload = _path_run(tmp_path, monkeypatch)
    if mutation == "checkpoint":
        payload["models"]["primary"]["checkpoint_sha256"] = "f" * 64
    elif mutation == "geometry":
        payload["geometry_guards"]["passed"] = False
    elif mutation == "review":
        review.write_text("{}")
    else:
        (manifest.parent / payload["images"][3]["structure_path"]).write_text("changed")
    if mutation in {"checkpoint", "geometry"}:
        write_json_atomic(manifest, payload)
        rev = load_json_object(review)
        rev["candidate_manifest_sha256"] = sha256_file(manifest)
        write_json_atomic(review, rev)
    with pytest.raises(ValueError):
        prepare_candidate_round(request, manifest, review, POLICY, tmp_path / "learning", method="ml_neb_sella")
    assert not (tmp_path / "learning").exists()


def test_unknown_sella_request_option_fails_during_preflight(tmp_path):
    request, _, _ = _fixture(tmp_path)
    payload = load_json_object(request)
    payload["sella_refinement"] = {**SETTINGS, "order": 0}
    request.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="exactly"):
        _load_request(request)


@pytest.mark.parametrize("force_error,valid_label", [(0.0, True), (1.0, True), (1.0, False)])
def test_sella_labels_use_existing_error_gate(tmp_path, monkeypatch, force_error, valid_label):
    request, primary, secondary, manifest, review, _ = _path_run(tmp_path, monkeypatch)
    destination = tmp_path / "learning"
    state = prepare_candidate_round(request, manifest, review, POLICY, destination, method="ml_neb_sella")
    state_path = destination / "active_learning_state.json"
    predictions_path = tmp_path / "predictions.json"
    predictions = run_batch(Path(state["prediction_batch"]["path"]), primary, secondary, predictions_path,
                            device="cpu", calculator_loader=lambda *args: PathCalculator(0))
    # VASP execution is outside this local integration test.
    monkeypatch.setattr("scripts.select_dual_model_ts_vasp_labels.build_fe110_active_learning_force_label",
                        lambda *args, **kwargs: {"test_fixture": True})
    batch = prepare_vasp_labels(state_path, predictions_path, tmp_path / "labels",
                                profile_path=ROOT / "configs/true_fe110_production.yaml")
    assert "sella_final" in {row["sample_id"] for row in batch["labels"]}
    by_id = {row["sample_id"]: row for row in predictions["predictions"]}
    state = load_json_object(state_path)
    labels = []
    for selected in batch["labels"]:
        row = by_id[selected["sample_id"]]
        forces = np.asarray(row["primary_forces_eV_per_A"])
        forces[1, 0] += force_error
        labels.append({"sample_id": selected["sample_id"], "structure_sha256": row["structure_sha256"],
                       "vasp_energy_eV": row["primary_energy_eV"], "vasp_forces_eV_per_A": forces.tolist(),
                       "acceptance_evidence": {key: valid_label for key in (
                           "scheduler_DONE", "normal_vasp_completion", "electronically_converged",
                           "complete_atom_aligned_force_block", "total_magnetic_moment_available",
                           "atom_resolved_magnetic_moments_available", "sigma_0p20_compatibility")}})
    label_path = tmp_path / "test_labels.json"
    write_json_atomic(label_path, {"document_kind": "dual_model_ts_vasp_force_label_set", "labels": labels,
                                   "source_batch_sha256": state["vasp_label_batch"]["sha256"]})
    state["status"] = "awaiting_completed_VASP_force_labels"
    write_json_atomic(state_path, state)
    if not valid_label:
        with pytest.raises(ValueError, match="incomplete"):
            assess(state_path, label_path, tmp_path / "assessment.json")
        return
    result = assess(state_path, label_path, tmp_path / "assessment.json")
    assert result["models"]["matris_primary"]["screening_passed"] is (force_error == 0)
    assert result["calibrated_active_learning_acceleration"] is False
    assert result["decision"].startswith("fine_tune" if force_error else "retain")


def _rerun_fixture(tmp_path, monkeypatch):
    request, primary, _, manifest, review, _ = _path_run(tmp_path, monkeypatch)
    directory = tmp_path / "learning"
    state = prepare_candidate_round(request, manifest, review, POLICY, directory, method="ml_neb_sella")
    def bound(name, data):
        path = tmp_path / name
        write_json_atomic(path, data)
        return {"path": str(path), "sha256": sha256_file(path)}
    state["status"] = "awaiting_energy_force_aware_MatRIS_fine_tuning"
    state["vasp_error_assessment"] = bound("assessment.json", {
        "decision": "fine_tune_MatRIS_then_require_new_checkpoint_and_complete_path_rerun",
        "reaction_id": "test-reaction", "round_index": 0,
        "models": {"matris_primary": {"checkpoint_sha256": sha256_file(primary)}}})
    checkpoint = tmp_path / "new.pth.tar"
    checkpoint.write_bytes(b"new-test-checkpoint")
    result_ref = bound("heldout.json", {"test_fixture": True})
    heldout = bound("heldout_review.json", {
        "candidate_checkpoint": {"sha256": sha256_file(checkpoint), "strict_reload_passed": True, "all_parameters_finite": True},
        "source_result": result_ref})
    heldout["status"] = "PASS"
    retention = bound("retention.json", {"test_fixture": True})
    retention["status"] = "SOFT_WARNING"
    promotion = {"document_kind": "matris_checkpoint_promotion", "status": "promoted_for_current_test_candidate",
                 "scope": {"reaction_id": "test-reaction", "result_class": "predicted_path_candidate_only"},
                 "base_checkpoint_overwrite": False,
                 "checkpoint": {"local_path": str(checkpoint), "sha256": sha256_file(checkpoint), "remote_path": "/home/sbq/sbq/new.pt"},
                 "basis": {"tiered_adsorption_retention_review": retention, "frozen_TS_heldout_review": heldout,
                           "frozen_TS_heldout_result": result_ref, "active_policy": state["source_bindings"]["policy"]}}
    state_path = directory / "active_learning_state.json"
    write_json_atomic(state_path, state)
    promotion_path = tmp_path / "promotion.json"
    write_json_atomic(promotion_path, promotion)
    return state_path, promotion_path, request


def test_new_checkpoint_rerun_preserves_entire_path_and_sella(tmp_path, monkeypatch):
    state, promotion, source = _rerun_fixture(tmp_path, monkeypatch)
    source_hash, state_hash = sha256_file(source), sha256_file(state)
    receipt = prepare_rerun(state, promotion, tmp_path / "rerun")
    rerun = _load_request(tmp_path / "rerun/request.json")
    original = _load_request(source)
    assert receipt["automatic_submission"] is False
    assert receipt["round_index"] == 1
    assert rerun["sella_refinement"] == original["sella_refinement"]
    assert [row["sha256"] for row in rerun["images"]] == [row["sha256"] for row in original["images"]]
    assert rerun["models"]["primary"]["checkpoint_sha256"] != original["models"]["primary"]["checkpoint_sha256"]
    assert sha256_file(source) == source_hash and sha256_file(state) == state_hash


@pytest.mark.parametrize("mutation", ["same_checkpoint", "heldout_fail", "stale", "budget", "checkpoint_binding"])
def test_rerun_rejects_invalid_training_or_acceptance(tmp_path, monkeypatch, mutation):
    state_path, promotion_path, source_path = _rerun_fixture(tmp_path, monkeypatch)
    state, promotion = load_json_object(state_path), load_json_object(promotion_path)
    if mutation == "same_checkpoint":
        source = load_json_object(source_path)
        source["models"]["primary"]["checkpoint_sha256"] = promotion["checkpoint"]["sha256"]
        write_json_atomic(source_path, source)
        state["source_bindings"]["source_request"]["sha256"] = sha256_file(source_path)
    elif mutation == "heldout_fail":
        promotion["basis"]["frozen_TS_heldout_review"]["status"] = "FAIL"
    elif mutation == "stale":
        Path(promotion["basis"]["frozen_TS_heldout_result"]["path"]).write_text("changed")
    elif mutation == "budget":
        state["round_index"] = 4
        assessment_ref = state["vasp_error_assessment"]
        assessment_path = Path(assessment_ref["path"])
        assessment = load_json_object(assessment_path)
        assessment["round_index"] = 4
        write_json_atomic(assessment_path, assessment)
        assessment_ref["sha256"] = sha256_file(assessment_path)
    else:
        heldout_ref = promotion["basis"]["frozen_TS_heldout_review"]
        heldout_path = Path(heldout_ref["path"])
        heldout = load_json_object(heldout_path)
        heldout["candidate_checkpoint"]["sha256"] = "f" * 64
        write_json_atomic(heldout_path, heldout)
        heldout_ref["sha256"] = sha256_file(heldout_path)
    write_json_atomic(state_path, state)
    write_json_atomic(promotion_path, promotion)
    with pytest.raises(ValueError):
        prepare_rerun(state_path, promotion_path, tmp_path / "rerun")
    assert not (tmp_path / "rerun").exists()
