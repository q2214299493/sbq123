import copy
import json
import math
from pathlib import Path

import pytest

from scripts.thermochemistry.engine import calculate
from scripts.scientific_intake import validator
from scripts.thermochemistry.frequencies import draft_intake, parse_outcar
from scripts.thermochemistry.harmonic import CM1_EV, KB, add_ideal_gas, harmonic

REPORTS = Path(__file__).resolve().parents[1] / "reports/multiphase"


def case():
    return json.loads((REPORTS / "ch_co_intake_20261119.json").read_text(encoding="utf8"))


def review():
    return json.loads((REPORTS / "ch_co_frequency_audit_20261119.json").read_text(encoding="utf8"))


def spectrum(doc):
    return next(r for r in doc["records"] if r["kind"] == "spectrum")


def synthetic_upload(doc, states=("IS", "FS")):
    basis = spectrum(doc)["value"]["thermal_basis"]
    records = []
    for state in states:
        record = copy.deepcopy(next(r for r in doc["records"] if r["state"] == state and r["kind"] == "structure"))
        identity = record["value"]["identity"]
        record.update(id=f"synthetic-{state}", kind="corrections", mode="USER_PROVIDED",
                      provenance={"source_type": "user_supplied", "source_reference": "analytical test fixture"})
        record["validation"].update(validated_properties=["corrections"], validation_method="synthetic fixture review")
        record["value"] = dict(zpe_ev=0.2, thermal_enthalpy_ev=0.1, entropy_ev_per_k=0.0005,
                               gibbs_correction_ev=0.15, temperature_k=300, standard_state="test surface",
                               structure_identity=identity, thermal_basis=basis)
        records.append(record)
    return {"schema_version": 1, "reaction_id": doc["reaction_id"], "records": records}


def test_exact_si_and_analytical_partition_function():
    assert CM1_EV == pytest.approx(0.00012398419843320026, rel=1e-13)
    q = 1000 * CM1_EV
    temp = q / (KB * math.log(2))
    r = harmonic([1000], temperature=temp)
    assert r["zpe_ev"] == pytest.approx(q / 2)
    assert r["thermal_enthalpy_ev"] == pytest.approx(q)
    assert r["entropy_ev_per_k"] == pytest.approx(2 * KB * math.log(2))
    assert r["gibbs_correction_ev"] == pytest.approx(-q / 2)


def test_soft_mode_and_frozen_high_frequency():
    r = harmonic([1e-8, 90000], temperature=1)
    assert r["included_modes_one_based"] == [1, 2]
    assert r["thermal_enthalpy_ev"] == pytest.approx(KB, rel=1e-7)
    assert math.isfinite(r["gibbs_correction_ev"])


@pytest.mark.parametrize("modes,excluded", [([0], None), ([-1, 15], None), ([-1, -2, 15], 1), ([15], 1)])
def test_zero_or_unassigned_modes(modes, excluded):
    with pytest.raises(ValueError):
        harmonic(modes, excluded_mode=excluded)


def test_scaled_zpe_and_independent_frequency_uncertainties():
    r = harmonic([100, -50, 200], scale=0.9, scaling_reference="synthetic calibration", excluded_mode=2,
                 mode_sigma_cm1=[3, 20, 4])
    assert r["included_modes_one_based"] == [1, 3]
    assert r["zpe_ev"] == pytest.approx(150 * 0.9 * CM1_EV)
    assert r["zpe_sigma_ev"] == pytest.approx(0.5 * 0.9 * CM1_EV * 5)
    assert r["gibbs_correction_ev"] is None
    with pytest.raises(ValueError, match="reference"):
        harmonic([100], scale=0.9)


def test_gibbs_uncertainty_derivative():
    kwargs = dict(temperature=350)
    g = harmonic([100], mode_sigma_cm1=[1.5], **kwargs)
    delta = harmonic([100.001], **kwargs)["gibbs_correction_ev"] - harmonic([99.999], **kwargs)["gibbs_correction_ev"]
    assert g["gibbs_sigma_ev"] == pytest.approx(delta / 0.002 * 1.5)


