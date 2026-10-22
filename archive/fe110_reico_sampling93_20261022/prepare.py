"""Prepare the 93 remaining frozen random families; no remote execution."""
from __future__ import annotations

import json
import shutil
import tarfile
from collections import Counter
from pathlib import Path

import yaml
from ase.io import read

from archive.fe110_adsorption_validation_20261018.runtime import verify
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
GEOMETRY = ROOT / "calculations/fe110_reico_pilot300_20261022/geometry_v1"
PRIOR = ROOT / "calculations/fe110_reico_pilot300_20261022/sampling6_v1"
DEST = ROOT / "calculations/fe110_reico_pilot300_20261022/sampling93_v1"
REMOTE = "/home/sbq/sbq/aqcat25_ts_pilot/reico_sampling93_20261022_v1"
EXCEPTION = "fe110_reico_sampling93_20261022"
AUTH = ROOT / "docs/reviews/fe110_reico_sampling93_20261022/user_authorization.md"


def copy(source, relative):
    target = DEST / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    shutil.copy2(source, target)
    return {"path": Path(relative).as_posix(), "sha256": sha256_file(target)}


def prepare():
    DEST.mkdir(exist_ok=False)
    summary = load_json_object(GEOMETRY / "summary_0100.json")
    prior = load_json_object(PRIOR / "validation_request.json")
    completed = load_json_object(PRIOR / "sampling_review.json")
    excluded = {r["family_id"] for r in completed["cases"]}
    assert len(excluded) == 6 and summary["generated"] == 99
    families = [r for r in summary["families"] if r["status"] == "CPU_GEOMETRY_CANDIDATE"
                and r["family_id"] not in excluded]
    assert len(families) == 93
    artifacts = [copy(GEOMETRY / "summary_0100.json", "evidence/generation_summary.json"),
                 copy(GEOMETRY / "inputs/config.json", "evidence/geometry_config.json"),
                 copy(GEOMETRY / "inputs/slab.POSCAR", "evidence/slab.POSCAR"),
                 copy(AUTH, "evidence/user_authorization.md")]
    rows = []
    for family in families:
        name = family["family_id"]
        directory = GEOMETRY / "families" / name
        record = load_json_object(directory / "family.json")
        assert record["status"] == "CPU_GEOMETRY_CANDIDATE"
        assert sha256_file(directory / "POSCAR") == record["poscar_sha256"]
        atoms = read(directory / "POSCAR", format="vasp")
        structure = copy(directory / "POSCAR", "samples/" + name + ".vasp")
        source = copy(directory / "family.json", "sources/" + name + ".json")
        artifacts.extend([structure, source])
        rows.append({"sample_id": name, "source_name": name, "composition": record["composition"],
                     "partition": record["partition"], "structure_path": structure["path"],
                     "structure_sha256": structure["sha256"], "symbols": atoms.get_chemical_symbols(),
                     "fixed_atom_indices_0based": list(range(18)), "family_record_path": source["path"],
                     "family_record_sha256": source["sha256"]})
    source = {"document_kind": "frozen_reico_unlabeled_sampling_sources", "samples": rows,
              "generation_summary_path": artifacts[0]["path"], "generation_summary_sha256": artifacts[0]["sha256"],
              "slab_path": "evidence/slab.POSCAR", "existing_six_families_excluded": sorted(excluded),
              "reference_DFT_labels_present": False}
    source_path = DEST / "evidence/source_inventory.json"
    write_json_exclusive(source_path, source)
    source_sha = sha256_file(source_path)
    artifacts.append({"path": "evidence/source_inventory.json", "sha256": source_sha})
    exception = {"authorized_by": "user_explicit_20261022_continue_sampling_and_deduplication",
                 "authorizing_user_request": "可以的继续", "scope": "remaining93_frozen_random_families_short_sampling_only",
                 "remote_root": REMOTE, "canonical_remote_boundary": "/home/ubuntu/hdd/sbq/sbq",
                 "gpu_index": prior["gpu_index"], "gpu_uuid": prior["gpu_uuid"],
                 "execution_mode": "direct_no_scheduler", "executor": "archive/fe110_adsorption_validation_20261018/runtime.py",
                 "model_backend": "aqcat25", "candidate_checkpoint_sha256": prior["models"]["candidate"]["sha256"],
                 "source_manifest_sha256": source_sha, "generation_config_sha256": prior["generation_config_sha256"],
                 "sample_count": 93, "source_names": sorted(r["sample_id"] for r in rows),
                 "sample_role": "frozen_family_unlabeled_geometry_sampling", "limits": prior["limits"],
                 "max_wall_seconds": 600, "max_return_bytes": 96_000_000,
                 "requires_current_user_execution_authorization": True, "automatic_retry": False,
                 "training": False, "new_VASP": False, "production_promotion": False}
    # Add only this new task-owned exception to each source history.
    release = Path(r"C:\Users\86177\.codex\worktrees\fe110-reico-pilot300\work")
    for root in (ROOT, release):
        path = root / "configs/execution_backends.yaml"
        text = path.read_text(encoding="utf-8")
        assert EXCEPTION not in text
        block = yaml.safe_dump({EXCEPTION: exception}, sort_keys=False, allow_unicode=True)
        block = "".join("      " + line if line.strip() else line for line in block.splitlines(keepends=True))
        assert text.count("    direct_execution_exceptions:\n") == 1
        text = text.replace("    direct_execution_exceptions:\n", "    direct_execution_exceptions:\n" + block, 1)
        path.write_text(text, encoding="utf-8", newline="\n")
    policy = copy(ROOT / "configs/execution_backends.yaml", "backend_policy.yaml")
    artifacts.append(policy)
    for source_file, target in (
            (ROOT / "archive/fe110_adsorption_validation_20261018/runtime.py", "runtime/runtime.py"),
            (ROOT / "archive/fe110_adsorption_validation_20261018/validation_helpers.py", "runtime/validation_helpers.py"),
            (ROOT / "scripts/adsorption/reico_sampling.py", "runtime/reico_sampling.py")):
        artifacts.append(copy(source_file, target))
    request = {"document_kind": "adsorption_bounded_random_sampling", "schema_version": 1,
               "run_id": "direct-fe110-reico-sampling93-20261022-v1", "exception_id": EXCEPTION,
               "remote_root": REMOTE, "execution_mode": "direct_no_scheduler", "scheduler_job_id": None,
               "gpu_index": exception["gpu_index"], "gpu_uuid": exception["gpu_uuid"],
               "max_wall_seconds": 600, "max_return_bytes": 96_000_000, "limits": prior["limits"],
               "models": prior["models"], "samples": rows, "sample_role": exception["sample_role"],
               "geometry_cases": [], "source_manifest_path": "evidence/source_inventory.json",
               "source_manifest_sha256": source_sha, "generation_config_path": "evidence/geometry_config.json",
               "generation_config_sha256": prior["generation_config_sha256"],
               "policy": policy, "artifacts": artifacts,
               "scientific_boundaries": {"training": False, "new_VASP": False, "production_promotion": False,
                                         "measured_acceleration": False, "maximum_optimizer_updates": 93 * 20}}
    write_json_exclusive(DEST / "validation_request.json", request)
    write_json_exclusive(DEST / "submission_authorization.json", {"user_authorized": True,
        "action": "RUN_GPU_REICO_BOUNDED_SAMPLING", "request_sha256": sha256_file(DEST / "validation_request.json"),
        "user_request": "可以的继续", "source_path": str(AUTH.relative_to(ROOT)),
        "source_sha256": sha256_file(AUTH), "reviewer": "Codex"})
    verify(DEST / "validation_request.json", DEST / "submission_authorization.json")
    with tarfile.open(DEST / "validation_bundle.tar", "x") as handle:
        for path in sorted(DEST.rglob("*")):
            if path.is_file() and path.name != "validation_bundle.tar":
                handle.add(path, arcname=path.relative_to(DEST).as_posix(), recursive=False)
    print(json.dumps({"status": "PACKAGE_VERIFIED", "families": len(rows),
                      "partitions": dict(Counter(r["partition"] for r in rows)),
                      "request_sha256": sha256_file(DEST / "validation_request.json"),
                      "archive_bytes": (DEST / "validation_bundle.tar").stat().st_size}))


if __name__ == "__main__":
    prepare()
