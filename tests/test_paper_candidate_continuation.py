"""Pure metadata/ASE geometry fixtures; no model is loaded or evaluated."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms

from scripts.artifact_io import sha256_file


SOURCE = Path(__file__).resolve().parents[1] / "archive/chco_paper_aqcat25_20261112/next_candidate.py"
spec = importlib.util.spec_from_file_location("paper_next_candidate", SOURCE)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


@pytest.fixture
def bindings(tmp_path):
    def artifact(name, payload):
        path = tmp_path / name
        path.write_text(json.dumps(payload))
        return {"path": str(path), "sha256": sha256_file(path)}

    checkpoint = tmp_path / "new.pt"
    checkpoint.write_bytes(b"MOCK CHECKPOINT BYTES; never deserialized")
    new = {"path": str(checkpoint), "sha256": sha256_file(checkpoint)}
    previous = {"path": "MOCK_POSCAR", "sha256": "f" * 64}
    initial = artifact("original.json", {"checkpoint": {"sha256": worker.FT512}})
    training = artifact("training.json", {"protocol_sha256": "c" * 64, "base_checkpoint": {"sha256": worker.FT512},
                                          "training_samples": [{"label": {"structure": {"sha256": previous["sha256"]}}}]})
    result_payload = {"document_kind": "aqcat25_paper_single_label_training_result", "status": "completed_candidate_only",
                      "base_checkpoint_sha256": worker.FT512, "protocol_sha256": "c" * 64,
                      "training_request_artifact_sha256": training["sha256"], "checkpoint": new,
                      "production_checkpoint_promotion": False, "scientific_acceptance": False,
                      "training_evidence": {"completed_epochs": 100, "completed_steps": 100, "observed_optimizer_updates": 100,
                                            "optimizer_update_events": [{"step": i, "epoch": float(i)} for i in range(1, 101)]}}
    result = artifact("result.json", result_payload)
    request = {"initial_request": initial, "training_request": training, "training_result": result,
               "previous_candidate": previous, "checkpoint": new, "protocol_sha256": "c" * 64}
    return SimpleNamespace(request=request, common=SimpleNamespace(FT512=worker.FT512, digest=lambda path: sha256_file(Path(path))), result=result_payload)


def test_training_result_has_one_matching_latest_label(bindings):
    original = worker.training_bindings(bindings.request, bindings.common)
    assert original["checkpoint"]["sha256"] == worker.FT512


@pytest.mark.parametrize("change", ["wrong_base", "epochs", "missing_update", "protocol", "wrong_label", "training_raw_bytes", "result_raw_bytes"])
def test_cross_round_or_incomplete_training_cannot_continue(bindings, change):
    case = bindings
    if change == "training_raw_bytes":
        Path(case.request["training_request"]["path"]).write_text("{}")
    elif change == "result_raw_bytes":
        Path(case.request["training_result"]["path"]).write_text("{}")
    elif change == "wrong_label":
        case.request["previous_candidate"]["sha256"] = "0" * 64
    else:
        if change == "wrong_base":
            case.result["base_checkpoint_sha256"] = "0" * 64
        elif change == "epochs":
            case.result["training_evidence"]["completed_epochs"] = 99
        elif change == "missing_update":
            case.result["training_evidence"]["optimizer_update_events"].pop()
        else:
            case.result["protocol_sha256"] = "0" * 64
        path = Path(case.request["training_result"]["path"])
        path.write_text(json.dumps(case.result))
        case.request["training_result"]["sha256"] = sha256_file(path)
    with pytest.raises(ValueError):
        worker.training_bindings(case.request, case.common)


@pytest.fixture
def geometries():
    previous = Atoms("Fe45C2OH", positions=np.arange(147).reshape(49, 3) / 100, cell=np.eye(3) * 20, pbc=True)
    previous.set_constraint(FixAtoms(indices=range(18)))
    initial = previous.copy()
    initial.positions[45:, 0] += 1.0  # Original IS differs; continuation must not reset to it.
    frame = previous.copy()
    frame.info.update(bonds_TS=[[45, 46, "form"]], mode_TS=np.zeros((49, 3)))
    frame.info["mode_TS"][45, 0] = 1.0
    original = {"fixed_indices_zero_based": list(range(18)), "reaction": {"bonds": [[45, 46, "form"]],
                                                                         "adsorbate_indices": [45, 46, 47, 48]}}
    geometry_calls = []

    def geometry(atoms, reference, request):
        geometry_calls.append((atoms, reference, request))

    def context(atoms, bonds, indices, spin, low):
        atoms.info.update(bonds_TS=bonds, indices_ads=indices, is_spin_off=spin, is_low_fi=low)

    common = SimpleNamespace(fixed=lambda atoms: sorted(int(i) for c in atoms.constraints for i in c.get_indices()),
                             geometry=geometry, pilot=SimpleNamespace(validate_reaction_metadata=lambda *args: None,
                                                                        add_model_context=context))
    return SimpleNamespace(previous=previous, frame=frame, initial=initial, original=original, common=common, calls=geometry_calls)


def test_geometry_is_previous_frame_not_original_idpp_or_initial_state(geometries):
    case = geometries
    case.frame.positions[45, 0] += 1.8e-15
    guess = worker.continuation_geometry(case.previous, case.frame, case.initial, case.original, case.common)
    assert np.array_equal(guess.positions, case.frame.positions)
    assert not np.array_equal(guess.positions, case.initial.positions)
    assert np.array_equal(guess.info["mode_TS"], case.frame.info["mode_TS"])
    assert guess.info["bonds_TS"] == case.original["reaction"]["bonds"]
    guess.positions[45, 0] += 0.1
    assert not np.array_equal(guess.positions, case.frame.positions)
    assert len(case.calls) == 1 and case.calls[0][1] is case.initial


@pytest.mark.parametrize("change", ["position", "cell", "SD", "mode_shape", "mode_nan", "mode_fixed", "mode_zero", "bond"])
def test_inconsistent_geometry_or_mode_is_rejected(geometries, change):
    case = geometries
    if change == "position":
        case.frame.positions[45, 0] += 1e-4
    elif change == "cell":
        case.frame.cell[0, 0] += 1e-4
    elif change == "SD":
        case.frame.set_constraint(FixAtoms(indices=range(17)))
    elif change == "mode_shape":
        case.frame.info["mode_TS"] = np.zeros((48, 3))
    elif change == "mode_nan":
        case.frame.info["mode_TS"][45, 0] = float("nan")
    elif change == "mode_fixed":
        case.frame.info["mode_TS"][0, 0] = 1.0
    elif change == "mode_zero":
        case.frame.info["mode_TS"] *= 0
    else:
        case.frame.info["bonds_TS"] = [[45, 47, "form"]]
    with pytest.raises(ValueError):
        worker.continuation_geometry(case.previous, case.frame, case.initial, case.original, case.common)
