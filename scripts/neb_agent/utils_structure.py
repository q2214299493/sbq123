from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from scripts.workflow_geometry import minimum_image_delta_xyz


@dataclass
class Poscar:
    comment: str
    cell: np.ndarray
    symbols: list[str]
    counts: list[int]
    frac: np.ndarray
    selective: bool
    flags: list[tuple[str, str, str]]

    @property
    def labels(self) -> list[str]:
        return [symbol for symbol, count in zip(self.symbols, self.counts) for _ in range(count)]

    @property
    def atom_count(self) -> int:
        return int(sum(self.counts))


def read_poscar(path: Path) -> Poscar:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 8:
        raise ValueError(f"Incomplete POSCAR: {path}")
    scale = float(lines[1].split()[0])
    raw_cell = np.array([[float(x) for x in lines[i].split()[:3]] for i in range(2, 5)])
    if scale < 0:
        target_volume = abs(scale)
        factor = (target_volume / abs(np.linalg.det(raw_cell))) ** (1.0 / 3.0)
    else:
        factor = scale
    cell = raw_cell * factor
    symbols = lines[5].split()
    counts = [int(x) for x in lines[6].split()]
    index = 7
    selective = lines[index].strip().lower().startswith("s")
    if selective:
        index += 1
    direct = lines[index].strip().lower().startswith(("d", "f"))
    index += 1
    atom_count = sum(counts)
    coords = np.array([[float(x) for x in lines[index + i].split()[:3]] for i in range(atom_count)])
    flags: list[tuple[str, str, str]] = []
    for i in range(atom_count):
        fields = lines[index + i].split()
        flags.append(tuple(value.upper()[0] for value in fields[3:6]) if selective else tuple())
    frac = coords if direct else (coords * factor) @ np.linalg.inv(cell)
    return Poscar(lines[0].strip(), cell, symbols, counts, frac, selective, flags)


def write_poscar(path: Path, structure: Poscar) -> None:
    lines = [structure.comment, "1.0"]
    lines.extend("  " + "  ".join(f"{value:18.12f}" for value in row) for row in structure.cell)
    lines.append("  " + "  ".join(structure.symbols))
    lines.append("  " + "  ".join(str(value) for value in structure.counts))
    if structure.selective:
        lines.append("Selective dynamics")
    lines.append("Direct")
    for index, row in enumerate(structure.frac):
        line = "  " + "  ".join(f"{value:18.12f}" for value in row)
        if structure.selective:
            line += "   " + "   ".join(structure.flags[index])
        lines.append(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def cell_delta(first: Poscar, second: Poscar) -> float:
    return float(np.max(np.abs(first.cell - second.cell)))


def minimum_image_delta(frac_from: np.ndarray, frac_to: np.ndarray) -> np.ndarray:
    return minimum_image_delta_xyz(np.asarray(frac_to) - np.asarray(frac_from))


def displacement_cart(structure: Poscar, frac_from: np.ndarray, frac_to: np.ndarray) -> np.ndarray:
    return minimum_image_delta(frac_from, frac_to) @ structure.cell


def pbc_distance(structure: Poscar, i: int, j: int) -> float:
    return float(np.linalg.norm(displacement_cart(structure, structure.frac[i], structure.frac[j])))


def max_neighbor_step(first: Poscar, second: Poscar, indices: list[int] | None = None) -> float:
    use = indices if indices is not None else list(range(first.atom_count))
    return max(float(np.linalg.norm(displacement_cart(first, first.frac[i], second.frac[i]))) for i in use)


def minimum_pair_distance(structure: Poscar) -> tuple[float, tuple[int, int]]:
    best = (float("inf"), (-1, -1))
    for i in range(structure.atom_count):
        for j in range(i):
            distance = pbc_distance(structure, i, j)
            if distance < best[0]:
                best = (distance, (j, i))
    return best


def compatible(first: Poscar, second: Poscar, cell_tolerance: float = 1e-6) -> list[str]:
    errors: list[str] = []
    if first.atom_count != second.atom_count:
        errors.append("atom_count_mismatch")
    if first.symbols != second.symbols or first.counts != second.counts:
        errors.append("species_or_order_mismatch")
    if cell_delta(first, second) > cell_tolerance:
        errors.append("cell_mismatch")
    if first.selective != second.selective or first.flags != second.flags:
        errors.append("selective_dynamics_mismatch")
    return errors


def numbered_image_dirs(workdir: Path) -> list[Path]:
    return sorted(path for path in workdir.iterdir() if path.is_dir() and path.name.isdigit())


def preferred_image_structure(directory: Path) -> Path:
    contcar = directory / "CONTCAR"
    if contcar.is_file() and contcar.stat().st_size > 0:
        return contcar
    return directory / "POSCAR"


def copy_with_frac(template: Poscar, frac: np.ndarray, comment: str) -> Poscar:
    return Poscar(
        comment, template.cell.copy(), list(template.symbols), list(template.counts), frac.copy(), template.selective, list(template.flags)
    )


def write_xyz(path: Path, structures: list[Poscar], comments: list[str] | None = None) -> None:
    lines: list[str] = []
    for image_index, structure in enumerate(structures):
        lines.append(str(structure.atom_count))
        lines.append(comments[image_index] if comments else f"image={image_index}")
        cart = structure.frac @ structure.cell
        for label, position in zip(structure.labels, cart):
            lines.append(f"{label:2s} {position[0]:16.9f} {position[1]:16.9f} {position[2]:16.9f}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
