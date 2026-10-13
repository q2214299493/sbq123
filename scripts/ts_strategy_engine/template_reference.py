"""Read-only registered-template snapshots and safe reference summaries; no result transfer."""
from __future__ import annotations

from pathlib import Path

from scripts.artifact_io import require_sha256, sha256_file, sha256_json
from . import fingerprint, matched_static_evidence, strategy, templates
from .registry import open_registry


def _related_rows(connection, table, key, identities):
    values = sorted({value for value in identities if value is not None})
    if not values:
        return []
    placeholders = ",".join("?" for _ in values)
    return [dict(row) for row in connection.execute(
        f"SELECT * FROM {table} WHERE {key} IN ({placeholders}) ORDER BY {key}", values)]


def _registered_state(database):
    """Snapshot complete rows behind the existing template validator's joined view."""
    with open_registry(database) as connection:
        connection.execute("BEGIN")
        records = [dict(row) for row in connection.execute("SELECT * FROM ts_strategy_templates ORDER BY template_id")]
        validations = _related_rows(connection, "ts_validations", "ts_validation_id", (r["ts_validation_id"] for r in records))
        barriers = _related_rows(connection, "ts_barriers", "barrier_set_id", (r["barrier_set_id"] for r in records))
        file_ids = [r["ts_structure_file_id"] for r in records]
        file_ids.extend(value for row in validations for key, value in row.items() if key.endswith("_file_id"))
        files = _related_rows(connection, "files", "file_id", file_ids)
    return {"templates": records, "validations": validations, "barriers": barriers, "files": files}


def _snapshot(database):
    if database is None:
        raise ValueError("template reference requires an explicit --database")
    before = _registered_state(database)
    loaded = templates.load_templates(database)
    after = _registered_state(database)
    if sha256_json(before) != sha256_json(after):
        raise ValueError("template registry changed during snapshot reading")
    code = {module.__name__: sha256_file(Path(module.__file__))
            for module in (templates, fingerprint, strategy, matched_static_evidence)}
    digest = sha256_json({"schema_version": 1, "registered_rows": after, "loaded_templates": loaded, "code_sha256": code})
    return loaded, {"schema_version": 1, "snapshot_sha256": digest, "template_count": len(loaded),
                    "registered_row_counts": {key: len(value) for key, value in after.items()}, "code_sha256": code,
                    "registered_evidence_only": True, "physical_source_files_reverified": False}


def template_snapshot(database: Path):
    """Return identity metadata only; historical structures/energies stay in their registry."""
    return _snapshot(database)[1]


def template_references(database: Path, current_fingerprint: dict, expected_sha256: str | None, *, enabled: bool = True):
    if enabled != (expected_sha256 is not None):
        raise ValueError("template reference requires both --use-templates and --expected-template-snapshot-sha256")
    if not enabled:
        return [], None, {}
    loaded, snapshot = _snapshot(database)
    expected = require_sha256(expected_sha256, label="expected template snapshot SHA-256")
    if snapshot["snapshot_sha256"] != expected:
        raise ValueError("template snapshot identity mismatch; capture and review the current registered evidence")
    errors = {}
    for item in loaded:
        try:
            templates.validate_record(item)
        except ValueError as exc:
            errors[item["template_id"]] = str(exc)
            item["evidence_valid"] = False
    return fingerprint.rank_templates(current_fingerprint, loaded), snapshot, errors


def reference_report(ranked, snapshot, errors, composed, rules):
    """Keep provenance/eligibility and method choices, never historical numerical results."""
    selected = (composed["template_match"] or {}).get("template_id")
    threshold = rules.get("strategy_transfer_threshold", rules["template_transfer_threshold"])
    rows = []
    for match in ranked:
        item = match["template"]
        reasons = []
        if item["template_id"] in errors:
            reasons.append("template_record_invalid: " + errors[item["template_id"]])
        if item["outcome"] != "success":
            reasons.append("failure_experience_not_success")
        if not match["evidence_valid"]:
            reasons.append("registered_success_evidence_not_valid")
        if not match["chemical_event_equivalent"]:
            reasons.append("chemical_events_missing_or_not_equivalent")
        if not match["strategy_transferable"]:
            reasons.append("existing_strategy_matching_conditions_not_met")
        if match["score"] < threshold:
            reasons.append("below_existing_transfer_threshold")
        if composed["status"].startswith("STOP"):
            reasons.append(composed["status"])
        if not reasons and selected != item["template_id"]:
            reasons.append("another_template_selected_by_existing_composition")
        rows.append({"template_id": item["template_id"], "source_calculation_id": item["source_calculation_id"],
            "ts_validation_id": item.get("ts_validation_id"), "barrier_set_id": item.get("barrier_set_id"),
            "selected": item["template_id"] == selected, "reasons": reasons,
            "template_similarity_score": match["score"],
            **{key: match[key] for key in ("match_level", "strategy_match_level", "compatible", "chemical_match",
               "chemical_event_equivalent", "evidence_valid", "strategy_transferable", "result_transferable")},
            "registered_validation": {key: item.get(key) for key in (
                "validation_source_method", "evidence_grade", "kinetic_eligible", "imaginary_frequency_count",
                "geometry_status", "validation_reviewer", "validation_reviewed_at")}})
    fields = ("waypoint_strategy", "interpolation_strategy", "neb_settings", "dimer_usage")
    return {"enabled": True, "snapshot": snapshot, "expected_snapshot_sha256": snapshot["snapshot_sha256"],
            "selected_template_id": selected, "templates": rows,
            "existing_strategy_transfer_threshold": threshold,
            "selection_status": "MATCHED_METHOD_REFERENCE" if selected else "NO_QUALIFIED_MATCH_RULE_FALLBACK",
            "borrowable_method_strategy": {key: composed[key] for key in fields} if selected else {},
            "nontransferable_fields": sorted(templates.NONTRANSFERABLE_STRATEGY_KEYS | set(composed["nontransferable_artifacts"])),
            "ranking_kind": "existing_template_similarity_not_method_effectiveness_or_success_probability",
            "current_task_checks_still_required": True, "scientific_results_imported": False,
            "physical_source_files_reverified": False}
