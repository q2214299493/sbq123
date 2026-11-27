from __future__ import annotations

import copy

import shutil

from pathlib import Path

from typing import Any

from scripts.aqcat25_handoff import validate_handoff

from scripts.artifact_io import sha256_file

from .active_learning_common import (
    current_round,
    load_state,
    utc_now,
    write_json,
)

from .active_learning_path_common import _empty_destination


def _copy_structure_ref(
    ref: dict[str, Any], source_root: Path, destination: Path, name: str
) -> dict[str, Any]:
    source = source_root / ref["path"]
    target = destination / "structures" / f"{name}.vasp"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if sha256_file(target) != ref["sha256"]:
        raise ValueError(f"path rerun handoff structure hash mismatch: {name}")
    copied = dict(ref)
    copied["path"] = target.relative_to(destination).as_posix()
    return copied

def prepare_ml_neb_path_rerun(state_path: Path, destination: Path) -> dict[str, Any]:
    state = load_state(state_path)
    current = current_round(state)
    if current["status"] != "awaiting_ml_neb_path_rerun":
        raise ValueError("current round is not ready for an ML-NEB path rerun")
    _empty_destination(destination)
    source_path = Path(current["candidate"]["source_handoff_path"])
    if sha256_file(source_path) != current["candidate"]["source_handoff_sha256"]:
        raise ValueError("source handoff changed before path rerun preparation")
    source = validate_handoff(source_path, root=source_path.parent)
    handoff = copy.deepcopy(source)
    next_index = int(current["round_index"]) + 1
    handoff["handoff_id"] = f"{source['handoff_id']}_path_active_learning_round_{next_index:03d}"
    checkpoint = state["latest_finetuned_checkpoint"]
    handoff["model"]["checkpoint_sha256"] = checkpoint["sha256"]
    handoff["candidate_structure"] = _copy_structure_ref(
        handoff["candidate_structure"], source_path.parent, destination, "candidate"
    )
    transition = handoff["transition_state"]
    transition["initial_structure"] = _copy_structure_ref(
        transition["initial_structure"], source_path.parent, destination, "initial"
    )
    transition["final_structure"] = _copy_structure_ref(
        transition["final_structure"], source_path.parent, destination, "final"
    )
    transition["waypoint_structures"] = [
        _copy_structure_ref(ref, source_path.parent, destination, f"waypoint_{index:02d}")
        for index, ref in enumerate(transition["waypoint_structures"], start=1)
    ]
    handoff_path = write_json(destination / "handoff.json", handoff)
    validate_handoff(handoff_path, root=destination)
    request = {
        "schema_version": 1,
        "document_kind": "aqcat25_ml_neb_path_rerun_request",
        "reaction_id": state["reaction_id"],
        "round_index": next_index,
        "handoff": {"path": "handoff.json", "sha256": sha256_file(handoff_path)},
        "checkpoint": checkpoint,
        "run_settings": current["candidate"]["run_settings"],
        "required_return_document_kind": "gpu_ml_neb_path_manifest",
        "automatic_submission": False,
    }
    request_path = write_json(destination / "path_rerun_request.json", request)
    current["path_rerun"] = {
        "status": "prepared_not_submitted",
        "request_path": str(request_path.resolve()),
        "request_sha256": sha256_file(request_path),
        "handoff_sha256": sha256_file(handoff_path),
    }
    current["status"] = "awaiting_ml_neb_path_rerun_result"
    state["status"] = current["status"]
    state["next_action"] = "review_then_run_full_ML_NEB_path_on_MZ73_and_return_through_work"
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return request
