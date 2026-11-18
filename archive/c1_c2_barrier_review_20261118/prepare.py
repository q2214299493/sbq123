"""Prepare two electronic-barrier review packets, never accept or register them."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from ase.io import read

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.neb_agent.utils_vasp import parse_oszicar, parse_outcar
from scripts.registry_connection import open_registry
from scripts.ts_strategy_engine.evidence import validate_endpoint_evidence
from scripts.ts_strategy_engine.matched_static_evidence import barrier_values
from scripts.vasp_result_gate import final_scf_state, read_incar_values


ROOT = Path(__file__).resolve().parents[2]
DATABASE = ROOT / "data/project_registry.sqlite3"
OUTPUT = ROOT / "outputs/c1_c2_barrier_review_20261118_v1"
CASES = {
    "ch_co": ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109/ts_acceptance_20261115_v1/vfa/vfa_analysis.json",
    "int06_mid": ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/vfa_ci9796856_image04_local_h_fe_20260925/vfa_analysis.json",
}
CONVENTION = "fe110_converged_toten_sigma0p20_v1"


def ref(path):
    return {"path": str(path), "sha256": sha256_file(path)}


def geometry(path):
    atoms = read(path, format="vasp")
    fixed = sorted({int(i) for constraint in atoms.constraints for i in constraint.get_indices()})
    return {**ref(path), "symbols": atoms.get_chemical_symbols(), "cell_A": atoms.cell.array.tolist(),
            "composition": dict(Counter(atoms.get_chemical_symbols())), "fixed_indices_zero_based": fixed}


def source_record(outcar, structure, expected_hash):
    if sha256_file(outcar) != expected_hash:
        raise ValueError(f"Source output changed: {outcar}")
    directory = outcar.parent
    incar = directory / "INCAR"
    if not incar.is_file():
        incar = directory.parent / "INCAR"  # A NEB image uses its common input.
    values = read_incar_values(incar)
    parsed = parse_outcar(outcar, include_final_forces=True, include_sha256=True)
    scf = final_scf_state(parse_oszicar(directory / "OSZICAR"), values, parsed)
    if not parsed["normal_completion"] or parsed["fatal_keywords"] or not scf["electronically_converged"]:
        raise ValueError(f"Source not normally/electronically complete: {outcar}")
    if not (float(values["ENCUT"]) == 400 and int(values["ISPIN"]) == 2
            and int(values["ISMEAR"]) == 1 and float(values["SIGMA"]) == 0.2):
        raise ValueError(f"Source not on the locked electronic branch: {incar}")
    geom = geometry(structure)
    forces = parsed["forces_eV_per_A"]
    if forces is None or len(forces) != len(geom["symbols"]):
        raise ValueError("Incomplete final force block")
    return {"outcar": ref(outcar), "structure": geom, "incar": {**ref(incar), "values": values},
            "final_toten_eV": parsed["final_toten_eV"], "normal_completion": True, "scf": scf,
            "last_FORCES_max_atom_eVA": parsed["atomic_force_history"][-1] if parsed["atomic_force_history"] else None,
            "final_force_vectors_max_eVA": float(np.linalg.norm(forces, axis=1).max()),
            "force_threshold_eVA": abs(float(values["EDIFFG"])), "final_output_hash_matches": parsed["source_sha256"] == expected_hash}


def endpoint(connection, record):
    result = dict(connection.execute("SELECT * FROM results WHERE result_id=?", [record["static_result_id"]]).fetchone())
    file = dict(connection.execute("SELECT * FROM files WHERE file_id=?", [result["source_file_id"]]).fetchone())
    structure = dict(connection.execute("SELECT * FROM files WHERE file_id=?", [record["structure_file_id"]]).fetchone())
    if sha256_file(Path(structure["local_path"])) != structure["sha256"]:
        raise ValueError("Registered endpoint structure changed")
    evidence = source_record(Path(file["local_path"]), Path(structure["local_path"]), file["sha256"])
    if result["reference_convention"] != CONVENTION or abs(result["numeric_value"] - evidence["final_toten_eV"]) > 1e-8:
        raise ValueError("Registered endpoint value differs from source")
    return {"registered_result": result, "registered_energy_file": file, "registered_structure_file": structure, **evidence}


def prepare_case(connection, key, vfa_path):
    vfa = load_json_object(vfa_path)
    contract = vfa["reaction_contract"]
    handoff_path = Path(vfa["vfa_handoff"])
    handoff = load_json_object(handoff_path)
    source_structure = Path(handoff["source_ts_candidate"])
    source_outcar = source_structure.with_name("OUTCAR")
    source_hash = next(item["sha256"] for item in vfa["source_files"] if Path(item["path"]) == source_outcar)
    ts = source_record(source_outcar, source_structure, source_hash)
    members = {name: endpoint(connection, record) for name, record in contract["endpoints"].items()}
    members["ts"] = ts
    geoms = [members[name]["structure"] for name in ("initial", "ts", "final")]
    geometry_checks = {"atom_identity_order": all(g["symbols"] == geoms[0]["symbols"] for g in geoms),
        "cell": all(np.allclose(g["cell_A"], geoms[0]["cell_A"], atol=1e-9, rtol=0) for g in geoms),
        "fixed_mask": all(g["fixed_indices_zero_based"] == contract["compatibility"]["fixed_atom_indices_zero_based"] for g in geoms)}
    if not all(geometry_checks.values()):
        raise ValueError(f"Source identity/cell/fixed-mask mismatch: {geometry_checks}")
    validation = dict(connection.execute("SELECT * FROM ts_validations WHERE source_saddle_calculation_id=? AND grade='A'",
        [vfa["source_saddle_calculation_id"]]).fetchone())
    if validation["contract_sha256"] != vfa["contract_sha256"] or validation["compatibility_fingerprint"] != vfa["compatibility_sha256"]:
        raise ValueError("Registered validation identity mismatch")
    current = load_json_object(OUTPUT / key / "current_ts_gate.json")
    values = barrier_values([{"numeric_value": members[name]["final_toten_eV"]} for name in ("initial", "ts", "final")])
    existing = {name: [dict(row) for row in connection.execute(f"SELECT * FROM {name} WHERE calculation_id=?",
        [vfa["source_saddle_calculation_id"]])] for name in ("results", "calculation_compatibility")}
    sources = [{**ref(Path(item["path"])), "expected_sha256": item["sha256"],
                "matches": sha256_file(Path(item["path"])) == item["sha256"]} for item in vfa["source_files"]]
    return {"status": "PREPARED_WITH_BLOCKERS_NOT_APPROVED", "reaction_id": contract["reaction_id"],
        "energy_convention": CONVENTION, "source_method": vfa["source_method"],
        "registered_grade_a_validation": validation, "original_analysis": ref(vfa_path), "handoff": ref(handoff_path),
        "source_members": members, "geometry_checks": geometry_checks,
        "endpoint_registry_check": validate_endpoint_evidence(DATABASE, contract),
        "compatibility_proposal": {"document": contract["compatibility"], "sha256": vfa["compatibility_sha256"],
            "calculation_id": vfa["source_saddle_calculation_id"], "approved_for_database_write": False},
        "draft_electronic_barrier_eV": values, "draft_value_scope": "arithmetic review only;not a registered or report-authorized barrier",
        "current_ts_gate": {**ref(OUTPUT / key / "current_ts_gate.json"), "decision": current["DECISION"],
            "allowed_actions": current["ALLOWED_ACTIONS"], "explanation": current.get("CHEMICAL_INTERPRETATION")},
        "old_validation_source_checks": sources, "existing_ts_registry_dependencies": existing,
        "registration_sequence_after_review": ["Refresh/review stale analysis bindings without overwriting originals",
            "Obtain a fresh claim-bound TS gate", "Review/register TS final energy,compatibility,source/status/TS-structure dependencies",
            "Recheck the complete chain with matched_static_rows/matched_static_convention",
            "Atomically register barrier and strategy-only Grade-A learning record via record-barrier"],
        "learning_record_scope": {"required": True, "ready_for_registration": False,
            "restriction": "Method strategy only;no transferable indices,coordinates,MODECAR,images,job IDs,energies or barriers"},
        "approval": None, "scientific_execution_authorized": False, "registry_write_authorized": False,
        "zpe_entropy_free_energy_included": False}


def registration_draft(packet, key):
    source = packet["registered_grade_a_validation"]["source_saddle_calculation_id"]
    result_id = source + "_final_toten_sigma0p20_eV"
    return {"document_kind": "non_executable_barrier_registration_review_request", "schema_version": 1,
        "status": "DRAFT_NOT_APPROVED", "reaction_id": packet["reaction_id"],
        "barrier_set_id_proposal": "fe110_" + key + "_sigma0p20_review_20261118",
        "ts_validation_id": packet["registered_grade_a_validation"]["ts_validation_id"],
        "source_calculation_id": source,
        "initial_result_id": packet["source_members"]["initial"]["registered_result"]["result_id"],
        "ts_result_proposal": {"result_id": result_id, "calculation_id": source, "result_name": "final_toten",
            "numeric_value": packet["source_members"]["ts"]["final_toten_eV"], "unit": "eV",
            "reference_convention": packet["energy_convention"], "source": packet["source_members"]["ts"]["outcar"],
            "intended_validation_status_after_owner_acceptance": "accepted_compatible_final_energy",
            "accepted_in_registry": False},
        "final_result_id": packet["source_members"]["final"]["registered_result"]["result_id"],
        "ts_structure_file_proposal": {"file_id": source + "_barrier_review_20261118_ts_structure",
            "role": "ts_structure", "source": packet["source_members"]["ts"]["structure"]},
        "compatibility_proposal": packet["compatibility_proposal"],
        "draft_barrier_values_eV": packet["draft_electronic_barrier_eV"],
        "mandatory_atomic_learning_record": packet["learning_record_scope"],
        "preconditions": packet["registration_sequence_after_review"],
        "current_gate": packet["current_ts_gate"], "approval": None,
        "registry_apply_manifest": None, "database_write_performed": False}


def main():
    if (OUTPUT / "review_summary.json").exists():
        raise ValueError("Refuse overwrite of existing review")
    packets = {}
    with open_registry(DATABASE) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        before = {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                  for name in ("results", "ts_barriers", "ts_validations", "ts_strategy_templates")}
        for key, vfa in CASES.items():
            packets[key] = prepare_case(connection, key, vfa)
        connection.rollback()
    for key, packet in packets.items():
        write_json_exclusive(OUTPUT / key / "review_packet.json", packet)
        write_json_exclusive(OUTPUT / key / "registration_request.draft.json", registration_draft(packet, key))
    summary = {"status": "PREPARED_WITH_BLOCKERS_NOT_APPROVED", "client_date": "2026-11-18 Asia/Shanghai",
        "created_at": datetime.now(timezone.utc).isoformat(), "database": str(DATABASE), "registry_query_only": True,
        "registry_counts_at_snapshot": before, "packets": {key: {**ref(OUTPUT/key/"review_packet.json"),
            "content_sha256": sha256_json(packet), "draft_values": packet["draft_electronic_barrier_eV"],
            "current_gate": packet["current_ts_gate"]["decision"]} for key, packet in packets.items()},
        "formal_registration_performed": False, "new_scientific_jobs": False,
        "approval": None, "next_action": "Review binding differences and registration dependencies;do not rerun science by default"}
    write_json_exclusive(OUTPUT / "review_summary.json", summary)
    print({key: {"draft_values": p["draft_electronic_barrier_eV"], "endpoint_check": p["endpoint_registry_check"]["status"],
        "current_gate": p["current_ts_gate"]["decision"]} for key, p in packets.items()})


if __name__ == "__main__":
    main()
