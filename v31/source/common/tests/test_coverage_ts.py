"""One reversible molecular adsorption with one independent coverage; synthetic offline evidence only."""
from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
import sys

from jsonschema import ValidationError
import pytest

from scripts.artifact_io import sha256_bytes, sha256_json
from scripts.baseline_mkm.coverage_ts import evaluate
from scripts.baseline_mkm.single_point_result import check_close
from scripts.kinetic_parameters.engine import generate
from scripts.kinetic_parameters.export import catkinas
from scripts.native_model import assemble
from scripts.reaction_network.builder import build_network
from test_kinetic_parameters import case, signed


def example(*, change=None, explicit_reverse=False, existing_term=False, cite_fit=True, zero_slope=False, reaction_g=0):
    base, model = case(system="Fe110", gas=True, standard_pa=200000)
    definition = deepcopy(base["reactions"][0]["definition"])
    param = deepcopy(base["parameter_sets"][0])
    old_product, = definition["products"]
    product = "H2-ads"
    site = base["catalog"]["sites"][0]
    sid = site["site_id"] = "fixture-site"
    surface = next(s for s in base["catalog"]["surfaces"] if s["surface_id"] == site["surface_id"])
    species = [deepcopy(s) for s in base["species"] if s["species_id"] in definition["reactants"] | definition["products"]]
    for s in species:
        if s["species_id"] == old_product:
            s.update(species_id=product, site_occupancy={sid: 1})
    definition.update(products={product: 1}, required_sites={sid: 1}, sites_consumed={sid: 1})
    gibbs = dict(forward=.4, reverse=.4-reaction_g, reaction=reaction_g)
    for key, x in gibbs.items():
        definition["free_energies"]["values"][key]["value"] = x
        if key != "reaction":
            param[key]["activation_energy"]["value"] = x
    if explicit_reverse:
        model["forward"] = model["reverse"] = {"method": "prefactor"}
        for side in ("forward", "reverse"):
            param[side].update(prefactor=1.e12, prefactor_unit="s^-1")
    model.pop("local_event")
    # These are declared synthetic coefficients, never fitted or submitted as research data.
    source = (Path(__file__).parent / "fixtures/coverage_ts/fixture-slope.json").read_bytes()
    path = "tests/fixtures/coverage_ts/fixture-slope.json"
    if zero_slope or reaction_g:
        reference = json.loads(source)
        forward = [.4, .4 if zero_slope else .45]
        reference.update(forward_barrier_eV=forward, reverse_barrier_eV=[g - reaction_g for g in forward],
                         reaction_G_eV=reaction_g)
        source = json.dumps(reference).encode()
        path = "synthetic-variant-slope.json"
    src = dict(kind="synthetic", calculation_id="fixture-ts-slope",
               artifact={"path": path, "sha256": sha256_bytes(source)})
    term = dict(species_id=product, coefficient=dict(value=0 if zero_slope else .1, unit="eV", reference_id=param["energy_reference_id"], source=src),
                expression="linear_transition_state_shift", already_in_barrier=False, min_fraction=.05, max_fraction=.9)
    fit = dict(format="linear-ts-at-reference/1", reaction_id=definition["reaction_id"], parameter_set_id=param["parameter_set_id"],
               phase_id=surface["phase_id"], surface_id=surface["surface_id"], site_inventory_id=sid,
               coverage_basis="fraction_of_named_site_inventory", reference_coverage=.2, reference_gibbs_eV=gibbs,
               validity_range=deepcopy(param["validity_range"]), term=term)
    if change:
        change(fit, param)
    raw = json.dumps(fit, sort_keys=True, allow_nan=False).encode()
    digest = sha256_bytes(raw)
    sources = [*base["source_artifacts"], dict(role="verified_evidence", file=Path(path).name, sha256=sha256_bytes(source)),
               dict(role="verified_evidence", file="fit.json", sha256=digest)]
    if cite_fit:
        model["sources"].append(dict(kind="synthetic", reference="fit.json", sha256=digest))
    if existing_term:
        param["coverage_terms"] = [deepcopy(term)]
        param["coverage_terms"][0]["coefficient"]["source"] = deepcopy(param["sources"][0])
        model["coverage_fractions"] = {product: .2}
    bundle = dict(base["catalog"], schema_version="1.0.0", sites=[site], species=species, reactions=[definition],
                  parameter_sets=[param], runs=[])
    options = dict(sources=sources, verified_hashes={s["sha256"] for s in sources},
                   ts_reviews=[dict(reaction_id=fit["reaction_id"], grade="A", structure_identity=definition["ts_id"],
                                    assignment="synthetic fixture", review_reference="fixture TS")])
    first = build_network(bundle, **options)
    decision = dict(reaction_id=definition["reaction_id"], subject_sha256=first["reactions"][0]["subject_sha256"],
                    decision="accepted", reviewer="software fixture", reason="test only", reviewed_at="2026-11-19T01:00:00Z")
    network = build_network(bundle, **options, decisions=[decision])
    dataset = generate(network, signed(network, model))
    binding = dict(format="mkm-coverage-ts/1", network_version=network["network_version"], dataset_version=dataset["dataset_version"],
                   evidence=dict(path="fit.json", sha256=digest))
    return network, dataset, binding, raw


