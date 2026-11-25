from copy import deepcopy

import pytest

from scripts.artifact_io import load_json_object as read, sha256_file, write_json_exclusive as save
from scripts.baseline_mkm import analysis as api
from scripts.baseline_mkm import single_point as flow
from scripts.baseline_mkm.kinetic_analysis import coverage_analysis, indexed, product_analysis, rate_analysis
from scripts.baseline_mkm.pathway_analysis import pathway_graph
from scripts.reaction_network.builder import directions
from test_catkinas_closed_cycle import cycle_model
from test_mkm_single_point import PHASE, OUT, approved, replay, runtime, start  # noqa: F401

BASE = (
    PHASE / "closed_cycle_network.json",
    OUT / "cycle_dataset.json",
    PHASE / "workflow_configuration.json",
    PHASE / "result.json",
)
OPTIONS = PHASE.parent / "phase3_1/benchmark_normalization.json"


def accepted(opt=OPTIONS):
    return api.analyze(*BASE, read(PHASE / "benchmark_manifest.json"), opt)


def test_closed_cycle_evidence():
    a = accepted()
    assert a["temperature_K"] == 400 and a["partial_pressures_bar"] == {"H2-g": 1, "NO-g": 0.5, "HNO-g": 0.1}
    c = indexed(a["coverage"], "species_id")
    for k, v in {"H2-top": 0.30710124, "H2-bridge": 0.69667948, "HNO-top": 0.40121221}.items():
        assert c[k]["species_coverage"] == pytest.approx(v)
        assert c[k]["fraction_of_all_sites"] == pytest.approx(v / 2)
    for site, v in {"top-Ni": 0.29168655, "bridge-Cu": 0.30332052}.items():
        assert a["utilization"][site]["vacancy_fraction"] == pytest.approx(v)
    assert a["tof"]["overall"]["per_site_pair_s"] == pytest.approx(81.51277016)
    assert a["tof"]["products"]["HNO-g"]["per_site_pair_s"] == pytest.approx(163.02554032)
    assert a["selectivity"]["molar"] == {"HNO-g": 1}
    assert a["selectivity"]["element_selectivity"]["C"] is None
    assert a["selectivity"]["unconverted_feed_outlet_per_reference_s"] is None
    assert a["utilization"]["top-Ni"]["dominant_adsorbates"] == ["HNO-top"]
    assert a["rates"]["steady_state_residual"] < 1e-12
    ads = a["rates"]["reactions"][0]
    assert a["phase_comparison"]["fcc-Cu"]["occupied_fraction"] == pytest.approx(0.69667948)
    assert ads["kf"] != ads["forward_flux"] and ads["forward_activation_free_energy_eV"] == 0.4
    assert ads["reverse_activation_free_energy_eV"] == 0.5 and ads["applied_forward_barrier_eV"] != 0.4
    factors = ads["activity_factors"]["forward"]
    assert factors["vacancy_factor"] == pytest.approx(0.29168655 * 0.30332052)
    assert {k: factors[k] for k in ("gas_orders", "surface_orders", "vacant_site_orders")} == {
        "gas_orders": {"H2-g": 1},
        "surface_orders": {},
        "vacant_site_orders": {"top-Ni": 1, "bridge-Cu": 1},
    }
    assert ads["gas_contribution"]["H2-g"] == pytest.approx(-81.51277)


def test_topological_branching_and_cycles():
    g = accepted()["pathways"]
    assert g["cross_phase_reactions"] == ["ads", "transfer"]
    assert g["cyclic_species_components"] and len(g["reversible_reactions"]) == 4
    h = next(p for p in g["feed_to_product"] if p["feed"] == "H2-g")
    assert h["competing_paths"] and h["product"] == "HNO-g"
    assert g["pathway_percentages"] is None and g["branching"]
    assert "transfer" in {s["reaction_id"] for p in h["paths"] for s in p["steps"]}


