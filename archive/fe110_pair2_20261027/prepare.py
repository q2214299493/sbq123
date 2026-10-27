"""Freeze two existing molecular seeds before any new optimization result."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

from archive.fe110_fixed53_comparison_20261027.prepare import MODELS, copy_file
from archive.fe110_training512_20261027.prepare import RUNTIME
from archive.fe110_10b_lowforce_20261023.legacy_helpers import pose_distance, pose_variants
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import review, surface_pose_symmetries
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .runtime import verify

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "calculations/fe110_reico_pilot300_20261022/paired_relaxation2_20261027_v2"
PACKAGE = OUTPUT / "package"
REMOTE = "/home/sbq/sbq/fe110_paired_relaxation2_20261027_v2"
POLICY = ROOT / "configs/execution_backends.yaml"
EXCEPTION = "fe110_paired_relaxation2_20261027"
QUOTE = "同一起点的小规模C₂/C₃优化对照，再以一致的DFT标准检查终态和实际成本。"
AUTH = ROOT / "docs/reviews/fe110_pair2_20261027/user_authorization.md"


def selection():
    prior_path = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_geometry3_20261020_v1/validation_request.json"
    prior = load_json_object(prior_path)
    old = next(c for c in prior["geometry_cases"] if c["name"] == "10_A")
    care_root = ROOT / "calculations/fe110_care8_isomers_20260716"
    care_path, revision_path = care_root / "candidate_manifest.json", care_root / "revised/revision_manifest.json"
    care, revision = load_json_object(care_path), load_json_object(revision_path)
    c3 = next(r for r in revision["records"] if r["name"] == "05_C3H2O_FLJNAOYG_cfg2")
    if c3["geometry_review"]["verdict"] != "pass":
        raise ValueError("C3 revision not reviewed")
    slab_path = ROOT / care["source_slab"]
    if sha256_file(slab_path) != care["source_slab_sha256"]:
        raise ValueError("clean slab provenance changed")
    sources = [("10_A", ROOT / old["seed_source_path"], old["seed_sha256"], "C2H3"),
        ("C3_05", care_root / "revised/05_C3H2O_FLJNAOYG_cfg2/POSCAR", None, "C3H2O")]
    slab = read_poscar(slab_path)
    operations = surface_pose_symmetries(slab)
    data = ROOT / "calculations/fe110_reico_pilot300_20261022/combined_force_package_20261027_v3"
    manifest = load_json_object(data / "training_manifest.json")
    result = []
    for name, source, expected, formula in sources:
        if expected and sha256_file(source) != expected:
            raise ValueError("historical10A seed changed")
        pose = read_poscar(source)
        checked = review(pose, pose, list(range(45, len(pose.frac))))
        if checked["verdict"] != "pass":
            raise ValueError("source geometry rejected")
        variants = pose_variants(pose, operations)
        nearest = {}
        for split, rows in manifest["splits"].items():
            distances = [(pose_distance(read_poscar(data / r["structure_path"]), variants), r["sample_id"])
                for r in rows if r["composition"] == formula]
            nearest[split] = min(distances) if distances else None
        if any(nearest[split] and nearest[split][0] <= 0.2 for split in ["train", "development"]):
            raise ValueError("benchmark seed conflicts with training/development geometry")
        result.append({"name": name, "composition": formula, "seed_source_path": source.relative_to(ROOT).as_posix(),
            "seed_path": "geometry/" + name + "/POSCAR", "seed_sha256": sha256_file(source), "geometry_review": checked,
            "nearest_by_split_adsorbate_RMSD_A": nearest,
            "exposure": "historically_observed_system_not_new_blind" if name == "10_A" else "existing_reviewed_CARE_candidate_new_trajectory",
            "selection_basis": "preexisting_source_geometry_and_composition;not_new_model_error_or_endpoint_outcome"})
    return result, source_file_manifest([prior_path, care_path, revision_path, slab_path, data / "training_manifest.json"])


def prepare():
    if OUTPUT.exists():
        raise FileExistsError("preserve existing paired comparison attempt")
    cases, sources = selection()
    OUTPUT.mkdir(parents=True)
    (PACKAGE / "evidence").mkdir(parents=True)
    for case in cases:
        copy_file(ROOT / case["seed_source_path"], PACKAGE / case["seed_path"])
    write_json_exclusive(PACKAGE / "evidence/selection.json", {"cases": cases, "source_files": sources,
        "training_data_or_splits_changed": False, "paused_C3_DFT_jobs_resumed": False})
    for relative in [*RUNTIME, "archive/fe110_pair2_20261027/runtime.py",
            "archive/fe110_adsorption_validation_20261018/runtime.py", "archive/fe110_adsorption_validation_20261018/validation_helpers.py"]:
        copy_file(ROOT / relative, PACKAGE / "runtime" / relative)
    copy_file(ROOT / "docs/reviews/fe110_fixed53_comparison_20261027/comparison_summary.json", PACKAGE / "evidence/frozen_force_comparison.json")
    copy_file(AUTH, PACKAGE / "scope.md")
    sharing = copy.deepcopy(yaml.safe_load(POLICY.read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["direct_execution_exceptions"]["fe110_fixed53_force_comparison_20261027"]["gpu_sharing"])
    scope = {"remote_root": REMOTE, "gpu_index": 0, "gpu_uuid": "GPU-483c224e-cc19-13e2-24ad-c83efd14fa75", "gpu_sharing": sharing,
        "max_wall_seconds": 600, "CPU_count": 4, "memory_GB": 32,
        "models": {key: MODELS[key] for key in ["control", "new512"]},
        "cases": [{k: c[k] for k in ["name", "composition", "seed_path", "seed_sha256"]} for c in cases],
        "limits": {"seed_max_steps": 80, "fmax_eV_per_A": 0.1, "LBFGS_maxstep_A": 0.2}}
    exception = {"scope": scope, "authorizing_user_request": QUOTE, "canonical_remote_boundary": "/home/ubuntu/hdd/sbq/sbq",
        "automatic_retries": 0, "VASP_submission_authority": False}
    previous = OUTPUT / "previous_execution_backends.yaml"
    copy_file(POLICY, previous)
    text = POLICY.read_text(encoding="utf-8")
    marker = "    direct_execution_exceptions:\n"
    if text.count(marker) != 1 or EXCEPTION in yaml.safe_load(text)["backends"]["aqcat_gpu"]["direct_execution_exceptions"]:
        raise ValueError("ambiguous or duplicate policy exception")
    snippet = yaml.safe_dump({EXCEPTION: exception}, sort_keys=False, allow_unicode=True)
    POLICY.write_text(text.replace(marker, marker + "".join("      " + line + "\n" for line in snippet.splitlines()), 1), encoding="utf-8", newline="\n")
    copy_file(POLICY, PACKAGE / "execution_backends.yaml")
    request = {"scope": scope, "policy": {"path": "execution_backends.yaml", "sha256": sha256_file(PACKAGE / "execution_backends.yaml")},
        "exception_id": EXCEPTION, "execution_mode": "direct_no_scheduler", "scheduler_job_id": None,
        "boundaries": {"training": False, "model_reselection": False, "model_promotion": False, "VASP": False}}
    request["artifacts"] = [{"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p)} for p in sorted(PACKAGE.rglob("*")) if p.is_file()]
    write_json_exclusive(PACKAGE / "request.json", request)
    write_json_exclusive(PACKAGE / "authorization.json", {"action": "RUN_PAIRED_ML_RELAXATION", "user_authorized": True,
        "user_request": QUOTE, "request_sha256": sha256_file(PACKAGE / "request.json")})
    verify(PACKAGE / "request.json")
    write_json_exclusive(OUTPUT / "preparation_receipt.json", {"status": "PAIRED_ML_READY", "request_sha256": sha256_file(PACKAGE / "request.json"),
        "cases": cases, "source_files": source_file_manifest([Path(__file__), AUTH, previous, POLICY, PACKAGE / "request.json"])})
    print({"status": "PAIRED_ML_READY", "request_sha256": sha256_file(PACKAGE / "request.json")}, flush=True)


if __name__ == "__main__":
    prepare()
