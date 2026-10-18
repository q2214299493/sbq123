import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import write

from archive.fe110_adsorption_validation_20261018.runtime import load_atoms, local_path, validate_scope
from archive.fe110_adsorption_validation_20261018.validation_helpers import cuda_binding, force_metrics


def scope():
    exception = {"gpu_index": 1, "gpu_uuid": "GPU-example", "remote_root": "/home/sbq/sbq/test",
                 "max_wall_seconds": 1800, "baseline_checkpoint_sha256": "a" * 64,
                 "candidate_checkpoint_sha256": "b" * 64, "heldout_count": 16,
                 "geometry_case_names": ["06_C", "07_B", "08_A"], "seed_max_steps": 80,
                 "minimum_drift_max_steps": 20, "fmax_eV_per_A": .1, "authorizing_user_request": "验证"}
    request = {k: exception[k] for k in ("gpu_index", "gpu_uuid", "remote_root", "max_wall_seconds")}
    request.update(execution_mode="direct_no_scheduler", scheduler_job_id=None,
                   models={"baseline": {"sha256": "a" * 64}, "candidate": {"sha256": "b" * 64}},
                   heldout=[{"sample_id": str(i)} for i in range(16)],
                   geometry_cases=[{"name": n} for n in exception["geometry_case_names"]],
                   limits={k: exception[k] for k in ("seed_max_steps", "minimum_drift_max_steps", "fmax_eV_per_A")})
    auth = {"user_authorized": True, "user_request": "验证", "request_sha256": "c" * 64,
            "action": "RUN_GPU_ADSORPTION_FROZEN_VALIDATION"}
    return request, auth, "c" * 64, exception


def test_exact_authorized_scope():
    validate_scope(*scope())


@pytest.mark.parametrize("change", ["authorization", "gpu", "budget", "checkpoint", "heldout", "scheduler"])
def test_scope_expansion_rejected(change):
    request, auth, sha, exception = copy.deepcopy(scope())
    if change == "authorization":
        auth["request_sha256"] = "changed"
    elif change == "gpu":
        request["gpu_index"] = 2
    elif change == "budget":
        request["limits"]["seed_max_steps"] = 81
    elif change == "checkpoint":
        request["models"]["candidate"]["sha256"] = "changed"
    elif change == "heldout":
        request["heldout"][0] = request["heldout"][1]
    else:
        request["scheduler_job_id"] = "1234"
    with pytest.raises(ValueError):
        validate_scope(request, auth, sha, exception)


def test_package_escape_rejected(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        local_path(tmp_path, "../unrelated")


def test_cpu_fallback_rejected(monkeypatch):
    model = SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device=SimpleNamespace(type="cpu"))]))
    with pytest.raises(RuntimeError, match="CPU|cpu"):
        cuda_binding(SimpleNamespace(model=model))


def test_raw_force_metrics_do_not_average_in_fixed_atoms():
    symbols = ["Fe"] * 45 + ["C", "O"]
    reference, predicted = np.zeros((47, 3)), np.zeros((47, 3))
    predicted[:18] = 100
    predicted[45] = [1, 0, 0]
    result = force_metrics(reference, predicted, symbols, list(range(18)))
    assert result["Fe"]["vector_rmse_eV_A"] == 0
    assert result["adsorbate"]["vector_rmse_eV_A"] == pytest.approx(np.sqrt(.5))


def test_fixed_mask_and_inference_zero_tags(tmp_path):
    atoms = Atoms("Fe45CO", positions=np.arange(141).reshape(47, 3) * .1, cell=np.eye(3) * 30)
    atoms.set_constraint(FixAtoms(indices=range(18)))
    path = tmp_path / "POSCAR"
    write(path, atoms, format="vasp")
    checked = load_atoms(path)
    assert checked.get_tags().tolist() == [0] * 47
    assert checked.constraints[0].get_indices().tolist() == list(range(18))


def test_gpu_constructor_explicitly_disables_cpu():
    tree = ast.parse(Path(__file__).with_name("runtime.py").read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "patched_calc"]
    assert len(calls) == 1
    assert any(k.arg == "cpu" and isinstance(k.value, ast.Constant) and k.value.value is False for k in calls[0].keywords)