@pytest.mark.parametrize("explicit_reverse", [False, True])
@pytest.mark.parametrize("theta", [.05, .2, .65, .9])
def test_both_directions_and_native_units(theta, explicit_reverse):
    inputs = example(explicit_reverse=explicit_reverse)
    n, d, binding, raw = inputs
    before = sha256_json([n, d, binding])
    result = evaluate(*inputs, theta)
    delta = .1 * (theta - .2)
    assert result["delta_G_TS_eV"] == pytest.approx(delta)
    assert result["physical_gibbs_eV"] == pytest.approx(dict(forward=.4+delta, reverse=.4+delta, reaction=0))
    # Independent Boltzmann factor, standard-state coefficients, and per-bar encoding.
    factor = math.exp(-delta/(8.617333262145e-5*400))
    parent = catkinas(d)["rows"][0]
    for side in ("forward", "reverse"):
        check_close(result["expected_native_coefficients"][side]["coefficient"], parent[side]["coefficient"]*factor, side)
    k = result["activity_coefficients_per_s"]
    assert k["forward"] / k["reverse"] == pytest.approx(1)
    assert abs(result["equilibrium"]["log_ratio_residual"]) < 1e-10
    native = result["expected_native_apparent"]
    assert native["Ea_eV"] == pytest.approx(parent["fixed_T_energy_input"]["Ea_eV"] + delta)
    assert native["G0_eV"] == pytest.approx(8.617333262145e-5 * 400 * math.log(2))
    assert not result["execution_authorized"] and result["native_feedback"] == "BLOCKED"
    assert before == sha256_json([n, d, binding])
    assert result["contract"]["format"] == "mkm-coverage-ts-contract/1"
    assert result["contract"]["scientific_review"] == d["reactions"][0]["model"]["scientific_review"]


def test_zero_coefficient_and_cli(tmp_path):
    inputs = example(zero_slope=True)
    n, d, binding, raw = inputs
    for name, value in (("n", n), ("d", d), ("binding", binding)):
        (tmp_path / name).write_text(json.dumps(value))
    (tmp_path / "fit.json").write_bytes(raw)
    args = [sys.executable, "-m", "scripts.baseline_mkm.coverage_ts", *(str(tmp_path / k) for k in ("n", "d", "binding")), ".8"]
    result = json.loads(subprocess.check_output(args, cwd=Path(__file__).resolve().parents[1]))
    parent = catkinas(d)["rows"][0]
    assert result["expected_native_apparent"] == parent["fixed_T_energy_input"]
    for side in ("forward", "reverse"):
        assert result["expected_native_coefficients"][side] == parent[side]


@pytest.mark.parametrize("theta", [True, "0.4", float("inf"), float("nan"), -.01, 1.001, .01, .91])
def test_invalid_coverage(theta):
    with pytest.raises(ValueError):
        evaluate(*example(), theta)


