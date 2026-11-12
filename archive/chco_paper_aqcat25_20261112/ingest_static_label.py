"""Review one 49-atom paper static label with owning parsers; never accept state.

The legacy production label schema is closed. Write its standard label plus a
separate, raw-byte-bound extension carrying geometry/request/magnetic evidence.
The extension retains the base kind required by paper_sequential, but is outside
the legacy production schema. Neither artifact accepts state or a TS.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


def require(passed: bool, message: str) -> None:
    if not passed:
        raise ValueError(message)


def review(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    import numpy as np
    from ase.geometry import find_mic
    from ase.io import read
    from pymatgen.io.vasp.inputs import Kpoints
    from scripts.aqcat25_calibration import parse_final_outcar
    from scripts.aqcat25_ts_schema import validate_document
    from scripts.artifact_io import load_json_object, sha256_file
    from scripts.matris_training_exclusions import geometry_fingerprint
    from scripts.neb_agent.mz73_static import load_reviewed_case_contract
    from scripts.neb_agent.submission import InputBundle
    from scripts.neb_agent.utils_structure import read_poscar
    from scripts.neb_agent.utils_vasp import parse_outcar
    from scripts.slurm_force_label import verify_slurm_force_label_live
    from scripts.ts_strategy_engine.paper_sequential import validate_state
    from scripts.vasp_result_gate import final_scf_status, read_incar_values

    directory = args.directory.resolve(strict=True)
    paths = {name: directory / name for name in (
        "POSCAR", "INCAR", "KPOINTS", "POTCAR", "POTCAR.spec", "OUTCAR", "OSZICAR",
        "submission_preflight.json", "submission_record.json")}
    paths.update(state=args.state, contract=args.contract, scheduler=args.scheduler_evidence, backend_config=args.backend_config)
    sources = {name: {"path": str(path.resolve(strict=True)), "sha256": sha256_file(path)} for name, path in paths.items()}
    require(sources["state"]["sha256"] == args.state_sha256, "reviewed paper state bytes changed")
    state = load_json_object(args.state)
    validate_state(state)
    require(state["status"] == "awaiting_accepted_label", "record_execution must precede ingestion")
    row, protocol = state["evaluations"][-1], state["protocol"]
    execution, request = row["execution"], row["request"]
    require(execution is not None and protocol["atom_count"] == 49, "one executed 49-atom request is required")
    require(sources["POSCAR"]["sha256"] == request["candidate_structure_sha256"], "candidate POSCAR bytes changed")
    contract = load_reviewed_case_contract(args.contract, workdir_name=directory.name, config_path=args.backend_config)
    require(all(contract[key] == protocol[key] for key in ("contract_sha256", "compatibility_sha256")), "contract/compatibility mismatch")
    compatibility = contract["compatibility"]
    preflight = load_json_object(paths["submission_preflight.json"])
    require(preflight.get("experimental_backend") == "mz73_paper_vasp", "not the scoped Slurm experiment")
    bundle = InputBundle.from_preflight(preflight)
    bundle.verify(directory)
    for name, digest in bundle.files:
        paths[name] = directory / name
        sources[name] = {"path": str(paths[name].resolve(strict=True)), "sha256": digest}
    require(bundle.kind == "diagnostic_static" and bundle.bundle_sha256 == execution["bundle_sha256"], "reviewed input bundle mismatch")
    receipt = load_json_object(paths["submission_record.json"])
    require(receipt.get("status") == "SUBMITTED" and receipt.get("scheduler") == "Slurm"
            and receipt.get("server_alias") == "mz73_paper_vasp", "missing native Slurm submission receipt")
    for recorded, expected in (("job_id", execution["job_id"]), ("bundle_sha256", execution["bundle_sha256"]),
                               ("gate_decision_sha256", execution["gate_sha256"])):
        require(receipt.get(recorded) == expected, f"submission {recorded} mismatch")
    require(sources["POTCAR"]["sha256"] == receipt["potcar_sha256"] == compatibility["potcar_bundle_sha256"], "POTCAR bundle mismatch")
    require(sources["POTCAR.spec"]["sha256"] == dict(bundle.files)["POTCAR.spec"], "POTCAR spec mismatch")
    values = read_incar_values(paths["INCAR"])
    expected_values = {"NSW": 0, "IBRION": -1, "ISPIN": 2, "ENCUT": compatibility["encut_ev"],
                       "EDIFF": compatibility["ediff_ev"], "ISMEAR": compatibility["ismear"], "SIGMA": compatibility["sigma_ev"]}
    require(all(float(values.get(key, "nan")) == value for key, value in expected_values.items()), "static magnetic/DFT compatibility mismatch")
    kpoints = Kpoints.from_file(paths["KPOINTS"])
    require(kpoints.kpts == [tuple(compatibility["kmesh"])] and str(kpoints.style) == "Gamma"
            and tuple(kpoints.kpts_shift) == (0.0, 0.0, 0.0), "KPOINTS compatibility mismatch")
    structure = read_poscar(paths["POSCAR"])
    require(structure.labels == contract["atom_symbols"] and len(structure.labels) == 49, "atom mapping mismatch")
    require(structure.selective and all(tuple(flags) in (("F", "F", "F"), ("T", "T", "T")) for flags in structure.flags), "unsupported SD mask")
    fixed = [index for index, flags in enumerate(structure.flags) if tuple(flags) == ("F", "F", "F")]
    require(fixed == compatibility["fixed_atom_indices_zero_based"] == sorted(set(range(49)) - set(protocol["movable_atom_indices_zero_based"])), "fixed-atom compatibility mismatch")
    require(np.allclose(structure.cell, compatibility["cell_angstrom"], atol=1e-8, rtol=0), "input cell mismatch")
    geometry = geometry_fingerprint(structure)
    require(sources["POSCAR"]["sha256"] not in protocol["held_out_structure_sha256"] and
            geometry not in protocol["held_out_geometry_sha256"], "protected structure/geometry cannot become a training label")
    parsed = parse_final_outcar(paths["OUTCAR"])
    scf = final_scf_status(paths["OSZICAR"], paths["INCAR"], paths["OUTCAR"])
    magnetic = parse_outcar(paths["OUTCAR"])
    require(parsed["normal_completion"] and magnetic["normal_completion"] and not magnetic["fatal_keywords"]
            and magnetic.get("run_index", 1) <= 1, "incomplete, failed or concatenated VASP output")
    require(scf["electronically_converged"] and scf["last_electronic_iteration"] < scf["nelm"], "electronic convergence failed")
    forces = np.asarray(parsed["forces_eV_per_A"], dtype=float)
    moments = np.asarray(magnetic["local_magnetization_last_muB"], dtype=float)
    totals = magnetic["total_magnetization_history_muB"]
    require(forces.shape == (49, 3) and np.isfinite(forces).all() and np.isfinite(parsed["final_toten_eV"]), "incomplete/nonfinite raw force or energy label")
    require(moments.shape == (49,) and np.isfinite(moments).all() and totals and np.isfinite(totals[-1]), "missing/nonfinite total or atomic magnetic moments")
    output = read(paths["OUTCAR"], index=-1, format="vasp-out")
    require(output.get_chemical_symbols() == structure.labels and np.allclose(output.cell, structure.cell, atol=1e-5, rtol=0), "output order/cell mismatch")
    _, movement = find_mic(output.positions - structure.frac @ structure.cell, structure.cell, pbc=[True, True, False])
    require(np.isfinite(movement).all() and float(np.max(movement)) <= 1e-5, "evaluated OUTCAR coordinates differ from POSCAR")
    require(np.array_equal(output.get_forces(apply_constraint=False), forces), "canonical and ASE raw force parsers disagree")
    live = verify_slurm_force_label_live(load_json_object(args.scheduler_evidence), job_id=execution["job_id"],
                                       remote_dir=receipt["remote_dir"], workdir_name=directory.name, config_path=args.backend_config)
    require(all(sha256_file(path) == sources[name]["sha256"] for name, path in paths.items()), "source changed during scientific/live review")
    evidence = {**load_json_object(args.scheduler_evidence), **sources["scheduler"], "live_recheck": live,
                "source_files": sources, "magnetic_evidence": {"total_magnetic_moment_muB": totals[-1],
                "atom_resolved_magnetic_moments_muB": moments.tolist(), "magnetic_ground_state_verified": False},
                "geometry_review": {"maximum_coordinate_difference_A": float(np.max(movement)), "tolerance_A": 1e-5}}
    standard = {"schema_version": 1, "document_kind": "vasp_ts_force_label", "reaction_id": contract["reaction_id"],
                "round_index": request["evaluation_index"] - 1, "contract_sha256": contract["contract_sha256"],
                "compatibility_sha256": contract["compatibility_sha256"],
                "result_class": "vasp_completed_electronic_converged_force_label_only", "reportable_final_energy": False,
                "eligible_for_force_only_training": True, "scheduler_evidence": evidence,
                "label_request": {**sources["state"], "json_pointer": f"/evaluations/{request['evaluation_index'] - 1}/request",
                                  "request_sha256": row["request_sha256"]},
                "structure": {**sources["POSCAR"], "symbols": structure.labels}, "fixed_atom_indices_zero_based": fixed,
                "outcar": sources["OUTCAR"], "oszicar": sources["OSZICAR"], "normal_completion": True, **scf,
                "dft_toten_eV_force_label_only": parsed["final_toten_eV"], "forces_eV_per_A": forces.tolist()}
    validate_document(standard, expected_kind="vasp_ts_force_label", schema_path=args.backend_config.parent / "aqcat25_ts_active_learning.schema.json")
    paper = {**standard, "schema_scope": "paper_sequential_extension", "geometry_sha256": geometry,
             "paper_sequential_request_sha256": row["request_sha256"], "scientifically_validated_ts": False, "reportable_barrier": False}
    return standard, paper


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("owner-source-root", "directory", "state", "contract", "scheduler-evidence", "backend-config", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--state-sha256", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.owner_source_root.resolve(strict=True)))
    from scripts.artifact_io import sha256_file, write_json_exclusive

    require(not args.output.exists(), "output directory already exists")
    standard, paper = review(args)
    args.output.mkdir(parents=True, exist_ok=False)
    standard_path = args.output / "vasp_force_label.json"
    write_json_exclusive(standard_path, standard)
    paper["standard_label"] = {"path": str(standard_path.resolve()), "sha256": sha256_file(standard_path)}
    write_json_exclusive(args.output / "paper_force_label.json", paper)
    print("REVIEWABLE_FORCE_LABEL_ONLY; state unchanged; TS not accepted")


if __name__ == "__main__":
    main()
