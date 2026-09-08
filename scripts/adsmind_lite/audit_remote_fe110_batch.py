from __future__ import annotations

import argparse
import base64
import json
import shlex
import subprocess
from typing import Any

import numpy as np

from scripts.adsorption.build_fe110_adsorption import (
    Poscar,
    classify_fe110_anchor_site,
    expanded_symbols,
    fe110_anchor_site_distances,
    minimum_image_delta,
    parse_poscar_text,
)
from scripts.execution_backends import load_execution_backends


ANCHOR_SYMBOL = {
    "CO": "C",
    "H": "H",
    "O": "O",
    "OH": "O",
    "H2O": "O",
    "C": "C",
}


def parse_args() -> argparse.Namespace:
    backend = load_execution_backends().vasp
    parser = argparse.ArgumentParser(description="Read-only Fe(110) batch site audit over SSH.")
    parser.add_argument("--host", default=backend.server_alias)
    parser.add_argument("--remote-root", default="~/sbq/Fe110/adsorption/step12A")
    return parser.parse_args()


def fetch_structures(host: str, remote_root: str) -> dict[str, str]:
    root = f'"$HOME"/{shlex.quote(remote_root[2:])}' if remote_root.startswith("~/") else shlex.quote(remote_root)
    command = (
        f"cd {root} && "
        "for f in clean_static/POSCAR */*/POSCAR */*/CONTCAR; do "
        '[ -f "$f" ] || continue; '
        "printf 'FILE:%s\\n' \"$f\"; base64 -w0 \"$f\"; printf '\\n'; "
        "done"
    )
    completed = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host, command],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    lines = completed.stdout.splitlines()
    payload: dict[str, str] = {}
    for index in range(0, len(lines), 2):
        if index + 1 >= len(lines) or not lines[index].startswith("FILE:"):
            raise ValueError("unexpected remote structure stream")
        path = lines[index][5:]
        payload[path] = base64.b64decode(lines[index + 1]).decode("utf-8")
    return payload


def full_distance(poscar: Poscar, first: int, second: int) -> float:
    delta = minimum_image_delta(poscar.frac[first] - poscar.frac[second])
    return float(np.linalg.norm(delta @ poscar.cell))


def anchor_index(poscar: Poscar, adsorbate: str) -> int:
    symbols = expanded_symbols(poscar)
    anchor = ANCHOR_SYMBOL[adsorbate]
    candidates = [index for index, symbol in enumerate(symbols) if symbol != "Fe" and symbol == anchor]
    if not candidates:
        raise ValueError(f"{adsorbate}: anchor atom {anchor} is missing")
    return candidates[0]


def internal_geometry(poscar: Poscar, adsorbate: str) -> dict[str, Any]:
    symbols = expanded_symbols(poscar)
    non_fe = [index for index, symbol in enumerate(symbols) if symbol != "Fe"]
    result: dict[str, Any] = {}
    if adsorbate == "CO":
        carbon = next(index for index in non_fe if symbols[index] == "C")
        oxygen = next(index for index in non_fe if symbols[index] == "O")
        result["co_angstrom"] = round(full_distance(poscar, carbon, oxygen), 4)
    elif adsorbate == "OH":
        oxygen = next(index for index in non_fe if symbols[index] == "O")
        hydrogen = next(index for index in non_fe if symbols[index] == "H")
        result["oh_angstrom"] = round(full_distance(poscar, oxygen, hydrogen), 4)
    elif adsorbate == "H2O":
        oxygen = next(index for index in non_fe if symbols[index] == "O")
        hydrogens = [index for index in non_fe if symbols[index] == "H"]
        vectors = []
        for hydrogen in hydrogens:
            delta = minimum_image_delta(poscar.frac[hydrogen] - poscar.frac[oxygen]) @ poscar.cell
            vectors.append(delta)
        result["oh_angstrom"] = [round(float(np.linalg.norm(vector)), 4) for vector in vectors]
        cosine = float(np.dot(vectors[0], vectors[1]) / np.linalg.norm(vectors[0]) / np.linalg.norm(vectors[1]))
        result["hoh_degree"] = round(float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))), 3)
    return result


def audit_structure(
    text: str,
    path: str,
    adsorbate: str,
    planned_site: str,
    reference_text: str | None = None,
) -> dict[str, Any]:
    poscar = parse_poscar_text(text, path)
    reference = parse_poscar_text(reference_text, f"{path} reference") if reference_text is not None else poscar
    symbols = expanded_symbols(poscar)
    anchor = anchor_index(poscar, adsorbate)
    site, offset = classify_fe110_anchor_site(poscar, poscar.frac[anchor], reference_poscar=reference)
    reference_anchor_frac = (poscar.frac[anchor] @ poscar.cell) @ np.linalg.inv(reference.cell)
    site_distances = fe110_anchor_site_distances(reference, reference_anchor_frac)
    fe_indices = [index for index, symbol in enumerate(symbols) if symbol == "Fe"]
    adsorbate_indices = [index for index, symbol in enumerate(symbols) if symbol != "Fe"]
    nearest_fe_index = min(fe_indices, key=lambda index: full_distance(poscar, anchor, index))
    nearest_anchor_fe = full_distance(poscar, anchor, nearest_fe_index)
    cartesian = poscar.frac @ poscar.cell
    top_fe_z = float(np.max(cartesian[fe_indices, 2]))
    minimum_contact = min(
        full_distance(poscar, adsorbate_index, fe_index) for adsorbate_index in adsorbate_indices for fe_index in fe_indices
    )
    return {
        "path": path,
        "planned_site": planned_site,
        "classified_site": site,
        "site_match": site == planned_site,
        "lateral_offset_angstrom": round(offset, 4),
        "site_offsets_angstrom": {name: round(distance, 4) for name, distance in site_distances.items()},
        "anchor_fe_angstrom": round(nearest_anchor_fe, 4),
        "nearest_fe_index_1based": nearest_fe_index + 1,
        "anchor_minus_top_fe_z_angstrom": round(float(cartesian[anchor, 2] - top_fe_z), 4),
        "nearest_fe_below_top_angstrom": round(float(top_fe_z - cartesian[nearest_fe_index, 2]), 4),
        "minimum_fe_adsorbate_angstrom": round(minimum_contact, 4),
        "overlap": minimum_contact < 0.8,
        **internal_geometry(poscar, adsorbate),
    }


def main() -> None:
    args = parse_args()
    structures = fetch_structures(args.host, args.remote_root)
    records = []
    for adsorbate in ANCHOR_SYMBOL:
        for planned_site in ("top", "short_bridge", "long_bridge", "hollow"):
            poscar_path = f"{adsorbate}/{planned_site}/POSCAR"
            latest_path = f"{adsorbate}/{planned_site}/CONTCAR"
            initial = audit_structure(structures[poscar_path], poscar_path, adsorbate, planned_site)
            latest = audit_structure(
                structures.get(latest_path, structures[poscar_path]),
                latest_path if latest_path in structures else poscar_path,
                adsorbate,
                planned_site,
                structures[poscar_path],
            )
            records.append(
                {
                    "adsorbate": adsorbate,
                    "planned_site": planned_site,
                    "latest_source": "CONTCAR" if latest_path in structures else "POSCAR",
                    "initial_site": initial["classified_site"],
                    **{key: value for key, value in latest.items() if key not in {"path", "planned_site"}},
                }
            )
    print(json.dumps(records, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
