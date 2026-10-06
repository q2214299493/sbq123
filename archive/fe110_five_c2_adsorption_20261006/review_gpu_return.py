"""Return exact GPU bytes and review chemistry before any VASP handoff."""
import io
import json
import subprocess
import tarfile
from pathlib import Path

import numpy as np
import yaml
from ase.io import read

from scripts.artifact_io import sha256_file, write_json
from scripts.aqcat25_handoff import validate_handoff
from scripts.adsorption.build_fe110_adsorption import read_poscar, fe110_anchor_site_distances
from scripts.adsmind_lite.relaxed_analysis import connectivity_edges, connectivity_change
from scripts.workflow_geometry import minimum_image_delta_xy

ROOT = Path(__file__).resolve().parents[2]
BATCH = ROOT / "calculations/fe110_five_c2_adsorption_20261006/gpu_batch_v4"
REMOTE = "/home/sbq/sbq/aqcat25_ts_pilot/fe110_five_c2_adsorption_20261006_gpu_v4"


def main():
    manifest = json.loads((BATCH / "batch_manifest.json").read_text())
    names = [item["name"] for item in manifest["handoffs"]]
    collect(names)
    review(names)


def collect(names):
    required = {"POSCAR", "result.json", "gpu_result_manifest.json", "producer_exit_record.json"}
    if all((BATCH / name / "output/job_2139" / filename).is_file() for name in names for filename in required):
        return
    # Legacy SCP worked for early returns; SSH tar avoids the failing SFTP subsystem.
    command = "tar -cf - -C " + REMOTE + " " + " ".join(name+"/output/job_2139" for name in names)
    transfer = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "IdentitiesOnly=yes",
                          "-i", "C:/Users/86177/.ssh/id_ed25519_fe_agent", "-p", "36039",
                          "sbq@10sx4jr711576.vicp.fun", command], capture_output=True)
    if transfer.returncode:
        raise RuntimeError(transfer.stderr.decode(errors="replace")[-2000:])
    raw = transfer.stdout
    if len(raw) > 2_000_000:
        raise ValueError("Unexpectedly large return")
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            parts = Path(member.name).parts
            assert member.isfile() and len(parts) == 4 and parts[0] in names
            assert parts[1:3] == ("output", "job_2139")
            assert parts[3] in {"POSCAR", "result.json", "gpu_result_manifest.json", "producer_exit_record.json"}
            content = archive.extractfile(member).read()
            target = BATCH / member.name
            if target.exists():
                assert target.read_bytes() == content, "Do not overwrite a different returned file"
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)


def review(names):
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text())
    slab = read_poscar(ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR")
    records, atoms_by_name = [], {}
    for name in names:
        directory = BATCH / name
        output = directory / "output/job_2139"
        doc = validate_handoff(output / "gpu_result_manifest.json", root=directory)
        initial, final = read(directory / "POSCAR"), read(output / "POSCAR")
        indices = list(range(45, len(final)))
        initial_edges = connectivity_edges(initial, indices, rules["connectivity"]["covalent_radius_scale"], rules["connectivity"]["minimum_bond_distance_angstrom"])
        final_edges = connectivity_edges(final, indices, rules["connectivity"]["covalent_radius_scale"], rules["connectivity"]["minimum_bond_distance_angstrom"])
        chemistry = connectivity_change(len(indices), initial_edges, final_edges)
        contact = min(final.get_distance(i, j, mic=True) for i in indices for j in range(45))
        invariants = doc["result"]["structure_invariants"]
        assert all(invariants.values()) and np.allclose(initial.cell, final.cell, atol=1e-10)
        assert np.allclose(initial.positions[:18], final.positions[:18], atol=1e-8)
        assert doc["producer"]["gpu_job_id"] == "2139"
        sites = []
        for index in indices:
            if final[index].symbol == "H":
                continue
            distances = fe110_anchor_site_distances(slab, final.get_scaled_positions()[index])
            site = min(distances, key=distances.get)
            sites.append({"index_0based": index, "element": final[index].symbol, "site": site,
                          "lateral_A": distances[site],
                          "nearest_Fe_A": min(final.get_distance(index, j, mic=True) for j in range(45))})
        eligible = bool(not chemistry["connectivity_changed"] and contact >= rules["contact_validation"]["hard_contact_distance_angstrom"])
        record = {"candidate": name, "source_sha256": sha256_file(output / "POSCAR"),
                  "return_validation": "PASS", "steps": doc["result"]["optimizer_steps"],
                  "fmax_eV_A": doc["result"]["predicted_force"]["fmax"],
                  "predicted_energy_eV_not_DFT": doc["result"]["predicted_energy"]["value"],
                  "chemistry": chemistry, "sites": sites, "minimum_surface_contact_A": contact,
                  "eligible_initial_VASP_candidate": eligible, "duplicate_of": None}
        records.append(record)
        atoms_by_name[name] = final
    # Conservative duplicate check: retain surface-relative orientation; no arbitrary Kabsch rotations.
    retained = []
    for record in sorted(records, key=lambda item: item["predicted_energy_eV_not_DFT"]):
        if not record["eligible_initial_VASP_candidate"]:
            continue
        atoms = atoms_by_name[record["candidate"]]
        for previous in retained:
            if previous["candidate"][:2] != record["candidate"][:2]:
                continue
            if [s["site"] for s in previous["sites"]] != [s["site"] for s in record["sites"]]:
                continue
            prior = atoms_by_name[previous["candidate"]]
            # Compare same-index absolute adsorption coordinates under the actual cell PBC.
            delta = minimum_image_delta_xy(atoms.get_scaled_positions()[45:] - prior.get_scaled_positions()[45:]) @ atoms.cell.array
            rmsd = float(np.sqrt(np.mean(np.sum(delta**2, axis=1))))
            if rmsd <= rules["duplicate_detection"]["geometry_rmsd_tolerance_angstrom"] and abs(record["predicted_energy_eV_not_DFT"]-previous["predicted_energy_eV_not_DFT"]) <= rules["duplicate_detection"]["energy_tolerance_ev"]:
                record["duplicate_of"] = previous["candidate"]
                record["duplicate_RMSD_A"] = rmsd
                break
        if record["duplicate_of"] is None:
            retained.append(record)
    result = {"job_id": "2139", "producer_exit_codes": [0]*12,
              "source_review": "Predicted starting geometry only; not final adsorption acceptance.",
              "records": records, "selected": [r["candidate"] for r in retained],
              "lost_target_species": ["03"], "submit_vasp": False}
    write_json(ROOT / "calculations/fe110_five_c2_adsorption_20261006/gpu_return_review.json", result)
    for record in records:
        print(json.dumps({k: record[k] for k in ("candidate", "steps", "chemistry", "eligible_initial_VASP_candidate", "duplicate_of", "sites")}, ensure_ascii=True))
    print("SELECTED", result["selected"])


if __name__ == "__main__":
    main()
