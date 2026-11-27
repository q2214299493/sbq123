"""Local surface kinetics for Cantera extensible reactor callbacks."""

from copy import deepcopy

import cantera as ct
import numpy as np
from sbq123.common.kinetic_model.contracts import RootFailure, number


class LocalSource:
    """Track one qualified surface branch from the previous accepted physical state."""

    def __init__(self, model, factor: float, coverage: list, distance: float):
        try:
            from sbq123.mkm.catkinas.local import local_point
        except ModuleNotFoundError as exc:
            raise ValueError("Install sbq123-reactor-cantera[dynamic] for local MKM") from exc
        self.solve = local_point
        self.model = model
        self.factor = factor
        self.anchor = [number(q, "initial coverage", nonnegative=True) for q in coverage]
        self.distance = number(distance, "maximum local coverage displacement", positive=True)
        if self.distance > 1 or len(self.anchor) != model.phases.count("surface") or not self.anchor:
            raise ValueError("Invalid surface branch specification")
        self.reference = None
        self.orientation = None
        self.receipts = []
        self.failure = None

    def evaluate(self, gas, *, commit=False):
        c = np.asarray(gas.concentrations) * 1000
        if not np.all(np.isfinite(c)) or min(c) < -1e-10 * sum(abs(c)):
            raise ValueError("Nonphysical local gas state")
        state = np.append(np.maximum(c, 0), [gas.T, gas.P])

        def follow(start, anchor, end, depth):
            try:
                rates, receipt = self.solve(
                    self.model, end[:-2], float(end[-2]), float(end[-1]), anchor, self.distance, expected_orientation=self.orientation
                )
            except RootFailure as exc:
                if start is None or depth >= 8 or "continuity limit" not in str(exc):
                    exc.prior_receipts = tuple(self.receipts)
                    raise
                mid = (start + end) * 0.5
                _, intermediate = follow(start, anchor, mid, depth + 1)
                return follow(mid, intermediate["coverage"], end, depth + 1)
            self.receipts.append(receipt)
            return rates, receipt

        rates, receipt = follow(self.reference, self.anchor, state, 0)
        if commit:
            self.reference = state.copy()
            self.anchor = receipt["coverage"].copy()
            self.orientation = receipt["orientation"]
        gas_rates = [v * self.factor for v, p in zip(rates, self.model.phases) if p == "gas"]
        return np.asarray(gas_rates), receipt

    def snapshot(self):
        return (None if self.reference is None else self.reference.copy(), self.anchor.copy(), self.orientation)

    def restore(self, state):
        self.reference, self.anchor, self.orientation = deepcopy(state)


class CoupledTank(ct.ExtensibleIdealGasReactor):
    """Cantera control volume with a signed mol/m³/s source supplied by a local MKM."""

    def after_eval(self, t, lhs, rhs):
        try:
            rates, _ = self.local_source.evaluate(self.phase)
            mass_terms = rates * self.phase.molecular_weights * self.volume / 1000
            for index, name in enumerate(self.phase.species_names):
                rhs[self.component_index(name)] += mass_terms[index]
        except (ValueError, ArithmeticError) as exc:
            self.local_source.failure = exc
            raise
