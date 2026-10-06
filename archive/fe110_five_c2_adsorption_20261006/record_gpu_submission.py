"""Capture actual scheduler/producer evidence and create a superseding task event."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json

ROOT = Path(__file__).resolve().parents[2]
CALC = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "IdentitiesOnly=yes",
       "-i", "C:/Users/86177/.ssh/id_ed25519_fe_agent", "-p", "36039", "sbq@10sx4jr711576.vicp.fun"]


def main():
    observed = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    folder = CALC / "gpu_submission_evidence"
    folder.mkdir(exist_ok=True)
    records = []
    for job, version in (("2136", "v1"), ("2137", "v2"), ("2138", "v3"), ("2139", "v4")):
        remote = f"/home/sbq/sbq/aqcat25_ts_pilot/fe110_five_c2_adsorption_20261006_gpu_{version}"
        receipt = subprocess.run(SSH + [f"cat {remote}/submission_receipt.txt"], capture_output=True, check=True).stdout
        assert receipt.strip() == job.encode(), (job, receipt)
        (folder / f"submission_{job}.txt").write_bytes(receipt)
        scheduler_path = folder / f"scheduler_{job}.txt"
        if job != "2139" and scheduler_path.exists():
            # Slurm discards old completed jobs; retain previously captured evidence.
            scheduler = scheduler_path.read_bytes()
        else:
            scheduler = subprocess.run(SSH + [f"scontrol show job {job}"], capture_output=True, check=True).stdout
            scheduler_path.write_bytes(scheduler)
        status = next(field.split("=", 1)[1] for field in scheduler.decode().split() if field.startswith("JobState="))
        records.append({"job_id": job, "version": version, "scheduler_state": status, "remote_root": remote,
                        "scheduler_evidence_sha256": sha256_file(folder / f"scheduler_{job}.txt")})
    evidence = {"observed_at": observed, "jobs": records, "active_job_id": "2139",
                "candidate_count": 12, "species_candidate_counts": [3, 2, 1, 3, 3],
                "batch_manifest_sha256": sha256_file(CALC / "gpu_batch_v4/batch_manifest.json"),
                "checks": {"python_syntax": "pass", "12_handoff_schema_hash_atom_order_SD": "pass",
                           "remote_no_model_ASE_preflight": "pass", "shell_syntax": "pass",
                           "canonical_root_containment_positive_and_escape_negative_tests": "pass"},
                "scientific_status": "predicted_candidate_generation_only_not_VASP_validated",
                "failures": "2136/2137/2138 exited during bootstrap before any candidate optimization; preserved. v4 fixes both canonical-root checks and pins permitted cache/temp directories.",
                "unverified": ["optimizer convergence", "final chemistry", "final site", "post-relaxation duplicates", "VASP energies"]}
    write_json(CALC / "gpu_submission_evidence_2139.json", evidence)
    old_id = "task-fe110-five-c2-adsorption-review-20261006"
    old = json.loads((ROOT / f"modules/state_handoff/events/{old_id}.json").read_text(encoding="utf-8"))
    new_id = "task-fe110-five-c2-adsorption-gpu2139-submitted-20261006"
    event = {
        "schema_version": 1, "occurred_at": observed, "recorded_at": observed,
        "event_id": new_id, "event_type": "task_updated", "entity": old["entity"],
        "summary": "User-authorized AQCat25 adsorption batch2139 submitted for12 reviewed candidates; bootstrap failures2136/2137/2138 preserved.",
        "evidence": [{"locator": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256_file(path),
                      "authority": authority, "observed_at": observed} for path, authority in (
                          (CALC / "gpu_batch_v4/reviewed_plan.json", "user_authorization"),
                          (CALC / "gpu_submission_evidence_2139.json", "module_validation"),
                          (folder / "scheduler_2139.txt", "scheduler"))],
        "review": {"required": False, "reason_codes": [], "status": "not_required"},
        "payload": {**old["payload"],
                    "current_evidence": ["User explicitly authorized GPU pre-relaxation only; no VASP submitted.",
                                         "12 selected local CARE seeds (species counts3/2/1/3/3) pass initial geometry and hash-bound schema/ASE preflight; three excluded raw seeds retained.",
                                         f"MZ73 Slurm2139 scheduler={records[-1]['scheduler_state']}; one GPU,4CPU,32GiB,120minute limit; maximum80 LBFGS steps per candidate at0.10eV/A.",
                                         "Failed bootstrap2136/2137/2138 did not produce adsorption results. Task-local runtime handles verified root symlink and pins cache/temp paths; no global scientific method change.",
                                         "Final geometry/chemistry and duplicate review remain pending. Predictions are not reportable adsorption energies. Prior Dimer9833429 review remains deferred."],
                    "one_executable_step": "After2139 finishes, collect all producer receipts, return manifests and predicted structures; validate in work and review final chemistry/sites/duplicates before requesting VASP.",
                    "submission_boundary": "GPU12 batch explicitly authorized and submitted. No automatic continuation/resubmission or VASP handoff.",
                    "authoritative_references": old["payload"]["authoritative_references"] + [
                        "calculations/fe110_five_c2_adsorption_20261006/gpu_submission_evidence_2139.json",
                        "calculations/fe110_five_c2_adsorption_20261006/gpu_batch_v4/batch_manifest.json"]},
        "supersedes": [old_id, "task-fe110-five-c2-adsorption-gpu2138-submitted-20261006"],
    }
    target = ROOT / f"modules/state_handoff/events/{new_id}.json"
    if target.exists():
        raise FileExistsError(target)
    write_json(target, event)
    print(json.dumps({"job": "2139", "scheduler_state": records[-1]["scheduler_state"], "event": str(target)}))


if __name__ == "__main__":
    main()