def test_dead_end_and_coreactant_requirement():
    n = read(BASE[0])
    n["species"].append(dict(n["species"][1], species_id="orphan"))
    graph = pathway_graph(n, None, ["NO-g"], ["HNO-g"])
    assert "orphan" in graph["dead_ends"]
    assert "HNO-g" not in graph["feed_reachable_with_all_coreactants"]
    assert graph["feed_to_product"][0]["paths"]  # projected path still needs a hydrogen donor


def test_missing_densities():
    with pytest.raises(ValueError, match="normalization"):
        accepted(None)
    a = accepted()
    assert all(r["concentration_mol_per_surface_m2"] is None for r in a["coverage"])
    assert a["tof"]["overall"]["mol_per_kg_s"] is None and a["tof"]["overall"]["mol_per_m2_s"] is None
    assert a["tof"]["overall"]["per_site_pair_s"] == pytest.approx(81.5127701616477)


def test_quantitative_conversions(tmp_path):
    opt = read(OPTIONS)
    # Explicit synthetic calibration: three top sites and one bridge per chosen reference.
    opt.update(
        reference_basis=None,
        sites_per_reference={"top-Ni": 3, "bridge-Cu": 1},
        site_density_mol_per_surface_m2={"top-Ni": 3e-5, "bridge-Cu": 1e-5},
        reference_mol_per_catalyst_m2=1e-5,
        reference_mol_per_kg=0.02,
        reference_mol_per_reactor_m3=3.0,
    )
    source = tmp_path / "synthetic.json"
    save(source, {k: v for k, v in opt.items() if k != "source"})
    opt["source"] = {"path": source.name, "sha256": sha256_file(source)}
    p = save(tmp_path / "options.json", opt)
    # The conversion arithmetic remains available for this separate calibration.
    # Applying a 3:1 denominator to the accepted 1:1 native extent must fail.
    with pytest.raises(ValueError, match="verified network evidence"):
        accepted(p)
    network, dataset, config, point = map(read, BASE)
    rates = rate_analysis(network, dataset, point)
    coverage = coverage_analysis(network, point, opt, rates)
    tof, _ = product_analysis(config, rates["gas_net_production"], indexed(network["species"], "species_id"),
                              rates["tolerance"], opt, reference={"reference_basis": "other",
                              "denominator_value": 1, "sites_per_reference": opt["sites_per_reference"]})
    c = indexed(coverage["species"], "species_id")["H2-top"]
    assert c["fraction_of_all_sites"] == pytest.approx(c["species_coverage"] * 0.75)
    assert c["concentration_mol_per_surface_m2"] == pytest.approx(c["species_coverage"] * 3e-5)
    extent = tof["extent_per_reference_s"]
    t = tof["overall"]
    assert t["per_site_s"] == pytest.approx(extent / 4)
    assert t["mol_per_m2_s"] == pytest.approx(extent * 1e-5)
    assert t["mol_per_kg_s"] == pytest.approx(extent * 0.02)
    assert t["mol_per_m3_reactor_s"] == pytest.approx(extent * 3)
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="normalization evidence"):
        accepted(p)


def carbon_mixture():
    gas = {"feed": -3.0, "C1": 3.0, "C2": 3.0}
    species = {s: {"composition": {"C": n}} for s, n in zip(gas, (3, 1, 2), strict=True)}
    config = {
        "overall_stoichiometry": {"feed": -1, "C1": 1, "C2": 1},
        "selectivity_products": ["C1", "C2", "feed"],
    }
    return gas, species, config


def test_product_distribution_and_unconverted_feed():
    gas, species, c = carbon_mixture()
    t, s = product_analysis(
        c, gas, species, 1e-10, {"feed_inlet_per_reference_s": {"feed": 4}, "target_products": ["C2"]},
        reference={"reference_basis": "reference_site", "sites_per_reference": {"s": 1}, "denominator_value": 1}
    )
    assert s["molar"] == {"C1": 0.5, "C2": 0.5, "feed": 0}
    assert s["element_selectivity"]["C"] == {"C1": 1 / 3, "C2": 2 / 3, "feed": 0}
    assert s["unconverted_feed_outlet_per_reference_s"] == {"feed": 1}
    assert s["byproduct_production"]["C1"] == 3 and s["consumption"]["feed"] == 3
    assert t["extent_per_reference_s"] == 3 and s["element_balance"]["C"]["residual"] == 0


