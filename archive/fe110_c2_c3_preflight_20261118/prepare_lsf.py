"""Bind the reviewed nine force-label inputs to LSF ranks and runtime limits."""
from __future__ import annotations

import argparse
from pathlib import Path

from ase.data import atomic_numbers, covalent_radii
from ase.io import read
import numpy as np

from archive.fe110_joint_priority_20261117.analyze import BASE, guard_hashes, load, save, sha, table
from scripts.neb_agent.submission import InputBundle, _bsub_command, preflight
from .prepare import checked, copy_bound


PREPARED = BASE / "c2_c3_label_preflight_20261118_v1"
SOURCE_SHA = "e0ff8e82068b4b20451e8909de142b5a9a449409d0ec4ca8e73c0a6dea129a7a"
POTCAR_SHA = "789d410ebfae1e818dfd0aec0ee85ed2f07f4b15201a5a592442350f2a8f2b90"
JOINT_SHA = "6f8d2662558241ee36b7ab2f4159283e78feb71913a84bfd9f6c0d78b232709c"
DEFERRED = "family_0001_step002"
ACTION = "SUBMIT_DIAGNOSTIC_VASP"
REMOTE_ROOT = "~/sbq/Fe110/reico_c2_c3_label9_20261118_v1"


def oxygen_contacts(path: Path) -> dict:
    atoms = read(path, format="vasp")
    symbols = atoms.get_chemical_symbols()
    if symbols[:45] != ["Fe"] * 45 or symbols[45:] != ["C", "C", "O", "H"]:
        raise ValueError("Unexpected formula or atom order for the O–Fe review")
    oxygen = symbols.index("O")
    distances = atoms.get_distances(oxygen, range(45), mic=True)
    base = float(covalent_radii[atomic_numbers["Fe"]] + covalent_radii[atomic_numbers["O"]])
    return {
        "geometry_path": str(path),
        "geometry_sha256": sha(path),
        "nearest_Fe": [{"index_1based": int(i)+1, "distance_A": float(distances[i])}
                       for i in np.argsort(distances)[:4]],
        "coordination_by_scale": {str(scale): int(np.sum(distances <= scale*base))
                                  for scale in (1.20, 1.225, 1.25, 1.275, 1.30)},
        "nearest_C_O_A": float(min(atoms.get_distance(i, oxygen, mic=True) for i in (45, 46))),
        "O_H_A": float(atoms.get_distance(oxygen, symbols.index("H"), mic=True)),
    }


def review_fourth(row: dict) -> dict:
    joint_path = BASE / "joint_priority614_20261117_v1/results_v2/joint_priority.json"
    checked(joint_path, JOINT_SHA)
    doc = load(joint_path)
    hashes = {Path(x["path"]).resolve(): x["sha256"] for x in doc["source_files"]}
    target = Path(row["coordinate_path"])
    checked(target, row["coordinate_sha256"])
    mid = target.with_name("step_001.vasp")
    mid_meta = load(mid.with_suffix(".json"))
    checked(mid, mid_meta["structure_sha256"])
    labels = []
    for label in doc["frames"]:
        if not label["sample_id"].startswith("family_0001_"):
            continue
        coords, forces = (Path(label[k]).resolve() for k in ("structure_path", "label_path"))
        checked(coords, label["structure_sha256"])
        checked(forces, hashes[forces])
        labels.append({**oxygen_contacts(coords), "id": label["sample_id"],
                       "DFT_physical_label_key": label["physical_label_key"],
                       "label_sha256": hashes[forces], "qualification": label["qualification_scope"],
                       "DFT_fmax_eV_A": label["DFT_fmax_eV_A"],
                       "O_force_metrics": label["actual_error"]["groups"]["adsorbate_O"]})
    if {r["id"] for r in labels} != {f"family_0001_step{s:03d}" for s in (0, 8, 14)}:
        raise ValueError("Unexpected set of existing labels in family_0001")
    last = oxygen_contacts(target)
    reference = next(r for r in labels if r["id"] == "family_0001_step000")
    trace = [reference, oxygen_contacts(mid), last]
    fe42 = [r["nearest_Fe"][0]["index_1based"] for r in trace]
    second = [r["nearest_Fe"][1]["distance_A"] for r in trace]
    if fe42 != [42, 42, 42] or sorted(second) != second:
        raise ValueError("O–Fe geometry differs from the reviewed trend")
    return {
        "id": DEFERRED,
        "disposition": "DEFER_OUTSIDE_FIRST_ROUND",
        "reason": "Same primary Fe42, continuous opening of secondary O–Fe41, close labelled reference and two already-labelled later same-family geometries.",
        "source_joint_inventory_sha256": JOINT_SHA,
        "reference_symmetry_RMSD_A": row["closest_existing_catalog_label"]["full_RMSD_A"],
        "trace_000_001_002": trace, "existing_label_references": labels,
        "exact_target_label_found_in_audited_catalog": row["exact_catalog_label_match"],
        "candidate_DFT_force_known": False, "independent_new_adsorption_mode_established": False,
        "saved_nominal_core_hours": row["conditional_core_h_cap"],
    }


