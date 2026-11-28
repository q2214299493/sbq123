"""Build recommendations, inspect the Fe inventory or record a human review."""

import argparse
from pathlib import Path

from scripts.artifact_io import load_json_object as read, sha256_json
from .benchmark import fe_inventory, read_sources, synthetic
from .engine import rank
from .structure_binding import validate_structures
from .proposals import proposals, publish, review
from .evidence import registry_inventory
from scripts.baseline_mkm.single_point import ticket_binding
from scripts.kinetic_parameters.engine import check_version
from scripts.artifact_io import sha256_file


def emit(packet, objective, out):
    report = rank(packet, objective)
    publish(out / "reports" / (sha256_json(report) + ".json"), report)
    items = proposals(report, out / "proposals")
    return dict(report_sha256=sha256_json(report), proposal_ids=[p["proposal_id"] for p in items])


def verify_metric_values(data, documents):
    for m in data["metrics"]:
        if m["status"] == "accepted":
            locator = m.get("value_path")
            if not isinstance(locator, list) or not locator:
                raise ValueError("An accepted sensitivity needs a source field path")
            value = documents[m["source"]]
            for field in locator:
                value = value[field]
            if value != m["value"]:
                raise ValueError("Sensitivity differs from its source field")
            binding = m.get("scope_record")
            if not binding and locator[-1] == "value":
                binding = {"source": m["source"], "path": locator[:-1]}
            if not binding:
                m["status"] = "unverified_scope"
                continue
            record = documents[binding["source"]]
            for field in binding["path"]:
                record = record[field]
            fields = (
                "kind",
                "coordinate",
                "parameter_type",
                "parameter",
                "target",
                "observable",
                "observable_kind",
                "scope",
                "value",
                "status",
            )
            same_record = binding["source"] == m["source"] and binding["path"] + ["value"] == locator
            if any(record.get(k) != m.get(k) for k in fields) or (
                not same_record and record.get("value_source_sha256") != data["sources"][m["source"]]["sha256"]
            ):
                raise ValueError("Sensitivity scientific scope differs from reviewed source")


def network_blockers(candidate, documents):
    networks = [
        d
        for d in documents.values()
        if isinstance(d, dict)
        and d.get("network_version") == candidate["scope"]["network_version"]
        and isinstance(d.get("reactions"), list)
        and isinstance(d.get("catalog"), dict)
        and d.get("format") == "reaction-network/1"
    ]
    if not networks:
        return ["Parent reaction network unavailable for scientific attribution"]
    network = networks[0]
    check_version(network, "network_version")
    reactions = {r["definition"]["reaction_id"]: r["definition"] for r in network["reactions"]}
    if not candidate["reaction_ids"] or set(candidate["reaction_ids"]) - reactions.keys():
        return ["Candidate reaction absent from the parent network"]
    connected = [reactions[k] for k in candidate["reaction_ids"]]
    try:
        reason = validate_structures(candidate, network, fixture=documents.get("fixture", {}).get("structures", {}))
    except ValueError as exc:
        return [str(exc)]
    if reason:
        return [reason]
    for field in ("phase_ids", "surface_ids"):
        if set(candidate[field]) - {s for row in connected for s in row[field]}:
            return ["Candidate " + field + " differ from the bound reaction context"]
    species = {s for row in connected for side in ("reactants", "products") for s in row[side]}
    if candidate.get("interface_id") and candidate["interface_id"] not in {row.get("interface_id") for row in connected}:
        return ["Candidate interface differs from the parent network"]
    if set(candidate["site_context"]) - {s["site_id"] for s in network["catalog"]["sites"]}:
        return ["Unknown site inventory in parent network"]
    if set(candidate["species_ids"]) - species:
        return ["Candidate species differ from the bound reaction context"]
    return []


def import_packet(path, registry=None, tickets=None):
    data = read(path)
    documents = read_sources(path.resolve().parent, data["sources"])
    # Keep the producer's selected inputs resolvable when ranking or reviewing from another cwd.
    for name, document in documents.items():
        if isinstance(document, dict) and document.get("format") == "reaction-network/1":
            data["planning_network_source"] = name
            data["sources"][name]["path"] = str((path.resolve().parent / data["sources"][name]["path"]).resolve())
        if name == "fixture":
            data["sources"][name]["path"] = str((path.resolve().parent / data["sources"][name]["path"]).resolve())
    verify_metric_values(data, documents)
    for c in data["candidates"]:
        c.setdefault("blockers", []).extend(network_blockers(c, documents))
        if key := c.get("strategy_source"):
            c["strategy"] = dict(documents[key], source_sha256=data["sources"][key]["sha256"])
        if key := c.get("path_quality_source"):
            quality = documents[key]
            if quality.get("document_kind") != "neb_path_quality_evidence" or not quality.get("source_files"):
                raise ValueError("Unbound NEB Agent path-quality evidence")
            c["path_quality"] = dict(source=key, sha256=data["sources"][key]["sha256"], evidence=quality)
        if key := c.get("spc_source"):
            c["spc_execution_proposal"] = documents[key]
        if tickets is not None and c.get("ticket"):
            binding = ticket_binding(tickets, c["ticket"]["ticket_id"])
            if c["ticket"]["question_id"] != binding["question_id"]:
                raise ValueError("Ticket question differs from the reviewed candidate")
    for record in data["reliability"]:
        if key := record.get("aqcat25_source"):
            record["aqcat25_force_review"] = documents[key]
    if registry:
        targets = {h for c in data["candidates"] for h in c["targets"].values() if h}
        data["registry_hits"] = registry_inventory(registry, targets) if targets else {}
    data["sources"]["reviewed_input_packet"] = dict(path=path.name, sha256=sha256_file(path))
    return data


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="action", required=True)
    b = sub.add_parser("benchmark")
    b.add_argument("output", type=Path)
    f = sub.add_parser("inventory")
    f.add_argument("database", type=Path)
    f.add_argument("output", type=Path)
    r = sub.add_parser("rank")
    r.add_argument("packet", type=Path)
    r.add_argument("objective", type=Path)
    r.add_argument("output", type=Path)
    r.add_argument("--registry", type=Path)
    r.add_argument("--tickets", type=Path)
    h = sub.add_parser("review")
    h.add_argument("directory", type=Path)
    h.add_argument("decision", type=Path)
    returned = sub.add_parser("ingest-return")
    returned.add_argument("directory", type=Path)
    returned.add_argument("review", type=Path)
    returned.add_argument("sha256")
    returned.add_argument("network_directory", type=Path)
    args = cli.parse_args()
    if args.action == "benchmark":
        data, policies = synthetic(Path.cwd())
        index = {k: emit(data, v, args.output) for k, v in policies.items()}
        publish(args.output / "index.json", index)
    elif args.action == "inventory":
        publish(args.output, fe_inventory(Path.cwd(), args.database))
    elif args.action == "rank":
        data = import_packet(args.packet, args.registry, args.tickets)
        print(emit(data, read(args.objective), args.output))
    elif args.action == "ingest-return":
        from sbq123.discovery.ranking.scientific_priority.returned_result import ingest
        print(ingest(args.directory, args.review, args.sha256, args.network_directory))
    else:
        print(review(args.directory, read(args.decision)))


if __name__ == "__main__":
    main()
