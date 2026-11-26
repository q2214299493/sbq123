import copy
import json
import time

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.constraints import FixAtoms

from scripts.adsorption.reico_sampling import geometry_audit, sample_case, validate_sampling_scope

LIMITS = {"max_steps": 20, "maxstep_A": .05, "ML_fmax_eV_A": .1,
          "minimum_Fe_Fe_A": 1.8, "minimum_adsorbate_height_A": -.5,
          "minimum_periodic_vacuum_gap_A": 8.}
GUARDS = {"C-Fe": 1.6, "Fe-H": 1.3, "C-H": .85}


def atoms_fixture():
    positions = [[x * 2.5, y * 2.5, 3. + layer * 2.] for layer in range(5) for y in range(3) for x in range(3)]
    atoms = Atoms("Fe45CH", positions=positions + [[2., 2., 13.], [3., 2., 13.]], cell=[9., 9., 24.], pbc=True)
    atoms.set_constraint(FixAtoms(indices=range(18)))
    return atoms


class Harmonic(Calculator):
    implemented_properties = ["energy", "forces"]

    def __init__(self, target):
        super().__init__()
        self.target = np.asarray(target)

    def calculate(self, atoms=None, properties=None, system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        delta = atoms.positions - self.target
        self.results = {"energy": float(.5 * np.sum(delta**2)), "forces": -delta}


def scope():
    exception = {"gpu_index": 1, "gpu_uuid": "GPU-example", "remote_root": "/home/sbq/sbq/example",
                 "max_wall_seconds": 600, "limits": copy.deepcopy(LIMITS), "authorizing_user_request": "continue",
                 "candidate_checkpoint_sha256": "a" * 64, "sample_count": 2, "source_names": ["one", "two"],
                 "source_manifest_sha256": "b" * 64, "generation_config_sha256": "c" * 64}
    request = copy.deepcopy(exception)
    request.update(execution_mode="direct_no_scheduler", scheduler_job_id=None,
                   models={"candidate": {"sha256": "a" * 64}}, geometry_cases=[],
                   samples=[{"sample_id": k, "source_name": k} for k in ("one", "two")],
                   sample_role="screened_untrained_diagnostic_not_independent_heldout")
    auth = {"user_authorized": True, "action": "RUN_GPU_REICO_BOUNDED_SAMPLING",
            "request_sha256": "d" * 64, "user_request": "continue"}
    return request, auth, "d" * 64, exception


def test_exact_sampling_scope():
    validate_sampling_scope(*scope())


@pytest.mark.parametrize("key", ["gpu_index", "source_manifest_sha256", "generation_config_sha256",
                                 "checkpoint", "budget", "authorization", "membership", "scheduler"])
def test_scope_expansion_rejected(key):
    request, auth, sha, exception = scope()
    if key == "checkpoint":
        request["models"]["candidate"]["sha256"] = "e" * 64
    elif key == "budget":
        request["limits"]["max_steps"] += 1
    elif key == "authorization":
        auth["request_sha256"] = "e" * 64
    elif key == "membership":
        request["samples"][0] = request["samples"][1]
    elif key == "scheduler":
        request["scheduler_job_id"] = "123"
    else:
        request[key] = "changed"
    with pytest.raises(ValueError):
        validate_sampling_scope(request, auth, sha, exception)


def test_geometry_guard_handles_fixed_layer_collision_and_nonfinite():
    atoms = atoms_fixture()
    original = atoms.copy()
    assert not geometry_audit(atoms, original, GUARDS, LIMITS)["failures"]
    atoms.positions[0, 0] += .01
    assert "ORDER_CELL_OR_FIXED_LAYER_CHANGED" in geometry_audit(atoms, original, GUARDS, LIMITS)["failures"]
    atoms = original.copy()
    atoms.positions[46] = atoms.positions[45] + [.4, 0, 0]
    assert "SHORT_CONTACT:C-H" in geometry_audit(atoms, original, GUARDS, LIMITS)["failures"]
    atoms.positions[46, 0] = np.nan
    assert geometry_audit(atoms, original, GUARDS, LIMITS)["failures"] == ["NONFINITE_GEOMETRY"]


def test_twenty_step_cap_and_fixed_atoms_and_restart(tmp_path):
    atoms = atoms_fixture()
    initial = atoms.positions.copy()
    target = initial.copy()
    target[18:45, 0] += .1
    target[45:, 0] += 2.
    atoms.calc = Harmonic(target)
    result = sample_case(atoms, tmp_path / "trajectory", LIMITS, GUARDS, time.monotonic() + 30)
    assert result["status"] == "STEP_LIMIT_REACHED"
    assert result["optimizer_steps"] == 20 and len(result["frames"]) == 21
    assert np.array_equal(atoms.positions[:18], initial[:18])
    assert (tmp_path / "trajectory/lbfgs_restart.json").is_file()
    assert all(r["max_step_displacement_A"] <= .05 + 1e-8 for r in result["frames"])
    assert all(not r["geometry_audit"]["failures"] for r in result["frames"])
    with pytest.raises(FileExistsError):
        sample_case(atoms, tmp_path / "trajectory", LIMITS, GUARDS, time.monotonic() + 30)


def test_guard_stop_retains_rejected_boundary(tmp_path):
    atoms = atoms_fixture()
    target = atoms.positions.copy()
    target[46] = target[45]
    atoms.calc = Harmonic(target)
    result = sample_case(atoms, tmp_path / "boundary", LIMITS, GUARDS, time.monotonic() + 30)
    assert result["status"] == "GUARD_STOP_PRESERVED"
    assert result["frames"][-1]["geometry_audit"]["failures"] == ["SHORT_CONTACT:C-H"]
    assert all(not r["geometry_audit"]["failures"] for r in result["frames"][:-1])


def test_timeout_is_not_reported_as_success(tmp_path):
    atoms = atoms_fixture()
    atoms.calc = Harmonic(atoms.positions.copy() + [.1, 0, 0])
    with pytest.raises(TimeoutError):
        sample_case(atoms, tmp_path / "timeout", LIMITS, GUARDS, time.monotonic() - 1)
    record = json.loads((tmp_path / "timeout/case_record.json").read_bytes())
    assert record["status"] == "RUNTIME_ERROR_PRESERVED"
    assert not record["ML_optimizer_converged"]
