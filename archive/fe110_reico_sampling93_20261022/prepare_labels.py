"""Prepare reviewed selected statics locally; never upload or submit jobs."""
from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

from archive.fe110_reico_sampling93_20261022.prepare import DEST, ROOT
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.neb_agent.submission import preflight
from scripts.vasp_inputs import build_fe110_active_learning_force_label


def prepare_one(row, destination, selection_sha, custodian, custodian_path):
    if not re.fullmatch(r"family_\d{4}_step\d{3}", row["sample_id"]):
        raise ValueError("invalid selected sample identity")
    directory = destination / row["sample_id"]
    if sha256_file(Path(row["structure_path"])) != row["structure_sha256"]:
        raise ValueError("selected source structure changed")
    if directory.exists():
        label = load_json_object(directory / "label_request.json")
        profile = load_json_object(directory / "input_profile.json")
        check = load_json_object(directory / "submission_preflight.json")
        validation = load_json_object(directory / "incar_validation.json")
        if (label["selection_sha256"] != selection_sha
                or sha256_file(directory / "POSCAR") != row["structure_sha256"]
                or sha256_file(Path(profile["profile_path"])) != profile["profile_sha256"]
                or any(sha256_file(directory / n) != s for n, s in check["files"].items())):
            raise ValueError("existing input preparation changed;inspect before recovery")
    else:
        directory.mkdir(exist_ok=False)
        shutil.copy2(row["structure_path"], directory / "POSCAR")
        profile = build_fe110_active_learning_force_label(directory)
        write_json_exclusive(directory / "input_profile.json", profile)
        write_json_exclusive(directory / "label_request.json", {
            "document_kind": "reico_selected_fixed_geometry_DFT_label_request", **row,
            "selection_sha256": selection_sha, "ionic_convergence_required": False,
            "requested_labels": ["compatible_TOTEN", "all_atom_forces", "total_and_local_magnetic_moments"],
            "scientific_acceptance": False})
        Incar, _ = custodian.require_pymatgen()
        symbols, counts = custodian.load_structure(directory / "POSCAR")
        validation = custodian.validate_incar(dict(Incar.from_file(directory / "INCAR")),
                                              symbols, counts, "adsorption_static", "metal_fe")
        write_json_exclusive(directory / "incar_validation.json", validation)
        write_json_exclusive(directory / "incar_validation_binding.json", {
            "source": str(custodian_path), "source_sha256": sha256_file(custodian_path),
            "INCAR_sha256": sha256_file(directory / "INCAR"), "POSCAR_sha256": sha256_file(directory / "POSCAR"),
            "api": "validate_incar", "calculation_type": "adsorption_static", "surface_family": "metal_fe"})
        check = preflight(directory, "diagnostic_static")
    if not check["passed"] or validation["status"] != "PASS" or validation["warnings"]:
        raise ValueError("prepared static has unresolved input validation")
    return {**row, "directory": str(directory.resolve()), "input_hashes": check["files"],
            "bundle_sha256": check["bundle_sha256"], "cores": profile["cores"], "status": "PREPARED_NOT_SUBMITTED"}


def prepare():
    selection_path = DEST / "selection/selected_frames.json"
    selection = load_json_object(selection_path)
    if (selection["existing_DFT_labels"] != 12 or selection["selected_count"] > 300
            or selection["model_accuracy_or_convergence_filter"]):
        raise ValueError("selection scope changed")
    rows = [r for r in selection["selected"] if not r["already_DFT_labeled"]]
    if len(rows) > 288:
        raise ValueError("remaining DFT cap exceeded")
    destination = DEST / "dft_inputs_v1"
    destination.mkdir(exist_ok=True)
    custodian_path = ROOT / "skills/fe-vasp-incar-custodian/scripts/incar_custodian.py"
    spec = importlib.util.spec_from_file_location("reico_owned_incar_custodian", custodian_path)
    custodian = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(custodian)
    prepared = []
    for row in rows:
        prepared.append(prepare_one(row, destination, sha256_file(selection_path), custodian, custodian_path))
        if len(prepared) % 25 == 0:
            print("prepared " + str(len(prepared)) + "/" + str(len(rows)), flush=True)
    report = {"document_kind": "reico_selected_DFT_inputs_prepared", "samples": prepared,
              "selection_sha256": sha256_file(selection_path), "new_DFT_jobs_submitted": 0,
              "existing_DFT_labels": 12, "pilot_label_cap": 300,
              "configurations_if_all_new_pass": 12 + len(prepared),
              "explicit_VASP_submission_authority_and_gates_required": True,
              "automatic_retry": False, "training_performed": False}
    write_json_exclusive(destination / "batch_request.json", report)
    print("PREPARED_NOT_SUBMITTED " + str(len(prepared)), flush=True)


if __name__ == "__main__":
    prepare()
