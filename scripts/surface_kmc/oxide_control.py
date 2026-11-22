"""Offline renderer for the isolated seven-site CO2 software control."""
import argparse
import json
from pathlib import Path

from scripts.artifact_io import sha256_bytes
from scripts.multiphase_contracts import _unique_keys
from scripts.scientific_validation import finite_number
from scripts.surface_kmc.native import pattern_header, slots


def checked_number(values, key, **bounds):
    value = values[key]
    if type(value) not in (int, float):
        raise ValueError(f"{key} requires a JSON number")
    # A Zacros R8 token needs a decimal point or an exponent; str(int) has neither.
    number = finite_number(value, key, **bounds)
    if number != value:
        raise ValueError(f"{key} cannot be represented exactly as a native real")
    return number


def cluster_lines(graph, energies):
    inventories = graph["leg_inventories"]
    species = graph["bridge_species_id"]
    clusters = [
        ("acid_vacancy", inventories[:1], [], [None], checked_number(energies, "empty_acid_eV")),
        ("oxygen_vacancy", inventories[1:], [], [None], checked_number(energies, "empty_oxygen_eV")),
        ("ordered_bridge", inventories, [(0, 1)], [(species, 1)] * 2, checked_number(energies, "bridge_eV_per_molecule")),
    ]
    if checked_number(energies, "intermolecular_lateral_interactions_eV") != 0:
        raise ValueError("The oxide control defines only single-entity clusters")
    if type(energies["graph_multiplicity"]) is not int or energies["graph_multiplicity"] != 1:
        raise ValueError("Ordered single-entity clusters require multiplicity one")
    names = {species: graph["bridge_alias"] + "*"}
    lines = []
    for name, sites, edges, state, energy in clusters:
        lines.extend([f"cluster {name}", *pattern_header(sites, edges, graph["site_aliases"]),
                      "lattice_state", *slots(state, names), f"graph_multiplicity {energies['graph_multiplicity']}",
                      f"cluster_eng {energy}", "end_cluster"])
    return "\n".join(lines)


def structural_members(prior, root):
    sources = {}
    for key in ("manifest", "mapping", "graph"):
        raw = (root / prior[key]).read_bytes()
        if sha256_bytes(raw) != prior[key + "_sha256"]:
            raise ValueError(f"Structural source changed: {key}")
        sources[key] = json.loads(raw, object_pairs_hook=_unique_keys)
    manifest = sources["manifest"]
    files = {}
    source = root / prior["manifest"]
    for name, expected in manifest["files_sha256"].items():
        raw = (source.parent / name).read_bytes()
        if sha256_bytes(raw) != expected:
            raise ValueError(f"Structural input changed: {name}")
        files[name] = raw
    return sources["graph"], manifest, files


def render(control_path, root):
    control_bytes = control_path.read_bytes()
    c = json.loads(control_bytes, object_pairs_hook=_unique_keys)
    if (c["dataset_id"] != "synthetic_oxide_zacros_control_v1" or c["eligible_for_production"] is not False
            or c["scope"] != "synthetic_software_control_only"):
        raise ValueError("Expected isolated synthetic oxide control v1")
    execution = c["execution"]
    expected = {"random_seed": 23123, "max_steps": 0, "native_wall_seconds": 15,
                "external_timeout_seconds": 30, "maximum_processes": 1, "maximum_threads": 1, "retries": 0}
    if execution != expected or any(type(value) is not int for value in execution.values()):
        raise ValueError("Runtime controls differ from the zero-event benchmark")
    prior = c["archived_structure"]
    graph, manifest, files = structural_members(prior, root)

    conditions, gas, energy = c["conditions"], c["gas"], c["energetics"]
    temperature = checked_number(conditions, "temperature_K", positive=True)
    pressure = checked_number(conditions, "total_pressure_bar", positive=True)
    fraction = checked_number(conditions, "CO2_mole_fraction", positive=True)
    mass = checked_number(gas, "molecular_weight_amu", positive=True)
    gas_energy = checked_number(gas, "reference_energy_eV")
    proximity = checked_number(energy, "proximity_factor", nonnegative=True)
    if gas["species"] != graph["gas_alias"] or proximity > 1 or fraction > 1:
        raise ValueError("Invalid gas identity, composition or proximity factor")
    if checked_number(conditions, "CO2_partial_pressure_bar", positive=True) != pressure * fraction:
        raise ValueError("CO2 partial pressure differs from total pressure times mole fraction")
    replacements = {
        "TEMPERATURE_K": temperature, "TOTAL_PRESSURE_BAR": pressure,
        "GAS_MOLAR_MASS": mass, "GAS_MOLE_FRACTION": fraction,
        "REVIEWED_CLUSTER_BLOCKS": cluster_lines(graph, energy),
    }
    for name, unit, coefficient in [("adsorption", "bar^-1 s^-1", -1), ("desorption", "s^-1", 1)]:
        event = c["events"][name]
        stoichiometry = event["CO2_gas_stoichiometry"]
        if event["unit"] != unit or type(stoichiometry) is not int or stoichiometry != coefficient:
            raise ValueError(f"Invalid native gas order or prefactor unit for {name}")
        replacements[f"{name.upper()}_PRE_EXPON"] = checked_number(event, "pre_expon", positive=True)
        replacements[f"{name.upper()}_EA_EV"] = checked_number(event, "activation_energy_eV", nonnegative=True)
    for name in manifest["templates_require_binding"]:
        text = files.pop(name).decode("utf-8")
        for key, value in replacements.items():
            text = text.replace(f"@{key}@", str(value))
        if "@" in text:
            raise ValueError(f"Unbound field in {name}")
        if name == "simulation_input.dat.in":
            text = text.replace("gas_molec_weights ", f"gas_energies {gas_energy}\ngas_molec_weights ")
        if name == "mechanism_input.dat.in":
            text = text.replace("\nend_step", f"\nprox_factor {proximity}\nend_step")
        files[name.removesuffix(".in")] = text.encode("utf-8")

    result = {
        "dataset_id": c["dataset_id"], "scope": c["scope"], "engine": "Zacros 4.0",
        "control_sha256": sha256_bytes(control_bytes),
        "structural_manifest_sha256": prior["manifest_sha256"], "graph_sha256": prior["graph_sha256"],
        "mapping_sha256": prior["mapping_sha256"], "files_sha256": {
            name: sha256_bytes(raw) for name, raw in sorted(files.items())
        },
    }
    return files, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control", type=Path)
    parser.add_argument("new_directory", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    files, manifest = render(args.control, args.root)
    args.new_directory.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        (args.new_directory / name).write_bytes(raw)
    (args.new_directory / "input_manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode())


if __name__ == "__main__":
    main()
