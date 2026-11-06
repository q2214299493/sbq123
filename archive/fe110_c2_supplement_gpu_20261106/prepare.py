"""Freeze the exact accepted12 inputs for a bounded Slurm GPU batch; no launch."""
from pathlib import Path

from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.aqcat25_handoff import atom_order_sha256, validate_handoff
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest_valid, write_json_exclusive


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "calculations/fe110_c2_site_supplement_20261106/review_v1"
OUT = SOURCE.parent / "gpu_slurm_ft512_20261106_v1"
PACKAGE = OUT / "package"
REMOTE = "/home/sbq/sbq/fe110_c2_supplement_gpu_20261106_v1"
MODEL_PATH = "/home/sbq/sbq/fe110_scratch512_20261028_v1/finetune/control/output/direct-fe110-scratch512-finetune20-20261028-v1/checkpoints/2026-10-28-20-56-32/best_checkpoint.pt"
MODEL_SHA = "cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0"
REVIEW_SHA = "abb50499fb05a9caec0c53944fe876ffd3112e9daf2de460ac1b4394798c486f"
USER = "这12个都保留，先提交GPU加速，完成后回收检查位点和连接关系，再决定是否提交VASP。"


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(source.read_bytes())


def main():
    review = load_json_object(SOURCE / "candidate_review.json")
    independent = load_json_object(SOURCE / "independent_verification.json")
    if (sha256_file(SOURCE / "candidate_review.json") != REVIEW_SHA or not source_file_manifest_valid(review)
            or independent["manifest_sha256"] != REVIEW_SHA or independent["status"] != "PASS_GEOMETRY_READBACK_ONLY"):
        raise ValueError("accepted source review changed")
    OUT.mkdir(parents=True, exist_ok=False)
    PACKAGE.mkdir()
    frozen = ROOT / "calculations/fe110_c2_adsorption_11_15_20261020/ft512_gpu_20261029_v1/package/runtime"
    for path in frozen.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            copy(path, PACKAGE / "runtime" / path.relative_to(frozen))
    for source, target in ((Path(__file__).with_name("worker.py"), "worker.py"),
            (ROOT / "scripts/artifact_io.py", "artifact_io.py"),
            (ROOT / "scripts/aqcat25_handoff.py", "aqcat25_handoff.py"),
            (ROOT / "configs/aqcat25_handoff.schema.json", "handoff.schema.json"),
            (ROOT / "configs/execution_backends.yaml", "execution_backends.yaml"),
            (ROOT / "configs/true_fe110_production.yaml", "evidence/profile.yaml"),
            (SOURCE / "candidate_review.json", "evidence/source_review.json")):
        copy(source, PACKAGE / target)
    cases = []
    for row in review["candidates"]:
        source = Path(row["structure"])
        if sha256_file(source) != row["structure_sha256"]:
            raise ValueError("accepted structure changed")
        seed = f"inputs/{row['name']}/POSCAR"
        copy(source, PACKAGE / seed)
        symbols = expanded_symbols(read_poscar(source))
        anchors = {a["atom_0based"] for a in row["saved_geometry"]["heavy_atoms"] if a["nearest_Fe"][0]["distance_A"] <= 2.65}
        handoff = {"schema_version": 2, "direction": "work_to_gpu", "workflow_kind": "adsorption",
            "handoff_id": "fe110_c2_supplement_20261106_" + row["name"], "source_workflow_sha256": REVIEW_SHA,
            "candidate_structure": {"path": seed, "sha256": row["structure_sha256"], "format": "vasp_poscar",
                "atom_count": len(symbols), "atom_order_sha256": atom_order_sha256(symbols)},
            "compatibility": {"branch": "true_fe110_5layer_5x5x1", "sha256": sha256_file(PACKAGE / "evidence/profile.yaml"),
                "slab_model": "Fe45_bottom18_fixed", "facet": "Fe(110)"},
            "model": {"identifier": "AQCat25_ft512_frozen_partial_cdd391d", "checkpoint_sha256": MODEL_SHA,
                "fmax_eV_per_A": .1, "max_steps": 80},
            "selective_dynamics": {"fixed_atom_indices_1based": list(range(1, 19)), "free_atom_count": len(symbols) - 18},
            "adsorption": {"evidence_gated_plan_sha256": REVIEW_SHA, "clean_slab_sha256": review["slab_sha256"],
                "identity_and_connectivity": row["target_graph"], "intended_motif": row["proposed_binding_family"],
                "surface_elements": ["Fe"], "adsorbate_atoms": [{"index_1based": i + 1, "symbol": symbols[i],
                    "role": "anchor" if i in anchors else "non_anchor"} for i in range(45, len(symbols))],
                "connectivity_constraints": [], "monitored_pairs": [{"label": bond["pair"],
                    "atoms_1based": [i + 1 for i in bond["atoms_0based"]]} for bond in row["geometry"]["bond_distances"]]},
            "restrictions": {"predicted_candidate_only": True, "submit_vasp": False,
                "scientific_acceptance": False, "direct_gpu_to_vasp_handoff": False}}
        handoff_path = f"handoffs/{row['name']}.json"
        (PACKAGE / "handoffs").mkdir(exist_ok=True)
        write_json_exclusive(PACKAGE / handoff_path, handoff)
        validate_handoff(PACKAGE / handoff_path, root=PACKAGE, schema_path=PACKAGE / "handoff.schema.json")
        cases.append({"name": row["name"], "seed_path": seed, "seed_sha256": row["structure_sha256"], "handoff_path": handoff_path})
    script = f'''#!/bin/bash
#SBATCH --job-name=fe110-c2-supp12
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=00:10:00
#SBATCH --chdir={REMOTE}
#SBATCH --output={REMOTE}/slurm-%j.out
#SBATCH --error={REMOTE}/slurm-%j.err
set -euo pipefail
: "${{SLURM_JOB_ID:?real Slurm job required}}"
: "${{REQUEST_SHA256:?request digest required}}"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
export PYTHONPATH={REMOTE}:{REMOTE}/runtime:/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor
export MPLCONFIGDIR={REMOTE}/cache/matplotlib XDG_CACHE_HOME={REMOTE}/cache/xdg TMPDIR={REMOTE}/tmp
export TORCH_HOME={REMOTE}/cache/torch HF_HOME={REMOTE}/cache/huggingface WANDB_MODE=disabled
mkdir -p "$MPLCONFIGDIR" "$XDG_CACHE_HOME" "$TMPDIR" "$TORCH_HOME" "$HF_HOME"
/home/sbq/sbq/ml_ts_acceleration/venv/bin/python {REMOTE}/worker.py run --request {REMOTE}/request.json --sha256 "$REQUEST_SHA256"
'''
    with (PACKAGE / "run.sbatch").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(script)
    request = {"document_kind": "fe110_c2_supplement_gpu_slurm", "execution_mode": "slurm", "remote_root": REMOTE,
        "source_review_sha256": REVIEW_SHA, "cases": cases, "model": {"path": MODEL_PATH, "sha256": MODEL_SHA},
        "limits": {"seed_max_steps": 80, "fmax_eV_per_A": .1, "LBFGS_maxstep_A": .2},
        "resources": {"GPU_count": 1, "CPU_count": 4, "memory_GB": 32, "wall_seconds": 600, "allocator_MiB": 16384},
        "boundaries": {"training": False, "model_promotion": False, "VASP": False, "CPU_fallback": False},
        "domain": {"status": "checkpoint_and_target_motif_calibration_not_established", "ranking_allowed": False,
            "note": "18 has7 adsorbate atoms beyond old2-6 envelope; old calibration binds another checkpoint."},
        "artifacts": [{"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p)} for p in sorted(PACKAGE.rglob("*")) if p.is_file()]}
    write_json_exclusive(PACKAGE / "request.json", request)
    write_json_exclusive(PACKAGE / "authorization.json", {"action": "RUN_GPU_ADSORPTION_RELAXATION",
        "user_authorized": True, "user_request": USER, "request_sha256": sha256_file(PACKAGE / "request.json"),
        "source_review_sha256": REVIEW_SHA, "VASP_authorized": False})
    write_json_exclusive(OUT / "preparation_receipt.json", {"request_sha256": sha256_file(PACKAGE / "request.json"),
        "cases": len(cases), "handoffs": "12 schema-v2 PASS", "source_review_sha256": REVIEW_SHA,
        "native_GPU_preflight": "must pass inside actual Slurm allocation before model loading", "submitted": False})
    print("PREPARED12 frozen inputs; real Slurm only; no training, CPU fallback or VASP")


if __name__ == "__main__":
    main()
