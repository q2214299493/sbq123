"""Record authorized GPU inference submission without scientific acceptance."""

import json
from datetime import datetime, timezone

from archive.fe110_five_c2_adsorption_20261006.c2_force_gpu import BASE, EVIDENCE, PACKAGE, ROOT
from scripts.artifact_io import sha256_file, write_json
from scripts.state_manager.models import validate_event


def main():
    old_id = "task-fe110-chco-repair-vasp9842136-submitted-20261008"
    new_id = "task-fe110-c2-force-gpu2177-submitted-20261008"
    target = ROOT / f"modules/state_handoff/events/{new_id}.json"
    assert not target.exists()
    submission = json.loads((EVIDENCE / "submission_summary.json").read_text())
    assert submission["job_id"] == "2177" and submission["structure_count"] == 10
    assert submission["batch_manifest_sha256"] == sha256_file(PACKAGE / "batch_manifest.json")
    old = json.loads((ROOT / f"modules/state_handoff/events/{old_id}.json").read_text())
    paths = [
        BASE / "c2_force_diagnostic_v1/assessment_plan.json",
        PACKAGE / "authorization.json",
        PACKAGE / "batch_manifest.json",
        EVIDENCE / "preflight_binding.json",
        EVIDENCE / "submission_summary.json",
        EVIDENCE / "submit.txt",
        EVIDENCE / "scheduler_2177.txt",
    ]
    event = {
        "schema_version": 1,
        "event_id": new_id,
        "occurred_at": submission["observed_at"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "event_type": "task_updated",
        "entity": old["entity"],
        "summary": "Submitted one ten-structure frozen-checkpoint force inference batch as GPU2177; no optimization, training or new VASP.",
        "evidence": [
            {
                "locator": p.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(p),
                "authority": "scheduler" if p.name == "scheduler_2177.txt" else "repository_document",
                "observed_at": submission["observed_at"],
            }
            for p in paths
        ],
        "review": {"required": False, "reason_codes": [], "status": "not_required"},
        "supersedes": [old_id],
        "payload": {
            **old["payload"],
            "phase": "active",
            "current_evidence": [
                "Five closed VASP jobs supply ten exact initial/final structures and finite atom-wise DFT forces; structures/source hashes and force-frame electronic convergence validated.",
                "Fixed Fe0-17 remain excluded from error metrics; raw DFT fixed-atom force vectors retained in local labels.",
                "No original GPU atom-wise force vectors existed; maximum-force comparison is not vector MAE/RMSE.",
                "User authorized one ten-structure frozen AQCat25 inference only; no reoptimization, training, new VASP or automatic retry.",
                f"GPU2177 scheduler {submission['scheduler_state']} at {submission['observed_at']}; 1GPU,4CPU,32GiB,30min limit; no-model remote preflight PASS.",
                "Ten initial/final pairs are correlated; no independent held-out claim, no CH-C-O species03 coverage, no global adsorption-domain recalibration or measured acceleration benefit.",
                "Existing fourteen VASP adsorption submissions remain untouched; no fresh VASP scheduler checkpoint performed during this inference submission.",
            ],
            "one_executable_step": "Collect GPU2177 producer receipt and ten exact-structure predictions; verify checkpoint/source/output hashes and compute movable-Fe/adsorbate atom-wise force errors against frozen VASP labels before deciding on a separate fine-tuning request.",
            "submission_boundary": "Only GPU2177 frozen-geometry inference authorized. No further GPU/VASP submission, automatic retry, stopping, model training or scientific result promotion.",
            "authoritative_references": old["payload"]["authoritative_references"] + [p.relative_to(ROOT).as_posix() for p in paths],
        },
    }
    validate_event(event)
    write_json(target, event)
    print(target.relative_to(ROOT).as_posix())


def record_result():
    old_id = "task-fe110-c2-force-gpu2177-submitted-20261008"
    new_id = "task-fe110-c2-force-gpu2177-assessed-20261008"
    target = ROOT / f"modules/state_handoff/events/{new_id}.json"
    assert not target.exists()
    old = json.loads((ROOT / f"modules/state_handoff/events/{old_id}.json").read_text())
    receipt = json.loads((EVIDENCE / "producer_exit_record.json").read_text())
    assert receipt["exit_code"] == 0
    paths = [
        EVIDENCE / name
        for name in [
            "producer_exit_record.json",
            "predictions.returned.json",
            "canonical_calibration_diagnostic.json",
            "force_error_assessment.json",
            "per_atom_force_errors.csv",
            "local_residual_review.json",
        ]
    ]
    event = {
        **old,
        "event_id": new_id,
        "occurred_at": receipt["finished_utc"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "supersedes": [old_id],
        "summary": "GPU2177 producer completed and exact ten-structure force assessment passed provenance checks; local C/O residual warnings remain, no training or global calibration promotion.",
        "evidence": [
            {
                "locator": p.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(p),
                "authority": "module_validation",
                "observed_at": receipt["finished_utc"],
            }
            for p in paths
        ],
        "payload": {
            **old["payload"],
            "current_evidence": [
                "GPU2177 producer exit0; output/checkpoint/source/ten exact structure hashes and finite N-by-3 force vectors validated. Durable Slurm terminal state unavailable, not inferred DONE.",
                "Five closed jobs, ten correlated initial/final structures; 306 movable-atom vectors after excluding fixedFe0-17. No species03 CH-C-O or independent held-out coverage.",
                "All-movable MAE0.049276/RMSE0.142569/P950.326162/max0.422557eV/A pass unchanged reference force thresholds; missing other calibration families prevents global domain recalibration.",
                "Initial/final adsorbate RMSE0.264832/0.185275eV/A; final FeRMSE0.037950 versus O0.332249eV/A on only twoO atoms. Local C/O residual warnings are not new hard gates.",
                "Recommend reviewing a C/O-focused fine-tuning candidate after completing species coverage and freezing disjoint validation/replay. No training, new VASP, accepted energy promotion or quantified acceleration benefit.",
            ],
            "one_executable_step": "Prepare a C/O-focused adsorption fine-tuning and disjoint validation plan using existing data after completing species03 coverage; preparation only, require separate authorization before any GPU training or new calculation.",
            "submission_boundary": "GPU2177 inference is finished. No additional GPU/VASP submissions, model training, retries or global calibration promotion authorized.",
            "authoritative_references": old["payload"]["authoritative_references"] + [p.relative_to(ROOT).as_posix() for p in paths],
        },
    }
    validate_event(event)
    write_json(target, event)
    print(target.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