def bind_single_point(root: Path, row: dict, pots: dict) -> dict:
    source = Path(row["local_input_directory"])
    folder = root / row["id"]
    folder.mkdir(parents=True)
    minutes = row["proposed_wall_minutes"]
    if minutes not in (90, 135) or 32*minutes/60 != row["conditional_core_h_cap"]:
        raise ValueError("Reviewed limits and per-point cost differ")
    for name, digest in row["input_hashes"].items():
        checked(source / name, digest)
        if name != "script.lsf":
            copy_bound(source / name, folder / name, digest)
    script = source / "script.lsf"
    first_line, separator, body = script.read_bytes().partition(b"\n")
    if not separator or b"#BSUB" in body or b"NP=32\n" not in body:
        raise ValueError("Unexpected existing LSF script")
    with (folder / "script.lsf").open("xb") as stream:
        stream.write(first_line+b"\n"+f"#BSUB -W {minutes}\n".encode("ascii")+body)
    evidence = preflight(folder, "diagnostic_static", write_report=False)
    if not evidence["passed"] or evidence["cores"] != 32 or evidence["wall_limit_minutes"] != minutes:
        raise ValueError(f"Final local preflight failed for {row['id']}: {evidence['errors']}")
    bundle = InputBundle.from_preflight(evidence)
    bundle.verify(folder)
    report = folder / "submission_preflight.json"
    save(report, evidence)
    pot = pots[row["POTCAR.spec"]]
    remote_pot = "~/sbq/" + pot["path"].split("/sbq/", 1)[1]
    return {"id": row["id"], "original_rank": row["rank"], "composition": row["composition"],
            "MPI_ranks": 32, "LSF_limit_minutes": minutes, "nominal_budget_core_hours": 32*minutes/60,
            "historical_median_core_hours": row["historical_median_core_h"], "local_input_directory": str(folder),
            "remote_directory": f"{REMOTE_ROOT}/{row['id']}", "POTCAR_spec": row["POTCAR.spec"],
            "POTCAR_source": remote_pot, "POTCAR_sha256": pot["sha256"], "input_sha256": evidence["files"],
            "bundle_sha256": bundle.bundle_sha256, "preflight_sha256": sha(report),
            "bsub_preview": _bsub_command(evidence), "allowed_when_authorized": ACTION,
            "execution_authorized": False}


def prepare(destination: Path):
    frozen = guard_hashes()
    source, pot = (PREPARED / name for name in ("review.json", "remote_POTCAR_hash_check.json"))
    checked(source, SOURCE_SHA)
    checked(pot, POTCAR_SHA)
    previous = load(source)
    rows = previous["DFT_first_ten"]
    fourth = rows[3]
    if len(rows) != 10 or fourth["id"] != DEFERRED or len(previous["reserve_ids_only"]) != 10:
        raise ValueError("Reviewed batch, decision point, or reserve list changed")
    review = review_fourth(fourth)
    destination.mkdir(parents=True, exist_ok=False)
    save(destination / "O-Fe第四点复核.json", review)
    pots = load(pot)["observed"]
    selected = [bind_single_point(destination / "vasp_review_inputs", r, pots)
                for r in rows if r["id"] != DEFERRED]
    if guard_hashes() != frozen:
        raise ValueError("Frozen package, model, task or protocol changed")
    totals = {"jobs": len(selected), "ranks_per_job": 32, "LSF_minutes_total_if_serial": sum(r["LSF_limit_minutes"] for r in selected),
              "nominal_LSF_budget_core_hours": sum(r["nominal_budget_core_hours"] for r in selected),
              "historical_median_core_hours": sum(r["historical_median_core_hours"] for r in selected),
              "allocated_or_consumed_core_hours": 0}
    save(destination / "final_submission_list.json", {"jobs": selected, "budget": totals, "backend": "sunboquan-codex",
         "queue_from_canonical_script": "Gkn_normal", "deferred_fourth": DEFERRED, "reserve_ids_only": previous["reserve_ids_only"],
         "source_preflight_sha256": SOURCE_SHA, "POTCAR_receipt_sha256": POTCAR_SHA,
         "frozen_hashes": frozen, "execution_authorized": False, "DFT_submitted": 0})
    table(destination / "最终提交清单.csv", selected, [
        ("original_rank", "原排名"), ("id", "候选ID"), ("composition", "组成"), ("MPI_ranks", "核数"),
        ("LSF_limit_minutes", "LSF限时分钟"), ("nominal_budget_core_hours", "计划核时"),
        ("historical_median_core_hours", "历史中位核时"), ("bsub_preview", "命令预览"),
        ("remote_directory", "目标目录"), ("POTCAR_sha256", "POTCAR哈希"), ("bundle_sha256", "输入包哈希"),
        ("preflight_sha256", "预检哈希"), ("execution_authorized", "现有执行授权")])
    print(totals)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    prepare(parser.parse_args().output.resolve())
