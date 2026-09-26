"""Read returned GPU1802 evidence; no scientific acceptance or remote actions."""
from datetime import datetime, timezone
import json
from io import StringIO
import os
from pathlib import Path
import shutil
import subprocess

from ase.io import read
import numpy as np

from scripts.artifact_io import load_json_object, sha256_bytes, sha256_file, write_json
from scripts.dual_model_ml_neb import _load_request
from scripts.ml_candidate_source import load_candidate_path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_is_a_int06_path_20260926/gpu_execution_20260926"


def main():
    output = PACKAGE / "output/run2"
    summary_path = PACKAGE / "gpu1802_return_checks.json"
    if summary_path.exists():
        raise FileExistsError("Preserve existing checkpoint")
    manifest_path = output / "dual_model_gpu_ml_neb_path_manifest.candidate.json"
    manifest = load_json_object(manifest_path)
    request_path = PACKAGE / "request.json"
    request = _load_request(request_path)
    state = load_json_object(output / "ml_neb_state.json")
    # Runtime hash precedes seal_successful_run adding producer receipt fields.
    unsealed = {k: v for k, v in manifest.items() if k not in ("producer", "producer_exit_record")}
    unsealed_bytes = (json.dumps(unsealed, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    assert sha256_bytes(unsealed_bytes) == state["candidate_manifest_sha256"]
    assert manifest["source_request"]["sha256"] == sha256_file(request_path)
    assert manifest["models"] == request["models"]
    assert manifest["reaction"] == request["reaction"]
    assert manifest["runner_sha256"] == sha256_file(PACKAGE / "runtime/dual_model_ml_neb.py")
    receipt = output / manifest["producer_exit_record"]["path"]
    assert sha256_file(receipt) == manifest["producer_exit_record"]["sha256"]
    assert load_json_object(receipt)["exit_code"] == 0
    atoms, _ = load_candidate_path(request, manifest, manifest_path, request_path, method="ml_neb")
    comparisons = manifest["fixed_path_model_comparison"]["images"]
    assert len(comparisons) == len(atoms)
    for row, comparison in zip(manifest["images"], comparisons):
        assert row["image"] == comparison["image"]
        assert row["structure_sha256"] == comparison["structure_sha256"]
        assert np.isfinite(list(comparison[k] for k in (
            "primary_energy_eV", "secondary_energy_eV", "movable_force_vector_rmse_eVA",
            "movable_force_difference_max_norm_eVA"))).all()
    # CONTCAR copies are explicitly ML snapshots, not VASP outputs.
    # Keep legacy Perl output paths below Windows MAX_PATH.
    movie_dir = ROOT / "archive/is_int06_path_20260926/gpu1802_movie_review"
    movie_dir.mkdir(exist_ok=True)
    for row in manifest["images"]:
        folder = movie_dir / row["image"]
        folder.mkdir(exist_ok=True)
        snapshot = folder / "CONTCAR"
        if snapshot.exists():
            assert sha256_file(snapshot) == row["structure_sha256"]
        else:
            shutil.copyfile(output / row["structure_path"], snapshot)
    tools = ROOT / "archive/is_int06_path_20260926/vtst_tools"
    env = os.environ.copy()
    env["PATH"] = "C:/Program Files/Git/usr/bin;" + env["PATH"]
    movie = subprocess.run(["C:/Program Files/Git/usr/bin/perl.exe", "-I", tools.as_posix(),
                            (tools / "nebmovie.pl").as_posix(), "1"], cwd=movie_dir,
                           env=env, capture_output=True, text=True, check=True)
    movie_lines = (movie_dir / "movie").read_text().splitlines()
    block_size = 9 + len(atoms[0])
    assert len(movie_lines) == block_size * len(atoms)
    frames = [read(StringIO("\n".join(movie_lines[i:i + block_size]) + "\n"), format="vasp")
              for i in range(0, len(movie_lines), block_size)]
    assert len(frames) == len(atoms)
    assert all(np.allclose(a.positions, b.positions, atol=2e-5, rtol=0) for a, b in zip(atoms, frames))
    summary = {
        "job_id": "1802", "producer_exit_code": 0, "scheduler_terminal_state": "unavailable_record_purged",
        "manifest_sha256": sha256_file(manifest_path), "request_sha256": sha256_file(request_path),
        "source_and_structure_hashes_passed": True, "recomputed_geometry_passed": True,
        "ordinary_converged": manifest["optimizer"]["final_converged"],
        "completed_steps": manifest["optimizer"]["final_steps"],
        "maximum_internal_neb_force_eVA": max(r["projected_neb_force_max_eVA"] for r in manifest["images"][1:-1]),
        "strict_internal_peak_images": manifest["strict_internal_peak_images"],
        "maximum_energy_image": max(manifest["images"], key=lambda r: r["predicted_energy_eV"])["image"],
        "maximum_adjacent_rmsd_A": max(manifest["adjacent_rmsd_A"]),
        "audit_exact_hashes_passed": True,
        "model_model_vector_rmse_range_eVA": [min(r["movable_force_vector_rmse_eVA"] for r in comparisons), max(r["movable_force_vector_rmse_eVA"] for r in comparisons)],
        "movie_check": {"command": "nebmovie.pl 1", "exit_code": movie.returncode, "frames": len(frames), "matches_returned_ml_snapshots": True},
        "scientific_status": "predicted_candidate_needs_work_review_not_TS_or_DFT_barrier",
    }
    write_json(summary_path, summary)
    print(summary)
    previous = ROOT / "modules/state_handoff/events/task-is-a-int06-gpu1802-runtime-started-20260926.json"
    event = load_json_object(previous)
    now = datetime.now(timezone.utc).isoformat()
    event.update(event_id="task-is-a-int06-gpu1802-returned-20260926", occurred_at=now, recorded_at=now,
                 summary="GPU1802 producer completed ordinary ML-NEB in19 steps; complete exact-path AQCat25 audit and recomputed geometry pass, three predicted peaks require review.",
                 supersedes=[event["event_id"]])
    event["evidence"] = [{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p),
                          "authority": authority, "observed_at": now} for p, authority in
                         ((summary_path, "module_validation"), (manifest_path, "calculation_file"),
                          (receipt, "calculation_file"), (request_path, "repository_document"))]
    event["payload"]["current_evidence"] = [
        "GPU1802 producer exited0 at2026-09-26T07:07:45Z; live Slurm record purged, terminal scheduler status unavailable.",
        "Ordinary MatRIS ML-NEB converged in19 steps, maximum NEB force0.081585 eV/A below0.10; complete11-image AQCat25 exact-path audit returned.",
        "Request6011d0a9/checkpoints/runner and all returned structure hashes verified; geometry recomputed PASS, max adjacent RMSD0.080181 A, movie11frames matches snapshots.",
        "Predicted MatRIS local peaks01/05/09, global maximum05; do not infer three real TS from an ML profile.",
        "No ML-CI, restraints, new training or VASP submission; returned path remains needs_work_review."]
    event["payload"]["one_executable_step"] = "Review the complete multi-peak ML path and H50 site changes, then prepare the appropriate compatible VASP coarse-NEB handoff; do not submit without authorization."
    event["payload"]["authoritative_references"] = [summary_path.relative_to(ROOT).as_posix(), manifest_path.relative_to(ROOT).as_posix()]
    write_json(ROOT / f"modules/state_handoff/events/{event['event_id']}.json", event)


if __name__ == "__main__":
    main()