def test_gas_pressure_dependence_and_linear_rotor_enthalpy():
    model = dict(mass_amu=28, moments_amu_angstrom2=[8.8], symmetry_number=2, electronic_degeneracy=1)
    surface = harmonic([2170], temperature=300)
    a, b = surface.copy(), surface.copy()
    add_ideal_gas(a, model, 1e5)
    add_ideal_gas(b, model, 2e5)
    assert a["thermal_enthalpy_ev"] - surface["thermal_enthalpy_ev"] == pytest.approx(3.5 * KB * 300)
    assert b["gibbs_correction_ev"] - a["gibbs_correction_ev"] == pytest.approx(KB * 300 * math.log(2))
    assert "gas_contributions" not in surface


def test_vasp_observations(tmp_path):
    pos = tmp_path / "POSCAR"
    pos.write_text("toy\n1\n5 0 0\n0 5 0\n0 0 5\nH\n2\nSelective dynamics\nDirect\n0 0 0 F F F\n.5 .5 .5 T T F\n")
    out = tmp_path / "OUTCAR"
    example = " NIONS = 2 IBRION = 5\n 1 f  = 2.1 THz 70.5 cm-1 8 meV\n 2 f/i= 1 THz 33.3 cm-1 4 meV\n"
    out.write_text(example)
    r = parse_outcar(out, pos)
    assert r["frequencies_cm1"] == [70.5, -33.3] and r["atom_map"] == [1]
    assert r["cartesian_count_matches"] and r["settings"]["IBRION"] == "5"
    assert len(r["source_artifact_hash"]) == 64 and r["validation_status"] == "unreviewed"
    upload = draft_intake(r, "synthetic", "TS")
    validator().validate(upload)
    assert upload["records"][0]["acceptance"]["acceptance_status"] == "pending"
    out.write_text(example.replace("70.5 cm-1", "7.05D+1 cm-1"))
    assert parse_outcar(out, pos)["frequencies_cm1"] == [70.5, -33.3]
    out.write_text(example + " 3 f = invalid\n")
    with pytest.raises(ValueError, match="frequency row"):
        parse_outcar(out, pos)


def test_fe110_published_evidence_only():
    doc = case()
    r = calculate([doc], ts_review=review(), phase="adsorbate")
    assert r["electronic_ev"] == pytest.approx(dict(forward=0.97360174, reverse=0.31429371, reaction=0.65930803))
    assert r["states"]["TS"]["zpe_ev"] == pytest.approx(0.5140516496724512)
    assert r["states"]["TS"]["excluded_reaction_coordinate_one_based"] == 12
    assert r["states"]["TS"]["included_modes_one_based"] == list(range(1, 12))
    assert r["states"]["IS"] is r["states"]["FS"] is r["reaction"] is None
    assert r["status"] == "partial" and not r["execution_authorized"]
    assert doc == case()


def test_missing_phase_does_not_grant_surface_or_gas_correction():
    doc = case()
    r = calculate([doc, synthetic_upload(doc)], ts_review=review())
    assert r["reaction"] is None and any("Specify gas or adsorbate" in x for x in r["issues"])
    assert r["states"]["TS"]["zpe_ev"] > 0 and r["states"]["TS"]["gibbs_correction_ev"] is None


def test_human_acceptance_preserves_provisional_result():
    doc = case()
    up = synthetic_upload(doc)
    record = up["records"][0]
    record["validation"].update(validation_status="unreviewed", limitations=["Example only"])
    record["acceptance"].update(acceptance_status="accepted", acceptance_scope=["thermochemistry"],
                                accepted_by="example", acceptance_reason="Sensitivity fixture",
                                acceptance_timestamp="2026-11-19T12:00:00+08:00")
    r = calculate([doc, up], phase="adsorbate", ts_review=review())
    assert r["status"] == "scoped_estimate" and "IS.corrections" in r["scoped_unverified_inputs"]
    assert not r["execution_authorized"] and r["states"]["IS"]["validation"]["validation_status"] == "unreviewed"


