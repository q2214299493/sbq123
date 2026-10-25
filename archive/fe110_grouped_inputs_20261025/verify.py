"""Recheck prepared inputs and their source bindings without remote actions."""
from __future__ import annotations

import argparse
from pathlib import Path

from scripts.artifact_io import (
    load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid,
    write_json_exclusive,
)
from scripts.neb_agent.submission import preflight
from scripts.vasp_result_gate import read_incar_values


def verify(output):
    plan = load_json_object(output / "plan.json")
    if not source_file_manifest_valid(plan) or not source_file_manifest_valid(
            load_json_object(output / "input_binding.json")):
        raise ValueError("preparation source binding changed")
    if plan["case_counts"] != {"single_points": 12, "optimizations": 2}:
        raise ValueError("exact12+2 scope changed")
    inventory = [Path(__file__), output / "plan.json", output / "input_binding.json",
                 output / "cost_reference.json"]
    for case in plan["cases"]:
        directory = Path(case["directory"])
        if case["submitted"] or case["uploaded"] or case["execution_authorized"]:
            raise ValueError("local preparation gained execution status")
        check = preflight(directory, case["kind"], write_report=False)
        if not check["passed"] or check["bundle_sha256"] != case["bundle_sha256"]:
            raise ValueError("canonical input preflight changed")
        if sha256_file(directory / "POSCAR") != case["structure_sha256"]:
            raise ValueError("reviewed geometry not preserved")
        incar = read_incar_values(directory / "INCAR")
        expected_nsw = 0 if case["role"] == "single_points" else 80
        if (int(incar["NSW"]) != expected_nsw or int(incar["LORBIT"]) != 11
                or float(incar["SIGMA"]) != .2 or int(incar["ISPIN"]) != 2):
            raise ValueError("stage or magnetic-output branch changed")
        validation = load_json_object(directory / "incar_custodian_validation.json")
        if validation["status"] != "VALIDATION_ONLY" or validation["blockers"]:
            raise ValueError("INCAR scientific review blocked")
        if (directory / "POTCAR").exists():
            raise ValueError("POTCAR contents must remain remote")
        inventory.extend(directory / name for name in [*case["input_hashes"],
            "prepared_case.json", "incar_custodian_validation.json", "POTCAR.metadata.json",
            "input_profile.json", "submission_preflight.json"])
    result = {"status": "PASS", "canonical_preflights_rechecked": 14,
        "custodian_validations_checked": 14, "POSCAR_hashes_preserved": 14,
        "all_local_moments_requested": True, "POTCAR_contents_local": False,
        "execution_authorized": False, "source_files": source_file_manifest(inventory)}
    write_json_exclusive(output / "verification.json", result)
    print({k: v for k, v in result.items() if k != "source_files"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify(args.output.resolve())
