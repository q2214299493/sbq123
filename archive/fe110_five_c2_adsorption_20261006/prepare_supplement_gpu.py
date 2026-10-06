"""Freeze the five user-authorized supplemental adsorption GPU inputs."""
from __future__ import annotations

import itertools
import json
import shutil
from pathlib import Path

from ase.io import read

from scripts.aqcat25_handoff import atom_order_sha256, validate_handoff
from scripts.artifact_io import sha256_file, write_json

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
OUT = BASE / "gpu_supplement_v1"
REMOTE = "/home/sbq/sbq/aqcat25_ts_pilot/fe110_five_c2_adsorption_20261006_gpu_supplement_v1"
NAMES = ["01_extra1", "02_extra1", "02_extra2", "03_extra1", "03_extra2"]


def main():
    if OUT.exists():
        raise FileExistsError("Frozen packages must not be overwritten")
    review_path = BASE / "supplement_v1/candidate_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    candidates = review["candidates"]
    assert [c["name"] for c in candidates] == NAMES
    prior = BASE / "gpu_batch_v4"
    prior_manifest = json.loads((prior / "batch_manifest.json").read_text())
    hashes = {r["path"]: r["sha256"] for r in prior_manifest["files"]}
    for candidate in candidates:
        assert candidate["geometry"]["verdict"] == "pass"
        assert not candidate["geometry"]["warnings"]
        assert sha256_file(ROOT / candidate["structure_path"]) == candidate["structure_sha256"]
    OUT.mkdir()
    plan = {
        "user_authorization": "2026-10-06: 提交gpu加速",
        "action": "SUBMIT_BOUNDED_AQCAT25_ADSORPTION_PRE_RELAXATION_ONLY",
        "candidate_review_sha256": sha256_file(review_path),
        "original_review_sha256": review["source_review_sha256"],
        "prior_runtime_manifest_sha256": sha256_file(prior / "batch_manifest.json"),
        "source_kind": "reviewed_user_owned_local_CARE_template_variants_not_verified_minima",
        "selected": [{"name": c["name"], "structure_sha256": c["structure_sha256"]} for c in candidates],
        "checkpoint_sha256": prior_manifest["checkpoint_sha256"],
        "limits": {"steps_per_candidate": 80, "fmax_eV_per_A": 0.10,
                   "gpu_count": 1, "cpu_count": 4, "host_memory_GiB": 32,
                   "walltime_minutes": 120},
        "constraints": "Only bottom18 Fe fixed. No internal-bond, height or adsorption-site forces.",
        "chemical_review": "All adsorbate pairs monitored. Empty runner constraint list is not a chemistry verdict; canonical exact-graph review is required after return.",
        "restrictions": {"submit_vasp": False, "fine_tune": False,
                         "automatic_resubmit": False, "scientific_acceptance": False},
    }
    write_json(OUT / "reviewed_plan.json", plan)
    compatibility = json.loads((prior / "compatibility.json").read_text())
    assert compatibility["clean_slab_sha256"] == review["slab_sha256"]
    assert compatibility["method_protocol_sha256"] == sha256_file(ROOT / "docs/01_METHOD_PROTOCOL.md")
    shutil.copyfile(prior / "compatibility.json", OUT / "compatibility.json")
    template = json.loads((prior / "01_cfg0/handoff.json").read_text())
    handoffs = []
    for candidate in candidates:
        name = candidate["name"]
        directory = OUT / name
        directory.mkdir()
        shutil.copyfile(ROOT / candidate["structure_path"], directory / "POSCAR")
        atoms = read(directory / "POSCAR", format="vasp")
        symbols = atoms.get_chemical_symbols()
        fixed = sorted({int(i)+1 for constraint in atoms.constraints for i in constraint.get_indices()})
        assert fixed == list(range(1, 19))
        doc = json.loads(json.dumps(template))
        doc["handoff_id"] = "fe110_five_c2_20261006_supplement_" + name
        doc["source_workflow_sha256"] = sha256_file(OUT / "reviewed_plan.json")
        doc["candidate_structure"].update(sha256=sha256_file(directory / "POSCAR"),
                                         atom_count=len(atoms), atom_order_sha256=atom_order_sha256(symbols))
        doc["compatibility"]["sha256"] = sha256_file(OUT / "compatibility.json")
        doc["selective_dynamics"] = {"fixed_atom_indices_1based": fixed, "free_atom_count": len(atoms)-len(fixed)}
        doc["adsorption"].update(
            evidence_gated_plan_sha256=doc["source_workflow_sha256"],
            identity_and_connectivity=candidate["care_code"] + " " + candidate["connectivity"],
            intended_motif=json.dumps({k: candidate[k] for k in ("site", "anchor_global_0based", "azimuth_deg", "tilt_deg", "hypothesis")}),
            adsorbate_atoms=[{"index_1based": i+1, "symbol": s, "role": "non_anchor" if s == "H" else "anchor"}
                             for i, s in enumerate(symbols) if s != "Fe"],
            connectivity_constraints=[],
            monitored_pairs=[{"label": f"adsorbate_{i+1}_{j+1}", "atoms_1based": [i+1, j+1]}
                             for i, j in itertools.combinations(range(45, len(atoms)), 2)])
        write_json(directory / "handoff.json", doc)
        validate_handoff(directory / "handoff.json", root=directory)
        handoffs.append({"name": name, "handoff_sha256": sha256_file(directory / "handoff.json")})
    for relative in ["preflight.py", "runtime_patch_provenance.json"] + ["runtime/" + p.name for p in (prior / "runtime").iterdir() if p.is_file()]:
        assert sha256_file(prior / relative) == hashes[relative]
        target = OUT / relative
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(prior / relative, target)
    script = (prior / "batch_job.sh").read_bytes()
    assert sha256_file(prior / "batch_job.sh") == hashes["batch_job.sh"]
    assert script.count(prior_manifest["remote_root"].encode()) == 1
    script = script.replace(prior_manifest["remote_root"].encode(), REMOTE.encode())
    script = script.replace(b"--job-name=fe110-five-c2-ads", b"--job-name=fe110-c2-supp5")
    (OUT / "batch_job.sh").write_bytes(script)
    write_json(OUT / "batch_manifest.json", {
        "remote_root": REMOTE, "handoffs": handoffs,
        "checkpoint_sha256": prior_manifest["checkpoint_sha256"],
        "files": [{"path": p.relative_to(OUT).as_posix(), "sha256": sha256_file(p)}
                  for p in sorted(OUT.rglob("*")) if p.is_file()],
    })
    print(json.dumps({"status": "WORK_BEFORE_TRANSFER_PASS", "candidate_count": 5,
                      "manifest_sha256": sha256_file(OUT / "batch_manifest.json")}))


if __name__ == "__main__":
    main()
