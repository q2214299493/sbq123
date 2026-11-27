"""Local surface kinetics for Cantera extensible reactor callbacks."""

from dataclasses import dataclass

import cantera as ct
import numpy as np
from sbq123.common.kinetic_model.contracts import RootFailure, identity, number


@dataclass(frozen=True)
class _Checkpoint:
    state: tuple
    coverage: tuple
    orientation: int
    receipt_sha256: str


@dataclass(frozen=True)
class _ReportSource:
    """Evaluate observations against one immutable accepted checkpoint."""

    source: "LocalSource"
    checkpoint: _Checkpoint

    def evaluate(self, gas, *, commit=False):
        if commit:
            raise ValueError("A report cannot advance the physical trajectory")
        return self.source._evaluate(gas, "report", self.checkpoint)


class LocalSource:
    """Own local solver receipts and the most recently accepted physical checkpoint."""

    def __init__(self, model, factor: float, coverage: list, distance: float):
        try:
            from sbq123.mkm.catkinas.local import local_point
        except ModuleNotFoundError as exc:
            raise ValueError("Install sbq123-reactor-cantera[dynamic] for local MKM") from exc
        self.solve = local_point
        self.model = model
        self.factor = factor
        self.initial = tuple(number(q, "initial coverage", nonnegative=True) for q in coverage)
        self.distance = number(distance, "maximum local coverage displacement", positive=True)
        if self.distance > 1 or len(self.initial) != model.phases.count("surface") or not self.initial:
            raise ValueError("Invalid surface branch specification")
        self.checkpoint = None
        self.receipts = []
        self.failure = None

    def report_at(self, checkpoint):
        """Return a read-only evaluation view of the specified physical checkpoint."""
        if checkpoint is None:
            raise ValueError("A report requires an accepted physical checkpoint")
        return _ReportSource(self, checkpoint)

    def evaluate(self, gas, *, commit=False):
        return self._evaluate(gas, "accepted" if commit else "trial", self.checkpoint)

    def _evaluate(self, gas, kind, checkpoint):
        c = np.asarray(gas.concentrations) * 1000
        if not np.all(np.isfinite(c)) or min(c) < -1e-10 * sum(abs(c)):
            raise ValueError("Nonphysical local gas state")
        state = np.append(np.maximum(c, 0), [gas.T, gas.P])
        predecessor = checkpoint.receipt_sha256 if checkpoint else None
        orientation = checkpoint.orientation if checkpoint else None
        recovered = []

        def follow(start, anchor, end, depth, ownership):
            try:
                rates, raw = self.solve(
                    self.model, end[:-2], float(end[-2]), float(end[-1]), anchor, self.distance, expected_orientation=orientation
                )
                if raw.get("converged") is not True:
                    raise RootFailure("Unconverged local MKM evaluation", raw)
            except RootFailure as exc:
                if start is None or depth >= 8 or "continuity limit" not in str(exc):
                    exc.prior_receipts = tuple(self.receipts)
                    exc.subdivision_failures = tuple(recovered)
                    self.failure = exc
                    raise
                recovered.append(exc.receipt)
                mid = (start + end) * 0.5
                _, intermediate = follow(start, anchor, mid, depth + 1, "trial")
                return follow(mid, intermediate["coverage"], end, depth + 1, ownership)
            # Keep the original solver content and digest recoverable. The outer
            # identity also binds evaluation ownership and the physical predecessor.
            record = dict(raw)
            record["solver_receipt_sha256"] = record.pop("receipt_sha256")
            record.update(evaluation_type=ownership, predecessor_checkpoint_sha256=predecessor)
            if recovered:
                record["subdivision_failures"] = recovered.copy()
            record["receipt_sha256"] = identity(record)
            self.receipts.append(record)
            return rates, record

        rates, receipt = follow(
            checkpoint.state if checkpoint else None, checkpoint.coverage if checkpoint else self.initial, state, 0, kind
        )
        if kind == "accepted":
            self.checkpoint = _Checkpoint(tuple(state), tuple(receipt["coverage"]), receipt["orientation"], receipt["receipt_sha256"])
        gas_rates = [v * self.factor for v, p in zip(rates, self.model.phases) if p == "gas"]
        return np.asarray(gas_rates), receipt


class CoupledTank(ct.ExtensibleIdealGasReactor):
    """Cantera control volume with a signed mol/m鲁/s source supplied by a local MKM."""

    def after_eval(self, t, lhs, rhs):
        try:
            rates, _ = self.local_source.evaluate(self.phase)
            mass_terms = rates * self.phase.molecular_weights * self.volume / 1000
            for index, name in enumerate(self.phase.species_names):
                rhs[self.component_index(name)] += mass_terms[index]
        except (ValueError, ArithmeticError) as exc:
            self.local_source.failure = exc
            raise