@pytest.mark.parametrize("change", [
    lambda f, p: f.pop("reference_coverage"), lambda f, p: f.update(reference_coverage=.95),
    lambda f, p: f.update(site_inventory_id="other"), lambda f, p: f.update(surface_id="other"),
    lambda f, p: f.update(phase_id="other"), lambda f, p: f.update(coverage_basis="per_site_pair"),
    lambda f, p: f["term"].update(already_in_barrier=True), lambda f, p: f["term"].update(species_id="H2-g"),
    lambda f, p: f["term"]["coefficient"].update(unit="kJ/mol"), lambda f, p: f["term"]["coefficient"].update(reference_id="other"),
    lambda f, p: f["reference_gibbs_eV"].update(forward=.45), lambda f, p: f.update(parameter_set_id="other"),
    lambda f, p: f["term"]["coefficient"]["source"]["artifact"].update(sha256="0"*64),
    lambda f, p: f["validity_range"].update(max_pressure_Pa=99999), lambda f, p: f["validity_range"].update(min_temperature_K=450),
])
def test_incompatible_scientific_fit(change):
    inputs = example(change=change)
    with pytest.raises((ValueError, ValidationError)):
        evaluate(*inputs, .3)


def test_stale_bindings_and_unreviewed_source():
    n, d, b, raw = example()
    for key in ("network_version", "dataset_version"):
        with pytest.raises(ValueError, match="versions"):
            evaluate(n, d, dict(b, **{key: "0"*64}), raw, .3)
    with pytest.raises(ValueError, match="SHA-256"):
        evaluate(n, d, b, raw+b" ", .3)
    fresh = raw+b" "
    with pytest.raises(ValueError, match="review evidence"):
        evaluate(n, d, dict(b, evidence=dict(b["evidence"], sha256=sha256_bytes(fresh))), fresh, .3)
    changed = deepcopy(d)
    changed["reactions"][0]["energies"]["gibbs_ev"]["forward"] += .1
    changed["dataset_version"] = sha256_json({k: v for k, v in changed.items() if k != "dataset_version"})
    with pytest.raises(ValueError, match="reproduced"):
        evaluate(n, changed, dict(b, dataset_version=changed["dataset_version"]), raw, .3)


def test_discrimination_at_solver_trial_states():
    # Frozen initial, frozen final and dynamic have the same interior root.
    inputs = example()
    theta0, root = .1, 1/3  # a_g = 1 bar / 2 bar; standard-state K = 1

    def residual(state, sampled):
        rates = evaluate(*inputs, sampled)["activity_coefficients_per_s"]
        return rates["forward"]*.5*(1-state) - rates["reverse"]*state

    for sampled in (theta0, root, .25):
        assert abs(residual(root, sampled)) < 1e-10
    for state in (.2, .25):
        rates = [residual(state, sampled) for sampled in (theta0, root, state)]
        assert len({round(x, 6) for x in rates}) == 3
    assert residual(.1, .1) > 0 and residual(.8, .8) < 0


def test_fit_must_be_cited_by_kinetic_review():
    with pytest.raises(ValueError, match="review evidence"):
        evaluate(*example(cite_fit=False), .4)


def test_existing_fixed_term_cannot_be_applied_twice():
    inputs = example(existing_term=True)
    assert inputs[1]["export_eligible"]
    with pytest.raises(ValueError, match="previously applied"):
        evaluate(*inputs, .4)


def test_discriminator_fixed_baseline_native_readback():
    _, dataset, _, _ = example()
    cfg = {"dataset_version": dataset["dataset_version"], "partial_pressure_bar": {"H2-g": 1},
           "catkinas": {"aliases": {"H2-ads": "H2", "H2-g": "H2"}, "initial_coverages": {"H2-ads": .1},
                        "MaxTime": 3, "MaxOdeTime": 3}}
    files, manifest = assemble("catkinas", dataset, cfg)
    assert "(1): H2 + # <-> H2#" in files["INPUT_phase25.m"]
    assert manifest["validation"]["native_text_readback"] == {
        "equation_count": 1, "correction_switches": [0, -2, 0], "coefficients_round_trip": True}


@pytest.mark.parametrize("explicit_reverse", [True, False])
def test_nonunity_equilibrium_is_preserved(explicit_reverse):
    inputs = example(reaction_g=-.025, explicit_reverse=explicit_reverse)
    for theta in (.1, .7):
        result = evaluate(*inputs, theta)
        k = result["activity_coefficients_per_s"]
        g = result["physical_gibbs_eV"]
        assert g["forward"] - g["reverse"] == pytest.approx(-.025)
        assert k["forward"] / k["reverse"] == pytest.approx(math.exp(.025 / (8.617333262145e-5*400)))
