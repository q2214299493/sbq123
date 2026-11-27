"""Convert private Cantera states to the SBQ123 molar material-balance contract."""

import cantera as ct
import numpy as np

from sbq123.common.kinetic_model.contracts import RootFailure, number
from .kinetics.source import LocalSource


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
        if mode not in ("fixed", "dynamic_mkm") or (mode == "dynamic_mkm" and mechanism.surface is None):
            raise ValueError("Unsupported kinetic mode for this dataset")
        self.dynamic = mode == "dynamic_mkm"
        self.surface_names = [n for n, p in zip(mechanism.model.species, mechanism.model.phases) if p == "surface"]
        cov = inputs["initial_coverage"]
        if not isinstance(cov, (tuple, list)) or len(cov) != len(self.surface_names):
            raise ValueError("Specify one initial amount per registered surface species")
        self.coverage = [number(v, "coverage", nonnegative=True) for v in cov]
        self.occupancy = np.array([o[0] for o, p in zip(mechanism.model.occupancy, mechanism.model.phases) if p == "surface"])
        if np.dot(self.occupancy, self.coverage) > 1:
            raise ValueError("Initial coverages exceed the site inventory")
        self.distance = number(inputs["max_root_distance"], "surface branch distance", positive=True)
        if self.distance > 1:
            raise ValueError("Coverage displacement exceeds one site inventory")

    def phases(self, x, *, flow_guard=False):
        gas, surface = self.m.fresh(flow_guard=flow_guard)
        gas.TPX = self.t, self.p, np.append(x, 0.0) if flow_guard else x
        if surface is not None:
            surface.TP = self.t, self.p
            occupied = self.occupancy * self.coverage
            surface.coverages = {**dict(zip(self.surface_names, occupied)), self.m.model.sites[0]: max(0, 1 - sum(occupied))}
        return gas, surface

    def branch(self, gas):
        if not self.dynamic:
            return None
        src = LocalSource(self.m.model, self.m.factor, self.coverage, self.distance)
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
            if surface is not None:
                cover = [surface.concentrations[surface.species_index(n)] / surface.site_density for n in self.surface_names]
            rates = self.m.signed_rates(gas, surface)
        predicted, vacant, traffic = self.m.model.production(c, cover, gas.T, gas.P)
        idx = [i for i, p in enumerate(self.m.model.phases) if p == "gas"]
        gas_traffic = np.array(traffic)[idx] * self.m.factor
        expected = np.array(predicted)[idx] * self.m.factor
        if not np.all(np.isfinite(rates)) or np.any(abs(rates - expected) > 2e-8 * np.maximum(gas_traffic, 1e-30)):
            raise RootFailure("Local species rates disagree with the registered kinetic model")
        surf_idx = [i for i, p in enumerate(self.m.model.phases) if p == "surface"]
        if surf_idx and (
            min(cover) < -1e-9 or min(vacant) < -1e-9 or any(abs(predicted[i]) > 2e-7 * max(traffic[i], 1e-20) for i in surf_idx)
        ):
            raise RootFailure("Surface inventory or local steady balance failed")
        outlet_mdot = self.mdot if mdot is None else mdot
        flow = outlet_mdot / gas.mean_molecular_weight * 1000 * x
        atoms = np.array([[gas.n_atoms(k, e) for k in self.names] for e in gas.element_names])
        elemental = atoms @ (flow - self.feed)
        if np.any(abs(elemental) > 2e-7 * self.fin * np.maximum(1, atoms @ self.x)):
            raise RootFailure("Element flow is not conserved")
        consumed = self.feed[self.ia] - flow[self.ia]
        formed = flow[self.ib] - self.feed[self.ib]
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
            conversion=float(consumed / self.feed[self.ia]),
            yield_mol_per_mol_fed=float(formed / self.feed[self.ia]),
            selectivity_mol_per_mol_consumed=float(formed / consumed) if abs(consumed) > 1e-12 * self.feed[self.ia] else None,
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
