"""Species-Gibbs and gas-feed derivatives, limited to hash-bound, reviewed inputs."""

from copy import deepcopy
from math import exp, fsum, isclose
from pathlib import Path

from scripts.artifact_io import load_json_object as read, sha256_file, sha256_json
from scripts.baseline_mkm.pressure_perturbation import checked_feed
from scripts.baseline_mkm.ts_perturbation import PARENT, reproduce as reproduce_parent, reviewed_reaction
from scripts.kinetic_parameters.engine import calculate, check_version, conditions
from scripts.kinetic_parameters.export_contract import validate_export
from scripts.scientific_validation import finite_number

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "reports/multiphase/phase3_0"
THERMO = ROOT / "tests/fixtures/multiphase/closed_cycle_reference.json"
FIXED_OTHERS = "fixed_other_partial_pressures"
FIXED_TOTAL = "fixed_total_proportional_remainder"


def baseline_config():
    path = BASE / "workflow_configuration.json"
    if sha256_file(path) != read(BASE / "benchmark_manifest.json")["input_hashes"]["configuration"]:
        raise ValueError("Changed accepted baseline configuration")
    return read(path)


def pressure_feed(registered, feed, total_bar, sid, log_shift, constraint):
    if set(feed) != set(registered) or sid not in registered:
        raise ValueError("All and only registered gas partial pressures are required")
    for value in feed.values():
        finite_number(value, "partial pressure", nonnegative=True)
    total = finite_number(total_bar, "total pressure", positive=True)
    if not isclose(fsum(feed.values()), total, rel_tol=1e-12, abs_tol=0):
        raise ValueError("Partial pressures do not sum to the declared total")
    before = finite_number(feed[sid], "selected partial pressure", positive=True)
    after = finite_number(before * exp(finite_number(log_shift, "log pressure displacement")), "perturbed pressure", positive=True)
    result = feed.copy()
    if constraint == FIXED_TOTAL:
        if not before < total or not after < total:
            raise ValueError("Fixed-total composition requires a positive remaining gas fraction")
        factor = (total - after) / (total - before)
        result = {s: p * factor for s, p in feed.items()}
    elif constraint != FIXED_OTHERS:
        raise ValueError("Unknown feed constraint")
    result[sid] = after
    new_total = fsum(result.values())
    if constraint == FIXED_TOTAL:
        if not isclose(new_total, total, rel_tol=1e-12):
            raise ValueError("Invalid pressure normalization")
        new_total = total
    return result, new_total


def checked_thermo(network):
    digest = sha256_file(THERMO)
    if not any(a["file"] == THERMO.name and a["sha256"] == digest for a in network["source_artifacts"]):
        raise ValueError("Missing reviewed species formation Gibbs evidence")
    return read(THERMO), digest


def intermediate_identity(network, parent, sid, thermo):
    species = next((s for s in network["species"] if s["species_id"] == sid), None)
    if not species or species["phase"] != "surface":
        raise ValueError("A registered surface intermediate is required")
    if species["validation"]["status"] != "accepted" or species["thermochemistry_status"] != "reviewed":
        raise ValueError("Missing reviewed species thermochemistry")
    bound = [s for s in parent["species"] if s["species_id"] == sid]
    if not species.get("structure_id") or bound != [species]:
        raise ValueError("Species identity differs from the reviewed kinetic dataset")
    sites = {s["site_id"]: s for s in network["catalog"]["sites"]}
    footprint = species["site_occupancy"]
    if not footprint or any(
        k not in sites
        or sites[k]["surface_id"] not in species["surface_ids"]
        or sites[k]["validation"]["status"] != "accepted"
        or type(v) is not int
        or v < 1
        for k, v in footprint.items()
    ):
        raise ValueError("Unconfirmed site inventory")
    value = finite_number(thermo["formation_G_eV"].get(sid), "reviewed formation Gibbs energy")
    linked = [r for r in parent["reactions"] if any(sid in r["direction"]["forward"][key] for key in ("reactants", "products"))]
    if not linked:
        raise ValueError("No connected reactions")
    basis = {
        (r["parameter_set"]["energy_reference_id"], r["parameter_set"]["standard_state_id"], r["parameter_set"]["temperature_K"])
        for r in linked
    }
    if len(basis) != 1 or next(iter(basis))[2] != thermo["temperature_K"]:
        raise ValueError("Incompatible Gibbs references, temperatures or standard states")
    ref, standard, temp = next(iter(basis))
    phases = {s["surface_id"]: s["phase_id"] for s in network["catalog"]["surfaces"]}
    return dict(
        species_id=sid,
        structure_id=species["structure_id"],
        surface_ids=species["surface_ids"],
        phase_ids=[phases[s] for s in species["surface_ids"]],
        site_occupancy=footprint,
        formation_G_eV=value,
        reference=ref,
        standard_state=standard,
        temperature_K=temp,
        connected=[r["reaction_id"] for r in linked],
    )


