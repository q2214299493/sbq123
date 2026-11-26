"""Project a hash-bound, replayed Zacros window into a V2.1 result and finite-window observations."""
import argparse
import json
from pathlib import Path

from scripts.artifact_io import sha256_file, sha256_json
from scripts.kinetic_data.native_rate_output import build_output, conditions_pa, require
from scripts.kinetic_data.scientific_identity import read_artifact
from scripts.rate_output_v2 import validate_network_bound_rate_output
from scripts.reaction_network.catalog import catalog, register_species
from scripts.surface_kmc.result_binding import verified_window_series


def _load_manifest(path, expected):
    manifest, digest = read_artifact(path)
    require(digest == expected, "Bridge manifest SHA-256 differs")
    refs = manifest["artifacts"]
    require(manifest["format"] == "kmc-window-sources/1" and
            set(refs) - {"molecular_mapping"} == {"dataset", "configuration", "network", "window"},
            "Incomplete bridge manifest")
    paths = {key: (path.parent / ref["path"]).resolve() for key, ref in refs.items() if key != "molecular_mapping"}
    return refs, paths


def _exit_kind(side, species, mapped):
    """Conservation is necessary for intact desorption. Identity requires a pinned event mapping."""
    if list(side["reactants"].values()) != [1] or list(side["products"].values()) != [1]:
        return "other_loss"
    bound, = side["reactants"]
    final, = side["products"]
    resident, product = species[bound], species[final]
    if not (resident["composition"] and resident["composition"] == product["composition"]
            and resident["charge"] is not None and resident["charge"] == product["charge"]):
        return "other_loss"
    if (resident.get("configuration_id") and product.get("configuration_id")
            and resident["configuration_id"] != product["configuration_id"]):
        return "configuration_change"
    if product["phase"] != "gas":
        return "other_loss"
    return "intact_desorption" if mapped else "unmapped_desorption"


def _exchange(side, species):
    initial, final = side["reactants"], side["products"]
    phases = [{species[s]["phase"] for s in group} for group in (initial, final)]
    if phases == [{"gas"}, {"surface"}]:
        return "adsorption"
    if phases == [{"surface"}, {"gas"}]:
        return "desorption"
    return None


class MolecularMappingError(ValueError):
    """The optional intact-desorption evidence cannot establish molecular fate."""


def _mapping_keys(entries, reactions, species):
    if not isinstance(entries, list):
        raise MolecularMappingError("Molecular mapping intact_desorptions must be a list")
    fields = ("reaction_id", "direction", "surface_species", "gas_species")
    keys = set()
    for i, row in enumerate(entries):
        label = f"Molecular mapping intact_desorptions[{i}]"
        if not isinstance(row, dict):
            raise MolecularMappingError(f"{label} must be an object")
        for field in fields:
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise MolecularMappingError(f"{label}.{field} must be a nonempty string")
        key = tuple(row[field] for field in fields)
        rid, direction, bound, gas = key
        if rid not in reactions or direction not in ("forward", "reverse"):
            raise MolecularMappingError(f"{label} references unknown reaction or direction: {rid}/{direction}")
        side = reactions[rid]["direction"][direction]
        if (not side or bound not in species or gas not in species or species[bound]["phase"] != "surface"
                or side["reactants"] != {bound: 1} or side["products"] != {gas: 1}
                or _exit_kind(side, species, True) != "intact_desorption"):
            raise MolecularMappingError(f"{label} conflicts with the directed molecular event: {key}")
        if key in keys:
            raise MolecularMappingError(f"{label} duplicates a molecular mapping")
        keys.add(key)
    return keys


