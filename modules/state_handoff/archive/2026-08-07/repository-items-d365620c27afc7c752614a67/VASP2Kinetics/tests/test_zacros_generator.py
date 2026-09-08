"""Tests for Phase 6 static Zacros adapter generation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.kinetics.schema import (
    CalculationInfo,
    Energetics,
    KineticDataset,
    QualityInfo,
    ReactionRecord,
    ReactionStatus,
    SpeciesInfo,
    SystemInfo,
)
from src.zacros.generator import generate_zacros_project

def _record(
    reaction_id: str,
    reactant: list[str],
    product: list[str],
    source_path: Path,
    activation_energy: float | None = 0.98,
    reaction_energy: float | None = 0.2,
) -> ReactionRecord:
    return ReactionRecord(
        reaction_id=reaction_id,
        system=SystemInfo(material="Fe", surface="Fe110", facet="110"),
        species=SpeciesInfo(reactant=reactant, product=product),
        energetics=Energetics(
            E_initial=None,
            E_final=None,
            E_reaction=reaction_energy,
            Ea_forward=activation_energy,
            Ea_reverse=None,
            candidate_TS_energy=None,
        ),
        calculation=CalculationInfo(
            method="VASP",
            functional="PBE",
            source_path=str(source_path),
        ),
        quality=QualityInfo(
            vasp_converged=True,
            ts_verified=False,
            scientific_review=False,
        ),
        status=ReactionStatus.UNVERIFIED,
    )


def _write_inputs(
    directory: Path,
    records: list[ReactionRecord],
    statuses: dict[str, str],
    reaction_sites: dict[str, str],
) -> tuple[Path, Path, Path, Path]:
    dataset_path = directory / "kinetic_dataset.json"
    validation_path = directory / "validation_report.json"
    surface_path = directory / "surface_config.yaml"
    output_path = directory / "zacros_project"
    dataset_path.write_text(
        json.dumps(KineticDataset(records=records).to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    validation_path.write_text(
        json.dumps(
            {
                "checks": [
                    {"reaction_id": reaction_id, "overall_status": status}
                    for reaction_id, status in statuses.items()
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    site_lines = "\n".join(
        f"  {reaction_id}: {site}" for reaction_id, site in reaction_sites.items()
    )
    surface_text = """
surface:
  material: Fe
  facet: 110
  sites:
    - top
    - bridge
    - hollow
""".lstrip()
    if site_lines:
        surface_text += f"reaction_sites:\n{site_lines}\n"
    else:
        surface_text += "reaction_sites: {}\n"
    surface_path.write_text(surface_text, encoding="utf-8")
    return dataset_path, validation_path, surface_path, output_path


class ZacrosGeneratorTests(unittest.TestCase):
    """Cover conversion, warnings, rejection, and provenance."""

    def test_normal_reaction_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            record = _record("r1", ["CO*"], ["C*", "O*"], temp_path)
            dataset, validation, surface, output = _write_inputs(
                temp_path,
                [record],
                {"r1": "PASS"},
                {"r1": "bridge"},
            )
            before = {
                "dataset": dataset.read_bytes(),
                "validation": validation.read_bytes(),
                "surface": surface.read_bytes(),
            }

            report = generate_zacros_project(
                dataset,
                validation,
                surface,
                output,
                allow_warning=True,
            )
            lattice = (output / "lattice_input.dat").read_text(encoding="utf-8")
            mechanism = (output / "mechanism_input.dat").read_text(encoding="utf-8")
            energetics = (output / "energetics_input.dat").read_text(encoding="utf-8")
            mapping = json.loads((output / "mapping.json").read_text(encoding="utf-8"))
            after = {
                "dataset": dataset.read_bytes(),
                "validation": validation.read_bytes(),
                "surface": surface.read_bytes(),
            }

        self.assertEqual(report["generated"], 1)
        self.assertEqual(report["failed"], 0)
        self.assertIn("facet: 110", lattice)
        self.assertIn("site_type: bridge", lattice)
        self.assertIn("reaction: CO* -> C* + O*", mechanism)
        self.assertIn("sites: bridge", mechanism)
        self.assertIn("barrier: 0.98", mechanism)
        self.assertIn("Ea: 0.98", energetics)
        self.assertIn("E_reaction: 0.2", energetics)
        self.assertEqual(mapping["r1"]["zacros_id"], 1)
        self.assertEqual(mapping["r1"]["source_path"], str(temp_path))
        self.assertEqual(mapping["r1"]["activation_energy"], 0.98)
        self.assertEqual(before, after)

    def test_species_are_deduplicated_without_renaming(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            first = _record("r1", ["CO*"], ["C*", "O*"], temp_path)
            second = _record("r2", ["C*", "O*"], ["CO*"], temp_path)
            dataset, validation, surface, output = _write_inputs(
                temp_path,
                [first, second],
                {"r1": "PASS", "r2": "PASS"},
                {"r1": "bridge", "r2": "top"},
            )

            generate_zacros_project(
                dataset,
                validation,
                surface,
                output,
                allow_warning=True,
            )
            species = (output / "species_input.dat").read_text(encoding="utf-8")

        self.assertEqual(species.splitlines(), ["CO*", "C*", "O*"])

    def test_missing_site_is_warning_without_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            record = _record("r1", ["CO*"], ["C*", "O*"], temp_path)
            dataset, validation, surface, output = _write_inputs(
                temp_path,
                [record],
                {"r1": "PASS"},
                {},
            )

            report = generate_zacros_project(
                dataset,
                validation,
                surface,
                output,
                allow_warning=True,
            )
            mechanism = (output / "mechanism_input.dat").read_text(encoding="utf-8")

        self.assertEqual(report["generated"], 1)
        self.assertEqual(report["warnings"], 1)
        self.assertIn("missing site information", report["warning_reactions"][0]["reasons"])
        self.assertIn("sites: NOT_AVAILABLE", mechanism)

    def test_missing_barrier_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            record = _record("r1", ["CO*"], ["C*", "O*"], temp_path, None)
            dataset, validation, surface, output = _write_inputs(
                temp_path,
                [record],
                {"r1": "WARNING"},
                {"r1": "bridge"},
            )

            report = generate_zacros_project(
                dataset,
                validation,
                surface,
                output,
                allow_warning=True,
            )

        self.assertEqual(report["generated"], 0)
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["errors"][0]["reason"], "missing activation energy")

    def test_failed_validation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            record = _record("r1", ["CO*"], ["C*", "O*"], temp_path)
            dataset, validation, surface, output = _write_inputs(
                temp_path,
                [record],
                {"r1": "FAILED"},
                {"r1": "bridge"},
            )

            report = generate_zacros_project(
                dataset,
                validation,
                surface,
                output,
                allow_warning=True,
            )

        self.assertEqual(report["generated"], 0)
        self.assertEqual(report["errors"][0]["reason"], "validation status FAILED")


if __name__ == "__main__":
    unittest.main()
