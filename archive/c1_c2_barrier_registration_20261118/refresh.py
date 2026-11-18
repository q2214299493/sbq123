"""Refresh the two accepted TS review chains without modifying their sources."""
from datetime import datetime, timezone
from pathlib import Path
from shutil import copyfile

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.ts_strategy_engine.dimer_analysis import analyze_dimer
from scripts.ts_strategy_engine.execution_gate_cli import build_decision
from scripts.ts_validation.analyze_vfa import DEFAULT_PROFILE, analyze_vfa
from scripts.ts_validation.dimer_frequency_gate import evaluate_dimer_frequency_gate


ROOT = Path(__file__).resolve().parents[2]
PREP = ROOT / "outputs/c1_c2_barrier_review_20261118_v1"
OUTPUT = ROOT / "outputs/c1_c2_barrier_registration_20261118_v1"
REVIEWER = "Codex evidence refresh under the user's 2026-11-18 instruction"


def resolve(value, root):
    return (root / Path(value)).resolve(strict=True)


def binding(path):
    return {"path": str(path), "sha256": sha256_file(path)}


def checked(path, digest):
    if sha256_file(path) != digest:
        raise ValueError(f"Historical evidence changed: {path}")
    return load_json_object(path)


def refresh_dimer(handoff, old_saddle, out, originals):
    final = resolve(handoff["source_ts_candidate"], old_saddle.parent)
    historical = checked(old_saddle, handoff["saddle_analysis_sha256"])
    current = analyze_dimer(final.parent, write_output=False)
    changes = {k for k in current.keys() | historical.keys() if current.get(k) != historical.get(k)}
    metadata = {"requires_connectivity_validation", "connectivity_role", "requires_frequency_validation",
                "requires_frequency_and_connectivity_validation"}
    if changes - metadata or not current["technically_converged"]:
        raise ValueError(f"Non-metadata difference in Dimer replay: {sorted(changes)}")
    path = out / "dimer_analysis.json"
    write_json_exclusive(path, current)
    review_ref = handoff["dimer_frequency_gate"]
    historical_soft = resolve(review_ref["manual_review_path"], old_saddle.parent)
    soft = checked(historical_soft, review_ref["manual_review_sha256"])
    if not evaluate_dimer_frequency_gate(historical, old_saddle, final, historical_soft)["ts_validation_eligible"]:
        raise ValueError("Historical Dimer soft-warning review did not approve this saddle")
    originals.append(binding(historical_soft))
    soft_path = out / "dimer_soft_gate_review.json"
    write_json_exclusive(soft_path, {**soft, "saddle_analysis_sha256": sha256_file(path),
        "reviewer": REVIEWER, "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "supersedes_reference_only": binding(historical_soft),
        "refresh_basis": "Same raw files, structure, warning codes and numerical residuals; only connectivity-description fields changed."})
    handoff["dimer_frequency_gate"] = evaluate_dimer_frequency_gate(current, path, final, soft_path)
    return path


def claim_for(draft):
    return {"barrier_set_id": draft["barrier_set_id_proposal"],
            "ts_result_id": draft["ts_result_proposal"]["result_id"],
            **{k: draft[k] for k in ("reaction_id", "source_calculation_id", "ts_validation_id",
                                   "initial_result_id", "final_result_id")}}


