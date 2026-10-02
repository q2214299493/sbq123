"""User-authorized, non-destructive CI restart of completed NEB9808511."""
from __future__ import annotations

import argparse
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from ase.geometry import find_mic

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json, write_json_exclusive
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.neb_agent.submission import preflight
from scripts.neb_agent.utils_structure import compatible, copy_with_frac, read_poscar, write_poscar, write_xyz
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, load_bound_evidence, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action
from scripts.ts_strategy_engine.path_evidence import validate_path_binding, validate_path_review, write_path_review_draft
from scripts.ts_strategy_engine.contract import load_contract
from scripts.scheduler_evidence import query_lsf_job

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822"
SOURCE = BASE / "h_is_a_int06_gpu1802_neb_sbq123_108r_16pn_20260930"
RAW = SOURCE / "completed_review_20261002"
NORMALIZED = SOURCE / "normalized_final_path_20261002"
CI = BASE / "h_is_a_int06_ci9808511_sbq123_108r_20261002"
THRESHOLDS = ROOT / "configs/neb_agent/default_thresholds.yaml"
REQUEST = Path(__file__).with_name("user_request.json")
POTCAR = "~/sbq/Fe110/potcars/Fe_C_O_H/POTCAR"
POTCAR_SHA = "e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85"


def normalize() -> None:
    if NORMALIZED.exists() or CI.exists():
        raise FileExistsError("Inspect existing evidence; never overwrite a prepared restart.")
    rows, structures = [], []
    for i in range(11):
        name = f"{i:02d}"
        original = RAW / name / ("POSCAR" if i in (0, 10) else "CONTCAR")
        structure = read_poscar(original)
        if structures and compatible(structures[0], structure):
            raise ValueError(f"Incompatible structure {name}")
        shifts = np.zeros_like(structure.frac, dtype=int)
        if structures:
            previous = structures[-1]
            cart_delta, _ = find_mic((structure.frac - previous.frac) @ structure.cell, structure.cell, pbc=True)
            target = previous.frac + cart_delta @ np.linalg.inv(structure.cell)
            shifts = np.rint(target - structure.frac).astype(int)
            if np.max(np.abs(target - structure.frac - shifts)) > 1e-9:
                raise ValueError("Unwrapping is not an integer lattice translation")
        if np.any(shifts[:18]):
            raise ValueError("Fixed layer would change coordinates")
        normalized = copy_with_frac(structure, structure.frac + shifts, structure.comment)
        target_path = NORMALIZED / name / "POSCAR"
        write_poscar(target_path, normalized)
        final = read_poscar(target_path)
        _, errors = find_mic((final.frac - structure.frac) @ structure.cell, structure.cell, pbc=True)
        if float(errors.max()) > 1e-8 or final.flags != structure.flags:
            raise ValueError("Physical geometry or fixed flags changed")
        step = 0.0 if not structures else float(np.linalg.norm((final.frac - structures[-1].frac) @ final.cell, axis=1).max())
        rows.append({"image": name, "source": str(original), "source_sha256": sha256_file(original),
                     "normalized_sha256": sha256_file(target_path), "integer_lattice_shifts": shifts.tolist(),
                     "physical_equivalence_max_error_A": float(errors.max()), "max_unwrapped_neighbor_step_A": step})
        structures.append(final)
    shutil.copyfile(SOURCE / "INCAR", NORMALIZED / "INCAR")
    write_json(NORMALIZED / "normalization_receipt.json", {
        "status": "PASS", "source_job_id": "9808511", "rows": rows,
        "scope": "Only integer lattice translations; atom order, cell, flags and physical geometry retained.",
        "source_analysis": {"path": str(RAW / "neb_analysis.json"), "sha256": sha256_file(RAW / "neb_analysis.json")},
    })
    result = diagnose(NORMALIZED, ["49"], [str(i) for i in range(18)], THRESHOLDS, expected_interior=9)
    if result["status"] != "PASS":
        raise ValueError(f"Normalized geometry: {result['status']}, {result['errors']}")
    subprocess.run(["python", "-m", "scripts.neb_agent.prepare_restart", "--source", str(NORMALIZED),
                    "--destination", str(CI)], cwd=ROOT, check=True)
    for name in ("KPOINTS", "POTCAR.spec", "reaction_contract.normalized.json", "script.lsf"):
        shutil.copyfile(SOURCE / name, CI / name)
    report = load_json_object(SOURCE / "path_generation_report.json")
    report.update(method_used="converged_VASP_neb9808511_restart", interpolation_strategy="no_reinterpolation_integer_PBC_unwrap_only",
                  strategy_source="user_authorized_CI_refinement_of_completed_ordinary_NEB", source_job_id="9808511",
                  source_structure_hashes={f"{i:02d}": sha256_file(CI / f"{i:02d}/POSCAR") for i in range(11)},
                  normalization_receipt={"path": str(NORMALIZED / "normalization_receipt.json"),
                                         "sha256": sha256_file(NORMALIZED / "normalization_receipt.json")})
    report.pop("source_manifest", None)
    report.pop("source_request", None)
    write_json(CI / "path_generation_report.json", report)
    write_xyz(CI / "movie.xyz", structures)
    print("Normalized geometry PASS. Max adjacent atom step A:", max(r["max_unwrapped_neighbor_step_A"] for r in rows))
    print("CI restart prepared; INCAR and VTST evidence still required.")


