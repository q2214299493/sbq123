"""Read-only source/graph review using the existing CARE and geometry owners.

Run in the already installed care_fe110_ft environment. No structure builder,
scientific executor, acceptance gate or production database writer is called.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def molecular_graph(species):
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors
    mol = Chem.MolFromMolBlock(species["molecule"], removeHs=False)
    if mol is None:
        raise ValueError("Original CARE MolBlock cannot be parsed")
    explicit = Chem.AddHs(mol)
    return {"smiles": Chem.MolToSmiles(mol), "formula": rdMolDescriptors.CalcMolFormula(mol),
        "atoms": [{"index": atom.GetIdx(), "element": atom.GetSymbol(), "H_count": atom.GetTotalNumHs(),
                   "radical_electrons": atom.GetNumRadicalElectrons(), "atom_map": atom.GetAtomMapNum()}
                  for atom in mol.GetAtoms()],
        "explicit_symbols": [atom.GetSymbol() for atom in explicit.GetAtoms()],
        "explicit_edges": [[b.GetBeginAtomIdx(), b.GetEndAtomIdx()] for b in explicit.GetBonds()],
        "bond_types": [str(b.GetBondType()) for b in explicit.GetBonds()]}


def graph(symbols, edges):
    import networkx as nx
    value = nx.Graph()
    value.add_nodes_from((index, {"element": symbol}) for index, symbol in enumerate(symbols))
    value.add_edges_from(edges)
    return value


def mappings(left, right):
    import networkx as nx
    matcher = nx.algorithms.isomorphism.GraphMatcher(left, right,
        node_match=lambda a, b: a["element"] == b["element"])
    result = list(matcher.isomorphisms_iter())
    if len(result) > 64:
        raise ValueError("too many mappings; retain ambiguity rather than select one")
    return result


def geometry(poscar, molecular, owner):
    symbols = owner.expanded_symbols(poscar)
    ads = [i for i, symbol in enumerate(symbols) if symbol != "Fe"]
    edges = owner.connectivity(poscar, ads)
    matched = mappings(graph(molecular["explicit_symbols"], molecular["explicit_edges"]),
                       graph([symbols[i] for i in ads], edges))
    return {"atom_count": len(symbols), "symbols": poscar.symbols, "counts": poscar.counts,
        "cell_A": poscar.cell.tolist(), "adsorbate_zero_based": ads,
        "edges_global_zero_based": [[ads[i], ads[j]] for i, j in edges],
        "mapping_count": len(matched),
        "mol_to_global_zero_based": [{str(i): ads[j] for i, j in mapping.items()} for mapping in matched],
        "fixed_atoms": sum(flag == ("F", "F", "F") for flag in poscar.flags),
        "authority": "existing owner distance-connectivity observations; no bond-order or stability acceptance"}


def main(args):
    sys.path.insert(0, str(args.project_root))
    import rdkit
    import networkx as nx
    from scripts.adsorption import build_fe110_care_isomers as owner
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=False)
    (output / "raw").mkdir()
    (output / "collector.original.py").write_bytes(Path(__file__).read_bytes())
    records = []

    def bind(path, name):
        before = digest(path)
        target = output / "raw" / name
        shutil.copyfile(path, target)
        if digest(target) != before or digest(path) != before:
            raise ValueError("source changed while freezing")
        records.append({"path": str(path), "snapshot": str(target), "sha256": before})
        return before

    bind(args.network, "original_C4_network.json.gz")
    with gzip.open(output / "raw/original_C4_network.json.gz", "rb") as handle:
        raw = handle.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError("source archive exceeds bounded inspection")
    network = json.loads(raw)
    csv_path = args.care_package / "reaction_isomer_mapping.csv"
    bind(csv_path, csv_path.name)
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        row = next(row for row in csv.DictReader(handle) if row["base_reaction_id"] == "C1C6_R004388")
    reaction_index = int(row["care_reaction_index"])
    reaction = network["reactions"][reaction_index]
    codes = {"C07": "POVFFVOJLQBKHT-UHFFFAOYSA-N*", "C_add": "OKTJSMMVPCPJKN-UHFFFAOYSA-N*",
             "C4": "KPCJOPHPOHQVQO-UHFFFAOYSA-N*"}
    if set(reaction["components"][0] + reaction["components"][1]) != {*codes.values(), "*"}:
        raise ValueError("original CARE reaction index does not match the source mapping")
    selected = {label: network["species_registry"][code] for label, code in codes.items()}
    mol = {label: molecular_graph(value) for label, value in selected.items()}
    configs = {}
    for label, species in selected.items():
        configs[label] = []
        for key, config in species["ads_configs"].items():
            pose, permutation = owner.care_source_pose(config)
            configs[label].append({"config_id": key, "geometry": geometry(pose, mol[label], owner),
                "geometry_flags_scope": "Temporary care_source_pose flags are all movable by design; they do not represent original ASE constraints.",
                "original_ASE_constraints": config["ase"]["data"]["constraints"],
                                   "grouped_poscar_to_original_ASE_zero_based": permutation})
    local = []
    care_root = args.care_package / "structures/C3H2O/POVFFVOJLQBKHT-UHFFFAOYSA-N/config_2"
    relative = "calculations/fe110_care8_isomers_20260716"
    paths = [("CARE_export_config2", care_root / "POSCAR"),
        ("Fe45_raw", args.project_root / relative / "07_C3H2O_POVFFVOJ_cfg2/POSCAR"),
        ("Fe45_revised", args.project_root / relative / "revised/07_C3H2O_POVFFVOJ_cfg2/POSCAR"),
        ("Fe45_prepared", args.project_root / "calculations/fe110_c3_targeted_relaxation_20261023/screen80_v2/07_C3H2O_POVFFVOJ_cfg2/POSCAR")]
    for label, path in paths:
        bound = bind(path, label + "_POSCAR")
        local.append({"label": label, "path": str(path), "sha256": bound,
                      "geometry": geometry(owner.read_poscar(path), mol["C07"], owner)})
    c4_graph = graph(mol["C4"]["explicit_symbols"], mol["C4"]["explicit_edges"])
    c07_graph = graph(mol["C07"]["explicit_symbols"], mol["C07"]["explicit_edges"])
    matcher = nx.algorithms.isomorphism.GraphMatcher(c4_graph, c07_graph,
        node_match=lambda a, b: a["element"] == b["element"])
    correspondences = []
    for mapping in matcher.subgraph_isomorphisms_iter():
        extra = set(c4_graph) - set(mapping)
        if len(extra) == 1 and mol["C4"]["explicit_symbols"][next(iter(extra))] == "C":
            atom = next(iter(extra))
            correspondences.append({"product_C4_to_C07_mol_index": mapping, "additional_C4_mol_index": atom,
                "additional_atom_neighbors": [{"C4_mol_index": i, "element": c4_graph.nodes[i]["element"]}
                                               for i in c4_graph.neighbors(atom)]})
    parent = json.loads((args.parent_plan_dir / "materialization_receipt.json").read_text(encoding="utf-8"))
    parent_checks = [{"path": r["path"], "expected_sha256": r["sha256"], "unchanged": digest(Path(r["path"])) == r["sha256"]}
                     for r in parent["sources"]]
    save(output / "selected_original_network.json", {"codes": codes, "reaction": reaction, "species": selected,
         "origin": {"network_sha256": records[0]["sha256"], "reaction_pointer": "/reactions/" + str(reaction_index)}})
    save(output / "host_review_observations.json", {"schema_version": 1, "collected_at": datetime.now(timezone.utc).isoformat(),
        "mode": "HOST_READ_ONLY_GRAPH_AND_SOURCE_REVIEW", "original_reaction_row": row,
        "original_reaction_record": {k: reaction.get(k) for k in ["class_name", "r_type", "stoic", "components", "is_atoms", "fs_atoms", "neb_images"]},
        "codes": codes, "molecular_graphs": mol, "CARE_configs": configs, "local_C07_structures": local,
        "C4_C07_graph_correspondences": correspondences, "parent_source_checks": parent_checks,
        "sources": records, "owner_source": {"path": owner.__file__, "sha256": digest(Path(owner.__file__))},
        "runtime": {"python": sys.version, "rdkit": rdkit.__version__, "networkx": nx.__version__},
        "scientific_acceptance": False, "human_adoption": None, "human_review_seconds": None,
        "mapping_scope": "Element/explicit-H connectivity graph correspondence; radical changes at the reaction center are not constrained. No reaction trajectory, TS, energy, atom-map authority or stability acceptance inferred."})
    print(json.dumps({"output": str(output), "C07_local_mapping_counts": [r["geometry"]["mapping_count"] for r in local],
                      "graph_correspondences": correspondences, "source_configs": {k: len(v) for k, v in configs.items()}}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ["project-root", "network", "care-package", "parent-plan-dir", "output-dir"]:
        parser.add_argument("--" + argument, type=Path, required=True)
    main(parser.parse_args())
