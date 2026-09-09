from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.artifact_io import sha256_json
from scripts.neb_agent.utils_vasp import parse_oszicar, parse_outcar
from scripts.scientific_validation import finite_number, integer_number
from scripts.ts_strategy_engine.contract import load_contract, normalize_contract
from scripts.ts_strategy_engine.execution_evidence import validated_ts
from scripts.ts_strategy_engine.fingerprint import build_fingerprint, rank_templates
from scripts.ts_strategy_engine.strategy import compose_strategy
from scripts.vasp_result_gate import final_scf_status, read_incar_values

ROOT = Path(__file__).resolve().parents[1]


def raw_contract():
    return {"reaction_id": "co", "reaction_family": "co_dissociation", "reactant_id": "co*",
            "product_id": "c*+o*", "index_base": 0, "atom_map": [[0, 0], [1, 1], [2, 2]],
            "atom_symbols": ["Fe", "C", "O"], "reaction_atoms": [1, 2],
            "broken_bonds": [[1, 2]], "formed_bonds": [], "site_changes": [],
            "compatibility": {"material": "Fe", "surface": "110", "branch": "test",
                              "slab_model": "FeCO", "xc": "pbe", "potcar_family": "paw_pbe",
                              "encut_ev": 400, "kmesh": [5, 5, 1], "magnetic_state": "fm", "coverage": "test"},
            "endpoints": {side: {"calculation_id": side, "structure_file_id": side + "_s",
                                  "static_result_id": side + "_e"} for side in ("initial", "final")}}


def rehash(contract):
    contract["atom_map_sha256"] = sha256_json(contract["atom_map"])
    contract["compatibility_sha256"] = sha256_json(contract["compatibility"])
    contract.pop("contract_sha256", None)
    contract["contract_sha256"] = sha256_json(contract)
    return contract


def vasp_files(tmp_path, oszicar, outcar=None, nelm=60):
    (tmp_path / "INCAR").write_text(f"NELM={nelm}; EDIFF=1e-5\n")
    (tmp_path / "OSZICAR").write_text(oszicar)
    if outcar is not None:
        (tmp_path / "OUTCAR").write_text(outcar)
    return final_scf_status(tmp_path / "OSZICAR", tmp_path / "INCAR",
                            tmp_path / "OUTCAR" if outcar is not None else None, include_cycles=True)


def osz_cycle(step, iteration=5, delta="1e-7", complete=True, band="1e-7"):
    return (f"DAV: {iteration} -100 {delta} {band} 20 1e-4\n"
            + (f" {step} F= -100 E0= -100 d E= 0\n" if complete else ""))


def out_cycle(step, iteration=5, converged=True, complete=True):
    return (f"Iteration {step}( {iteration})\n"
            + ("aborting loop because EDIFF is reached\n" if converged else "")
            + ("energy(sigma->0) = -100\n" if complete else ""))


@pytest.mark.parametrize("final,expected", [("incomplete", "INCOMPLETE"), ("nelm", "NOT_CONVERGED"), ("valid", "PASS")])
def test_final_cycle_controls_convergence(tmp_path, final, expected):
    iteration = 60 if final == "nelm" else 5
    complete = final != "incomplete"
    out = out_cycle(1) + out_cycle(2, iteration, final == "valid", complete)
    if complete:
        out += "General timing and accounting informations for this job\n"
    status = vasp_files(tmp_path, osz_cycle(1) + osz_cycle(2, iteration, complete=complete), out)
    assert status["status"] == expected
    assert status["electronically_converged"] is (final == "valid")
    assert status["latest_started_electronic_cycle"]["cycle"] == 2
    assert status["latest_completed_electronic_cycle"]["cycle"] == (2 if complete else 1)
    assert status["final_target_complete"] is complete


@pytest.mark.parametrize("tail", ["DAV:", "DAV: 1 -100", "DAV: 1 -100 NaN 0", "       N E dE d eps\n"])
def test_truncated_oszicar_cannot_reuse_old_cycle(tmp_path, tail):
    status = vasp_files(tmp_path, osz_cycle(1) + tail, out_cycle(1))
    assert status["status"] == "INCOMPLETE"
    assert status["electronically_converged"] is False


