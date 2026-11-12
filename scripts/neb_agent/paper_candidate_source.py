"""Read-only local provenance for one paper-sequential candidate continuation.

Remote JSON bytes are never rewritten. Model weights are identified by the
bound training/worker receipts, not downloaded or scientifically calibrated.
The returned effective view is not a replacement request or execution permit.
"""
from __future__ import annotations

import base64
import copy
import json
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np

from scripts.artifact_io import load_json_object, require_sha256, sha256_bytes, sha256_file


FROZEN_BASE = "cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0"
BINDING_KIND = "paper_candidate_local_source_binding"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _previous_geometry(previous: Path, trajectory: Path, original_is: Path, control: dict) -> None:
    from ase.io import read
    from scripts.aqcat25_ml_neb import _fixed_indices

    atoms, frame, initial = read(previous, format="vasp"), read(trajectory, index=-1, format="traj"), read(original_is, format="vasp")
    _require(len(atoms) == len(frame) == len(initial) == 49 and
             atoms.get_chemical_symbols() == frame.get_chemical_symbols() == initial.get_chemical_symbols(), "previous frame atom identity mismatch")
    _require(_fixed_indices(atoms) == _fixed_indices(frame) == control["fixed_indices_zero_based"], "previous frame SD mask mismatch")
    _require(np.array_equal(atoms.pbc, frame.pbc) and np.allclose(atoms.cell, frame.cell, atol=1e-12, rtol=0)
             and np.allclose(atoms.positions, frame.positions, atol=1e-12, rtol=0), "previous trajectory/POSCAR mismatch")
    mode = np.asarray(frame.info.get("mode_TS"), dtype=float)
    _require(mode.shape == (49, 3) and np.isfinite(mode).all() and np.any(mode != 0)
             and np.all(mode[_fixed_indices(frame)] == 0), "invalid previous mode_TS")
    bonds = [[int(row[0]), int(row[1]), str(row[2])] for row in frame.info.get("bonds_TS", [])]
    _require(bonds == control["reaction"]["bonds"], "previous trajectory bond metadata changed")