def _observables(dataset, network, window, intact_desorptions=None):
    idx = catalog(dict(dataset["catalog"], species=dataset["species"], reactions=dataset["reactions"]))
    species = idx["species"]
    # Network-local labels for replay. Cross-result joins verify source records separately.
    require(all(s.get("structural_provenance") for s in species.values()), "Missing network molecular provenance")
    fingerprints = register_species(idx)
    require(species == {s["species_id"]: s for s in network["species"]}, "Incompatible molecular identities")
    # Replay a historical file-only checksum only after exact record equality. All
    # scientific joins and new projections use the selector-bound fingerprints.
    if fingerprints != network["species_fingerprints"]:
        require(register_species(idx, snapshot_v1=True) == network["species_fingerprints"],
                "Incompatible molecular identities")
    obs = window["observation"]
    a, b = obs["window_s"]
    duration = b - a
    exits = {sid: {} for sid in obs["molecules_per_cell"]}
    mapped = _mapping_keys(intact_desorptions, idx["reactions"], species) if intact_desorptions is not None else set()
    verified = set()
    progress, exchange = {}, []
    for row in dataset["reactions"]:
        rid = row["reaction_id"]
        pathway = obs["pathway_flux"][rid]
        rates = dict(net=pathway["net_rate"])
        for direction in ("forward", "reverse"):
            side = row["direction"][direction]
            if side is None:
                rates[direction] = "not_applicable"
                continue
            count = pathway[direction]
            rates[direction] = count / duration
            kind = _exchange(side, species)
            if kind:
                exchange.append(dict(reaction_id=rid, direction=direction, process=kind,
                                     event_count=count, events_per_cell_s=rates[direction]))
                if kind == "desorption":
                    key = (rid, direction, next(iter(side["reactants"])), next(iter(side["products"])))
                    exchange[-1]["molecular_fate"] = _exit_kind(side, species, key in mapped)
            consumed = exits.keys() & side["reactants"].keys()
            for sid in consumed:
                lost = side["reactants"][sid] - side["products"].get(sid, 0)
                if sid in side["products"]:
                    # Counts alone cannot identify a molecule replaced in the same state.
                    exits[sid].setdefault("other_loss", 0)
                if lost <= 0:
                    continue
                key = (rid, direction, sid, next(iter(side["products"]), None))
                channel = _exit_kind(side, species, key in mapped)
                if channel == "intact_desorption":
                    verified.add(key)
                exits[sid][channel] = exits[sid].get(channel, 0) + count * lost
        progress[rid] = rates
    if verified != mapped:
        raise MolecularMappingError("Molecular mapping has no corresponding surface-state exit")
    residence = {}
    for sid, mean in obs["molecules_per_cell"].items():
        exposure = mean * duration
        channels = exits[sid]
        intact = channels.get("intact_desorption", 0)
        total = sum(channels.values())
        reason = ("other_or_unresolved_loss_channel" if "other_loss" in channels else
                  "configuration_changing_exit" if "configuration_change" in channels else
                  "missing_molecular_identity_mapping" if "unmapped_desorption" in channels else
                  "no_observed_molecular_desorption" if not intact else None)
        residence[sid] = dict(molecule_seconds=exposure, state_exits=total, exit_counts=channels,
                              exposure_per_state_exit_s=exposure / total if total else None,
                              molecular_desorptions=intact, estimate_s=None if reason else exposure / intact,
                              unavailable_reason=reason)
    utilization = {}
    for site, occupied in obs["coverage"].items():
        capacity = window["site_capacities"][site]
        require(capacity > 0 and -1e-12 <= occupied <= 1 + 1e-12, "Invalid site utilization")
        utilization[site] = dict(capacity_sites=capacity, occupied_fraction=occupied, vacancy_fraction=1 - occupied)
    return progress, dict(species_fingerprints=fingerprints, mean_molecules_per_cell=obs["molecules_per_cell"],
                          time_weighted_occupied_fraction_by_species=obs["occupied_fraction_by_species"],
                          time_weighted_site_utilization=utilization, directional_exchange=exchange,
                          residence_exposure_over_desorptions=residence)


def _native_sources(window, directory):
    leaf = window["checkpoint_lineage"][-1]
    run = Path(leaf["run"])
    claim, _ = read_artifact(run / "claim.json")
    plan = claim["plan"]
    require(sha256_json(plan) == leaf["plan_sha256"], "Native plan changed")

    def ref(path, expected):
        require(sha256_file(path) == expected, f"Native evidence changed: {path.name}")
        return dict(path=(path.relative_to(directory) if path.is_relative_to(directory) else path).as_posix(),
                    sha256=expected)

    native = []
    for name, digest in plan["inputs"].items():
        folder = Path(plan["lineage"]["run"]) if name == "restart.inf" else run
        native.append(ref(folder / name, digest))
    return native, ref(run / "result.json", leaf["receipt_sha256"]), plan["inputs"]["lattice_input.dat"]


