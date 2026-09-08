from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.adsorption.build_gas_step12a_references import SPECIES as NEW_SPECIES
from scripts.artifact_io import sha256_json
from scripts.registry_write import apply_registry_batch, plan_registry_batch
from scripts.ts_strategy_engine.registry import open_registry
from scripts.artifact_io import sha256_file as sha256


ROOT = Path(__file__).resolve().parents[2]
CALC_ROOT = ROOT / "calculations" / "fe110_step12a_gas_references_20260828"
RESULTS_ROOT = CALC_ROOT / "results"
PROVENANCE = CALC_ROOT / "provenance"
SUBMISSION = PROVENANCE / "submission_manifest.json"
DATABASE = ROOT / "data" / "project_registry.sqlite3"
REFERENCE_CONVENTION = "fe110_gas_pbe_20A_gamma_species_spin_v1"
SURFACE_CONVENTION = "fe110_converged_toten_sigma0p20_v1"
TOTEN_RE = re.compile(r"free\s+energy\s+TOTEN\s*=\s*([-+0-9.Ee]+)\s+eV")
FATAL_MARKERS = ("VERY BAD NEWS", "BRMIX: very serious problems", "ZBRENT: fatal error", "ERROR FEXCF")
CALCULATION_JOBS = {"CO": "9733110", "H": "9733111", "O": "9733112", "OH": "9733113", "C": "9733114"}
ACTIVE_JOBS = {"CO": "9733110", "H": "9733111", "O": "9733112", "OH": "9733121", "C": "9733114"}
H2O_JOB = "9558015"
ADSORPTION_CALCULATIONS = {
    "CO": {
        "top": "fe110_ads_co_top_step12a_job9558184",
        "short_bridge": "fe110_ads_step12a_co_short_bridge_historical_20260828",
        "long_bridge": "fe110_ads_step12a_co_long_bridge_historical_20260828",
    },
    "H": {
        site: f"fe110_ads_step12a_h_{site}_historical_20260828"
        for site in ("top", "short_bridge", "long_bridge", "hollow")
    },
    "O": {
        site: f"fe110_ads_step12a_o_{site}_historical_20260828"
        for site in ("top", "short_bridge", "long_bridge", "hollow")
    },
    "OH": {
        site: f"fe110_ads_step12a_oh_{site}_historical_20260828"
        for site in ("top", "short_bridge", "long_bridge", "hollow")
    },
    "H2O": {"top": "fe110_ads_step12a_h2o_top_historical_20260828"},
    "C": {
        site: f"fe110_ads_step12a_c_{site}_historical_20260828"
        for site in ("top", "short_bridge", "long_bridge")
    },
}




def incar_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("!", 1)[0].split("#", 1)[0]
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip().upper()] = value.strip()
    return values


def parse_poscar(path: Path) -> tuple[list[str], list[list[float]]]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
    scale = float(lines[1])
    cell = [[scale * float(value) for value in lines[index].split()[:3]] for index in (2, 3, 4)]
    elements = lines[5].split()
    counts = [int(value) for value in lines[6].split()]
    index = 7
    if lines[index].lower().startswith("s"):
        index += 1
    direct = lines[index].lower().startswith("d")
    index += 1
    names: list[str] = []
    coordinates: list[list[float]] = []
    for element, count in zip(elements, counts, strict=True):
        for _ in range(count):
            coordinate = [float(value) for value in lines[index].split()[:3]]
            index += 1
            if direct:
                coordinate = [sum(coordinate[k] * cell[k][j] for k in range(3)) for j in range(3)]
            names.append(element)
            coordinates.append(coordinate)
    return names, coordinates


def distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))