def run_case(case):
    packet = load_json_object(PREP / case / "review_packet.json")
    draft = load_json_object(PREP / case / "registration_request.draft.json")
    old_path = Path(packet["original_analysis"]["path"])
    previous = checked(old_path, packet["original_analysis"]["sha256"])
    old_root = old_path.parent
    old_handoff = resolve(previous["vfa_handoff"], old_root)
    handoff = checked(old_handoff, previous["vfa_handoff_sha256"])
    old_saddle = resolve(handoff["saddle_analysis_source"], old_handoff.parent)
    old_mode = resolve(previous["review_path"], old_root)
    old_scope = old_root / "vfa_scope_review.json"
    originals = [binding(p) for p in (old_path, old_handoff, old_saddle, old_mode, old_scope)]
    mismatches = [item for item in previous["source_files"] if sha256_file(Path(item["path"])) != item["sha256"]]
    if mismatches and (case != "int06_mid" or [Path(x["path"]).resolve() for x in mismatches] != [DEFAULT_PROFILE.resolve()]):
        raise ValueError("Unexpected stale historic source")
    policy = yaml.safe_load(DEFAULT_PROFILE.read_text(encoding="utf-8"))["transition_state"]["vfa"]["validation"]
    if policy != previous["frequency_policy"]:
        raise ValueError("Frequency policy changed; do not silently renew review")
    out = OUTPUT / case
    out.mkdir(parents=True, exist_ok=False)
    for name in ("POSCAR", "OUTCAR"):
        source = old_root / name
        expect = next(r["sha256"] for r in previous["source_files"] if Path(r["path"]).resolve() == source.resolve())
        copyfile(source, out / name)
        if sha256_file(out / name) != expect:
            raise ValueError(f"Frequency source differs: {name}")
    saddle = refresh_dimer(handoff, old_saddle, out, originals) if case == "ch_co" else old_saddle
    handoff.update(saddle_analysis_source=str(saddle), saddle_analysis_sha256=sha256_file(saddle))
    handoff_path = out / "vfa_handoff.json"
    write_json_exclusive(handoff_path, handoff)
    mode = load_json_object(old_mode)
    scope = load_json_object(old_scope)
    for review in (mode, scope):
        if review["vfa_handoff_sha256"] != previous["vfa_handoff_sha256"]:
            raise ValueError("Original review did not bind the handoff")
        review["vfa_handoff_sha256"] = sha256_file(handoff_path)
    mode["vfa_handoff"] = str(handoff_path)
    write_json_exclusive(out / "vfa_scope_review.json", scope)
    mode_path = out / "vfa_review.json"
    write_json_exclusive(mode_path, mode)
    result = analyze_vfa(out, previous["reaction_contract"], mode_path, write_output=False)
    invariant = ("grade", "kinetic_eligible", "normal_completion", "source_method", "principal_mode_index",
                 "modes", "imaginary_frequencies_cm1", "principal_mode_assignment", "geometry_status",
                 "contract_sha256", "atom_map_sha256", "compatibility_sha256", "frequency_output_file_id",
                 "source_saddle_sha256", "frequency_poscar_sha256")
    differences = [k for k in invariant if result.get(k) != previous.get(k)]
    analysis_path = out / "vfa_analysis.json"
    write_json_exclusive(analysis_path, {**result, "barrier_claim": claim_for(draft)})
    write_json_exclusive(out / "reference_review.json", {"reviewer": REVIEWER, "originals": originals,
        "historical_profile_mismatch": mismatches, "current_profile": binding(DEFAULT_PROFILE),
        "frequency_policy_unchanged": True, "scientific_field_differences": differences,
        "no_new_calculation": True, "updated_references": [binding(p) for p in
            (handoff_path, mode_path, out / "vfa_scope_review.json", analysis_path)]})
    if differences or result["grade"] != "A" or not result["scientific_review_bound"]:
        raise ValueError(f"Refreshed VFA not identical in scientific fields: {differences}; grade={result['grade']}")
    original_gate = load_json_object(PREP / case / "current_ts_gate.json")
    ev = original_gate["EVIDENCE"]
    request = {f"{k}_file": v["path"] for k, v in ev["source_bindings"].items()}
    request.update(validation_file=str(analysis_path), climb=ev["climb"], path_reviewed=ev["path_reviewed"])
    req_path = out / "current_gate_request.json"
    write_json_exclusive(req_path, request)
    decision = build_decision(req_path, out / "current_gate_decision.json")
    for original in originals:
        if sha256_file(Path(original["path"])) != original["sha256"]:
            raise ValueError("Historical evidence changed during refresh")
    return decision


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("ch_co", "int06_mid"))
    case = parser.parse_args().case
    decision = run_case(case)
    print({k: decision[k] for k in ("DECISION", "ALLOWED_ACTIONS", "CHEMICAL_INTERPRETATION")})
