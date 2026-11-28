"""Qualify mass-normalized turnover independently of the native MKM analysis."""
from math import isfinite
from pathlib import Path

from sbq123.common.evidence import trust
from sbq123.common.kinetic_model.contracts import identity, number


MASS_OPTIONS = {"reference_mol_per_kg", "catalyst_m2_per_kg", "mass_conversion_approval"}
MASS_BASIS = "kg_total_catalyst"


def _approved_factor(locator, directory, context):
    from sbq123.common.workflow.multiphase_contracts import read_artifact

    if not isinstance(locator, dict) or not isinstance(locator.get("sha256"), str):
        raise ValueError("Missing independent mass conversion approval")
    pin = locator["sha256"]
    if not trust.approved("mass_conversion", pin):
        raise ValueError("Mass conversion approval is not independently pinned")
    path = directory / locator["path"]
    approval, _ = read_artifact(path, expected_sha256=pin)
    if (approval["format"] != "mkm-mass-conversion/1" or approval["decision"] != "approved"
            or not isinstance(approval["reviewer"], str) or not approval["reviewer"].strip()
            or identity(approval["context"]) != identity(context)):
        raise ValueError("Approval does not cover this result, catalyst, reference or validity scope")
    ref = approval["calibration"]
    if not isinstance(ref["sha256"], str) or len(ref["sha256"]) != 64:
        raise ValueError("Missing calibration source identity")
    calibration, _ = read_artifact(path.parent / ref["path"], expected_sha256=ref["sha256"])
    if calibration["mass_basis"] != MASS_BASIS or calibration["unit"] != "mol_reference/kg":
        raise ValueError("Calibration requires moles of the bound reference per kg of total catalyst")
    factor = number(calibration["value"], "mass calibration", positive=True)
    return factor, dict(approval_sha256=pin, calibration_sha256=ref["sha256"],
                        reviewer=approval["reviewer"], context=context)


def mass_options(options, profile, network, hashes, result_hash, point, reference):
    """Only forward independently supported factors to the numerical conversion."""
    clean = {k: v for k, v in options.items() if k not in MASS_OPTIONS}
    requested = options.get("reference_mol_per_kg")
    context = dict(dataset_sha256=hashes["dataset"], network_sha256=hashes["network"],
                   point_sha256=result_hash, configuration_sha256=hashes["configuration"],
                   catalyst_project_id=network["project_id"], catalyst_catalog_sha256=identity(network["catalog"]),
                   reference_sha256=identity(reference), validity_scope=point["scope"])
    status = dict(status="unavailable", unit="mol/(kg s)", mass_basis=MASS_BASIS)
    try:
        if reference is None:
            raise ValueError("Missing reviewed native reference")
        locator = options.get("mass_conversion_approval")
        if locator is None:
            raise ValueError("Missing independent mass conversion approval")
        factor, provenance = _approved_factor(locator, Path(profile).parent, context)
        if requested is not None and number(requested, "requested mass factor", positive=True) != factor:
            raise ValueError("Requested factor differs from the approved calibration")
    except (KeyError, OSError, ValueError, TypeError) as exc:
        status["reason"] = str(exc)
        if requested is not None:
            try:
                hypothetical = number(requested, "hypothetical mass factor", positive=True)
            except ValueError:
                status["reason"] += "; invalid hypothetical mass factor"
            else:
                status["hypothetical"] = dict(reference_mol_per_kg=hypothetical)
        return clean, status
    return clean, dict(status, status="available", reference_mol_per_kg=factor, **provenance)


def project_mass_turnover(report, mass):
    """Publish only finite rates based on the reviewed native observable."""
    tof = report["tof"]
    rows = [tof["overall"], *tof["products"].values()]
    if mass["status"] == "available":
        factor = mass["reference_mol_per_kg"]
        for row in rows:
            native = row["per_reference_s"]
            if native is not None:
                value = native * factor
                if isfinite(value) and (value != 0 or native == 0):
                    row["mol_per_kg_s"] = value
        report["normalization"]["reference_mol_per_kg"] = factor
        report["validation"]["missing_normalization"].remove("reference_mol_per_kg")
        if tof["overall"]["mol_per_kg_s"] is None:
            mass = dict(mass, status="unavailable", reason="Overall native turnover missing or outside numeric range")
    report["mass_normalization"] = mass


def compare_mass_turnover(left, right):
    """Compare saved overall rates after independent replay of both original input sets.

    Each side is (serialized analysis dict, analyze keyword arguments). Replays use
    the installed role and its independent approval pins. No report hash is a grant.
    """
    from sbq123.common.compat import historical_module

    analyze = historical_module("mkm", "scripts.baseline_mkm.analysis").analyze

    reports = []
    for saved, inputs in (left, right):
        replay = analyze(**inputs)
        qualification = replay["mass_normalization"]
        if qualification["status"] != "available":
            return dict(status="unavailable", difference_mol_per_kg_s=None, reason=qualification["reason"])
        if identity(saved) != identity(replay):
            return dict(status="unavailable", difference_mol_per_kg_s=None, reason="Report differs from replay")
        reports.append(replay)
    a, b = reports
    for key in ("network_version", "dataset_version", "scope", "temperature_K", "partial_pressures_bar"):
        if a[key] != b[key]:
            return dict(status="unavailable", difference_mol_per_kg_s=None, reason=f"Incompatible {key}")
    if (not a["tof"]["overall_stoichiometry"]
            or a["tof"]["overall_stoichiometry"] != b["tof"]["overall_stoichiometry"]):
        return dict(status="unavailable", difference_mol_per_kg_s=None, reason="Different overall reactions")
    values = [r["tof"]["overall"]["mol_per_kg_s"] for r in reports]
    if None in values or not isfinite(values[1] - values[0]):
        return dict(status="unavailable", difference_mol_per_kg_s=None, reason="Overall rate difference unavailable")
    return dict(status="available", difference_mol_per_kg_s=values[1] - values[0],
                source_reports_sha256=[identity(r) for r in reports])