@pytest.mark.parametrize("change", ["grade", "source", "constraints", "structure", "index"])
def test_ts_grade_and_evidence_binding(change):
    a = review()
    if change == "grade":
        a["scientific_review_sources"]["TS"]["grade"] = a["ts_mode_review"]["grade"] = "B"
    elif change == "source":
        a["states"]["TS"]["frequency_output"]["sha256"] = "a" * 64
    elif change == "constraints":
        a["states"]["TS"]["frequency_constraints"] = "other"
    elif change == "structure":
        a["states"]["TS"]["structure"]["sha256"] = "b" * 64
    else:
        a["ts_mode_review"]["index"] = 1
    r = calculate([case()], ts_review=a)
    assert r["states"]["TS"] is None and r["reaction"] is None


def test_mixed_source_reaction_closure_and_unknown_uncertainty():
    doc = case()
    up = synthetic_upload(doc)
    r = calculate([doc, up], phase="adsorbate", ts_review=review())
    assert r["status"] == "complete"
    assert r["states"]["IS"]["route"] == "corrections" and r["states"]["TS"]["route"] == "spectrum"
    assert all("original_calculation_id" not in v["provenance"] for v in up["records"])
    reaction = r["reaction"]
    assert reaction["closure_residual_ev"] == pytest.approx(0, abs=1e-12)
    for key in ("reaction", "forward", "reverse"):
        assert reaction["free_energy_ev"][key] == pytest.approx(reaction["electronic_ev"][key] + reaction["thermal_ev"][key])
        assert reaction["free_energy_sigma_ev"][key] is None


@pytest.mark.parametrize("field,value", [("standard_state", "other"), ("temperature_k", 310),
                                          ("structure_identity", "different"), ("thermal_basis", "other model"),
                                          ("gibbs_correction_ev", 0.35)])
def test_mismatches_and_double_counting(field, value):
    doc = case()
    up = synthetic_upload(doc)
    up["records"][0]["value"][field] = value
    r = calculate([doc, up], phase="adsorbate", ts_review=review())
    assert r["reaction"] is None and r["issues"]


def test_only_precomputed_with_independent_uncertainty():
    doc = case()
    up = synthetic_upload(doc, ("IS", "TS", "FS"))
    doc["records"].remove(spectrum(doc))
    for r in doc["records"]:
        if r["kind"] == "electronic_energy":
            r["thermal_model"] = {"electronic_sigma_ev": 0.02}
    for r in up["records"]:
        r["thermal_model"] = {"gibbs_sigma_ev": 0.01}
    r = calculate([doc, up], ts_review=review(), independent_errors=True)
    assert r["status"] == "complete"
    assert r["reaction"]["free_energy_sigma_ev"]["forward"] == pytest.approx(math.sqrt(0.001))
    assert all(s["route"] == "corrections" for s in r["states"].values())


def test_zpe_only_and_raw_subspace_mismatch():
    doc = case()
    up = synthetic_upload(doc)
    for r in up["records"]:
        r["value"] = {k: r["value"][k] for k in ("structure_identity", "thermal_basis", "zpe_ev")}
    assert calculate([doc, up], operation="zpe", ts_review=review())["status"] == "complete"
    assert calculate([doc, up], ts_review=review())["reaction"] is None
    record = copy.deepcopy(spectrum(doc))
    record.update(state="IS", id="synthetic-IS-spectrum")
    record["value"].update(frequencies_cm1=[20, 30, 40], atom_map=[45], expected_modes=3,
                           structure_identity=up["records"][0]["value"]["structure_identity"])
    doc["records"].append(record)
    r = calculate([doc, {"schema_version": 1, "reaction_id": doc["reaction_id"], "records": up["records"][1:]}],
                  operation="zpe", ts_review=review())
    assert any("active maps" in item for item in r["issues"])
