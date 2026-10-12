"""Produce adsorption completion evidence and conservative surface-aware duplicate groups.

This analyzer does not accept results or mutate the registry. Review its output
before preparing a separate append-only registration plan.
"""
from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import numpy as np
import yaml
from ase.io import read

from scripts.adsmind_lite.relaxed_analysis import (
    connectivity_change, connectivity_edges, maximum_slab_displacement, minimum_cross_distance,
)
from scripts.aqcat25_calibration import parse_final_outcar
from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.neb_agent.utils_vasp import parse_oszicar
from scripts.vasp_result_gate import read_incar_values, validate_vasp_relaxation
from scripts.workflow_geometry import minimum_image_delta_xy
from .build_fe110_adsorption import expanded_symbols, fe110_anchor_site_distances, read_poscar
from .build_fe110_care_batch import molecular_signature
from .build_fe110_care_isomers import surface_pose_symmetries


def surface_equivalence(first, second, slab, operations) -> dict:
    """Compare absolute adsorption positions under real clean-slab symmetries only.

    No height shift, COM fitting or Kabsch rotation. The *same* operation must
    match adsorbate and relaxed Fe environment; interchangeable H are permitted.
    Carbon ordering remains fixed to the already-reviewed graph/atom mapping.
    """
    if expanded_symbols(first) != expanded_symbols(second) or not np.allclose(first.cell, second.cell):
        raise ValueError("different composition, atom mapping or cell")
    hydrogens = [i for i, s in enumerate(expanded_symbols(first)[45:]) if s == "H"]
    scores = []
    for rotation, translation in operations:
        clean_mapped = slab.frac @ rotation.T + translation
        distances = np.linalg.norm(
            minimum_image_delta_xy(clean_mapped[:, None, :] - slab.frac[None, :, :]) @ slab.cell, axis=2,
        )
        mapping = np.argmin(distances, axis=1)
        if len(set(mapping)) != 45 or distances[np.arange(45), mapping].max() > .01:
            raise ValueError("symmetry does not map the clean slab bijectively")
        mapped = second.frac @ rotation.T + translation
        fe_delta = minimum_image_delta_xy(mapped[:45] - first.frac[mapping]) @ first.cell
        fe_rmsd = float(np.sqrt(np.mean(np.sum(fe_delta**2, axis=1))))
        for order in itertools.permutations(hydrogens):
            indices = list(range(len(first.frac) - 45))
            for a, b in zip(hydrogens, order, strict=True):
                indices[a] = b
            delta = minimum_image_delta_xy(mapped[45:][indices] - first.frac[45:]) @ first.cell
            ads_rmsd = float(np.sqrt(np.mean(np.sum(delta**2, axis=1))))
            scores.append({"adsorbate_RMSD_A": ads_rmsd, "slab_RMSD_A": fe_rmsd,
                           "slab_max_displacement_A": float(np.linalg.norm(fe_delta, axis=1).max())})
    return min(scores, key=lambda r: (max(r["adsorbate_RMSD_A"], r["slab_RMSD_A"]), r["adsorbate_RMSD_A"]))


def compatibility_checks(directory, initial, final, clean, manifest, receipt) -> dict:
    values = read_incar_values(directory / "INCAR")
    expected = manifest["builder"]["incar"]
    key_types = {"GGA": str, "ENCUT": float, "EDIFF": float, "EDIFFG": float,
                 "ISPIN": int, "ISMEAR": int, "SIGMA": float, "ISIF": int}
    def flags(pose):
        return [tuple(x.upper() for x in row) for row in pose.flags]
    checks = {key: key_types[key](values[key]) == key_types[key](expected[key]) for key in key_types}
    checks.update(
        dipole_off=values.get("LDIPOL", "F").upper().strip(".") in {"F", "FALSE"},
        atom_order=expanded_symbols(initial) == expanded_symbols(final),
        clean_Fe45=expanded_symbols(final)[:45] == ["Fe"] * 45 and expanded_symbols(final).count("Fe") == 45,
        cell=np.allclose(initial.cell, clean.cell, atol=1e-8, rtol=0) and np.allclose(final.cell, clean.cell, atol=1e-8, rtol=0),
        flags=flags(initial) == flags(final) == [("F", "F", "F")] * 18 + [("T", "T", "T")] * (len(final.frac) - 18),
        fixed_positions=np.max(np.abs(minimum_image_delta_xy(final.frac[:18] - clean.frac[:18]) @ clean.cell)) < 1e-7,
        input_fixed_positions=np.max(np.abs(minimum_image_delta_xy(initial.frac[:18] - clean.frac[:18]) @ clean.cell)) < 1e-7,
        potcar=receipt["remote"]["files"]["POTCAR"]["sha256"] == receipt["submission"]["potcar_sha256"],
    )
    k = (directory / "KPOINTS").read_text().splitlines()
    checks["kmesh"] = k[1].strip() == "0" and k[2].lower().startswith("g") and k[3].split() == ["5", "5", "1"] and all(float(x) == 0 for x in k[4].split())
    moments = [float(value) for term in values["MAGMOM"].split()
               for value in ([term.split("*")[1]] * int(term.split("*")[0]) if "*" in term else [term])]
    checks["magmom"] = moments == [2.2] * 45 + [0.] * (len(final.frac) - 45)
    return {key: bool(value) for key, value in checks.items()}


