"""Translate release-qualified elementary mass action to a Cantera 3.2 mechanism."""

from dataclasses import dataclass
import hashlib
from importlib.resources import files
import json
import math

import cantera as ct
import numpy as np
import yaml

from sbq123.common.evidence.registry import entry, model_record
from sbq123.common.kinetic_model.contracts import GAS_CONSTANT, Model, number
from ._trust import COMPANION_SHA256


@dataclass
class Mechanism:
    """Fresh Cantera phases and their audited SI-to-kmol rate conversion."""

    model: Model
    text: str
    gas: ct.Solution
    surfaces: tuple
    factor: float
    area_per_volume: float
    groups: list
    companion: dict

    def fresh(self, *, flow_guard=False):
        gas = ct.Solution(yaml=self.text, name="gas")
        if flow_guard:
            # FlowReactor 3.2.0 uses the last gas wall source in evalDae.
            # At surface steady state the summed wall mass flux is zero.
            # Append an unpopulated, nonreacting coordinate with that exact flux.
            record = dict(gas.species(0).input_data)
            record["name"] = "SBQ-inert-coordinate"
            gas.add_species(ct.Species.from_dict(record))
        surfaces = tuple(ct.Interface(yaml=self.text, name=s.name, adjacent=[gas]) for s in self.surfaces)
        return gas, surfaces

    def signed_rates(self, gas, surfaces):
        rates = gas.net_production_rates * 1000
        for surface in surfaces:
            rates += surface.get_net_production_rates(gas) * self.area_per_volume * 1000
        return rates


