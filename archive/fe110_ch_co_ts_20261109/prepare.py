"""Prepare a local CH* + CO* -> CH-C-O* path review; never submit jobs."""
from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import numpy as np

from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar, write_poscar
from scripts.adsorption.build_fe110_care_batch import pose_measurements
from scripts.adsorption.build_fe110_care_isomers import connectivity, surface_pose_symmetries
from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry
from scripts.ts_endpoint.validator import BondChange, EndpointValidationRequest, TSEndpointValidator
from scripts.ts_strategy_engine.contract import normalize_contract
from scripts.ts_strategy_engine.evidence import validate_endpoint_evidence
from scripts.workflow_geometry import minimum_image_delta_xy


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109/review_ready_v2"
DATABASE = ROOT / "data/project_registry.sqlite3"
INITIAL = "fe110_five_c2_adsorption_20261006_03_cfg0_direct_vasp_CH_CO_reclassified_20261021"
FINAL = "fe110_five_c2_adsorption_20261006_03_extra2_repair_v1"
CLEAN_SHA = "3337ad4e89a2719551035fadbd5082a60c12cafcadc14748d8b48a198379109d"


def distance(pose, left, right):
    return float(np.linalg.norm(minimum_image_delta_xy(pose.frac[right] - pose.frac[left]) @ pose.cell))


def load_sources():
    records = []
    with open_registry(DATABASE) as db:
        db.execute("PRAGMA query_only=ON")
        for cid in (INITIAL, FINAL):
            compatibility = db.execute(
                "SELECT compatibility_json FROM calculation_compatibility WHERE calculation_id=?", (cid,),
            ).fetchone()
            files = db.execute(
                "SELECT file_id,filename,local_path,sha256 FROM files WHERE calculation_id=? "
                "AND filename IN ('CONTCAR','OUTCAR')", (cid,),
            ).fetchall()
            energy = db.execute(
                "SELECT result_id,numeric_value,reference_convention FROM results WHERE calculation_id=? "
                "AND result_name='final_toten' AND validation_status='accepted_compatible_final_energy'", (cid,),
            ).fetchall()
            if len(files) != 2 or len(energy) != 1 or compatibility is None:
                raise ValueError("Missing unique registered endpoint sources or accepted energy: " + cid)
            sources = {row["filename"]: dict(row) for row in files}
            for source in sources.values():
                if sha256_file(Path(source["local_path"])) != source["sha256"]:
                    raise ValueError("Registered source hash mismatch: " + source["file_id"])
            records.append({"calculation_id": cid, "compatibility": json.loads(compatibility[0]),
                            "sources": sources, "energy": dict(energy[0])})
        clean_row = db.execute("SELECT local_path FROM files WHERE sha256=? LIMIT 1", (CLEAN_SHA,)).fetchone()
    if records[0]["compatibility"] != records[1]["compatibility"]:
        raise ValueError("Full endpoint compatibility differs.")
    if clean_row is None or sha256_file(Path(clean_row[0])) != CLEAN_SHA:
        raise ValueError("Clean slab source not verified.")
    return records, clean_row