@pytest.mark.parametrize("key", ["overall_stoichiometry", "selectivity_products"])
def test_missing_selectivity_definition(key):
    gas, species, c = carbon_mixture()
    c.pop(key)
    _, s = product_analysis(c, gas, species, 1e-9, {})
    assert s["molar"] is None and s["element_selectivity"]["C"] is None


@pytest.mark.parametrize("defect", ["overall", "elements", "inlet"])
def test_inconsistent_product_conditions(defect):
    gas, species, c = carbon_mixture()
    opts = {}
    if defect == "overall":
        c["overall_stoichiometry"]["C2"] = 2
    elif defect == "elements":
        c.pop("overall_stoichiometry")
        gas["C1"] = 1
    else:
        opts["feed_inlet_per_reference_s"] = {"feed": 1}
    with pytest.raises(ValueError):
        product_analysis(c, gas, species, 1e-9, opts)


@pytest.mark.parametrize(
    "field",
    [
        "stage",
        "result_sha256",
        "network_version_id",
        "question_id",
        "raw_plan_sha256",
        "approval",
        "output_hashes",
    ],
)
def test_refuse_unbound_result(field):
    m = read(PHASE / "benchmark_manifest.json")
    m[field] = "changed"
    with pytest.raises(ValueError):
        api.analyze(*BASE, m)


def test_draft_inspection(tmp_path):
    f = next((PHASE.parent / "networks").glob("network-2a80*.json"))
    a = api.inspect_draft(f, PHASE.parent / "phase2_4/fe110_parameters.json")
    assert a["status"] == "structural_inspection_only" and all(
        a[k] is None for k in ("tof", "rates", "coverage", "selectivity", "utilization")
    )
    assert (
        a["pathways"]["reactions"][0]["reversible"] is None and a["pathways"]["reactions"][0]["net_flux"] is None
    )
    assert "Unknown site balance" in next(iter(a["missing"]["reactions"].values()))
    api.publish(tmp_path / "draft", a)
    diagram = (tmp_path / "draft/pathways.md").read_text(encoding="utf8")
    assert "unknown" in diagram and "<-->" not in diagram
    assert not (tmp_path / "draft/ticket_handoff.json").exists()


def test_directional_rates():
    n, d, _, p = map(read, BASE)
    # Hypothetical forward-only record with the same NET flux: the residual remains balanced.
    r = n["reactions"][0]
    r["definition"]["reversible"] = False
    r["direction"] = directions(r["definition"])
    row = p["reactions"][0]
    row["kf"] *= row["net_flux"] / row["forward_flux"]
    row.update(kr=None, reverse_flux=None, reverse_unit=None, forward_flux=row["net_flux"])
    a = rate_analysis(n, d, p)["reactions"][0]
    assert (
        a["reversible"] is False and a["reverse_flux"] is None and a["reverse_activation_free_energy_eV"] is None
    )
    r["definition"]["reversible"] = None
    with pytest.raises(ValueError, match="Unknown reversibility"):
        rate_analysis(n, d, p)


def test_site_balance_and_bad_inventory():
    n, d, _, p = map(read, BASE)
    rates = rate_analysis(n, d, p)
    with pytest.raises(ValueError, match="inventory differs"):
        coverage_analysis(n, p, {"sites_per_reference": {"top-Ni": 1}}, rates)
    p["sites"][0]["vacancy_fraction"] += 0.01
    with pytest.raises(ValueError, match="vacancy balance"):
        coverage_analysis(n, p, {}, rates)


