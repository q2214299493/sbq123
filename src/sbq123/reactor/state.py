"""Convert private Cantera states to the SBQ123 molar material-balance contract."""

import cantera as ct
import numpy as np

from sbq123.common.kinetic_model.contracts import RootFailure, number
from .kinetics.source import LocalSource


# Dimensionless resolution for CSTR surface flux imbalance and site fractions.
CSTR_SURFACE_TOL = 1e-8


class Case:
    def __init__(self, mechanism, inputs):
        self.m = mechanism
        self.opts = inputs
        self.names = mechanism.gas.species_names
        self.t = number(inputs["temperature_K"], "temperature", positive=True)
        self.p = number(inputs["pressure_Pa"], "pressure", positive=True)
        self.volume = number(inputs["volume_m3"], "vessel volume", positive=True)
        self.fin = number(inputs["inlet_mol_s"], "molar feed", positive=True)
        if min(self.volume, self.fin) < np.finfo(float).tiny:
            raise ValueError("Flow or volume outside supported floating-point domain")
        comp = inputs["composition"]
        if not isinstance(comp, dict) or set(comp) != set(self.names):
            raise ValueError("Supply every gas mole fraction")
        self.x = np.array([number(comp[n], n, nonnegative=True) for n in self.names])
        if abs(sum(self.x) - 1) > 1e-10:
            raise ValueError("Feed mole fractions must sum to one")
        self.a, self.b = inputs["reactant"], inputs["product"]
        if self.a not in self.names or self.b not in self.names or self.a == self.b or comp[self.a] <= 0:
            raise ValueError("Invalid conversion or selectivity target")
        self.ia, self.ib = self.names.index(self.a), self.names.index(self.b)
        mechanism.gas.TPX = self.t, self.p, self.x
        self.mass_per_mol = mechanism.gas.mean_molecular_weight / 1000
        self.mdot = self.fin * self.mass_per_mol
        self.qin = self.mdot / mechanism.gas.density
        if min(self.qin, self.mdot) <= 0 or not np.isfinite([self.mdot, self.qin, self.volume / self.qin]).all():
            raise ValueError("Inlet state outside floating-point domain")
        self.feed = self.fin * self.x
        mode = inputs["mode"]
        if mode not in ("fixed", "dynamic_mkm") or (mode == "dynamic_mkm" and not mechanism.surfaces):
            raise ValueError("Unsupported kinetic mode for this dataset")
        self.dynamic = mode == "dynamic_mkm"
        self.surface_names = [n for n, p in zip(mechanism.model.species, mechanism.model.phases) if p == "surface"]
        self.occupancy = np.asarray([o for o, p in zip(mechanism.model.occupancy, mechanism.model.phases) if p == "surface"],
                                    dtype=float).reshape((len(self.surface_names), len(mechanism.model.sites)))
        self.coverage = self.checked_coverage(inputs["initial_coverage"])
        self.distance = number(inputs["max_root_distance"], "surface branch distance", positive=True)
        if self.distance > 1:
            raise ValueError("Coverage displacement exceeds one site inventory")

    def checked_coverage(self, raw):
        if not isinstance(raw, (tuple, list)) or len(raw) != len(self.surface_names):
            raise ValueError("Specify one initial amount per registered surface species")
        cov = [number(v, "coverage", nonnegative=True) for v in raw]
        if np.any(np.asarray(cov) @ self.occupancy > 1):
            raise ValueError("Initial coverages exceed the site inventory")
        return cov

    def set_coverages(self, surfaces, amounts):
        vacancies = 1 - np.asarray(amounts) @ self.occupancy
        for k, surf in enumerate(surfaces):
            values = {name: value * count for name, value, count in zip(self.surface_names, amounts, self.occupancy[:,k]) if count}
            values[self.m.model.sites[k]] = max(0, vacancies[k])
            surf.coverages = values

    def phases(self, x, *, flow_guard=False, coverage=None):
        gas, surfaces = self.m.fresh(flow_guard=flow_guard)
        gas.TPX = self.t, self.p, np.append(x, 0.0) if flow_guard else x
        for surf in surfaces:
            surf.TP = gas.TP
        self.set_coverages(surfaces, self.coverage if coverage is None else coverage)
        return gas, surfaces

    def branch(self, gas, coverage=None):
        if not self.dynamic:
            return None
        src = LocalSource(self.m.model, self.m.factor, self.coverage if coverage is None else coverage, self.distance)
        src.evaluate(gas, commit=True)
        return src

    def observe(self, gas, surface, branch, coord, tau, *, commit=False, mdot=None):
        x = gas.X
        if not np.isfinite(x).all() or min(x) < -1e-10 or abs(sum(x) - 1) > 1e-9 or gas.density <= 0:
            raise RootFailure("Nonphysical Cantera state")
        c = np.maximum(gas.concentrations * 1000, 0)
        if min(gas.concentrations) < -1e-10 * sum(abs(gas.concentrations)):
            raise RootFailure("Negative gas concentration")
        cover, receipt = [], None
        if branch:
            rates, receipt = branch.evaluate(gas, commit=commit)
            cover = receipt["coverage"]
        else:
            if surface:
                amounts = {n: v / s.site_density for s in surface for n, v in zip(s.species_names, s.concentrations)}
                cover = [amounts[n] for n in self.surface_names]
            rates = self.m.signed_rates(gas, surface)
        predicted, vacant, traffic = self.m.model.production(c, cover, gas.T, gas.P)
        idx = [i for i, p in enumerate(self.m.model.phases) if p == "gas"]
        gas_traffic = np.array(traffic)[idx] * self.m.factor
        # The two physical unit conversions can erase a nonzero directional
        # rate. A relative error budget below one representable mol/s cannot
        # certify a zero increment, even when the rounded outlet is unchanged.
        smallest_resolved = np.finfo(float).smallest_subnormal / 2e-6
        small = gas_traffic * self.volume < smallest_resolved
        if np.any(small):
            amounts = dict(zip(self.names, c)) | dict(zip(self.surface_names, cover))
            activities = [amounts[n] for n in self.m.model.species] + list(vacant)
            for j in np.flatnonzero(small):
                i = idx[j]
                active = any(step.net[i] and step.coefficient > 0
                             and all(not order or value > 0 for order, value in zip(step.orders, activities))
                             for step in self.m.model.steps)
                if active:
                    raise RootFailure("Nonzero reaction traffic below molar-flow resolution", {
                        "converged": False, "unresolved_species": self.names[j],
                        "minimum_resolved_mol_s": float(smallest_resolved),
                    })
        expected = np.array(predicted)[idx] * self.m.factor
        if not np.all(np.isfinite(rates)) or np.any(abs(rates - expected) > 2e-8 * np.maximum(gas_traffic, 1e-30)):
            raise RootFailure("Local species rates disagree with the registered kinetic model")
        surf_idx = [i for i, p in enumerate(self.m.model.phases) if p == "surface"]
        surface_tol = CSTR_SURFACE_TOL if self.opts["kind"] == "CSTR" else 2e-7
        if surf_idx and (
            min(cover) < -1e-9 or min(vacant) < -1e-9 or any(abs(predicted[i]) > surface_tol * max(traffic[i], 1e-20) for i in surf_idx)
        ):
            raise RootFailure("Surface inventory or local steady balance failed")
        outlet_mdot = self.mdot if mdot is None else mdot
        flow = outlet_mdot / gas.mean_molecular_weight * 1000 * x
        atoms = np.array([[gas.n_atoms(k, e) for k in self.names] for e in gas.element_names])
        elemental = atoms @ (flow - self.feed)
        if np.any(abs(elemental) > 2e-7 * self.fin * np.maximum(1, atoms @ self.x)):
            raise RootFailure("Element flow is not conserved")
        # Use elementary one-way stoichiometry, including the reverse direction
        # and species that occur on both sides of an autocatalytic reaction.
        rate_gas, rate_surface = gas, surface
        if branch:
            rate_gas, rate_surface = self.m.gas, self.m.surfaces
            rate_gas.TPX = gas.T, gas.P, x
            for s in rate_surface:
                s.TP = rate_gas.TP
            self.set_coverages(rate_surface, cover)
        created = rate_gas.creation_rates * 1000
        destroyed = rate_gas.destruction_rates * 1000
        for s in rate_surface or ():
            area_factor = 1000 * self.m.area_per_volume
            created += area_factor * s.get_creation_rates(rate_gas)
            destroyed += area_factor * s.get_destruction_rates(rate_gas)
        return dict(
            coordinate=float(coord),
            residence_time_s=float(tau),
            temperature_K=float(gas.T),
            pressure_Pa=float(gas.P),
            volumetric_flow_m3_s=float(outlet_mdot / gas.density),
            amount_or_flow=dict(zip(self.names, map(float, flow))),
            mole_fractions=dict(zip(self.names, map(float, x))),
            concentration_mol_m3=dict(zip(self.names, map(float, c))),
            source_mol_m3_s=dict(zip(self.names, map(float, rates))),
            creation_mol_m3_s=dict(zip(self.names, map(float, created))),
            destruction_mol_m3_s=dict(zip(self.names, map(float, destroyed))),
            coverage=[float(v) for v in cover] if cover else None,
            vacancy=list(map(float, vacant)),
            local_receipt_sha256=receipt["receipt_sha256"] if receipt else None,
            element_residual_mol_s=dict(zip(gas.element_names, map(float, elemental))),
            mass_residual_kg_s=float(flow @ gas.molecular_weights / 1000 - self.mdot),
        )


def network(reactor):
    net = ct.ReactorNet([reactor])
    net.rtol, net.atol = 1e-10, 1e-15
    net.max_steps = 100000
    return net


def propagate(exc, branch):
    if branch is not None and getattr(branch, "failure", None) is not None:
        raise branch.failure from exc
    raise RootFailure("Cantera integration failed", {"converged": False, "reason": str(exc)}) from exc
