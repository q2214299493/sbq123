"""Numerical and source guards; no model forward or checkpoint writer."""
from __future__ import annotations

from copy import deepcopy
import unittest

from .analyze import diagnose, validate_packet, vector_metrics
from .prepare import force_stage


def example():
    reference = {"sample_id": "fixture", "partition": "train", "qualification_scope": "STRICT_RAW_E_F_LOCALMAG", "composition": "C",
                 "force_stage": "DFT_fmax_le0p02", "structure_sha256": "source_A", "symbols": ["Fe", "C"],
                 "DFT_forces_eV_per_A": [[100., 0., 0.], [0., 0., 0.]], "fixed_atom_indices_0based": [0],
                 "force_role_groups": {"adsorbate_C": [1], "near_Fe": [], "other_Fe": []}}
    packet = {"checkpoint_sha256": "model_A", "samples": [{"sample_id": "fixture", "structure_sha256": "source_A",
              "predicted_forces_eV_per_A": [[-100., 0., 0.], [3., 4., 0.]]}]}
    return reference, packet


class DiagnosisGuards(unittest.TestCase):
    def test_vector_rmse_is_not_component_mae(self):
        value = vector_metrics([[0., 0., 0.]], [[3., 4., 0.]])
        self.assertEqual(value["vector_RMSE_eV_A"], 5.)
        self.assertEqual(value["vector_MAE_eV_A"], 5.)
        self.assertAlmostEqual(value["component_MAE_eV_A"], 7 / 3)

    def test_fixed_fe_error_excluded(self):
        reference, packet = example()
        result = diagnose([reference], packet, "model_A")
        self.assertEqual(result["frames"][0]["groups"]["all_movable"]["vector_RMSE_eV_A"], 5.)

    def test_wrong_checkpoint_rejected(self):
        reference, packet = example()
        with self.assertRaises(ValueError):
            validate_packet([reference], packet, "model_B")

    def test_different_coordinates_rejected(self):
        reference, packet = example()
        packet["samples"][0]["structure_sha256"] = "source_B"
        with self.assertRaises(ValueError):
            validate_packet([reference], packet, "model_A")

    def test_extra_or_protected_sample_rejected(self):
        reference, packet = example()
        extra = deepcopy(packet["samples"][0])
        extra["sample_id"] = "heldout"
        packet["samples"].append(extra)
        with self.assertRaises(ValueError):
            validate_packet([reference], packet, "model_A")

    def test_heldout_partition_rejected(self):
        reference, packet = example()
        reference["partition"] = "heldout"
        with self.assertRaises(ValueError):
            validate_packet([reference], packet, "model_A")

    def test_nonfinite_prediction_rejected(self):
        reference, packet = example()
        packet["samples"][0]["predicted_forces_eV_per_A"][1][0] = float("nan")
        with self.assertRaises(ValueError):
            validate_packet([reference], packet, "model_A")

    def test_nearzero_direction_not_invented(self):
        value = vector_metrics([[0., 0., 0.]], [[1., 0., 0.]])
        self.assertEqual(value["cosine_usable_atoms"], 0)
        self.assertIsNone(value["mean_cosine_nonzero"])

    def test_force_stage_boundaries(self):
        self.assertEqual(force_stage(.02), "DFT_fmax_le0p02")
        self.assertEqual(force_stage(.05), "DFT_fmax_0p02_to0p05")
        self.assertEqual(force_stage(.10), "DFT_fmax_0p05_to0p10")
        self.assertEqual(force_stage(.50), "DFT_fmax_0p10_to0p50")


if __name__ == "__main__":
    unittest.main()
