from copy import deepcopy
import unittest

from .runner import MODEL_SHA, validate_scope


def request():
    return {"action": "FROZEN_TRAIN_DEVELOPMENT_FORCES_ONLY", "model": {"sha256": MODEL_SHA},
            "max_GPU_count": 1, "max_GPU_seconds": 600, "producer_seconds": 500,
            "forbidden_work": {"training": True, "optimization": True, "DFT": True, "heldout_or_quarantine": True, "model_reselection": True},
            "samples": [{"sample_id": str(i), "partition": "train" if i < 536 else "development"} for i in range(614)]}


class FrozenScopeTests(unittest.TestCase):
    def test_protected_partition_is_rejected(self):
        value = request()
        value["samples"][-1]["partition"] = "heldout"
        with self.assertRaises(ValueError):
            validate_scope(value)

    def test_model_and_budget_must_remain_frozen(self):
        for change in ("checkpoint", "budget"):
            value = deepcopy(request())
            if change == "checkpoint":
                value["model"]["sha256"] = "other"
            else:
                value["max_GPU_seconds"] = 601
            with self.assertRaises(ValueError):
                validate_scope(value)

    def test_training_cannot_be_enabled(self):
        value = request()
        value["forbidden_work"]["training"] = False
        with self.assertRaises(ValueError):
            validate_scope(value)


if __name__ == "__main__":
    unittest.main()