def analyze_one(directory: Path, slab, analysis: dict) -> dict:
    receipt = load_json_object(directory / "collection.json")
    submission = receipt["submission"]
    manifest_path = Path(submission["workdir"]) / "candidate_manifest.json"
    manifest = load_json_object(manifest_path)
    for name in ("INCAR", "POSCAR", "CONTCAR", "OUTCAR", "OSZICAR", "KPOINTS"):
        if sha256_file(directory / name) != receipt["remote"]["files"][name]["sha256"]:
            raise ValueError(f"collection hash changed: {directory.name}/{name}")
    initial, final = [read_poscar(directory / name) for name in ("POSCAR", "CONTCAR")]
    atoms_initial, atoms = [read(directory / name, format="vasp") for name in ("POSCAR", "CONTCAR")]
    atoms_initial.pbc = atoms.pbc = [True, True, False]
    ads = list(range(45, len(atoms)))
    rules = analysis["connectivity"]
    initial_edges = connectivity_edges(atoms_initial, ads, rules["covalent_radius_scale"], rules["minimum_bond_distance_angstrom"])
    final_edges = connectivity_edges(atoms, ads, rules["covalent_radius_scale"], rules["minimum_bond_distance_angstrom"])
    chemistry = connectivity_change(len(ads), initial_edges, final_edges)
    signature_match = False
    try:
        signature_match = molecular_signature(initial) == molecular_signature(final)
    except ValueError:
        pass
    errors = []
    try:
        convergence = validate_vasp_relaxation(directory)
    except ValueError as exc:
        convergence = {"passed": False, "reason": str(exc)}
        errors.append("convergence")
    parsed = parse_final_outcar(directory / "OUTCAR")
    forces = np.asarray(parsed["forces_eV_per_A"], dtype=float)
    if forces.shape != (len(atoms), 3) or not np.isfinite(forces).all():
        raise ValueError("nonfinite/incomplete force block")
    fmax = float(np.linalg.norm(forces[18:], axis=1).max())
    force_limit = -float(read_incar_values(directory / "INCAR")["EDIFFG"])
    checks = compatibility_checks(directory, initial, final, slab, manifest, receipt)
    if not all(checks.values()):
        errors.append("compatibility")
    if fmax > force_limit:
        errors.append("force_limit")
    if chemistry["connectivity_changed"] or not signature_match:
        errors.append("chemical_identity_changed")
    contact = minimum_cross_distance(atoms, list(range(45)), ads)
    if contact < analysis["contact_validation"]["hard_contact_distance_angstrom"]:
        errors.append("collision")
    displacement = maximum_slab_displacement(atoms_initial, atoms, list(range(45)))
    if displacement > analysis["surface_reconstruction"]["maximum_slab_displacement_angstrom"]:
        errors.append("surface_reconstruction_review")
    cart = final.frac @ final.cell
    contacts = []
    for i in ads:
        distances = sorted((float(atoms.get_distance(i, j, mic=True)), j) for j in range(45))
        projection = fe110_anchor_site_distances(slab, final.frac[i])
        site, offset = min(projection.items(), key=lambda x: x[1])
        contacts.append({"atom_0based": i, "symbol": atoms[i].symbol, "nearest_Fe_0based": distances[0][1],
                         "nearest_Fe_A": distances[0][0], "three_nearest_Fe": distances[:3],
                         "closest_site_projection": site, "lateral_offset_A": offset,
                         "off_symmetry": offset > analysis["site_classification"]["top_lateral_tolerance_angstrom"],
                         "height_above_top_Fe_A": float(cart[i, 2] - cart[:45, 2].max())})
    internal = [{"atoms_0based": [a, b], "pair": atoms[a].symbol + "-" + atoms[b].symbol,
                 "distance_A": float(atoms.get_distance(a, b, mic=True)), "bond": (a - 45, b - 45) in final_edges}
                for a, b in itertools.combinations(ads, 2)]
    return {"name": directory.name, "job_id": submission["job_id"], "species_id": submission["species_id"],
            "target_graph": submission["connectivity"], "formula": submission["formula"],
            "directory": str(directory.resolve()), "collection_sha256": sha256_file(directory / "collection.json"),
            "candidate_manifest_sha256": sha256_file(manifest_path), "convergence": convergence,
            "ionic_steps": parse_oszicar(directory / "OSZICAR")["ionic_steps"],
            "final_toten_eV": parsed["final_toten_eV"], "fmax_movable_eV_A": fmax,
            "force_limit_eV_A": force_limit, "compatibility_checks": checks,
            "chemistry": chemistry, "signature_match": signature_match,
            "minimum_Fe_adsorbate_A": contact, "maximum_slab_displacement_A": displacement,
            "internal_distances": internal, "contacts": contacts, "blockers": errors,
            "eligible_for_review": not errors, "scientific_acceptance": False,
            "duplicate_of": None}


