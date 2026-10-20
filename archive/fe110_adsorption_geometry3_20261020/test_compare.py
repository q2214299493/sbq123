import copy
import time

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.constraints import FixAtoms

from archive.fe110_adsorption_validation_20261018 import runtime
from archive.fe110_adsorption_validation_20261018.test_runtime import scope
from archive.fe110_adsorption_geometry3_20261020.compare import same_graph
from archive.fe110_adsorption_geometry3_20261020 import trajectory_audit
from archive.fe110_adsorption_validation_20261018.test_review import synthetic_surface
from scripts.adsorption.build_fe110_adsorption import expanded_symbols


def test_graph_identity_survives_json_list_roundtrip():
    assert same_graph([(0, 2), (0, 3), (1, 2)], [[0, 2], [0, 3], [1, 2]])
    assert not same_graph([(0, 2)], [[0, 3]])


def test_frozen_poscar_trajectory_audit_respects_periodic_equivalence(monkeypatch, tmp_path):
    _, reference = synthetic_surface()
    first = Atoms(expanded_symbols(reference), positions=reference.frac @ reference.cell,
                  cell=reference.cell, pbc=[True, True, False])
    second = first.copy()
    second.positions += reference.cell[0]
    monkeypatch.setattr(trajectory_audit, "read", lambda *args, **kwargs: [first, second])
    result = trajectory_audit.audit(tmp_path / "synthetic.traj", reference)
    assert result["frame_count"] == 2
    assert result["graph_changed_frame_indices_0based"] == []
    assert result["maximum_adjacent_atom_displacement_A"] < 1e-12
    assert result["maximum_fixed_atom_displacement_A"] < 1e-12


def test_distinct_minimum_target_must_be_backend_bound():
    request, auth, sha, exception = copy.deepcopy(scope())
    request["limits"]["minimum_drift_fmax_eV_A"] = .02
    with pytest.raises(ValueError, match="budget"):
        runtime.validate_scope(request, auth, sha, exception)
    exception["minimum_drift_fmax_eV_A"] = .02
    runtime.validate_scope(request, auth, sha, exception)
    request["limits"]["minimum_drift_fmax_eV_A"] = .01
    with pytest.raises(ValueError, match="budget"):
        runtime.validate_scope(request, auth, sha, exception)


@pytest.mark.parametrize("origin,target", [("seed", .1), ("minimum", .02)])
def test_optimizer_uses_the_declared_origin_target(tmp_path, monkeypatch, origin, target):
    # Synthetic fixture tests dispatch only;never a scientific model/input.
    atoms = Atoms("Fe45CO", positions=np.arange(141).reshape(47, 3)*.1, cell=np.eye(3)*30)
    atoms.set_constraint(FixAtoms(indices=range(18)))
    calc = SinglePointCalculator(atoms, forces=np.zeros((47, 3)))
    seen = []

    class FakeOptimizer:
        nsteps = 0

        def __init__(self, *args, **kwargs):
            pass

        def attach(self, *args, **kwargs):
            pass

        def run(self, **kwargs):
            seen.append(kwargs["fmax"])
            return True

    monkeypatch.setattr(runtime, "load_atoms", lambda _: atoms.copy())
    monkeypatch.setattr(runtime, "LBFGS", FakeOptimizer)
    (tmp_path / "seed").write_text("synthetic fixture")
    case = {"name": "synthetic", "seed_path": "seed", "reference_path": "seed"}
    limits = {"seed_max_steps": 80, "minimum_drift_max_steps": 20, "fmax_eV_per_A": .1, "minimum_drift_fmax_eV_A": .02}
    result = runtime.relax_case(tmp_path, tmp_path / "output", case, origin, calc, limits, time.monotonic()+10)
    assert seen == [target]
    assert result["ML_optimizer_fmax_target_eV_A"] == target
    assert result["scientific_acceptance"] is False