def shift_intermediate(network, parent, child, sid, shift):
    thermo, source_hash = checked_thermo(network)
    identity = intermediate_identity(network, parent, sid, thermo)
    species = {s["species_id"]: s for s in network["species"]}
    changed = {}
    for rid in identity["connected"]:
        entry, row = reviewed_reaction(network, child, rid)
        law = row["direction"]["forward"]
        ends = [fsum(thermo["formation_G_eV"][s] * n for s, n in law[k].items()) for k in ("reactants", "products")]
        ts = finite_number(thermo["transition_state_G_eV"].get(rid), "absolute TS Gibbs energy")
        g = row["energies"]["gibbs_ev"]
        if not all(
            isclose(g[k], x, abs_tol=1e-10)
            for k, x in zip(("forward", "reverse", "reaction"), (ts - ends[0], ts - ends[1], ends[1] - ends[0]))
        ):
            raise ValueError(f"{rid}: formation/TS energies do not reproduce reviewed barriers")
        initial, final = (law[k].get(sid, 0) * shift for k in ("reactants", "products"))
        before = g.copy()
        g.update(forward=g["forward"] - initial, reverse=g["reverse"] - final, reaction=g["reaction"] + final - initial)
        param = row["parameter_set"]
        for direction in ("forward", "reverse"):
            param[direction]["activation_energy"]["value"] = g[direction]
        rates, equilibrium, correction = calculate(dict(entry, energies=row["energies"]), param, row["model"], species)
        for direction, rate in rates.items():
            row["rates"][direction].update(rate)
        row.update(equilibrium=equilibrium, coverage_shift_ev=correction)
        changed[rid] = dict(parent_gibbs_eV=before, derived_gibbs_eV=g.copy(), absolute_TS_G_eV=ts)
    # Species structural identity remains bound to the immutable network fingerprint.
    child["species_formation_G_eV"] = dict(thermo["formation_G_eV"])
    child["species_formation_G_eV"][sid] += shift
    return dict(
        identity=identity, derived_formation_G_eV=child["species_formation_G_eV"][sid], affected=changed, thermochemistry_sha256=source_hash
    )


def shift_pressure(network, child, config, sid, shift, constraint):
    gases = {s["species_id"] for s in network["species"] if s["phase"] == "gas"}
    rows = child["reactions"]
    total = rows[0]["parameter_set"]["pressure_Pa"] / 100000
    if "total_pressure_bar" in config and not isclose(config["total_pressure_bar"], total, rel_tol=1e-12):
        raise ValueError("Declared total differs from reviewed kinetics")
    feed, new_total = pressure_feed(gases, config["partial_pressure_bar"], total, sid, shift, constraint)
    entries = {r["definition"]["reaction_id"]: r for r in network["reactions"]}
    for r in rows:
        p = r["parameter_set"]
        if p["pressure_Pa"] != total * 100000:
            raise ValueError("Inconsistent baseline total pressure")
        if new_total != total:
            p["pressure_Pa"] = new_total * 100000
        conditions(entries[r["reaction_id"]], p, r["model"])
    return dict(
        parent_feed_bar=config["partial_pressure_bar"], feed_bar=feed, parent_total_bar=total, total_bar=new_total, constraint=constraint
    )


def derive(network, parent, config, spec, sign):
    check_version(network, "network_version")
    validate_export(parent)
    if (
        parent["dataset_version"] != PARENT
        or parent["network_version"] != network["network_version"]
        or config["dataset_version"] != PARENT
        or type(sign) is not int
        or sign not in (-1, 1)
    ):
        raise ValueError("Expected the accepted parent, matching network and signed displacement")
    child = deepcopy(parent)
    sid, kind = spec["species_id"], spec["kind"]
    shift = sign * finite_number(spec["step"], "finite-difference step", positive=True)
    if kind == "intermediate_G":
        details = shift_intermediate(network, parent, child, sid, shift)
    elif kind == "gas_order":
        details = shift_pressure(network, child, config, sid, shift, spec["constraint"])
        if "composition_grid" in spec:
            if spec["constraint"] != FIXED_TOTAL:
                raise ValueError("Explicit composition grid requires fixed total pressure")
            feed = spec["composition_grid"]["plus" if sign == 1 else "minus"]
            actual = checked_feed(details["parent_feed_bar"], feed, sid, details["total_bar"])
            if actual * sign <= 0:
                raise ValueError("Composition grid direction differs from the signed plan")
            details.update(original_target_bar=details["feed_bar"], feed_bar=feed, intended_log_step=actual)
    else:
        raise ValueError("Unknown sensitivity observable")
    child["sensitivity_perturbation"] = dict(spec=spec, sign=sign, parent_dataset=PARENT, **details)
    del child["dataset_version"]
    child = dict(dataset_version=sha256_json(child), **child)
    return child, configuration(config, child)


def configuration(base, dataset):
    data = dataset["sensitivity_perturbation"]
    result = dict(base, dataset_version=dataset["dataset_version"])
    if data["spec"]["kind"] == "gas_order":
        result.update(partial_pressure_bar=data["feed_bar"], total_pressure_bar=data["total_bar"])
    return result


def reproduce(network, dataset):
    parent = reproduce_parent(network, dataset)
    if "coverage_iteration" in dataset:
        from scripts.baseline_mkm.coverage_energy import reconstruct_child
        return reconstruct_child(network, parent, dataset["coverage_iteration"])
    if "sensitivity_perturbation" not in dataset:
        return parent
    request = dataset["sensitivity_perturbation"]
    return derive(network, parent, baseline_config(), request["spec"], request["sign"])[0]