def parse_outcar(path: Path) -> dict[str, Any]:
    last_toten: float | None = None
    normal = False
    reached = False
    ediff = False
    fatal: list[str] = []
    collecting = False
    current: list[tuple[float, float, float]] = []
    forces: list[tuple[float, float, float]] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            match = TOTEN_RE.search(raw)
            if match:
                last_toten = float(match.group(1))
            normal |= "General timing and accounting informations for this job" in raw
            reached |= "reached required accuracy - stopping structural energy minimisation" in raw
            ediff |= "aborting loop because EDIFF is reached" in raw
            for marker in FATAL_MARKERS:
                if marker in raw and marker not in fatal:
                    fatal.append(marker)
            if "TOTAL-FORCE (eV/Angst)" in raw:
                collecting = True
                current = []
                continue
            if collecting:
                fields = raw.split()
                if len(fields) >= 6:
                    try:
                        current.append(tuple(float(value) for value in fields[-3:]))
                        continue
                    except ValueError:
                        pass
                if current:
                    forces = current
                    collecting = False
    if collecting and current:
        forces = current
    maximum = max((math.sqrt(sum(value * value for value in force)) for force in forces), default=None)
    return {
        "final_toten_eV": last_toten,
        "normal_completion": normal,
        "reached_required_accuracy": reached,
        "ediff_reached": ediff,
        "fatal_markers": fatal,
        "max_force_eV_A": maximum,
    }


def audit_reference(species: str) -> dict[str, Any]:  # noqa: C901
    folder = RESULTS_ROOT / species
    required = ("POSCAR", "CONTCAR", "INCAR", "KPOINTS", "OUTCAR", "OSZICAR", "vasp.out", "job.sh")
    missing = [name for name in required if not (folder / name).is_file()]
    if missing:
        raise ValueError(f"{species}: missing returned files: {', '.join(missing)}")
    incar = incar_values(folder / "INCAR")
    expected_common = {
        "GGA": "PE",
        "ENCUT": "400",
        "EDIFF": "1E-5",
        "EDIFFG": "-0.02",
        "ISMEAR": "0",
        "SIGMA": "0.05",
    }
    for key, expected in expected_common.items():
        if incar.get(key) != expected:
            raise ValueError(f"{species}: incompatible {key}={incar.get(key)!r}")
    if species == "H2O":
        expected_spin = {"ispin": 1, "magmom": None, "nupdown": None}
    else:
        model = NEW_SPECIES[species]
        expected_spin = {
            "ispin": model["ispin"],
            "magmom": model.get("magmom"),
            "nupdown": model.get("nupdown"),
        }
    if int(incar["ISPIN"]) != expected_spin["ispin"]:
        raise ValueError(f"{species}: incompatible ISPIN")
    if expected_spin["magmom"] is None:
        if "MAGMOM" in incar or "NUPDOWN" in incar:
            raise ValueError(f"{species}: closed-shell branch contains spin constraints")
    elif incar.get("MAGMOM") != expected_spin["magmom"] or int(incar.get("NUPDOWN", -99)) != expected_spin["nupdown"]:
        raise ValueError(f"{species}: incompatible open-shell MAGMOM/NUPDOWN")
    kpoints = [line.strip() for line in (folder / "KPOINTS").read_text().splitlines()]
    if len(kpoints) < 4 or kpoints[2].lower() != "gamma" or kpoints[3].split()[:3] != ["1", "1", "1"]:
        raise ValueError(f"{species}: incompatible KPOINTS")
    parsed = parse_outcar(folder / "OUTCAR")
    if not (
        parsed["normal_completion"]
        and parsed["reached_required_accuracy"]
        and parsed["ediff_reached"]
        and not parsed["fatal_markers"]
        and parsed["final_toten_eV"] is not None
        and parsed["max_force_eV_A"] is not None
        and parsed["max_force_eV_A"] <= 0.02000001
    ):
        raise ValueError(f"{species}: electronic/ionic/force completion gate failed: {parsed}")
    names, coordinates = parse_poscar(folder / "CONTCAR")
    geometry: dict[str, Any] = {"names": names}
    if species == "CO":
        geometry["bond_A"] = distance(coordinates[0], coordinates[1])
        if not 1.0 <= geometry["bond_A"] <= 1.3:
            raise ValueError(f"CO: invalid final bond {geometry['bond_A']}")
    elif species == "OH":
        geometry["bond_A"] = distance(coordinates[0], coordinates[1])
        if not 0.8 <= geometry["bond_A"] <= 1.2:
            raise ValueError(f"OH: invalid final bond {geometry['bond_A']}")
    elif species == "H2O":
        geometry["oh_A"] = [distance(coordinates[0], coordinates[1]), distance(coordinates[0], coordinates[2])]
        if any(not 0.8 <= value <= 1.2 for value in geometry["oh_A"]):
            raise ValueError(f"H2O: invalid final O-H distances {geometry['oh_A']}")
    files = {}
    for path in folder.iterdir():
        if path.is_file():
            stat = path.stat()
            files[path.name] = {
                "byte_size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "sha256": sha256(path),
            }
    return {"species": species, "incar": incar, "technical": parsed, "geometry": geometry, "files": files}


