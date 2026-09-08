from __future__ import annotations

from typing import Any

from .adsmind_common import load_yaml_schema


def load_fts_rules(path: str) -> dict[str, Any]:
    return load_yaml_schema(
        path,
        ("scope", "method", "calibration_profiles"),
        "iron FTS rules require scope, method, and calibration_profiles",
    )


def assert_fts_surface(surface_name: str, rules: dict[str, Any]) -> None:
    allowed = {str(name).casefold() for name in rules["scope"]["allowed_surface_names"]}
    if surface_name.casefold() not in allowed:
        raise ValueError(f"{surface_name}: {rules['scope']['reason_code']}")


def find_profile(species_name: str, rules: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    normalized = species_name.casefold()
    for profile_name, profile in rules["calibration_profiles"].items():
        names = [profile_name, *profile.get("aliases", [])]
        if normalized in {str(name).casefold() for name in names}:
            return profile_name, profile
    return None


def plan_calibrated_fts_species(
    species_name: str,
    rules: dict[str, Any],
    *,
    available_templates: set[str] | None = None,
    surface_name: str = "Fe110",
) -> dict[str, Any] | None:
    """Return a reviewed Fe(110) motif plan for an exact calibrated species name."""
    assert_fts_surface(surface_name, rules)
    matched = find_profile(species_name, rules)
    if matched is None:
        return None
    profile_name, profile = matched
    available_templates = available_templates or set()
    candidates: list[dict[str, Any]] = []
    for source in sorted(profile["candidates"], key=lambda item: int(item["priority"])):
        candidate = dict(source)
        required = bool(candidate.get("template_required", False))
        candidate["build_ready"] = not required or candidate["motif_id"] in available_templates
        candidate["reason_code"] = "selected_by_reviewed_fts_rule" if candidate["build_ready"] else "reviewed_structure_template_required"
        candidates.append(candidate)

    priority_blocked = bool(candidates and not candidates[0]["build_ready"])
    any_blocked = any(not candidate["build_ready"] for candidate in candidates)
    decision = "BLOCKED" if priority_blocked else "PARTIAL" if any_blocked else "READY"
    return {
        "species": species_name,
        "matched_profile": profile_name,
        "decision": decision,
        "confidence": profile.get("confidence", "low"),
        "evidence": {"type": profile.get("evidence"), "global_minimum_claim": False},
        "candidate_count": len(candidates),
        "candidates": candidates,
        "suppressed": profile.get("suppress", []),
    }


def rank_carbon_sites(coordination_demand: int, rules: dict[str, Any]) -> list[str]:
    if coordination_demand not in range(5):
        raise ValueError("carbon coordination demand must be an integer from 0 to 4")
    return list(rules["method"]["carbon_coordination_demand"][coordination_demand]["ranked_sites"])


def plan_feature_based_fts_species(
    species_name: str,
    features: dict[str, Any],
    rules: dict[str, Any],
    *,
    surface_name: str = "Fe110",
) -> dict[str, Any]:
    """Create non-build-ready Fe(110) retrieval hypotheses from explicit chemical features.

    Coordination demand is dimensionless; atom labels are species-local, not
    structure indices. The result must never be used directly to generate POSCARs.
    """
    assert_fts_surface(surface_name, rules)
    carbon_centers = [center for center in features.get("carbon_centers", []) if center.get("surface_accessible", True)]
    oxygen_centers = [center for center in features.get("oxygen_centers", []) if center.get("surface_accessible", True)]
    if not carbon_centers and not oxygen_centers:
        return _feature_failure(species_name, "no_accessible_binding_center")

    carbon_centers.sort(key=lambda center: (-int(center["coordination_demand"]), str(center["label"])))
    candidates: list[dict[str, Any]] = []
    carbonyl = next((oxygen for oxygen in oxygen_centers if oxygen.get("role") == "carbonyl"), None)
    eta2_allowed = bool(features.get("eta2_CO_geometry_allowed", False)) and carbonyl is not None and carbon_centers
    oxygen_role = oxygen_centers[0].get("role") if oxygen_centers else None

    cc_mode = features.get("cc_mode")
    if cc_mode:
        candidates.extend(_plan_cc_mode(species_name, features, rules, str(cc_mode)))
    elif oxygen_role == "water_or_alcohol_donor" and all(int(center["coordination_demand"]) == 0 for center in carbon_centers):
        primary_o = oxygen_centers[0]
        candidates.extend(
            [
                _motif(species_name, f"{primary_o['label']}_top_chain_along_row", "O_centered", [primary_o["label"]]),
                _motif(species_name, f"{primary_o['label']}_top_chain_across_row", "O_centered", [primary_o["label"]]),
            ]
        )
    elif features.get("carbonyl_subtype") == "closed_shell_aldehyde" and eta2_allowed:
        candidates.append(_motif(species_name, "eta2_CO_side_on", "bidentate", [carbon_centers[0]["label"], carbonyl["label"]]))
        candidates.append(_motif(species_name, "O_top_tilted", "monodentate", [carbonyl["label"]]))
        if features.get("flexible_c2plus", False):
            candidates.append(_motif(species_name, "eta2_CO_rotated", "bidentate", [carbon_centers[0]["label"], carbonyl["label"]]))
    elif features.get("carbonyl_subtype") == "acyl_radical" and eta2_allowed:
        primary = carbon_centers[0]
        candidates.extend(
            [
                _motif(species_name, f"{primary['label']}_top", "C_centered", [primary["label"]]),
                _motif(species_name, "eta2_CO_side_on", "bidentate", [primary["label"], carbonyl["label"]]),
                _motif(species_name, f"{primary['label']}_long_bridge", "C_centered", [primary["label"]]),
            ]
        )
    elif carbon_centers:
        primary = carbon_centers[0]
        demand = int(primary["coordination_demand"])
        ranked_sites = _steric_adjusted_carbon_sites(primary, rank_carbon_sites(demand, rules))
        candidates.extend(_motif(species_name, f"{primary['label']}_{site}", "C_centered", [primary["label"]]) for site in ranked_sites)
        if eta2_allowed:
            eta2 = _motif(species_name, "eta2_CO_side_on", "bidentate", [primary["label"], carbonyl["label"]])
            if oxygen_role == "hydroxyl" and demand == 2:
                candidates.insert(1, eta2)
            else:
                candidates.append(eta2)
    else:
        primary_o = oxygen_centers[0]
        role_rules = rules["method"]["oxygen_role"].get(primary_o.get("role"), {})
        candidates.extend(
            _motif(species_name, f"{primary_o['label']}_{site}", "O_centered", [primary_o["label"]])
            for site in role_rules.get("ranked_sites", [])
        )

    for priority, candidate in enumerate(candidates, start=1):
        candidate["priority"] = priority
        candidate["build_ready"] = False
        candidate["reason_code"] = "search_hypothesis_only_requires_external_evidence"
    return {
        "species": species_name,
        "decision": "NEEDS_WHITELIST",
        "confidence": "low",
        "evidence": {"type": "iron_fts_chemical_feature_rule", "global_minimum_claim": False},
        "candidate_count": len(candidates),
        "candidates": candidates,
        "suppressed": ["fixed_site_sweep", "heuristic_candidate_generation"],
    }


def _steric_adjusted_carbon_sites(center: dict[str, Any], sites: list[str]) -> list[str]:
    if not center.get("substituted", False):
        return sites
    return [site for site in sites if site != "hollow"] + [site for site in sites if site == "hollow"]


def _plan_cc_mode(species: str, features: dict[str, Any], rules: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    mode_rules = rules["method"]["c_c_modes"].get(mode)
    if mode_rules is None:
        raise ValueError(f"unsupported C-C adsorption mode: {mode}")
    cc_atoms = list(features.get("cc_atoms", ["C1", "C2"]))
    radical = str(features.get("radical_carbon", cc_atoms[0]))
    motifs: list[dict[str, Any]] = []
    for name in mode_rules["ranked_motifs"]:
        if name == "di_sigma_long":
            motifs.append(_motif(species, name, "di_sigma", cc_atoms))
        elif name == "di_sigma_short":
            motifs.append(_motif(species, name, "di_sigma", cc_atoms))
        elif name == "eta2_CC_side_on":
            motifs.append(_motif(species, name, "bidentate", cc_atoms))
        elif name == "pi_top":
            motifs.append(_motif(species, name, "pi_complex", cc_atoms))
        elif name == "radical_C_top":
            motifs.append(_motif(species, f"{radical}_top", "C_centered", [radical]))
        elif name == "radical_C_long_bridge":
            motifs.append(_motif(species, f"{radical}_long_bridge", "C_centered", [radical]))
        elif name == "radical_C_bridge":
            motifs.append(_motif(species, f"{radical}_bridge", "C_centered", [radical]))
    return motifs


def _motif(species: str, suffix: str, binding_mode: str, binding_atoms: list[str]) -> dict[str, Any]:
    return {
        "motif_id": f"{species}_{suffix}",
        "binding_mode": binding_mode,
        "binding_atoms": binding_atoms,
        "site_pattern": suffix.split("_", 1)[-1],
    }


def _feature_failure(species: str, reason: str) -> dict[str, Any]:
    return {
        "species": species,
        "decision": "NEEDS_REVIEW",
        "confidence": "low",
        "candidate_count": 0,
        "candidates": [],
        "reason_code": reason,
    }
