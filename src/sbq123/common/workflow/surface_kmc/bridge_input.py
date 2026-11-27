"""Materialize the structural parts of a reviewed finite-lattice candidate, offline."""
import argparse
import json
from pathlib import Path

from scripts.artifact_io import sha256_bytes
from scripts.multiphase_contracts import _unique_keys
from scripts.surface_kmc.bridge_topology import read_audit


def _text(lines):
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_candidate(graph_path, mapping_path, root):
    """Bind rendered bytes to the source graph, its two sources and the archived mapping."""
    # The topology matcher uses tuples for edges. Keep the manifest JSON-native in memory too.
    audit = json.loads(json.dumps(read_audit(graph_path, root), allow_nan=False))
    mapping = mapping_path.read_bytes()
    if json.loads(mapping, object_pairs_hook=_unique_keys) != audit:
        raise ValueError("Archived mapping differs from the independently rebuilt graph audit")

    candidate = audit["zacros_candidate"]
    surface = candidate["surface_species"]
    mechanism = ["mechanism"]
    for name, key in (("adsorption", "adsorption"), ("desorption", "desorption_pattern")):
        event = candidate[key]
        gas, coefficient = event["gas_reacs_prods"]
        mechanism.extend([
            f"step {name}", *candidate["event_header"], f"gas_reacs_prods {gas} {coefficient}",
            "initial", *event["initial"], "final", *event["final"],
            f"pre_expon @{name.upper()}_PRE_EXPON@", f"activ_eng @{name.upper()}_EA_EV@", "end_step",
        ])
    files = {
        "lattice_input.dat": _text(candidate["lattice_input_lines"]),
        "state_input.dat": _text(candidate["state_input_lines"]),
        "mechanism_input.dat.in": _text([*mechanism, "end_mechanism"]),
        "simulation_input.dat.in": _text([
            "random_seed 23123", "temperature @TEMPERATURE_K@", "pressure @TOTAL_PRESSURE_BAR@",
            "n_gas_species 1", f"gas_specs_names {candidate['gas_species']}",
            "gas_molec_weights @GAS_MOLAR_MASS@", "gas_molar_fracs @GAS_MOLE_FRACTION@",
            "n_surf_species 1", f"surf_specs_names {surface['surf_specs_names']}",
            f"surf_specs_dent {surface['surf_specs_dent']}", "debug_report_processes",
            "max_steps 0", "wall_time 15", "finish",
        ]),
        "energetics_input.dat.in": _text(["energetics", "@REVIEWED_CLUSTER_BLOCKS@", "end_energetics"]),
    }
    manifest = {
        "format": "zacros-4.0-bridge-structural-candidate/1",
        "native_run_eligible": False,
        "graph_sha256": audit["graph_sha256"],
        "mapping_sha256": sha256_bytes(mapping),
        "sources": audit["sources"],
        "source_reversible": candidate["source_reversible"],
        "ordered_seed_nodes_by_entity": audit["initial_bridges"],
        "complete_native_members": ["lattice_input.dat", "state_input.dat"],
        "templates_require_binding": sorted(name for name in files if name.endswith(".in")),
        "files_sha256": {name: sha256_bytes(data) for name, data in sorted(files.items())},
    }
    return files, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path)
    parser.add_argument("mapping", type=Path)
    parser.add_argument("output", type=Path, help="new empty destination to create")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="root of graph source bindings")
    args = parser.parse_args()
    files, manifest = build_candidate(args.graph, args.mapping, args.root)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        (args.output / name).write_bytes(raw)
    (args.output / "input_manifest.json").write_bytes(_text([json.dumps(manifest, allow_nan=False, indent=2)]))


if __name__ == "__main__":
    main()
