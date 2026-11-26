"""Independent finite-population expectations for the two B.2.1 synthetic systems."""

import copy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.artifact_io import load_json_object as read, write_json_exclusive
from scripts.baseline_mkm.analysis import analyze_observations, coverage_status
from scripts.baseline_mkm.kinetic_analysis import coverage_analysis
from scripts.kinetic_data.stoichiometric_sources import build_matrices, project_progress
from scripts.rate_output_v2 import validate_rate_output_v2
from scripts.reaction_network.__main__ import read_source
from scripts.reaction_network.builder import build_network

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/multiphase"
ARCH = REPORT / "phase3_1_1"
OXIDE = ROOT / "tests/fixtures/multiphase/synthetic_oxide_site_network.json"
WORK = REPORT / "stage_b2_1"


def inputs(system):
    if system == "interface":
        network = read(ARCH / "network.json")
        observations = read(ARCH / "observations.json")
        observations["inventory_reference"] = "interface-repeat"
    else:
        sources = []
        network = build_network(read_source(OXIDE, "definition", sources), sources=sources)
        observations = read(WORK / "oxide_observations.json")
    assert network["network_version"] == observations["network_version"]
    return network, observations


def calculate(network, observations):
    return coverage_analysis(network, observations, {})


def molecules(result):
    return {s["species_id"]: s["molecule_count"]["value"] for s in result["species"]}


def totals(result, site):
    counts = result["sites"][site]["site_counts"]
    return tuple(counts[k] for k in ("capacity", "occupied", "vacant"))


@pytest.mark.parametrize("system", ["oxide", "interface"])
def test_bound_public_entry_and_hand_balances(system, tmp_path):
    network, obs = inputs(system)
    nf, of = tmp_path / "network.json", tmp_path / "obs.json"
    write_json_exclusive(nf, network)
    write_json_exclusive(of, obs)
    result = analyze_observations(nf, of)
    Draft202012Validator(read(ROOT / "configs/kinetics/mkm_coverage.schema.json")).validate(result)
    assert result == read(WORK / f"{system}_validation.json")
    assert result["status"] == "complete"
    assert "rates" not in result
    if system == "oxide":
        assert molecules(result) == {"co2-bound": 2}
        hand = {"acid-A": (4, 2, 2), "oxygen-B": (3, 2, 1)}
        for site, kind in [("acid-A", "lewis-acid"), ("oxygen-B", "basic-oxygen")]:
            row = result["sites"][site]
            assert (row["phase_id"], row["surface_id"], row["site_type"]) == ("oxide-alpha", "oxide-012", kind)
            assert row["contributions"]["co2-bound"]["occupied_sites"] == 2
        surface = network["catalog"]["surfaces"][0]
        assert surface["lattice_vectors_angstrom"] == [[6.1, 0, 0], [1.7, 5.2, 0], [0, 0, 21]]
        assert network["validation_report"]["mkm_status"] == "blocked"
    else:
        assert molecules(result) == {"H2-bridge": 0.30, "H2-top": 0.50}
        hand = {"top-Ni": (2, 0.80, 1.20), "bridge-Cu": (1, 0.30, 0.70)}
        shared = result["sites"]["top-Ni"]
        assert shared["competitors"] == ["H2-bridge", "H2-top"]
        assert shared["contributions"]["H2-top"]["occupied_sites"] == 0.50
        assert shared["contributions"]["H2-bridge"]["occupied_sites"] == 0.30
        assert result["sites"]["bridge-Cu"]["contributions"]["H2-bridge"]["occupied_sites"] == 0.30
    for site, (capacity, occupied, vacant) in hand.items():
        row = result["sites"][site]
        assert totals(result, site) == pytest.approx((capacity, occupied, vacant))
        assert row["occupied_fraction"] == pytest.approx(occupied / capacity)
        assert row["vacancy_fraction"] == pytest.approx(vacant / capacity)
        assert row["site_counts"]["reference"] == obs["inventory_reference"]
        assert row["site_counts"]["missing"] == []


def test_structure_only_has_no_measured_counts_or_capacity():
    n, o = inputs("oxide")
    out = calculate(n, dict(o, species=[], sites=[]))
    assert molecules(out) == {"co2-bound": None}
    assert coverage_status(out) == "partial"
    for row in out["sites"].values():
        assert row["occupied_fraction"] is row["vacancy_fraction"] is None
        assert all(row["site_counts"][k] is None for k in ("capacity", "occupied", "vacant"))
    assert "rates" not in out


def test_missing_capacity_preserves_molecular_and_occupied_site_counts():
    n, o = inputs("oxide")
    o["sites"].pop()
    out = calculate(n, o)
    assert molecules(out) == {"co2-bound": 2}
    assert totals(out, "acid-A") == (4, 2, 2)
    assert totals(out, "oxygen-B") == (None, 2, None)
    assert out["sites"]["oxygen-B"]["occupied_fraction"] is None
    assert out["sites"]["oxygen-B"]["site_counts"]["missing"] == ["oxygen-B: capacity per oxide-counting-cell"]


