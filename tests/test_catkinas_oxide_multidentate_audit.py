"""Offline checks on one adsorbate shared by two independent inventories."""
from fractions import Fraction
from pathlib import Path
import re

import pytest

from scripts.artifact_io import load_json_object as read, sha256_file, write_json_exclusive
from scripts.baseline_mkm.analysis import analyze_observations
from scripts.baseline_mkm.native import native_names
from scripts.baseline_mkm.network_mapping import map_network
from scripts.kinetic_data.stoichiometric_sources import build_matrices, conservation_residuals, project_progress
from scripts.reaction_network.__main__ import read_source
from scripts.reaction_network.builder import build_network

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/multiphase"
OUT = BASE / "stage_b2_3_1_1"
FIXTURE = ROOT / "tests/fixtures/multiphase/synthetic_oxide_site_network.json"


@pytest.fixture
def oxide():
    sources = []
    return build_network(read_source(FIXTURE, "definition", sources), sources=sources)


def test_counting_cell_matches_independent_fractions(oxide, tmp_path):
    ref = read(OUT / "independent_reference.json")
    obs = read(BASE / "stage_b2_1/oxide_observations.json")
    network_path = tmp_path / "network.json"
    write_json_exclusive(network_path, oxide)
    result = analyze_observations(network_path, BASE / "stage_b2_1/oxide_observations.json")
    assert ref["network_version"] == obs["network_version"] == oxide["network_version"]
    assert result == read(BASE / "stage_b2_1/oxide_validation.json")
    assert len(result["species"]) == 1
    species, = result["species"]
    assert species["molecule_count"] == {"reference": ref["inventory_reference"], "value": 2}
    assert ref["molecule_count"] == 2 and species["species_id"] == ref["species_id"] == "co2-bound"
    assert species["site_occupancy"] == {"acid-A": 1, "oxygen-B": 1}
    for site, capacity in (("acid-A", 4), ("oxygen-B", 3)):
        row = ref["inventory"][site]
        counted = result["sites"][site]["site_counts"]
        assert (row["capacity"], row["occupied"], row["vacant"]) == (capacity, 2, capacity - 2)
        assert all(counted[k] == row[k] for k in ("capacity", "occupied", "vacant"))
        assert Fraction(row["occupied_fraction"]) == Fraction(2, capacity)
        assert Fraction(row["vacancy_fraction"]) == Fraction(capacity - 2, capacity)
    assert Fraction(ref["vacancy_fraction_product_if_mean_field_factorization"]) == Fraction(1, 2) * Fraction(1, 3)
    assert ref["actual_available_adjacent_pairs"] is None


@pytest.mark.parametrize("extent", [-2, -1, 0, 1])
def test_signed_event_counts_close_each_inventory(oxide, extent):
    # Counts per event in a finite sample. No rate or kinetic constant is supplied.
    r = oxide["reactions"][0]["definition"]
    m = build_matrices([r])
    species, vacant = project_progress(m, {r["reaction_id"]: extent})
    assert species == {"co2": -extent, "co2-bound": extent}
    assert vacant == {"acid-A": -extent, "oxygen-B": -extent}
    ref = read(OUT / "independent_reference.json")["per_net_adsorption_event"]
    assert ref["gas_molecules"] == {"co2": -1} and ref["bound_molecules"] == {"co2-bound": 1}
    assert ref["vacancies"] == {"acid-A": -1, "oxygen-B": -1}
    assert ref["occupied_sites"] == {"acid-A": 1, "oxygen-B": 1}
    for site, capacity in (("acid-A", 4), ("oxygen-B", 3)):
        occupied = 2 + species["co2-bound"]
        empty = capacity - 2 + vacant[site]
        assert min(occupied, empty) >= 0 and occupied + empty == capacity
        assert Fraction(ref["occupied_fraction_change"][site]) == Fraction(1, capacity)
        assert Fraction(ref["vacant_fraction_change"][site]) == -Fraction(1, capacity)
    residual = conservation_residuals(m, oxide["species"])[r["reaction_id"]]
    assert residual == ref["residual"] == {"elements": {"C": 0, "O": 0}, "charge": 0,
                                         "inventories": {"acid-A": 0, "oxygen-B": 0}}


