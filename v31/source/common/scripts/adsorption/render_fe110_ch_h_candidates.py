from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from scripts.adsorption.build_fe110_adsorption import (
    fe110_rule_defaults,
    identify_top_layer,
    read_poscar,
)
from scripts.workflow_geometry import pbc_xy_distance


COLORS = {"Fe": "#9ca3af", "C": "#111827", "H_CH": "#38bdf8", "H_in": "#f97316"}


def _plot_candidate(ax_top, ax_side, poscar: Path, title: str) -> None:
    structure = read_poscar(poscar)
    cart = structure.frac @ structure.cell
    top_indices = identify_top_layer(structure, fe110_rule_defaults()["z_tolerance"])

    ax_top.scatter(cart[top_indices, 0], cart[top_indices, 1], s=180, c=COLORS["Fe"], edgecolors="white")
    ax_side.scatter(cart[:18, 1], cart[:18, 2], s=70, c="#6b7280", edgecolors="white")
    ax_side.scatter(cart[18:45, 1], cart[18:45, 2], s=90, c=COLORS["Fe"], edgecolors="white")

    labels = ((45, "C", 120), (46, "H_CH", 95), (47, "H_in", 95))
    for index, label, size in labels:
        ax_top.scatter(cart[index, 0], cart[index, 1], s=size, c=COLORS[label], edgecolors="white", zorder=5)
        ax_side.scatter(cart[index, 1], cart[index, 2], s=size, c=COLORS[label], edgecolors="white", zorder=5)

    ax_top.plot(cart[[45, 46], 0], cart[[45, 46], 1], color=COLORS["H_CH"], linewidth=2.0)
    ax_top.plot(cart[[45, 47], 0], cart[[45, 47], 1], color=COLORS["H_in"], linewidth=1.5, linestyle="--")
    ax_side.plot(cart[[45, 46], 1], cart[[45, 46], 2], color=COLORS["H_CH"], linewidth=2.0)
    ax_side.plot(cart[[45, 47], 1], cart[[45, 47], 2], color=COLORS["H_in"], linewidth=1.5, linestyle="--")

    target_distance = pbc_xy_distance(structure.cell, cart[45], cart[47])
    ax_top.set_title(f"{title}\nC···H = {target_distance:.3f} Å", fontsize=10)
    ax_top.set_xlabel("x (Å)")
    ax_top.set_ylabel("y (Å)")
    ax_side.set_xlabel("y (Å)")
    ax_side.set_ylabel("z (Å)")
    ax_top.set_aspect("equal", adjustable="box")
    ax_side.set_aspect("equal", adjustable="box")
    for ax in (ax_top, ax_side):
        ax.grid(alpha=0.15)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render top and side views of Fe(110) CH+H candidates.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("candidate", nargs="+", help="TITLE=POSCAR")
    args = parser.parse_args()

    parsed: list[tuple[str, Path]] = []
    for item in args.candidate:
        title, separator, raw_path = item.partition("=")
        if not separator:
            raise ValueError(f"candidate must use TITLE=POSCAR syntax: {item}")
        parsed.append((title, Path(raw_path)))

    figure, axes = plt.subplots(2, len(parsed), figsize=(5.2 * len(parsed), 8.4), constrained_layout=True)
    if len(parsed) == 1:
        axes = np.asarray(axes).reshape(2, 1)
    for column, (title, poscar) in enumerate(parsed):
        _plot_candidate(axes[0, column], axes[1, column], poscar, title)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, dpi=240, facecolor="white")
    plt.close(figure)


if __name__ == "__main__":
    main()
