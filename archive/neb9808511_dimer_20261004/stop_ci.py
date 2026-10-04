"""Explicit user cancellation, using only the repository's stop authority."""
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import load_json_object, write_json, sha256_file
from scripts.scheduler_evidence import query_lsf_job
from scripts.neb_agent.submission import stop_job
from scripts.ts_strategy_engine.execution_evidence import load_bound_evidence, execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action

ROOT = Path(__file__).resolve().parents[2]
RECORDS = Path(__file__).resolve().parent
CI = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_ci9808511_sbq123_108r_20261002"


def main():
    receipt = RECORDS / "stop_receipt.json"
    if receipt.exists():
        raise FileExistsError("Stop receipt exists; reconcile it rather than repeat cancellation")
    current = query_lsf_job("9826728", stage="ci_neb")
    write_json(RECORDS / "scheduler_before.json", current)
    if current["status"] not in {"PEND", "RUN"}:
        raise ValueError(f"Job already terminal: {current['status']}; no stop issued")
    request = {"thresholds_file": str(ROOT / "configs/neb_agent/default_thresholds.yaml"),
               "scheduler_file": str(RECORDS / "scheduler_before.json"),
               "preflight_file": str(CI / "submission_preflight.json")}

    def decide(name):
        path = RECORDS / name
        write_json(path, request)
        bindings = {}
        values = {key: load_bound_evidence(path, request, key, bindings)
                  for key in ("thresholds", "scheduler", "preflight", "authorization")}
        return decide_execution({}, {}, values["thresholds"], climb=True, path_reviewed=False,
                                scheduler=values["scheduler"], preflight=values["preflight"],
                                authorization=values["authorization"], source_bindings=bindings)

    initial = decide("stop_request_before_authorization.json")
    source = RECORDS / "user_request.json"
    auth = {"schema_version": 1, "document_kind": "user_execution_authorization", "action": "STOP_JOB",
            "job_id": "9826728", "allowed_scheduler_statuses": ["PEND", "RUN"],
            "authorized_at": datetime.now(timezone.utc).isoformat(),
            "source": {"path": str(source), "sha256": sha256_file(source)},
            "target": {"server_alias": "sunboquan-codex", "job_id": "9826728",
                       "remote_dir": "~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/" + CI.name},
            "workdir_identity": workdir_identity(CI),
            "bundle_sha256": load_json_object(CI / "submission_preflight.json")["bundle_sha256"],
            "evidence_sha256": execution_evidence_sha256(initial["EVIDENCE"])}
    auth_path = RECORDS / "stop_authorization.json"
    write_json(auth_path, auth)
    request["authorization_file"] = str(auth_path)
    decision = decide("stop_gate_request.json")
    decision_path = RECORDS / "stop_gate_decision.json"
    write_json(decision_path, decision)
    require_action(decision_path, "STOP_JOB", decision["state_sha256"])
    stopped = stop_job(decision_path, "sunboquan-codex", "9826728", receipt)
    after = query_lsf_job("9826728", stage="ci_neb")
    write_json(RECORDS / "scheduler_after.json", after)
    print("Stop issued", stopped["job_id"], "confirmed state", after["status"])


if __name__ == "__main__":
    main()