def test_unknown_reference_independent_fraction_and_explicit_zero():
    n, o = inputs("oxide")
    o["species"][0]["molecular_reference"] = None
    o["sites"][0]["vacancy_fraction"] = 0.5
    out = calculate(n, o)
    assert molecules(out) == {"co2-bound": None}
    assert totals(out, "acid-A") == (4, 2, 2)
    assert totals(out, "oxygen-B") == (3, None, None)
    assert out["sites"]["acid-A"]["balance_status"] == "incomplete_attribution"
    o["species"][0].update(coverage=0, molecular_reference=o["inventory_reference"])
    del o["sites"][0]["vacancy_fraction"]
    out = calculate(n, o)
    assert molecules(out) == {"co2-bound": 0}
    assert totals(out, "acid-A") == (4, 0, 4)
    assert totals(out, "oxygen-B") == (3, 0, 3)


def test_observed_footprint_dispute_preserves_agreed_inventory_and_molecules():
    n, o = inputs("oxide")
    o["species"][0]["site_occupancy"] = {"acid-A": 1}
    out = calculate(n, o)
    assert coverage_status(out) == "partial"
    assert out["species"][0]["site_occupancy"] is None
    assert molecules(out) == {"co2-bound": 2}
    assert totals(out, "acid-A") == (4, 2, 2)
    assert totals(out, "oxygen-B") == (3, None, None)
    assert out["sites"]["oxygen-B"]["unresolved_membership"] == ["co2-bound"]
    assert "oxygen-B" in out["species"][0]["missing"][0]


def test_unknown_footprint_affects_only_possible_surface():
    n, o = inputs("interface")
    s = next(x for x in n["species"] if x["species_id"] == "H2-top")
    s["site_occupancy"] = None
    o["species"][1].update(coverage=0.5, molecular_reference=o["inventory_reference"])
    o["sites"] = []
    out = calculate(n, o)
    assert molecules(out)["H2-top"] == 0.5
    assert totals(out, "top-Ni") == (2, None, None)
    assert totals(out, "bridge-Cu") == (1, 0.3, 0.7)
    assert out["sites"]["top-Ni"]["unresolved_membership"] == ["H2-top"]


@pytest.mark.parametrize("conflict", ["overlap", "capacity", "duplicate"])
def test_physical_capacity_conflict_is_local(conflict):
    n, o = inputs("oxide")
    n["catalog"]["sites"].append(dict(n["catalog"]["sites"][0], site_id="spectator"))
    o["sites"].append({"site_id": "spectator", "physical_site_ids": ["third-pool"]})
    if conflict == "overlap":
        o["sites"][1]["physical_site_ids"][0] = "acid-1"
    elif conflict == "duplicate":
        o["sites"][0]["physical_site_ids"][0] = "acid-2"
    else:
        o["sites_per_molecular_reference"] = {o["inventory_reference"]: {"acid-A": 7}}
    out = calculate(n, o)
    affected = ["acid-A", "oxygen-B"] if conflict == "overlap" else ["acid-A"]
    for site in affected:
        row = out["sites"][site]
        assert totals(out, site) == (None, None, None)
        assert row["occupied_fraction"] is row["vacancy_fraction"] is None
        assert row["site_counts"]["missing"]
    assert totals(out, "spectator") == (1, 0, 1)
    if conflict != "overlap":
        assert totals(out, "oxygen-B") == (3, 2, 1)
    assert molecules(out) == {"co2-bound": 2}
    assert coverage_status(out) == "partial"


def test_named_reference_converts_only_with_consistent_inventory_sizes():
    n, o = inputs("oxide")
    o["species"][0].update(molecular_reference="double-cell", coverage=4)
    o["sites_per_molecular_reference"] = {"double-cell": {"acid-A": 8}}
    good = calculate(n, o)
    assert molecules(good)["co2-bound"] == 2
    assert totals(good, "oxygen-B") == (3, 2, 1)
    assert good["sites"]["oxygen-B"]["occupied_fraction"] == pytest.approx(2 / 3)
    assert not good["species"][0]["missing"]
    o["sites_per_molecular_reference"]["double-cell"]["oxygen-B"] = 9
    ambiguous = calculate(n, o)
    assert molecules(ambiguous)["co2-bound"] is None
    assert ambiguous["species"][0]["molecular_coverage"] == 4
    assert "consistent capacity ratio" in ambiguous["species"][0]["missing"][0]
    assert totals(ambiguous, "oxygen-B") == (3, None, None)


