"""Accept final saddle TOTEN only from the currently validated TS object."""
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, sha256_json
from scripts.neb_agent.utils_vasp import parse_outcar, parse_oszicar
from scripts.scientific_validation import finite_number
from scripts.ts_strategy_engine.execution_gate import require_action
from scripts.vasp_result_gate import final_scf_state, read_incar_values


CONVENTION = "fe110_converged_toten_sigma0p20_v1"


def _saddle_sources(state, analysis_path):
    handoff_path = (analysis_path.parent / state["vfa_handoff"]).resolve(strict=True)
    handoff = load_json_object(handoff_path)
    saddle = (handoff_path.parent / handoff["source_ts_candidate"]).resolve(strict=True)
    outcar = saddle.with_name("OUTCAR")
    incar = (saddle.parent if state["source_method"] == "dimer" else saddle.parent.parent) / "INCAR"
    paths = (saddle, outcar, incar, saddle.with_name("OSZICAR"))
    sources = {Path(item["path"]).resolve(): item["sha256"] for item in state["source_files"]}
    if not all(path in sources and sha256_file(path) == sources[path] for path in paths):
        raise ValueError("TS final-energy sources missing, unbound or stale")
    return paths, sources


def _require_registered_saddle(connection, state, row, compatibility):
    claim = state.get("barrier_claim") or {}
    cid = row["calculation_id"]
    if claim.get("ts_result_id") != row["result_id"] or claim.get("source_calculation_id") != cid:
        raise ValueError("Current barrier gate does not name this saddle energy")
    record = connection.execute("SELECT * FROM ts_validations WHERE ts_validation_id=?",
                                (claim["ts_validation_id"],)).fetchone()
    keys = {"validation_calculation_id": "calculation_id", "source_saddle_calculation_id": "source_saddle_calculation_id",
            "source_method": "source_method", "frequency_output_file_id": "frequency_output_file_id",
            "contract_sha256": "contract_sha256", "atom_map_sha256": "atom_map_sha256",
            "compatibility_sha256": "compatibility_fingerprint"}
    if (record is None or record["grade"] != "A" or record["kinetic_eligible"] != 1
            or record["source_saddle_calculation_id"] != cid or record["source_method"] not in {"dimer", "ci_neb"}
            or any(state.get(k) != record[v] for k, v in keys.items())
            or state["compatibility_sha256"] != sha256_json(compatibility)):
        raise ValueError("Current gate, registered Grade-A TS and energy compatibility differ")
    return record


def validate_saddle_energy(connection, row, validation, target):
    if (target["domain"] != "transition_state_search" or row["result_name"] != "final_toten"
            or row["unit"] != "eV" or row["validation_status"] != "accepted_compatible_final_energy"
            or row["reference_convention"] != CONVENTION or target["compatibility"].get("final_energy_convention") != CONVENTION):
        raise ValueError("Expected a production-branch TS final TOTEN in eV")
    gate = require_action(Path(validation["gate_decision"]), "APPROVE_TS_CANDIDATE", validation["gate_state_sha256"])
    state = gate["EVIDENCE"]["validation"]
    record = _require_registered_saddle(connection, state, row, target["compatibility"])
    analysis_path = Path(gate["EVIDENCE"]["source_bindings"]["validation"]["path"])
    (saddle, outcar, incar, oszicar), sources = _saddle_sources(state, analysis_path)
    registered = connection.execute("SELECT * FROM files WHERE file_id=?", (row["source_file_id"],)).fetchone()
    if (registered is None or registered["calculation_id"] != row["calculation_id"]
            or registered["job_record_id"] != record["source_job_record_id"] or registered["existence_status"] != "confirmed"
            or Path(registered["local_path"]).resolve() != outcar or registered["sha256"] != sources[outcar]):
        raise ValueError("Registered OUTCAR does not bind the validated saddle job")
    settings = read_incar_values(incar)
    if (int(settings["ISMEAR"]), float(settings["SIGMA"]), float(settings["ENCUT"]), int(settings["ISPIN"])) != (1, .2, 400., 2):
        raise ValueError("Saddle did not use production electronic settings")
    parsed = parse_outcar(outcar, include_final_forces=True, include_sha256=True)
    if (not parsed["normal_completion"] or parsed["fatal_keywords"]
            or not final_scf_state(parse_oszicar(oszicar), settings, parsed)["electronically_converged"]
            or finite_number(parsed["final_toten_eV"], "final TOTEN") != finite_number(row["numeric_value"], "result energy")
            or parsed["source_sha256"] != sources[outcar]
            or any(sha256_file(p) != sources[p] for p in (saddle, outcar, incar, oszicar))):
        raise ValueError("Final saddle energy or completion fails current output validation")
