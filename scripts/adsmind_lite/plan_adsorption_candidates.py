from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from scripts.artifact_io import load_json_object, write_json

from .evidence_gate import resolve_external_evidence
from .fts_prescreen import load_fts_rules
from .prescreen import load_prescreen_rules, plan_batch


ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan a small chemistry-aware adsorption candidate set; never submits jobs.")
    parser.add_argument("--species", required=True, help="Comma-separated exact species labels.")
    parser.add_argument("--surface-name", default="Fe110", help="Must be Fe110 for the iron FTS pre-screen rules.")
    parser.add_argument(
        "--rules",
        type=Path,
        default=ROOT / "configs" / "adsmind_lite" / "prescreen_rules.yaml",
    )
    parser.add_argument("--available-template", action="append", default=[], help="Motif ID with a reviewed structure template.")
    parser.add_argument(
        "--fts-rules",
        type=Path,
        default=ROOT / "configs" / "adsmind_lite" / "iron_fts_prescreen.yaml",
    )
    parser.add_argument(
        "--external-evidence",
        action="append",
        default=[],
        type=Path,
        help="JSON evidence package; whitelist is evaluated before authoritative literature.",
    )
    parser.add_argument(
        "--evidence-rules",
        type=Path,
        default=ROOT / "configs" / "adsmind_lite" / "evidence_gate.yaml",
    )
    parser.add_argument(
        "--adsorbate-rules",
        type=Path,
        default=ROOT / "configs" / "adsmind_lite" / "adsorbate_rules.yaml",
        help="Adsorbate metadata catalog used to formulate retrieval targets.",
    )
    parser.add_argument(
        "--species-features",
        type=Path,
        help="Optional YAML/JSON mapping under species_features; creates retrieval hypotheses only.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON output path; stdout remains a compact summary.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    names = [value.strip() for value in args.species.split(",") if value.strip()]
    rules = load_prescreen_rules(str(args.rules))
    fts_rules = load_fts_rules(str(args.fts_rules))
    evidence_rules = yaml.safe_load(args.evidence_rules.read_text(encoding="utf-8"))
    external_plans: dict[str, dict] = {}
    for path in args.external_evidence:
        payload = load_json_object(path)
        for target in payload.get("targets", [payload]):
            plan = resolve_external_evidence(target, evidence_rules)
            species = str(plan["species"])
            if species in external_plans:
                raise SystemExit(f"duplicate external evidence for {species}")
            external_plans[species] = plan
    adsorbate_catalog = yaml.safe_load(args.adsorbate_rules.read_text(encoding="utf-8"))["adsorbates"]
    species_features: dict[str, dict] = {}
    if args.species_features:
        feature_payload = yaml.safe_load(args.species_features.read_text(encoding="utf-8"))
        raw_features = feature_payload.get("species_features", feature_payload) if isinstance(feature_payload, dict) else None
        if not isinstance(raw_features, dict) or any(not isinstance(value, dict) for value in raw_features.values()):
            raise SystemExit("species features must be a mapping of species names to feature mappings")
        species_features = {str(key): value for key, value in raw_features.items()}
    try:
        plan = plan_batch(
            names,
            rules,
            available_templates=set(args.available_template),
            adsorbate_catalog=adsorbate_catalog,
            fts_rules=fts_rules,
            external_plans=external_plans,
            species_features=species_features,
            surface_name=args.surface_name,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, plan)
    summary = plan["summary"]
    print(
        f"species={summary['species']} candidates={summary['candidate_count']} "
        f"ready={summary['ready_species']} blocked={summary['blocked_species']} "
        f"needs_review={summary['needs_review_species']} "
        f"needs_whitelist={summary['needs_whitelist_species']} "
        f"needs_literature={summary['needs_literature_species']} "
        f"search_hypotheses={summary['search_hypothesis_count']} submitted=0"
    )
    for species_plan in plan["species_plans"]:
        motifs = ",".join(item["motif_id"] for item in species_plan["candidates"]) or "-"
        print(f"{species_plan['species']} {species_plan['decision']} {motifs}")


if __name__ == "__main__":
    main()
