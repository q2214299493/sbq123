"""In-memory guard cases only; fixtures are never written as scientific inputs."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
import unittest

import numpy as np

from scripts.adsorption.build_fe110_adsorption import Poscar
from .geometry import distance_metrics, iron_maps, packed_pose
from .path_sources import first_frame
from .select_budget import budget_rows, rejection_reason


def fixture():
    cell = np.diag([9., 9., 20.])
    fe = [[i / 3, j / 3, (k + 2) / 20] for k in range(5) for i in range(3) for j in range(3)]
    ads = [[.11, .13, .40], [.22, .18, .41], [.28, .23, .42], [.10, .19, .43]]
    flags = [["F"] * 3 for _ in range(18)] + [["T"] * 3 for _ in range(31)]
    pose = Poscar("synthetic bookkeeping fixture", cell, ["Fe", "C", "O", "H"], [45, 2, 1, 1], np.asarray(fe + ads), flags)
    slab = Poscar("synthetic slab", cell, ["Fe"], [45], np.asarray(fe), flags[:45])
    operations = [(np.eye(3, dtype=int), np.asarray([shift / 3, 0., 0.])) for shift in range(3)]
    return pose, slab, operations


class SymmetryGuards(unittest.TestCase):
    def setUp(self):
        self.pose, self.slab, self.operations = fixture()
        self.maps = iron_maps(self.slab, self.operations)
        self.reference = packed_pose(self.pose, self.operations, self.maps)

    def test_identity(self):
        self.assertAlmostEqual(distance_metrics(self.pose, self.reference)["full_RMSD_A"], 0, places=12)

    def test_equal_carbon_permutation(self):
        changed = deepcopy(self.pose)
        changed.frac[[45, 46]] = changed.frac[[46, 45]]
        self.assertLess(distance_metrics(changed, self.reference)["full_RMSD_A"], 1e-12)

    def test_surface_translation_maps_fe_roles(self):
        changed = deepcopy(self.pose)
        changed.frac[:] += np.asarray([1 / 3, 0, 0])
        self.assertLess(distance_metrics(changed, self.reference)["full_RMSD_A"], 1e-12)

    def test_full_periodic_image(self):
        changed = deepcopy(self.pose)
        changed.frac[45:, :2] += 1
        self.assertLess(distance_metrics(changed, self.reference)["full_RMSD_A"], 1e-12)

    def test_height_change_is_preserved(self):
        changed = deepcopy(self.pose)
        changed.frac[45:, 2] += .5 / 20
        self.assertAlmostEqual(distance_metrics(changed, self.reference)["full_RMSD_A"], .5, places=12)

    def test_movable_fe_change_is_not_erased(self):
        changed = deepcopy(self.pose)
        changed.frac[18, 0] += .05
        result = distance_metrics(changed, self.reference)
        self.assertAlmostEqual(result["minimum_ads_pose_RMSD_A"], 0, places=12)
        self.assertGreater(result["full_RMSD_A"], .08)
        self.assertAlmostEqual(result["movable_Fe_max_displacement_A_at_best_full"], .45, places=12)

    def test_different_cell_is_not_same_structure(self):
        changed = deepcopy(self.pose)
        changed.cell[0, 0] += .001
        with self.assertRaises(ValueError):
            distance_metrics(changed, self.reference)

    def test_fixed_and_free_layers_cannot_swap(self):
        rotation = np.diag([1, 1, -1])
        with self.assertRaises(ValueError):
            iron_maps(self.slab, [(rotation, np.asarray([0., 0., .4]))])


class LabelAndBudgetGuards(unittest.TestCase):
    def test_first_step_raw_force_extraction(self):
        data = (b"Iteration 1( 9)\naborting loop because EDIFF is reached\n"
                b"POSITION TOTAL-FORCE (eV/Angst)\n-----\n"
                b"0.0000 0.0000 0.0000 1.0 2.0 3.0\n1.0000 0.0000 0.0000 -1.0 -2.0 -3.0\n"
                b"free  energy   TOTEN  = -10.123 eV\n")
        path = SimpleNamespace(open=lambda _: BytesIO(data))
        row = first_frame(path, 2)
        self.assertTrue(row["EDIFF_marker_before_force"])
        self.assertEqual(row["forces_eV_per_A"][0], [1., 2., 3.])
        self.assertEqual(row["E_TOTEN_eV"], -10.123)
        start, end = row["source_byte_range"]
        self.assertTrue(data[start:end].startswith(b"POSITION TOTAL-FORCE"))

    def test_incomplete_frame_is_not_called_missing_dft(self):
        path = SimpleNamespace(open=lambda _: BytesIO(b"Iteration 1( 9)\n"))
        with self.assertRaises(ValueError):
            first_frame(path, 2)

    def test_same_family_does_not_receive_two_first_batch_slots(self):
        row = {"family_id": "family_0001"}
        reason = rejection_reason(row, [{"family_id": "family_0001"}], {"full_RMSD_A": 1.}, {"full_RMSD_A": 1.})
        self.assertIn("one_representative", reason)

    def test_existing_coordinate_requires_review_before_new_dft(self):
        row = {"family_id": "new"}
        reason = rejection_reason(row, [], {"full_RMSD_A": None}, {"full_RMSD_A": 0.})
        self.assertIn("existing_path_force_label", reason)

    def test_no_runtime_estimate_for_unbound_c4(self):
        with self.assertRaises(KeyError):
            budget_rows([{"composition": "C4H2"}], {})


if __name__ == "__main__":
    unittest.main()
