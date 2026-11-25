"""Intake allows partial evidence, while scientific and execution gates stay independent."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import ValidationError

from scripts.scientific_intake import AVAILABLE, INCOMPATIBLE, MISSING, OPTIONAL, UNVERIFIED, report

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "reports/multiphase/ch_co_intake_20261119.json"


def case():
    return json.loads(CASE.read_text(encoding="utf-8"))


def evidence(kind="temperature", value=None, state="reaction", mode="USER_PROVIDED"):
    return {
        "id": f"upload-{state}-{kind}", "state": state, "kind": kind, "mode": mode,
        "value": {"kelvin": 400} if value is None else value,
        "provenance": {"source_type": "user_supplied"},
        "validation": {"validation_status": "unreviewed", "compatibility_status": "unknown",
                       "validated_properties": [], "limitations": []},
        "acceptance": {"acceptance_status": "pending"},
    }


def accept(r, op):
    r["acceptance"] = {"acceptance_status": "accepted", "acceptance_scope": [op],
                       "accepted_by": "test reviewer", "acceptance_reason": "Sensitivity case only",
                       "acceptance_timestamp": "2026-11-19T10:00:00+08:00"}


def validate(r):
    r["validation"].update(validation_status="validated", validated_properties=[r["kind"]],
                           compatibility_status="compatible", validation_method="test property review")
    return r


def assess(*records, op="thermochemistry"):
    base = case()
    return report([base, {"schema_version": 1, "reaction_id": base["reaction_id"], "records": list(records)}], op)


@pytest.mark.parametrize(("mode", "source", "reference"), [
    ("USER_PROVIDED", "user_supplied", "provided table 2"),
    ("LITERATURE_EXTERNAL", "external_platform", "external study A/run B"),
    ("LITERATURE_EXTERNAL", "literature", "example publication, table 2"),
    ("LITERATURE_EXTERNAL", "database", "example dataset, entry B"),
])
def test_alternative_sources_without_local_id(mode, source, reference):
    r = validate(evidence(mode=mode))
    r["provenance"] = {"source_type": source, "source_reference": reference}
    result = assess(r)
    assert result["fields"]["reaction.temperature"]["status"] == AVAILABLE
    assert any(w.get("missing_provenance") for w in result["warnings"] if w["record_id"] == r["id"])


def test_absent_provenance_is_reportable():
    r = evidence()
    del r["provenance"]
    result = assess(r)
    assert result["fields"]["reaction.temperature"]["status"] == UNVERIFIED
    assert any("source_type" in w.get("missing_provenance", []) for w in result["warnings"])


def test_assumption_requires_scope_and_limits_preserves_validation():
    r = evidence(mode="USER_APPROVED_ASSUMPTION")
    accept(r, "thermochemistry")
    assert not assess(r)["fields"]["reaction.temperature"]["usable"]
    r["validation"]["limitations"] = ["Exploratory trial temperature"]
    before = copy.deepcopy(r)
    result = assess(r)["fields"]["reaction.temperature"]
    assert result["status"] == UNVERIFIED and result["usable"]
    assert not assess(r, op="kinetic_handoff")["fields"]["reaction.temperature"]["usable"]
    assert r == before


@pytest.mark.parametrize("key,value", [("validation_status", "rejected"), ("compatibility_status", "incompatible")])
def test_acceptance_cannot_override_rejection(key, value):
    r = validate(evidence())
    accept(r, "thermochemistry")
    r["validation"][key] = value
    assert assess(r)["fields"]["reaction.temperature"]["status"] == INCOMPATIBLE


def test_confirmation_keeps_geometric_projection():
    r = evidence("site_mapping", {"occupancies": [{"species": "X*", "site_type": "bridge", "multiplicity": 1}],
                                "sites_consumed": [], "sites_released": [], "interface_assignment": "single surface",
                                "reaction_classification": "association"})
    accept(r, "site_mapping")
    r["validation"]["limitations"] = ["Illustrative mapping"]
    result = assess(r, op="site_mapping")
    assert result["inputs_complete"]
    assert result["fields"]["reaction.site_mapping"]["status"] == UNVERIFIED
    assert result["fields"]["reaction.site_inference"]["selected"] == "reaction-site_inference"
    assert not assess(r, op="kinetic_handoff")["fields"]["reaction.site_mapping"]["usable"]


def corrections():
    records = []
    for r in case()["records"]:
        if r["kind"] == "structure":
            value = dict(zpe_ev=0.3, thermal_enthalpy_ev=0.1, entropy_ev_per_k=0.0005, gibbs_correction_ev=0.2,
                         temperature_k=400, standard_state="example", structure_identity=r["value"]["identity"],
                         thermal_basis="reviewed external basis")
            records.append(validate(evidence("corrections", value, r["state"])))
    return records


def conditions():
    return [validate(evidence()), validate(evidence("standard_state", {"convention": "example"}))]


def test_precomputed_route_without_spectra():
    base = case()
    base["records"] = [r for r in base["records"] if r["kind"] != "spectrum"] + corrections() + conditions()
    result = report([base])
    assert result["inputs_complete"] and not result["execution_authorized"]
    assert result["thermal_routes"] == {s: f"{s}.corrections" for s in ("IS", "TS", "FS")}
    assert result["fields"]["TS.spectrum"]["status"] == OPTIONAL


def test_ts_only_and_operation_specific_fields():
    result = assess()
    assert result["thermal_routes"] == {"IS": None, "TS": "TS.spectrum", "FS": None}
    assert result["fields"]["IS.spectrum"]["status"] == MISSING
    assert result["fields"]["reaction.pressure"]["status"] == OPTIONAL
    assert assess(op="electronic")["inputs_complete"]
    assert assess(op="kinetic_handoff")["mkm_status"] == "blocked"


def test_precomputed_inputs_carry_their_own_conditions():
    result = assess(*corrections())
    assert result["inputs_complete"]
    assert result["fields"]["reaction.temperature"]["value"] == 400
    different = corrections()
    different[0]["value"]["temperature_k"] = 500
    assert assess(*different)["fields"]["reaction.temperature"]["status"] == INCOMPATIBLE


def test_explicit_unknowns_can_be_filled_later():
    r = evidence("temperature", {"kelvin": None})
    assert "Missing kelvin" in assess(r)["fields"]["reaction.temperature"]["candidates"][0]["reasons"]
    other = validate(evidence())
    other["id"] += "-reviewed"
    assert assess(r, other)["fields"]["reaction.temperature"]["status"] == AVAILABLE


def test_zpe_can_proceed_without_other_corrections_or_temperature():
    inputs = corrections()
    for r in inputs:
        r["value"] = {k: r["value"][k] for k in ("zpe_ev", "structure_identity", "thermal_basis")}
    assert assess(*inputs, op="zpe")["inputs_complete"]
    assert not assess(*inputs)["inputs_complete"]


@pytest.mark.parametrize(("k", "v"), [("temperature_k", 500), ("standard_state", "other"),
                                        ("structure_identity", "unrelated")])
def test_mismatched_correction_can_be_replaced_by_compatible_upload(k, v):
    corrected = corrections()[0]
    corrected["value"]["thermal_basis"] = next(r["value"]["thermal_basis"] for r in case()["records"]
                                                if r["kind"] == "spectrum")
    bad = copy.deepcopy(corrected)
    bad["id"] += "-other-context"
    bad["value"][k] = v
    assert assess(bad, *conditions())["fields"]["IS.corrections"]["status"] == INCOMPATIBLE
    assert assess(bad, corrected, *conditions())["fields"]["IS.corrections"]["selected"] == corrected["id"]


def test_mixed_sources_need_common_thermal_basis():
    r = corrections()
    result = assess(r[0], r[-1], *conditions())
    assert not result["inputs_complete"]
    assert result["fields"]["TS.spectrum"]["status"] == INCOMPATIBLE


def test_partial_spectrum_explains_missing_fields():
    r = validate(evidence("spectrum", {"frequencies_cm1": [20.0]}, "IS"))
    f = assess(r)["fields"]["IS.spectrum"]
    assert f["status"] == UNVERIFIED and "Missing atom_map" in f["candidates"][0]["reasons"]


def test_ambiguous_upload_and_replay():
    r = validate(evidence())
    assert assess(r, r)["fields"]["reaction.temperature"]["status"] == AVAILABLE
    other = copy.deepcopy(r)
    other["value"]["kelvin"] = 500
    with pytest.raises(ValueError, match="Conflicting evidence ID"):
        assess(r, other)
    other["id"] += "-2"
    assert assess(r, other)["fields"]["reaction.temperature"]["status"] == INCOMPATIBLE


def test_missing_information_no_job_or_registry_access(tmp_path):
    base = case()
    base["records"] = []
    p = tmp_path / "empty.json"
    p.write_text(json.dumps(base))
    run = subprocess.run([sys.executable, "-m", "scripts.scientific_intake", str(p)], cwd=ROOT,
                         check=True, capture_output=True, text=True)
    result = json.loads(run.stdout)
    assert not result["inputs_complete"] and not result["execution_authorized"]
    assert set(tmp_path.iterdir()) == {p}


def test_invalid_acceptance_or_wrong_reaction():
    r = evidence()
    r["acceptance"] = {"acceptance_status": "accepted"}
    with pytest.raises(ValidationError):
        assess(r)
    with pytest.raises(ValueError, match="reaction IDs"):
        report([case(), {"schema_version": 1, "reaction_id": "other", "records": []}])
