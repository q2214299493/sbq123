"""Package the explicitly authorized, bounded adsorption pre-relaxation batch."""
from __future__ import annotations

import json
import shutil
import argparse
from pathlib import Path

from scripts.aqcat25_handoff import atom_order_sha256, validate_handoff
from scripts.artifact_io import sha256_file, sha256_json, write_json
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import expanded_symbols

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "calculations/fe110_five_c2_adsorption_20261006/gpu_batch_v1"
REMOTE = "/home/sbq/sbq/aqcat25_ts_pilot/fe110_five_c2_adsorption_20261006_gpu_v1"
CHECKPOINT_SHA = "e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50"


def main() -> None:
    global OUT, REMOTE
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", choices=["v1", "v2", "v3", "v4"], default="v1")
    args = parser.parse_args()
    OUT = OUT.with_name(f"gpu_batch_{args.version}")
    REMOTE = REMOTE.rsplit("_", 1)[0] + "_" + args.version
    if OUT.exists():
        raise FileExistsError(OUT)
    review_path = ROOT / "calculations/fe110_five_c2_adsorption_20261006/candidate_review.json"
    data = json.loads(review_path.read_text(encoding="utf-8"))
    selected = [c for c in data["candidates"] if not (
        (c["species_id"] == "02" and c["config_id"] == "0") or
        (c["species_id"] == "03" and c["config_id"] != "0"))]
    assert len(selected) == 12
    assert all(c["geometry_review"]["verdict"] == "pass" for c in selected)
    assert sha256_file(ROOT / data["slab"]) == data["slab_sha256"]
    OUT.mkdir()
    plan = {
        "user_authorization": "2026-10-06: 先提交gpu加速",
        "action": "SUBMIT_BOUNDED_AQCAT25_ADSORPTION_PRE_RELAXATION_ONLY",
        "candidate_review_sha256": sha256_file(review_path),
        "retrieval_evidence_sha256": sha256_file(ROOT / "archive/fe110_five_c2_adsorption_20261006/request_and_retrieval.json"),
        "literature_review_sha256": sha256_file(ROOT / "archive/fe110_five_c2_adsorption_20261006/literature_review.json"),
        "source_kind": "user_owned_local_CARE_predicted_poses_not_verified_stable_minima",
        "source_network_sha256": data["source_network_sha256"],
        "selected": [{"species_id": c["species_id"], "config_id": c["config_id"],
                      "source_structure_sha256": c["structure_sha256"]} for c in selected],
        "excluded": {"02/cfg0": "initial height gate needs review", "03/cfg1": "height-only variant of cfg0", "03/cfg2": "height-only variant of cfg0"},
        "limits": {"steps_per_candidate": 80, "fmax_eV_per_A": 0.10, "gpu_count": 1,
                   "walltime_minutes": 120, "submit_vasp": False},
        "review": "Initial geometry and connectivity pass; other surface-symmetry duplicates remain to be assessed after return. No stable/global-minimum claim.",
        "constraints": "Only original bottom18 Fe fixed; no artificial bond or height restraints. Connectivity monitored, not enforced by optimizer.",
    }
    write_json(OUT / "reviewed_plan.json", plan)
    compatibility = {"branch": "true_fe110_5layer_5x5x1", "slab_model": "true_fe110_fe45_5layer", "facet": "110",
                     "method_protocol_sha256": sha256_file(ROOT / "docs/01_METHOD_PROTOCOL.md"),
                     "clean_slab_sha256": data["slab_sha256"], "sigma_eV": 0.20,
                     "gpu_energy_is_not_DFT": True}
    write_json(OUT / "compatibility.json", compatibility)
    contacts = json.loads((ROOT / "archive/fe110_five_c2_adsorption_20261006/export_verification.json").read_text(encoding="utf-8"))["nearest_contacts"]
    handoffs = []
    for candidate in selected:
        name = f"{candidate['species_id']}_cfg{candidate['config_id']}"
        directory = OUT / name
        directory.mkdir()
        source = ROOT / candidate["structure"]
        assert sha256_file(source) == candidate["structure_sha256"]
        shutil.copyfile(source, directory / "POSCAR")
        poscar = read_poscar(source)
        symbols = expanded_symbols(poscar)
        fixed = [i + 1 for i, flags in enumerate(poscar.flags) if tuple(flags) == ("F", "F", "F")]
        assert fixed == list(range(1, 19))
        pairs = [{"label": f"internal_{a+46}_{b+46}", "atoms_1based": [a+46, b+46]}
                 for a, b in candidate["geometry_review"]["connectivity_edges_local_0based"]]
        current_contacts = next(c["nearest_contacts"] for c in contacts if c["species_id"] == candidate["species_id"] and c["config_id"] == candidate["config_id"])
        pairs.extend({"label": f"seed_surface_contact_{c['atom_index_zero_based']+1}",
                      "atoms_1based": [c["atom_index_zero_based"]+1, c["nearest_Fe_zero_based"]+1]} for c in current_contacts)
        document = {
            "schema_version": 2, "direction": "work_to_gpu", "workflow_kind": "adsorption",
            "handoff_id": f"fe110_five_c2_20261006_{name}",
            "source_workflow_sha256": sha256_file(OUT / "reviewed_plan.json"),
            "candidate_structure": {"path": "POSCAR", "sha256": sha256_file(source), "format": "vasp_poscar",
                                    "atom_count": len(symbols), "atom_order_sha256": atom_order_sha256(symbols)},
            "compatibility": {"branch": compatibility["branch"], "slab_model": compatibility["slab_model"],
                              "facet": "110", "sha256": sha256_file(OUT / "compatibility.json")},
            "model": {"identifier": "AQCat25 demo_single model.pt", "checkpoint_sha256": CHECKPOINT_SHA,
                      "fmax_eV_per_A": 0.10, "max_steps": 80},
            "selective_dynamics": {"fixed_atom_indices_1based": fixed, "free_atom_count": len(symbols)-len(fixed)},
            "adsorption": {
                "evidence_gated_plan_sha256": sha256_file(OUT / "reviewed_plan.json"),
                "clean_slab_sha256": data["slab_sha256"],
                "identity_and_connectivity": candidate["care_code"] + " " + candidate["connectivity"],
                "intended_motif": json.dumps(candidate["geometry_review"]["atom_site_details"], ensure_ascii=True),
                "surface_elements": ["Fe"],
                "adsorbate_atoms": [{"index_1based": i+1, "symbol": symbol, "role": "non_anchor" if symbol == "H" else "anchor"} for i, symbol in enumerate(symbols) if symbol != "Fe"],
                "connectivity_constraints": [], "monitored_pairs": pairs,
            },
            "restrictions": {"predicted_candidate_only": True, "submit_vasp": False,
                             "scientific_acceptance": False, "direct_gpu_to_vasp_handoff": False},
        }
        write_json(directory / "handoff.json", document)
        validate_handoff(directory / "handoff.json", root=directory)
        handoffs.append({"name": name, "handoff_sha256": sha256_file(directory / "handoff.json")})
    runtime = OUT / "runtime"
    runtime.mkdir()
    files = {
        "aqcat25_handoff.py": ROOT / "scripts/aqcat25_handoff.py",
        "artifact_io.py": ROOT / "scripts/artifact_io.py",
        "aqcat25_gpu_job.sh": ROOT / "scripts/aqcat25_gpu_job.sh",
        "aqcat25_mz73_env.sh": ROOT / "scripts/aqcat25_mz73_env.sh",
        "aqcat25_handoff.schema.json": ROOT / "configs/aqcat25_handoff.schema.json",
        "relax_endpoint_candidates.py": Path("C:/Users/86177/Desktop/机器学习/aqcat25_ts_pilot/relax_endpoint_candidates.py"),
    }
    for name, source in files.items():
        if name.endswith(".sh"):
            content = source.read_bytes().replace(b"\r\n", b"\n")
            if name == "aqcat25_mz73_env.sh" and args.version != "v1":
                # MZ73 /home/sbq/sbq is a verified symlink to /home/ubuntu/hdd/sbq/sbq.
                # Resolve the allowed root and all targets; retain lexical and canonical containment.
                line = b'  [ "$boundary" = /home/sbq/sbq ] || return 2\n'
                assert content.count(line) == 1
                content = content.replace(line, b'  [ -d "$boundary" ] || return 2\n')
            if name == "aqcat25_gpu_job.sh" and args.version == "v4":
                line = b'case "$GPU_ENV_SOURCE" in /home/sbq/sbq/*) ;; *) exit 2 ;; esac'
                assert content.count(line) == 1
                content = content.replace(line, b'GPU_ALLOWED_ROOT=$(realpath -e -- /home/sbq/sbq) || exit 2\ncase "$GPU_ENV_SOURCE" in "$GPU_ALLOWED_ROOT"/*) ;; *) exit 2 ;; esac')
            (runtime / name).write_bytes(content)
        else:
            shutil.copyfile(source, runtime / name)
    for name in ("preflight.py", "batch_job.sh"):
        content = (Path(__file__).parent / name).read_bytes()
        if name == "batch_job.sh":
            content = content.replace(b"fe110_five_c2_adsorption_20261006_gpu_v1", REMOTE.split("/")[-1].encode())
        (OUT / name).write_bytes(content)
    if args.version != "v1":
        write_json(OUT / "runtime_patch_provenance.json", {
            "failed_jobs": ["2136", "2137", "2138"] if args.version == "v4" else ["2136", "2137"], "model_started": False,
            "cause": "Canonical root guard incorrectly requires lexical root to equal its realpath; MZ73 root is a symlink.",
            "observed_lexical_root": "/home/sbq/sbq", "observed_real_root": "/home/ubuntu/hdd/sbq/sbq",
            "change": "Task-local environment helper resolves the allowed root and verifies every write target remains inside that canonical root. Global helper and prior package unchanged.",
            "environment_policy": "Pin writable cache/temp paths under the allowed root instead of inheriting scheduler scratch paths. Trace bootstrap to retain exact failures.",
        })
    batch = {"remote_root": REMOTE, "handoffs": handoffs, "checkpoint_sha256": CHECKPOINT_SHA,
             "files": [{"path": str(path.relative_to(OUT)).replace("\\", "/"), "sha256": sha256_file(path)}
                       for path in sorted(OUT.rglob("*")) if path.is_file()]}
    write_json(OUT / "batch_manifest.json", batch)
    print(json.dumps({"status": "WORK_BEFORE_TRANSFER_PASS", "candidate_count": len(handoffs),
                      "batch_sha256": sha256_file(OUT / "batch_manifest.json"), "remote_root": REMOTE}))


if __name__ == "__main__":
    main()
