"""Review and register existing CHCO Dimer/VFA evidence;never submit calculations."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive, write_json
from scripts.registry_connection import open_registry
from scripts.registry_transactions import approve_plan
from scripts.registry_write import apply_registry_batch
from scripts.ts_strategy_engine.contract import load_contract
from scripts.ts_strategy_engine.dimer_analysis import analyze_dimer
from scripts.ts_strategy_engine.evidence import record_ts_validation
from scripts.ts_strategy_engine.execution_gate import require_action
from scripts.ts_strategy_engine.execution_gate_cli import build_decision
from scripts.ts_validation.analyze_vfa import analyze_vfa, vfa_scope_checks
from scripts.ts_validation.prepare_vfa_from_ts_image import prepare_vfa_handoff
from scripts.ts_validation.validation_pipeline import evaluate_validation_pipeline

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109"
SOURCE = BASE / "dimer_completion_20261115_v1/source"
MODES = BASE / "vfa_mode12_review_20261115_v1"
OUT = BASE / "ts_acceptance_20261115_v1"
VFA = OUT / "vfa"
DB = ROOT / "data/project_registry.sqlite3"
CONTRACT = BASE / "local_triplet_review_20261112_v1/reaction_contract.reviewed.json"
AUTHORITY = Path(__file__).with_name("user_authority.md")
REVIEWER = "Codex formal evidence review under explicit user request 2026-11-15"
VALIDATION_ID = "fe110_ch_co_dimer9998592_vfa2260_grade_a_20261115"


def now():
    return datetime.now(timezone.utc).isoformat()


def identities():
    with open_registry(DB) as connection:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute("SELECT c.calculation_id,c.workflow_status,j.job_record_id,j.scheduler_job_id "
            "FROM calculations c JOIN jobs j ON c.calculation_id=j.calculation_id "
            "WHERE j.server_alias=? AND j.scheduler_job_id IN (?,?)",
            ("sunboquan-codex", "9998592", "2260")).fetchall()
    result = {str(row["scheduler_job_id"]): dict(row) for row in rows}
    if len(rows) != 2 or set(result) != {"9998592", "2260"}:
        raise ValueError("Source/validation job identities are missing or ambiguous")
    return result


def review():
    if OUT.exists():
        raise ValueError("Review destination exists;inspect its saved state before retry")
    inventory = load_json_object(MODES / "remote_inventory.json")
    for item in inventory["files"]:
        if sha256_file(MODES / "raw" / item["relative_path"]) != item["sha256"]:
            raise ValueError("Collected frequency evidence changed")
    dimer = load_json_object(SOURCE / "dimer_analysis.json")
    if analyze_dimer(SOURCE, write_output=False) != dimer:
        raise ValueError("Current Dimer analysis differs;no summary-only acceptance")
    mode = load_json_object(MODES / "mode12_review.json")
    metrics = load_json_object(MODES / "mode12_metrics.json")
    for key, filename in (("quantitative_metrics_sha256", "mode12_metrics.json"),
                          ("visual_review_sha256", "mode12_three_frames.png")):
        if mode[key] != sha256_file(MODES / filename):
            raise ValueError("Reviewed target-mode evidence changed")
    if (mode["mode_assignment"] != "accepted" or mode["geometry_status"] != "pass"
            or mode["principal_mode_index"] != 12 or metrics["source_outcar_sha256"] != sha256_file(MODES / "raw/OUTCAR")):
        raise ValueError("Target mode is not currently accepted")
    ids = identities()
    contract = load_contract(CONTRACT)
    OUT.mkdir()
    previous = BASE / "dimer_completion_20261115_v1/dimer_soft_gate_review.json"
    residual = load_json_object(previous)
    residual.update(status="accepted", decision="accept_for_ts_validation", reviewer=REVIEWER,
        reviewed_at=now(), authority_source=str(AUTHORITY), authority_sha256=sha256_file(AUTHORITY),
        previous_review=str(previous), previous_review_sha256=sha256_file(previous),
        note="Formal review:hard atomic-force/electronic/negative-curvature evidence passes;complete unique mode12 is target CC coupling. Exact Force/Torque warnings retained. Old diagnostic approval remains unchanged;not a claim that soft numerical targets passed.")
    write_json_exclusive(OUT / "dimer_soft_gate_review.json", residual)
    prepare_vfa_handoff(SOURCE, VFA, contract["reaction_atoms"], contract,
        SOURCE / "dimer_analysis.json", False, OUT / "dimer_soft_gate_review.json")
    if sha256_file(VFA / "POSCAR") != sha256_file(MODES / "raw/POSCAR"):
        raise ValueError("Refreshed review geometry differs from actually calculated frequency geometry")
    for item in inventory["files"]:
        name = item["relative_path"]
        if name in {"POSCAR", "vfa_handoff.json", "vfa_scope_review.json"}:
            continue
        shutil.copy2(MODES / "raw" / name, VFA / name)
    scope = load_json_object(VFA / "vfa_scope_review.json")
    scope.update(status="accepted_for_partial_hessian", reviewer=REVIEWER, reviewed_at=now(),
        original_scope_review=str(MODES / "raw/vfa_scope_review.json"),
        original_scope_review_sha256=sha256_file(MODES / "raw/vfa_scope_review.json"),
        notes="Same actually calculated C45/C46/O47/H48 scope;all reaction atoms active. Clear CC assignment;no unresolved local surface coupling. No Hessian expansion or thermochemistry claim.")
    write_json(VFA / "vfa_scope_review.json", scope)
    formal = dict(mode)
    formal.update(status="accepted", reviewer=REVIEWER, reviewed_at=now(),
        validation_calculation_id=ids["2260"]["calculation_id"],
        source_saddle_calculation_id=ids["9998592"]["calculation_id"],
        source_job_record_id=ids["9998592"]["job_record_id"],
        frequency_output_file_id="chco_vfa2260_formal_20261115_OUTCAR",
        vfa_handoff=str(VFA / "vfa_handoff.json"), vfa_handoff_sha256=sha256_file(VFA / "vfa_handoff.json"),
        diagnostic_review=str(MODES / "mode12_review.json"), diagnostic_review_sha256=sha256_file(MODES / "mode12_review.json"),
        authorization_boundary="Formal TS evidence only;four-atom partial Hessian. No barrier/free-energy or kinetics-readiness claim;no new calculation.")
    write_json_exclusive(VFA / "vfa_review.json", formal)
    analysis = analyze_vfa(VFA, contract, VFA / "vfa_review.json")
    pipeline = evaluate_validation_pipeline(dimer_analysis_path=SOURCE / "dimer_analysis.json",
        dimer_soft_review_path=OUT / "dimer_soft_gate_review.json", vfa_workdir=VFA,
        vfa_analysis_path=VFA / "vfa_analysis.json", output=OUT / "pipeline_status.json")
    if analysis["grade"] != "A" or not pipeline["scientifically_validated_ts"] or not all(vfa_scope_checks(VFA).values()):
        raise ValueError("Formal scientific owner did not accept current evidence")
    print({"grade": analysis["grade"], "pipeline": pipeline["status"], "no_new_job": True})


def gate():
    request = load_json_object(BASE / "dimer_image05_20261112_v1/submission_request.json")
    request.pop("authorization_file", None)  # No execution authorization is requested or reused.
    request["validation_file"] = str(VFA / "vfa_analysis.json")
    request["scheduler_file"] = str(SOURCE / "scheduler_evidence.json")
    write_json_exclusive(OUT / "acceptance_request.json", request)
    decision = build_decision(OUT / "acceptance_request.json", OUT / "acceptance_decision.json")
    require_action(OUT / "acceptance_decision.json", "APPROVE_TS_CANDIDATE", decision["state_sha256"])
    print({"decision": decision["DECISION"], "allowed": decision["ALLOWED_ACTIONS"]})


def prepare_registry():
    ids = identities()
    frequency = ids["2260"]
    scheduler = load_json_object(MODES / "scheduler_evidence.json")
    if scheduler["status"] != "DONE" or scheduler["job_id"] != "2260":
        raise ValueError("No authoritative VFA DONE evidence")
    files = []
    paths = [VFA / item["relative_path"] for item in load_json_object(MODES / "remote_inventory.json")["files"]]
    paths += [VFA / name for name in ("vfa_review.json", "vfa_analysis.json")]
    paths += [OUT / name for name in ("dimer_soft_gate_review.json", "pipeline_status.json", "acceptance_request.json", "acceptance_decision.json")]
    paths += [MODES / name for name in ("mode12_metrics.json", "mode12_review.json", "mode12_three_frames.png", "scheduler_evidence.json", "verification.json")]
    paths += [AUTHORITY, CONTRACT]
    for index, path in enumerate(dict.fromkeys(paths)):
        file_id = "chco_vfa2260_formal_20261115_OUTCAR" if path == VFA / "OUTCAR" else f"chco_vfa2260_formal_20261115_{index:03d}"
        files.append({"file_id": file_id, "calculation_id": frequency["calculation_id"],
            "job_record_id": frequency["job_record_id"], "role": "frequency_output" if path == VFA / "OUTCAR" else "formal_TS_review_provenance",
            "filename": path.name, "local_path": str(path), "storage_mode": "local_only", "byte_size": path.stat().st_size,
            "sha256": sha256_file(path), "existence_status": "confirmed", "notes": "Existing2260 data;new formal-review binding;no new job or energy result"})
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch", "batch_id": "chco_formal_ts_provenance_20261115_v1",
        "created_at": now(), "reviewer": REVIEWER, "reason": "Formal TS provenance and terminal frequency job;TS validation written separately by gated owner",
        "rows": {"files": files, "job_status_history": [{"job_record_id": frequency["job_record_id"], "scheduler_status": "DONE",
            "scientific_status": "Completed local Hessian;one reviewed CC imaginary mode;formal scientific validation through gated TS owner",
            "checked_at": scheduler["checked_at"], "source_command": scheduler["source_command"], "source_text": scheduler["query"]["stdout"], "reviewer": REVIEWER}],
            "reviews": [{"review_id": "chco_formal_TS_review_20261115_v1", "calculation_id": frequency["calculation_id"],
                "review_type": "formal_TS_local_vibrational_acceptance", "decision": "accepted", "reviewer": REVIEWER, "reviewed_at": now(),
                "evidence": str(OUT / "acceptance_decision.json"), "reason": "Grade A owner review;exact residual warnings retained;no barrier/thermal result"}]},
        "workflow_status_changes": [{"status_change_id": "chco_vfa2260_done_20261115_v1", "calculation_id": frequency["calculation_id"],
            "expected_workflow_status": frequency["workflow_status"], "new_workflow_status": "done", "changed_at": now(),
            "reviewer": REVIEWER, "reason": "Authoritative DONE and complete local frequency output;scientific grade separately registered"}]}
    write_json_exclusive(OUT / "registry_batch.json", batch)
    print({"rows": {key: len(value) for key, value in batch["rows"].items()}, "workflow_changes": 1})


def apply_provenance():
    plan = load_json_object(OUT / "registry_plan.json")
    batch = load_json_object(OUT / "registry_batch.json")
    decision = load_json_object(OUT / "acceptance_decision.json")
    require_action(OUT / "acceptance_decision.json", "APPROVE_TS_CANDIDATE", decision["state_sha256"])
    approval = approve_plan(plan, reviewer=REVIEWER, reviewed_at=now())
    write_json_exclusive(OUT / "registry_approval.json", approval)
    receipt = apply_registry_batch(DB, batch, confirmed_sha256=plan["plan_sha256"], plan=plan, approval=approval)
    write_json_exclusive(OUT / "registry_receipt.json", receipt)
    print({key: receipt[key] for key in ("inserted", "updated", "already_applied")})


def register_validation():
    with open_registry(DB) as connection:
        existing = connection.execute("SELECT * FROM ts_validations WHERE ts_validation_id=?", (VALIDATION_ID,)).fetchone()
    if existing:
        raise ValueError("TS record already exists;verify instead of repeating write")
    decision = load_json_object(OUT / "acceptance_decision.json")
    value = record_ts_validation(DB, VALIDATION_ID, load_json_object(VFA / "vfa_analysis.json"),
        gate_decision=OUT / "acceptance_decision.json", gate_state_sha256=decision["state_sha256"])
    write_json_exclusive(OUT / "ts_registration_receipt.json", {"ts_validation_id": value, "recorded_at": now()})
    print(value)


def verify():
    batch = load_json_object(OUT / "registry_batch.json")
    analysis = load_json_object(VFA / "vfa_analysis.json")
    count = 0
    with open_registry(DB) as connection:
        connection.execute("PRAGMA query_only=ON")
        for table, rows in batch["rows"].items():
            for row in rows:
                query = 'SELECT COUNT(*) FROM "' + table + '" WHERE ' + ' AND '.join('"' + key + '" IS ?' for key in row)
                if connection.execute(query, tuple(row.values())).fetchone()[0] != 1:
                    raise ValueError("Registry readback differs: " + table)
                count += 1
        result = dict(connection.execute("SELECT * FROM ts_validations WHERE ts_validation_id=?", (VALIDATION_ID,)).fetchone())
        if (result["grade"] != "A" or result["kinetic_eligible"] != 1
                or result["frequency_output_file_id"] != analysis["frequency_output_file_id"]
                or result["source_saddle_calculation_id"] != analysis["source_saddle_calculation_id"]
                or result["contract_sha256"] != analysis["contract_sha256"]
                or result["principal_mode_assignment"] != "accepted"
                or result["imaginary_frequency_count"] != 1):
            raise ValueError("Registered TS identity/grade differs")
        cid = analysis["validation_calculation_id"]
        if connection.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (cid,)).fetchone()[0] != "done":
            raise ValueError("Frequency workflow status differs")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok" or connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Registry integrity failed")
    for item in batch["rows"]["files"]:
        if sha256_file(Path(item["local_path"])) != item["sha256"]:
            raise ValueError("Registered evidence file changed")
    old = load_json_object(OUT / "dimer_soft_gate_review.json")
    if sha256_file(Path(old["previous_review"])) != old["previous_review_sha256"]:
        raise ValueError("Old diagnostic review was modified")
    write_json_exclusive(OUT / "verification.json", {"status": "PASS", "metadata_rows_verified": count,
        "workflow_changes_verified": 1, "accepted_TS_records": 1, "ts_validation_id": VALIDATION_ID,
        "grade": "A", "old_diagnostic_review_unchanged": True, "no_new_calculation": True,
        "barrier_registered": False, "thermochemistry_calculated": False})
    print({"status": "PASS", "metadata_rows": count, "accepted_TS": VALIDATION_ID})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    actions = {"review": review, "gate": gate, "prepare-registry": prepare_registry,
        "apply-provenance": apply_provenance, "register-validation": register_validation, "verify": verify}
    parser.add_argument("phase", choices=actions)
    actions[parser.parse_args().phase]()
