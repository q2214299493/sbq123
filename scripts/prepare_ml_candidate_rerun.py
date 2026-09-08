"""Prepare a reviewed checkpoint's full-path rerun, preserving the Sella choice."""
from __future__ import annotations

import argparse
import copy
import json
import shutil
from pathlib import Path

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.dual_model_ml_neb import _load_images, _load_request
from scripts.execution_backends import require_gpu_write_path
from scripts.matris_sella_local_peak import validate_request as validate_local_peak_request
from scripts.prepare_matris_finetune_request import FINE_TUNE_DECISION, FINE_TUNE_STATUS


def _bound(ref):
    path = Path(ref["path"])
    if not path.is_file() or sha256_file(path) != ref["sha256"]:
        raise ValueError("rerun source evidence changed or missing")
    return path


def _sella_followup(state, source):
    early_ref = state["source_bindings"].get("local_peak_entry")
    if early_ref:
        early = validate_local_peak_request(_bound(early_ref))[0]
        if early["source_request"]["sha256"] != state["source_bindings"]["source_request"]["sha256"]:
            raise ValueError("early Sella rerun source mismatch")
        return {"status": "requires_new_path_and_segment_review", "previous_entry": early_ref,
                **{key: early[key] for key in ("segment", "settings", "limits")}}
    if state.get("candidate_method") == "ml_neb_sella" and "sella_refinement" not in source:
        raise ValueError("Sella method would be lost from the rerun")
    return None


def prepare_rerun(state_path, promotion_path, destination):
    state = load_json_object(state_path)
    if state.get("document_kind") != "dual_model_ts_active_learning_state" or state.get("status") != FINE_TUNE_STATUS:
        raise ValueError("rerun requires an active-learning fine-tuning decision")
    assessment = load_json_object(_bound(state["vasp_error_assessment"]))
    if (assessment.get("decision") != FINE_TUNE_DECISION
            or assessment.get("reaction_id") != state["reaction_id"]
            or assessment.get("round_index") != state["round_index"]):
        raise ValueError("rerun assessment binding mismatch")
    source_path = _bound(state["source_bindings"]["source_request"])
    source = _load_request(source_path)
    _load_images(source, source_path.parent)
    policy_path = _bound(state["source_bindings"]["policy"])
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    round_index = state["round_index"] + 1
    if round_index >= policy["round_control"]["maximum_rounds"]:
        raise ValueError("active-learning round budget exhausted")
    promotion = load_json_object(promotion_path)
    if (promotion.get("document_kind") != "matris_checkpoint_promotion"
            or not str(promotion.get("status", "")).startswith("promoted_for_current_")
            or promotion.get("scope", {}).get("reaction_id") != state["reaction_id"]
            or promotion.get("scope", {}).get("result_class") != "predicted_path_candidate_only"
            or promotion.get("base_checkpoint_overwrite") is not False):
        raise ValueError("an existing task-scoped checkpoint promotion is required")
    basis = promotion["basis"]
    for name in ("tiered_adsorption_retention_review", "frozen_TS_heldout_review", "frozen_TS_heldout_result", "active_policy"):
        _bound(basis[name])
    if (basis["tiered_adsorption_retention_review"].get("status") not in {"PASS", "SOFT_WARNING"}
            or basis["frozen_TS_heldout_review"].get("status") != "PASS"
            or basis["active_policy"]["sha256"] != sha256_file(policy_path)):
        raise ValueError("checkpoint promotion retention/heldout/policy evidence is not accepted")
    checkpoint = promotion["checkpoint"]
    heldout_review = load_json_object(_bound(basis["frozen_TS_heldout_review"]))
    if (heldout_review.get("candidate_checkpoint", {}).get("sha256") != checkpoint["sha256"]
            or heldout_review.get("candidate_checkpoint", {}).get("strict_reload_passed") is not True
            or heldout_review.get("candidate_checkpoint", {}).get("all_parameters_finite") is not True
            or heldout_review.get("source_result", {}).get("sha256") != basis["frozen_TS_heldout_result"]["sha256"]):
        raise ValueError("held-out review is not bound to the promoted checkpoint/result")
    checkpoint_path = Path(checkpoint["local_path"])
    if not checkpoint_path.is_file() or sha256_file(checkpoint_path) != checkpoint["sha256"]:
        raise ValueError("new checkpoint hash mismatch")
    primary = source["models"]["primary"]
    if checkpoint["sha256"] == primary["checkpoint_sha256"]:
        raise ValueError("fine-tuning rerun requires a new checkpoint")
    if assessment["models"]["matris_primary"]["checkpoint_sha256"] != primary["checkpoint_sha256"]:
        raise ValueError("fine-tuning assessment used a different base checkpoint")
    require_gpu_write_path(checkpoint["remote_path"])
    early = _sella_followup(state, source)
    if destination.exists():
        raise FileExistsError(f"destination already exists: {destination}")
    rerun = copy.deepcopy(source)
    if early is not None:
        rerun.pop("sella_refinement", None)
        rerun["sella_local_peak_followup"] = early
    rerun["request_id"] = f"{source['request_id']}_al_{round_index}_{checkpoint['sha256'][:12]}"
    rerun["active_learning_round"] = round_index
    rerun["models"]["primary"].update(checkpoint_sha256=checkpoint["sha256"], remote_checkpoint_path=checkpoint["remote_path"],
                                      identifier=f"MatRIS checkpoint {checkpoint['sha256'][:12]}")
    rerun["rerun_provenance"] = {"state": {"path": str(state_path.resolve()), "sha256": sha256_file(state_path)},
                               "checkpoint_promotion": {"path": str(promotion_path.resolve()), "sha256": sha256_file(promotion_path)}}
    (destination / "structures").mkdir(parents=True)
    for row in rerun["images"]:
        target = destination / "structures" / f"{row['image']}.vasp"
        shutil.copy2(source_path.parent / row["path"], target)
        if sha256_file(target) != row["sha256"]:
            raise ValueError("rerun source image changed while copying")
        row["path"] = target.relative_to(destination).as_posix()
    request_path = destination / "request.json"
    write_json_atomic(request_path, rerun)
    _load_images(_load_request(request_path), destination)
    receipt = {"status": "prepared_not_submitted", "round_index": round_index,
               "request_sha256": sha256_file(request_path), "checkpoint_sha256": checkpoint["sha256"],
               "sella_refinement": rerun.get("sella_refinement"),
               "sella_local_peak_followup": rerun.get("sella_local_peak_followup"), "automatic_submission": False}
    write_json_atomic(destination / "PREPARED_NOT_SUBMITTED.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("state", "promotion", "destination"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_rerun(args.state, args.promotion, args.destination)))


if __name__ == "__main__":
    main()
