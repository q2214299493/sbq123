"""Build and optionally publish a write-once local network artifact."""
import argparse
import json
from pathlib import Path

from scripts.artifact_io import sha256_bytes, sha256_file, sha256_json, write_json_exclusive
from scripts.multiphase_contracts import _unique_keys
from scripts.reaction_network.builder import build_network, from_registry_mapping


def read_source(path, role, sources):
    raw = path.read_bytes()
    sources.append({"role": role, "file": path.name, "sha256": sha256_bytes(raw)})
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_keys)


def publish(snapshot, directory):
    digest = sha256_json({k: v for k, v in snapshot.items() if k != "network_version"})
    if snapshot["network_version"] != digest:
        raise ValueError("Network version digest mismatch")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"network-{digest}.json"
    try:
        write_json_exclusive(path, snapshot)
    except FileExistsError:
        existing = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
        if sha256_json(existing) != sha256_json(snapshot):
            raise ValueError("Existing network artifact differs; preserve it for review") from None
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("definition", type=Path, help="Phase 1 bundle, network-definition/1, or Phase 1 partial field mapping")
    parser.add_argument("--project-id", help="Catalyst project ID for a partial registry field mapping")
    parser.add_argument("--intake", type=Path, action="append", default=[])
    parser.add_argument("--thermochemistry", type=Path, action="append", default=[])
    parser.add_argument("--evidence", type=Path, action="append", default=[], help="Verify an existing review/source artifact")
    parser.add_argument("--decision", type=Path, action="append", default=[], help="Existing review bound to a reaction subject digest")
    parser.add_argument("--ts-review", type=Path, action="append", default=[], help="Grade A assignment with reaction ID and TS identity")
    parser.add_argument("--site-proposal", type=Path, help="Site projections and mapping options bound to the parent version")
    parser.add_argument("--site-confirmation", type=Path, help="Researcher decision bound to the original site proposal")
    parser.add_argument("--site-catalog", type=Path, help="Project-specific allowed site types, keyed by surface ID")
    parser.add_argument("--output-dir", type=Path, help="Write a content-addressed version; otherwise print the snapshot")
    args = parser.parse_args()
    sources = []
    definition = read_source(args.definition, "definition", sources)
    if definition.get("record_kind") == "partial_phase1_field_mapping":
        if not args.project_id:
            parser.error("--project-id is required for this mapping")
        definition = from_registry_mapping(definition, args.project_id)
    intakes = [read_source(p, "intake", sources) for p in args.intake]
    thermal = [read_source(p, "thermochemistry", sources) for p in args.thermochemistry]
    decisions = [read_source(p, "network_review", sources) for p in args.decision]
    ts_reviews = [read_source(p, "ts_review", sources) for p in args.ts_review]
    verified = set()
    for path in args.evidence:
        digest = sha256_file(path)
        sources.append({"role": "verified_evidence", "file": path.name, "sha256": digest})
        verified.add(digest)
    site_inputs = {key: json.loads(path.read_bytes(), object_pairs_hook=_unique_keys)
                   for key, path in (("site_proposal", args.site_proposal), ("site_confirmation", args.site_confirmation),
                                     ("site_catalog", args.site_catalog)) if path}
    network = build_network(definition, intakes=intakes, thermochemistry=[d.get("calculation", d) for d in thermal],
                            sources=sources, verified_hashes=verified, decisions=decisions, ts_reviews=ts_reviews, **site_inputs)
    if args.output_dir:
        print(publish(network, args.output_dir))
    else:
        print(json.dumps(network, ensure_ascii=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