def _record(key):
    raw = files("sbq123.reactor").joinpath("registries", "mechanisms.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != COMPANION_SHA256:
        raise ValueError("Thermodynamic companion identity mismatch")
    doc = json.loads(raw)
    if doc["schema_version"] != 1 or not isinstance(key, str):
        raise ValueError("No qualified thermodynamics and mechanism companion for this dataset")
    from sbq123.common.evidence.trust import project_document
    record = project_document("thermo_companion", key) if key not in doc["records"] else None
    external = record is not None
    if external:
        rec, companion_digest = record
    else:
        rec = doc["records"].get(key)
        if rec is None:
            raise ValueError("No qualified thermodynamics and mechanism companion for this dataset")
        companion_digest = COMPANION_SHA256
    required = {"scope", "model_sha256", "thermo", "site_geometry", "element_weights_kg_kmol", "reference_pressure_Pa", "reversible_pairs"}
    if not isinstance(rec, dict) or set(rec) not in (required, required | {"control_model"}):
        raise ValueError("Malformed mechanism companion")
    if not isinstance(rec["thermo"], dict) or not isinstance(rec["element_weights_kg_kmol"], dict):
        raise ValueError("Invalid species or element table")
    if not isinstance(rec["scope"], str) or not rec["scope"].strip() or external and "control_model" in rec:
        raise ValueError("Unsupported companion qualification")
    raw_model = rec.get("control_model")
    if raw_model is None:
        registered = model_record(key)
        if registered["scope"] != rec["scope"] or registered["sha256"] != rec["model_sha256"]:
            raise ValueError("Companion and kinetic dataset qualification differ")
        raw_model = registered["model"]
    return dict(rec, companion_sha256=companion_digest), raw_model


def _side(names, amounts):
    return " + ".join((str(v) + " " if v != 1 else "") + n for n, v in zip(names, amounts) if v)


def mechanism(
    dataset_id: str,
    *,
    volume_m3: float,
    catalyst_loading_kg: float | None = None,
    catalyst: str | None = None,
    conversion_id: str | None = None,
) -> Mechanism:
    """Build private phase objects from installed input identities. All external amounts are mol, m, kg, s."""
    if ct.__version__ != "3.2.0":
        raise ValueError("This adapter requires Cantera 3.2.0")
    volume = number(volume_m3, "reactor volume", positive=True)
    rec, raw = _record(dataset_id)
    model = Model._from_verified_record(raw, registered_digest=rec["model_sha256"], provenance=rec["scope"])
    gamma, area_v, factor = _basis(model, rec, volume, catalyst_loading_kg, catalyst, conversion_id)
    names = list(model.species + model.sites)
    gas_names = [n for n, phase in zip(model.species, model.phases) if phase == "gas"]
    if set(rec["thermo"]) != set(names):
        raise ValueError("Incomplete thermodynamics")
    species = []
    for i, name in enumerate(names):
        th = rec["thermo"][name]
        if set(th) != {"T0_K", "h0_J_mol", "s0_J_mol_K", "cp_J_mol_K"}:
            raise ValueError("Unsupported or incomplete thermodynamic record")
        source = raw["species"][i] if i < len(model.species) else {"elements": {}, "charge": 0, "sites": {}}
        if source["charge"]:
            raise ValueError("Charged Cantera phases require a separately qualified electrochemical standard state")
        spec = dict(
            name=name,
            composition=source["elements"],
            thermo={
                "model": "constant-cp",
                "reference-pressure": number(rec["reference_pressure_Pa"], "standard pressure", positive=True),
                "T0": number(th["T0_K"], "thermo T0", positive=True),
                "h0": 1000 * number(th["h0_J_mol"], "h0"),
                "s0": 1000 * number(th["s0_J_mol_K"], "s0"),
                "cp0": 1000 * number(th["cp_J_mol_K"], "cp", positive=True),
            },
        )
        if source["sites"]:
            spec["sites"] = sum(source["sites"].values())
        species.append(spec)
    elements = list(rec["element_weights_kg_kmol"])
    if set(elements) != {e for s in raw["species"] for e in s["elements"]}:
        raise ValueError("Missing elemental mass")
    gas_phase = {
        "name": "gas",
        "thermo": "ideal-gas",
        "kinetics": "gas",
        "elements": elements,
        "species": gas_names,
        "reactions": "none",
        "state": {"T": model.reference_temperature_K, "P": 101325},
    }
    doc = {
        "units": {"length": "m", "quantity": "kmol", "time": "s", "activation-energy": "J/kmol"},
        "elements": [{"symbol": e, "atomic-weight": number(rec["element_weights_kg_kmol"][e], e, positive=True)} for e in elements],
        "phases": [gas_phase],
        "species": species,
    }
    surface_owner = {}
    for k, site in enumerate(model.sites, start=1):
        members = [site]
        for name, occ in zip(model.species, model.occupancy):
            if occ[k - 1]:
                if sum(v > 0 for v in occ) > 1:
                    raise ValueError("An adsorbate spanning site families requires coupled site thermodynamics")
                members.append(name)
        surface_owner.update(dict.fromkeys(members, k))
        doc["phases"].append(dict(name="surface" if k == 1 else f"surface-{k}", thermo="ideal-surface",
            kinetics="surface", elements=elements, species=members, reactions="none",
            **{"adjacent-phases": ["gas"], "site-density": gamma}))
    groups = _reactions(doc, rec, model, names, gas_names, surface_owner, gamma, factor)
    text = yaml.safe_dump(doc, sort_keys=False)
    gas = ct.Solution(yaml=text, name="gas")
    surfaces = tuple(ct.Interface(yaml=text, name=phase["name"], adjacent=[gas]) for phase in doc["phases"][1:])
    result = Mechanism(model, text, gas, surfaces, factor, area_v, groups, rec)
    return result


def verify_conversion(m: Mechanism, temperature: float, pressure: float) -> float:
    """Compare each forward and reverse rate of progress to independent SBQ123 mass action."""
    model = m.model
    if (
        not model.temperature_domain_K[0] <= temperature <= model.temperature_domain_K[1]
        or not model.pressure_domain_Pa[0] <= pressure <= model.pressure_domain_Pa[1]
    ):
        raise ValueError("Conditions outside the registered kinetic domain")
    worst = 0.0
    for power in (1, -1):
        weights = np.arange(1, m.gas.n_species + 1, dtype=float) ** power
        m.gas.TPX = temperature, pressure, weights
        activities = dict(zip(m.gas.species_names, m.gas.concentrations * 1000))
        for surface in m.surfaces:
            surface.TP = temperature, pressure
            surface.coverages = np.arange(1, surface.n_species + 1, dtype=float) ** power
            activities.update(zip(surface.species_names, surface.concentrations / surface.site_density))
        for surf, index, forward, reverse in m.groups:
            phase = m.surfaces[surf - 1] if surf else m.gas
            unit = phase.site_density if surf else m.factor / 1000
            for k, array in ((forward, phase.forward_rates_of_progress), (reverse, phase.reverse_rates_of_progress)):
                if k is None:
                    continue
                step = model.steps[k]
                expected = step.coefficient * math.exp(
                    -step.activation_J_mol / GAS_CONSTANT * (1 / temperature - 1 / model.reference_temperature_K)
                )
                expected *= math.prod(activities[n] ** o for n, o in zip(model.species + model.sites, step.orders))
                actual = float(array[index] / unit)
                error = abs(actual - expected) / max(abs(expected), np.finfo(float).tiny)
                if not math.isfinite(error) or error > 1e-9:
                    raise ValueError("Cantera forward/reverse rate differs from the registered model")
                worst = max(worst, error)
    return worst


def _basis(model, rec, volume, catalyst_loading_kg, catalyst, conversion_id):
    mass = None if catalyst_loading_kg is None else number(catalyst_loading_kg, "catalyst loading", positive=True)
    gamma, area_v, factor = 0.0, 0.0, 1.0
    if model.rate_basis == "mol_per_mol_site_s":
        geometry = rec["site_geometry"]
        if not geometry or mass is None or not model.sites:
            raise ValueError("Reviewed reference density, catalyst area and loading are required")
        profile = entry("catalysts", catalyst)
        if catalyst != geometry["catalyst"] or conversion_id != geometry["conversion_id"] or conversion_id not in profile["conversion_ids"]:
            raise ValueError("Unqualified catalyst or conversion")
        approved = entry("basis_conversions", conversion_id)
        density = number(geometry["mol_sites_per_m2"], "site density", positive=True)
        if len(model.sites) > 1:
            densities = geometry.get("site_densities_mol_m2", {})
            if set(densities) != set(model.sites) or any(number(v, "site density", positive=True) != density for v in densities.values()):
                raise ValueError("This reference requires one of each site per reference unit")
        specific = number(geometry["m2_per_kg"], "specific area", positive=True)
        if (
            approved["model_sha256"] != model.digest
            or approved["scope"] != model.provenance
            or profile["scope"] != model.provenance
            or not math.isclose(density * specific, approved["mol_sites_per_kg"], rel_tol=1e-12)
        ):
            raise ValueError("Conversion approval scope or surface basis mismatch")
        gamma, area_v = density / 1000, specific * (mass / volume)
        factor = density * area_v
    else:
        if catalyst is not None or conversion_id is not None:
            raise ValueError("Catalyst identity and site conversion apply only to qualified site-based coefficients")
        if model.rate_basis == "mol_per_kg_catalyst_s":
            if mass is None:
                raise ValueError("A positive catalyst loading is required")
            factor = mass / volume
        elif mass is not None:
            raise ValueError("Volumetric coefficients already contain the catalyst basis")
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError("Kinetic normalization outside floating-point domain")
    return gamma, area_v, factor


def _reactions(doc, rec, model, names, gas_names, surface_names, gamma, factor):
    pairs = dict(rec["reversible_pairs"])
    groups = []
    for i, step in enumerate(model.steps):
        if i in pairs.values():
            continue
        left = list(step.orders)
        net = list(step.net) + [-sum(n * occ[k] for n, occ in zip(step.net, model.occupancy)) for k in range(len(model.sites))]
        right = [n + s for n, s in zip(left, net)]
        if min(right) < 0 or not any(left) or not any(right):
            raise ValueError("Unsupported non-elementary reaction")
        rev = pairs.get(i)
        if rev is not None and (model.steps[rev].orders != tuple(right) or model.steps[rev].net != tuple(-n for n in step.net)):
            raise ValueError("Inconsistent elementary reverse step")
        owners = {surface_names[n] for n, a, b in zip(names, left, right) if (a or b) and n in surface_names}
        if len(owners) > 1:
            raise ValueError("Coupled elementary step spans independently normalized Cantera phases")
        surf = next(iter(owners), 0)
        ng = sum(n for name, n in zip(names, left) if name in gas_names)
        ns = sum(left) - ng
        coefficient = (gamma ** (1 - ns) if surf else factor / 1000) * 1000**ng
        A = step.coefficient * coefficient * math.exp(step.activation_J_mol / (GAS_CONSTANT * model.reference_temperature_K))
        key = doc["phases"][surf]["name"] + "-reactions"
        index = len(doc.setdefault(key, []))
        doc[key].append(
            {
                "equation": _side(names, left) + (" <=> " if rev is not None else " => ") + _side(names, right),
                "rate-constant": {"A": A, "b": 0.0, "Ea": 1000 * step.activation_J_mol},
            }
        )
        doc["phases"][surf]["reactions"] = [key]
        groups.append((surf, index, i, rev))
    return groups
