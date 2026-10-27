"""One-model budget compatibility and development/heldout boundary checks."""
import copy

import pytest

from archive.fe110_training512_20261027.prepare import make_config, validation_plan
from archive.fe110_training512_20261027.verify import differences
from scripts.adsorption.direct_force_training import reviewed_arms


def test_historical_two_arm_requests_keep_their_original_scope():
    assert reviewed_arms({"arm_request_sha256": {"control": "a", "treatment": "b"}}) == ["control", "treatment"]


def test_single_arm_requires_explicit_matching_policy():
    assert reviewed_arms({"arms": ["control"], "arm_request_sha256": {"control": "a"}}) == ["control"]


@pytest.mark.parametrize("arms,bindings", [([], {}), (["control"], {"control": "a", "treatment": "b"}),
    (["control", "treatment"], {"control": "a"}), (["control", "control"], {"control": "a"}),
    (["other"], {"other": "a"}), (["treatment"], {"treatment": "a"})])
def test_missing_or_expanded_arm_bindings_fail_closed(arms, bindings):
    with pytest.raises(ValueError, match="hash bindings"):
        reviewed_arms({"arms": arms, "arm_request_sha256": bindings})


def test_config_rebinds_data_and_cadence_without_changing_model_or_loss():
    template = {"model": {"architecture": "unchanged"}, "loss_functions": [{"energy": {"coefficient": 0}}],
        "optim": {"max_epochs": 2, "eval_every": 248, "checkpoint_every": 248,
                  "lr_initial": 1e-5, "scheduler_params": {"epochs": 2}},
        "dataset": {"train": {"src": "old_train", "metadata_path": "old_meta"},
                    "val": {"src": "old_val", "metadata_path": "old_valmeta"}}}
    original = copy.deepcopy(template)
    result = make_config(template)
    assert template == original
    assert result["model"] == original["model"] and result["loss_functions"] == original["loss_functions"]
    assert result["optim"]["eval_every"] == result["optim"]["checkpoint_every"] == 512
    assert set(result["dataset"]) == {"train", "val"}
    assert result["dataset"]["val"]["src"].endswith("/development.db")


def test_validation_keeps_historical_test_exposure_explicit():
    manifest = {"splits": {"development": [{}] * 78,
        "heldout": [{"sample_id": f"old_{i}", "source_collection": "legacy_control_20261019"} for i in range(46)]
        + [{"sample_id": f"new_{i}", "source_collection": "reviewed_reico_statics137"} for i in range(7)]}}
    plan = validation_plan(manifest)
    assert len(plan["historically_evaluated_heldout_ids"]) == 46
    assert plan["heldout_frames"] == 53 and not plan["heldout_is_new_blind_test"]
    assert not plan["heldout_consumed_for_candidate_selection"] and not plan["GPU_evaluation_authorized"]
    assert plan["selection_split"] == "development"


def test_independent_config_diff_detects_changed_loss_and_added_loader():
    original = {"loss": {"energy": 0}, "dataset": {"train": "a", "val": "b"}}
    changed = {"loss": {"energy": 1}, "dataset": {"train": "a", "val": "b", "test": "c"}}
    assert differences(original, changed) == {"loss.energy", "dataset.test"}


def test_independent_config_diff_ignores_dictionary_order():
    assert differences({"a": {"x": 1, "y": [2, 3]}}, {"a": {"y": [2, 3], "x": 1}}) == set()
