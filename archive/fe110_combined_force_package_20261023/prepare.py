"""Assemble a new local force dataset from reviewed sources; never launch training."""
from __future__ import annotations

import copy
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from ase.db import connect
from ase.io import read

from archive.fe110_10b_lowforce_20261023.legacy_helpers import pose_distance, pose_variants
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.adsorption.force_finetune import (
    build_database, build_database_metadata, load_manifest, local_path, validate_label_row,
)
from scripts.adsorption.reico_dataset_audit import reserved_geometries
from scripts.adsorption.reico_force_coverage import force_coverage
from scripts.artifact_io import (
    sha256_file, source_file_manifest, source_file_manifest_valid, write_json,
)

from .role_helpers import atom_weights, role_groups

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/fe110_reico_pilot/combined_force_package_v1.json"
PRIORITY = {"train": 0, "development": 1, "heldout": 2, "observed_heldout": 3}


def save_once(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2)+"\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("preserve changed artifact:"+str(path))
    else:
        with path.open("xb") as handle:
            handle.write(data)


def copy_checked(source, target, expected):
    if sha256_file(source) != expected:
        raise ValueError("source hash changed:"+str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256_file(target) != expected:
            raise ValueError("preserve changed package file:"+str(target))
    else:
        with source.open("rb") as src, target.open("xb") as dst:
            dst.write(src.read())


def canonical_split(value):
    return "heldout" if value == "final_test" else value


def assert_group_isolation(rows):
    groups = {}
    for row in rows:
        split = canonical_split(row["split"])
        if split not in PRIORITY:
            raise ValueError("unknown source partition")
        keys = [("group", row["calculation_group"])]
        if row.get("source_job_id"):
            keys.append(("job", str(row["source_job_id"])))
        if row.get("family_id"):
            keys.append(("family", row["family_id"]))
        for key in keys:
            if groups.setdefault(key, split) != split:
                raise ValueError("whole-job/family split leakage:"+str(key))


def set_uniform_sampling(rows):
    for row in rows:
        free = sorted(set(range(len(row["symbols"]))) - set(row["fixed_atom_indices_0based"]))
        weights = np.zeros(len(row["symbols"]))
        weights[free] = 1. / len(free)
        row["proposed_per_atom_loss_weights"] = weights.tolist()
        row["proposed_source_stage_sampling_probability"] = 1. / len(rows)


def coverage_groups(rows):
    """Diagnostic grouping only; legacy source groups are not new ML families."""
    return [{**r, "family_id": r.get("family_id", r["calculation_group"])} for r in rows]


def static_row(source, selection):
    selected = selection[source["sample_id"]]
    if (source["data_qc_status"] != "PASS" or source["magnetic_review_flags"]
            or source["Fe_positive_moment_count"] != 45 or len(source["local_magnetization_muB"]) != len(source["symbols"])
            or source["partition"] != selected["partition"] or source["family_id"] != selected["family_id"]
            or source["structure_sha256"] != selected["structure_sha256"]):
        raise ValueError("static source lost QC or frozen-family binding")
    row = copy.deepcopy(source)
    row.update(split=canonical_split(source["partition"]), calculation_group="reico_"+source["family_id"],
        ionic_step=1, source_OUTCAR_sha256=source["input_output_hashes"]["OUTCAR"],
        energy_eV_force_label_only=source["toten_eV_force_label_only"],
        magnetic_review_level="LOCAL_MOMENTS_REVIEWED_POSITIVE_FE", source_collection="reviewed_reico_statics137",
        stage="random_static", accepted_endpoint=False, training_authorized=False)
    return row


def source_rows(paths, config, reserved):
    legacy = load_manifest(paths["legacy_manifest"])
    rows = []
    for split, samples in [*legacy["splits"].items(), ("observed_heldout", legacy["quarantined_observed_heldout"])]:
        for original in samples:
            row = copy.deepcopy(original)
            row.update(split=split, source_collection="legacy_control_20261019")
            row.setdefault("magnetic_review_level", "PRESERVED_LEGACY_SOURCE_REVIEW")
            rows.append((row, paths["legacy_manifest"].parent, original["label_source"], None))
    selection = {r["sample_id"]: r for r in json.loads(paths["frozen_selection"].read_bytes())["selected"]}
    for key in ("static_labels", "incremental_labels"):
        for original in json.loads(paths[key].read_bytes())["samples"]:
            directory = Path(original["structure_path"]).parent
            for name, digest in original["input_output_hashes"].items():
                if sha256_file(directory/name) != digest:
                    raise ValueError("reviewed raw static evidence changed")
            row = static_row(original, selection)
            rows.append((row, directory, None, paths[key]))
    supplement = json.loads(paths["supplement"].read_bytes())
    if supplement["magnetic_review_level"] != "LEGACY_TOTAL_MAGNETIZATION_ONLY":
        raise ValueError("10_B magnetic tier changed")
    for original in supplement["samples"]:
        validate_label_row(paths["supplement"].parent, original)
        row = copy.deepcopy(original)
        if row["split"] != "train" or row["magnetic_review_level"] != supplement["magnetic_review_level"]:
            raise ValueError("10_B split or magnetic level changed")
        row.update(source_collection="10B_legacy_total_only6", stage="late_trajectory")
        rows.append((row, paths["supplement"].parent, original["label_source"], None))
    counts = {group: Counter(r[0]["split"] for r in rows if r[0]["source_collection"] == group)
              for group in {r[0]["source_collection"] for r in rows}}
    expected = config["expected_source_counts"]
    if (dict(counts["legacy_control_20261019"]) != expected["legacy"]
            or dict(counts["reviewed_reico_statics137"]) != expected["static"]
            or dict(counts["10B_legacy_total_only6"]) != {"train": expected["10B_train"]}):
        raise ValueError("source checkpoint counts changed")
    assert_group_isolation([r[0] for r in rows])
    if len({r[0]["sample_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate sample identifier")
    return rows


def materialize(rows, output, reserved):
    alternatives = {r["structure_sha256"]: Path(r["structure_path"]) for r, _ in reserved}
    sources, result = {}, []
    for row, source_root, reference, qc_path in rows:
        original = copy.deepcopy(row)
        structure = Path(row["structure_path"])
        if not structure.is_absolute():
            structure = local_path(source_root, row["structure_path"])
        if not structure.exists():
            structure = alternatives[row["structure_sha256"]]
        target = output / "structures" / (row["sample_id"]+".vasp")
        copy_checked(structure, target, row["structure_sha256"])
        row["structure_path"] = target.relative_to(output).as_posix()
        if reference:
            path = local_path(source_root, reference["path"])
            if sha256_file(path) != reference["sha256"]:
                raise ValueError("legacy label source changed")
            if str(path) not in sources:
                sources[str(path)] = {s["sample_id"]: s for s in json.loads(path.read_bytes())["samples"]}
            original = sources[str(path)][reference["sample_id"]]
        else:
            path = qc_path
        archived = output / "source_archives" / (sha256_file(path)+".json")
        copy_checked(path, archived, sha256_file(path))
        label = output / "labels" / (row["sample_id"]+".json")
        save_once(label, {"samples": [original], "source_archive": {"path": archived.relative_to(output).as_posix(),
                   "sha256": sha256_file(archived)}, "original_sample_id": original["sample_id"]})
        row["label_source"] = {"path": label.relative_to(output).as_posix(), "sha256": sha256_file(label), "sample_id": original["sample_id"]}
        row.setdefault("structure_equivalence_sha256", row["structure_sha256"])
        atoms = read(target, format="vasp")
        atoms.pbc = [True, True, False]
        if "force_role_groups" not in row:
            row["force_role_groups"] = role_groups(atoms)
            row["proposed_per_atom_loss_weights"] = atom_weights(row["force_role_groups"], len(atoms)).tolist()
            row["group_radius_A_proposed_not_geometry_gate"] = 3.
        row.update(partition=row["split"], composition=atoms[45:].get_chemical_formula(), training_authorized=False)
        validate_label_row(output, row)
        result.append(row)
    return result


def isolate(rows, output, reserved, slab, threshold):
    operations = surface_pose_symmetries(slab)
    protected = [(r, a, canonical_split(r.get("partition", r.get("split")))) for r, a in reserved]
    variants = {}
    for ref, atoms, split in protected:
        if split not in PRIORITY or split == "train":
            raise ValueError("reserved geometry has unknown partition")
        pose = read_poscar(Path(ref["structure_path"]))
        variants.setdefault(tuple(sorted(Counter(atoms.get_chemical_symbols()).items())), []).append(
            (ref["sample_id"], split, pose_variants(pose, operations)))
    conflicts, comparisons = [], 0
    for index, row in enumerate(rows):
        if row["split"] == "observed_heldout":
            continue
        pose = read_poscar(output/row["structure_path"])
        for name, split, reference in variants.get(tuple(sorted(Counter(row["symbols"]).items())), []):
            if PRIORITY[split] <= PRIORITY[row["split"]]:
                continue
            comparisons += 1
            distance = pose_distance(pose, reference)
            if distance <= threshold:
                conflicts.append({"sample_id": row["sample_id"], "split": row["split"], "reserved_sample_id": name,
                                  "reserved_split": split, "adsorbate_RMSD_A": distance})
        if (index+1) % 100 == 0:
            print(f"ISOLATION {index+1}/{len(rows)}", flush=True)
    excluded = {r["sample_id"] for r in conflicts}
    return [r for r in rows if r["sample_id"] not in excluded], {"geometry_conflicts": conflicts,
        "quarantined_sample_ids": sorted(excluded), "comparisons": comparisons, "threshold_A": threshold,
        "reserved_geometries": len(reserved), "reserved_forces_or_energies_used": False,
        "method": "real clean-face Fe110 symmetry,XY MIC,all equal-element permutations;conservative adsorbate RMSD"}


def database(split, output, rows):
    receipt = output / (split+"_build_receipt.json")
    target, metadata = output / (split+".db"), output / (split+"_metadata.npz")
    if receipt.exists():
        saved = json.loads(receipt.read_bytes())
        if sha256_file(target) != saved["database_sha256"] or sha256_file(metadata) != saved["metadata_sha256"]:
            raise ValueError("completed database changed")
        return saved
    build_database(output/"training_manifest.json", target, split)
    db = connect(target)
    with db:
        for item, row in zip(db.select(), rows, strict=True):
            data = dict(item.data)
            data.update(magnetic_review_level=row["magnetic_review_level"], source_collection=row["source_collection"],
                        family_id=row.get("family_id", ""), global_magnetic_ground_state_verified=False)
            db.update(item.id, data=data)
    result = build_database_metadata(target, metadata)
    save_once(receipt, result)
    return result


def run(config_path=CONFIG):
    config = json.loads(config_path.read_bytes())
    output = ROOT/config["output"]
    output.mkdir(parents=True, exist_ok=True)
    paths = {k: ROOT/v["path"] for k, v in config["inputs"].items()}
    for key, path in paths.items():
        if sha256_file(path) != config["inputs"][key]["sha256"]:
            raise ValueError("frozen input changed:"+key)
    for key in ("static_review", "incremental_review", "supplement_review"):
        if not source_file_manifest_valid(json.loads(paths[key].read_bytes())):
            raise ValueError("QC source binding changed:"+key)
    prior = json.loads(paths["legacy_manifest"].read_bytes())
    reserved_cfg = json.loads(paths["reserved_config"].read_bytes())
    reserved = reserved_geometries(json.loads((ROOT/reserved_cfg["inventory"]).read_bytes()), prior,
        paths["legacy_manifest"].parent, [ROOT/p for p in reserved_cfg["reserved_geometry_catalogs"]])
    bindings = source_file_manifest([config_path, *paths.values(), Path(__file__), Path(__file__).with_name("role_helpers.py"),
        ROOT/"scripts/adsorption/force_finetune.py", ROOT/"scripts/adsorption/force_role_data.py",
        ROOT/"scripts/adsorption/build_fe110_care_isomers.py", ROOT/"archive/fe110_10b_lowforce_20261023/legacy_helpers.py",
        ROOT/reserved_cfg["inventory"], *[ROOT/p for p in reserved_cfg["reserved_geometry_catalogs"]]])
    save_once(output/"assembly_request.json", {"source_files": bindings, "training_authorized": False, "new_DFT": False})
    if (output/"package_summary.json").exists():
        return json.loads((output/"package_summary.json").read_bytes())
    rows = materialize(source_rows(paths, config, reserved), output, reserved)
    retained, isolation = isolate(rows, output, reserved, read_poscar(paths["clean_slab"]), config["isolation_A"])
    assert_group_isolation(retained)
    save_once(output/"isolation_review.json", isolation)
    splits = {s: [r for r in retained if r["split"] == s] for s in ("train", "development", "heldout")}
    set_uniform_sampling(splits["train"])
    manifest = {"document_kind": "aqcat25_adsorption_force_training_manifest", "schema_version": 1,
        "training_target": "forces_only", "energy_loss_coefficient": 0, "reportable_final_energy": False,
        "splits": splits, "quarantined_observed_heldout": [r for r in retained if r["split"] == "observed_heldout"],
        "quarantined_geometry_conflicts": [r for r in rows if r["sample_id"] in isolation["quarantined_sample_ids"]],
        "prior_manifest_sha256": sha256_file(paths["legacy_manifest"]), "training_authorized": False,
        "new_VASP": False, "model_promoted": False, "source_files": bindings,
        "sampling_policy": "uniform_frames_like_existing_control;renormalized over retained training rows",
        "magnetic_policy": "Preserve legacy review levels;positive local Fe moments do not prove a global magnetic ground state."}
    save_once(output/"training_manifest.json", manifest)
    load_manifest(output/"training_manifest.json")
    receipts = {s: database(s, output, splits[s]) for s in ("train", "development")}
    if (output/"heldout.db").exists() or (output/"training_request.json").exists():
        raise ValueError("unexpected heldout loader or executable training request")
    atoms = {r["sample_id"]: read(output/r["structure_path"], format="vasp") for r in splits["train"]}
    coverage = force_coverage(coverage_groups(splits["train"]), atoms, [0, .05, .10, .50, 1, 2, 5, 10])
    summary = {"status": "LOCAL_DATA_PACKAGE_PREPARED_NO_TRAINING", "split_counts": {s: len(v) for s, v in splits.items()},
        "observed_heldout_quarantined": len(manifest["quarantined_observed_heldout"]),
        "geometry_quarantine_count": len(isolation["quarantined_sample_ids"]),
        "source_counts_by_split": {s: dict(Counter(r["source_collection"] for r in v)) for s, v in splits.items()},
        "magnetic_levels_by_split": {s: dict(Counter(r["magnetic_review_level"] for r in v)) for s, v in splits.items()},
        "training_force_coverage": coverage, "database_receipts": receipts,
        "coverage_group_definition": "Original ML family_id for random sources;existing calculation_group for legacy/replay sources. No manifest family identities added.",
        "manifest_sha256": sha256_file(output/"training_manifest.json"), "source_files": bindings,
        "training_authorized": False, "GPU_or_training_or_new_DFT": False, "heldout_loader_created": False}
    save_once(output/"package_summary.json", summary)
    return summary


if __name__ == "__main__":
    try:
        result = run()
        print(json.dumps({k: result[k] for k in ("status", "split_counts", "observed_heldout_quarantined", "geometry_quarantine_count")}))
    except Exception as error:
        config = json.loads(CONFIG.read_bytes())
        output = ROOT/config["output"]
        output.mkdir(parents=True, exist_ok=True)
        write_json(output/("failure_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+".json"),
                   {"status": "FAILED", "error": str(error), "training_started": False})
        raise