def test_unmeasured_rates_are_distinct_from_equilibrium_targets(oxide):
    r = oxide["reactions"][0]["definition"]
    ref = read(OUT / "independent_reference.json")
    known = ref["required_equilibrium_residual"]
    assert known["forward_minus_reverse"] == 0
    m = build_matrices([r])
    assert project_progress(m, {r["reaction_id"]: 0}) == (known["species"], known["vacancies"])
    observed = ref["initial_source_rates"]
    assert project_progress(m, {r["reaction_id"]: None}) == (observed["species"], observed["vacancies"])
    assert set(ref["initial_flux"].values()) == {None}
    assert all(ref[k] is None for k in ("temperature_K", "CO2_partial_pressure_bar", "forward_coefficient",
                                         "reverse_coefficient", "native_rate_denominator", "computed_steady_state",
                                         "detailed_balance_numeric_residual", "native_input_comparison"))
    assert r["reversible"] is None and not oxide["parameter_sets"]


def test_documented_bridge_template_round_trips_structural_terms(oxide):
    draft = OUT / "oxide_CO2.m.in"
    lines = draft.read_text(encoding="utf8").splitlines()
    equation, = [line for line in lines if line.startswith("(1):")]
    left, right = equation.removeprefix("(1): ").split(" [")[0].split(" <-> ")
    assert left.split(" + ") == ["CO2", "#1", "#2"]
    assert right == "CO2#1#2"
    _, *site_numbers = right.split("#")
    mapping = {"1": "acid-A", "2": "oxygen-B"}
    footprint = {mapping[number]: 1 for number in site_numbers}
    bound, = [s for s in oxide["species"] if s["phase"] == "surface"]
    assert footprint == bound["site_occupancy"] == oxide["reactions"][0]["definition"]["sites_consumed"]
    assignments = dict(line[:-1].split(" = ") for line in lines if line.endswith(";"))
    assert assignments["Q1x2_CO2_INIT"] == "<bridge_population_in_documented_native_units>"
    assert float(assignments["Q1_v_INIT"]) == 1 / 2 and float(assignments["Q2_v_INIT"]) == 1 / 3
    assert {key for key in assignments if key.startswith("Q")} == {"Q1x2_CO2_INIT", "Q1_v_INIT", "Q2_v_INIT"}
    assert set(re.findall(r"<(\w+)>", draft.read_text(encoding="utf8"))) == {
        "effective_Ea_eV", "effective_G0_eV", "temperature_K", "CO2_partial_pressure_bar",
        "bridge_population_in_documented_native_units"}
    manifest = read(OUT / "evidence.json")["template_manifest"]
    assert manifest["sha256"] == sha256_file(draft) and manifest["runnable"] is False


def test_single_native_symbol_and_two_independent_balances_blocked(oxide):
    with pytest.raises(ValueError, match="multidentate"):
        native_names(oxide["species"], {"co2": "CO2", "co2-bound": "CO2"}, {"acid-A": 1, "oxygen-B": 2})
    files, result = map_network(oxide)
    assert files == {} and result["native_input_hashes"] == {}
    assert result["native_execution_eligibility"] == "blocked"
    assert any(i["status"] == "unsupported" and i["id"] == "co2-bound" for i in result["issues"])
    readiness = read(OUT / "execution_readiness.json")
    assert not readiness["execution_authorized"] and readiness["native_attempts"] == 0
    assert readiness["native_input_sha256"] is readiness["execution_plan"] is readiness["approval_request"] is None
    assert readiness["native_parser_acceptance"] == readiness["native_numerical_convergence"] == "not_run"
    assert readiness["independent_numerical_agreement"] == "not_evaluable"
