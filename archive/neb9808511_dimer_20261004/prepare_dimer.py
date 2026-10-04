"""Reviewed ordinary-NEB handoff; never overwrite or submit implicitly."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import shutil

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scripts.artifact_io import load_json_object, sha256_file, write_json, write_json_exclusive
from scripts.scheduler_evidence import validate_stored_lsf_evidence, query_lsf_job
from scripts.ts_strategy_engine.execution_evidence import load_bound_evidence, execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action
from scripts.ts_strategy_engine.handoff import prepare_reviewed_dimer_handoff
from scripts.ts_strategy_engine.dimer_gate import validate_modecar_bundle
from scripts.neb_agent.utils_structure import read_poscar
from scripts.neb_agent.submission import preflight
from scripts.vasp_inputs import build_fe110_dimer

ROOT = Path(__file__).resolve().parents[2]
RECORD = Path(__file__).resolve().parent
BASE = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822"
PARENT = BASE / "h_is_a_int06_ci9808511_sbq123_108r_20261002"
RAW = BASE / "h_is_a_int06_gpu1802_neb_sbq123_108r_16pn_20260930/completed_review_20261002"
DEST = BASE / "h_is_a_int06_dimer_neb9808511_image05_32r_16pn_20261004"
POTCAR = "~/sbq/Fe110/potcars/Fe_C_O_H/POTCAR"
POTCAR_SHA = "e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85"


def gate(request, destination):
    write_json(destination, request)
    bindings = {}
    evidence = {key: load_bound_evidence(destination, request, key, bindings)
                for key in ("geometry", "analysis", "thresholds", "path_quality", "preflight", "scheduler", "authorization")}
    return decide_execution(evidence["geometry"], evidence["analysis"], evidence["thresholds"],
                            climb=False, path_reviewed=True, path_quality=evidence["path_quality"],
                            preflight=evidence["preflight"], scheduler=evidence["scheduler"],
                            authorization=evidence["authorization"], source_bindings=bindings)


def request():
    return {"geometry_file": str(PARENT / "path_geometry_diagnosis.json"),
            "analysis_file": str(PARENT / "completed_parent_analysis.json"),
            "thresholds_file": str(ROOT / "configs/neb_agent/default_thresholds.yaml"),
            "path_quality_file": str(RAW / "neb_path_quality.json"),
            "climb": False, "path_reviewed": True}


def prepare():
    if DEST.exists():
        raise FileExistsError("Handoff exists; inspect it rather than overwrite")
    for source in load_json_object(PARENT / "completed_parent_analysis.json")["source_files"]:
        if sha256_file(Path(source["path"])) != source["sha256"]:
            raise ValueError("Stale parent source: " + source["path"])
    # Completed parent is no longer retained by bjobs. Preserve original DONE bytes.
    parent = load_json_object(PARENT / "parent_scheduler_evidence.json")
    validate_stored_lsf_evidence(parent, required_status="DONE")
    shutil.copyfile(PARENT / "parent_scheduler_evidence.json", RECORD / "parent_scheduler.json")
    data = request()
    data["scheduler_file"] = str(RECORD / "parent_scheduler.json")
    decision = gate(data, RECORD / "prepare_gate_request.json")
    path = RECORD / "prepare_gate_decision.json"
    write_json(path, decision)
    require_action(path, "PREPARE_DIMER_HANDOFF", decision["state_sha256"])
    prepare_reviewed_dimer_handoff(contract_path=PARENT / "reaction_contract.normalized.json",
                                  analysis=PARENT / "completed_parent_analysis.json",
                                  path_review=PARENT / "path_review.json", source_image=PARENT / "05/POSCAR",
                                  previous_image=PARENT / "04/POSCAR", next_image=PARENT / "06/POSCAR",
                                  destination=DEST, dry_run=False, gate_decision=path,
                                  gate_state_sha256=decision["state_sha256"])
    shutil.copyfile(PARENT / "reaction_contract.normalized.json", DEST / "reaction_contract.normalized.json")
    rendered = build_fe110_dimer(DEST, cores=32)
    write_json(DEST / "input_profile_receipt.json", rendered)
    mode = np.loadtxt(DEST / "MODECAR")
    norms = np.linalg.norm(mode, axis=1)
    result = {"mode_norm": float(np.linalg.norm(mode)), "fixed_max_component": float(np.abs(mode[:18]).max()),
              "reaction_atom_49_amplitude": float(norms[49]),
              "top_atoms_zero_based": [{"index": int(i), "amplitude": float(norms[i])}
                                       for i in np.argsort(norms)[-6:][::-1]]}
    write_json(DEST / "mode_numeric_review.json", result)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    structures = [read_poscar(PARENT / f"{i:02d}/POSCAR") for i in (4, 5, 6)]
    for ax, coordinates in zip(axes, ((0, 1), (0, 2)), strict=True):
        for s, label, color in zip(structures, ("04", "05", "06"), ("blue", "black", "red"), strict=True):
            cart = s.frac @ s.cell
            ax.scatter(cart[18:45, coordinates[0]], cart[18:45, coordinates[1]], c="gray", s=14, alpha=.15)
            ax.scatter(cart[45:, coordinates[0]], cart[45:, coordinates[1]], c=color, label=label, s=30)
            ax.plot(cart[[49], coordinates[0]], cart[[49], coordinates[1]], marker="*", c=color, markersize=12)
        cart = structures[1].frac @ structures[1].cell
        ax.quiver(cart[49, coordinates[0]], cart[49, coordinates[1]], mode[49, coordinates[0]],
                  mode[49, coordinates[1]], angles="xy", scale_units="xy", scale=1, color="green")
        ax.set_aspect("equal")
        ax.legend()
        ax.set_xlabel("x / A")
        ax.set_ylabel(("y" if coordinates[1] == 1 else "z") + " / A")
    fig.suptitle("Ordinary NEB9808511: 04 / 05 / 06, H50 mode (green)")
    fig.tight_layout()
    fig.savefig(DEST / "mode_review.png", dpi=150)
    plt.close(fig)
    print(result)
    print((DEST / "script.lsf").read_text())


def bind():
    review = load_json_object(DEST / "mode_review.json")
    if review["status"] != "accepted":
        raise ValueError("Visual/chemical mode review required before binding")
    validation = validate_modecar_bundle(DEST)
    write_json(DEST / "dimer_mode_validation.json", validation)
    if not validation["hard_gate_passed"]:
        raise ValueError(validation["hard_gate_errors"])
    check = preflight(DEST, "dimer")
    if not check["passed"]:
        raise ValueError(check["errors"])
    data = request()
    data["preflight_file"] = str(DEST / "submission_preflight.json")
    initial = gate(data, DEST / "gate_request_before_authorization.json")
    source = RECORD / "user_request.json"
    auth = {"schema_version": 1, "document_kind": "user_execution_authorization", "action": "START_DIMER",
            "calculation_kind": "dimer", "authorized_at": datetime.now(timezone.utc).isoformat(),
            "source": {"path": str(source), "sha256": sha256_file(source)},
            "target": {"server_alias": "sunboquan-codex", "remote_dir": "~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/" + DEST.name},
            "workdir_identity": workdir_identity(DEST), "bundle_sha256": check["bundle_sha256"],
            "evidence_sha256": execution_evidence_sha256(initial["EVIDENCE"]),
            "potcar": {"source": POTCAR, "sha256": POTCAR_SHA, "spec_sha256": check["files"]["POTCAR.spec"]}}
    write_json(DEST / "user_execution_authorization.json", auth)
    data["authorization_file"] = str(DEST / "user_execution_authorization.json")
    decision = gate(data, DEST / "execution_gate_request.json")
    write_json(DEST / "execution_gate_decision.json", decision)
    require_action(DEST / "execution_gate_decision.json", "START_DIMER", decision["state_sha256"])
    print("Dimer preflight and START_DIMER gate PASS", decision["ALLOWED_ACTIONS"])


def checkpoint():
    receipt = load_json_object(DEST / "submission_record.json")
    if receipt["status"] != "SUBMITTED":
        raise ValueError("Submission not confirmed")
    state = query_lsf_job(receipt["job_id"], stage="dimer")
    write_json(DEST / "scheduler_checkpoint_submission.json", state)
    old_id = "task-is-a-int06-ci9826728-20261002"
    event = load_json_object(ROOT / "modules/state_handoff/events" / (old_id + ".json"))
    stamp = datetime.now(timezone.utc).isoformat()
    event_id = f"task-is-a-int06-dimer{receipt['job_id']}-20261004"
    files = [(RECORD / "user_request.json", "user_authorization"),
             (RECORD / "stop_receipt.json", "repository_document"),
             (RECORD / "scheduler_after.json", "scheduler"),
             (DEST / "dimer_handoff.json", "module_validation"),
             (DEST / "mode_review.json", "module_validation"),
             (DEST / "dimer_mode_validation.json", "module_validation"),
             (DEST / "submission_preflight.json", "module_validation"),
             (DEST / "execution_gate_decision.json", "module_validation"),
             (DEST / "submission_record.json", "repository_document"),
             (DEST / "scheduler_checkpoint_submission.json", "scheduler")]
    event.update(event_id=event_id, occurred_at=stamp, recorded_at=stamp, supersedes=[old_id],
                 summary=f"User cancelled CI9826728 (EXIT); reviewed ordinary NEB9808511 peak05 Dimer{receipt['job_id']} submitted once, {state['status']}.")
    event["evidence"] = [{"locator": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path),
                           "authority": authority, "observed_at": stamp} for path, authority in files]
    event["payload"] = {
        "objective": f"Monitor Dimer{receipt['job_id']} from ordinary NEB9808511 peak05 for IS-A to INT06 H migration.",
        "phase": "active", "current_evidence": [
            "CI9826728 cancelled through explicit user STOP_JOB authorization; scheduler EXIT confirmed; remote files retained.",
            "Ordinary NEB9808511 remains accepted as a technically converged parent:71 steps, maximum final NEB force0.049947 eV/A. Reuse its normalized final04/05/06, not failed CI final structures.",
            "Peak05 triad passes electronic, normal-termination, geometry, atom-order/fixed-mask and periodic mapping checks. Actual-coordinate mode review accepted; H50 amplitude0.98415, fixedFe0-17 zero.",
            f"Dimer{receipt['job_id']} submitted once on sunboquan-codex/sbq123; scheduler{state['status']};32 total ranks,16 per node;ALGO Fast,SIGMA0.20,EDIFF1e-7,EDIFFG-0.02,IOPT2,NSW300.",
            "This refines local migration peak05; lower peaks01/09 are not proven eliminated. No TS acceptance, frequency, barrier or Grade-A result claimed."],
        "one_executable_step": f"At the next requested checkpoint query LSF{receipt['job_id']} and Dimer OUTCAR/OSZICAR/DIMCAR; distinguish electronic convergence, force/torque/curvature, geometry and scientific validity.",
        "submission_boundary": "One Dimer authorized and submitted; no duplicate, restart, GPU or frequency calculation automatically authorized.",
        "done_when": ["Dimer technically converged and reviewed; later local frequency and compatible-energy registration require current gates."],
        "constraints": ["Preserve accepted INT06-MID and MID-FS segments.", "Preserve atom mapping, fixedFe0-17 and SIGMA0.20 compatibility branch.", "32 ranks,16-per-node cap for this single Dimer;108 ranks belonged to nine-image NEB."],
        "authoritative_references": [path.relative_to(ROOT).as_posix() for path, _ in files]}
    write_json_exclusive(ROOT / "modules/state_handoff/events" / (event_id + ".json"), event)
    print("Dimer", receipt["job_id"], state["status"], "event", event_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "bind", "checkpoint"))
    args = parser.parse_args()
    {"prepare": prepare, "bind": bind, "checkpoint": checkpoint}[args.action]()
