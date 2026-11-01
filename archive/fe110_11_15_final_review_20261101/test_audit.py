"""Small adapter tests; synthetic coordinates are not scientific results."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from ase import Atoms
from ase.io import write
import numpy as np

from archive.fe110_11_15_final_review_20261101 import audit
from archive.fe110_11_15_final_review_20261101 import summarize
from scripts.adsorption.build_fe110_adsorption import Poscar
from scripts.artifact_io import write_json_exclusive


class AuditBoundaries(unittest.TestCase):
    def test_initialize_refuses_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(audit, "OUT", Path(tmp)):
            with self.assertRaises(FileExistsError):
                audit.initialize()

    def test_analyze_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(audit, "OUT", Path(tmp)):
            output = Path(tmp) / "analysis.json"
            write_json_exclusive(output, {"preserved": True})
            before = output.read_bytes()
            with self.assertRaises(FileExistsError):
                audit.analyze()
            self.assertEqual(before, output.read_bytes())

    def test_unknown_collection_selection_never_connects(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(audit, "OUT", Path(tmp)), \
                patch.object(audit.collector, "collect_snapshot") as remote:
            write_json_exclusive(Path(tmp) / "sources.json", {"records": [{"name": "known"}]})
            with self.assertRaisesRegex(ValueError, "empty collection"):
                audit.collect("unknown")
            remote.assert_not_called()

    def test_bonds_keep_zero_based_indices_and_h_placement(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "POSCAR"
            positions = [[0, 0, 0]] * 45 + [[5, 5, 10], [6.4, 5, 10],
                [5, 5, 11.1], [6.4, 5, 11.1], [7.5, 5, 10]]
            atoms = Atoms("Fe45C2H3", positions=positions, cell=[30, 30, 30], pbc=True)
            write(output, atoms, format="vasp", vasp5=True)
            rows = audit.bond_details(output, {"covalent_radius_scale": 1.25,
                "minimum_bond_distance_angstrom": .35})
            self.assertEqual({tuple(r["atoms_zero_based"]) for r in rows},
                             {(45, 46), (45, 47), (46, 48), (46, 49)})
            self.assertEqual([r["elements"] for r in rows][0], ["C", "C"])

    def test_duplicate_groups_do_not_chain_transitively(self):
        rows = [{"name": n, "toten_eV": e, "blockers": [], "requested_graph_preserved": True}
                for n, e in (("A", -3), ("B", -2), ("C", -1))]
        pairs = [{"first": a, "second": b, "duplicate": d}
                 for a, b, d in (("A", "B", True), ("B", "C", True), ("A", "C", False))]
        groups = summarize.grouped(rows, pairs)
        self.assertEqual([g["members"] for g in groups], [["A", "B"], ["C"]])

    def test_nonconverged_low_energy_is_not_representative(self):
        rows = [{"name": "A", "toten_eV": -3, "blockers": ["force_limit"], "requested_graph_preserved": True},
                {"name": "B", "toten_eV": -2, "blockers": [], "requested_graph_preserved": True}]
        pairs = [{"first": "A", "second": "B", "duplicate": True}]
        self.assertEqual(summarize.grouped(rows, pairs), [{"representative": "B", "members": ["B"]}])

    def test_carbon_exchange_uses_actual_element_indices(self):
        coords = np.zeros((51, 3))
        coords[46, 0], coords[47, 0] = 1., 2.
        pose = Poscar("synthetic", np.eye(3), ["Fe", "O", "C", "H"], [45, 1, 2, 3],
                      coords, [("T", "T", "T")] * 51)
        seen = []

        def comparison(first, second, slab, operations):
            seen.append(second.frac[46, 0])
            score = 1. if len(seen) == 1 else .1
            return {"adsorbate_RMSD_A": score, "slab_RMSD_A": .01, "slab_max_displacement_A": .02}

        with patch.object(audit, "surface_equivalence", side_effect=comparison):
            result = summarize.compare_poses(pose, pose, None, [])
        self.assertEqual(seen, [1., 2.])
        self.assertTrue(result["carbon_exchange"])
        self.assertEqual(pose.frac[46, 0], 1.)


if __name__ == "__main__":
    unittest.main()
