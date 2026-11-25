"""Freeze the reviewed INT06->MID CI-NEB path for one bounded GPU drift test."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CALC = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822"
SOURCE = CALC / "h_migration_int06_mid_vasp_bowed_20260921/ci_completed_review_20260925"
TEMPLATE = CALC / "h_migration_int06_mid_fresh_seed_20260916/submission_20260916/payload/request.json"
OUTPUT = CALC / "h_migration_int06_mid_ci_seed_gpu_20260926"
CHECKPOINT = "/home/sbq/sbq/matris_energy_force_finetune_c2hoh_retention_candidate2_20260902/results/job_1506/epoch_checkpoints/epoch_006.pth.tar"
CHECKPOINT_SHA = "8e53cfb0e54aec7aa918cefae3ce7b4a9488d87231626f7ae4bc98fdebdbeb49"
REVIEW_SHA = "9653c30cbf5deb83f642fcab23f3c252e4262c9fcaf11009b5ebd8b3b9898167"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUTPUT.exists():
        raise SystemExit(f"Refusing to overwrite existing package: {OUTPUT}")
    if digest(SOURCE / "path_review.json") != REVIEW_SHA:
        raise SystemExit("Source CI-NEB review hash changed")
    request = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    request["request_id"] = "int06_mid_ci9796856_exact_seed_bounded_20260926"
    request["run_kind"] = "bounded_gpu_path_drift_test"
    request["source_plan"] = {
        "method": "exact reviewed final VASP CI-NEB 00-06; no IDPP or waypoint rebuilding",
        "source_ci_neb_job_id": "9796856",
        "source_path_review_sha256": REVIEW_SHA,
    }
    request.pop("source_seed_review", None)
    request["models"]["primary"].update(
        checkpoint_sha256=CHECKPOINT_SHA,
        remote_checkpoint_path=CHECKPOINT,
    )
    request["ordinary_ml_neb"].update(
        max_steps=40,
        ml_ci="off",
        purpose="one 40-step unrestrained ordinary ML-NEB drift test from converged CI-NEB path",
    )
    request["scheduler_resources"]["walltime"] = "02:00:00"
    request["production_limits"].update(
        image_count=7,
        production_submission_authorized=True,
        automatic_retry=False,
        automatic_vasp_submission=False,
        required_return_status="needs_work_review",
    )
    request["domain_validation"].update(
        status="on_path_force_screen_passed_off_path_drift_untested",
        note="Epoch 6 passed the exact-structure CI-path screening batch 1785; this bounded optimizer test does not confer TS-domain calibration.",
    )
    request["fallback_policy"] = {
        "gpu_attempts": 1,
        "on_drift": "review same-structure VASP static labels before any fine-tune",
        "automatic_submission": False,
    }
    image_rows = []
    for index in range(7):
        name = f"{index:02d}"
        source = SOURCE / name / ("POSCAR" if index in (0, 6) else "CONTCAR")
        target = OUTPUT / "structures" / f"{name}.vasp"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        image_rows.append(
            {"image": name, "path": f"structures/{name}.vasp", "sha256": digest(target),
             "source_path": str(source.relative_to(ROOT)).replace("\\", "/"),
             "source_sha256": digest(source)}
        )
    request["images"] = image_rows
    runtime = OUTPUT / "runtime"
    runtime.mkdir()
    for name in (
        "dual_model_ml_neb.py", "dual_model_ml_neb_job.sh", "aqcat25_ml_neb.py",
        "mlip_same_structure_benchmark.py", "artifact_io.py", "aqcat25_handoff.py",
        "ml_sella_candidate.py",
    ):
        shutil.copyfile(ROOT / "scripts" / name, runtime / name)
    helper = CALC / "active_learning/int06_mid_ci9796856_exact_screen_20260926/runtime/aqcat25_mz73_env.sh"
    shutil.copyfile(helper, runtime / "aqcat25_mz73_env.sh")
    request["runtime_bindings"] = {path.name: digest(path) for path in runtime.iterdir()}
    # Preserve the submitted Windows request bytes across platforms and Git.
    (OUTPUT / "request.json").write_text(
        json.dumps(request, indent=2) + "\n", encoding="utf-8", newline="\r\n"
    )
    print(json.dumps({"package": str(OUTPUT), "request_sha256": digest(OUTPUT / "request.json"),
                      "images": image_rows, "runtime_bindings": request["runtime_bindings"]}, indent=2))


if __name__ == "__main__":
    main()
