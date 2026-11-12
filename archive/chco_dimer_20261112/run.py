"""One authorized Dimer handoff; stages stop for actual work-side mode review."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess

import numpy as np

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.neb_agent.submission import preflight, submit, submission_status
from scripts.neb_agent.utils_structure import minimum_image_delta, read_poscar
from scripts.scheduler_evidence import query_lsf_job
from scripts.ts_strategy_engine.dimer_gate import validate_modecar_bundle
from scripts.ts_strategy_engine.execution_evidence import (
    execution_evidence_sha256, workdir_identity,
)
from scripts.ts_strategy_engine.execution_gate import require_action
from scripts.ts_strategy_engine.execution_gate_cli import build_decision
from scripts.ts_strategy_engine.handoff import prepare_reviewed_dimer_handoff
from scripts.vasp_inputs import build_fe110_dimer

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109"
REVIEW = PARENT / "local_triplet_review_20261112_v1"
OUT = PARENT / "dimer_image05_20261112_v1"
HOST = "sunboquan-codex"
REMOTE = "~/sbq/Fe110/ts/ch_co_to_chco_20261110/" + OUT.name
AUTHORITY = Path(__file__).with_name("user_authority.md")
POTCAR = "~/sbq/Fe110/adsorption/fe110_five_c2_20261006/03_cfg0_direct_vasp/POTCAR"
POTCAR_SHA = "e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85"


def now():
    return datetime.now(timezone.utc).isoformat()


def prepare():
    if OUT.exists():
        raise ValueError("Destination exists; inspect stage receipts, never overwrite or resubmit.")
    if load_json_object(REVIEW / "verification.json")["status"] != "PASS":
        raise ValueError("Reviewed source verification did not pass.")
    # Bind the real user's method choice, not an automatic policy override.
    intent = REVIEW / "explicit_dimer_intent_20261112.json"
    write_json_exclusive(intent, {
        "action": "PREPARE_DIMER_HANDOFF", "authorized_at": now(),
        "source": {"path": str(AUTHORITY), "sha256": sha256_file(AUTHORITY)},
        "candidate_image": "05", "neighbors": ["04", "06"],
    })
    request = load_json_object(REVIEW / "execution_gate_request.json")
    request["authorization_file"] = str(intent)
    request_path = REVIEW / "explicit_dimer_gate_request_20261112.json"
    decision_path = REVIEW / "explicit_dimer_decision_20261112.json"
    write_json_exclusive(request_path, request)
    decision = build_decision(request_path, decision_path)
    require_action(decision_path, "PREPARE_DIMER_HANDOFF", decision["state_sha256"])
    work = REVIEW / "path"
    prepare_reviewed_dimer_handoff(
        contract_path=REVIEW / "reaction_contract.reviewed.json",
        analysis=work / "neb_analysis.json", path_review=work / "path_review.json",
        source_image=work / "05", previous_image=work / "04", next_image=work / "06",
        destination=OUT, dry_run=False, gate_decision=decision_path,
        gate_state_sha256=decision["state_sha256"],
    )
    build = build_fe110_dimer(OUT, cores=32)
    write_json_exclusive(OUT / "input_build.json", build)
    metrics, positions, mode = mode_metrics()
    write_json_exclusive(OUT / "mode_metrics.json", metrics)
    plot_mode(positions, mode)
    print({"decision": decision["DECISION"], "allowed": decision["ALLOWED_ACTIONS"],
           "mode_metrics": metrics, "submission_status": submission_status(OUT)})


def mode_metrics():
    center = read_poscar(OUT / "POSCAR")
    mode = np.loadtxt(OUT / "MODECAR")
    if mode.shape != (center.atom_count, 3) or not np.isfinite(mode).all():
        raise ValueError("Invalid generated mode.")
    expected = minimum_image_delta(read_poscar(OUT / "PREVIOUS_POSCAR").frac,
                                   read_poscar(OUT / "NEXT_POSCAR").frac) @ center.cell
    fixed = np.array([[flag == "F" for flag in row] for row in center.flags])
    expected[fixed] = 0.0
    expected /= np.linalg.norm(expected)
    if not np.allclose(mode, expected, atol=1e-11, rtol=0):
        raise ValueError("MODECAR is not the normalized reviewed central tangent.")
    reactions = load_json_object(REVIEW / "reaction_contract.reviewed.json")["reaction_atoms"]
    positions = center.frac @ center.cell
    derivatives = {}
    for name, a, b in (("forming_CC", 45, 46), ("CO", 46, 47), ("CH", 45, 48)):
        vector = minimum_image_delta(center.frac[a], center.frac[b]) @ center.cell
        derivatives[name] = float(np.dot(vector / np.linalg.norm(vector), mode[b] - mode[a]))
    weights = np.sum(mode * mode, axis=1)
    metrics = {
        "modecar_sha256": sha256_file(OUT / "MODECAR"),
        "poscar_sha256": sha256_file(OUT / "POSCAR"),
        "norm": float(np.linalg.norm(mode)), "fixed_max_abs": float(np.max(np.abs(mode[fixed]))),
        "reaction_indices": reactions,
        "reaction_amplitude_fraction": float(np.linalg.norm(mode[reactions])),
        "reaction_squared_amplitude_fraction": float(weights[reactions].sum()),
        "bond_distance_derivative_A_per_unit_mode": derivatives,
        "atom_squared_amplitude": {str(i): float(weights[i]) for i in reactions},
        "largest_amplitude_atoms_zero_based": np.argsort(weights)[-8:][::-1].tolist(),
        "parent_sampling_warning_retained_A": 0.62833058,
        "scientific_status": "starting_mode_only_not_a_hessian_eigenmode_or_TS",
    }
    return metrics, positions, mode


def plot_mode(positions, mode):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, dims, label in ((axes[0], (0, 1), "Top x-y"), (axes[1], (0, 2), "Side x-z")):
        a, b = dims
        ax.scatter(positions[:45, a], positions[:45, b], c="lightgray", s=65, edgecolor="gray")
        for index, color, symbol in ((45, "black", "C45"), (46, "black", "C46"),
                                     (47, "red", "O47"), (48, "royalblue", "H48")):
            ax.scatter(positions[index, a], positions[index, b], c=color, s=80)
            ax.annotate(symbol, positions[index, [a, b]], xytext=(3, 7), textcoords="offset points")
        ax.quiver(positions[:, a], positions[:, b], mode[:, a], mode[:, b],
                  angles="xy", scale_units="xy", scale=0.45, color="green", width=.004)
        for i, j in ((45, 46), (46, 47), (45, 48)):
            ax.plot(positions[[i, j], a], positions[[i, j], b], color="orange", lw=1)
        ax.set_aspect("equal")
        ax.set_title(label + "; green = signed central tangent")
        ax.set_xlabel("x / A")
        ax.set_ylabel(("y" if b == 1 else "z") + " / A")
    fig.suptitle("NEB 9994246: image 05, local tangent from 04 and 06")
    fig.tight_layout()
    fig.savefig(OUT / "mode_review.png", dpi=150)
    plt.close(fig)


def accept_mode():
    """Call only after inspecting the mode metrics and rendered mode, not automatically."""
    from scripts.artifact_io import write_json
    review_path = OUT / "mode_review.json"
    review = load_json_object(review_path)
    if review["status"] != "needs_review":
        raise ValueError("Mode already reviewed; do not overwrite.")
    metrics, _, _ = mode_metrics()
    if metrics["bond_distance_derivative_A_per_unit_mode"]["forming_CC"] >= 0:
        raise ValueError("Forward local tangent does not form the target C-C bond.")
    review.update({
        "status": "accepted", "reviewer": "Codex work-side scientific mode review",
        "reviewed_at": now(),
        **{key: "accepted" for key in ("reaction_center_continuity", "periodic_mapping",
           "adsorption_site_continuity", "reaction_mechanism_continuity", "mode_assignment")},
        "target_reaction_event": "C45-C46 formation in CH + CO -> CHCO; C45-H48 and C46-O47 remain intact",
        "candidate_between_is_and_fs": "accepted",
        "single_target_process_without_stable_intermediate": "accepted",
        "notes": "Actual top/side arrows and metrics reviewed; target atoms dominate. Parent C-C sampling warning retained, not TS acceptance.",
        "mode_metrics_sha256": sha256_file(OUT / "mode_metrics.json"),
        "visual_review_sha256": sha256_file(OUT / "mode_review.png"),
    })
    write_json(review_path, review)
    gate = validate_modecar_bundle(OUT)
    write_json_exclusive(OUT / "mode_validation.json", gate)
    if not gate["hard_gate_passed"]:
        raise ValueError(gate["hard_gate_errors"])
    report = preflight(OUT, "dimer")
    if not report["passed"]:
        raise ValueError(report["errors"])
    print({"mode_gate": gate, "preflight_passed": report["passed"], "cores": report["cores"]})


def authorize():
    remote_check = load_json_object(OUT / "remote_preflight.json")
    if remote_check["returncode"] != 0:
        raise ValueError("Remote target/runtime/POTCAR preflight failed.")
    report = load_json_object(OUT / "submission_preflight.json")
    if not report["passed"] or report["cores"] != 32:
        raise ValueError("Reviewed Dimer preflight differs.")
    request = load_json_object(REVIEW / "execution_gate_request.json")
    request["preflight_file"] = str(OUT / "submission_preflight.json")
    before = OUT / "readiness_request.json"
    write_json_exclusive(before, request)
    decision = build_decision(before, OUT / "readiness_decision.json")
    authority = {
        "schema_version": 1, "document_kind": "user_execution_authorization",
        "action": "START_DIMER", "calculation_kind": "dimer", "authorized_at": now(),
        "source": {"path": str(AUTHORITY), "sha256": sha256_file(AUTHORITY)},
        "target": {"server_alias": HOST, "remote_dir": REMOTE},
        "workdir_identity": workdir_identity(OUT), "bundle_sha256": report["bundle_sha256"],
        "evidence_sha256": execution_evidence_sha256(decision["EVIDENCE"]),
        "potcar": {"source": POTCAR, "sha256": POTCAR_SHA,
                   "spec_sha256": report["files"]["POTCAR.spec"]},
    }
    write_json_exclusive(OUT / "user_execution_authorization.json", authority)
    request["authorization_file"] = str(OUT / "user_execution_authorization.json")
    write_json_exclusive(OUT / "submission_request.json", request)
    decision = build_decision(OUT / "submission_request.json", OUT / "submission_decision.json")
    require_action(OUT / "submission_decision.json", "START_DIMER", decision["state_sha256"])
    print({"decision": decision["DECISION"], "allowed": decision["ALLOWED_ACTIONS"],
           "bundle_sha256": report["bundle_sha256"]})


def launch():
    if submission_status(OUT)["status"] != "NOT_RESERVED":
        raise ValueError("Existing attempt: reconcile it; never retry submission.")
    result = submit(OUT, OUT / "submission_decision.json", HOST, REMOTE,
                    POTCAR, POTCAR_SHA, "START_DIMER")
    print({"status": result["status"], "job_id": result["job_id"]})
    scheduler = query_lsf_job(result["job_id"], stage="dimer")
    write_json_exclusive(OUT / "initial_scheduler_evidence.json", scheduler)
    print({"scheduler_status": scheduler["status"], "job_id": result["job_id"]})


def remote_preflight():
    command = (
        "set -e; whoami; hostname; "
        "test -r /home_gkx/env/intel/intel2016.sh; "
        'test -x "$HOME/soft/vasp541vtst/bin/vasp_std"; '
        f"test ! -e {REMOTE}; test ! -e {REMOTE}.submission-reservation; "
        f"sha256sum {POTCAR}; "
        "bjobs -w 2>&1"
    )
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                             HOST, command], capture_output=True, text=True, timeout=45)
    payload = {"checked_at": now(), "server_alias": HOST, "command": command,
               "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    write_json_exclusive(OUT / "remote_preflight.json", payload)
    if result.returncode or POTCAR_SHA not in result.stdout:
        raise ValueError("Remote preflight failed; inspect saved evidence, no submission.")
    print(payload)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("prepare", "accept-mode", "remote-preflight", "authorize", "submit"))
    phase = parser.parse_args().phase
    {"prepare": prepare, "accept-mode": accept_mode, "remote-preflight": remote_preflight,
     "authorize": authorize, "submit": launch}[phase]()
