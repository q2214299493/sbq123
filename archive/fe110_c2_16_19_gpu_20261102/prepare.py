"""Freeze twelve reviewed seeds and their standard work-to-GPU handoffs."""
from pathlib import Path

import yaml

from archive.fe110_pair2_20261027.runtime import verify
from scripts.adsorption.build_fe110_adsorption import read_poscar, expanded_symbols
from scripts.aqcat25_handoff import atom_order_sha256, validate_handoff
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2_adsorption_16_19_20261101"
SOURCE = BASE / "review_ready_v2"
OUTPUT = BASE / "gpu_ft512_20261102_v1"
PACKAGE = OUTPUT / "package"
POLICY = ROOT / "configs/execution_backends.yaml"
REMOTE = "/home/sbq/sbq/fe110_c2_16_19_ft512_20261102_v1"
EXCEPTION = "fe110_c2_16_19_ft512_20261102"


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256_file(source) != sha256_file(target):
            raise ValueError("preserve differing partial artifact: " + str(target))
        return
    with target.open("xb") as stream:
        stream.write(source.read_bytes())


def write_checked(target, document):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if load_json_object(target) != document:
            raise ValueError("preserve changed partial metadata: " + str(target))
    else:
        write_json_exclusive(target, document)


def prepare(*, resume_local=False):
    if OUTPUT.exists():
        if not resume_local or any(p.exists() for p in [PACKAGE / "request.json", PACKAGE / "authorization.json",
                OUTPUT / "preparation_receipt.json", OUTPUT / "upload_reservation.json", OUTPUT / "launch_reservation.json"]):
            raise FileExistsError("only an explicit pre-request local resume is supported; preserve submitted packages")
    manifest = load_json_object(SOURCE / "candidate_review.json")
    independent = load_json_object(SOURCE / "independent_verification.json")
    if (manifest["candidate_count"] != 12 or independent["status"] != "PASS_GEOMETRY_READBACK_ONLY"
            or independent["manifest_sha256"] != sha256_file(SOURCE / "candidate_review.json")):
        raise ValueError("the reviewed twelve-seed source changed")
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    exception = policy["backends"]["aqcat_gpu"]["direct_execution_exceptions"][EXCEPTION]
    scope = exception["scope"]
    expected = {r["name"]: r for r in scope["cases"]}
    if set(expected) != {r["name"] for r in manifest["candidates"]}:
        raise ValueError("policy/source candidate membership differs")
    OUTPUT.mkdir(exist_ok=resume_local)
    old = ROOT / "calculations/fe110_c2_adsorption_11_15_20261020/ft512_gpu_20261029_v1/package/runtime"
    overrides = {"archive/fe110_pair2_20261027/runtime.py", "archive/fe110_c2_16_19_gpu_20261102/adapter.py"}
    for path in old.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            relative = path.relative_to(old).as_posix()
            copy(ROOT / relative if relative in overrides else path, PACKAGE / "runtime" / relative)
    for relative in overrides:
        copy(ROOT / relative, PACKAGE / "runtime" / relative)
    copy(ROOT / "scripts/aqcat25_handoff.py", PACKAGE / "runtime/aqcat25_handoff.py")
    copy(ROOT / "scripts/artifact_io.py", PACKAGE / "runtime/artifact_io.py")
    copy(ROOT / "configs/aqcat25_handoff.schema.json", PACKAGE / "handoff.schema.json")
    copy(SOURCE / "candidate_review.json", PACKAGE / "evidence/source_geometry_review.json")
    copy(SOURCE / "independent_verification.json", PACKAGE / "evidence/source_readback.json")
    for name in ("request.json", "whitelist_screen.json", "literature_screening.json"):
        copy(BASE / name, PACKAGE / "evidence" / name)
    copy(POLICY, PACKAGE / "execution_backends.yaml")
    copy(ROOT / "configs/true_fe110_production.yaml", PACKAGE / "evidence/production_profile.yaml")
    write_checked(PACKAGE / "evidence/frozen_force_comparison.json", {
        "model_checkpoint_sha256": {"finetune": scope["models"]["finetune"]["sha256"]},
        "role": "frozen prior partial snapshot; uncalibrated seven/eight-adsorbate-atom candidates, not model promotion"})
    for row in manifest["candidates"]:
        case = expected[row["name"]]
        path = Path(row["structure"])
        if (sha256_file(path) != row["structure_sha256"] or case["seed_sha256"] != row["structure_sha256"]
                or row["geometry_review"]["verdict"] != "pass" or case["composition"] != row["formula"]):
            raise ValueError("reviewed pose changed: " + row["name"])
        copy(path, PACKAGE / case["seed_path"])
        pose = read_poscar(path)
        symbols = expanded_symbols(pose)
        handoff = {"schema_version": 2, "direction": "work_to_gpu", "workflow_kind": "adsorption",
            "handoff_id": EXCEPTION + "_" + row["name"],
            "source_workflow_sha256": sha256_file(SOURCE / "candidate_review.json"),
            "candidate_structure": {"path": case["seed_path"], "sha256": case["seed_sha256"],
                "format": "vasp_poscar", "atom_count": len(symbols), "atom_order_sha256": atom_order_sha256(symbols)},
            "compatibility": {"branch": "true_fe110_5layer_5x5x1", "sha256": sha256_file(PACKAGE / "evidence/production_profile.yaml"),
                "slab_model": "Fe45_bottom18_fixed", "facet": "Fe(110)"},
            "model": {"identifier": "AQCat25_ft512_frozen_partial_cdd391d", "checkpoint_sha256": scope["models"]["finetune"]["sha256"],
                "fmax_eV_per_A": scope["limits"]["fmax_eV_per_A"], "max_steps": scope["limits"]["seed_max_steps"]},
            "selective_dynamics": {"fixed_atom_indices_1based": list(range(1, 19)), "free_atom_count": len(symbols) - 18},
            "adsorption": {"evidence_gated_plan_sha256": sha256_file(SOURCE / "candidate_review.json"),
                "clean_slab_sha256": manifest["source_slab_sha256"], "identity_and_connectivity": row["connectivity"],
                "intended_motif": "reviewed exploratory seed " + row["name"] + "; placement anchors only, no artificial bond restraints",
                "surface_elements": ["Fe"],
                "adsorbate_atoms": [{"index_1based": i + 1, "symbol": symbols[i], "role": "non_anchor" if symbols[i] == "H" else "anchor"}
                    for i in range(45, len(symbols))],
                "connectivity_constraints": [],
                "monitored_pairs": [{"label": b["pair"], "atoms_1based": [i + 1 for i in b["atoms_0based"]]}
                    for b in row["bond_distances"]]},
            "restrictions": {"predicted_candidate_only": True, "submit_vasp": False,
                "scientific_acceptance": False, "direct_gpu_to_vasp_handoff": False}}
        target = PACKAGE / "handoffs" / (row["name"] + ".json")
        write_checked(target, handoff)
        validate_handoff(target, root=PACKAGE, schema_path=PACKAGE / "handoff.schema.json")
    request = {"document_kind": "fe110_c2_16_19_ft512_relaxation", "scope": scope,
        "policy": {"path": "execution_backends.yaml", "sha256": sha256_file(PACKAGE / "execution_backends.yaml")},
        "exception_id": EXCEPTION, "execution_mode": "direct_no_scheduler", "scheduler_job_id": None,
        "domain": {"status": "out_of_calibrated_domain", "adsorbate_atoms": [7, 8],
            "use": "candidate_pre_relaxation_only", "ranking_allowed": False},
        "boundaries": {"training": False, "model_reselection": False, "model_promotion": False, "VASP": False}}
    request["artifacts"] = [{"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p)}
        for p in sorted(PACKAGE.rglob("*")) if p.is_file()]
    write_json_exclusive(PACKAGE / "request.json", request)
    write_json_exclusive(PACKAGE / "authorization.json", {"action": "RUN_PAIRED_ML_RELAXATION", "user_authorized": True,
        "user_request": exception["authorizing_user_request"], "sharing_authorization": exception["sharing_authorization"],
        "request_sha256": sha256_file(PACKAGE / "request.json")})
    verify(PACKAGE / "request.json")
    write_json_exclusive(OUTPUT / "preparation_receipt.json", {"status": "LOCAL_PASS_12_SEEDS_AND_HANDOFFS",
        "request_sha256": sha256_file(PACKAGE / "request.json"), "GPU_seconds_cap": 600,
        "allocator_limit_MiB": 16384, "max_total_ML_steps": 960, "shared_resident_processes_not_stopped": True,
        "domain": request["domain"], "VASP_submitted": False,
        "resumed_pre_request_local_package": resume_local,
        "recovered_local_failure": "missing handoffs parent directory; no remote upload or model launch" if resume_local else None})
    print("PREPARED12 standard handoffs; sharedGPU0/600s/16GiB; no launch")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--resume-local", action="store_true")
    prepare(resume_local=parser.parse_args().resume_local)
