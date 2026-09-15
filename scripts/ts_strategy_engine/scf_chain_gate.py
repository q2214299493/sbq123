"""Bounded SCF stage policy, owned/exported by execution_gate.

This is a delegated *within-allocation* gate, not a submission authority.
No stage, including the last, grants TS/energy-reporting/Dimer authority.
"""
from __future__ import annotations

import math
from typing import Any

from scripts.artifact_io import require_sha256, sha256_json
from scripts.scientific_validation import finite_number

STAGES = ("A_fixed_density", "B_self_consistent", "C_restart")
ACTION = "SUBMIT_DIAGNOSTIC_VASP"
LIMITS = ("energy_eV", "force_vector_eV_A", "local_moment_muB", "total_moment_muB")


def validate_policy(policy: dict) -> None:
    if set(policy) != {"geometry_A", "baseline", "restart"}:
        raise ValueError("SCF policy must explicitly specify geometry/baseline/restart limits")
    finite_number(policy["geometry_A"], "geometry_A", positive=True)
    for group in ("baseline", "restart"):
        if set(policy[group]) != set(LIMITS):
            raise ValueError("incomplete SCF comparison policy")
        for name, limits in policy[group].items():
            if set(limits) != {"warning", "stop"}:
                raise ValueError("each comparison needs warning and stop limits")
            warning = finite_number(limits["warning"], name, positive=True)
            stop = finite_number(limits["stop"], name, positive=True)
            if stop < warning:
                raise ValueError("stop limit below warning limit")


def scope_matches(evidence: dict) -> bool:
    """A single-static authorization must never authorize three calculations."""
    pre = evidence.get("preflight", {})
    scope = evidence.get("authorization", {}).get("scf_chain_scope", {})
    return bool(
        pre.get("kind") == "scf_repair_chain"
        and pre.get("scf_chain", {}).get("passed") is True
        and scope == {
            "manifest_sha256": pre.get("files", {}).get("scf_chain.json"),
            "stages": list(STAGES), "max_allocations": 1, "retry": False,
        }
        and evidence.get("authorization", {}).get("calculation_kind") == "scf_repair_chain"
    )


def make_runtime_permit(decision: dict, decision_sha256: str) -> dict:
    """Called ONLY after execution_gate.require_action in the submit executor."""
    if ACTION not in decision.get("ALLOWED_ACTIONS", []) or not scope_matches(decision["EVIDENCE"]):
        raise PermissionError("missing reviewed three-stage execution scope")
    evidence = decision["EVIDENCE"]
    pre = evidence["preflight"]
    return {
        "schema_version": 1, "action": ACTION, "stages": list(STAGES),
        "manifest_sha256": pre["files"]["scf_chain.json"],
        "runtime_sha256": pre["files"]["scf_chain_runtime.pyz"],
        "gate_sha256": require_sha256(decision_sha256, label="gate"),
        "bundle_sha256": pre["bundle_sha256"],
        "target": evidence["authorization"]["target"],
    }


def require_runtime_permit(permit: dict, manifest_sha256: str) -> None:
    if (permit.get("schema_version") != 1 or permit.get("action") != ACTION
            or permit.get("stages") != list(STAGES)
            or permit.get("manifest_sha256") != manifest_sha256
            or permit.get("target", {}).get("server_alias") != "sunboquan-codex"):
        raise PermissionError("missing/stale SCF runtime permit")
    for key in ("manifest_sha256", "runtime_sha256", "gate_sha256", "bundle_sha256"):
        require_sha256(permit[key], label=key)


def compare_states(current: dict, reference: dict) -> dict[str, float]:
    """Compare complete atom-resolved vectors, not merely maximum forces."""
    cf, rf = current["forces"], reference["forces"]
    cm, rm = current["moments"], reference["moments"]
    if not cf or len(cf) != len(rf) or len(cm) != len(cf) or len(rm) != len(cf):
        raise ValueError("incomplete force/moment comparison")
    if any(len(v) != 3 for v in cf + rf):
        raise ValueError("forces must be three-component vectors")
    for value in [current["energy"], reference["energy"], current["total_moment"],
                  reference["total_moment"], *cm, *rm, *(x for v in cf + rf for x in v)]:
        finite_number(value, "SCF state")
    return {
        "energy_eV": abs(current["energy"] - reference["energy"]),
        "force_vector_eV_A": max(math.dist(a, b) for a, b in zip(cf, rf)),
        "local_moment_muB": max(abs(a - b) for a, b in zip(cm, rm)),
        "total_moment_muB": abs(current["total_moment"] - reference["total_moment"]),
    }


def decide_stage(stage: str, evidence: dict[str, Any], policy: dict, *,
                 permit: dict, manifest_sha256: str, prior: list[dict]) -> dict:
    require_runtime_permit(permit, manifest_sha256)
    validate_policy(policy)
    index = STAGES.index(stage)
    if len(prior) != index or any(
        p.get("stage") != STAGES[i] or p.get("status") not in {"PASS", "PASS_WITH_WARNING"}
        or p.get("manifest_sha256") != manifest_sha256 for i, p in enumerate(prior)
    ):
        raise PermissionError("preceding SCF stages have not passed")
    errors = list(evidence.get("errors", []))
    warnings = []
    # Numeric residuals remain mandatory even if VASP prints an EDIFF sentence.
    if evidence.get("exit_code") != 0 or evidence.get("normal_end") is not True:
        errors.append("PROCESS_OR_NORMAL_END_FAILED")
    if evidence.get("electronic_pass") is not True:
        errors.append("ELECTRONIC_CONVERGENCE_FAILED")
    if evidence.get("runtime_matches") is not True:
        errors.append("ACTUAL_RUNTIME_PARAMETERS_MISMATCH")
    if index:
        if evidence.get("restart_files_valid") is not True:
            errors.append("RESTART_FILES_INVALID")
        groups = ("baseline",) if index == 1 else ("baseline", "restart")
        for group in groups:
            values = evidence.get("comparisons", {}).get(group, {})
            if set(values) != set(LIMITS):
                errors.append(group + ":INCOMPLETE_COMPARISON")
                continue
            for key, value in values.items():
                value = finite_number(value, key, nonnegative=True)
                limits = policy[group][key]
                if value > limits["stop"]:
                    errors.append(group + ":" + key)
                elif value > limits["warning"]:
                    warnings.append(group + ":" + key)
    status = "STOP" if errors else "PASS_WITH_WARNING" if warnings else "PASS"
    return {
        "stage": stage, "status": status, "errors": errors, "warnings": warnings,
        "manifest_sha256": manifest_sha256, "evidence_sha256": sha256_json(evidence),
        "next_stage": STAGES[index + 1] if not errors and index < 2 else None,
        "numerical_repair_verified": not errors and index == 2,
        "scientific_acceptance": False, "ALLOWED_ACTIONS": [],
    }