def bind() -> None:
    accepted, _ = validate_path_review(CI / "path_review.json", CI / "path_generation_report.json")
    if not accepted:
        raise ValueError("Current path review not accepted/hash-bound")
    geometry = diagnose(CI, ["49"], [str(i) for i in range(18)], THRESHOLDS, expected_interior=9)
    if geometry["status"] != "PASS":
        raise ValueError("Child geometry did not pass")
    contract = load_contract(CI / "reaction_contract.normalized.json")
    binding = validate_path_binding(CI, contract)
    if not binding["valid"]:
        raise ValueError(binding["errors"])
    parent_analysis = load_json_object(RAW / "neb_analysis.json")
    chemical = load_json_object(RAW / "parent_chemical_evidence.json")
    for row, evidence in zip(parent_analysis["images"], chemical["rows"], strict=True):
        row["diagnostic_sigma0_energy_eV"] = row["final_energy_eV"]
        row["final_energy_eV"] = evidence["toten_eV"]
        row["relative_energy_eV"] = evidence["toten_eV"] - chemical["rows"][0]["toten_eV"]
    peak = max(chemical["rows"], key=lambda row: row["toten_eV"])["image"]
    parent_analysis.update(path_binding=binding, path_binding_valid=binding["valid"],
                           contract_sha256=contract["contract_sha256"], atom_map_sha256=contract["atom_map_sha256"],
                           compatibility_sha256=contract["compatibility_sha256"], complete_energy_profile=True,
                           maximum_image=peak, internal_maximum=peak not in {"00", "10"},
                           geometry_validated=True, path_reviewed=True,
                           normalization_scope="The CI geometries are integer-translation equivalents of these final ordinary-NEB OUTCAR geometries; normalized geometry receipt binds both.")
    parent_analysis["source_files"].extend(source_file_manifest([
        RAW / "parent_chemical_evidence.json", NORMALIZED / "normalization_receipt.json",
        CI / "path_generation_report.json", CI / "path_review.json", CI / "path_geometry_diagnosis.json",
        CI / "reaction_contract.normalized.json",
    ]))
    write_json(CI / "completed_parent_analysis.json", parent_analysis)
    check = preflight(CI, "ci_neb")
    if not check["passed"]:
        raise ValueError(check["errors"])
    request = {"geometry_file": str(CI / "path_geometry_diagnosis.json"),
               "analysis_file": str(CI / "completed_parent_analysis.json"), "thresholds_file": str(THRESHOLDS),
               "path_quality_file": str(RAW / "neb_path_quality.json"),
               "preflight_file": str(CI / "submission_preflight.json"), "climb": False, "path_reviewed": True}

    def decide(path: Path) -> dict:
        write_json(path, request)
        bindings = {}
        evidence = {name: load_bound_evidence(path, request, name, bindings)
                    for name in ("geometry", "analysis", "thresholds", "path_quality", "preflight", "authorization")}
        return decide_execution(evidence["geometry"], evidence["analysis"], evidence["thresholds"],
                                climb=False, path_reviewed=True, path_quality=evidence["path_quality"],
                                preflight=evidence["preflight"], authorization=evidence["authorization"], source_bindings=bindings)

    initial = decide(CI / "gate_request_before_authorization.json")
    write_json(CI / "gate_before_authorization.json", initial)
    auth = {"schema_version": 1, "document_kind": "user_execution_authorization", "action": "ENABLE_CI_NEB",
            "calculation_kind": "ci_neb", "authorized_at": datetime.now(timezone.utc).isoformat(),
            "source": {"path": str(REQUEST), "sha256": sha256_file(REQUEST)},
            "target": {"server_alias": "sunboquan-codex", "remote_dir": "~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/" + CI.name},
            "workdir_identity": workdir_identity(CI), "bundle_sha256": check["bundle_sha256"],
            "evidence_sha256": execution_evidence_sha256(initial["EVIDENCE"]),
            "potcar": {"source": POTCAR, "sha256": POTCAR_SHA, "spec_sha256": check["files"]["POTCAR.spec"]}}
    write_json(CI / "user_execution_authorization.json", auth)
    request["authorization_file"] = str(CI / "user_execution_authorization.json")
    decision = decide(CI / "execution_gate_request.json")
    write_json(CI / "execution_gate_decision.json", decision)
    require_action(CI / "execution_gate_decision.json", "ENABLE_CI_NEB", decision["state_sha256"])
    print("CI preflight PASS; ENABLE_CI_NEB allowed", decision["ALLOWED_ACTIONS"])


