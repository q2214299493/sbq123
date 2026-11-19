import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.multiphase_contracts import COLLECTIONS, main, validate_bundle
from scripts.runtime_resources import resource_path


FIXTURES = Path(__file__).parent / "fixtures" / "multiphase"


@pytest.fixture
def bundle():
    return json.loads((FIXTURES / "valid.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("collection,name,key", COLLECTIONS)
def test_all_record_schemas_are_strict_and_versioned(bundle, collection, name, key):
    folder = "catalysis" if collection in {"projects", "materials", "phases", "surfaces", "sites", "interfaces"} else "kinetics"
    schema = json.loads(resource_path(f"configs/{folder}/{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    row = bundle[collection][0]
    row["extra"] = "typo"
    with pytest.raises(ValueError, match="Additional properties"):
        validate_bundle(bundle)
    del row["extra"]
    row["schema_version"] = "2.0.0"
    with pytest.raises(ValueError, match="1.0.0"):
        validate_bundle(bundle)
    row["schema_version"] = "1.0.0"
    del row[key]
    with pytest.raises(ValueError, match=key):
        validate_bundle(bundle)


def test_bundle_and_packaged_schema_resources(bundle):
    validate_bundle(bundle)
    for name in ("configs/catalysis/common.schema.json", "configs/kinetics/bundle.schema.json"):
        Draft202012Validator.check_schema(json.loads(resource_path(name).read_text(encoding="utf-8")))


@pytest.mark.parametrize(("path", "bad", "message"), [
    (("species", 1, "charge"), 1, "charge conservation"),
    (("species", 1, "composition"), {"H": 1}, "element conservation"),
    (("species", 0, "composition"), {"Xx": 1}, "not one of"),
    (("species", 1, "site_occupancy", "top-Ni"), 2, "site conservation"),
    (("species", 1, "surface_ids"), ["facet-Cu"], "interface and surface"),
    (("species", 1, "material_ids"), ["Cu"], "material/surface identity"),
    (("species", 2, "species_id"), "H2-bridge", "duplicate ID"),
    (("species", 0, "adsorption_geometry"), "bridge", "null"),
    (("phases", 0, "material_id"), "absent", "unknown materials"),
    (("surfaces", 0, "miller_indices"), [0, 0, 0], "contain items"),
    (("surfaces", 0, "miller_indices"), [1, 0, 1, 0], "Miller-Bravais"),
    (("sites", 0, "surface_id"), "absent", "unknown surfaces"),
    (("interfaces", 0, "surface_ids"), ["facet-Ni", "facet-Ni"], "non-unique"),
    (("reactions", 0, "phase_ids"), ["fcc-Ni"], "phase/surface"),
    (("reactions", 0, "interface_id"), None, "requires an interface"),
    (("reactions", 0, "products"), {"unknown": 1}, "unknown species"),
    (("reactions", 0, "reactants"), {"H2-g": -1}, "minimum"),
    (("reactions", 0, "required_sites"), {"bridge-Cu": 1}, "footprint"),
    (("reactions", 0, "ts_id"), None, "not of type"),
    (("reactions", 0, "electronic_energies", "forward", "value"), 1.0, "minus reverse"),
    (("reactions", 0, "free_energies", "values", "reverse", "value"), 0.51, "minus reverse"),
    (("reactions", 0, "electronic_energies", "forward", "reference_id"), "other", "energy reference"),
    (("reactions", 0, "electronic_energies", "forward", "unit"), "kJ/mol", "eV"),
    (("reactions", 0, "free_energies", "values", "reverse", "source", "calculation_id"), "wrong", "provenance"),
    (("reactions", 0, "reversible"), False, "irreversible"),
    (("reactions", 0, "eligibility"), "eligible", "accepted"),
    (("parameter_sets", 0, "energy_reference_id"), "other", "parameter reference"),
    (("parameter_sets", 0, "rate_law_id"), "other", "rate law"),
    (("parameter_sets", 0, "standard_state_id"), "other", "standard state"),
    (("parameter_sets", 0, "forward", "prefactor"), 0, "minimum"),
    (("parameter_sets", 0, "forward", "prefactor_unit"), "unknown", "not one of"),
    (("parameter_sets", 0, "temperature_K"), 500, "validity"),
    (("parameter_sets", 0, "temperature_K"), 405, "Gibbs temperature"),
    (("parameter_sets", 0, "forward", "activation_energy", "value"), 0.34, "differs"),
    (("parameter_sets", 0, "sources", 0, "artifact", "sha256"), "short", "does not match"),
    (("runs", 1, "engine"), "CATKINAS", "required property|Additional properties"),
    (("runs", 1, "parameter_set_ids"), ["absent"], "unknown parameter_sets"),
    (("runs", 0, "approval_status"), "approved", "not of type"),
    (("runs", 0, "execution_status"), "accepted", "not one of"),
])
def test_bad_records_fail_closed(bundle, path, bad, message):
    target = bundle
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = bad
    with pytest.raises(ValueError, match=message):
        validate_bundle(bundle)


def test_missing_energies_are_explicit_and_survive_as_draft(bundle):
    rx = bundle["reactions"][0]
    rx.update(ts_treatment="unresolved", ts_id=None, free_energies=None)
    rx["electronic_energies"] = dict.fromkeys(("reaction", "forward", "reverse"))
    bundle["parameter_sets"][0].update(forward=None, reverse=None)
    before = deepcopy(bundle)
    validate_bundle(bundle)
    assert before == bundle


def test_same_number_of_different_sites_cannot_cancel(bundle):
    bundle["reactions"][0]["sites_consumed"] = {"top-Ni": 2}
    with pytest.raises(ValueError, match="site conservation"):
        validate_bundle(bundle)


def test_different_interface_even_on_same_facets(bundle):
    another = dict(bundle["interfaces"][0], interface_id="other-junction", structure_id="other-structure")
    bundle["interfaces"].append(another)
    bundle["species"][1]["interface_id"] = "other-junction"
    with pytest.raises(ValueError, match="different interface"):
        validate_bundle(bundle)


def test_integer_stoichiometry_and_liquid_species(bundle):
    gas = bundle["species"][0]
    gas.update(species_id="H-liquid", phase="liquid", composition={"H": 1}, charge=1)
    rx = bundle["reactions"][0]
    rx["reactants"] = {"H-liquid": 2}
    bundle["species"][1]["charge"] = 2
    validate_bundle(bundle)


def test_separate_succeeded_unconverged_unapproved_run(bundle):
    run = bundle["runs"][1]
    run.update(execution_status="succeeded", numerical_convergence="unconverged")
    validate_bundle(bundle)
    run["scientific_validity"] = {"status": "accepted", "review": run["inputs"]["mechanism_input"]}
    with pytest.raises(ValueError, match="accepted run lacks"):
        validate_bundle(bundle)


def test_required_native_input_role(bundle):
    del bundle["runs"][1]["inputs"]["lattice_input"]
    with pytest.raises(ValueError, match="lattice_input"):
        validate_bundle(bundle)


def test_coverage_and_standard_states(bundle):
    p = bundle["parameter_sets"][0]
    term = {"species_id": "H2-bridge", "coefficient": p["forward"]["activation_energy"],
            "expression": "theta", "already_in_barrier": False, "min_fraction": 0, "max_fraction": 0.5}
    p["coverage_terms"] = [term]
    validate_bundle(bundle)
    term["min_fraction"] = 0.7
    with pytest.raises(ValueError, match="coverage validity"):
        validate_bundle(bundle)
    term.update(min_fraction=0, species_id="H2-g")
    with pytest.raises(ValueError, match="species on the reaction surface"):
        validate_bundle(bundle)
    p["coverage_terms"] = []
    other = deepcopy(p)
    other["parameter_set_id"] = "second"
    other["standard_states"]["gas_pressure_Pa"] = 42
    bundle["parameter_sets"].append(other)
    with pytest.raises(ValueError, match="conflicting standard-state"):
        validate_bundle(bundle)


def reviewed_example(bundle):
    # Exercise metadata constraints only. All values and receipts in this test are mock objects.
    reaction = bundle["reactions"][0]
    parameter = bundle["parameter_sets"][0]
    receipt = bundle["species"][0]["structural_provenance"]
    for rows in (bundle[c] for c, _, _ in COLLECTIONS if c != "runs"):
        for record in rows:
            record["validation"] = {"status": "accepted", "review": receipt}
    for s in bundle["species"]:
        s["thermochemistry_status"] = "reviewed"
    for owner, field in [(reaction, "provenance"), (parameter, "sources")]:
        owner["eligibility"] = "eligible"
        owner[field][0]["kind"] = "electronic_structure"
    thermal = deepcopy(reaction["provenance"][0])
    thermal.update(kind="thermal_correction", calculation_id="thermal-fixture")
    reaction["provenance"].append(thermal)
    parameter["sources"].append(thermal)
    for energy in reaction["electronic_energies"].values():
        energy["source"]["kind"] = "electronic_structure"
    for energy in reaction["free_energies"]["values"].values():
        energy["source"] = thermal
    for name in ("forward", "reverse"):
        parameter[name]["activation_energy"]["source"] = thermal
    return reaction, parameter


def test_eligibility_and_reversibility(bundle):
    rx, p = reviewed_example(bundle)
    validate_bundle(bundle)
    p["reverse"] = None
    with pytest.raises(ValueError, match="needs reverse rate"):
        validate_bundle(bundle)
    rx["reversible"] = False
    validate_bundle(bundle)
    rx["free_energies"]["values"]["forward"] = None
    with pytest.raises(ValueError, match="missing forward"):
        validate_bundle(bundle)


def test_prediction_cannot_supply_reviewed_energies(bundle):
    rx, _ = reviewed_example(bundle)
    rx["provenance"][0]["kind"] = "model_prediction"
    rx["electronic_energies"]["reaction"]["source"]["kind"] = "model_prediction"
    with pytest.raises(ValueError, match="scientific evidence"):
        validate_bundle(bundle)


def test_electronic_only_source_cannot_stand_in_for_thermochemistry(bundle):
    rx, _ = reviewed_example(bundle)
    rx["free_energies"]["values"]["forward"]["source"] = rx["provenance"][0]
    with pytest.raises(ValueError, match="thermochemical evidence"):
        validate_bundle(bundle)


def test_eligible_rate_cites_its_bound_barrier(bundle):
    _, p = reviewed_example(bundle)
    p["forward"]["activation_energy"]["source"] = p["sources"][0]
    with pytest.raises(ValueError, match="reaction barrier's source"):
        validate_bundle(bundle)


def test_eligible_reaction_requires_reviewed_catalyst(bundle):
    reviewed_example(bundle)
    bundle["sites"][0]["validation"]["status"] = "rejected"
    with pytest.raises(ValueError, match="reviewed catalyst"):
        validate_bundle(bundle)


def test_chemical_identifier_is_text_and_numbers_must_be_finite(bundle):
    bundle["materials"][0]["name"] = "InF"
    validate_bundle(bundle)
    bundle["parameter_sets"][0]["forward"]["prefactor"] = float("nan")
    with pytest.raises(ValueError, match="finite number"):
        validate_bundle(bundle)


@pytest.mark.parametrize("contents", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}', '{"x":', '[]'])
def test_cli_rejects_malformed_input(tmp_path, contents, capsys):
    path = tmp_path / "bad.json"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        main([str(path)])
    assert failure.value.code == 1
    assert "Invalid multiphase bundle" in capsys.readouterr().err


def test_fixture_cli(capsys):
    assert main([str(FIXTURES / "valid.json")]) == 0
    with pytest.raises(SystemExit) as failure:
        main([str(FIXTURES / "invalid.json")])
    assert failure.value.code == 1
    assert "missing-project" in capsys.readouterr().err
