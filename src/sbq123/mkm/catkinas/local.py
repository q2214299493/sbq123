"""Local deterministic mean-field solver. Native CATKINAS execution is separate."""

import numpy as np
from scipy.optimize import least_squares

from sbq123.common.kinetic_model.contracts import identity, RootFailure, number


def local_point(model, gas, temperature, pressure, anchor, max_distance, tol=1e-9, *, expected_orientation=None):
    indices = [i for i, p in enumerate(model.phases) if p == "surface"]
    if not isinstance(anchor, (list, tuple, np.ndarray)) or np.ndim(anchor) != 1:
        raise RootFailure("Expected a one-dimensional numeric surface coverage")
    values = [v.item() if isinstance(v, np.generic) else v for v in anchor]
    anchor = np.array([number(v, "surface coverage", nonnegative=True) for v in values])
    max_distance = number(max_distance, "branch distance", positive=True)
    tol = number(tol, "surface residual tolerance", positive=True)
    if not indices or anchor.shape != (len(indices),) or not np.isfinite(anchor).all() or np.any((anchor < 0) | (anchor > 1)):
        raise RootFailure("A physical initial surface branch specification is required")
    if min(model.source(gas, anchor, temperature, pressure)[1], default=1) < -tol:
        raise RootFailure("Initial coverage violates site balance")

    # Scale each surface equation by its own characteristic reaction traffic.
    # Slowing all steps equally must not turn an arbitrary seed into a steady state.
    occupancy = np.asarray([model.occupancy[i] for i in indices])
    interior = np.full(len(indices), 0.5 / max(1, float(occupancy.sum(axis=0).max())))
    scale = np.maximum.reduce(
        [np.asarray(model.production(gas, state, temperature, pressure)[2])[indices] for state in (anchor, interior, np.zeros_like(anchor))]
    )
    if np.any(scale <= 0):
        raise RootFailure("Locally singular surface root: missing reaction traffic")

    def residual(theta):
        rates, _ = model.source(gas, theta, temperature, pressure)
        return np.asarray(rates)[indices] / scale

    solution = least_squares(residual, anchor, bounds=(0, 1), gtol=1e-13, xtol=1e-13, ftol=1e-13, max_nfev=400)
    theta = solution.x
    rates, vacancy = model.source(gas, theta, temperature, pressure)
    norm = float(np.linalg.norm(residual(theta), ord=np.inf))
    distance = float(np.max(np.abs(theta - anchor)))
    orientation = int(np.linalg.slogdet(solution.jac)[0])

    def reject(reason):
        failure = dict(
            converged=False,
            reason=reason,
            model_sha256=model.digest,
            gas_concentration_mol_m3=list(map(float, gas)),
            temperature_K=temperature,
            pressure_Pa=pressure,
            scaled_residual_inf=norm,
            residual_inf=float(np.max(np.abs(np.asarray(rates)[indices]))),
            equation_scales=scale.tolist(),
            candidate=theta.tolist(),
            anchor=anchor.tolist(),
            orientation=orientation,
        )
        raise RootFailure(reason, dict(failure, receipt_sha256=identity(failure)))

    if not solution.success or norm > tol or min(vacancy, default=1) < -tol:
        reject("Unconverged or unphysical local surface root")
    if np.linalg.matrix_rank(solution.jac) < len(indices):
        reject("Locally singular surface root")
    if expected_orientation is not None and expected_orientation != orientation:
        reject("Surface root branch orientation changed")
    if distance > max_distance:
        reject("Surface root continuity limit exceeded")
    record = dict(
        model_sha256=model.digest,
        temperature_K=temperature,
        pressure_Pa=pressure,
        gas_concentration_mol_m3=[float(v) for v in gas],
        coverage=theta.tolist(),
        vacancy=list(map(float, vacancy)),
        anchor=anchor.tolist(),
        distance=distance,
        scaled_residual_inf=norm,
        residual_inf=float(np.max(np.abs(np.asarray(rates)[indices]))),
        equation_scales=scale.tolist(),
        evaluations=int(solution.nfev),
        converged=True,
        orientation=orientation,
        root_state_sha256=identity(theta.tolist()),
        solver="bounded_least_squares",
    )
    return rates, dict(record, receipt_sha256=identity(record))
