"""Hand-calculated native-basis projections, conservation and uncertainty checks."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.kinetic_data import stoichiometric_sources as sources
from scripts.rate_output_v2 import generate_source_terms


def reaction(rid, left, right, consumed=None, released=None):
    return dict(reaction_id=rid, reactants=left, products=right, sites_consumed=consumed or {},
                sites_released=released or {})


BASIS = {"extent_unit": "event", "time_unit": "s", "denominator_value": 1, "denominator_unit": "site pair",
         "reference_id": "alpha-beta", "definition": "One alpha and one beta site"}


@pytest.mark.parametrize(("left", "right", "net", "expected"), [
    ({"A": 1}, {"B": 1}, 4, {"A": -4, "B": 4}),
    ({"A": 1}, {"B": 2}, 4, {"A": -4, "B": 8}),
    ({"A": 2.0}, {"B": 1}, -3, {"A": 6, "B": -3}),
    ({"A": 1}, {"B": 1}, 0, {"A": 0, "B": 0}),
])
def test_signed_source_counts(left, right, net, expected):
    matrices = sources.build_matrices([reaction("r", left, right)])
    assert sources.project_progress(matrices, {"r": net}) == (expected, {})


@pytest.mark.parametrize("bad", [0, -1, 0.5, True, "2", float("nan")])
def test_network_coefficients_follow_current_integer_contract(bad):
    with pytest.raises(ValueError):
        sources.build_matrices([reaction("r", {"A": bad}, {"B": 1})])


def test_parallel_and_serial_paths_and_sparse_unknowns():
    rows = [reaction("alpha", {"A": 1, "X": 2}, {"B": 2, "X": 2}, {"q": 1, "v": 1}, {"v": 1}),
            reaction("beta", {"A": 1}, {"B": 2}, {"q": 1}),
            reaction("gamma", {"B": 1}, {"C": 1}, released={"p": 1})]
    matrices = sources.build_matrices(rows)
    nets = {"beta": 2, "gamma": -1, "alpha": 3}
    assert sources.project_progress(matrices, nets) == ({"A": -5, "B": 11, "C": -1, "X": 0}, {"p": -1, "q": -5, "v": 0})
    nets["alpha"] = None
    expected = ({"A": None, "B": None, "C": -1, "X": 0}, {"p": -1, "q": None, "v": 0})
    assert sources.project_progress(matrices, nets) == expected
    assert matrices == sources.build_matrices(reversed(rows))
    assert generate_source_terms is sources.generate_source_terms
    report = generate_source_terms(dict(row, net=nets[row["reaction_id"]]) for row in rows)
    assert list(expected[0]) == [s["species_id"] for s in report["species"]]
    assert list(expected[1]) == [s["site_id"] for s in report["site_inventories"]]
    assert report == generate_source_terms(dict(row, net=nets[row["reaction_id"]]) for row in reversed(rows))


def test_duplicate_and_missing_reaction_id_and_non_numeric_net():
    r = reaction("d", {"A": 1}, {"B": 1})
    with pytest.raises(ValueError, match="Duplicate reaction_id"):
        sources.build_matrices([r, r])
    m = sources.build_matrices([r])
    for invalid in ({"wrong": 1}, {"d": "not_applicable"}, {"d": float("inf")}, {"d": False}):
        with pytest.raises(ValueError):
            sources.project_progress(m, invalid)


def interfacial():
    sites = {"phase-alpha/facet/top": 2, "phase-beta/facet/top": 1, "interface/edge": 1}
    definition = reaction("bind", {"M-g": 1}, {"M-interface": 1}, consumed=sites.copy())
    catalog = [dict(species_id="M-g", composition={"C": 1, "O": 1}, charge=-1, site_occupancy={}),
               dict(species_id="M-interface", composition={"C": 1, "O": 1}, charge=-1, site_occupancy=sites.copy())]
    return definition, catalog, sites


def test_cross_phase_multisite_same_type_and_interface_counted_independently():
    definition, catalog, sites = interfacial()
    m = sources.build_matrices([definition])
    species, vacancy = sources.project_progress(m, {"bind": 3})
    assert species == {"M-g": -3, "M-interface": 3}
    assert vacancy == {"phase-alpha/facet/top": -6, "phase-beta/facet/top": -3, "interface/edge": -3}
    assert sources.conservation_residuals(m, catalog)["bind"] == {
        "elements": {"C": 0, "O": 0}, "charge": 0, "inventories": dict.fromkeys(sites, 0)}


@pytest.mark.parametrize(("field", "new", "group", "key", "expected"), [
    ("composition", {"C": 1, "O": 2}, "elements", "O", 1),
    ("charge", 0, "charge", None, 1),
    ("site_occupancy", {"phase-alpha/facet/top": 1, "phase-beta/facet/top": 1, "interface/edge": 1},
     "inventories", "phase-alpha/facet/top", -1),
    ("site_occupancy", {"unannounced": 1}, "inventories", "unannounced", 1),
])
def test_element_charge_and_inventory_fail_independently(field, new, group, key, expected):
    r, catalog, sites = interfacial()
    catalog[1][field] = new
    residual = sources.conservation_residuals(sources.build_matrices([r]), catalog)["bind"]
    assert (residual[group][key] if key else residual[group]) == expected
    if group != "charge":
        assert residual["charge"] == 0
    if group != "elements":
        assert residual["elements"] == {"C": 0, "O": 0}
    if group != "inventories":
        assert residual["inventories"] == dict.fromkeys(sites, 0)


@pytest.mark.parametrize("field", ["composition", "charge", "site_occupancy"])
def test_missing_conservation_evidence_names_species_and_field(field):
    r, catalog, _ = interfacial()
    del catalog[1][field]
    with pytest.raises(ValueError, match=f"M-interface.{field}"):
        sources.conservation_residuals(sources.build_matrices([r]), catalog)


def test_source_residuals_identify_numeric_and_missing_data_disagreement():
    r, _, _ = interfacial()
    projected = generate_source_terms([dict(r, net=2)])
    reported = deepcopy(projected)
    reported["species"][0]["net_production_rate"] += 1
    reported["site_inventories"][0]["net_vacancy_rate"] = None
    diff = sources.source_residuals(projected, reported)
    assert diff["species"]["M-g"] == {"consistent": False, "residual": 1}
    site = reported["site_inventories"][0]["site_id"]
    assert diff["site_inventories"][site] == {"consistent": False, "residual": None}
    assert sources.source_residuals(reported, reported)["site_inventories"][site] == {"consistent": True, "residual": None}


def chain():
    return sources.build_matrices([reaction("r1", {"A": 1}, {"B": 2}, {"s": 1}), reaction("r2", {"B": 1}, {"C": 1})])


def test_correlated_projection_and_label_permutation():
    m = chain()
    # B = 2*r1 - r2; Var(B) = 4*4 + 9 - 4*1 = 21. Vacancy and A both equal -r1.
    report = sources.source_covariance(m, BASIS, reaction_ids=["r1", "r2"], covariance=[[4, 1], [1, 9]])
    assert [(x["id"], x["numerator_unit"]) for x in report["axes"]] == [
        ("A", "molecule"), ("B", "molecule"), ("C", "molecule"), ("s", "vacancy")]
    assert report["native_normalization"] == BASIS
    assert report["covariance"] == [[4, -7, -1, 4], [-7, 21, -7, -7], [-1, -7, 9, -1], [4, -7, -1, 4]]
    swapped = sources.source_covariance(m, BASIS, reaction_ids=["r2", "r1"], covariance=[[9, 1], [1, 4]])
    assert swapped == report


def test_singular_covariance_and_known_zero():
    m = chain()
    singular = sources.source_covariance(m, BASIS, reaction_ids=["r1", "r2"], covariance=[[1, 2], [2, 4]])
    assert singular["covariance"][1] == [0, 0, 0, 0]
    result = sources.source_covariance(m, BASIS, reaction_ids=["r1", "r2"], covariance=[[0, 0], [0, 3]])
    assert result["covariance"][0] == [0, 0, 0, 0]


def test_global_psd_and_tiny_negative_source_variance():
    m = sources.build_matrices([reaction(r, {"a": 1}, {"b": 1}) for r in ("x", "y", "z")])
    # All three 2-by-2 minors pass. The summed-rate variance is negative.
    invalid = [[1, -0.9, -0.9], [-0.9, 1, -0.9], [-0.9, -0.9, 1]]
    with pytest.raises(ValueError, match="positive semidefinite"):
        sources.source_covariance(m, BASIS, reaction_ids=m.reaction_ids, covariance=invalid)
    m = sources.build_matrices([reaction("x", {"a": 1}, {"b": 1}), reaction("y", {"b": 1}, {"a": 1})])
    with pytest.raises(ValueError, match="variance|semidefinite"):
        sources.source_covariance(m, BASIS, reaction_ids=["x", "y"], covariance=[[1, 1 + 4e-16], [1 + 4e-16, 1]])


def test_unavailable_and_explicit_independent_variances():
    m = chain()
    assert sources.source_covariance(m, BASIS)["covariance"] is None
    diagonal = sources.source_covariance(m, BASIS, independent_variances={"r1": 4, "r2": 9})["covariance"]
    assert diagonal[1] == [-8, 25, -9, -8]
    partial = sources.source_covariance(m, BASIS, independent_variances={"r1": 4, "r2": None})["covariance"]
    assert partial == [[4, -8, 0, 4], [-8, None, None, -8], [0, None, None, 0], [4, -8, 0, 4]]
    mol = sources.source_covariance(m, dict(BASIS, extent_unit="mmol"))
    assert all(row["numerator_unit"] == "mmol" for row in mol["axes"])


@pytest.mark.parametrize("values", [
    [[1, 2], [2, 1]], [[1, 0.1], [0.2, 1]], [[1, 1], [1, 0]], [[-1e-100, 0], [0, 1]],
    [[float("nan"), 0], [0, 1]], [[True, 0], [0, 1]], [[1, None], [None, 1]], [[1, 2]], [[1e-80, 1e-20], [1e-20, 1]],
])
def test_invalid_full_covariance(values):
    with pytest.raises(ValueError):
        sources.source_covariance(chain(), BASIS, covariance=values, reaction_ids=["r1", "r2"])


@pytest.mark.parametrize("options", [
    {"covariance": [[1, 0], [0, 1]]}, {"reaction_ids": ["r1", "r1"], "covariance": [[1, 0], [0, 1]]},
    {"independent_variances": {"r1": 1}}, {"independent_variances": {"r1": 1, "r2": -1}},
    {"independent_variances": {"r1": 1, "r2": 1}, "covariance": [[1, 1], [1, 1]]},
])
def test_uncertainty_requires_unambiguous_evidence(options):
    with pytest.raises(ValueError):
        sources.source_covariance(chain(), BASIS, **options)


def replay_archived_cycle():
    from hashlib import sha256

    root = Path(__file__).resolve().parents[1]
    paths = {"result": "reports/multiphase/phase3_0/result.json",
             "network": "reports/multiphase/phase3_0/closed_cycle_network.json",
             "analysis": "reports/multiphase/phase3_1/closed_cycle/analysis.json"}
    raw = {k: (root / p).read_bytes() for k, p in paths.items()}
    hashes = {k: sha256(data).hexdigest() for k, data in raw.items()}
    result, network, analysis = (json.loads(raw[k]) for k in ("result", "network", "analysis"))
    for key in ("result", "network"):
        assert hashes[key] == analysis["source_hashes"][key]
    assert network["network_version"] == analysis["normalization"]["network_version"]
    assert result["validation"]["status"] == analysis["validation"]["status"] == "passed"
    matrices = sources.build_matrices(r["definition"] for r in network["reactions"])
    net = {r["reaction_id"]: r["net_flux"] for r in result["reactions"]}
    species, vacancy = sources.project_progress(matrices, net)
    balances = sources.conservation_residuals(matrices, network["species"])
    gas_residual = {sid: species[sid] - observed for sid, observed in result["gas_net_production"].items()}
    extent = species["H2-g"] / result["total_reaction"]["H2-g"]
    sites = analysis["normalization"]["sites_per_reference"]
    assert set(sites) == set(vacancy)
    assert result["total_reaction"] == {"H2-g": -1, "HNO-g": 2, "NO-g": -2}
    assert all(species[sid] == extent * n for sid, n in result["total_reaction"].items())
    return {
        "temperature_K": analysis["temperature_K"], "source_artifacts": {k: {"path": paths[k], "sha256": h} for k, h in hashes.items()},
        "network_version": network["network_version"], "reference_basis": analysis["normalization"]["reference_basis"],
        "sites_per_reference": sites, "net_progress_per_pair_s": net, "species_sources_per_pair_s": species,
        "vacancy_sources_per_pair_s": vacancy, "reported_gas_source_residual_per_pair_s": gas_residual,
        "conservation_residuals_per_event": balances, "overall_turnover_per_pair_s": extent,
        "mean_turnover_per_individual_site_s": extent / sum(sites.values()), "net_progress_covariance": None,
        "archived_turnover": analysis["tof"]["overall"],
    }


def test_archived_400_k_sources_and_independent_site_conservation():
    replay = replay_archived_cycle()
    assert (replay["temperature_K"], replay["reference_basis"]) == (400, "reference_site_pair")
    assert replay["overall_turnover_per_pair_s"] == replay["archived_turnover"]["per_site_pair_s"] == 81.5127701616477
    assert replay["species_sources_per_pair_s"]["HNO-g"] == 163.0255403232954
    assert replay["mean_turnover_per_individual_site_s"] == replay["archived_turnover"]["per_site_s"] == 40.75638508082385
    assert replay["vacancy_sources_per_pair_s"] == {"top-Ni": 0, "bridge-Cu": 0}
    assert replay["sites_per_reference"] == {"top-Ni": 1, "bridge-Cu": 1}
    assert set(replay["reported_gas_source_residual_per_pair_s"].values()) == {0}
    assert set(replay["conservation_residuals_per_event"]) == {"ads", "transfer", "hydrogenate", "desorb"}
    for row in replay["conservation_residuals_per_event"].values():
        assert row == {"elements": {"H": 0, "N": 0, "O": 0}, "charge": 0, "inventories": {"bridge-Cu": 0, "top-Ni": 0}}
    receipt = Path(__file__).resolve().parents[1] / "reports/multiphase/stage_b1_3/ni_cu_replay.json"
    assert json.loads(receipt.read_bytes()) == replay