def _read_mapping(directory, ref, network_sha):
    if (not isinstance(ref, dict) or not isinstance(ref.get("path"), str) or not ref["path"].strip()
            or not isinstance(ref.get("sha256"), str)):
        raise MolecularMappingError("Invalid molecular mapping reference: path and sha256 required")
    try:
        document, digest = read_artifact(directory / ref["path"])
    except (OSError, ValueError) as exc:
        raise MolecularMappingError(f"Unreadable molecular mapping: {exc}") from exc
    if (digest != ref["sha256"] or not isinstance(document, dict) or document.get("format") != "kmc-intact-desorptions/1"
            or document.get("network_sha256") != network_sha):
        raise MolecularMappingError("Invalid molecular mapping source, format or network binding")
    if not isinstance(document.get("intact_desorptions"), list):
        raise MolecularMappingError("Molecular mapping intact_desorptions must be a list")
    return document["intact_desorptions"]


def bridge(manifest_path, manifest_sha256, *, allow_partial_mapping=False):
    """Read-only. File references in the returned record resolve relative to the input manifest."""
    path = Path(manifest_path).resolve()
    refs, paths = _load_manifest(path, manifest_sha256)
    window, digest = read_artifact(paths["window"])
    require(digest == refs["window"]["sha256"] and window["format"] == "kmc-window-binding/2",
            "Changed window sidecar or missing approved network identity")
    network, raw = read_artifact(paths["network"])
    for key, expected in (("network", window["reaction_network"]["file_sha256"]),
                          ("dataset", window["dataset"]["file_sha256"]), ("configuration", window["configuration_sha256"])):
        require(refs[key]["sha256"] == expected, f"Manifest differs from bound {key}")
    require(raw == refs["network"]["sha256"], "Changed network bytes")
    run = Path(window["checkpoint_lineage"][-1]["run"])
    series = verified_window_series(window, paths["dataset"], paths["configuration"], run)
    dataset = series["dataset"]
    definition = window["definition"]
    require(definition["basis"] == "simulation_cell" and definition["denominator"] == 1,
            "Expected native whole-cell normalization")
    try:
        mappings = (_read_mapping(path.parent, refs["molecular_mapping"], raw)
                    if "molecular_mapping" in refs else [])
        progress, obs = _observables(dataset, network, window, mappings)
    except MolecularMappingError as exc:
        if not allow_partial_mapping:
            raise
        progress, obs = _observables(dataset, network, window)
        obs["molecular_mapping_error"] = str(exc)
        for values in obs["residence_exposure_over_desorptions"].values():
            values.update(molecular_desorptions=None, estimate_s=None, unavailable_reason=str(exc))
    if "molecular_mapping" in refs:
        obs["molecular_mapping"] = refs["molecular_mapping"]
    inputs, receipt, lattice = _native_sources(window, path.parent)
    c = window["conditions"]
    # V2.1 stores pressure in Pa; retain the native bar-valued conditions in the window.
    conditions = conditions_pa(c["temperature_K"], c["pressure_Pa"] / 100000, c["partial_pressure_bar"])
    basis = dict(basis_kind="simulation_cell", reference_id="lattice-" + lattice,
                 denominator_unit="simulation cell", definition="One entire simulated lattice.")
    rates = build_output(dataset, network, engine=dict(name="Zacros", version="4.0"),
                         run_id=window["result"]["plan_sha256"], conditions=conditions, basis=basis,
                         inputs=inputs, provenance=dict(network=refs["network"], dataset=refs["dataset"],
                                                        native_output=receipt), observations=progress)
    validate_network_bound_rate_output(rates, paths["network"])
    trajectory = series["trajectory"]
    clocks = {k: [trajectory[k][0][1], trajectory[k][-1][1]] for k in ("procstat", "specnum")}
    record = dict(format="kmc-window-integration/1", manifest_sha256=manifest_sha256,
                  window=window, rate_output=rates, observations=obs, sampled_spans_s=clocks,
                  statistics=dict(independent_trajectories=1, effective_sample_size=None, confidence_interval=None,
                                  observed_events=sum(p["forward"] + p["reverse"]
                                                      for p in window["observation"]["pathway_flux"].values()),
                                  scope="one finite window; checkpoint segments share one trajectory"))
    return dict(record, record_sha256=sha256_json(record))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("manifest_sha256")
    args = parser.parse_args()
    print(json.dumps(bridge(args.manifest, args.manifest_sha256), indent=2, allow_nan=False))
