"""V2 contracts use synthetic serialized rates. No engine or database is needed."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.multiphase_contracts import main as v1_main, read_unique_json, validate_bundle
from scripts.rate_output_v2 import generate_source_terms, main, validate_rate_output_v2


FIX = Path(__file__).parent / "fixtures" / "multiphase"


@pytest.fixture
def output():
    return read_unique_json(FIX / "rate_output_v2.json")


def test_native_progress_and_inventory_source_terms(output):
    before = deepcopy(output)
    validate_rate_output_v2(output)
    assert output == before
    calculated = generate_source_terms(iter(output["reaction_rates"]))
    assert {r["species_id"]: r["net_production_rate"] for r in calculated["species"]} == {
        "H2-g": -2, "H-alpha": 5, "H-beta": -1,
    }
    assert calculated["site_inventories"] == output["source_terms"]["site_inventories"]
    output["reaction_rates"].reverse()
    output["source_terms"]["species"].reverse()
    output["native_normalization"].update(denominator_value=100, denominator_unit="lattice sites",
                                         reference_id="lattice-population", definition="Per 100 lattice sites")
    validate_rate_output_v2(output)
    assert output["native_normalization"]["denominator_value"] == 100


def test_zero_and_unknown_are_distinct(output):
    row = output["reaction_rates"][0]
    row["reverse"] = row["forward"]
    row["net"] = 0
    output["source_terms"] = generate_source_terms(output["reaction_rates"])
    assert {v["species_id"]: v["net_production_rate"] for v in output["source_terms"]["species"]}["H2-g"] == 0
    output.update(validity_range=None)
    output["conditions"]["partial_pressures"] = None
    validate_rate_output_v2(output)
    row["net"] = None
    with pytest.raises(ValueError, match="net"):
        validate_rate_output_v2(output)


@pytest.mark.parametrize("key", ["format", "schema_version"])
@pytest.mark.parametrize("value", [None, "1.0.0", "2", "2.0.1", "kinetic-rate-output/3"])
def test_exact_discriminators(output, key, value):
    if value is None:
        del output[key]
    else:
        output[key] = value
    with pytest.raises(ValueError, match=key):
        validate_rate_output_v2(output)


@pytest.mark.parametrize("path", [
    (), ("engine",), ("native_normalization",), ("conditions",), ("conditions", "partial_pressures", 0),
    ("reaction_rates", 0), ("source_terms",), ("source_terms", "species", 0), ("source_terms", "site_inventories", 0),
    ("validity_range",), ("provenance",), ("provenance", "dataset"), ("validation",),
])
def test_unknown_properties_are_never_discarded(output, path):
    target = output
    for key in path:
        target = target[key]
    target["unexpected"] = True
    with pytest.raises(ValueError, match="unexpected|Additional properties|not valid"):
        validate_rate_output_v2(output)


@pytest.mark.parametrize("path", [
    ("dataset_version",), ("network_version",), ("reaction_rates", 0, "parameter_set_id"),
    ("native_normalization", "reference_id"), ("provenance", "network"),
    ("provenance", "dataset", "sha256"), ("provenance", "native_output", "path"),
])
def test_incomplete_bindings_fail(output, path):
    target = output
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]
    with pytest.raises(ValueError, match=str(path[-1])):
        validate_rate_output_v2(output)


@pytest.mark.parametrize(("path", "bad"), [
    (("network_version",), "old"), (("provenance", "native_output", "sha256"), "short"),
    (("validation", "status"), "accepted"), (("native_normalization", "denominator_value"), 0),
    (("conditions", "temperature_K"), 500), (("conditions", "partial_pressures", 0, "pressure_Pa"), 100001),
    (("reaction_rates", 0, "net"), 5), (("reaction_rates", 1, "reaction_id"), "dissociate"),
    (("reaction_rates", 1, "parameter_set_id"), "p-dissociate"), (("reaction_rates", 0, "forward"), -1),
    (("reaction_rates", 0, "net"), float("nan")), (("source_terms", "species", 0, "net_production_rate"), 2),
    (("source_terms", "species", 0, "species_id"), "ghost"),
    (("source_terms", "site_inventories", 0, "site_id"), "beta"),
    (("source_terms", "site_inventories", 0, "net_vacancy_rate"), -2),
    (("source_terms", "site_inventories"), []), (("validity_range", "max_pressure_Pa"), 1),
])
def test_invalid_rates_and_sources(output, path, bad):
    target = output
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = bad
    with pytest.raises(ValueError):
        validate_rate_output_v2(output)


@pytest.mark.parametrize("duplicate", ['"format":', '"native_output":', '"net_production_rate":'])
def test_nested_duplicate_keys_fail_in_file_reader(output, tmp_path, duplicate, capsys):
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(output).replace(duplicate, duplicate + " null, " + duplicate, 1))
    with pytest.raises(SystemExit) as exc:
        main([path.as_posix()])
    assert exc.value.code == 1 and "duplicate JSON property" in capsys.readouterr().err


def test_cli_and_both_version_boundaries(output):
    old = FIX / "valid.json"
    new = FIX / "rate_output_v2.json"
    assert main([str(new)]) == v1_main([str(old)]) == 0
    for cli, path in ((main, old), (v1_main, new)):
        with pytest.raises(SystemExit) as exc:
            cli([str(path)])
        assert exc.value.code == 1
    mixed = dict(read_unique_json(old), **output)
    for validate in (validate_bundle, validate_rate_output_v2):
        with pytest.raises(ValueError):
            validate(mixed)
    legacy = read_unique_json(old)
    legacy["format"] = output["format"]
    with pytest.raises(ValueError):
        validate_bundle(legacy)


def test_tiny_signal_and_spectator_are_preserved(output):
    row = output["reaction_rates"][0]
    output["reaction_rates"] = [row]
    row.update(forward=1e-30, reverse=0, net=1e-30)
    row["reactants"]["spectator"] = row["products"]["spectator"] = 2
    output["source_terms"] = generate_source_terms([row])
    amounts = {s["species_id"]: s["net_production_rate"] for s in output["source_terms"]["species"]}
    assert amounts == {"H2-g": -1e-30, "H-alpha": 2e-30, "spectator": 0}
    validate_rate_output_v2(output)
    row["net"] = 0
    with pytest.raises(ValueError, match="net must equal"):
        validate_rate_output_v2(output)


def test_derived_overflow_is_reported(output):
    row = output["reaction_rates"][0]
    row.update(forward=1e308, reverse=0, net=1e308)
    with pytest.raises(ValueError, match="finite numeric range"):
        validate_rate_output_v2(output)


def test_both_schema_resources_and_standalone_fragment(output):
    from jsonschema import Draft202012Validator

    from scripts.runtime_resources import resource_path

    for name in ("rate_output_v2", "rate_source_terms_v2"):
        schema = read_unique_json(resource_path(f"configs/kinetics/{name}.schema.json"))
        Draft202012Validator.check_schema(schema)
    with pytest.raises(ValueError):
        validate_rate_output_v2(output["source_terms"])