@pytest.mark.parametrize("system", ["interface", "oxide", "Fe110"])
def test_run_to_analysis_cli_with_ticket_and_registry(tmp_path, runtime, monkeypatch, system):  # noqa: F811
    n, d, c = cycle_model(system, with_network=True)
    ref = read(BASE[2])
    c.update({k: ref[k] for k in ("overall_stoichiometry", "turnover_basis", "selectivity_products")})
    files = [save(tmp_path / k, v) for k, v in zip(("n", "d", "c"), (n, d, c), strict=True)]
    assert start(tmp_path, runtime, paths=files)["stage"] == "AWAITING_APPROVAL"
    run = tmp_path / "run"
    monkeypatch.setattr(flow, "launch", lambda folder, _exe: replay(folder))
    assert flow.execute(run, approved(tmp_path))["stage"] == "ACCEPTED"
    out = tmp_path / "output"
    args = ["run", str(run), str(out), "--registry-reviewer", "fixture reviewer"]
    api.main(args)
    result = read(out / "analysis.json")
    assert {s["site_type"] for s in result["coverage"]} == {s["site_type"] for s in n["catalog"]["sites"]}
    assert read(out / "ticket_handoff.json")["ticket_id"] == runtime[1]
    graph = (out / "pathways.md").read_text(encoding="utf8")
    assert "<-->|1|" in graph and graph.count(" · reversible") == 4
    batch = read(out / "registry_batch.json")
    assert batch["rows"]["files"][0]["sha256"] == sha256_file(out / "analysis.json")
    assert batch["rows"]["files"][0]["calculation_id"] == "mkm-" + result["source_hashes"]["plan"]
    api.main(args)
    (out / "report.md").write_bytes(b"other content")
    with pytest.raises(ValueError, match="different analysis"):
        api.main(args)


def test_multistep_reversible_cycle_with_distinct_reactions():
    network = read(BASE[0])
    # Parallel transfer mechanisms make a return path with a distinct elementary reaction.
    alternate = deepcopy(network["reactions"][1])
    alternate["definition"]["reaction_id"] = "transfer-alternative"
    network["reactions"].append(alternate)
    g = pathway_graph(network, None, [], [])
    assert g["multistep_cycle_witnesses"]
    cycle = g["multistep_cycle_witnesses"][0]
    assert cycle["species"][0] == cycle["species"][-1]
    assert len(set(s["reaction_id"] for s in cycle["steps"])) == len(cycle["steps"])
    assert g["pathway_percentages"] is None


def test_unequal_phase_inventory_aggregation_requires_weights():
    from scripts.baseline_mkm.kinetic_analysis import phase_utilization

    items = [dict(site_id="acid", occupied_fraction=0.9), dict(site_id="base", occupied_fraction=0.3)]
    assert phase_utilization(items, None)["occupied_fraction"] is None
    assert phase_utilization(items, {"acid": 1, "base": 3})["occupied_fraction"] == pytest.approx(0.45)


def test_near_equilibrium_needs_directional_exchange():
    n, d, _, p = map(read, BASE)
    row = p["reactions"][1]
    for k, flux in (("kf", "forward_flux"), ("kr", "reverse_flux")):
        row[k] *= (row[flux] + 1000) / row[flux]
        row[flux] += 1000
    rates = rate_analysis(n, d, p)
    transfer = rates["reactions"][1]
    assert transfer["near_equilibrium"] and transfer["fractional_directional_imbalance"] < 0.05
    assert rates["relative_activity_extremes"]["forward_flux"]["highest"] == ["transfer"]


def test_loading_and_volume_conversions():
    from scripts.baseline_mkm.kinetic_analysis import physical_factors

    factors = dict(reference_mol_per_catalyst_m2=1e-5, catalyst_m2_per_kg=2000, catalyst_kg_per_reactor_m3=150)
    assert physical_factors(factors) == pytest.approx(
        {"mol_per_m2_s": 1e-5, "mol_per_kg_s": 0.02, "mol_per_m3_reactor_s": 3}
    )
    with pytest.raises(ValueError, match="volume normalization"):
        physical_factors(dict(factors, reference_mol_per_reactor_m3=4))


def test_analysis_contract_for_accepted_and_draft():
    from jsonschema import Draft202012Validator

    schema = read(PHASE.parents[2] / "configs/kinetics/mkm_analysis.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(accepted())
    f = next((PHASE.parent / "networks").glob("network-2a80*.json"))
    draft = api.inspect_draft(f, PHASE.parent / "phase2_4/fe110_parameters.json")
    validator.validate(draft)
    assert not validator.is_valid(dict(draft, tof={"overall": 0}))
