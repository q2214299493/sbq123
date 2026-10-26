"""Replay raw-label admission and byte-range bindings; no computation launch."""
from __future__ import annotations

from collections import Counter
import io
from pathlib import Path

import numpy as np
from ase.geometry import find_mic
from ase.io import read

from archive.fe110_reico_followup_20261024.collect import save_once
from scripts.adsorption.force_finetune import validate_label_row
from scripts.adsorption.reico_probe_review import validate_static
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid
from scripts.neb_agent.utils_vasp import parse_oszicar
from scripts.vasp_result_gate import final_scf_status
from .collect import INPUT, OUTPUT, scope
from .review import AUDIT, FROZEN, check_collection, magnetic_status, raw_frames


def run():
    for name in ("collection_binding.json", "review_binding.json", "summary.json"):
        if not source_file_manifest_valid(load_json_object(OUTPUT / name)):
            raise ValueError("stale binding " + name)
    assert sha256_file(FROZEN) == "6a9121a26bc2a8eb51641cfe0b694fb3c4c4c719e791eaa2d4fc6fe0b10e9ebb"
    assert sha256_file(AUDIT) == "dd23d9d3d27e5f572475903dfaf94108d14d4a4f697cf145ddf887ebc7177ba0"
    rows = load_json_object(OUTPUT / "all_frame_qc_local_only.json")["samples"]
    by_job = {}
    for row in rows:
        by_job.setdefault(row["source_job_id"], []).append(row)
    static_diagnostics, trajectories = [], []
    raw_verified = 0
    for receipt in scope():
        directory, _, _ = check_collection(receipt)
        initial = read(directory / "POSCAR", format="vasp")
        cases = by_job[receipt["job_id"]]
        scf = final_scf_status(directory / "OSZICAR", directory / "INCAR", directory / "OUTCAR")
        if receipt["role"] == "single_points":
            row = cases[0]
            try:
                label = validate_static(directory, initial.get_chemical_symbols())
                strict_pass = True
                assert label["forces_eV_per_A"] == row["forces_eV_per_A"]
                assert label["local_magnetization_muB"] == row["local_magnetization_muB"]
                raw_verified += 1
            except ValueError:
                strict_pass = False
            assert strict_pass == (row["data_qc_status"] == "PASS")
            static_diagnostics.append({"sample_id": row["sample_id"], "source_job_id": receipt["job_id"],
                "canonical_SCF_summary": scf, "strict_static_admission_passed": strict_pass,
                "reason": row.get("reason"),
                "boundary_policy": "iteration must be strictly below NELM;EDIFF marker alone cannot override the boundary"})
            continue
        parsed = raw_frames(directory / "OUTCAR", len(initial))
        data = (directory / "OUTCAR").read_bytes()
        osz = parse_oszicar(directory / "OSZICAR")
        assert len(cases) == len(parsed) == 80
        for row, frame in zip(cases, parsed, strict=True):
            assert row["ionic_step"] == frame["ionic_step"]
            assert magnetic_status(frame["local_moment_tables"], len(initial))["local_magnetization_muB"] == row["local_magnetization_muB"]
            assert len(frame["local_moment_tables"]) >= 1
            start, end = row["source_force_byte_range"]
            table = data[start:end]
            assert table == frame["raw_force_table"]
            direct = np.loadtxt(io.BytesIO(table), skiprows=2)
            assert direct.shape == (len(initial), 6)
            assert np.array_equal(direct[:, 3:], row["forces_eV_per_A"])
            assert row["energy_eV_force_label_only"] == frame["toten_eV"]
            assert row["total_magnetization_muB"] == osz["magnetization_history_muB"][row["ionic_step"]-1]
            atoms = read(OUTPUT / row["structure_path"], format="vasp")
            _, delta = find_mic(direct[:, :3]-atoms.positions, atoms.cell, pbc=[True, True, False])
            bounds = np.linalg.norm(np.array([[.5*10**(-len(t.split(".")[-1])) for t in tokens]
                                             for tokens in frame["position_tokens"]]), axis=1)
            assert np.all(delta <= bounds+1e-8)
            raw_verified += 1
        minimum = min(cases, key=lambda r: r["movable_fmax_eV_A"])
        trajectories.append({"sample_id": receipt["sample_id"], "source_job_id": receipt["job_id"], "frames": 80,
            "local_moment_tables": sum(r["local_moment_table_count"] for r in cases),
            "SCF_iteration_range": [min(r["SCF"]["last_electronic_iteration"] for r in cases), max(r["SCF"]["last_electronic_iteration"] for r in cases)],
            "Fe_local_moment_range_muB": [min(r["Fe_moment_range_muB"][0] for r in cases), max(r["Fe_moment_range_muB"][1] for r in cases)],
            "initial_and_final_graph_same": cases[0]["graph_signature"] == cases[-1]["graph_signature"],
            "all_frame_graphs_same": len({r["graph_signature"] for r in cases}) == 1,
            "components_seen": sorted({r["adsorbate_component_count"] for r in cases}),
            "minimum_movable_force_eV_A": minimum["movable_fmax_eV_A"], "minimum_force_ionic_step": minimum["ionic_step"],
            "final_movable_force_eV_A": cases[-1]["movable_fmax_eV_A"],
            "final_SCF": scf, "parent_ionic_converged": cases[-1]["parent_ionic_converged"]})
    candidates = load_json_object(OUTPUT / "eligible_training_candidates.json")["samples"]
    recommended = load_json_object(OUTPUT / "recommended_small_supplement.json")["samples"]
    assert len({r["sample_id"] for r in candidates}) == len(candidates)
    assert {r["sample_id"] for r in recommended} <= {r["sample_id"] for r in candidates}
    for row in candidates:
        validate_label_row(OUTPUT, row)
        assert row["partition"] == "train" and not row["magnetic_review_flags"]
        assert not row["training_authorized"] and not row["accepted_endpoint"]
    snapshot = load_json_object(OUTPUT / "scheduler_snapshot.json")
    assert len(snapshot["requested"]) == 14
    result = {"status": "PASS", "frames_raw_replayed": raw_verified,
        "excluded_static_frames": len(rows)-raw_verified, "all_QC_counts": dict(Counter(r["data_qc_status"] for r in rows)),
        "validated_candidate_rows": len(candidates), "recommended_rows": len(recommended),
        "static_diagnostics": static_diagnostics, "trajectories": trajectories,
        "frozen366manifest_unchanged": True, "frozen485audit_unchanged": True,
        "legacy10B_magnetic_tier_unchanged": True, "new_DFT_GPU_or_training": False,
        "source_files": source_file_manifest([Path(__file__), OUTPUT / "summary.json", FROZEN, AUDIT,
            OUTPUT / "eligible_training_candidates.json", OUTPUT / "recommended_small_supplement.json",
            INPUT / "verification.json"])}
    save_once(OUTPUT / "independent_verification.json", result)
    print({k: result[k] for k in ("status", "frames_raw_replayed", "excluded_static_frames", "validated_candidate_rows", "recommended_rows")})


if __name__ == "__main__":
    run()
