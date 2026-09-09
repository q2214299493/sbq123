from __future__ import annotations

from typing import Any
from importlib import import_module

from scripts.artifact_io import sha256_file
from pathlib import Path

from .evidence_lifecycle import record_subject, require_transferable


def _reviewed_record(record: dict, species: str, surface: str, *, whitelist: bool) -> bool:
    try:
        if whitelist:
            validator = import_module("skills.catalysis-data-retrieval.scripts.validate_records")
            sources = validator.source_map(validator.load_source_config(validator.DEFAULT_SOURCES))
            if validator.validate_record(record, sources):
                return False
        evidence = record["evidence"]
        if evidence["source"]["reference"] != record.get("source_url", record.get("publisher_url")):
            return False
        if evidence["claim"]["record_sha256"] != record_subject(record):
            return False
        require_transferable(evidence, {
            "domain": "surface_adsorption", "scope": "motif_selection",
            "compatibility": {"species": species, "surface": surface},
        })
        return True
    except (KeyError, TypeError, ValueError):
        return False


def resolve_external_evidence(payload: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    from copy import deepcopy

    plan = _resolve_external_evidence(payload, rules)
    plan["source_evidence_payload"] = deepcopy(payload)
    return plan


def validate_external_plan(plan: dict, *, species: str, surface: str) -> dict:
    """Reapply the owning gate at consumption; a cached READY is not authority."""
    import yaml

    payload = plan.get("source_evidence_payload")
    if not isinstance(payload, dict) or payload.get("species") != species or payload.get("surface") != surface:
        raise ValueError("external plan lacks matching source evidence")
    path = Path(__file__).resolve().parents[2] / "configs/adsmind_lite/evidence_gate.yaml"
    expected = resolve_external_evidence(payload, yaml.safe_load(path.read_text(encoding="utf-8")))
    if expected != plan:
        raise ValueError("external plan is stale or differs from its source evidence")
    return expected


def _resolve_external_evidence(payload: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    """Resolve whitelist-first motif evidence without importing external energies."""
    species = str(payload["species"])
    surface = str(payload["surface"])
    whitelist = payload["whitelist"]
    status = str(whitelist["status"])
    literature = payload.get("literature", {"searched": False, "records": []})

    if status == "MATCH":
        if literature.get("searched") or literature.get("records"):
            raise ValueError("literature_search_forbidden_when_whitelist_match_exists")
        records = [record for record in whitelist.get("records", [])
                   if _exact_target_match(record) and _reviewed_record(record, species, surface, whitelist=True)]
        motifs = _collect_motifs(records, rules, source_type="whitelist")
        if not motifs:
            raise ValueError("whitelist_MATCH_requires_a_usable_stable_motif")
        return _plan(species, surface, "whitelist", motifs)

    if status != "NO_WHITELIST_MATCH":
        raise ValueError(f"unsupported_whitelist_status:{status}")
    if not literature.get("searched"):
        return _empty_plan(species, surface, "NEEDS_LITERATURE", "no_whitelist_match_requires_authoritative_literature")

    records = [record for record in literature.get("records", [])
               if _accepted_literature_record(record, rules)
               and _reviewed_record(record, species, surface, whitelist=False)]
    motifs = _collect_motifs(records, rules, source_type="authoritative_literature")
    if not motifs:
        return _empty_plan(species, surface, "NEEDS_REVIEW", "no_exact_authoritative_literature_stable_motif")
    return _plan(species, surface, "authoritative_literature", motifs)


def _accepted_literature_record(record: dict[str, Any], rules: dict[str, Any]) -> bool:
    required = rules["literature"]["required_source_fields"]
    if any(not record.get(field) for field in required):
        return False
    return (
        record.get("article_type") == rules["literature"]["article_type"]
        and record.get("journal_authority_review") == "accepted"
        and record.get("doi_verified") is True
        and _exact_target_match(record)
    )


def _exact_target_match(record: dict[str, Any]) -> bool:
    return record.get("exact_surface_match") is True and record.get("exact_adsorbate_match") is True


def _collect_motifs(records: list[dict[str, Any]], rules: dict[str, Any], *, source_type: str) -> list[dict[str, Any]]:
    required = rules["required_motif_fields"]
    accepted_stability = set(rules["literature"]["accepted_stability_evidence"])
    unique: dict[str, dict[str, Any]] = {}
    for record in records:
        source_id = str(record.get("record_id") or record.get("doi") or record.get("url") or "unidentified")
        for motif in record.get("stable_motifs", []):
            if any(field not in motif or motif[field] in (None, "", []) for field in required):
                continue
            rank = motif["stability_rank"]
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                continue
            if source_type == "authoritative_literature" and motif["stability_evidence"] not in accepted_stability:
                continue
            motif_id = str(motif["motif_id"])
            item = {**motif, "evidence_source": source_type, "source_ids": [source_id]}
            if motif_id in unique:
                if unique[motif_id]["stability_rank"] != rank:
                    raise ValueError(f"conflicting_stability_rank_for_motif:{motif_id}")
                unique[motif_id]["source_ids"] = list(dict.fromkeys([*unique[motif_id]["source_ids"], source_id]))
            else:
                unique[motif_id] = item
    return sorted(unique.values(), key=lambda item: (item["stability_rank"], item["motif_id"]))


def _plan(species: str, surface: str, source_type: str, motifs: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = []
    for priority, motif in enumerate(motifs, start=1):
        item = {**motif, "priority": priority}
        template = item.get("reviewed_structure_template")
        item["build_ready"] = (isinstance(template, dict)
                               and isinstance(template.get("path"), str)
                               and Path(template["path"]).is_file()
                               and sha256_file(Path(template["path"])) == template.get("sha256"))
        item["reason_code"] = "selected_by_evidence_gate" if item["build_ready"] else "reviewed_structure_template_required"
        candidates.append(item)
    blocked = sum(not item["build_ready"] for item in candidates)
    decision = "READY" if blocked == 0 else "BLOCKED" if blocked == len(candidates) else "PARTIAL"
    return {
        "species": species,
        "surface": surface,
        "decision": decision,
        "confidence": "medium",
        "evidence": {
            "type": source_type,
            "usage_scope": "structure_selection_stability_order_and_initial_geometry_only",
            "external_energy_use": "relative_order_reference_only",
            "energy_import_allowed": False,
            "local_relaxation_and_static_validation_required": True,
            "global_minimum_claim": False,
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
        "suppressed": ["fixed_site_sweep", "unsupported_site_or_configuration"],
    }


def _empty_plan(species: str, surface: str, decision: str, reason: str) -> dict[str, Any]:
    return {
        "species": species,
        "surface": surface,
        "decision": decision,
        "confidence": "low",
        "candidate_count": 0,
        "candidates": [],
        "reason_code": reason,
    }