def resolve_continuation_source(
    binding_path: Path, *, binding_sha256: str, candidate_path: Path,
    initial_structure_path: Path, expected_protocol_sha256: str, contract: dict[str, Any],
) -> dict[str, Any]:
    """Return effective_request/dependency_paths/source_binding, without writes.

    Binding shape: document_kind, protocol_sha256, continuation_request/report
    and candidate local {path,sha256} refs, plus source_map entries containing
    {source_path,path,sha256}. source_path is the exact original JSON path text.
    Every actually read remote metadata/code/structure/trajectory must be mapped.
    """
    binding_path = Path(binding_path).resolve(strict=True)
    dependencies: dict[Path, str] = {}

    def local(ref: dict) -> Path:
        _require(isinstance(ref, dict) and set(ref) == {"path", "sha256"}, "invalid local source descriptor")
        path = Path(ref["path"])
        path = (path if path.is_absolute() else binding_path.parent / path).resolve(strict=True)
        digest = require_sha256(ref["sha256"], label="candidate source")
        _require(path.is_file() and sha256_file(path) == digest, "local source bytes changed")
        _require(path not in dependencies or dependencies[path] == digest, "conflicting source identities")
        dependencies[path] = digest
        return path

    local({"path": str(binding_path), "sha256": binding_sha256})
    binding = load_json_object(binding_path)
    protocol = require_sha256(expected_protocol_sha256, label="paper protocol")
    _require(binding.get("document_kind") == BINDING_KIND and binding.get("protocol_sha256") == protocol, "candidate binding/protocol mismatch")
    mapping = {}
    for entry in binding["source_map"]:
        _require(set(entry) == {"source_path", "path", "sha256"} and isinstance(entry["source_path"], str)
                 and entry["source_path"] not in mapping, "duplicate/invalid local source mapping")
        mapping[entry["source_path"]] = {"path": entry["path"], "sha256": entry["sha256"]}

    def mapped(ref: dict) -> Path:
        _require(isinstance(ref, dict) and set(ref) == {"path", "sha256"} and ref["path"] in mapping, "raw source has no explicit local mapping")
        descriptor = mapping[ref["path"]]
        _require(descriptor["sha256"] == ref["sha256"], "mapped/raw source SHA mismatch")
        return local(descriptor)

    request_path, report_path = local(binding["continuation_request"]), local(binding["continuation_report"])
    request, report = load_json_object(request_path), load_json_object(report_path)
    _require(request.get("document_kind") == "paper_sequential_candidate_continuation_request"
             and request.get("protocol_sha256") == report.get("protocol_sha256") == protocol, "continuation request/report protocol mismatch")
    _require(report.get("request_sha256") == binding["continuation_request"]["sha256"]
             and report.get("status") == "prediction_completed_pending_review"
             and report.get("result_class") == "predicted_candidate_only", "continuation report is not a completed prediction")
    for key in ("DFT_performed", "training_performed", "scientifically_accepted", "IDPP_performed"):
        _require(report.get(key) is False, "candidate report overclaims stage or acceptance")
    _require(report.get("geometry_initialization") == "previous_trajectory_last_frame" and report.get("previous_mode_retained") is True
             and report.get("optimizer_converged") is True and report.get("optimizer_status") == "finished"
             and report.get("calculator_failure") is None, "candidate continuation/optimizer evidence failed")
    _require(report.get("cuda", {}).get("available") is True and report["cuda"].get("device_count") == 1
             and report.get("model_devices") and all(str(device).startswith("cuda:") for device in report["model_devices"]), "worker did not record CUDA-only inference")
    force = report.get("predicted_movable_fmax_eV_per_A")
    _require(type(force) in (int, float) and np.isfinite(force) and 0 <= force <= 0.01, "candidate ML force convergence failed")
    _require(report.get("ba_sella") == {"fmax": 0.01, "min_steps": 10, "max_steps": 1000, "eta": 0.01,
                                      "gamma": 0.05, "delta0": 0.05, "dot_prod_thr": 0.5, "nsteps_per_diag": 1}, "BA-Sella protocol changed")
    keys = ("initial_request", "training_request", "training_result", "checkpoint", "previous_candidate", "previous_trajectory")
    _require(report.get("input_bindings") == {key: request[key] for key in keys}, "worker report/input binding mismatch")
    _require(report.get("source_files") == request["source_files"], "worker code source manifest mismatch")
    names = {PurePosixPath(ref["path"].replace("\\", "/")).name for ref in request["source_files"]}
    _require({"next_candidate.py", "initial_candidate.py", "aqcat_ts_pilot.py", "mlip_same_structure_benchmark.py",
              "artifact_io.py", "calculations.py"} <= names, "worker implementation source manifest is incomplete")
    for ref in request["source_files"]:
        mapped(ref)
    original = load_json_object(mapped(request["initial_request"]))
    training = load_json_object(mapped(request["training_request"]))
    result = load_json_object(mapped(request["training_result"]))
    _require(original["checkpoint"]["sha256"] == training["base_checkpoint"]["sha256"] == result["base_checkpoint_sha256"] == FROZEN_BASE,
             "training did not reset the frozen FT512 base")
    _require(training.get("document_kind") == "paper_sequential_training_request"
             and training["protocol_sha256"] == result["protocol_sha256"] == protocol
             and result.get("document_kind") == "aqcat25_paper_single_label_training_result"
             and result.get("status") == "completed_candidate_only", "training request/result identity mismatch")
    _require(result["training_request_artifact_sha256"] == request["training_request"]["sha256"], "training raw request mismatch")
    checkpoint = request["checkpoint"]
    _require(require_sha256(checkpoint["sha256"], label="trained checkpoint") != FROZEN_BASE
             and checkpoint == result["checkpoint"], "trained checkpoint identity mismatch")
    _require(result.get("production_checkpoint_promotion") is False and result.get("scientific_acceptance") is False, "training result overclaims acceptance")
    evidence = result["training_evidence"]
    _require(all(evidence.get(key) == 100 for key in ("completed_epochs", "completed_steps", "observed_optimizer_updates"))
             and evidence.get("optimizer_update_events") == [{"step": i, "epoch": float(i)} for i in range(1, 101)], "100 actual training updates are not recorded")
    for key in ("reset_model_weights", "reset_optimizer_state", "reset_scheduler_state", "reset_amp_state", "reset_ema_state"):
        _require(training.get(key) is True, "training state was not reset")
    settings = training["training"]
    _require(training.get("checkpoint_selection") == "final_epoch_only" and settings.get("initial_learning_rate") == 1e-4
             and settings.get("scheduler") == "cosine" and settings.get("target") == "forces_only"
             and settings.get("epochs") == 100 and settings.get("energy_loss_coefficient") == 0.0
             and all(settings.get(key) is False for key in ("train_on_all", "train_finetuned", "replay", "validation_epoch_selection")), "not single-label force-only training")
    samples = training["training_samples"]
    _require(len(samples) == 1 and samples[0]["label"]["structure"]["sha256"] == request["previous_candidate"]["sha256"], "training/previous candidate mismatch")
    raw = base64.b64decode(samples[0]["raw_label_base64"], validate=True)
    _require(sha256_bytes(raw) == samples[0]["artifact_sha256"], "training label original bytes changed")
    _require(json.loads(raw) == samples[0]["label"], "training parsed label differs from its original bytes")
    previous, trajectory = mapped(request["previous_candidate"]), mapped(request["previous_trajectory"])
    initial = mapped(original["initial"])
    _require(sha256_file(initial_structure_path) == original["initial"]["sha256"], "original IS source mismatch")
    for key in ("contract_sha256", "compatibility_sha256", "atom_map_sha256"):
        _require(original["reaction"][key] == contract[key], "original reaction contract mismatch")
    _require(original["fixed_indices_zero_based"] == contract["compatibility"]["fixed_atom_indices_zero_based"], "original fixed mask mismatch")
    _require(report.get("fixed_indices_zero_based") == original["fixed_indices_zero_based"], "worker fixed mask mismatch")
    guard = mapped(original["geometry_guard_source"])
    guards = load_json_object(guard)["geometry_guards"]
    expected_bonds = [{"name": row["name"], "atoms": row["atoms_zero_based"],
                       "minimum_A": row.get("hard_minimum_A", row["minimum_A"]), "maximum_A": row.get("hard_maximum_A", row["maximum_A"]),
                       "soft_minimum_A": row["minimum_A"], "soft_maximum_A": row["maximum_A"]} for row in guards["preserved_bonds"]]
    _require(original["geometry"]["minimum_pair_distance_A"] == guards["minimum_pair_distance_A"]
             and original["geometry"]["preserved_bonds"] == expected_bonds, "original geometry guards changed")
    _previous_geometry(previous, trajectory, initial, original)
    local(binding["candidate"])
    output = report.get("output_candidate")
    _require(isinstance(output, dict) and set(output) == {"path", "sha256"}
             and isinstance(output["path"], str) and bool(output["path"])
             and require_sha256(output["sha256"], label="worker output candidate") == binding["candidate"]["sha256"],
             "worker report output and returned candidate differ")
    _require(sha256_file(candidate_path) == binding["candidate"]["sha256"], "new candidate is not the reviewed returned bytes")
    dependencies[Path(candidate_path).resolve(strict=True)] = binding["candidate"]["sha256"]
    dependencies[Path(initial_structure_path).resolve(strict=True)] = original["initial"]["sha256"]
    _require(all(sha256_file(path) == digest for path, digest in dependencies.items()), "source changed during provenance review")
    view = copy.deepcopy(original)
    view["checkpoint"] = copy.deepcopy(checkpoint)
    view["initial"] = {"path": str(initial), "sha256": original["initial"]["sha256"]}
    view["geometry_guard_source"] = {"path": str(guard), "sha256": original["geometry_guard_source"]["sha256"]}
    return {"effective_request": view, "dependency_paths": [*dependencies, Path(__file__).resolve()],
            "source_binding": {"kind": BINDING_KIND, "path": str(binding_path), "sha256": binding_sha256,
                               "protocol_sha256": protocol, "candidate_sha256": binding["candidate"]["sha256"],
                               "checkpoint_sha256": checkpoint["sha256"], "checkpoint_bytes_downloaded": False,
                               "submission_allowed": False, "model_scientifically_calibrated": False}}
