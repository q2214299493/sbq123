"""Collect exact GPU outputs and review four intact candidates without submission."""
from __future__ import annotations

import io
import json
import subprocess
import tarfile
from pathlib import Path

import numpy as np
import yaml
from ase.io import read

from archive.fe110_five_c2_adsorption_20261006.build_supplement import equivalent_rmsd, surface_symmetries
from scripts.adsorption.build_fe110_adsorption import read_poscar, classify_fe110_anchor_site
from scripts.adsmind_lite.relaxed_analysis import connectivity_edges, connectivity_change
from scripts.aqcat25_handoff import validate_handoff
from scripts.artifact_io import sha256_file, write_json

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
PACKAGE = BASE / "gpu_supplement_v1"
DEST = BASE / "gpu_supplement_review_v1"
GPU_SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "IdentitiesOnly=yes",
           "-i", "C:/Users/86177/.ssh/id_ed25519_fe_agent", "-p", "36039", "sbq@10sx4jr711576.vicp.fun"]


def collect_tar(command, destination, allowed):
    result = subprocess.run(command, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[:2000])
    if len(result.stdout) > 2_000_000:
        raise ValueError("Unexpectedly large structure return")
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
        for item in archive.getmembers():
            if not item.isfile() or item.name not in allowed or item.size > 200_000:
                raise ValueError("Unexpected archive member: " + item.name)
            content = archive.extractfile(item).read()
            target = destination / item.name
            if target.exists():
                if target.read_bytes() != content:
                    raise ValueError("Do not overwrite previously collected bytes")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)


def geometry(source, target, slab, rules):
    initial, final = read(source), read(target)
    ads = list(range(45, len(final)))
    config = rules["connectivity"]
    edges = [connectivity_edges(a, ads, config["covalent_radius_scale"], config["minimum_bond_distance_angstrom"])
             for a in (initial, final)]
    chemistry = connectivity_change(len(ads), *edges)
    expected = set(edges[0])
    contacts, bonds = [], []
    structure = read_poscar(target)
    for i in ads:
        distance, index = min((float(final.get_distance(i, j, mic=True)), j) for j in range(45))
        site, lateral = classify_fe110_anchor_site(structure, structure.frac[i], reference_poscar=slab)
        contacts.append({"atom_0based": i, "symbol": final[i].symbol, "nearest_Fe_0based": index,
                         "Fe_distance_A": distance, "site": site, "lateral_A": lateral})
    for i, j in sorted(set(edges[0]) | set(edges[1])):
        bonds.append({"atoms_0based": [i+45, j+45], "initial_A": float(initial.get_distance(i+45, j+45, mic=True)),
                      "final_A": float(final.get_distance(i+45, j+45, mic=True))})
    nonbonded = [float(final.get_distance(i+45, j+45, mic=True)) for i in range(len(ads))
                for j in range(i+1, len(ads)) if (i, j) not in expected]
    checks = {"finite_positions": bool(np.isfinite(final.positions).all()),
              "atom_order": initial.get_chemical_symbols() == final.get_chemical_symbols(),
              "cell": bool(np.allclose(initial.cell, final.cell, rtol=0, atol=1e-10)),
              "fixed_coordinates": bool(np.allclose(initial.positions[:18], final.positions[:18], rtol=0, atol=1e-8)),
              "fixed_indices": len(final.constraints) == 1 and list(final.constraints[0].get_indices()) == list(range(18)),
              "chemistry": not chemistry["connectivity_changed"],
              "surface_contact": min(c["Fe_distance_A"] for c in contacts) >= rules["contact_validation"]["hard_contact_distance_angstrom"],
              "no_nonbonded_collision": not nonbonded or min(nonbonded) >= rules["contact_validation"]["hard_contact_distance_angstrom"]}
    return {"checks": checks, "pass": all(checks.values()), "chemistry": chemistry,
            "bonds": bonds, "contacts": contacts, "minimum_nonbonded_A": min(nonbonded, default=None)}