def mark_duplicates(records: list[dict], slab, rules: dict) -> list[dict]:
    operations = surface_pose_symmetries(slab)
    poses = {r["name"]: read_poscar(Path(r["directory"]) / "CONTCAR") for r in records}
    representatives = []
    comparisons = []
    for record in sorted(records, key=lambda r: (r["final_toten_eV"], r["name"])):
        if not record["eligible_for_review"]:
            continue
        for prior in representatives:
            if prior["target_graph"] != record["target_graph"]:
                continue
            metrics = surface_equivalence(poses[prior["name"]], poses[record["name"]], slab, operations)
            de = abs(prior["final_toten_eV"] - record["final_toten_eV"])
            duplicate = max(metrics["adsorbate_RMSD_A"], metrics["slab_RMSD_A"]) <= rules["geometry_rmsd_tolerance_angstrom"] and de <= rules["energy_tolerance_ev"]
            comparisons.append({"first": prior["name"], "second": record["name"], **metrics, "energy_difference_eV": de, "duplicate": duplicate})
            if duplicate:
                record["duplicate_of"] = prior["name"]
                break
        if record["duplicate_of"] is None:
            representatives.append(record)
    return comparisons


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--slab", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    slab = read_poscar(args.slab)
    policy = Path("configs/adsmind_lite/analysis_rules.yaml")
    analysis = yaml.safe_load(policy.read_text(encoding="utf-8"))
    records = []
    # Cache unchanged parsed evidence, not scientific acceptance. A changed
    # source, analyzer, policy or clean reference receives a new cache key.
    binding = {"analyzer_sha256": sha256_file(Path(__file__)),
               "policy_sha256": sha256_file(policy), "slab_sha256": sha256_file(args.slab)}
    from scripts.artifact_io import sha256_json
    for path in sorted(args.sources.glob("*/collection.json")):
        receipt = load_json_object(path)
        if any(sha256_file(path.parent / name) != item["sha256"]
               for name, item in receipt["remote"]["files"].items() if name != "POTCAR"):
            raise ValueError("collected source changed")
        key = sha256_json({**binding, "collection_sha256": sha256_file(path)})
        cache = args.sources.parent / "parsed" / (path.parent.name + "_" + key + ".json")
        if cache.exists():
            record = load_json_object(cache)
        else:
            record = analyze_one(path.parent, slab, analysis)
            write_json_atomic(cache, record, ensure_ascii=True)
        records.append(record)
        print(f"REVIEW {record['name']} steps={record['ionic_steps']} fmax={record['fmax_movable_eV_A']:.6f} blockers={record['blockers']}", flush=True)
    comparisons = mark_duplicates(records, slab, analysis["duplicate_detection"])
    write_json_atomic(args.output, {"records": records, "comparisons": comparisons,
                      "analysis_policy": {"path": str(policy), "sha256": sha256_file(policy)},
                      "slab": {"path": str(args.slab.resolve()), "sha256": sha256_file(args.slab)},
                      "duplicate_scope": "this submitted batch; genuine clean-slab symmetry and fixed C roles; no free rotations",
                      "scientific_acceptance": False, "registry_written": False}, ensure_ascii=True)
    print(f"ANALYZED {len(records)} DUPLICATES {sum(r['duplicate_of'] is not None for r in records)}")


if __name__ == "__main__":
    main()
