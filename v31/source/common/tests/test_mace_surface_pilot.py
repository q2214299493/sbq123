from copy import deepcopy

import numpy as np
import pytest
import yaml
from ase import Atoms
from ase.constraints import FixAtoms

from scripts.mace_surface_pilot import CONFIG, RunSettings, check_geometry, checked_file, ref, validate_config


def config():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


@pytest.mark.parametrize("key", ["new_vasp_labels_authorized", "training_authorized", "production_promotion_authorized"])
def test_pilot_never_authorizes_more_execution(key):
    values = deepcopy(config())
    validate_config(values)
    values["active_learning"][key] = True
    with pytest.raises(ValueError, match="cannot authorize"):
        validate_config(values)


def test_step_budget_is_enforced():
    values = config()
    values["steps"]["ordinary_neb"] = 3
    with pytest.raises(ValueError, match="two steps"):
        validate_config(values)


def test_bound_file_cannot_be_substituted(tmp_path):
    path = tmp_path / "weights"
    path.write_bytes(b"original")
    binding = ref(path)
    assert checked_file(binding) == path.resolve()
    path.write_bytes(b"modified")
    with pytest.raises(ValueError, match="Bound source changed"):
        checked_file(binding)


def test_fixed_layer_drift_is_rejected():
    reference = Atoms(["Fe"] * 18 + ["C"], positions=np.array([[i * 2.0, 0., 0.] for i in range(19)]),
                      cell=[40, 10, 20], pbc=True, constraint=FixAtoms(indices=list(range(18))))
    candidate = reference.copy()
    check_geometry([candidate], reference, RunSettings())
    candidate.positions[0, 1] += .1
    with pytest.raises(ValueError, match="drift"):
        check_geometry([candidate], reference, RunSettings())
