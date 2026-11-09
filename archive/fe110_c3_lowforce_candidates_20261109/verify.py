"""Independently replay candidate bindings from saved raw sources; no training."""
from __future__ import annotations

import argparse
import io
from pathlib import Path

import numpy as np
from ase.geometry import find_mic
from ase.io import read

from scripts.adsorption.force_finetune import validate_label_row
from scripts.artifact_io import sha256_file, source_file_manifest_valid
from .prepare import OUTPUT, check_boundaries, frozen_hashes, load, save_json


def force_slice(source, row):
    start, end = row["source_force_byte_range"]
    if not (0 <= start < end <= len(source)):
        raise ValueError("invalid source byte range")
    table = source[start:end]
    values = np.loadtxt(io.BytesIO(table), skiprows=2)
    if values.shape != (len(row["symbols"]), 6) or not np.isfinite(values).all():
        raise ValueError("invalid raw six-column force table")
    if not np.array_equal(values[:, 3:], np.asarray(row["forces_eV_per_A"])):
        raise ValueError("candidate force differs from original source bytes")
    return table, values


def verify_candidate(output, row, source_bytes, independent, trajectory, initial):
    from archive.fe110_10b_lowforce_20261023.legacy_helpers import restore_input_lattice

    validate_label_row(output, row)
    step = row["ionic_step"]
    table, values = force_slice(source_bytes, row)
    if table != (output / row["raw_force_table_path"]).read_bytes():
        raise ValueError("saved raw force table changed")
    if sha256_file(output / row["raw_force_table_path"]) != row["source_force_table_sha256"]:
        raise ValueError("raw force-table hash differs")
    cross = independent[step - 1]
    if cross.get_chemical_symbols() != row["symbols"] or not np.array_equal(cross.get_forces(apply_constraint=False), values[:, 3:]):
        raise ValueError("independent ASE atom/force mapping differs")
    if not np.array_equal(cross.positions, values[:, :3]):
        raise ValueError("independent ASE raw position mapping differs")
    if abs(cross.get_potential_energy(force_consistent=True) - row["energy_eV_force_label_only"]) > 1e-8:
        raise ValueError("independent energy metadata differs")
    exact = trajectory[step - 1]
    restore_input_lattice(exact, initial, output / "source/XDATCAR")
    materialized = read(output / row["structure_path"], format="vasp")
    _, distances = find_mic(materialized.positions - exact.positions, exact.cell, pbc=[True, True, False])
    if max(distances) > 1e-12:
        raise ValueError("materialized high-precision trajectory coordinates differ")
    if row["partition"] != "train" or row["calculation_group"] != "reico_family_0099":
        raise ValueError("source-family isolation identity changed")
    if (row["magnetic_review_level"] != "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE"
            or row["magnetic_review_flags"] or row["movable_fmax_eV_A"] > .05):
        raise ValueError("low-force/magnetic eligibility changed")
    if any(row[k] is not False for k in ("training_authorized", "accepted_endpoint", "reportable_final_energy")):
        raise ValueError("candidate was promoted")
    return float(max(distances))


def run(output=OUTPUT):
    from archive.fe110_grouped_qc_20261026.review import magnetic_status, raw_frames
    from archive.fe110_10b_lowforce_20261023.review import scf_for_frame
    from scripts.neb_agent.utils_vasp import parse_oszicar
    from scripts.vasp_result_gate import read_incar_values

    output = Path(output).resolve()
    request, manifest = load(output / "request.json"), load(output / "candidate_manifest.json")
    check_boundaries(manifest)
    if not source_file_manifest_valid(load(output / "implementation_binding.json")):
        raise ValueError("implementation binding changed")
    source = output / "source"
    collection = load(output / "source_collection.json")
    for name, info in collection["files"].items():
        if sha256_file(source / name) != info["sha256"]:
            raise ValueError("raw source file changed: " + name)
    if frozen_hashes() != request["frozen512_before"]:
        raise ValueError("frozen512 package changed")
    rows = manifest["samples"]
    if len(rows) != 24 or [r["ionic_step"] for r in rows] != request["selected_steps"]:
        raise ValueError("candidate membership/order changed")
    if len({r["sample_id"] for r in rows}) != 24:
        raise ValueError("duplicate candidate IDs")
    original = (source / "OUTCAR").read_bytes()
    independent = read(source / "OUTCAR", format="vasp-out", index=":")
    trajectory = read(source / "XDATCAR", format="vasp-xdatcar", index=":")
    initial = read(source / "POSCAR", format="vasp")
    raw = raw_frames(source / "OUTCAR", 51)
    cycles = {r["ionic_step"]: r for r in parse_oszicar(source / "OSZICAR")["electronic_cycles"]}
    values = read_incar_values(source / "INCAR")
    maximum = 0.
    for row in rows:
        frame = raw[row["ionic_step"] - 1]
        scf_for_frame(frame, cycles[row["ionic_step"]], values)
        magnetic = magnetic_status(frame["local_moment_tables"], 51)
        if magnetic["local_magnetization_muB"] != row["local_magnetization_muB"] or magnetic["magnetic_review_flags"]:
            raise ValueError("independent local-moment replay differs")
        maximum = max(maximum, verify_candidate(output, row, original, independent, trajectory, initial))
    # Do not create a loader, executable request, registry record or accepted result.
    if any((output / name).exists() for name in ("train.db", "heldout.db", "training_request.json")):
        raise ValueError("unexpected executable training artifact")
    result = {"status": "PASS_INDEPENDENT_CANDIDATE_REPLAY_NOT_ADMITTED", "raw_source_files_verified": len(collection["files"]),
              "raw_force_tables_verified": len(rows), "high_precision_coordinate_frames_verified": len(rows),
              "maximum_materialized_coordinate_error_A": maximum, "source_frames": len(raw),
              "frozen512_unchanged": True, "terminal_scheduler_status": collection["terminal_scheduler_status"],
              "candidate_manifest_sha256": sha256_file(output / "candidate_manifest.json"),
              "separate_candidate_admission_review_required": True, "training_authorized": False,
              "reportable_final_energy": False, "accepted_endpoint": False, "registry_written": False}
    save_json(output / "independent_verification.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    print(__import__("json").dumps(run(parser.parse_args().output)))


if __name__ == "__main__":
    main()