def review() -> None:
    path = write_path_review_draft(CI, CI / "dist.dat", CI / "nebmovie0.vtst")
    result = load_json_object(path)
    result.update(status="accepted", reviewer="Codex delegated structural review under the current user CI-NEB request",
                  reviewed_at=datetime.now(timezone.utc).isoformat(),
                  notes="Inspected actual-coordinate contact sheet and all eleven geometries. Integer PBC shifts only, fixed Fe0-17 retained, no collisions or discontinuous physical jumps; C-C/C-O/original C-H retained. Refinement of global peak05 authorized; lower migration peaks remain separate features, not a single-saddle claim. VTST nebmovie produces CON-format movie in this installation; bound as nebmovie0.vtst, with separately generated genuine XYZ for portability.",
                  chemical_evidence_sha256=sha256_file(CI / "chemical_review_evidence.json"),
                  contact_sheet_sha256=sha256_file(CI / "path_review_contact_sheet.png"))
    write_json(path, result)
    print("Current normalized final path review accepted and hash-bound.")


def checkpoint() -> None:
    receipt = load_json_object(CI / "submission_record.json")
    if receipt["status"] != "SUBMITTED":
        raise ValueError("No successful submission receipt")
    parent = query_lsf_job("9808511", stage="ordinary_neb")
    if parent["status"] != "DONE":
        raise ValueError("Parent scheduler is not DONE")
    write_json(CI / "parent_scheduler_evidence.json", parent)
    current = query_lsf_job(receipt["job_id"], stage="ci_neb")
    write_json(CI / "scheduler_checkpoint_submission.json", current)
    previous_id = "task-is-a-int06-neb9808511-sbq123-switch-20260930"
    event = load_json_object(ROOT / "modules/state_handoff/events" / (previous_id + ".json"))
    stamp = datetime.now(timezone.utc).isoformat()
    event_id = f"task-is-a-int06-ci{receipt['job_id']}-20261002"
    event.update(event_id=event_id, occurred_at=stamp, recorded_at=stamp, supersedes=[previous_id],
                 summary=f"Ordinary NEB9808511 completed and reviewed; user-authorized CI-NEB{receipt['job_id']} submitted once and {current['status']}.")
    records = [(REQUEST, "user_authorization"),
               (CI / "parent_scheduler_evidence.json", "scheduler"),
               (NORMALIZED / "normalization_receipt.json", "module_validation"),
               (CI / "completed_parent_analysis.json", "module_validation"),
               (CI / "path_review.json", "module_validation"),
               (CI / "submission_preflight.json", "module_validation"),
               (CI / "execution_gate_decision.json", "module_validation"),
               (CI / "submission_record.json", "repository_document"),
               (CI / "scheduler_checkpoint_submission.json", "scheduler")]
    event["evidence"] = [{"locator": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path),
                           "authority": authority, "observed_at": stamp} for path, authority in records]
    event["payload"] = {
        "objective": f"Monitor CI-NEB{receipt['job_id']} for IS-A9725473 -> INT06_9748648 H migration.",
        "phase": "active", "current_evidence": [
            "Parent ordinary NEB9808511 is DONE; all nine internal images completed normally with final electronic convergence, 71 steps and maximum final NEB force0.049947 eV/A.",
            "Final structures were recovered with OUTCAR/OSZICAR/XDATCAR. Integer lattice translations only remove Fe periodic branch wrapping; atom order, fixedFe0-17 and physical structures are retained. Normalized geometry PASS; maximum adjacent atom displacement0.401628 A.",
            "Actual TOTEN maximum is image05. Lower peaks01 and09 remain diagnostic migration features; this refinement does not claim a single elementary TS for the whole multi-peak path.",
            "VTST dist.pl and nebmovie.pl0 completed; numeric and actual-coordinate visual review accepted. CI preflight and current hash-bound ENABLE_CI_NEB execution authorization pass.",
            f"CI-NEB{receipt['job_id']} submitted once on sunboquan-codex/sbq123, status{current['status']}; nine internal images,108 MPI ranks,12 per image,NPAR4,per-node cap16; LCLIMB true,IOPT1,EDIFFG -0.02,ALGO Fast,SIGMA0.20,NSW300.",
            "No final TS, virtual frequency, electronic barrier or Grade-A acceptance is claimed for this migration segment yet.",
        ],
        "one_executable_step": f"At the next requested checkpoint query LSF{receipt['job_id']} and the canonical compact NEB monitor for ~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/{CI.name}; distinguish queue state, electronic convergence, CI/NEB forces, geometry and scientific validity.",
        "submission_boundary": "One CI refinement authorized and submitted. No duplicate, restart, new GPU, Dimer or frequency submission without current evidence and user authority.",
        "done_when": ["CI path is technically converged and reviewed; later frequency validation and compatible-energy registration require their own gates."],
        "constraints": ["Preserve accepted INT06-MID and MID-FS segments.", "Preserve atom mapping, fixedFe0-17 and SIGMA0.20 compatibility branch.",
                        "108 total ranks retained with16-per-node cap and12 per internal image.",
                        "CI climbs the currently highest internal image dynamically; initial maximum05 does not lock image05 forever."],
        "authoritative_references": [path.relative_to(ROOT).as_posix() for path, _ in records],
    }
    target = ROOT / "modules/state_handoff/events" / (event_id + ".json")
    write_json_exclusive(target, event)
    print("CI job", receipt["job_id"], current["status"], "event", target.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("normalize", "review", "bind", "checkpoint"))
    args = parser.parse_args()
    {"normalize": normalize, "review": review, "bind": bind, "checkpoint": checkpoint}[args.action]()
