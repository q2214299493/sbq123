"""Component-isolated observations; scientific parsers remain with their owners."""
from __future__ import annotations

from collections import deque

import numpy as np

from scripts.neb_agent.outcar_blocks import block_metadata, read_force_blocks
from scripts.neb_agent.utils_structure import read_poscar
from scripts.neb_agent.utils_vasp import parse_oszicar, parse_outcar
from scripts.vasp_result_gate import final_scf_state, read_incar_values


def _observe(result, name, operation):
    try:
        value = operation()
        result["component_status"][name] = "OK"
        return value
    except (OSError, ValueError, TypeError, KeyError, IndexError, ImportError) as exc:
        result["component_status"][name] = "ERROR"
        result["component_errors"].append({"component": name, "error": f"{type(exc).__name__}: {exc}"})
        return None


def _forces(result, files, align):
    blocks = _observe(result, "force_blocks", lambda: read_force_blocks(files["OUTCAR"]))
    if not blocks:
        return
    result["force_block_observations"] = {key: blocks[key] for key in ("block_count", "selected_is_latest_attempt")}
    for key in ("selected", "latest_attempt"):
        result["force_block_observations"][key] = block_metadata(blocks[key]) if blocks[key] else None
    selected = blocks["selected"]
    if selected is None:
        result["component_errors"].append({"component": "force_blocks", "error": "no complete finite position/force table"})
        result["component_status"]["force_blocks"] = "ERROR"
        return
    norms = np.linalg.norm(selected["forces_eV_per_A"], axis=1)
    result["last_complete_force_block"] = {"rows": len(norms), "maximum_all_atoms_eV_per_A": float(norms.max()),
        "binding": block_metadata(selected), "selected_is_latest_attempt": blocks["selected_is_latest_attempt"],
        "scope": "position and force are from this same finite complete table; not automatically the final saved structure"}
    if "CONTCAR" not in files:
        return
    structure = _observe(result, "saved_structure", lambda: read_poscar(files["CONTCAR"]))
    if structure is not None:
        _observe(result, "force_structure_correspondence", lambda: _correspondence(result, selected, structure, norms, align))


def _correspondence(result, selected, structure, norms, align):
    if structure.atom_count != len(norms):
        raise ValueError("force/structure atom count mismatch")
    movable = [i for i, flags in enumerate(structure.flags) if not flags or any(v == "T" for v in flags)]
    result["last_complete_force_block"]["maximum_movable_eV_per_A"] = float(norms[movable].max()) if movable else None
    if align:
        from ase.geometry import find_mic
        delta, _ = find_mic(structure.frac @ structure.cell - np.asarray(selected["positions_A"]), structure.cell, pbc=True)
        result["last_block_to_saved_structure"] = {"maximum_MIC_mismatch_A": float(np.linalg.norm(delta, axis=1).max()),
            "binding": block_metadata(selected), "metric": "same-index MIC position mismatch in A; not an acceptance threshold", "index_base": 0}


def inspect_vasp(catalog, directory, sources, *, align):
    result = {"availability": [], "component_status": {}, "component_errors": [],
              "scheduler": "not queried; process files are not scheduler accounting"}
    files = {}
    for name in ("INCAR", "OSZICAR", "OUTCAR", "POSCAR", "CONTCAR", "vasp.out"):
        pair = _observe(result, "source:" + name, lambda name=name: catalog.file(directory, name))
        if pair is not None:
            path, reference = pair
            result["availability"].append(reference)
            if path:
                files[name] = path
                sources.append(reference)
            else:
                result["component_status"]["source:" + name] = reference["availability"]
    parsed = _observe(result, "oszicar", lambda: parse_oszicar(files["OSZICAR"])) if "OSZICAR" in files else None
    out = _observe(result, "outcar", lambda: parse_outcar(files["OUTCAR"])) if "OUTCAR" in files else None
    for name, value in (("oszicar", parsed), ("outcar", out)):
        if value is not None:
            result[name] = {k: v for k, v in value.items() if k != "electronic_cycles"}
    incar = _observe(result, "incar", lambda: read_incar_values(files["INCAR"])) if "INCAR" in files else None
    if incar is not None:
        result["incar"] = incar
    if parsed is not None and incar is not None:
        result["owner_scf_oszicar_only"] = _observe(result, "scf_oszicar", lambda: final_scf_state(parsed, incar))
        result["owner_scf_combined"] = _observe(result, "scf_combined", lambda: final_scf_state(parsed, incar, out)) if out else None
        result["scf_scope"] = "Existing owner results; disagreements remain, neither view accepts science."
    if "OUTCAR" in files:
        _observe(result, "force_analysis", lambda: _forces(result, files, align))
    if "vasp.out" in files:
        result["stdout_tail"] = _observe(result, "stdout", lambda: _tail(files["vasp.out"]))
    return result


def _tail(path):
    with path.open(encoding="utf-8", errors="replace") as handle:
        return "".join(deque((line[:1000] for line in handle), maxlen=40))[-3000:]