def test_known_zero_footprint_keeps_nonzero_molecular_count():
    n, o = inputs("oxide")
    row = next(s for s in n["species"] if s["species_id"] == "co2-bound")
    row["site_occupancy"] = {"acid-A": 0, "oxygen-B": 0}
    out = calculate(n, o)
    assert molecules(out)["co2-bound"] == 2
    assert totals(out, "acid-A") == (4, 0, 4) and totals(out, "oxygen-B") == (3, 0, 3)


@pytest.mark.parametrize("bad", [None, False, "", 3])
def test_finite_members_need_an_explicit_count_reference(bad):
    n, o = inputs("oxide")
    o["inventory_reference"] = bad
    with pytest.raises(ValueError, match="inventory_reference"):
        calculate(n, o)


def test_unknown_member_list_does_not_require_count_mode():
    n, o = inputs("interface")
    del o["inventory_reference"]
    o["sites"][0]["physical_site_ids"] = None
    out = calculate(n, o)
    assert "site_counts" not in out["sites"]["top-Ni"]
    assert out["sites"]["top-Ni"]["vacancy_fraction"] == 0.6


def relabel(data, names):
    if isinstance(data, dict):
        return {names.get(k, k): relabel(v, names) for k, v in data.items()}
    if isinstance(data, list):
        return [relabel(v, names) for v in data]
    return names.get(data, data) if isinstance(data, str) else data


def physical_results(out):
    sites = {
        s: {k: v for k, v in row.items() if k not in {"coverage_ranking", "competitors", "dominant_adsorbates"}}
        for s, row in out["sites"].items()
    }
    return {s["species_id"]: s for s in out["species"]}, sites


@pytest.mark.parametrize("system", ["interface", "oxide"])
def test_rebuilt_network_and_inverse_renaming(system):
    n, o = inputs(system)
    src = (ROOT / "tests/fixtures/multiphase/valid.json") if system == "interface" else OXIDE
    raw = read(src)
    # Two phases may use the same site type name but still own different physical inventories.
    if system == "interface":
        for site in raw["sites"]:
            site["site_type"] = "shared-label"
        n = build_network(raw)
    keys = [
        (group, field)
        for group, field in (
            ("phases", "phase_id"),
            ("surfaces", "surface_id"),
            ("sites", "site_id"),
            ("species", "species_id"),
        )
    ]
    names = {row[field]: f"{group}-{16 - i}" for group, field in keys for i, row in enumerate(raw[group])}
    new = relabel(raw, names)
    for group, _ in keys:
        new[group].reverse()
    changed = build_network(new)
    trial = relabel(o, names)
    trial["species"].reverse()
    trial["sites"].reverse()
    trial["network_version"] = changed["network_version"]
    before = calculate(n, o)
    after = relabel(calculate(changed, trial), {v: k for k, v in names.items()})
    assert physical_results(after) == physical_results(before)
    if system == "interface":
        assert before["sites"]["top-Ni"]["site_type"] == before["sites"]["bridge-Cu"]["site_type"]
        assert totals(before, "top-Ni") != totals(before, "bridge-Cu")


@pytest.mark.parametrize("system,delta", [("interface", 0.1), ("oxide", 1)])
def test_occupancy_change_matches_b1_stoichiometric_projection(system, delta):
    n, o = inputs(system)
    before = calculate(n, o)
    trial = copy.deepcopy(o)
    for row in trial["sites"]:
        row.pop("vacancy_fraction", None)
    trial["species"][0]["coverage"] += delta
    after = calculate(n, trial)
    rx = n["reactions"][0]
    rid = rx["definition"]["reaction_id"]
    matrix = build_matrices([dict(reaction_id=rid, **rx["direction"]["forward"])])
    species, vacancy = project_progress(matrix, {rid: delta})
    for sid, amount in molecules(before).items():
        assert molecules(after)[sid] - amount == pytest.approx(species.get(sid, 0))
    for site in before["sites"]:
        assert totals(after, site)[2] - totals(before, site)[2] == pytest.approx(vacancy[site])


def test_native_denominators_and_archived_rate_footprints():
    for case, basis in [("catkinas-phase3_0", "reference_site_pair"), ("zacros-dent", "simulation_cell")]:
        output = read(REPORT / "stage_b1_4/replay" / f"{case}.json")
        network = read(ROOT / output["provenance"]["network"]["path"])
        validate_rate_output_v2(output, network=network)
        native = output["native_normalization"]
        assert native["basis_kind"] == basis and native["denominator_value"] == 1
        assert "inventory_reference" not in native
        if basis == "reference_site_pair":
            assert read(REPORT / "phase3_1/benchmark_normalization.json")["sites_per_reference"] == {
                "top-Ni": 1,
                "bridge-Cu": 1,
            }
        else:
            species = next(row for row in network["species"] if row["species_id"] == "H2-bridge")
            assert species["site_occupancy"] == {"top-Ni": 1, "bridge-Cu": 1}
