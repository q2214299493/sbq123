"""Meaningful numerical, graph, provenance and non-chaining guards."""
from __future__ import annotations

import unittest

from .audit import BLOCKED, MISSING, REUSE, component_formulas, force_stats, gap_category, radius_clusters, source_root


class JointAuditTests(unittest.TestCase):
    def test_record_presence_does_not_override_admission_blockers(self):
        self.assertEqual(gap_category(True, False), BLOCKED)
        self.assertEqual(gap_category(True, True), REUSE)
        self.assertEqual(gap_category(False, False), MISSING)

    def test_fixed_force_excluded_and_missing_element_is_none(self):
        row = {"symbols": ["Fe", "Fe", "C"], "DFT_forces_eV_per_A": [[99, 0, 0], [0, 3, 4], [.02, 0, 0]],
               "fixed_atom_indices_0based": [0], "force_role_groups": {"adsorbate_C": [2], "adsorbate_O": [], "near_Fe": [1]}}
        values, atom = force_stats(row)
        self.assertEqual(values["all_movable"]["fmax_eV_A"], 5)
        self.assertIsNone(values["adsorbate_O"]["fmax_eV_A"])
        self.assertEqual(atom["element"], "Fe")

    def test_fragment_formula_not_intact_c3(self):
        self.assertEqual(component_formulas(["C", "C", "C", "O", "H", "H"], [[0, 3], [1, 2], [1, 4], [2, 5]]), ["C2H2", "CO"])

    def test_continuation_jobs_share_explicit_family(self):
        self.assertEqual(source_root({"family_id": "family_0099", "source_job_id": "9922624"})[0], source_root({"family_id": "family_0099", "source_job_id": "9924387"})[0])

    def test_radius_clustering_does_not_chain_or_cross_partitions(self):
        rows = [{"sample_id": name, "partition": split, "qualification_scope": "strict", "composition": "C", "force_bin": "low", "joint_signature": "C:1"} for name, split in [("a", "train"), ("b", "train"), ("c", "train"), ("d", "development")]]
        positions = {"a": 0, "b": .09, "c": .18, "d": 0}
        result = radius_clusters(rows, lambda a, b: abs(positions[a] - positions[b]), .1)
        self.assertEqual(result["b"]["representative_id"], "a")
        self.assertEqual(result["c"]["representative_id"], "c")
        self.assertEqual(result["d"]["representative_id"], "d")

    def test_wrong_role_partition_rejected(self):
        with self.assertRaises(ValueError):
            force_stats({"symbols": ["C"], "DFT_forces_eV_per_A": [[0, 0, 0]], "fixed_atom_indices_0based": [], "force_role_groups": {"adsorbate_C": [0], "other": [0]}})


if __name__ == "__main__":
    unittest.main()
