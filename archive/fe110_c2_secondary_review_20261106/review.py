"""Bounded existing-output collection and secondary adsorption-site diagnostics.

No model, scientific-job execution, acceptance or registry writes. Use the
canonical work repository and private source data; output files are write-once.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess

import numpy as np
from ase.io import read

from archive.fe110_adsorption_calibration_20261018.reviewed_trajectory_helpers import verify_frame
from archive.fe110_c2_site_coverage_20261106.audit import ROOT, SLAB, describe
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_batch import molecular_signature
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.adsorption.review_completed_batch import surface_equivalence
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.neb_agent.utils_vasp import parse_oszicar
from scripts.vasp_result_gate import final_scf_state, read_incar_values
from scripts.workflow_geometry import minimum_image_delta_xy


OUT = ROOT / "outputs/fe110_c2_secondary_review_20261106"
PRIOR = ROOT / "outputs/fe110_c2_site_coverage_20261106_final/evidence_checked.json"
PRIOR_SHA = "07cf68284879aaa2c4a31e3f30454ff7e53eb1e91f374e9eda7c510cda8cd6b9"
BASE = ROOT / "calculations/fe110_c2_adsorption_16_19_20261101"
GPU = BASE / "gpu_ft512_20261102_v1"
NAMES = [f"{n}_{letter}" for n in (16, 17) for letter in "ABC"]
SPECIES = ("05", "07", "09", "12", "13", "16", "17")
READER = ROOT / "archive/fe110_c2_dedup_20261021/tail_reader.py"


def collect() -> None:
    """Reuse the bounded reader; never fetch full OUTCAR or POTCAR contents."""
    OUT.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        folder = OUT / "sources" / name
        receipt = folder / "receipt.json"
        if receipt.exists():
            saved = load_json_object(receipt)
            if saved["exit_code"] or sha256_file(folder / "source.json") != saved["output_sha256"]:
                raise ValueError(f"preserve failed/changed collection: {name}")
            print("REUSED", name, flush=True)
            continue
        folder.mkdir(parents=True, exist_ok=False)
        submitted = load_json_object(GPU / "dft_submission_v1/inputs" / name / "submission_record.json")
        record = {"name": name, "job_id": submitted["job_id"], "remote_dir": submitted["remote_dir"],
                  "atom_count": 52, "potcar_sha256": submitted["potcar_sha256"]}
        code = "RECORDS=" + repr([record]) + "\n" + READER.read_text(encoding="utf-8")
        with (folder / "source.json").open("xb") as output, (folder / "stderr.txt").open("xb") as error:
            result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                                     "sunboquan-codex", "python3", "-"], input=code.encode("utf-8"),
                                    stdout=output, stderr=error, timeout=60, check=False)
        write_json_exclusive(receipt, {"exit_code": result.returncode,
            "reader_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
            "reader_source_sha256": sha256_file(READER), "output_sha256": sha256_file(folder / "source.json"),
            "collected_at": datetime.now(timezone.utc).isoformat(), "record": record, "remote_mutation": False})
        if result.returncode:
            raise RuntimeError(f"collection failed; see preserved stderr: {name}")
        print("COLLECTED", name, flush=True)


def signature(pose):
    try:
        return molecular_signature(pose)
    except ValueError:
        return None


def live_output(name: str, slab) -> dict:
    folder = OUT / "sources" / name
    receipt = load_json_object(folder / "receipt.json")
    if receipt["exit_code"] or sha256_file(folder / "source.json") != receipt["output_sha256"]:
        raise ValueError("failed or changed collection")
    source = load_json_object(folder / "source.json")
    if source["POTCAR_sha256"] != receipt["record"]["potcar_sha256"]:
        raise ValueError("POTCAR hash differs from submission")
    for filename, encoded in source["files"].items():
        target = folder / filename
        data = base64.b64decode(encoded, validate=True)
        if target.exists():
            if target.read_bytes() != data:
                raise ValueError(f"restored evidence changed: {target}")
        else:
            with target.open("xb") as handle:
                handle.write(data)
        if filename in ("POSCAR", "INCAR", "KPOINTS"):
            if sha256_file(target) != sha256_file(GPU / "dft300_v2" / name / filename):
                raise ValueError(f"remote input differs from submitted input: {name}/{filename}")
    initial, final = [read_poscar(folder / f) for f in ("POSCAR", "CONTCAR")]
    atoms = read(folder / "CONTCAR", format="vasp")
    atoms.pbc = [True, True, False]
    forces = verify_frame(atoms, source["frames"][-1])
    movable = np.array([flags != ("F", "F", "F") for flags in final.flags])
    fmax = float(np.linalg.norm(forces[movable], axis=1).max())
    electronic = final_scf_state(parse_oszicar(folder / "OSZICAR"), read_incar_values(folder / "INCAR"))
    compatible = (expanded_symbols(initial) == expanded_symbols(final) and initial.flags == final.flags
        and final.flags[:45] == slab.flags and np.allclose(final.cell, slab.cell, atol=1e-8, rtol=0)
        and np.max(np.abs(minimum_image_delta_xy(final.frac[:18] - slab.frac[:18]) @ slab.cell)) < 1e-7)
    target = read_poscar(BASE / "review_ready_v2" / name / "POSCAR")
    intact = signature(final) is not None and signature(final) == signature(target)
    return {"name": name, "stage": "existing_DFT_output_collected_for_secondary_review",
        **describe(folder / "CONTCAR", slab), "ionic_steps": source["total_steps"], "fmax_eV_A": fmax,
        "normal_completion": source["normal_completion"], "accuracy_marker": source["ionic_converged"],
        "electronic": electronic, "compatible": bool(compatible), "target_intact": intact,
        "numerically_converged": bool(source["normal_completion"] and source["ionic_converged"]
                                      and electronic["electronically_converged"] and fmax <= .02),
        "OUTCAR_sha256": source["OUTCAR_sha256"], "scheduler_state": "NOT_QUERIED",
        "scientific_acceptance": False}


def review() -> None:
    if (OUT / "evidence.json").exists():
        raise FileExistsError(OUT / "evidence.json")
    if sha256_file(PRIOR) != PRIOR_SHA:
        raise ValueError("prior stage evidence changed")
    slab = read_poscar(SLAB)
    prior = load_json_object(PRIOR)
    rows = [r for r in prior["rows"] if r["name"][:2] in SPECIES and r["stage"] in
            ("original_seed", "first_DFT_input_source_hash_verified", "cached_DFT_output")]
    for row in rows:
        if sha256_file(ROOT / row["path"]) != row["sha256"]:
            raise ValueError(f"stage structure changed: {row['path']}")
    rows += [live_output(name, slab) for name in NAMES]
    operations = surface_pose_symmetries(slab)
    comparisons = []
    for species in SPECIES:
        group = [r for r in rows if r["name"].startswith(species + "_")]
        seeds = [r for r in group if r["stage"] == "original_seed"]
        later = [r for r in group if r["stage"] != "original_seed"]
        for seed in seeds:
            for other in later:
                first, second = [read_poscar(ROOT / r["path"]) for r in (seed, other)]
                comparisons.append({"seed": seed["name"], "other": other["name"], "other_stage": other["stage"],
                    "same_molecular_signature": signature(first) == signature(second),
                    **surface_equivalence(first, second, slab, operations)})
    paths = [PRIOR, Path(__file__), READER, SLAB,
             ROOT / "configs/adsmind_lite/analysis_rules.yaml"]
    paths += [OUT / "sources" / name / filename for name in NAMES for filename in ("source.json", "receipt.json")]
    write_json_exclusive(OUT / "evidence.json", {"species": list(SPECIES), "rows": rows,
        "comparisons": comparisons, "source_files": source_file_manifest(paths),
        "comparison_caveat": "Raw-seed vs DFT RMSD is separation evidence, NOT a test of distinct minima.",
        "scientific_acceptance": False, "new_calculations": 0, "registry_written": False})
    for row in rows[-6:]:
        print(row["name"], row["ionic_steps"], round(row["fmax_eV_A"], 6),
              "INTACT" if row["target_intact"] else "CHANGED_CHEMISTRY",
              "FORCE_CONVERGED" if row["numerically_converged"] else "NOT_FORCE_CONVERGED")
    print("SECONDARY_REVIEW", len(rows), "stage records", len(comparisons), "diagnostic comparisons")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("collect", "review"))
    action = parser.parse_args().phase
    {"collect": collect, "review": review}[action]()
