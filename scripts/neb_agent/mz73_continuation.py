"""Exact user-authorized CH+CO continuation, retaining per-point VASP gates."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_file, sha256_json
from scripts.ts_strategy_engine.paper_stopping import effective_force_target, validate_authorization


AUTHORIZATION_SHA = "f3f660dba3bf4782641e718fb92d16c014a3f4fb614ee33043eb3ef48dacfebd"
ORIGIN_SHA = "6d13b33b213a40904fb0ee5f32548625979b03597c075a755ab091790db2ce7c"
PROTOCOL_SHA = "f977a873403ceebf9f09e49363599f7a030287411f0fcd387c623747ede955df"
PREFIX = "paper_chco_aqcat25_ft512_20261112_r"
NAMES = tuple(f"{PREFIX}{index:03d}_label" for index in range(2, 250))
LEGACY_NAMES = {f"{PREFIX}000_label", f"{PREFIX}001_label",
                f"{PREFIX}000_launch_recovery01_label", f"{PREFIX}000_timebudget_restart01_label"}
SCOPE = {"authorization_sha256": AUTHORIZATION_SHA, "origin_state_sha256": ORIGIN_SHA,
         "protocol_sha256": PROTOCOL_SHA, "first_round_index": 2, "last_round_index": 249,
         "force_target_eV_per_A": 0.03, "maximum_total_dft_evaluations": 250,
         "time_limit": "01:00:00", "memory": "15G", "automatic_retries": 0}
RESOURCES = {"mpi_ranks": 1, "gpus": 1, "cpus_per_task": 4, "memory": "15G", "time_limit": "01:00:00"}


def validate_scope(backend: dict[str, Any]) -> None:
    scope = backend.get("continuous_active_learning")
    names = set(backend["allowed_workdir_names"])
    if scope is None:
        if names.intersection(NAMES):
            raise ValueError("continuation leaves require the explicit user-authorized scope")
        return
    if sha256_json(scope) != sha256_json(SCOPE) or names != set(NAMES) | LEGACY_NAMES:
        raise ValueError("continuous MZ73 scope differs from the approved force-0.03 experiment")


def authorization(reference: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Recheck raw approval, original state and actual user source bytes."""
    from scripts.neb_agent.mz73_static import _bound_raw_source
    from scripts.ts_strategy_engine.paper_sequential import validate_state

    path = _bound_raw_source(reference)
    if reference["sha256"] != AUTHORIZATION_SHA:
        raise ValueError("another continuation approval was supplied")
    approval = load_json_object(path)
    origin_path = _bound_raw_source(approval["origin_state"])
    if sha256_file(origin_path) != ORIGIN_SHA:
        raise ValueError("continuation origin changed")
    origin = load_json_object(origin_path)
    validate_state(origin)
    target = validate_authorization(origin, approval, ORIGIN_SHA)
    source = _bound_raw_source(approval["source"])
    if source.read_bytes() != base64.b64decode(approval["raw_user_instruction_base64"], validate=True):
        raise ValueError("actual user instruction differs from the bound approval")
    expected = {"backend_id": "mz73_paper_vasp", "observed_hostname": "MZ73",
                "protocol_sha256": PROTOCOL_SHA, "first_evaluation_index": 3,
                "maximum_total_dft_evaluations": 250, "maximum_additional_dft_evaluations": 248,
                "resources": {"training": {"gpus": 1, "cpus_per_task": 4, "memory": "15G", "time_limit": "00:10:00"},
                              "search": {"gpus": 1, "cpus_per_task": 4, "memory": "15G", "time_limit": "00:10:00"},
                              "DFT": RESOURCES}}
    if target != 0.03 or any(sha256_json(approval.get(key)) != sha256_json(value) for key, value in expected.items()):
        raise ValueError("continuation host, budget or stopping target mismatch")
    return approval, origin


def validate_request(workdir: Path, request: dict[str, Any], backend: dict[str, Any]) -> dict[str, Any]:
    from scripts.neb_agent.mz73_static import _bound_raw_source
    from scripts.ts_strategy_engine.paper_sequential import validate_state

    if workdir.name not in NAMES or backend.get("continuous_active_learning") != SCOPE:
        raise ValueError("not an authorized continuous scientific round")
    index = NAMES.index(workdir.name) + 3
    if type(request.get("evaluation_index")) is not int or request["evaluation_index"] != index:
        raise ValueError("continuation workdir and evaluation index differ")
    reference = request.get("execution_budget_authorization")
    approval, _ = authorization(reference)
    state_path = _bound_raw_source(request.get("continuation_state"))
    case = Path(approval["origin_state"]["path"]).resolve(strict=True).parent
    if workdir.resolve(strict=True).parent != case / "labels" or not state_path.is_relative_to(case):
        raise ValueError("continuation state/workdir is outside its authorized case")
    state = load_json_object(state_path)
    validate_state(state)
    if (state["protocol_sha256"] != PROTOCOL_SHA or state["status"] != "awaiting_execution_receipt"
            or state["reserved_dft_slots"] != index or state["completed_label_count"] != index - 1
            or effective_force_target(state) != 0.03
            or state.get("stopping_revision", {}).get("reviewed_authorization", {}).get("artifact_sha256") != AUTHORIZATION_SHA):
        raise ValueError("continuation lacks the exact trained sequential state and active stopping revision")
    expected = state["evaluations"][-1]["request"]
    if any(sha256_json(request.get(key)) != sha256_json(value) for key, value in expected.items()):
        raise ValueError("continuation request does not bind its prepared owner state")
    if backend["time_limit"] != RESOURCES["time_limit"] or backend["memory"] != RESOURCES["memory"]:
        raise ValueError("continuation resource caps changed")
    return {**reference, "source": approval["source"], "protocol_sha256": PROTOCOL_SHA,
            "resources": RESOURCES.copy(), "limits": {"max_dft_jobs": 248, "training_epochs": 100},
            "force_target_eV_per_A": 0.03, "continuation_state": request["continuation_state"]}
