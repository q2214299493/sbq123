"""Bind an existing reviewed Dimer bundle to its parent's current evidence."""
from __future__ import annotations

import argparse
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent.submission import preflight
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--dimer", type=Path, required=True)
    args = parser.parse_args()
    dimer, parent = args.dimer.resolve(), args.parent.resolve()
    source = parent / "dimer_preparation_gate.json"
    previous = load_json_object(source)
    require_action(source, "PREPARE_DIMER_HANDOFF", previous["state_sha256"])
    accepted = parent / "user_stage_acceptance.json"
    report = preflight(dimer, "dimer")
    if not report["passed"]:
        raise ValueError(report["errors"])
    auth = {"action": "START_DIMER", "source_job_id": load_json_object(accepted)["source_job_id"],
            "source_user_acceptance": str(accepted), "source_user_acceptance_sha256": sha256_file(accepted),
            "bundle_sha256": report["bundle_sha256"], "scope": "One image-02 local Dimer, 80 cores; user requested the next refinement step"}
    write_json(dimer / "user_execution_authorization.json", auth)
    evidence = previous["EVIDENCE"]
    decision = decide_execution(evidence["geometry"], evidence["analysis"], evidence["thresholds"],
                                climb=False, path_reviewed=True, path_quality=evidence["path_quality"],
                                scheduler=evidence["scheduler"], preflight=report, authorization=auth,
                                source_bindings={"parent_gate": {"path": str(source), "sha256": sha256_file(source)},
                                                 "authorization": {"path": str(dimer / "user_execution_authorization.json"), "sha256": sha256_file(dimer / "user_execution_authorization.json")}})
    write_json(dimer / "execution_gate_decision.json", decision)
    require_action(dimer / "execution_gate_decision.json", "START_DIMER", decision["state_sha256"])
    print({"decision": decision["DECISION"], "allowed": decision["ALLOWED_ACTIONS"], "bundle_sha256": report["bundle_sha256"]})


if __name__ == "__main__":
    main()