def main():
    if OUT.exists():
        raise SystemExit("Output already exists; do not overwrite prepared evidence.")
    records, clean_row = load_sources()

    initial = read_poscar(Path(records[0]["sources"]["CONTCAR"]["local_path"]))
    final = read_poscar(Path(records[1]["sources"]["CONTCAR"]["local_path"]))
    slab = read_poscar(Path(clean_row[0]))
    symbols = expanded_symbols(initial)
    if symbols != expanded_symbols(final) or not np.array_equal(initial.cell, final.cell):
        raise ValueError("Endpoint order or cell mismatch.")
    if initial.flags != final.flags:
        raise ValueError("Selective Dynamics differs.")
    ads = [i for i, symbol in enumerate(symbols) if symbol != "Fe"]
    carbons = [i for i in ads if symbols[i] == "C"]
    hydrogen, = [i for i in ads if symbols[i] == "H"]
    oxygen, = [i for i in ads if symbols[i] == "O"]
    ch_carbon = min(carbons, key=lambda i: distance(initial, i, hydrogen))
    co_carbon, = [i for i in carbons if i != ch_carbon]
    expected_initial = {tuple(sorted(pair)) for pair in ((ch_carbon, hydrogen), (co_carbon, oxygen))}
    expected_final = expected_initial | {tuple(sorted(carbons))}
    for pose, expected in ((initial, expected_initial), (final, expected_final)):
        actual = {tuple(sorted((ads[a], ads[b]))) for a, b in connectivity(pose, ads)}
        if actual != expected:
            raise ValueError("Unexpected endpoint graph; do not substitute another C2HO isomer.")

    fixed = [i for i, flags in enumerate(initial.flags) if flags == ("F", "F", "F")]
    choices = []
    for rotation, translation in surface_pose_symmetries(slab):
        transformed_slab = slab.frac @ rotation.T + translation
        distances = np.linalg.norm(minimum_image_delta_xy(
            transformed_slab[:, None] - slab.frac[None, :]) @ slab.cell, axis=2)
        mapping = np.argmin(distances, axis=1)
        if len(set(mapping)) != len(slab.frac) or distances[np.arange(len(mapping)), mapping].max() > 0.01:
            continue
        permutation = np.argsort(mapping)
        if set(mapping[fixed]) != set(fixed):
            continue
        transformed = final.frac @ rotation.T + translation
        transformed[:45] = transformed[:45][permutation]
        frac = initial.frac + minimum_image_delta_xy(transformed - initial.frac)
        delta = (frac - initial.frac) @ initial.cell
        fixed_error = float(np.max(np.linalg.norm(delta[fixed], axis=1)))
        if fixed_error > 1e-6:
            continue
        score = float(np.sum(delta[ads] ** 2))
        choices.append((score, rotation, translation, permutation, frac, fixed_error))
    if not choices:
        raise ValueError("No face/fixed-layer-preserving surface mapping.")
    _, rotation, translation, permutation, mapped_frac, fixed_error = min(choices, key=lambda x: x[0])
    mapped_frac[fixed] = initial.frac[fixed]
    final = replace(final, frac=mapped_frac,
                    comment="CH-C-O FS; clean-slab symmetry and Fe permutation; no relaxation")

    OUT.mkdir(parents=True)
    endpoint_dir = OUT / "endpoints"
    endpoint_dir.mkdir()
    shutil.copyfile(records[0]["sources"]["CONTCAR"]["local_path"], endpoint_dir / "IS.vasp")
    write_poscar(endpoint_dir / "FS_symmetry_mapped.vasp", final)
    # Pure geometry waypoint, not a saddle prediction or force restraint.
    waypoint = read_poscar(endpoint_dir / "IS.vasp")
    waypoint = replace(waypoint, frac=initial.frac + 0.5 * (final.frac - initial.frac))
    cart = waypoint.frac @ waypoint.cell
    for anchor, terminal in ((ch_carbon, hydrogen), (co_carbon, oxygen)):
        vector = minimum_image_delta_xy(waypoint.frac[terminal] - waypoint.frac[anchor]) @ waypoint.cell
        length = 0.5 * (distance(initial, anchor, terminal) + distance(final, anchor, terminal))
        cart[terminal] = cart[anchor] + length * vector / np.linalg.norm(vector)
    waypoint = replace(waypoint, frac=cart @ np.linalg.inv(waypoint.cell))
    waypoint.frac[fixed] = initial.frac[fixed]
    waypoint = replace(waypoint, comment="Proposed C-C alignment waypoint; C-H/C-O retained; review only")
    write_poscar(endpoint_dir / "waypoint.vasp", waypoint)

    endpoint_links = {
        name: {"calculation_id": record["calculation_id"],
               "structure_file_id": record["sources"]["CONTCAR"]["file_id"],
               "static_result_id": record["energy"]["result_id"]}
        for name, record in zip(("initial", "final"), records, strict=True)
    }
    contract = normalize_contract({
        "reaction_id": "fe110_ch_co_to_chco_20261109", "reaction_family": "co_insertion",
        "reactant_id": "ch_star_plus_co_star/fe110_fe45", "product_id": "ch_c_o_star/fe110_fe45",
        "index_base": 0, "atom_map": [[i, i] for i in range(len(symbols))],
        "atom_symbols": symbols, "reaction_atoms": ads, "broken_bonds": [],
        "formed_bonds": [carbons], "site_changes": [],
        "compatibility": records[0]["compatibility"], "endpoints": endpoint_links,
        "waypoint_files": ["endpoints/waypoint.vasp"],
    })
    write_json_exclusive(OUT / "reaction_contract.json", contract)
    registered = validate_endpoint_evidence(DATABASE, contract)
    write_json_exclusive(OUT / "registered_endpoint_check.json", registered)
    validation = TSEndpointValidator().validate(EndpointValidationRequest(
        initial_structure=endpoint_dir / "IS.vasp", endpoint_structure=endpoint_dir / "FS_symmetry_mapped.vasp",
        reactive_atoms=tuple(ads), adsorbate_atoms=tuple(ads), surface_atoms=tuple(range(45)),
        bond_changes=(BondChange("form", tuple(carbons)),),
        atom_map=tuple((i, i) for i in range(len(symbols))), surface="fe110", reaction_type="co_insertion",
    ))
    write_json_exclusive(OUT / "endpoint_event_validation.json", validation.as_dict())
    write_json_exclusive(OUT / "endpoint_provenance.json", {
        "status": "LOCAL_PREPARATION_ONLY_AWAITING_REVIEW", "sources": records,
        "clean_slab": {"path": clean_row[0], "sha256": CLEAN_SHA},
        "fs_derivation": {"rotation_fractional": rotation.tolist(), "translation_fractional": translation.tolist(),
                          "new_Fe_order_from_original": permutation.tolist(),
                          "fixed_atom_roundoff_snapped_max_A": fixed_error,
                          "same_transform_applied_to_all_atoms": True, "adsorbate_roles_permuted": False},
        "prepared_files": {name: sha256_file(endpoint_dir / name) for name in
                           ("IS.vasp", "FS_symmetry_mapped.vasp", "waypoint.vasp")},
        "identity": {"CH_carbon": ch_carbon, "CO_carbon": co_carbon, "O": oxygen, "H": hydrogen},
        "measurements": {name: pose_measurements(pose) for name, pose in
                         (("IS", initial), ("FS_mapped", final), ("waypoint", waypoint))},
        "reaction_energy_eV_not_barrier": records[1]["energy"]["numeric_value"] - records[0]["energy"]["numeric_value"],
        "waypoint_C_C_A": distance(waypoint, *carbons),
        "intended_internal_images": 5,
        "image_count_rationale": "~2.03 A maximum mapped adsorbate motion; two segments around C-C alignment; geometry review required",
        "authorization": {"GPU": False, "VASP": False, "training": False},
    })
    print(json.dumps({"registry": registered["status"], "event_validation": validation.as_dict()["status"],
                      "output": str(OUT), "waypoint_C_C_A": distance(waypoint, *carbons)}))
    if registered["status"] != "PASS" or validation.errors:
        raise SystemExit("Endpoint gate needs review; no calculation/path submission.")


if __name__ == "__main__":
    main()
