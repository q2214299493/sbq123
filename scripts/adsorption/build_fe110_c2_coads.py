from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path

import numpy as np

from scripts.artifact_io import sha256_file
from scripts.workflow_geometry import pbc_xy_distance

from .build_fe110_adsorption import Poscar, read_poscar, write_poscar
from .c2_coads_catalog import (
    CandidateDefinition,
    initial_candidate_definitions,
    missing_candidate_definitions,
)
from .c2_coads_geometry import GEOMETRY


CandidateFactory = Callable[[Poscar], list[CandidateDefinition]]


def nearest_fe_distances(slab: Poscar, adsorbate_cart: np.ndarray) -> list[float]:
    slab_cart = slab.frac @ slab.cell
    return [min(pbc_xy_distance(slab.cell, atom, fe) for fe in slab_cart) for atom in adsorbate_cart]


def candidate_record(slab: Poscar, definition: CandidateDefinition) -> dict[str, object]:
    adsorbate_cart = definition.structure.frac[sum(slab.counts) :] @ slab.cell
    bonds = {
        bond_name: pbc_xy_distance(slab.cell, adsorbate_cart[first], adsorbate_cart[second])
        for first, second, bond_name in definition.intended_bonds
    }
    record: dict[str, object] = {
        "name": definition.name,
        "species": definition.species,
        "site_label": definition.site_label,
        "relative_rank": "selected minimal candidate set; not a global-minimum claim",
        "poscar": f"{definition.name}/POSCAR",
        "support_fe_indices_1based": [int(index + 1) for index in definition.support_indices],
        "bond_distances_angstrom": bonds,
        "nearest_fe_angstrom": {
            **{
                f"C{index + 1}": value
                for index, value in enumerate(nearest_fe_distances(slab, adsorbate_cart[: definition.carbon_count]))
            },
            **(
                {"O1": nearest_fe_distances(slab, adsorbate_cart[definition.carbon_count :])[0]}
                if len(adsorbate_cart) > definition.carbon_count
                else {}
            ),
        },
    }
    if definition.oxygen_site is not None:
        record["oxygen_site"] = definition.oxygen_site
    return record


def build_candidate_set(
    slab_path: Path,
    output: Path,
    definition_factory: CandidateFactory,
    selection_rule: str,
) -> dict[str, object]:
    """Write reviewed definitions and an UTF-8 manifest; coordinates and distances use Å."""
    slab = read_poscar(slab_path)
    if slab.symbols != ["Fe"] or slab.counts != [45]:
        raise ValueError("builder requires the verified Fe45 clean Fe(110) slab")
    definitions = definition_factory(slab)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for definition in definitions:
        write_poscar(output / definition.name / "POSCAR", definition.structure)
        records.append(candidate_record(slab, definition))
    manifest = {
        "version": 1,
        "surface": "true Fe(110), Fe45, five layers, bottom 18 Fe fixed",
        "source_slab": str(slab_path),
        "source_slab_sha256": sha256_file(slab_path),
        "selection_rule": selection_rule,
        "geometry_parameters_angstrom": GEOMETRY,
        "candidates": records,
    }
    (output / "candidate_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def build(slab_path: Path, output: Path) -> dict[str, object]:
    return build_candidate_set(
        slab_path,
        output,
        initial_candidate_definitions,
        "motif-first minimal set; no blind four-site sweep",
    )


def build_missing(slab_path: Path, output: Path) -> dict[str, object]:
    return build_candidate_set(
        slab_path,
        output,
        missing_candidate_definitions,
        "user-specified missing-only set after registry and scheduler deduplication",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the reviewed minimal Fe(110) C/C2/O coadsorption candidate set.")
    parser.add_argument("--slab", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--candidate-set", choices=("initial", "missing"), default="initial")
    args = parser.parse_args()
    manifest = build(args.slab, args.output) if args.candidate_set == "initial" else build_missing(args.slab, args.output)
    print(f"generated={len(manifest['candidates'])}")
    for item in manifest["candidates"]:
        print(f"{item['name']} | {item['bond_distances_angstrom']}")


if __name__ == "__main__":
    main()
