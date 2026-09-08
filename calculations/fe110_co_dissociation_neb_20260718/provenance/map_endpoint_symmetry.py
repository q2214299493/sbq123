from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import linear_sum_assignment

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.neb_agent.utils_structure import (  # noqa: E402
    Poscar,
    displacement_cart,
    read_poscar,
    write_poscar,
)


def distance(left: Poscar, start: np.ndarray, end: np.ndarray) -> float:
    return float(np.linalg.norm(displacement_cart(left, start, end)))


def mapped_candidate(initial: Poscar, final: Poscar, translation: np.ndarray) -> tuple[Poscar, list[int]]:
    shifted = final.frac + translation
    mapped = np.zeros_like(shifted)
    source_for_target = [-1] * initial.atom_count

    for symbol in initial.symbols:
        symbol_indices = [index for index, label in enumerate(initial.labels) if label == symbol]
        flag_groups = sorted({initial.flags[index] for index in symbol_indices})
        for flags in flag_groups:
            targets = [index for index in symbol_indices if initial.flags[index] == flags]
            sources = [index for index in symbol_indices if final.flags[index] == flags]
            if len(targets) != len(sources):
                raise ValueError(f"flag-group count mismatch for {symbol} {flags}")
            costs = np.array(
                [[distance(initial, initial.frac[target], shifted[source]) for source in sources] for target in targets]
            )
            target_rows, source_cols = linear_sum_assignment(costs)
            for target_row, source_col in zip(target_rows, source_cols):
                target = targets[int(target_row)]
                source = sources[int(source_col)]
                mapped[target] = shifted[source]
                source_for_target[target] = source

    result = Poscar(
        comment="Fe110 CO dissociation FS symmetry-mapped to Topic-1 CO/top endpoint",
        cell=initial.cell.copy(),
        symbols=list(initial.symbols),
        counts=list(initial.counts),
        frac=mapped,
        selective=initial.selective,
        flags=list(initial.flags),
    )
    return result, source_for_target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--initial", type=Path, required=True)
    parser.add_argument("--final", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    initial = read_poscar(args.initial)
    final = read_poscar(args.final)
    if initial.symbols != final.symbols or initial.counts != final.counts:
        raise ValueError("species/order mismatch")
    if not np.allclose(initial.cell, final.cell, atol=1e-8):
        raise ValueError("cell mismatch")

    candidates: list[dict[str, object]] = []
    for left in range(3):
        for right in range(3):
            translation = np.array([left / 3.0, right / 3.0, 0.0])
            mapped, permutation = mapped_candidate(initial, final, translation)
            displacements = np.array(
                [distance(initial, initial.frac[index], mapped.frac[index]) for index in range(initial.atom_count)]
            )
            candidates.append(
                {
                    "translation_fractional": translation.tolist(),
                    "reaction_max_A": float(displacements[45:47].max()),
                    "reaction_sum_A": float(displacements[45:47].sum()),
                    "all_max_A": float(displacements.max()),
                    "fe_max_A": float(displacements[:45].max()),
                    "displacements_A": displacements.tolist(),
                    "source_index_for_target_zero_based": permutation,
                    "structure": mapped,
                }
            )

    best = min(
        candidates,
        key=lambda item: (
            item["reaction_max_A"],
            item["reaction_sum_A"],
            item["all_max_A"],
            item["fe_max_A"],
        ),
    )
    write_poscar(args.output, best.pop("structure"))
    report = {
        "initial": str(args.initial),
        "source_final": str(args.final),
        "output": str(args.output),
        "method": "3x3 surface-lattice translation grid plus fixed/free and element-preserving Hungarian reordering",
        "selected": best,
        "candidate_scores": [
            {key: value for key, value in item.items() if key not in {"structure", "displacements_A", "source_index_for_target_zero_based"}}
            for item in candidates
        ],
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in best.items() if key != "displacements_A"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
