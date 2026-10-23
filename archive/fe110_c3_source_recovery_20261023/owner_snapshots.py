"""Exact archived owner-function snapshots; historical audit only, no execution authority."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import numpy as np
from scripts.adsorption.build_fe110_adsorption import Poscar, expanded_symbols
from scripts.adsorption.build_fe110_care_isomers import adsorbate_indices, connectivity
from scripts.vasp_result_gate import read_incar_values
from scripts.scientific_validation import finite_number, integer_number
from scripts.workflow_geometry import minimum_image_delta_xy
from .vasp_parser_snapshot import parse_oszicar, parse_outcar

OWNER_SOURCE_BINDINGS = {'compatibility_checks': {'source_path': 'scripts/adsorption/review_completed_batch.py', 'source_file_sha256': '68e35b8cb6840393588c1ce566db8df1102fcd0049ca1b8f6664c4cb9d2bbe3a', 'extracted_function_utf8_sha256': 'e29b21fc6457095b6d1cd7698c6f246e807e3da23fb8bf130b247b8d5ef49465'}, 'molecular_signature': {'source_path': 'scripts/adsorption/build_fe110_care_batch.py', 'source_file_sha256': '4a163cf4ffd4e21732f1a09d787c224b24a8938a4917de41dd706aeb28191b97', 'extracted_function_utf8_sha256': '6e6ebe165b88710eb18347b423d8b224758d53b243cc9a0a9b2342371409c05e'}, 'final_scf_state': {'source_path': 'scripts/vasp_result_gate.py', 'source_file_sha256': '1e476a2b434ceb39ca3245429c8b9faeb5e74b6b53862c02ae0e1dac72e47883', 'extracted_function_utf8_sha256': '47fddb4fcdfb5f921ebe0dd808bc5d7fbbf0a89e55311d4b427963e6b1c76e54'}, 'final_scf_status': {'source_path': 'scripts/vasp_result_gate.py', 'source_file_sha256': '1e476a2b434ceb39ca3245429c8b9faeb5e74b6b53862c02ae0e1dac72e47883', 'extracted_function_utf8_sha256': '1878891c569bfb64db3977317a8fcd8fa385d643aaf5135982e7484aeaf74b8d'}, 'validate_vasp_relaxation': {'source_path': 'scripts/vasp_result_gate.py', 'source_file_sha256': '1e476a2b434ceb39ca3245429c8b9faeb5e74b6b53862c02ae0e1dac72e47883', 'extracted_function_utf8_sha256': 'ad39d08971b484de1b380ab58937227f3168085521e3b584f1b9eff11be32189'}, 'parser_module': {'source_path': 'scripts/neb_agent/utils_vasp.py', 'source_file_sha256': 'd51741ec727e527f6d0ece6f606b8e014b068406956b2f065dff25ac23d40847'}}


def compatibility_checks(directory, initial, final, clean, manifest, receipt) -> dict:
    values = read_incar_values(directory / "INCAR")
    expected = manifest["builder"]["incar"]
    key_types = {"GGA": str, "ENCUT": float, "EDIFF": float, "EDIFFG": float,
                 "ISPIN": int, "ISMEAR": int, "SIGMA": float, "ISIF": int}
    def flags(pose):
        return [tuple(x.upper() for x in row) for row in pose.flags]
    checks = {key: key_types[key](values[key]) == key_types[key](expected[key]) for key in key_types}
    checks.update(
        dipole_off=values.get("LDIPOL", "F").upper().strip(".") in {"F", "FALSE"},
        atom_order=expanded_symbols(initial) == expanded_symbols(final),
        clean_Fe45=expanded_symbols(final)[:45] == ["Fe"] * 45 and expanded_symbols(final).count("Fe") == 45,
        cell=np.allclose(initial.cell, clean.cell, atol=1e-8, rtol=0) and np.allclose(final.cell, clean.cell, atol=1e-8, rtol=0),
        flags=flags(initial) == flags(final) == [("F", "F", "F")] * 18 + [("T", "T", "T")] * (len(final.frac) - 18),
        fixed_positions=np.max(np.abs(minimum_image_delta_xy(final.frac[:18] - clean.frac[:18]) @ clean.cell)) < 1e-7,
        input_fixed_positions=np.max(np.abs(minimum_image_delta_xy(initial.frac[:18] - clean.frac[:18]) @ clean.cell)) < 1e-7,
        potcar=receipt["remote"]["files"]["POTCAR"]["sha256"] == receipt["submission"]["potcar_sha256"],
    )
    k = (directory / "KPOINTS").read_text().splitlines()
    checks["kmesh"] = k[1].strip() == "0" and k[2].lower().startswith("g") and k[3].split() == ["5", "5", "1"] and all(float(x) == 0 for x in k[4].split())
    moments = [float(value) for term in values["MAGMOM"].split()
               for value in ([term.split("*")[1]] * int(term.split("*")[0]) if "*" in term else [term])]
    checks["magmom"] = moments == [2.2] * 45 + [0.] * (len(final.frac) - 45)
    return {key: bool(value) for key, value in checks.items()}


def molecular_signature(structure: Poscar) -> list:
    """Check C2 H placement and heavy-atom neighbors, not formula alone."""
    indices = adsorbate_indices(structure)
    symbols = [expanded_symbols(structure)[i] for i in indices]
    edges = connectivity(structure, indices)
    signature = []
    for index, symbol in enumerate(symbols):
        neighbors = [symbols[b if a == index else a] for a, b in edges if index in (a, b)]
        if symbol == "H":
            if len(neighbors) != 1 or neighbors[0] == "H":
                raise ValueError("hydrogen is detached or multiply connected in the candidate")
        else:
            signature.append([symbol, neighbors.count("H"), sorted(s for s in neighbors if s != "H")])
    return sorted(signature)


def final_scf_state(parsed: dict, values: dict[str, str], outcar: dict | None = None) -> dict[str, Any]:
    """Interpret already-parsed final cycles, shared by gates and NEB monitoring."""
    if not {"NELM", "EDIFF"} <= values.keys():
        raise ValueError("INCAR missing NELM or EDIFF")
    nelm = integer_number(values["NELM"], "NELM", positive=True)
    ediff = finite_number(values["EDIFF"], "EDIFF", nonnegative=True)
    latest = parsed.get("latest_started_electronic_cycle")
    out = outcar or {}
    final_out = out.get("final_target_step")
    aligned = bool(latest and final_out and latest["cycle"] == final_out["cycle"] and (
        final_out["iteration"] is None or final_out["iteration"] == latest["iteration"]
    ))
    explicit = bool(aligned and out.get("electronic_convergence_reached"))
    complete = bool(latest and not latest["malformed"] and (
        parsed.get("final_target_complete") or explicit
    ))
    if outcar is not None:
        # A complete OSZICAR cycle with both deltas is independent convergence
        # evidence when a compact OUTCAR contains only its normal footer.
        compact_complete = final_out is None and out.get("normal_completion")
        if not compact_complete and (not out.get("exists") or out.get("incomplete") or not aligned):
            complete = False
    iteration = latest["iteration"] if latest else None
    delta_e = latest["delta_e_eV"] if latest else None
    delta_eps = latest["delta_eps_eV"] if latest else None
    numeric = bool(iteration and iteration < nelm and delta_e is not None and delta_eps is not None
                   and ediff > 0 and abs(delta_e) <= ediff and abs(delta_eps) <= ediff)
    converged = bool(complete and iteration and iteration <= nelm and (explicit or numeric))
    incomplete = not complete or (not explicit and (delta_e is None or delta_eps is None))
    return {"last_electronic_iteration": iteration, "last_delta_e_eV": delta_e,
            "last_delta_eps_eV": delta_eps, "ediff_eV": ediff, "nelm": nelm,
            "electronically_converged": converged,
            "electronic_convergence_source": "OUTCAR_EDIFF_TERMINATION" if explicit else "OSZICAR_DELTA_E",
            "latest_started_electronic_cycle": latest,
            "latest_completed_electronic_cycle": parsed.get("latest_completed_electronic_cycle"),
            "final_target_step": latest, "final_target_complete": complete,
            "final_target_explicit_convergence": explicit,
            "incomplete": incomplete,
            "status": "PASS" if converged else "INCOMPLETE" if incomplete else "NOT_CONVERGED"}


def final_scf_status(
    oszicar: Path, incar: Path, outcar: Path | None = None, *, include_cycles: bool = False,
) -> dict[str, Any]:
    """Preserve the six-field public summary; opt into explicit cycle details.

    Both views use the same final-state validator. The default remains compatible
    with external force-label schemas that disallow additional fields.
    """
    state = final_scf_state(parse_oszicar(oszicar), read_incar_values(incar),
                            parse_outcar(outcar) if outcar else None)
    if include_cycles:
        return state
    return {key: state[key] for key in (
        "last_electronic_iteration", "last_delta_e_eV", "ediff_eV", "nelm",
        "electronically_converged", "electronic_convergence_source",
    )}


def validate_vasp_relaxation(directory: Path) -> dict[str, Any]:
    required = [directory / name for name in ("INCAR", "POSCAR", "CONTCAR", "OUTCAR", "OSZICAR")]
    missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError("VASP relaxation files missing or empty: " + ", ".join(missing))
    outcar = parse_outcar(directory / "OUTCAR")
    scf = final_scf_state(parse_oszicar(directory / "OSZICAR"), read_incar_values(directory / "INCAR"), outcar)
    errors: list[str] = []
    if not outcar.get("normal_completion"):
        errors.append("normal_completion_missing")
    if outcar.get("fatal_keywords"):
        errors.append("fatal_keywords=" + ",".join(outcar["fatal_keywords"]))
    if not outcar.get("reached_required_accuracy"):
        errors.append("ionic_convergence_missing")
    if not scf["electronically_converged"]:
        errors.append("electronic_convergence_failed")
    if errors:
        raise ValueError("VASP relaxation result gate failed: " + "; ".join(errors))
    return {"normal_completion": True, "ionic_converged": True, **scf}
