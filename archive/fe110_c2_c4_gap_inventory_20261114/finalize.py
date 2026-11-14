"""Export the gap matrix and verify frozen-source guards; no scientific acceptance."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from archive.fe110_independent_nearstable_20261113.audit import frozen_hashes
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from .collect import BASE, OUT, ROOT
from .coverage import force_maximum
from .network import export_csv


def run():
    request = load_json_object(OUT / "request_context.json")
    coverage = load_json_object(OUT / "reico536_coverage_v3.json")
    candidates = load_json_object(OUT / "candidate_inventory_v2.json")
    local = load_json_object(OUT / "local_geometry_headers.json")
    remote = load_json_object(OUT / "remote_geometry_headers_v2.json")
    network = load_json_object(OUT / "reaction_network_sources.json")
    rows = []
    for composition, values in coverage["per_composition"].items():
        force = coverage["force_table"][composition]
        rows.append({"gap_id": "REICO_" + composition, "carbon_scope": "C3" if composition.startswith("C3") else "C2",
                     "priority": "P1", "source": "reico536_coverage_v3.json", "available_evidence": "existing geometric pool and frozen536 force reference",
                     "missing": str(values["missing_geometric_joint_types"]) + " joint geometry types;" + str(values["robust_missing_groups_all_three_scales"]) + " cutoff-robust groups",
                     "nearstable_training_frames": force["low_force_le_0p05"], "nearstable_source_groups": force["low_force_source_groups"],
                     "next_action": "deduplicate real candidates;reuse matched compatible labels;do not infer force error from novelty",
                     "DFT_budget": "unallocated;not one SP per missing type"})
    rows += [
        {"gap_id": "C2_C_C_PATH", "carbon_scope": "C2", "priority": "P0_REUSE_REVIEW", "source": "job9994246_image01-06_opt207",
         "available_evidence": "6 same-coordinate raw E/F labels;active branch observed", "missing": "local moment tables;formal TS validation;broader path phases",
         "next_action": "review existing magnetic scope;extract existing trajectory before new SP", "DFT_budget": "0 to recover existing labels;no automatic six recalculations"},
        {"gap_id": "C2_H_TRANSFER", "carbon_scope": "C2", "priority": "P0_SOURCE_EXTRACTION", "source": "accepted_C2HO_OH_barrier+registered_INT06_MID_ISA_paths",
         "available_evidence": "accepted scalar anchors and registered path pointers", "missing": "reviewed atomic raw-force manifest across reaction stages",
         "next_action": "extract existing raw atomic forces with atom-map/coordinate/magnetism checks", "DFT_budget": "Needs confirmation after source extraction"},
        {"gap_id": "C2_INDEPENDENT_OPTIMIZATION", "carbon_scope": "C2", "priority": "P0_VALIDATION_REVIEW", "source": "job9927794_opt066;job9927514_opt048",
         "available_evidence": "26 low-force frames in two external [C]-CH3 trajectories", "missing": "vinyl-isomer independent coverage;11C terminal-evidence gate",
         "next_action": "reserve these sources for isomer-force stress review;retain existing vinyl test partition", "DFT_budget": "0 for existing compatible labels"},
        {"gap_id": "C3_INDEPENDENT_INTACT_NEARSTABLE", "carbon_scope": "C3", "priority": "P1_SOURCE_GAP", "source": "prior618reviewed_frames+CARE_FLJNAOYG_proposals",
         "available_evidence": "24 training nearstable frames in family0099;existing independent starting seeds", "missing": "0 verified independent intact C3 nearstable labels;third distinct target motif",
         "next_action": "source and binding-mode review outside training lineage;do not use CO+C2H2 fragments", "DFT_budget": "Needs confirmation;arbitrary single points cannot guarantee nearstable endpoint"},
        {"gap_id": "C3_REACTION_CHEMISTRY", "carbon_scope": "C3", "priority": "P1_SOURCE_GAP", "source": "C1C6_R057125::R;C1C6_R022170::F;C1C6_R000427::F;C1C6_R036189::R",
         "available_evidence": "existing symbolic reaction records", "missing": "atom-mapped C2+C1 growth/C3 cleavage/H-transfer path coordinates and labels",
         "next_action": "bind real geometries and isomers before considering labels", "DFT_budget": "Needs confirmation;no submitted or executable candidates"},
        {"gap_id": "C4_PATH_AND_OPTIMIZATION", "carbon_scope": "C4", "priority": "P1_MAINLINE", "source": "C1C6_R034176::R;REV_C1C6_R002321::F;C1C6_R038452::F;C1C6_R028346::R",
         "available_evidence": "four named growth/H-transfer/deoxygenation reaction proposals", "missing": "no C4 coordinates in inspected local and registered-DFT geometry scope;no current536 C4 labels",
         "next_action": "whitelist-first source/binding-mode/atom-map/Fe45 periodic-cell review before geometric sampling", "DFT_budget": "Needs confirmation;real structure IDs and coordinate hashes absent"},
        {"gap_id": "C5_REPRESENTATIVE", "carbon_scope": "C5", "priority": "P2_LIMITED", "source": "REV_C1C6_R044821::F;C1C6_R034542::F",
         "available_evidence": "two existing symbolic proposals", "missing": "coordinates,connectivity and compatible labels", "next_action": "one or few representative events after mainline sources are bound", "DFT_budget": "Needs confirmation;no preset quota"},
        {"gap_id": "C6_REPRESENTATIVE", "carbon_scope": "C6", "priority": "P2_LIMITED", "source": "REV_C1C6_R286696::F;REV_C1C6_R252658::F",
         "available_evidence": "two existing symbolic proposals", "missing": "coordinates,actual C6 skeleton and compatible labels", "next_action": "distinguish C3+C3 coadsorption from covalently connected C6", "DFT_budget": "Needs confirmation;no preset quota"},
        {"gap_id": "COVERAGE_IMPLEMENTATION_SCOPE", "carbon_scope": "C2-C6", "priority": "P0_BEFORE_EXTENSION", "source": "scripts/adsorption/reico_chemical_environments.py;configs/aqcat25_domain_gate.yaml",
         "available_evidence": "existing Fe45/small-adsorbate diagnostic and original-pretrain empirical domain gate", "missing": "canonical_graph accepts at most6 C/H/O atoms;TS uncalibrated;no new536 C4-C6 calibration",
         "next_action": "separately propose scalable graph/atom-role/cell-aware diagnostics;keep existing module and gates unchanged", "DFT_budget": "none for code/provenance review"},
    ]
    write_json_exclusive(OUT / "gap_matrix.json", {"records": rows, "status": "READ_ONLY_GAPS_NOT_EXECUTION_AUTHORITY",
        "source_files": source_file_manifest([OUT / n for n in ("reico536_coverage_v3.json", "candidate_inventory_v2.json", "reaction_network_sources.json", "local_geometry_headers.json", "remote_geometry_headers_v2.json")] + [Path(__file__)])})
    export_csv(OUT / "gap_matrix.csv", rows, ["gap_id", "carbon_scope", "priority", "source", "available_evidence", "missing", "nearstable_training_frames", "nearstable_source_groups", "next_action", "DFT_budget"])
    manifest = load_json_object(BASE / "combined_force_package_20261113_v1/training_manifest.json")
    numerical = {}
    for comp in coverage["force_table"]:
        values = [force_maximum(r) for r in manifest["splits"]["train"] if r["composition"] == comp]
        expected = coverage["force_table"][comp]
        if len(values) != expected["frames"] or sum(v <= .05 for v in values) != expected["low_force_le_0p05"]:
            raise ValueError("raw-force low-force count mismatch")
        numerical[comp] = {"frames": len(values), "low_force_le0p05": sum(v <= .05 for v in values), "fixed_atoms_excluded": True}
    artifact_names = ["registry_snapshot.json", "local_geometry_headers.json", "remote_headers_receipt_v2.json",
                      "reico536_coverage_v3.json", "reico_pool_label_bindings_v3.json", "reaction_network_sources.json",
                      "candidate_inventory_v2.json", "gap_matrix.json"]
    binding_checks = {name: source_file_manifest_valid(load_json_object(OUT / name)) for name in artifact_names}
    request_sources = request["source_files"]
    if isinstance(request_sources, list):
        request_checks = {r["path"]: sha256_file(Path(r["path"])) == r["sha256"] for r in request_sources}
    else:
        raise ValueError("unknown request source binding schema")
    model = BASE / "training536_execution_20261113_v4/returned/candidate.pt"
    checks = {"frozen512_536_12_file_hashes_unchanged": frozen_hashes() == request["frozen_hashes_before"],
              "current_task_unchanged": sha256_file(ROOT / "tasks/current_task.md") == request["current_task_sha256"],
              "backend_policy_unchanged": sha256_file(ROOT / "configs/execution_backends.yaml") == request["backend_policy_sha256"],
              "registry_unchanged": sha256_file(ROOT / "data/project_registry.sqlite3") == request["registry_sha256_before"],
              "candidate536_weight_hash_unchanged": sha256_file(model) == "2aaed376a1d5ad66999710f7d252aff79c45569f2a6a95510d4bff9bbc70acc0",
              "source_bindings_valid": all(binding_checks.values()) and all(request_checks.values()),
              "frozen_partitions_536_78_53_16": [len(manifest["splits"][s]) for s in ("train", "development", "heldout")] + [len(manifest["quarantined_observed_heldout"])] == [536, 78, 53, 16],
              "protected_path_labels_six": sum(r.get("protected_TS_validation", False) for r in candidates["records"]) == 6,
              "all14_network_reactions_without_invented_geometry": all(r["geometry_path"] is None for r in network["representative_proposals"]),
              "no_C4_C5_C6_in_inspected_nonempty_geometry_headers": not any(4 <= r.get("total_C", 0) <= 6 for r in local["records"] + remote["records"]),
              "no_unstable_local_geometry_read": all(r.get("stable_during_read", True) for r in local["records"]),
              "no_unstable_remote_geometry_read": all(r.get("stable_during_read", True) for r in remote["records"])}
    result = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
              "source_binding_checks": binding_checks, "request_source_checks": request_checks,
              "raw_force_count_recheck": numerical, "geometry_scope": {"local_headers": local["path_count"], "registered_DFT_directories": remote["registered_directory_scope"],
                 "remote_valid_headers": Counter(r["status"] for r in remote["records"])["VASP5_HEADER_ONLY"], "remote_empty_CONTCAR": 2,
                 "not_exhaustive_unregistered_server_or_other_GPU_search": True},
              "v1_v2_coverage_artifacts_superseded_not_validated_as_final_evidence": True,
              "new_training_inference_optimization_or_DFT_jobs": False, "scientific_acceptance_granted": False,
              "source_files": source_file_manifest([OUT / n for n in artifact_names] + [OUT / "request_context.json", Path(__file__)])}
    write_json_exclusive(OUT / "final_verification.json", result)
    print({"status": result["status"], "checks": checks, "gap_rows": len(rows)}, flush=True)
    if result["status"] != "PASS":
        raise ValueError("read-only verification did not pass")


if __name__ == "__main__":
    run()
