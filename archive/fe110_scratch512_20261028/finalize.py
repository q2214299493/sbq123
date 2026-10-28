"""Freeze reviewable requests and draft scoped exceptions;grant no execution."""
import copy
from pathlib import Path, PurePosixPath
import shutil

import numpy as np
from ase.db import connect
from ase.io import read
import yaml

from scripts.adsorption.nequip_force_job import verify
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .environment import ENV_ROOT
from .prepare import MANIFEST_SHA, REMOTE, SOURCE, config
from .probe import OUTPUT, ROOT

RUNTIME = ["scripts/__init__.py", "scripts/adsorption/__init__.py", "scripts/artifact_io.py",
    "scripts/adsorption/direct_gpu_batch.py", "scripts/adsorption/nequip_force_runtime.py", "scripts/adsorption/nequip_force_job.py"]


def verify_exports():
    manifest = load_json_object(SOURCE / "training_manifest.json")
    checked, grades = 0, {}
    for split in ["train", "development"]:
        records = manifest["splits"][split]
        frames = read(OUTPUT / "package/nequip/data" / (split + ".xyz"), index=":", format="extxyz")
        with connect(SOURCE / (split + ".db")) as db:
            originals = [r.toatoms() for r in db.select()]
        if len(frames) != len(records):
            raise ValueError("split row count changed")
        for frame, original, row in zip(frames, originals, records, strict=True):
            reference = read(SOURCE / row["structure_path"], format="vasp")
            if not np.allclose(frame.positions, reference.positions, rtol=0, atol=1e-12):
                raise ValueError("source POSCAR correspondence failed")
            for a, b in [(frame.positions, original.positions), (frame.cell.array, original.cell.array), (frame.pbc, original.pbc),
                         (frame.get_forces(apply_constraint=False), row["forces_eV_per_A"]),
                         (frame.arrays["force_loss_weights"], row["proposed_per_atom_loss_weights"])]:
                if not np.array_equal(a, b):
                    raise ValueError("independent export replay failed")
            if frame.get_chemical_symbols() != row["symbols"] or frame.info["sample_id"] != row["sample_id"]:
                raise ValueError("frame/atom identity changed")
            if frame.info["magnetic_review_level"] != row["magnetic_review_level"] or "energy" in frame.calc.results:
                raise ValueError("magnetic/force-only scope changed")
            if split == "train":
                level = row["magnetic_review_level"]
                grades[level] = grades.get(level, 0) + 1
            checked += 1
    write_json_exclusive(OUTPUT / "export_verification_v2.json", {"status": "PASS", "frames_checked": checked,
        "train_magnetic_levels": grades, "heldout_exported": False, "manifest_sha256": sha256_file(SOURCE / "training_manifest.json"),
        "source_files": source_file_manifest([SOURCE / "training_manifest.json", SOURCE / "train.db", SOURCE / "development.db",
            OUTPUT / "package/nequip/data/export.json", OUTPUT / "package/nequip/data/train.xyz", OUTPUT / "package/nequip/data/development.xyz"])})


def finalize():
    verify_exports()
    root = OUTPUT / "package/nequip_v2"
    shutil.copytree(OUTPUT / "package/nequip/data", root / "data")
    runtime = root / "runtime"
    for name in RUNTIME:
        target = runtime / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    summary = load_json_object(root / "data/export.json")
    cfg = config(PurePosixPath(REMOTE) / "nequip_v2/data", PurePosixPath(REMOTE) / "nequip_v2/output", summary["training_only_initialization"])
    cfg["trainer"]["callbacks"].append({"_target_": "scripts.adsorption.nequip_force_runtime.CUDAEvidence"})
    with (root / "config_reviewed.yaml").open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(cfg, handle, sort_keys=False)
    paths = [root / "config_reviewed.yaml", root / "data/train.xyz", root / "data/development.xyz", root / "data/export.json",
        *[runtime / name for name in RUNTIME]]
    request = {"document_kind": "fe110_nequip_force_scratch_trial", "training_authorized": False,
        "source_manifest_sha256": MANIFEST_SHA, "counts": {"train": 512, "development": 78},
        "initialization": "random_no_checkpoint", "framework_version": "0.19.1", "remote_root": REMOTE + "/nequip_v2",
        "entrypoint": ENV_ROOT + "/venv/bin/nequip-train", "config_path": "config_reviewed.yaml", "max_wall_seconds": 1800,
        "GPU_count": 1, "CPU_count": 4, "memory_GB": 32, "automatic_retries": 0, "gpu_index": 1,
        "gpu_uuid": "GPU-450609b3-d1fd-ac33-d03a-79891be402da", "energy_fitting": False,
        "artifacts": [{"path": p.relative_to(root).as_posix(), "sha256": sha256_file(p)} for p in paths]}
    write_json_exclusive(root / "training_request.json", request)
    digest = sha256_file(root / "training_request.json")
    verify(root / "training_request.json", digest)
    ft = OUTPUT / "package/finetune/control/training_request.json"
    ft_sha = sha256_file(ft)
    policy = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))
    draft = copy.deepcopy(policy["backends"]["aqcat_gpu"]["direct_execution_exceptions"]["fe110_force_training512_gpu0_20261027"])
    draft.update(authorized_by="PENDING_HUMAN_BUDGET_CONFIRMATION", authorizing_user_request=None,
        scope="one_twenty_epoch_force_only512_control", remote_root=REMOTE + "/finetune", gpu_index=1, gpu_uuid=request["gpu_uuid"],
        max_epochs=20, max_optimizer_steps_per_arm=10240, arm_request_sha256={"control": ft_sha})
    for obsolete in ["gpu_sharing", "original_comparison_sha256", "supersedes_unstarted_exception"]:
        draft.pop(obsolete, None)
    write_json_exclusive(OUTPUT / "execution_exception_proposals_v2.json", {"status": "PROPOSED_NOT_ACTIVE_POLICY",
        "fe110_force_training512_comparison20_20261028": draft,
        "fe110_nequip_scratch512_20261028": {"authorized_by": "PENDING_HUMAN_BUDGET_CONFIRMATION",
            "request_sha256": digest, "remote_root": request["remote_root"], "gpu_index": 1, "gpu_uuid": request["gpu_uuid"],
            "max_wall_seconds": 1800, "model_backend": "nequip_force_scratch", "scope": "Fe110_only_force_model_training_not_general_backend_permission"}})
    final = {"status": "LOCAL_REQUESTS_FROZEN_NATIVE_CPU_PREFLIGHT_PENDING", "GPU_training_authorized": False,
        "nequip_request_sha256": digest, "finetune_request_sha256": ft_sha, "sequential_GPU1_walltime_cap_seconds": 3600,
        "heldout53_and_observed16_isolated": True, "canonical_backend_policy_modified": False,
        "source_files": source_file_manifest([Path(__file__), root / "training_request.json", ft, OUTPUT / "export_verification_v2.json",
            OUTPUT / "finetune_preflight.json", *[ROOT / name for name in RUNTIME]])}
    write_json_exclusive(OUTPUT / "reviewed_requests_v2.json", final)
    print({k: v for k, v in final.items() if k != "source_files"})


if __name__ == "__main__":
    finalize()
