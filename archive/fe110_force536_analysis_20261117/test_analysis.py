"""Synthetic mathematical fixtures only; scientific outputs use the real614 frames."""
from __future__ import annotations

import unittest

import numpy as np

from .analyze import STRICT, bucket, frame_record, roles, subset_keys, summarize_bucket


def fixture():
    row = {"sample_id": "fixture", "partition": "train", "qualification_scope": STRICT, "composition": "C", "force_stage": "DFT_fmax_0p10_to0p50",
           "DFT_movable_fmax_eV_A": .3, "symbols": ["Fe", "Fe", "C"], "fixed_atom_indices_0based": [0],
           "force_role_groups": {"adsorbate_C": [2], "near_Fe": [1], "other_Fe": []}, "original_per_atom_weights": [0, .5, .5],
           "source_job_id": "fixture", "structure_sha256": "fixture_geometry", "physical_label_key": "fixture:1"}
    joined = {"source_root": "fixture_source", "near_duplicate": {"representative_id": "fixture"}, "adsorbate_component_count": 1,
              "carbon_backbone_connected": True, "component_formulas": ["C"], "joint_signature": "fixture"}
    return row, joined


class AnalysisTests(unittest.TestCase):
    def test_fixed_fe_excluded_and_movable_fe_can_trigger_handoff_flag(self):
        row, joined = fixture()
        target = np.asarray([[999., 0, 0], [.3, 0, 0], [.01, 0, 0]])
        predicted = np.asarray([[0., 0, 0], [.02, 0, 0], [.01, 0, 0]])
        value = frame_record(row, target, predicted, joined)
        self.assertTrue(value["ML_le0p05_DFT_gt0p10"])
        self.assertEqual(value["maximum_DFT_force_role"], "near_Fe")
        self.assertAlmostEqual(value["maximum_error_eV_A"], .28)
        self.assertEqual(value["groups"]["all_movable"]["atom_observations"], 2)

    def test_root_balancing_differs_from_frame_count_weighting(self):
        value = bucket()
        for i, (source, error) in enumerate([("A", 1.), ("A", 1.), ("A", 1.), ("B", 9.)]):
            value["target"].append(np.zeros((1, 3)))
            value["predicted"].append(np.asarray([[error, 0, 0]]))
            value["frames"].add(str(i))
            value["roots"].add(source)
            value["per_frame_MAE"].append(error)
            value["root_MAE"][source].append(error)
        result = summarize_bucket(("train", "ALL", "ALL", "ALL", "all_frames", "all_movable"), value)
        self.assertEqual(result["vector_MAE_eV_A"], 3.)
        self.assertEqual(result["source_balanced_frame_vector_MAE_eV_A"], 5.)

    def test_fragment_not_mixed_with_intact_population(self):
        row, joined = fixture()
        joined.update(adsorbate_component_count=2, carbon_backbone_connected=False, component_formulas=["C2H2", "CO"])
        keys = subset_keys(row, joined)
        self.assertTrue(any(k[4] == "CO_plus_C2H2" for k in keys))
        self.assertFalse(any(k[4] == "intact_connected" for k in keys))

    def test_duplicate_role_assignment_rejected(self):
        row, _ = fixture()
        row["force_role_groups"]["other_Fe"] = [1]
        with self.assertRaises(ValueError):
            roles(row)


if __name__ == "__main__":
    unittest.main()
