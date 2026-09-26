"""Bind reviewed full migration path to explicit one-job coarse-NEB authority."""
from datetime import datetime, timezone

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent.submission import preflight
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import validate_decision
from scripts.ts_strategy_engine.execution_gate_cli import build_decision
from scripts.ts_strategy_engine.path_evidence import validate_path_binding, validate_path_review
from scripts.ts_strategy_engine.contract import load_contract
from scripts.ts_strategy_engine.workflow import AnalyzeRequest, analyze_search
from archive.is_int06_path_20260926.prepare_vasp import ROOT, BASE, RUN


def main():
    if (RUN / "user_execution_authorization.json").exists():
        raise FileExistsError("Existing authorization must remain immutable")
    now = datetime.now(timezone.utc).isoformat()
    review_path = RUN / "path_review.json"
    review = load_json_object(review_path)
    assert review["status"] == "needs_review"
    write_json(RUN / "path_review.draft.json", review)
    review.update(status="accepted", reviewer="Codex delegated numerical/top-side/chemical review",
                  reviewed_at=now, notes="User: 审核然后提交粗neb吧. Complete11-image GPU1802 geometry and film checked; endpoints/fixed layers identical. H50 migrates continuously among Fe44/43/37 -> Fe41/43/44 -> Fe41/40/38. C2HO and originalCH intact, no OH/newCH bond. Fe38 distance initially increases because H first changes neighboring sites, not PBC discontinuity. Model peaks01/05/09 are sampling evidence, not three verified saddles or a minimum claim. Accept only as complete ordinary VASP exploration; no CI/Dimer, no extra restraint or automatic retry.")
    write_json(review_path, review)
    assert validate_path_review(review_path, RUN / "path_generation_report.json")[0]
    contract_path = RUN / "reaction_contract.normalized.json"
    assert validate_path_binding(RUN, load_contract(contract_path))["valid"]
    analyze_search(AnalyzeRequest(workdir=RUN, contract=contract_path,
                   thresholds=ROOT / "configs/neb_agent/default_thresholds.yaml", path_review=review_path))
    pf = preflight(RUN, "ordinary_neb")
    assert pf["passed"], pf["errors"]
    request = {"geometry_file": str(RUN / "path_geometry_diagnosis.json"),
               "analysis_file": str(RUN / "neb_analysis.json"),
               "thresholds_file": str(ROOT / "configs/neb_agent/default_thresholds.yaml"),
               "preflight_file": str(RUN / "submission_preflight.json"), "climb": False, "path_reviewed": True}
    request_path = RUN / "execution_gate_request.json"
    write_json(request_path, request)
    before = build_decision(request_path, RUN / "gate_before_authorization.json")
    source = RUN / "user_execution_request.json"
    write_json(source, {"verbatim": "审核然后提交粗neb吧", "received_date": "2026-09-26",
               "scope": "One reviewed complete IS-A9725473 -> INT06_9748648 ordinary VASP coarse NEB seeded from GPU1802.9 interiors/108ranks/NPAR4; no pilot, CI,Dimer,training,parameter scan,automatic retry. Accepted other intervals unchanged."})
    prior = load_json_object(BASE / "h_migration_int06_mid_vasp_bowed_20260921/ordinary_neb/user_execution_authorization.json")
    assert prior["potcar"]["spec_sha256"] == pf["files"]["POTCAR.spec"]
    auth = {"schema_version": 1, "document_kind": "user_execution_authorization", "action": "SUBMIT_VASP",
            "calculation_kind": "ordinary_neb", "authorized_at": now,
            "source": {"path": str(source), "sha256": sha256_file(source)},
            "target": {"server_alias": "sunboquan-codex",
                       "remote_dir": "~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/" + RUN.name},
            "workdir_identity": workdir_identity(RUN), "bundle_sha256": pf["bundle_sha256"],
            "evidence_sha256": execution_evidence_sha256(before["EVIDENCE"]), "potcar": prior["potcar"]}
    write_json(RUN / "user_execution_authorization.json", auth)
    request["authorization_file"] = str(RUN / "user_execution_authorization.json")
    write_json(request_path, request)
    gate = build_decision(request_path, RUN / "execution_gate_decision.json")
    validate_decision(gate)
    assert "SUBMIT_VASP" in gate["ALLOWED_ACTIONS"], gate["DECISION"]
    print(gate["DECISION"], gate["ALLOWED_ACTIONS"])


if __name__ == "__main__":
    main()