def test_truncated_outcar_and_appended_run_clear_success(tmp_path):
    path = tmp_path / "OUTCAR"
    for tail in ("Iteration 2( 1)\n", "Iteration 2(\n", "vasp.6.4\n"):
        path.write_text(out_cycle(1) + "reached required accuracy\nGeneral timing and accounting informations for this job\n" + tail)
        parsed = parse_outcar(path)
        assert parsed["incomplete"]
        assert not parsed["electronic_convergence_reached"]
        assert not parsed["normal_completion"]
        assert not parsed["reached_required_accuracy"]


def test_dimer_evaluations_in_same_ionic_step_do_not_reuse_convergence(tmp_path):
    out = out_cycle(1) + "Iteration 1( 1)\n"
    status = vasp_files(tmp_path, osz_cycle(1) + osz_cycle(1, iteration=1, complete=False), out)
    assert status["status"] == "INCOMPLETE"


@pytest.mark.parametrize("band", ["1e-2", "NaN", "Inf", "-Inf"])
def test_energy_delta_alone_does_not_prove_ediff(tmp_path, band):
    status = vasp_files(tmp_path, osz_cycle(1, band=band))
    assert status["electronically_converged"] is False


def test_complete_oszicar_can_supply_both_final_ediff_components(tmp_path):
    assert vasp_files(tmp_path, osz_cycle(1))["status"] == "PASS"


@pytest.mark.parametrize("text", ["NELM=60; EDIFF=1e-5", "  nelm = 60 ; eDiFf = 1e-5  ",
                                  "NELM=60; EDIFF=1e-5 # comment; NELM=3", "NELM=60 ! comment\nEDIFF=1e-5",
                                  "NELM=60; NELM=60; EDIFF=1e-5"])
def test_canonical_incar_syntax(tmp_path, text):
    path = tmp_path / "INCAR"
    path.write_text(text)
    assert read_incar_values(path) == {"NELM": "60", "EDIFF": "1e-5"}


@pytest.mark.parametrize("text", ["NELM=", "=60", "NELM=60 EDIFF=1e-5", "NELM=sixty",
                                  "NELM=60; NELM=20", "ENCUT=NaN", "EDIFF=Inf", "NELM=1.5", 'SYSTEM="broken'])
def test_malformed_incar_fails_closed(tmp_path, text):
    path = tmp_path / "INCAR"
    path.write_text(text)
    with pytest.raises(ValueError):
        read_incar_values(path)


def test_incar_retains_vector_logical_and_quoted_values(tmp_path):
    path = tmp_path / "INCAR"
    path.write_text('MAGMOM=3*2.0; LCLIMB=.TRUE.; SYSTEM="a; b # literal ! text"\n')
    assert read_incar_values(path) == {"MAGMOM": "3*2.0", "LCLIMB": ".TRUE.", "SYSTEM": "a; b # literal ! text"}


@pytest.mark.parametrize("field,value", [("index_base", 2), ("reaction_atoms", []), ("reaction_atoms", [-1]),
                                         ("reaction_atoms", [7]), ("atom_map", [[0, 0], [0, 1], [2, 2]]),
                                         ("atom_map", [[0, 0], [1, 1], [2, 7]]), ("reaction_id", None),
                                         ("reaction_id", "None"), ("broken_bonds", [[1, 1]])])
def test_self_consistent_normalized_contract_still_needs_semantics(tmp_path, field, value):
    payload = normalize_contract(raw_contract())
    payload[field] = value
    rehash(payload)
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_contract(path)
    with pytest.raises(ValueError):
        normalize_contract(payload)


@pytest.mark.parametrize("field,value", [("encut_ev", 0), ("encut_ev", -1), ("encut_ev", float("nan")),
                                         ("encut_ev", float("inf")), ("encut_ev", float("-inf")),
                                         ("kmesh", [0, 1, 1]), ("kmesh", [-1, 1, 1]), ("kmesh", [1.5, 1, 1]),
                                         ("kmesh", [1, float("inf"), 1]), ("kmesh", None), ("xc", None)])