def main():
    if DEST.exists():
        raise FileExistsError("Preserve the completed review; use a new version")
    batch = json.loads((PACKAGE / "batch_manifest.json").read_text())
    names = [r["name"] for r in batch["handoffs"]]
    allowed = {name+"/output/job_2142/"+file for name in names for file in
               ("POSCAR", "result.json", "gpu_result_manifest.json", "producer_exit_record.json")}
    collect_tar(GPU_SSH + ["tar -cf - -C " + batch["remote_root"] + " " + " ".join(sorted(allowed))], PACKAGE, allowed)
    assert all((PACKAGE / p).is_file() for p in allowed)
    DEST.mkdir()
    vasp = json.loads((BASE / "vasp_batch_v1/submission_summary.json").read_text())["records"]
    vasp_names = [r["name"] for r in vasp]
    command = "cd ~/sbq/Fe110/adsorption/fe110_five_c2_20261006; set --; for n in " + " ".join(vasp_names) + '; do if test -s "$n/CONTCAR"; then set -- "$@" "$n/CONTCAR"; fi; done; tar -cf - "$@"'
    collect_tar(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "sunboquan-codex", command],
                DEST / "vasp_structure_snapshot", {name+"/CONTCAR" for name in vasp_names})
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text())
    slab = read_poscar(ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR")
    symmetry = surface_symmetries(slab)
    comparisons = []
    prior = json.loads((BASE / "gpu_return_review.json").read_text())
    for name in prior["selected"]:
        directory = BASE / "gpu_batch_v4" / name
        doc = validate_handoff(directory / "output/job_2139/gpu_result_manifest.json", root=directory)
        assert doc["producer"]["checkpoint_sha256"] == batch["checkpoint_sha256"]
        assert doc["adsorption"]["clean_slab_sha256"] == json.loads((PACKAGE / names[0] / "handoff.json").read_text())["adsorption"]["clean_slab_sha256"]
        comparisons.append((name, directory / "output/job_2139/POSCAR", doc["result"]["predicted_energy"]["value"], "same_checkpoint_GPU"))
    for item in vasp:
        comparisons.append(("VASP_input_"+item["name"], BASE / "vasp_batch_v1" / item["name"] / "POSCAR", None, "VASP_input"))
        snapshot = DEST / "vasp_structure_snapshot" / item["name"] / "CONTCAR"
        if snapshot.is_file():
            comparisons.append(("VASP_snapshot_"+item["name"], snapshot, None, "unreviewed_live_VASP_structure"))
    records = []
    for name in names:
        directory = PACKAGE / name
        output = directory / "output/job_2142"
        doc = validate_handoff(output / "gpu_result_manifest.json", root=directory)
        assert doc["producer"]["gpu_job_id"] == "2142"
        assert doc["producer"]["checkpoint_sha256"] == batch["checkpoint_sha256"]
        assert doc["source_handoff"]["sha256"] == sha256_file(directory / "handoff.json")
        result = json.loads((output / "result.json").read_text())
        assert doc["producer_exit_record"]["exit_code"] == 0
        assert doc["result"]["optimizer_steps"] == result["optimizer_steps"]
        assert np.isfinite([result["energy_eV"], result["movable_fmax_eV_per_A"]]).all()
        assert result["converged"] and result["movable_fmax_eV_per_A"] <= 0.10
        assert np.isclose(doc["result"]["predicted_force"]["fmax"], result["movable_fmax_eV_per_A"])
        assert doc["domain_assessment"]["status"] == "in_domain"
        geo = geometry(directory / "POSCAR", output / "POSCAR", slab, rules)
        energy = doc["result"]["predicted_energy"]["value"]
        matches = []
        for other_name, path, other_energy, kind in comparisons:
            species = other_name.split("_")[-2] if other_name.startswith("VASP_") else other_name[:2]
            # Direct-VASP candidate has a longer suffix; use exact species metadata.
            if other_name.startswith("VASP_"):
                species = next(r["species_id"] for r in vasp if other_name.endswith(r["name"]))
            if species != name[:2]:
                continue
            distance = equivalent_rmsd(read_poscar(output / "POSCAR"), read_poscar(path), symmetry, remove_height_shift=False)
            matches.append({"name": other_name, "kind": kind, "RMSD_A": distance,
                            "geometry_match": distance <= rules["duplicate_detection"]["geometry_rmsd_tolerance_angstrom"],
                            "same_model_energy_difference_eV": abs(energy-other_energy) if other_energy is not None else None,
                            "path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)})
        duplicates = [m for m in matches if m["geometry_match"] and m["same_model_energy_difference_eV"] is not None
                      and m["same_model_energy_difference_eV"] <= rules["duplicate_detection"]["energy_tolerance_ev"]]
        vasp_matches = [m for m in matches if m["geometry_match"] and m["same_model_energy_difference_eV"] is None]
        status = "REJECT_TARGET_GRAPH_CHANGED" if not geo["pass"] else "DUPLICATE_GPU" if duplicates else "GEOMETRIC_MATCH_EXISTING_VASP" if vasp_matches else "UNIQUE_REVIEWED_GPU_CANDIDATE"
        record = {"name": name, "status": status, "source_structure_sha256": sha256_file(output / "POSCAR"),
                  "return_validation": "PASS", "ML_converged": result["converged"], "steps": result["optimizer_steps"],
                  "ML_fmax_eV_A": result["movable_fmax_eV_per_A"], "geometry": geo,
                  "domain_assessment": doc["domain_assessment"], "comparisons": matches,
                  "duplicates": duplicates, "VASP_geometry_matches": vasp_matches,
                  "predicted_energy_eV_NOT_DFT": energy}
        records.append(record)
        if geo["pass"]:
            comparisons.append((name, output / "POSCAR", energy, "same_checkpoint_GPU"))
        print(json.dumps({"name": name, "status": status, "duplicates": [m["name"] for m in duplicates],
                          "vasp_matches": [m["name"] for m in vasp_matches], "nearest": sorted(matches, key=lambda m:m["RMSD_A"])[:1],
                          "bonds": geo["bonds"]}))
    write_json(DEST / "review.json", {"job": "2142", "records": records, "surface_symmetry_operations": len(symmetry),
        "height_shift_removed_for_relaxed_duplicates": False, "identical_H_permutations": True,
        "energy_comparison_policy": "Only same-checkpoint compatible GPU predictions; no ML/DFT energy comparison or energy promotion.",
        "VASP_snapshots": "Geometry-only live snapshots, not accepted final energies or endpoints.",
        "rules_sha256": sha256_file(ROOT / "configs/adsmind_lite/analysis_rules.yaml"),
        "input_manifest_sha256": sha256_file(PACKAGE / "batch_manifest.json"),
        "selected": [r["name"] for r in records if r["status"] == "UNIQUE_REVIEWED_GPU_CANDIDATE"],
        "submit_gpu": False, "submit_vasp": False, "scientific_acceptance": False})


if __name__ == "__main__":
    main()
