"""Bind existing CARE reaction records, without importing predicted energies."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from pathlib import Path
import re

from scripts.artifact_io import source_file_manifest, write_json_exclusive
from .collect import CARE, OUT

SOURCE = CARE / "robust_minimax_path_screen"
SELECTED = {
    "REV_C1C6_R000124::F": (2, "P1", "CH+CO C-C coupling;existing9994246 is related diagnostic only"),
    "C1C6_R041835::R": (2, "P1", "C2 oxygenate H addition;C-H/O-H site requires atom-mapped geometry"),
    "C1C6_R057125::R": (3, "P1", "C2+C1 chain growth toward C3;actual mapped path missing"),
    "C1C6_R022170::F": (3, "P1", "C3 skeleton cleavage;keep CO+C2H2 diagnostics distinct from intact C3"),
    "C1C6_R000427::F": (3, "P1", "C3 C-O removal;actual mapped geometry missing"),
    "C1C6_R036189::R": (3, "P1", "C3 hydrogenation local environment;isomer and H site unresolved"),
    "C1C6_R034176::R": (4, "P1", "C3+C1 growth;C4 coordinate and compatible label gap"),
    "REV_C1C6_R002321::F": (4, "P1", "source nominal CO insertion;insertion mechanism not atom-map verified"),
    "C1C6_R038452::F": (4, "P1", "C4 oxygenate C-O removal;coordinate and label gap"),
    "C1C6_R028346::R": (4, "P1", "C4 H addition;coordinate and label gap"),
    "REV_C1C6_R044821::F": (5, "P2_REPRESENTATIVE", "one C5 oxygenated chain-growth representative;no full C5 matrix"),
    "C1C6_R034542::F": (5, "P2_REPRESENTATIVE", "one C5 deoxygenation representative;no full C5 matrix"),
    "REV_C1C6_R286696::F": (6, "P2_REPRESENTATIVE", "C3+C3 to intact C6;coadsorbed reactant is not a C6 skeleton"),
    "REV_C1C6_R252658::F": (6, "P2_REPRESENTATIVE", "one C6 oxygenated extension;no full C6 matrix"),
}


def formula(token: str) -> tuple[int, Counter]:
    token = token.strip().replace("(g)", "").replace("*", "")
    if not token:
        return 1, Counter()
    coefficient = re.match(r"^(\d+)", token)
    multiplier = int(coefficient[1]) if coefficient else 1
    token = token[len(coefficient[1]):] if coefficient else token
    terms = re.findall(r"([CHO])(\d*)", token)
    if not terms or "".join(a + b for a, b in terms) != token:
        raise ValueError("unsupported source species: " + token)
    counts = Counter()
    for element, count in terms:
        counts[element] += int(count or 1)
    return multiplier, counts


def reaction_counts(text: str) -> dict:
    sides = text.split("->")
    if len(sides) != 2:
        raise ValueError("source is not a directed reaction")
    result = []
    largest = []
    for side in sides:
        totals = Counter()
        sizes = []
        for token in side.split("+"):
            multiplier, counts = formula(token)
            totals.update({s: multiplier * n for s, n in counts.items()})
            sizes.append(counts["C"])
        result.append(dict(totals))
        largest.append(max(sizes))
    if result[0] != result[1]:
        raise ValueError("unbalanced source reaction: " + text)
    return {"element_totals_each_side": result, "total_C_each_side": result[0].get("C", 0),
            "largest_single_formula_C_each_side": largest,
            "connected_carbon_graph": "Needs confirmation;not determined by formula",
            "largest_formula_is_not_proof_of_connectivity_or_isomer": True}


def export_csv(path, rows, columns):
    with path.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (";".join(map(str, v)) if isinstance(v, list) else v) for k, v in row.items()})


def run():
    step_path = SOURCE / "retained_robust_path_steps.csv"
    network_path = SOURCE / "robust_screened_elementary_network.csv"
    with step_path.open(encoding="utf-8-sig", newline="") as handle:
        steps = list(csv.DictReader(handle))
    with network_path.open(encoding="utf-8-sig", newline="") as handle:
        network = {r["reaction_id"]: r for r in csv.DictReader(handle)}
    grouped = defaultdict(list)
    for row in steps:
        grouped[row["directed_id"]].append(row)
    records = []
    for directed_id, aliases in sorted(grouped.items()):
        texts = {r["directed_reaction"] for r in aliases}
        if len(texts) != 1:
            raise ValueError("reaction ID text conflict")
        original = network[aliases[0]["base_reaction_id"]]
        text = next(iter(texts))
        record = {"directed_id": directed_id, "base_reaction_id": aliases[0]["base_reaction_id"],
                  "reaction_direction": aliases[0]["reaction_direction"], "reaction": text,
                  "source_nominal_family": original["literature_family"],
                  "path_ids": sorted({r["path_id"] for r in aliases}),
                  "target_carbon_groups": sorted({int(r["target_carbon"]) for r in aliases}),
                  "source_kind": "EXISTING_SYMBOLIC_PREDICTED_OR_PRIOR_NETWORK_NOT_DFT_PATH",
                  "source_file": str(step_path), "geometry_path": None, "geometry_sha256": None,
                  "same_coordinate_DFT_label": "Needs confirmation;no coordinates bound",
                  "compatibility": "Needs confirmation;formula/network is not a DFT compatibility proof",
                  "new_DFT_budget": "UNALLOCATED;coordinates_atom_map_and_dedup_required_first",
                  "new_training_or_computation": False, **reaction_counts(text)}
        records.append(record)
    indexed = {r["directed_id"]: r for r in records}
    selected = []
    for name, (carbon, priority, reason) in SELECTED.items():
        record = {**indexed[name], "target_scope_C": carbon, "priority": priority,
                  "selection_reason": reason, "candidate_type": "REACTION_SOURCE_PROPOSAL_NOT_STRUCTURE_OR_DFT_READY"}
        selected.append(record)
    payload = {"status": "READ_ONLY_REACTION_SOURCE_GAP_INVENTORY", "source_steps": len(steps),
               "source_paths": len({r["path_id"] for r in steps}), "source_network_reactions": len(network),
               "unique_directed_records": len(records), "records": records, "representative_proposals": selected,
               "path_counts_by_target_C": dict(Counter(r["target_carbon"] for r in {r["path_id"]: r for r in steps}.values())),
               "predicted_barriers_imported_as_local_DFT_or_training_targets": False,
               "source_files": source_file_manifest([step_path, network_path, SOURCE / "robust_path_screen_summary.json", Path(__file__)])}
    write_json_exclusive(OUT / "reaction_network_sources.json", payload)
    export_csv(OUT / "reaction_source_proposals.csv", selected, ["directed_id", "target_scope_C", "priority", "reaction",
               "source_nominal_family", "source_kind", "source_file", "geometry_path", "same_coordinate_DFT_label",
               "selection_reason", "compatibility", "new_DFT_budget", "path_ids"])
    print({"network_reactions": len(network), "paths": payload["source_paths"], "directed_edges": len(records),
           "representative_proposals": len(selected)}, flush=True)


if __name__ == "__main__":
    run()