def accepted_energy(connection: Any, calculation_id: str) -> tuple[float, str]:
    row = connection.execute(
        """
        SELECT numeric_value, source_file_id FROM results
        WHERE calculation_id=? AND lower(result_name) IN ('final_toten', 'final_toten')
          AND validation_status='accepted_compatible_final_energy'
        ORDER BY created_at DESC LIMIT 1
        """,
        (calculation_id,),
    ).fetchone()
    if row is None or row["numeric_value"] is None or row["source_file_id"] is None:
        raise ValueError(f"missing accepted final energy for {calculation_id}")
    return float(row["numeric_value"]), str(row["source_file_id"])


def build_batch(checked_at: str) -> tuple[dict[str, Any], dict[str, Any]]:
    audits = {species: audit_reference(species) for species in (*ACTIVE_JOBS, "H2O")}
    rows: dict[str, list[dict[str, Any]]] = {
        name: []
        for name in (
            "calculations",
            "jobs",
            "job_status_history",
            "files",
            "results",
            "reviews",
            "calculation_compatibility",
        )
    }
    status_changes: list[dict[str, Any]] = []
    reference_energies = {species: audit["technical"]["final_toten_eV"] for species, audit in audits.items()}
    for species, job_id in ACTIVE_JOBS.items():
        calculation_id = f"fe110_gas_{species}_{CALCULATION_JOBS[species]}"
        job_record_id = f"job_fe110_gas_{species}_{job_id}"
        audit = audits[species]
        remote = (
            "~/sbq/Fe110/gas/OH/relax_restart_20260828"
            if species == "OH"
            else f"~/sbq/Fe110/gas/{species}/relax"
        )
        rows["job_status_history"].append(
            {
                "job_record_id": job_record_id,
                "scheduler_status": "DONE",
                "scientific_status": "accepted_compatible_gas_reference",
                "checked_at": checked_at,
                "source_command": f"ssh sunboquan-codex bjobs -a {job_id}",
                "source_text": f"Job <{job_id}> terminal DONE; raw VASP evidence returned and reviewed.",
                "reviewer": "Codex",
            }
        )
        output_file_ids: dict[str, str] = {}
        for filename in ("CONTCAR", "OUTCAR", "OSZICAR", "vasp.out"):
            meta = audit["files"][filename]
            file_id = f"file_{calculation_id}_{filename.replace('.', '_')}_final"
            rows["files"].append(
                {
                    "file_id": file_id,
                    "calculation_id": calculation_id,
                    "job_record_id": job_record_id,
                    "role": {"CONTCAR": "final_structure", "OUTCAR": "final_output", "OSZICAR": "ionic_log", "vasp.out": "runtime_log"}[filename],
                    "filename": filename,
                    "local_path": str((RESULTS_ROOT / species / filename).resolve()),
                    "remote_path": f"{remote}/{filename}",
                    "storage_mode": "repository",
                    "byte_size": meta["byte_size"],
                    "modified_at": meta["modified_at"],
                    "sha256": meta["sha256"],
                    "existence_status": "confirmed",
                    "license_or_sensitivity": "project_internal",
                }
            )
            output_file_ids[filename] = file_id
        rows["results"].extend(
            [
                {
                    "result_id": f"{calculation_id}-final-toten",
                    "calculation_id": calculation_id,
                    "result_name": "final_toten",
                    "numeric_value": audit["technical"]["final_toten_eV"],
                    "unit": "eV",
                    "reference_convention": REFERENCE_CONVENTION,
                    "source_file_id": output_file_ids["OUTCAR"],
                    "source_locator": "last free energy TOTEN in final OUTCAR",
                    "extraction_method": "regex_last_final_OUTCAR_TOTEN",
                    "validation_status": "accepted_compatible_final_energy",
                    "created_at": checked_at,
                    "notes": "Electronic gas-reference energy; no ZPE, entropy, or thermal correction.",
                },
                {
                    "result_id": f"{calculation_id}-max-force",
                    "calculation_id": calculation_id,
                    "result_name": "final_max_force",
                    "numeric_value": audit["technical"]["max_force_eV_A"],
                    "unit": "eV/A",
                    "source_file_id": output_file_ids["OUTCAR"],
                    "validation_status": "accepted_converged_force",
                    "created_at": checked_at,
                },
            ]
        )
        rows["reviews"].append(
            {
                "review_id": f"review_{calculation_id}_completion",
                "calculation_id": calculation_id,
                "review_type": "gas_reference_completion_validation",
                "decision": "PASS_ACCEPTED_REFERENCE",
                "reviewer": "Codex",
                "reviewed_at": checked_at,
                "evidence": json.dumps(audit, sort_keys=True),
                "reason": "Normal termination, electronic/ionic/force convergence, locked method and spin branch, and final molecular geometry passed.",
            }
        )
        status_changes.append(
            {
                "status_change_id": f"status-{calculation_id}-accepted",
                "calculation_id": calculation_id,
                "expected_workflow_status": "submitted_pending",
                "new_workflow_status": "energy_accepted",
                "changed_at": checked_at,
                "reviewer": "Codex",
                "reason": "Compatible gas-reference completion review passed.",
            }
        )

    h2o = audits["H2O"]
    h2o_calc = f"fe110_gas_H2O_{H2O_JOB}"
    h2o_job_record = f"job_fe110_gas_H2O_{H2O_JOB}"
    h2o_remote = "~/sbq/Fe110/gas/H2O/relax"
    rows["calculations"].append(
        {
            "calculation_id": h2o_calc,
            "module": "adsorption_workflow",
            "purpose": "Compatible isolated H2O reference for Fe(110) adsorption energies",
            "scientific_system": "isolated_H2O_20A_gamma",
            "workflow_status": "energy_accepted",
            "created_at": h2o["files"]["POSCAR"]["modified_at"],
            "source_record": "modules/catalysis_data_retrieval/outputs/20260629_h2o_gas/handoff.json",
            "notes": "Whitelist-seeded H2O geometry; energy is from the compatible local VASP calculation only.",
        }
    )
    rows["jobs"].append(
        {
            "job_record_id": h2o_job_record,
            "calculation_id": h2o_calc,
            "scheduler_job_id": H2O_JOB,
            "scheduler": "LSF",
            "server_alias": "sunboquan-codex",
            "queue": "Gkn_normal",
            "remote_directory": h2o_remote,
            "submit_script": "job.sh",
            "finished_at": h2o["files"]["OUTCAR"]["modified_at"],
        }
    )
    rows["job_status_history"].append(
        {
            "job_record_id": h2o_job_record,
            "scheduler_status": "DONE",
            "scientific_status": "accepted_compatible_gas_reference",
            "checked_at": checked_at,
            "source_command": "Historical job 9558015 plus live raw-file audit",
            "reviewer": "Codex",
        }
    )
    h2o_file_ids: dict[str, str] = {}
    for filename, meta in h2o["files"].items():
        file_id = f"file_{h2o_calc}_{filename.replace('.', '_')}"
        rows["files"].append(
            {
                "file_id": file_id,
                "calculation_id": h2o_calc,
                "job_record_id": h2o_job_record,
                "role": "final_output" if filename == "OUTCAR" else "final_structure" if filename == "CONTCAR" else "calculation_evidence",
                "filename": filename,
                "local_path": str((RESULTS_ROOT / "H2O" / filename).resolve()),
                "remote_path": f"{h2o_remote}/{filename}",
                "storage_mode": "repository",
                "byte_size": meta["byte_size"],
                "modified_at": meta["modified_at"],
                "sha256": meta["sha256"],
                "existence_status": "confirmed",
                "license_or_sensitivity": "project_internal",
            }
        )
        h2o_file_ids[filename] = file_id
    rows["files"].append(
        {
            "file_id": f"file_{h2o_calc}_POTCAR",
            "calculation_id": h2o_calc,
            "job_record_id": h2o_job_record,
            "role": "licensed_runtime_input",
            "filename": "POTCAR",
            "remote_path": f"{h2o_remote}/POTCAR.link",
            "storage_mode": "external_path_reference",
            "sha256": "52903520fd107a2a9d75ca9368f690537cdc0294bf7c59d8be552e936fdb6147",
            "existence_status": "confirmed",
            "license_or_sensitivity": "licensed_vasp_potential_no_local_copy",
        }
    )
    rows["results"].append(
        {
            "result_id": f"{h2o_calc}-final-toten",
            "calculation_id": h2o_calc,
            "result_name": "final_toten",
            "numeric_value": h2o["technical"]["final_toten_eV"],
            "unit": "eV",
            "reference_convention": REFERENCE_CONVENTION,
            "source_file_id": h2o_file_ids["OUTCAR"],
            "source_locator": "last free energy TOTEN in final OUTCAR",
            "extraction_method": "regex_last_final_OUTCAR_TOTEN",
            "validation_status": "accepted_compatible_final_energy",
            "created_at": checked_at,
        }
    )
    h2o_compat = json.dumps(
        {
            "code": "VASP 5.4.1",
            "xc": "PE",
            "encut_eV": 400.0,
            "ediff_eV": 1e-5,
            "ediffg_eV_A": -0.02,
            "ispin": 1,
            "ismear": 0,
            "sigma_eV": 0.05,
            "cell_A": [20.0, 20.0, 20.0],
            "kmesh": [1, 1, 1],
            "potcar_sha256": "52903520fd107a2a9d75ca9368f690537cdc0294bf7c59d8be552e936fdb6147",
            "reference_convention": REFERENCE_CONVENTION,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    rows["calculation_compatibility"].append(
        {
            "calculation_id": h2o_calc,
            "compatibility_fingerprint": hashlib.sha256(h2o_compat.encode()).hexdigest(),
            "compatibility_json": h2o_compat,
            "reviewer": "Codex",
            "reviewed_at": checked_at,
        }
    )
    rows["reviews"].append(
        {
            "review_id": f"review_{h2o_calc}_completion",
            "calculation_id": h2o_calc,
            "review_type": "gas_reference_completion_validation",
            "decision": "PASS_ACCEPTED_REFERENCE",
            "reviewer": "Codex",
            "reviewed_at": checked_at,
            "evidence": json.dumps(h2o, sort_keys=True),
            "reason": "Normal termination, convergence, closed-shell method, and intact H2O geometry passed.",
        }
    )

    with open_registry(DATABASE) as connection:
        clean_energy, clean_file_id = accepted_energy(connection, "fe110_clean_relax_job9557161_sigma0p20")
        for species, sites in ADSORPTION_CALCULATIONS.items():
            reference = float(reference_energies[species])
            for site, calculation_id in sites.items():
                adsorbed_energy, adsorbed_file_id = accepted_energy(connection, calculation_id)
                adsorption_energy = adsorbed_energy - clean_energy - reference
                result_id = f"{calculation_id}-adsorption-energy-direct-gas-v1"
                formula = (
                    f"Eads=E({species}*)-E(clean)-E({species}_gas); "
                    f"surface={SURFACE_CONVENTION}; gas={REFERENCE_CONVENTION}"
                )
                rows["results"].append(
                    {
                        "result_id": result_id,
                        "calculation_id": calculation_id,
                        "result_name": "adsorption_energy",
                        "numeric_value": adsorption_energy,
                        "unit": "eV",
                        "reference_convention": formula,
                        "source_file_id": adsorbed_file_id,
                        "source_locator": f"adsorbed={adsorbed_file_id}; clean={clean_file_id}; gas={species}",
                        "extraction_method": "three_term_electronic_energy_difference",
                        "validation_status": "accepted_compatible_adsorption_energy",
                        "uncertainty_text": "Electronic adsorption energy only; no ZPE, entropy, or finite-temperature correction.",
                        "created_at": checked_at,
                        "notes": "Negative means exothermic adsorption from the direct isolated gas/atomic reference.",
                    }
                )
                rows["reviews"].append(
                    {
                        "review_id": f"review_{calculation_id}_adsorption_energy_direct_gas_v1",
                        "calculation_id": calculation_id,
                        "review_type": "adsorption_energy_reference_tuple",
                        "decision": "PASS_ACCEPTED_ENERGY",
                        "reviewer": "Codex",
                        "reviewed_at": checked_at,
                        "evidence": json.dumps(
                            {
                                "adsorbed_eV": adsorbed_energy,
                                "clean_eV": clean_energy,
                                "gas_eV": reference,
                                "adsorption_eV": adsorption_energy,
                                "species": species,
                                "site": site,
                            },
                            sort_keys=True,
                        ),
                        "reason": "Adsorbed, clean-slab, and direct gas/atomic reference energies passed their owning convergence, geometry, and compatibility gates.",
                    }
                )
    summary = {
        "reference_energies_eV": reference_energies,
        "adsorption_energy_count": sum(len(sites) for sites in ADSORPTION_CALCULATIONS.values()),
        "audits": audits,
        "submission_sha256": sha256(SUBMISSION),
    }
    batch = {
        "schema_version": 1,
        "document_kind": "calculation_registry_batch",
        "batch_id": "fe110-step12a-gas-reference-completion-and-adsorption-energies-20260828",
        "created_at": checked_at,
        "reviewer": "User-authorized Codex gas-reference workflow",
        "reason": "Accept six compatible Step 12A gas/atomic references and compute nineteen unique adsorption energies.",
        "rows": rows,
        "workflow_status_changes": status_changes,
    }
    return batch, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize Step 12A gas references and adsorption energies.")
    parser.add_argument("command", choices=("plan", "apply"))
    parser.add_argument("--checked-at", required=True)
    parser.add_argument("--confirm-sha256")
    args = parser.parse_args()
    batch, summary = build_batch(args.checked_at)
    (PROVENANCE / "completion_review.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (PROVENANCE / "registry_completion_batch.json").write_text(
        json.dumps(batch, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    if args.command == "plan":
        result = plan_registry_batch(DATABASE, batch)
        output = PROVENANCE / "registry_completion_plan.json"
    else:
        if not args.confirm_sha256:
            raise ValueError("apply requires --confirm-sha256")
        result = apply_registry_batch(DATABASE, batch, confirmed_sha256=args.confirm_sha256)
        output = PROVENANCE / "registry_completion_receipt.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({**result, "manifest_sha256": sha256_json(batch)}, indent=2))


if __name__ == "__main__":
    main()
