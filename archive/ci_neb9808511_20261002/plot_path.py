"""Compact actual-coordinate contact sheet for the normalized CI input."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from ase.geometry import find_mic
from scripts.neb_agent.utils_structure import read_poscar
from scripts.artifact_io import load_json_object, source_file_manifest, write_json
from .prepare_ci import CI, RAW

fig, axes = plt.subplots(3, 4, figsize=(14, 9), constrained_layout=True)
chemical = load_json_object(RAW / "parent_chemical_evidence.json")
structures = [read_poscar(CI / f"{i:02d}/POSCAR") for i in range(11)]
cart = [s.frac @ s.cell for s in structures]
lower = np.min(np.concatenate(cart)[:, :2], axis=0) - 0.5
upper = np.max(np.concatenate(cart)[:, :2], axis=0) + 0.5
for i, (ax, s, xyz) in enumerate(zip(axes.flat, structures, cart)):
    ax.scatter(xyz[18:45, 0], xyz[18:45, 1], c="lightgray", s=70, edgecolors="gray")
    for atom, color in [(45, "black"), (46, "black"), (47, "red"), (48, "lightblue"), (49, "blue")]:
        ax.scatter(xyz[atom, 0], xyz[atom, 1], c=color, s=90 if atom < 48 else 50)
        ax.text(xyz[atom, 0]+0.1, xyz[atom, 1]+0.1, str(atom))
    for a,b in [(45,46),(46,47),(45,48)]:
        ax.plot(xyz[[a,b], 0], xyz[[a,b], 1], color="black", lw=1)
    ax.plot([p[49,0] for p in cart], [p[49,1] for p in cart], "b--", alpha=0.35)
    ax.set(xlim=(lower[0], upper[0]), ylim=(lower[1], upper[1]), aspect="equal",
           title=f"{i:02d}: dE={chemical['rows'][i]['toten_eV'] - chemical['rows'][0]['toten_eV']:.3f} eV")
axes.flat[-1].axis("off")
fig.suptitle("NEB9808511 converged restart: top view, H49 migration, no physical geometry changes")
fig.savefig(CI / "path_review_contact_sheet.png", dpi=120)
print(CI / "path_review_contact_sheet.png")
rows = []
for i,s in enumerate(structures):
    pairs = [(45,46),(46,47),(45,48),(47,49),(49,37)]
    distances = [float(find_mic((s.frac[b]-s.frac[a]) @ s.cell, s.cell, pbc=True)[1]) for a,b in pairs]
    rows.append({"image": f"{i:02d}", "toten_eV": chemical['rows'][i]['toten_eV'], "pair_distances_A": distances})
    print(f"{i:02d}", [round(value, 4) for value in distances])
write_json(CI / "chemical_review_evidence.json", {
    "rows": rows, "pairs_zero_based": [[45,46],[46,47],[45,48],[47,49],[49,37]],
    "distance_method": "ASE find_mic for the actual skew lattice; component-wise fractional rounding is not an exact shortest-distance metric here.",
    "source_files": source_file_manifest([CI / f"{i:02d}/POSCAR" for i in range(11)] + [RAW / "parent_chemical_evidence.json"]),
    "scope": "CI refinement readiness only; no final TS or barrier claim."})
