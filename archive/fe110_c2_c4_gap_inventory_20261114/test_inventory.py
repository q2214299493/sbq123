"""Scientific bookkeeping guard cases; these tests invoke no model or DFT."""
from __future__ import annotations

import unittest

from .collect import vasp5_header
from .coverage import label_status
from .inventory import component_sizes
from .network import reaction_counts


class InventoryGuards(unittest.TestCase):
    def test_title_does_not_determine_carbon_count(self):
        data = b"C6 in a title is not C6 geometry\n1\n1 0 0\n0 1 0\n0 0 1\nFe C H\n45 2 3\nDirect\n"
        self.assertEqual(vasp5_header(data)["total_C"], 2)

    def test_vasp4_is_unknown_not_zero_carbon(self):
        data = b"title\n1\n1 0 0\n0 1 0\n0 0 1\n45 6\nDirect\n0 0 0\n"
        self.assertNotIn("total_C", vasp5_header(data))

    def test_duplicate_species_blocks_are_counted(self):
        data = b"title\n1\n1 0 0\n0 1 0\n0 0 1\nFe C C\n45 2 2\nDirect\n"
        self.assertEqual(vasp5_header(data)["total_C"], 4)

    def test_three_fragments_do_not_make_a_c6_skeleton(self):
        graph = component_sizes(["C"] * 6, [(0, 1), (2, 3), (4, 5)])
        self.assertEqual(graph["total_C"], 6)
        self.assertEqual(graph["largest_C_C_connected_component"], 2)
        self.assertEqual(graph["carbon_counts_per_adsorbate_component"], [2, 2, 2])

    def test_oxygen_bridge_is_not_a_carbon_carbon_bond(self):
        graph = component_sizes(["C", "O", "C"], [(0, 1), (1, 2)])
        self.assertEqual(graph["largest_C_C_connected_component"], 1)
        self.assertEqual(graph["carbon_counts_per_adsorbate_component"], [2])

    def test_stoichiometry_does_not_infer_connectivity(self):
        counts = reaction_counts("C3H* + C3H2* -> C6H3* + *")
        self.assertEqual(counts["total_C_each_side"], 6)
        self.assertEqual(counts["largest_single_formula_C_each_side"], [3, 6])
        self.assertIn("Needs confirmation", counts["connected_carbon_graph"])

    def test_coefficient_and_conservation(self):
        counts = reaction_counts("2C2H3* -> C4H6* + *")
        self.assertEqual(counts["largest_single_formula_C_each_side"], [2, 4])
        with self.assertRaises(ValueError):
            reaction_counts("C2H3* -> C4H6*")

    def test_protected_label_overrides_reuse_candidate(self):
        label = {"partition": "heldout", "energy_force_evidence_ready_for_review": True}
        self.assertEqual(label_status([label]), "PROTECTED_NO_TRAINING")

    def test_energy_scalar_is_not_a_force_label(self):
        label = {"E_TOTEN_eV": -380, "partition": "train"}
        self.assertEqual(label_status([label]), "EXISTING_LABEL_QC_OR_COMPATIBILITY_BLOCKED")

    def test_reuse_review_does_not_grant_admission(self):
        label = {"partition": "train", "energy_force_evidence_ready_for_review": True}
        self.assertEqual(label_status([label]), "EXISTING_E_F_LOCALMAG_REVIEW_CANDIDATE_NOT_NEW_ADMISSION")


if __name__ == "__main__":
    unittest.main()
