"""Initial site/binding coverage; candidate counts are not stable-minimum counts."""
from __future__ import annotations

from typing import Any

from scripts.runtime_resources import resource_path

from .adsmind_common import SITE_CLASS_MAP, load_yaml_schema


SITE_PATTERN_ALIASES = {name.casefold(): value for name, value in SITE_CLASS_MAP.items()}
SITE_PATTERN_ALIASES.update({value.casefold(): value for value in SITE_CLASS_MAP.values()})
SINGLE_ANCHOR_MODES = {"c_centered", "o_centered", "terminal_c_centered"}
PLANNING_FIELDS = {
    "plan_source", "evidence_priority_rank", "evidence_decision",
    "initial_motif_coverage", "final_stable_minima_count",
}


def initial_motif_identity(motif: dict[str, Any]) -> dict[str, Any] | None:
    site = motif.get("generator_site_class") or motif.get("site_pattern")
    mode = motif.get("binding_mode")
    atoms = motif.get("binding_atoms")
    if not all(isinstance(value, str) and value.strip() for value in (site, mode)):
        return None
    if not isinstance(atoms, list) or not atoms or any(not isinstance(atom, str) or not atom.strip() for atom in atoms):
        return None
    atoms = sorted(atom.strip() for atom in atoms)
    if len(set(atoms)) != len(atoms):
        return None
    mode = mode.strip().casefold()
    return {
        "site_pattern": SITE_PATTERN_ALIASES.get(site.strip().casefold(), site.strip().casefold()),
        "binding_mode": "monodentate" if mode in SINGLE_ANCHOR_MODES else mode,
        "binding_atoms": atoms,
    }


def review_initial_motif_coverage(
    plan: dict[str, Any], rules: dict[str, Any], *, surface_name: str = "Fe110",
) -> dict[str, Any]:
    """Recompute coverage without inventing motifs, historical reviews or minima."""
    required = rules["policy"]["minimum_distinct_initial_motifs"]
    if type(required) is not int or required <= 0:
        raise ValueError("minimum_distinct_initial_motifs must be a positive integer")
    if plan.get("surface", surface_name) != surface_name:
        raise ValueError("adsorption plan surface does not match the requested surface")
    candidates = plan.get("candidates", [])
    if not isinstance(candidates, list) or any(not isinstance(item, dict) for item in candidates):
        raise ValueError("adsorption candidates must be a list of motif mappings")
    groups: dict[tuple, dict[str, Any]] = {}
    missing = []
    for index, motif in enumerate(candidates):
        motif_id = str(motif.get("motif_id") or f"candidate[{index}]")
        identity = initial_motif_identity(motif)
        if identity is None:
            missing.append(motif_id)
            continue
        key = (identity["site_pattern"], identity["binding_mode"], tuple(identity["binding_atoms"]))
        group = groups.setdefault(key, {"identity": identity, "motif_ids": []})
        group["motif_ids"].append(motif_id)
    shortfall = max(0, required - len(groups))
    complete = shortfall == 0 and not missing
    decision = plan["decision"]
    return {
        **plan,
        "surface": surface_name,
        "candidate_count": len(candidates),
        "evidence_decision": plan.get("evidence_decision", decision),
        "decision": "NEEDS_REVIEW" if decision == "READY" and not complete else decision,
        "initial_motif_coverage": {
            "required_count": required,
            "distinct_count": len(groups),
            "shortfall_count": shortfall,
            "missing_identity_motif_ids": missing,
            "status": "PASS" if complete else "NEEDS_REVIEW",
            "groups": list(groups.values()),
        },
        "final_stable_minima_count": None,
    }


def validate_generation_plan(plan: dict[str, Any], species: str, surface: str, rules: dict[str, Any]) -> dict[str, Any]:
    """Revalidate external evidence and current coverage, including legacy caches."""
    from .evidence_gate import validate_external_plan

    if plan.get("species") != species:
        raise ValueError("adsorption plan species does not match the request")
    evidence = plan.get("evidence") or {}
    external = bool(
        "source_evidence_payload" in plan
        or plan.get("plan_source") == "external_evidence_gate"
        or evidence.get("type") in {"whitelist", "authoritative_literature"}
    )
    if external:
        source = {key: value for key, value in plan.items() if key not in PLANNING_FIELDS}
        source["decision"] = plan.get("evidence_decision", plan["decision"])
        source = validate_external_plan(source, species=species, surface=surface)
        # A cached review/blocked decision never grants a generation upgrade.
        if plan["decision"] != "READY":
            source["decision"] = plan["decision"]
        plan = source
    reviewed = review_initial_motif_coverage(plan, rules, surface_name=surface)
    coverage = reviewed["initial_motif_coverage"]
    if reviewed["decision"] != "READY" or reviewed["evidence_decision"] != "READY" or coverage["status"] != "PASS":
        raise ValueError(
            f"{species}: initial_motif_coverage {coverage['distinct_count']}/{coverage['required_count']} "
            f"shortfall={coverage['shortfall_count']} decision={reviewed['decision']}; "
            "review existing evidence or missing modes before any partial batch; no rerun is authorized"
        )
    return reviewed


def generation_coverage_rules() -> dict[str, Any]:
    return load_yaml_schema(
        resource_path("configs/adsmind_lite/prescreen_rules.yaml"),
        ("policy", "species"), "prescreen rules require policy and species mappings",
    )