def test_raw_and_rehashed_compatibility_use_same_validator(field, value):
    raw = raw_contract()
    normalized = normalize_contract(raw)
    raw["compatibility"][field] = value
    normalized["compatibility"][field] = value
    for payload in (raw, rehash(normalized)):
        with pytest.raises(ValueError):
            normalize_contract(payload)


def test_endpoint_metadata_none_and_coordinate_nonfinite_are_rejected():
    raw = raw_contract()
    raw["endpoints"]["initial"]["calculation_id"] = None
    with pytest.raises(ValueError):
        normalize_contract(raw)
    raw = raw_contract()
    raw["reaction_coordinates"] = [{"kind": "distance", "name": "CO", "role": "primary",
                                    "atoms": [1, 2], "important_interval_A": [1, float("inf")]}]
    with pytest.raises(ValueError):
        normalize_contract(raw)


def test_valid_normalized_roundtrip_preserves_identity(tmp_path):
    contract = normalize_contract(raw_contract())
    path = tmp_path / "contract.yaml"
    path.write_text(yaml.safe_dump(contract))
    assert load_contract(path) == contract == normalize_contract(contract)


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf"), "NaN", "Inf", "-Inf", None, True])
def test_shared_scientific_number_validation(number):
    with pytest.raises(ValueError):
        finite_number(number, "value")
    with pytest.raises(ValueError):
        integer_number(number, "index")


@pytest.mark.parametrize("family,symbols,broken,formed,valid", [
    ("co_dissociation", ["Fe", "C", "O"], [[1, 2]], [], True),
    ("co_dissociation", ["Fe", "C", "O"], [[0, 2]], [], False),
    ("c_c_coupling", ["Fe", "C", "C"], [], [[1, 2]], True),
    ("c_c_coupling", ["Fe", "C", "O"], [], [[1, 2]], False),
])
def test_family_matches_declared_chemical_event(family, symbols, broken, formed, valid):
    contract = raw_contract()
    contract.update(reaction_family=family, atom_symbols=symbols, broken_bonds=broken, formed_bonds=formed)
    rules = yaml.safe_load((ROOT / "configs/ts_strategy_engine/families.yaml").read_text())
    result = compose_strategy(build_fingerprint(contract), [], rules)
    assert (result["status"] != "STOP_FAMILY_CONTRACT_MISMATCH") is valid


def test_renumbered_chemistry_is_comparable_but_not_reusable_result():
    left = build_fingerprint(raw_contract())
    raw = raw_contract()
    raw.update(atom_symbols=["C", "Fe", "O"], reaction_atoms=[0, 2], broken_bonds=[[0, 2]])
    right = build_fingerprint(raw)
    template = {"template_id": "prior", "fingerprint": left, "evidence_valid": True,
                "outcome": "success", "validation_grade": "A"}
    ranked = rank_templates(right, [template])[0]
    assert ranked["chemical_event_equivalent"]
    assert ranked["strategy_transferable"]
    assert not ranked["result_transferable"]
    assert left["fingerprint_id"] != right["fingerprint_id"]
    raw["atom_symbols"] = ["H", "Fe", "O"]
    wrong = rank_templates(build_fingerprint(raw), [template])[0]
    assert not wrong["chemical_event_equivalent"]
    assert not wrong["strategy_transferable"]


def test_missing_element_evidence_and_different_endpoint_identity_cannot_reuse():
    raw = raw_contract()
    left = build_fingerprint(raw)
    template = {"template_id": "prior", "fingerprint": left, "evidence_valid": True,
                "outcome": "success", "validation_grade": "A"}
    raw["endpoints"]["initial"]["static_result_id"] = "another-result"
    result = rank_templates(build_fingerprint(raw), [template])[0]
    assert result["strategy_transferable"] and not result["result_transferable"]
    raw.pop("atom_symbols")
    result = rank_templates(build_fingerprint(raw), [template])[0]
    assert not result["strategy_transferable"]


@pytest.mark.parametrize("method", ["neb", "dimer"])
def test_ts_acceptance_requirements_preserved(method):
    evidence = {"source_method": method, "frequency_grade": "A", "source_saddle_sha256": "a" * 64,
                "frequency_poscar_sha256": "a" * 64, "bidirectional_connectivity_valid": True,
                "dimer_technical_acceptance": True}
    assert validated_ts(evidence)
    for change in ({"frequency_grade": "B"}, {"frequency_poscar_sha256": "b" * 64},
                   {"dimer_technical_acceptance": False} if method == "dimer" else {"bidirectional_connectivity_valid": False}):
        assert not validated_ts({**evidence, **change})


