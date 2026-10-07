"""Freeze one reviewed CHCO repair, then reuse the exclusive submission adapter."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from ase.io import read

from archive.fe110_five_c2_adsorption_20261006 import supplement_gpu_remote as remote
from scripts.aqcat25_handoff import atom_order_sha256, validate_handoff
from scripts.artifact_io import sha256_file, write_json

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
PACKAGE = BASE / "gpu_repair_v1"
EVIDENCE = BASE / "gpu_repair_submission_v1"
REMOTE = "/home/sbq/sbq/aqcat25_ts_pilot/fe110_five_c2_adsorption_20261007_gpu_repair_v1"
NAME = "03_extra2_repair_v1"


def freeze():
    if PACKAGE.exists():
        raise FileExistsError("Never overwrite frozen repair package")
    review_path = BASE / "supplement_repair_v1/repair_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["recipe"]["name"] == NAME
    assert review["geometry"]["verdict"] == "pass" and not review["geometry"]["warnings"]
    source = ROOT / review["structure_path"]
    assert sha256_file(source) == review["structure_sha256"]
    prior = BASE / "gpu_supplement_v1"
    batch = json.loads((prior / "batch_manifest.json").read_text())
    for item in batch["files"]:
        assert sha256_file(prior / item["path"]) == item["sha256"], item["path"]
    compatibility = json.loads((prior / "compatibility.json").read_text())
    assert compatibility["method_protocol_sha256"] == sha256_file(ROOT / "docs/01_METHOD_PROTOCOL.md")
    assert compatibility["clean_slab_sha256"] == review["slab_sha256"]
    atoms = read(source, format="vasp")
    fixed = sorted({int(i)+1 for c in atoms.constraints for i in c.get_indices()})
    assert atoms.get_chemical_symbols() == ["Fe"]*45 + ["C", "C", "O", "H"]
    assert fixed == list(range(1, 19)) and len(atoms.constraints) == 1
    PACKAGE.mkdir()
    write_json(PACKAGE / "reviewed_plan.json", {
        "user_authorization": "2026-10-07: 继续; scoped to the immediately proposed one repaired-seed bounded GPU pre-relaxation",
        "action": "SUBMIT_BOUNDED_AQCAT25_ADSORPTION_PRE_RELAXATION_ONLY",
        "repair_review_sha256": sha256_file(review_path),
        "source_kind": review["source_kind"],
        "selected": [{"name": NAME, "structure_sha256": review["structure_sha256"]}],
        "prior_runtime_manifest_sha256": sha256_file(prior / "batch_manifest.json"),
        "checkpoint_sha256": batch["checkpoint_sha256"],
        "limits": {"steps_per_candidate": 80, "fmax_eV_per_A": 0.10,
                   "gpu_count": 1, "cpu_count": 4, "host_memory_GiB": 32, "walltime_minutes": 30},
        "constraints": review["constraints"],
        "chemical_review": "All six adsorbate pairs monitored; work-side exact-graph review after return is mandatory.",
        "restrictions": {"submit_vasp": False, "fine_tune": False,
                         "automatic_resubmit": False, "scientific_acceptance": False},
    })
    for relative in ["compatibility.json", "preflight.py", "runtime_patch_provenance.json"] + [
        "runtime/"+p.name for p in (prior / "runtime").iterdir() if p.is_file()
    ]:
        target = PACKAGE / relative
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(prior / relative, target)
    directory = PACKAGE / NAME
    directory.mkdir()
    shutil.copyfile(source, directory / "POSCAR")
    doc = json.loads((prior / "03_extra2/handoff.json").read_text())
    doc["handoff_id"] = "fe110_five_c2_20261007_" + NAME
    doc["source_workflow_sha256"] = sha256_file(PACKAGE / "reviewed_plan.json")
    doc["candidate_structure"].update(sha256=sha256_file(directory / "POSCAR"),
                                     atom_order_sha256=atom_order_sha256(atoms.get_chemical_symbols()))
    doc["adsorption"].update(evidence_gated_plan_sha256=doc["source_workflow_sha256"],
                            identity_and_connectivity=review["identity"],
                            intended_motif=json.dumps(review["recipe"], ensure_ascii=False))
    write_json(directory / "handoff.json", doc)
    validate_handoff(directory / "handoff.json", root=directory)
    script = (prior / "batch_job.sh").read_bytes()
    assert script.count(batch["remote_root"].encode()) == 1
    script = script.replace(batch["remote_root"].encode(), REMOTE.encode())
    script = script.replace(b"--job-name=fe110-c2-supp5", b"--job-name=fe110-chco-repair1")
    script = script.replace(b"--time=02:00:00", b"--time=00:30:00")
    (PACKAGE / "batch_job.sh").write_bytes(script)
    write_json(PACKAGE / "batch_manifest.json", {
        "remote_root": REMOTE, "checkpoint_sha256": batch["checkpoint_sha256"],
        "handoffs": [{"name": NAME, "handoff_sha256": sha256_file(directory / "handoff.json")}],
        "files": [{"path": p.relative_to(PACKAGE).as_posix(), "sha256": sha256_file(p)}
                  for p in sorted(PACKAGE.rglob("*")) if p.is_file()],
    })
    print(json.dumps({"status": "WORK_BEFORE_TRANSFER_PASS", "candidate_count": 1,
                      "manifest_sha256": sha256_file(PACKAGE / "batch_manifest.json")}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["freeze", "upload", "preflight", "submit"])
    args = parser.parse_args()
    if args.action == "freeze":
        freeze()
        return
    remote.PACKAGE, remote.EVIDENCE, remote.EXPECTED_REMOTE = PACKAGE, EVIDENCE, REMOTE
    sys.argv = [sys.argv[0], args.action]
    remote.main()


if __name__ == "__main__":
    main()
