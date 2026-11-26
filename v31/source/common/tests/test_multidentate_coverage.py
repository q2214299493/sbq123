"""Independent inventories on a version-bound synthetic interface; no solver required."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest
from referencing import Registry, Resource

from scripts.artifact_io import load_json_object as read, write_json_exclusive
from scripts.baseline_mkm import analysis as api
from scripts.baseline_mkm.analysis_report import markdown
from scripts.baseline_mkm.kinetic_analysis import activity_factors, coverage_analysis, indexed
from scripts.baseline_mkm.pathway_analysis import pathway_graph
from scripts.reaction_network.__main__ import read_source
from scripts.reaction_network.builder import build_network
from test_catkinas_closed_cycle import cycle_model
from test_mkm_analysis import BASE, accepted


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "reports/multiphase/phase3_1_1"
SCHEMAS = ROOT / "configs/kinetics"


@pytest.fixture
def inputs():
    return read(BENCH / "network.json"), read(BENCH / "observations.json")


def analyze(inputs):
    network, obs = inputs
    return coverage_analysis(network, obs, {})


def test_interface_benchmark_and_cli(tmp_path):
    sources = []
    network = build_network(read_source(ROOT / "tests/fixtures/multiphase/valid.json", "definition", sources), sources=sources)
    assert network == read(BENCH / "network.json")
    output = tmp_path / "coverage.json"
    args = ["coverage", str(BENCH / "network.json"), str(BENCH / "observations.json"), str(output)]
    api.main(args)
    assert output.read_bytes() == (BENCH / "validation.json").read_bytes()
    a = read(output)
    assert a["status"] == "complete"
    mol = indexed(a["species"], "species_id")
    assert len(mol) == 2 and mol["H2-bridge"]["molecular_coverage"] == 0.3
    assert mol["H2-bridge"]["phase_ids"] == ["fcc-Ni", "fcc-Cu"]
    assert mol["H2-bridge"]["interface_id"] == "junction"
    assert mol["H2-top"]["molecular_reference"] == {"kind": "inventory_site", "id": "top-Ni"}
    top, bridge = (a["sites"][k] for k in ("top-Ni", "bridge-Cu"))
    assert top["contributions"]["H2-bridge"] == {"multiplicity": 1, "occupied_fraction": 0.15}
    assert bridge["contributions"]["H2-bridge"]["occupied_fraction"] == 0.3
    assert top["competitors"] == ["H2-bridge", "H2-top"] and top["dominant_adsorbates"] == ["H2-top"]
    assert bridge["dominant_adsorbates"] == ["H2-bridge"]
    for site, vacancy in [(top, 0.6), (bridge, 0.7)]:
        assert site["occupied_fraction"] + site["vacancy_fraction"] == pytest.approx(1)
        assert site["balance_residual"] == pytest.approx(0)
        assert [v["mean_field_vacancy_factor"] for v in site["activity"]] == [vacancy, 1]
    draft = pathway_graph(network, None, ["H2-g"], ["H2-bridge"])
    assert "H2-bridge" in draft["feed_reachable_with_all_coreactants"]
    assert draft["pathway_percentages"] is None
    assert "rates" not in a
    with pytest.raises(FileExistsError):
        api.main(args)


@pytest.mark.parametrize("same_inventory", [True, False])
def test_same_surface_bidentate(inputs, same_inventory):
    network, obs = inputs
    s = indexed(network["species"], "species_id")["H2-bridge"]
    s.update(surface_ids=["facet-Ni"], interface_id=None)
    network["catalog"]["sites"][1]["surface_id"] = "facet-Ni"
    if same_inventory:
        s["site_occupancy"] = {"top-Ni": 2}
        obs["species"][0].pop("molecular_reference")
    obs["sites"] = []
    a = analyze(inputs)
    shares = a["sites"]["top-Ni"]["contributions"]
    assert shares["H2-bridge"]["occupied_fraction"] == pytest.approx(0.6 if same_inventory else 0.15)
    assert a["phase_comparison"]["fcc-Ni"]["occupied_fraction"] is None
    assert a["sites"]["top-Ni"]["vacancy_source"] == "site_balance"
    assert len(a["species"]) == 2


def test_unknown_reference_and_partial_denominator(inputs):
    _, obs = inputs
    row = obs["species"][0]
    ref = row.pop("molecular_reference")
    a = analyze(inputs)
    molecule = a["species"][0]
    assert molecule["molecular_coverage"] is None and molecule["missing"] == ["H2-bridge: molecular_reference"]
    assert a["sites"]["top-Ni"]["coverage_ranking"] is None
    assert a["sites"]["top-Ni"]["vacancy_fraction"] == 0.6
    assert a["sites"]["top-Ni"]["balance_residual"] is None
    row["molecular_reference"] = ref
    del obs["sites_per_molecular_reference"][ref]["bridge-Cu"]
    obs["sites"] = []
    a = analyze(inputs)
    assert a["species"][0]["molecular_coverage"] == 0.3
    assert a["species"][0]["missing"] == ["H2-bridge: sites_per_molecular_reference[interface-repeat][bridge-Cu]"]
    assert a["sites"]["top-Ni"]["balance_status"] == "balanced"
    assert a["sites"]["bridge-Cu"]["vacancy_fraction"] is None
    assert a["sites"]["bridge-Cu"]["activity"][0]["mean_field_vacancy_factor"] is None


@pytest.mark.parametrize("footprint", [None, {}, {"top-Ni": 0}])
def test_missing_footprint_and_confirmed_zero(inputs, footprint):
    network, obs = inputs
    s = indexed(network["species"], "species_id")["H2-top"]
    s["site_occupancy"] = footprint
    obs["species"][1].update(coverage=0, molecular_reference="interface-repeat")
    obs["sites"] = []
    a = analyze(inputs)
    top = a["sites"]["top-Ni"]
    assert a["species"][1]["molecular_coverage"] == 0
    assert a["sites"]["bridge-Cu"]["balance_status"] == "balanced"
    if footprint is None:
        assert top["unresolved_membership"] == ["H2-top"]
        assert top["vacancy_fraction"] is None and a["species"][1]["missing"]
    else:
        assert a["species"][1]["site_occupancy"] == {} and not a["species"][1]["missing"]
        assert top["vacancy_fraction"] == pytest.approx(0.85)


def test_zero_measurement_versus_absent(inputs):
    _, obs = inputs
    obs["species"][0]["coverage"] = 0
    obs["sites"] = []
    assert analyze(inputs)["sites"]["bridge-Cu"]["vacancy_fraction"] == 1
    del obs["species"][0]["coverage"]
    a = analyze(inputs)
    assert a["sites"]["bridge-Cu"]["vacancy_fraction"] is None
    assert a["species"][0]["missing"] == ["H2-bridge: coverage measurement"]


@pytest.mark.parametrize("bad", [0, -1, True, "1", float("nan")])
def test_invalid_reference_size(inputs, bad):
    inputs[1]["sites_per_molecular_reference"]["interface-repeat"]["top-Ni"] = bad
    with pytest.raises(ValueError, match="top-Ni"):
        analyze(inputs)


@pytest.mark.parametrize("issue", ["wrong-map", "wrong-domain", "overfilled", "unbalanced", "duplicate"])
def test_conflicts(inputs, issue):
    n, obs = inputs
    if issue == "wrong-map":
        obs["species"][0]["site_occupancy"] = {"top-Ni": 1}
    elif issue == "wrong-domain":
        indexed(n["species"], "species_id")["H2-bridge"]["surface_ids"] = ["facet-Ni"]
    elif issue == "overfilled":
        obs["species"][1]["coverage"] = 1
    elif issue == "unbalanced":
        obs["sites"][1]["vacancy_fraction"] = 0.6
    else:
        obs["species"].append(obs["species"][0])
    with pytest.raises(ValueError):
        analyze(inputs)


def test_amount_can_exceed_one_per_repeat(inputs):
    _, obs = inputs
    obs["sites_per_molecular_reference"]["interface-repeat"] = {"top-Ni": 4, "bridge-Cu": 2}
    obs["species"][0]["coverage"] = 1.5
    obs["sites"] = []
    a = analyze(inputs)
    assert a["species"][0]["molecular_coverage"] == 1.5
    assert a["sites"]["bridge-Cu"]["vacancy_fraction"] == 0.25


def test_per_inventory_vacancy_orders(inputs):
    network, _ = inputs
    network["reactions"][0]["direction"]["forward"]["sites_consumed"]["bridge-Cu"] = 2
    assert analyze(inputs)["sites"]["bridge-Cu"]["activity"][0]["mean_field_vacancy_factor"] == pytest.approx(0.49)


def test_activity_has_its_own_basis():
    obs = {"x": {"phase": "surface", "coverage": 1.5, "site_occupancy": {"a": 1, "b": 1}}}
    side = {"reactants": {"x": 1}, "sites_consumed": {}}
    with pytest.raises(ValueError, match="surface_activity"):
        activity_factors(side, {}, obs, {})
    obs["x"]["surface_activity"] = 0.25
    assert activity_factors(side, {}, obs, {})["adsorbate_factor"] == 0.25


def test_wrong_observation_version(tmp_path, inputs):
    p = tmp_path / "stale.json"
    write_json_exclusive(p, dict(inputs[1], network_version="0" * 64))
    with pytest.raises(ValueError, match="matching versioned network"):
        api.analyze_observations(BENCH / "network.json", p)


def test_schemas_reporting_and_legacy_bytes(inputs, tmp_path):
    molecular = read(SCHEMAS / "mkm_coverage.schema.json")
    full = read(SCHEMAS / "mkm_analysis.schema.json")
    for schema in (molecular, full):
        Draft202012Validator.check_schema(schema)
    data = read(BENCH / "validation.json")
    Draft202012Validator(molecular).validate(data)
    legacy = accepted()
    archived = BENCH.parent / "phase3_1/closed_cycle/analysis.json"
    digest = "76633f244d9a381f0fcfa458eb6f2ca6490337d9bfd78b295fedf82067524151"
    assert digest in read(archived.with_name("ticket_handoff.json"))["note"]
    output = tmp_path / "archived.json"
    api.main(["replay", str(archived), digest, str(output)])
    assert output.read_bytes() == archived.read_bytes()
    with pytest.raises(FileExistsError):
        api.main(["replay", str(archived), digest, str(output)])
    with pytest.raises(ValueError, match="reviewed SHA-256"):
        api.main(["replay", str(archived), "0" * 64, str(tmp_path / "invalid")])
    assert not (tmp_path / "invalid").exists()
    assert legacy["report_revision"] == "native-reference/1"
    assert json.dumps(accepted(), ensure_ascii=False) == json.dumps(legacy, ensure_ascii=False)
    # Reconstruct the expected new projection from the immutable historical values.
    expected = read(archived)
    expected["report_revision"] = "native-reference/1"
    reference = legacy["native_reference"]
    assert reference["reference_basis"] == "reference_site_pair"
    assert reference["sites_per_reference"] == {"bridge-Cu": 1, "top-Ni": 1}
    expected["native_reference"] = reference
    for reaction in expected["rates"]["reactions"]:
        assert reaction["flux_unit"] == "events per reference site per second"
        reaction["flux_unit"] = "events per reference site pair per second"
    assert expected == legacy
    # Exercise report projections separately from native scientific acceptance.
    report = dict(
        legacy,
        format="mkm-kinetic-analysis/2",
        coverage=data["species"],
        utilization=data["sites"],
        validation=dict(legacy["validation"], coverage_status="complete"),
    )
    registry = Registry().with_resource("mkm_coverage.schema.json", Resource.from_contents(molecular))
    Draft202012Validator(full, registry=registry).validate(report)
    assert "Species contributions by inventory" in markdown(report)
    assert coverage_analysis(*inputs, {})["species"] == data["species"]


@pytest.mark.parametrize("system", ["interface", "oxide", "Fe110"])
def test_single_inventory_overlay_reproduces_legacy(system):
    network, dataset, _ = cycle_model(system, with_network=True)
    point = read(BASE[-1])
    rates = api.rate_analysis(network, dataset, point)
    before = coverage_analysis(network, point, {}, rates)
    after = coverage_analysis(network, point, {})
    molecules = indexed(after["species"], "species_id")
    for row in before["species"]:
        site, sid = row["site_id"], row["species_id"]
        assert molecules[sid]["molecular_coverage"] == row["species_coverage"]
        inventory = after["sites"][site]
        assert inventory["contributions"][sid]["occupied_fraction"] == row["occupied_fraction"]
        assert inventory["vacancy_fraction"] == row["vacancy_fraction"]
        assert inventory["phase_id"] == row["phase_id"] and inventory["site_type"] == row["site_type"]


def test_reachability_and_coreactant_feasibility(inputs):
    network, _ = inputs
    network["reactions"][0]["direction"]["forward"]["reactants"]["H2-top"] = 1
    graph = pathway_graph(network, None, ["H2-g"], ["H2-bridge"])
    witness = graph["feed_to_product"][0]
    assert witness["paths"] and witness["enumeration_limited"] is False
    assert "H2-bridge" not in graph["feed_reachable_with_all_coreactants"]
    assert graph["reactions"][0]["net_flux"] is None and graph["pathway_percentages"] is None


def test_duplicate_reference_key_rejected(tmp_path):
    obs = (BENCH / "observations.json").read_bytes()
    p = tmp_path / "ambiguous.json"
    p.write_bytes(obs.replace(b'"top-Ni": 2', b'"top-Ni": 1, "top-Ni": 2'))
    with pytest.raises(ValueError, match="(?i)duplicate"):
        api.analyze_observations(BENCH / "network.json", p)


@pytest.mark.parametrize("sizes", [None, {"interface-repeat": None}])
def test_named_reference_without_inventory_sizes(tmp_path, inputs, sizes):
    observations = tmp_path / "observations.json"
    write_json_exclusive(observations, dict(inputs[1], sites_per_molecular_reference=sizes))
    a = api.analyze_observations(BENCH / "network.json", observations)
    Draft202012Validator(read(SCHEMAS / "mkm_coverage.schema.json")).validate(a)
    assert a["status"] == "partial"
    assert a["species"][0]["molecular_coverage"] == 0.30
    assert len(a["species"][0]["missing"]) == 2
    assert all(item["balance_status"] == "incomplete_attribution" for item in a["sites"].values())