def test_remote_audit_uses_same_parser_without_remote_dependencies(tmp_path):
    from scripts.adsorption.backfill_step12a_registry import remote_parser_preamble

    namespace = {}
    exec(remote_parser_preamble(), namespace)
    path = tmp_path / "INCAR"
    path.write_text("NELM=60; EDIFF=1e-5")
    assert namespace["_vasp_parser"]["read_incar_values"](path) == read_incar_values(path)
    osz = tmp_path / "OSZICAR"
    osz.write_text(osz_cycle(1) + osz_cycle(2, complete=False))
    assert namespace["_vasp_parser"]["parse_oszicar"](osz) == parse_oszicar(osz)


def test_nonfinite_scientific_thresholds_fail_before_decision():
    from scripts.neb_agent.path_quality_control import evaluate_quality
    from scripts.ts_validation.analyze_vfa import _frequency_policy

    with pytest.raises(ValueError, match="finite"):
        evaluate_quality({}, {"geometry": {"threshold": float("nan")}})
    with pytest.raises(ValueError, match="finite"):
        _frequency_policy({"meaningful_imaginary_frequency_min_cm1": float("inf")})


def test_legacy_path_binding_key_survives_chemical_enrichment():
    raw = raw_contract()
    symbols = raw.pop("atom_symbols")
    legacy = build_fingerprint(raw)
    enriched = build_fingerprint(raw, atom_symbols=symbols)
    assert legacy["fingerprint_id"] == enriched["fingerprint_id"]
    assert legacy["chemical_event_sha256"] is None
    assert enriched["chemical_events"]["broken_bonds"] == ["C-O"]
    assert enriched["chemical_event_sha256"]


def test_truncated_outcar_energy_summary_is_incomplete(tmp_path):
    status = vasp_files(tmp_path, osz_cycle(1), out_cycle(1, complete=False) + "energy(sigma->0) =")
    assert status["status"] == "INCOMPLETE"
    assert not status["electronically_converged"]


@pytest.mark.parametrize("bad", ["NaN", "Inf", "-Inf"])
def test_nonfinite_text_thresholds_are_not_silently_coerced(bad):
    from scripts.ts_validation.analyze_vfa import _frequency_policy

    with pytest.raises(ValueError, match="finite"):
        _frequency_policy({"meaningful_imaginary_frequency_min_cm1": bad})


def test_legacy_scf_summary_retains_strict_schema_fields(tmp_path):
    detailed = vasp_files(tmp_path, osz_cycle(1))
    legacy = final_scf_status(tmp_path / "OSZICAR", tmp_path / "INCAR")
    assert set(legacy) == {"last_electronic_iteration", "last_delta_e_eV", "ediff_eV", "nelm",
                           "electronically_converged", "electronic_convergence_source"}
    assert legacy == {key: detailed[key] for key in legacy}


@pytest.mark.parametrize("value", ["NaN", "Inf", "-Inf"])
@pytest.mark.parametrize("location", ["frequency", "vector"])
def test_nonfinite_vfa_evidence_cannot_be_skipped(value, location):
    from scripts.ts_validation.analyze_vfa import _frequency_modes

    frequency = value if location == "frequency" else "100"
    vector = value if location == "vector" else "0.1"
    text = f"1 f/i= 1 THz 1 2PiTHz {frequency} cm-1\n1 0 0 0 {vector} 0 0\n"
    with pytest.raises(ValueError, match="finite"):
        _frequency_modes(text)


def test_baseline_direct_cli_retains_standard_library_runtime(tmp_path):
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "-S", str(ROOT / "modules/fe_convergence_baseline/validate_baseline.py")],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "PASS: alpha-Fe convergence baseline is internally consistent" in result.stdout



def test_overflowing_numeric_text_in_policy_is_not_a_finite_threshold():
    from scripts.scientific_validation import validate_finite_tree

    with pytest.raises(ValueError, match="finite"):
        validate_finite_tree({"force_threshold": "1e999"})
