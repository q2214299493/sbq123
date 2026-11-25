from pathlib import Path

import pytest

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.ts_strategy_engine.evidence import _validate_ts_payload
from scripts.ts_strategy_engine.execution_gate import require_action
from scripts.ts_validation.analyze_vfa import analyze_vfa
from tests.scientific_claim_fixtures import neb_vfa_case
from test_scientific_claim_authority import claim_gate
from test_ts_strategy_engine import contract


def ci_case(root: Path, *, manual_single: bool = False):
    case = neb_vfa_case(root, contract())
    review_path = case["vfa"] / "review.json"
    review = load_json_object(review_path)
    for key in list(review):
        if "connectivity" in key or "displacement" in key:
            review.pop(key)
    if manual_single:
        review["single_imaginary_mode_assessment"] = "accepted_target_mode"
    write_json(review_path, review)
    policy = None if manual_single else case["payload"]["frequency_policy"]
    payload = analyze_vfa(case["vfa"], contract(), review_path, policy)
    return case, payload


@pytest.mark.parametrize("manual_single", [False, True])
def test_ci_accepts_without_downhill_but_keeps_current_source_gate(tmp_path, manual_single):
    case, payload = ci_case(tmp_path / "science", manual_single=manual_single)
    assert payload["grade"] == "A"
    assert payload["connectivity_required"] is False
    assert payload["connects_to_is"] is None
    assert payload["ci_neb_technical_acceptance"] is True
    _validate_ts_payload(payload)
    gate_path, decision = claim_gate(case["vfa"] / "vfa_analysis.json")
    require_action(gate_path, "APPROVE_TS_CANDIDATE", decision["state_sha256"])
    # A separate downhill diagnostic is not a required CI-NEB claim source.
    (case["plus"] / "OUTCAR").write_text("optional diagnostic changed\n")
    require_action(gate_path, "APPROVE_TS_CANDIDATE", decision["state_sha256"])
    (case["neb"] / "07/OUTCAR").write_text("source now incomplete\n")
    with pytest.raises(ValueError):
        require_action(gate_path, "APPROVE_TS_CANDIDATE", decision["state_sha256"])


def test_ci_unset_thresholds_need_explicit_single_mode_review(tmp_path):
    case, _ = ci_case(tmp_path / "science")
    payload = analyze_vfa(case["vfa"], contract(), case["vfa"] / "review.json")
    assert payload["grade"] == "Ungraded"


@pytest.mark.parametrize("damage", ["second_mode", "incomplete", "mode_not_assigned"])
def test_manual_ci_review_cannot_waive_frequency_failures(tmp_path, damage):
    case, _ = ci_case(tmp_path / "science", manual_single=True)
    if damage == "mode_not_assigned":
        path = case["vfa"] / "review.json"
        write_json(path, {**load_json_object(path), "mode_assignment": "Needs confirmation"})
    else:
        path = case["vfa"] / "OUTCAR"
        text = path.read_text()
        path.write_text(
            text + "\n2 f/i= 1 THz 100 cm-1\n"
            if damage == "second_mode"
            else text.replace("General timing and accounting informations for this job", "")
        )
    payload = analyze_vfa(case["vfa"], contract(), case["vfa"] / "review.json")
    assert payload["grade"] != "A"


def test_ci_registry_payload_cannot_replace_technical_acceptance_with_label(tmp_path):
    _, payload = ci_case(tmp_path / "science")
    with pytest.raises(ValueError, match="incomplete"):
        _validate_ts_payload({**payload, "ci_neb_technical_acceptance": False})


def test_ordinary_neb_cannot_bypass_connectivity_by_ci_label(tmp_path):
    case, _ = ci_case(tmp_path / "science")
    incar = case["neb"] / "INCAR"
    incar.write_text(incar.read_text().replace("LCLIMB=.TRUE.", "LCLIMB=.FALSE."))
    saddle_path = case["neb"] / "neb_analysis.json"
    saddle = load_json_object(saddle_path)
    current = analyze(case["neb"], Path(saddle["analysis_inputs"]["thresholds_path"]),
                      contract()["reaction_atoms"], write_output=False)
    write_json(saddle_path, {**saddle, **current})
    handoff_path = case["vfa"] / "vfa_handoff.json"
    write_json(handoff_path, {**load_json_object(handoff_path),
                             "saddle_analysis_sha256": sha256_file(saddle_path)})
    for name in ("vfa_scope_review.json", "review.json"):
        path = case["vfa"] / name
        write_json(path, {**load_json_object(path),
                          "vfa_handoff_sha256": sha256_file(handoff_path)})
    with pytest.raises(ValueError, match="actual climbing-image"):
        analyze_vfa(case["vfa"], contract(), case["vfa"] / "review.json")
