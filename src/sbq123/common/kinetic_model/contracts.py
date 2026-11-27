"""Ideal-gas, isothermal mass action. SI concentrations are mol/m³."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math

GAS_CONSTANT = 8.31446261815324


def identity(value):
    try:
        data = json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Expected a finite JSON value") from exc
    return sha256(data).hexdigest()


def number(value, field, *, positive=False, nonnegative=False):
    try:
        finite = type(value) in (float, int) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{field} must be a finite JSON number")
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError(f"{field} outside its physical range")
    return float(value)


def integer(value, field):
    if type(value) is not int:
        raise ValueError(f"{field} must be a JSON integer")
    return value


@dataclass(frozen=True)
class Step:
    net: tuple
    orders: tuple
    coefficient: float
    activation_J_mol: float


@dataclass(frozen=True)
class Model:
    digest: str
    species: tuple
    phases: tuple
    steps: tuple
    sites: tuple
    occupancy: tuple
    rate_basis: str
    reference_temperature_K: float
    temperature_domain_K: tuple
    pressure_domain_Pa: tuple
    provenance: str

    @classmethod
    def _from_verified_record(cls, raw, *, registered_digest, provenance):
        """The caller of this internal parser must get its pin from the installed registry."""
        if not isinstance(raw, dict) or identity(raw) != registered_digest:
            raise ValueError("Unregistered kinetic dataset")
        keys = {
            "schema_version",
            "species",
            "sites",
            "steps",
            "rate_basis",
            "reference_temperature_K",
            "temperature_domain_K",
            "pressure_domain_Pa",
        }
        if set(raw) != keys or type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
            raise ValueError("Invalid kinetic dataset schema")
        basis = raw["rate_basis"]
        if basis not in ("mol_per_m3_reactor_s", "mol_per_kg_catalyst_s", "mol_per_mol_site_s"):
            raise ValueError("Unsupported rate basis")
        sites = raw["sites"]
        if not isinstance(sites, list) or not all(isinstance(s, str) and s for s in sites) or len(sites) != len(set(sites)):
            raise ValueError("Invalid site inventory")
        species = raw["species"]
        if not isinstance(species, list) or not species:
            raise ValueError("Missing species")
        names, phases, inventories, occupancy = [], [], [], []
        for row in species:
            if not isinstance(row, dict) or set(row) != {"name", "phase", "elements", "charge", "sites"}:
                raise ValueError("Invalid species record")
            name, phase = row["name"], row["phase"]
            if not isinstance(name, str) or not name or name in names or phase not in ("gas", "surface"):
                raise ValueError("Invalid species identity")
            parts = row["elements"]
            if (
                not isinstance(parts, dict)
                or not parts
                or any(not isinstance(e, str) or not e or e == "charge" or integer(n, e) <= 0 for e, n in parts.items())
            ):
                raise ValueError("Invalid elemental composition")
            occ = row["sites"]
            if not isinstance(occ, dict) or set(occ) - set(sites) or bool(occ) != (phase == "surface"):
                raise ValueError("Invalid occupancy")
            if any(integer(n, "site occupancy") <= 0 for n in occ.values()):
                raise ValueError("Nonpositive site occupancy")
            names.append(name)
            phases.append(phase)
            inventories.append(dict(parts, charge=integer(row["charge"], "charge")))
            occupancy.append(tuple(occ.get(site, 0) for site in sites))
        if "gas" not in phases or set(names) & set(sites):
            raise ValueError("Gas species required and site identities must be distinct")
        components = names + sites
        steps = []
        if not isinstance(raw["steps"], list):
            raise ValueError("Invalid reaction list")
        for step in raw["steps"]:
            if not isinstance(step, dict) or set(step) != {"change", "orders", "coefficient", "activation_J_mol"}:
                raise ValueError("Invalid elementary step")
            change = step["change"]
            orders = step["orders"]
            if (
                not isinstance(change, dict)
                or not change
                or set(change) - set(names)
                or not isinstance(orders, dict)
                or set(orders) - set(components)
            ):
                raise ValueError("Unknown reaction participants")
            net = tuple(integer(change.get(n, 0), "stoichiometry") for n in names)
            order = tuple(integer(orders.get(n, 0), "activity order") for n in components)
            if not any(net) or min(order) < 0 or any(s < 0 and o == 0 for s, o in zip(net, order)):
                raise ValueError("Invalid mass-action orders")
            for element in set().union(*(row.keys() for row in inventories)):
                if sum(n * inv.get(element, 0) for n, inv in zip(net, inventories)):
                    raise ValueError(f"Unbalanced {element}")
            for i, site in enumerate(sites):
                uptake = sum(net[j] * occupancy[j][i] for j in range(len(names)))
                if uptake > order[len(names) + i]:
                    raise ValueError(f"Site-consuming step lacks vacant-site activity for {site}")
            steps.append(
                Step(net, order, number(step["coefficient"], "k", nonnegative=True), number(step["activation_J_mol"], "activation energy"))
            )

        def domain(field):
            vs = raw[field]
            if not isinstance(vs, list) or len(vs) != 2:
                raise ValueError(field)
            lo, hi = [number(v, field, positive=True) for v in vs]
            if lo > hi:
                raise ValueError(field)
            return (lo, hi)

        t = number(raw["reference_temperature_K"], "reference T", positive=True)
        td = domain("temperature_domain_K")
        if not td[0] <= t <= td[1]:
            raise ValueError("Reference temperature outside domain")
        return cls(
            registered_digest,
            tuple(names),
            tuple(phases),
            tuple(steps),
            tuple(sites),
            tuple(occupancy),
            basis,
            t,
            td,
            domain("pressure_domain_Pa"),
            provenance,
        )

    def source(self, concentrations, surfaces, temperature, pressure):
        rates, vacancies, _ = self.production(concentrations, surfaces, temperature, pressure)
        return rates, vacancies

    def production(self, concentrations, surfaces, temperature, pressure):
        """Gas orders use c/(1 mol/m³). Surface species use amount per reference site."""
        if (
            not self.temperature_domain_K[0] <= temperature <= self.temperature_domain_K[1]
            or not self.pressure_domain_Pa[0] <= pressure <= self.pressure_domain_Pa[1]
        ):
            raise ValueError("Local conditions outside kinetic domain")
        if len(concentrations) != self.phases.count("gas") or len(surfaces) != self.phases.count("surface"):
            raise ValueError("Local state vector has incorrect dimensions")
        if any(not math.isfinite(v) or v < 0 for v in concentrations) or any(not math.isfinite(v) for v in surfaces):
            raise ValueError("Invalid local activities")
        gas = iter(concentrations)
        ads = iter(surfaces)
        values = [next(gas) if phase == "gas" else next(ads) for phase in self.phases]
        vacant = [
            1 - sum(v * occ[i] for v, occ, p in zip(values, self.occupancy, self.phases) if p == "surface") for i in range(len(self.sites))
        ]
        rates = [0.0] * len(values)
        turnover = [0.0] * len(values)
        for step in self.steps:
            k = step.coefficient * math.exp(-step.activation_J_mol / GAS_CONSTANT * (1 / temperature - 1 / self.reference_temperature_K))
            progress = k * math.prod(v**o for v, o in zip(values + vacant, step.orders))
            for j, n in enumerate(step.net):
                rates[j] += n * progress
                turnover[j] += abs(n * progress)
        if not all(math.isfinite(v) for v in rates):
            raise ValueError("Nonfinite local rate")
        return rates, vacant, turnover


class RootFailure(ValueError):
    def __init__(self, message, receipt=None):
        super().__init__(message)
        self.receipt = receipt or {"converged": False, "reason": message}
