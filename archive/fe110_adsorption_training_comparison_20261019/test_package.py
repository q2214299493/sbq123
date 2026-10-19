import copy
import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from ase.db import connect

from archive.fe110_five_c2_adsorption_20261006 import test_adsorption_finetune as old
from archive.fe110_adsorption_training_comparison_20261019.prepare import BASE, make_config
from scripts.adsorption.force_finetune import build_database, build_database_metadata, digest, warm_start
from scripts.adsorption.force_role_data import ROLE_NAMES, role_metadata
from scripts.adsorption.force_training_preflight import check_budget, check_database_labels, check_launcher

fixture_manifest = old.fixture_manifest
ROOT = Path(__file__).resolve().parents[2]


def add_roles(payload):
    for split, rows in payload["splits"].items():
        for row in rows:
            row["force_role_groups"] = {key: [] for key in ROLE_NAMES}
            row["force_role_groups"].update(adsorbate_C=[45], adsorbate_H=[46], near_Fe=list(range(18, 25)), other_Fe=list(range(25, 45)))
            weights = np.zeros(47)
            weights[18:] = 1. / 29
            row["proposed_per_atom_loss_weights"] = weights.tolist()
            row["proposed_source_stage_sampling_probability"] = 1.
    return payload


def test_config_reuses_architecture_but_fixes_validation_cadence():
    path = ROOT / "calculations/fe110_five_c2_adsorption_20261006/adsorption_finetune_review_v6/config.yml"
    # Publication tests need no ignored calculation files.
    template = {"checkpoint": "old", "model": {"unchanged": [1, 2]}, "trainer": "old",
                "optim": {"max_epochs": 4, "scheduler_params": {"epochs": 4}},
                "evaluation_metrics": {}, "dataset": {"train": {"a2g_args": {}}, "val": {"a2g_args": {}}}}
    if path.is_file():
        template = yaml.safe_load(path.read_text())
    original = copy.deepcopy(template)
    config = make_config("/home/sbq/sbq/test", template)
    assert config["model"] == original["model"] and template == original
    assert "checkpoint" not in config
    assert config["optim"]["eval_every"] == config["optim"]["checkpoint_every"] == 248
    assert config["dataset"]["val"]["src"].endswith("/development.db")
    assert config["evaluation_metrics"]["primary_metric"] == "forces_role_vector_mae"
    assert BASE["sha256"] == "e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50"


@pytest.fixture
def budget():
    request = {"split_counts": {"train": 248}, "training_limits": {"epochs": 2, "learning_rate": 1e-5,
        "seed": 42, "batch_size": 1, "GPU_count": 1, "CPU_count": 4, "memory_GB": 32,
        "walltime_minutes": 30, "unattended_retries": 0, "max_optimizer_steps": 496}}
    config = {"optim": {"eval_every": 248, "checkpoint_every": 248, "scheduler_params": {"epochs": 2}},
              "dataset": {"train": {}, "val": {}}}
    return request, config


def test_bounded_equal_epoch_contract(budget):
    check_budget(*budget)


@pytest.mark.parametrize("field,value", [("epochs", 3), ("seed", 2), ("GPU_count", 2),
    ("walltime_minutes", 31), ("unattended_retries", 1), ("max_optimizer_steps", 497)])
def test_reject_silent_budget_expansion(budget, field, value):
    request, config = budget
    request["training_limits"][field] = value
    with pytest.raises(ValueError, match="budget"):
        check_budget(request, config)


def test_no_per_step_validation_or_heldout_loader(budget):
    request, config = budget
    config["optim"]["eval_every"] = 1
    with pytest.raises(ValueError, match="cadence"):
        check_budget(request, config)
    config["optim"]["eval_every"] = 248
    config["dataset"]["test"] = {}
    with pytest.raises(ValueError, match="heldout"):
        check_budget(request, config)


def test_database_metadata_checked_against_manifest(fixture_manifest):
    path, payload = fixture_manifest
    add_roles(payload)
    path.write_text(json.dumps(payload))
    for split in ("train", "development"):
        build_database(path, path.parent / f"{split}.db", split)
        build_database_metadata(path.parent / f"{split}.db", path.parent / f"{split}_metadata.npz")
    request = {"manifest_path": path.name}
    check_database_labels(path.parent, request)
    database = connect(path.parent / "train.db")
    row = database.get(1)
    data = dict(row.data)
    data["adsorption_force_weights"] = data["adsorption_force_weights"][::-1]
    database.update(1, data=data)
    with pytest.raises(ValueError, match="role metadata"):
        check_database_labels(path.parent, request)


def test_uniform_control_changes_no_raw_force_or_identity(fixture_manifest):
    _, payload = fixture_manifest
    row = add_roles(payload)["splits"]["train"][0]
    before = copy.deepcopy(row)
    weights = np.zeros(47)
    weights[18:] = 1. / 29
    row["proposed_per_atom_loss_weights"] = weights.tolist()
    data = role_metadata(row, "train")
    assert np.allclose(data["adsorption_force_weights"][18:], 1./29)
    for key in ("forces_eV_per_A", "structure_sha256", "fixed_atom_indices_0based", "calculation_group"):
        assert row[key] == before[key]


def test_wrapper_namespace_resource_and_no_auto_requeue(tmp_path):
    target = tmp_path / "runtime/role_training_job.sh"
    target.parent.mkdir()
    source = (ROOT / "scripts/adsorption/role_training_job.sh").read_text()
    target.write_text(source)
    check_launcher(tmp_path)
    target.write_text(source.replace('export PYTHONPATH="$PACKAGE_ROOT/runtime:$PYTHONPATH"', "true"))
    with pytest.raises(ValueError, match="PYTHONPATH"):
        check_launcher(tmp_path)


def test_no_authorization_file_no_warmstart_model_load(tmp_path, monkeypatch):
    from scripts.adsorption import force_finetune
    monkeypatch.setattr(force_finetune, "verify_request", lambda _: {})
    request = tmp_path / "request.json"
    request.write_text("{}")
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps({"request_sha256": digest(request), "user_authorized": False,
                                   "action": "RUN_GPU_ADSORPTION_SMALL_FINETUNE"}))
    output = tmp_path / "must_not_exist.pt"
    with pytest.raises(ValueError, match="authorization"):
        warm_start(request, approval, output)
    assert not output.exists()
