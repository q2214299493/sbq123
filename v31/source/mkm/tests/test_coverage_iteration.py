"""Synthetic interaction fits, analytic equilibrium and receipt-backed offline workflow tests."""

from copy import deepcopy
import json
import math

import numpy as np
import pytest
from jsonschema import ValidationError
from scipy.io import loadmat, savemat
from scipy.optimize import brentq

from scripts.artifact_io import sha256_bytes, sha256_file, sha256_json, write_json_exclusive as save
from scripts.baseline_mkm import coverage_study as study
from scripts.baseline_mkm import single_point as point
from scripts.baseline_mkm.coverage_energy import ExcessGibbs, system_identity
from scripts.baseline_mkm.coverage_feedback import assess_step, compare_roots, stability
from scripts.baseline_mkm.sensitivity_inputs import reproduce
from scripts.kinetic_parameters.engine import generate
from scripts.kinetic_parameters.export import catkinas, zacros
from scripts.thermochemistry.harmonic import KB
from test_coverage_ts import example
from test_kinetic_parameters import signed
from test_mkm_single_point import PHASE, make_decision, replay, runtime  # noqa: F401
from test_mkm_steady_states import C, D, N, POLICY

POL = dict(
    damping=0.5,
    coverage_atol=1e-7,
    energy_eV=1e-8,
    log_k=1e-7,
    source_per_s=1e-5,
    native_residual=1e-7,
    fd_step=1e-5,
    jacobian_rtol=1e-5,
    jacobian_atol=1e-6,
    eigen_margin_per_s=1e-5,
    stagnation_atol=1e-12,
    cycle_atol=1e-8,
)


def synthetic_source(f):
    values = {key: f[key] for key in ("axes", "W", "W_sigma", "capacities", "reactions", "system_sha256")}
    return json.dumps(dict(purpose="Constructed numerical fixture only", values=values), sort_keys=True).encode()


def fixture_model(cycle=False, mutate=None, baseline=None):
    network, parent = baseline or ((point.read(N), point.read(D)) if cycle else example(explicit_reverse=True)[:2])
    species = [s for s in network["species"] if s["phase"] == "surface"]
    sites = {s["site_id"]: 1 for s in network["catalog"]["sites"]}
    n = len(species)
    p = parent["reactions"][0]["parameter_set"]
    fit = dict(
        system_sha256=system_identity(network),
        format="mkm-excess-gibbs/1",
        reference_id="synthetic-repeat",
        energy_reference_id=p["energy_reference_id"],
        standard_state_id=p["standard_state_id"],
        coordinate_unit="molecules/reference_unit",
        energy_unit="eV/reference_unit",
        interaction_unit="eV*reference_unit/molecule^2",
        ts_slope_unit="eV*reference_unit/molecule",
        baseline="reviewed_Gibbs_at_x0",
        uncertainty="independent_upper_triangle_and_TS_1sigma",
        source_sha256=None,
        use_scope="synthetic_benchmark",
        temperature_K=[p["temperature_K"]] * 2,
        pressure_Pa=[p["pressure_Pa"]] * 2,
        capacities=sites,
        axes=[
            dict(
                species_id=s["species_id"],
                basis_inventory=next(iter(s["site_occupancy"])),
                activity_inventory=next(iter(s["site_occupancy"])),
                x0=0 if cycle else 0.5,
                domain=[0, 2],
            )
            for s in species
        ],
        W=np.zeros((n, n)).tolist(),
        W_sigma=np.zeros((n, n)).tolist(),
        reactions={
            r["reaction_id"]: dict(
                parent_gibbs_eV=r["energies"]["gibbs_ev"], absolute_TS_slope=[0] * n, TS_slope_sigma=[0] * n, native_events_per_reference=1
            )
            for r in parent["reactions"]
        },
    )
    if mutate:
        mutate(fit)
    parameter_source = synthetic_source(fit)
    if fit["source_sha256"] is None:
        fit["source_sha256"] = sha256_bytes(parameter_source)
    raw = json.dumps(fit, indent=2)
    digest = sha256_bytes(raw.encode())
    network = deepcopy(network)
    network["source_artifacts"].extend(
        [
            dict(role="verified_evidence", file="synthetic-fit.json", sha256=digest),
            dict(role="verified_evidence", file="synthetic-parameters.json", sha256=sha256_bytes(parameter_source)),
        ]
    )
    del network["network_version"]
    network["network_version"] = sha256_json(network)
    models = []
    for row in parent["reactions"]:
        m = deepcopy(row["model"])
        del m["scientific_review"]
        m["sources"].append(dict(kind="synthetic", reference="synthetic-fit.json", sha256=digest))
        models.extend(signed(network, m)["models"])
    parent = generate(network, dict(network_version=network["network_version"], models=models))
    return ExcessGibbs(network, parent, raw)


def test_one_species_gradient_barriers_and_detailed_balance():
    def fit(f):
        f["W"] = [[0.2]]
        f["W_sigma"] = [[0.01]]
        next(iter(f["reactions"].values()))["absolute_TS_slope"] = [0.03]

    m = fixture_model(mutate=fit)
    x = np.array([0.7])
    phi, mu = m.energy(x)
    assert phi == pytest.approx(0.004)
    assert mu == pytest.approx([0.04])
    assert (m.energy(x + 1e-6)[0] - m.energy(x - 1e-6)[0]) / 2e-6 == pytest.approx(mu[0])
    child = m.child(m.fractions(x))
    row = child["reactions"][0]
    assert row["energies"]["gibbs_ev"] == pytest.approx(dict(forward=0.406, reverse=0.366, reaction=0.04))
    assert row["coverage_energy"]["correction_sigma_eV"]["reaction"] == pytest.approx(0.002)
    assert row["equilibrium"]["log_ratio_residual"] == pytest.approx(0, abs=1e-12)
    assert reproduce(m.network, child) == child
    assert catkinas(child)["rows"][0]["provenance"]["coverage_energy"]["fit_sha256"] == m.digest
    with pytest.raises(ValueError, match="lattice"):
        zacros(child)


def test_cross_interaction_coordinate_conversion():
    def fit(f):
        f["W"][0][1] = f["W"][1][0] = -0.08
        f["capacities"][f["axes"][0]["basis_inventory"]] = 2

    m = fixture_model(True, fit)
    theta = {s: 0.2 for s in m.ids}
    x = m.coordinates(theta)
    assert x[0] == pytest.approx(0.4)
    assert m.fractions(x) == theta
    phi, mu = m.energy(x)
    assert phi == pytest.approx(-0.08 * x[0] * x[1])
    assert mu == pytest.approx([-0.08 * x[1], -0.08 * x[0], 0])
    for v, analytic in zip(np.eye(len(x)), mu, strict=True):
        assert (m.energy(x + 1e-6 * v)[0] - m.energy(x - 1e-6 * v)[0]) / 2e-6 == pytest.approx(analytic)
    with pytest.raises(ValueError, match="inventory"):
        m.coordinates(dict.fromkeys(m.ids, 0.9))


@pytest.mark.parametrize("defect", ["asymmetric", "domain", "source", "reference", "ts", "baseline"])
def test_invalid_fit(defect):
    def bad(f):
        if defect == "asymmetric":
            f["W"][0][1] = 1
        elif defect == "domain":
            f["axes"][0]["domain"] = [0.1, 1]
        elif defect == "source":
            f["source_sha256"] = "0" * 64
        elif defect == "reference":
            f["energy_reference_id"] = "other"
        elif defect == "ts":
            next(iter(f["reactions"].values()))["absolute_TS_slope"] = []
        else:
            next(iter(f["reactions"].values()))["parent_gibbs_eV"] = dict(forward=2, reverse=2, reaction=0)

    with pytest.raises((ValueError, ValidationError)):
        fixture_model(True, bad)


def test_duplicate_tampering_and_fixed_compatibility():
    m = fixture_model()
    theta = m.fractions(m.x0)
    child = m.child(theta)
    assert catkinas(child)["rows"][0]["fixed_T_energy_input"] == catkinas(m.parent)["rows"][0]["fixed_T_energy_input"]
    with pytest.raises(ValueError, match="unmodified"):
        ExcessGibbs(m.network, child, m.fit_text)
    with pytest.raises(ValueError, match="verified"):
        ExcessGibbs(m.network, m.parent, m.fit_text + " ")
    with pytest.raises(ValueError, match="already|previously"):
        fixture_model(baseline=example(existing_term=True)[:2])
    altered = deepcopy(child)
    altered["reactions"][0]["energies"]["gibbs_ev"]["forward"] += 0.1
    assert reproduce(m.network, altered) != altered


def observed(m, y, tag):
    theta = m.fractions(np.asarray([y]))
    return dict(
        run=tag, coverage=theta, vacancy=m.check_x(m.coordinates(theta)), residual=0, net_rate={"ads": 0}, tof={"per_reference_s": None}
    )


def test_three_roots_complete_jacobian_and_classification():
    # Equal unit activities at half coverage. Choose gas pressure p0/2 and shift baseline
    # reaction free energy by kBT ln(1/2) to recover the symmetric Frumkin equation.
    kt = KB * 400
    baseline = example(explicit_reverse=True, reaction_g=kt * math.log(0.5))[:2]

    def fit(f):
        f["W"] = [[-6 * kt]]
        f["capacities"][f["axes"][0]["basis_inventory"]] = 2
        f["axes"][0]["x0"] = 1.0
        f["W"] = [[-3 * kt]]  # x=2 theta

    m = fixture_model(mutate=fit, baseline=baseline)
    pressure = {"partial_pressure_bar": {"H2-g": 1.0}}

    def fn(t):
        return math.log(t / (1 - t)) - 6 * (t - 0.5)

    roots = [brentq(fn, 0.001, 0.2, xtol=1e-15), 0.5, brentq(fn, 0.8, 0.999, xtol=1e-15)]
    branches = []
    for i, t in enumerate(roots):
        obs = observed(m, 2 * t, str(i))
        result = assess_step(m, m.child(obs["coverage"]), obs, pressure, [], POL)
        assert result["status"] == "CONVERGED"
        report = result["stability"]
        assert report["status"] == ["STABLE", "UNSTABLE", "STABLE"][i], report
        assert report["feedback"][0][0] != 0
        assert np.asarray(report["reduced"]) == pytest.approx(np.asarray(report["fd"][-1]), rel=1e-5)
        branches.append(dict(status="CONVERGED", history=[dict(observation=obs)]))
    duplicate = deepcopy(branches[0])
    duplicate["history"][-1]["observation"]["run"] = "repeat"
    summary = compare_roots([*branches, duplicate], POLICY, m)
    assert summary["classification"] == "MULTIPLE_STEADY_STATES_OBSERVED"
    assert summary["root_partition"] == {"groups": [["0", "repeat"], ["1"], ["2"]], "distinct_observed_roots": 3}
    assert stability(m, m.fractions(np.array([0.6])), pressure, POL)["status"] == "UNKNOWN"


def test_damping_cycles_stagnation_and_missing_scale():
    m = fixture_model()
    p = {"partial_pressure_bar": {"H2-g": 1.0}}
    theta, obs = {"H2-ads": 0.2}, observed(m, 0.8, "trial")
    with pytest.raises(ValueError, match="domain|inventory"):
        m.child({"H2-ads": 2.5})
    r = assess_step(m, m.child(theta), obs, p, [], POL)
    assert r["status"] == "CONTINUE"
    assert r["next_coverage"] == {"H2-ads": 0.5}
    policy = dict(POL, damping=1)
    assert assess_step(m, m.child(theta), obs, p, [{"evaluation_coverage": obs["coverage"]}], policy)["status"] == "CYCLE"
    assert assess_step(m, m.child(theta), obs, p, [], dict(POL, damping=1e-15))["status"] == "STAGNATED"

    def missing(f):
        next(iter(f["reactions"].values()))["native_events_per_reference"] = None

    m = fixture_model(mutate=missing)
    assert stability(m, theta, p, POL)["status"] == "UNKNOWN"


def create_study(tmp_path, ticket, limit=2):
    m = fixture_model(True)
    cfg = point.read(C)
    cfg.pop("turnover_basis")
    cfg["dataset_version"] = m.parent["dataset_version"]
    initial = cfg["catkinas"]["initial_coverages"]
    policy = dict(POL, source_per_s=0.1, damping=1.0)
    req = dict(
        format="mkm-coverage-study/1",
        branches=[dict(initial=initial, max_calls=limit)],
        max_total_calls=2,
        iteration=policy,
        root_tolerances=POLICY,
    )
    paths = [save(tmp_path / name, v) for name, v in (("request", req), ("network", m.network), ("dataset", m.parent), ("config", cfg))]
    fit = tmp_path / "fit"
    fit.write_bytes(m.fit_text.encode())
    out = study.create(tmp_path / "outer", *paths, fit, *ticket, tmp_path / "offline")
    return tmp_path / "outer/study.json", out["sha256"]


@pytest.mark.parametrize("fail", [True, False])
def test_gate_replay_and_restart(tmp_path, runtime, monkeypatch, fail):  # noqa: F811
    original = point.tools_for_run
    monkeypatch.setattr(point, "tools_for_run", lambda p: dict(original(p), matlab_sha256="0" * 64))
    path, h = create_study(tmp_path, runtime)
    calls = []

    def simulated(directory, executable):
        calls.append(directory)
        if fail:
            return 7
        replay(directory)
        if len(calls) == 2:
            # Offline only: echo the second native initial condition in a copied MAT.
            from scripts.baseline_mkm.results import read_initial_coverages

            out = directory / "result_phase25"
            mat = out / "data1.mat"
            symbols = read_initial_coverages(mat, (out / "log1").read_text())
            lines = (directory / point.INPUT).read_text().splitlines()
            values = dict(line.removesuffix(";").split(" = ") for line in lines if "_INIT = " in line)
            native = {k: v for k, v in loadmat(mat).items() if not k.startswith("_")}
            native["yInits"] = np.asarray([[float(values[k + "_INIT"]) for k in symbols]])
            savemat(mat, native)
        return 0

    monkeypatch.setattr(point, "launch", simulated)

    def advance(mode, decision=None):
        return study.advance(path, h, mode, 1, decision)["branches"][0]

    assert advance("inspect")["status"] == "NOT_PREPARED"
    first = advance("prepare")
    assert first["status"] == "AWAITING_APPROVAL", first
    assert advance("prepare") == first and not calls
    run = path.parent / first["member"]
    source = PHASE / "benchmark_ticket_fixture.json"
    deny = make_decision(run, source)
    deny["DECISION"] = "reject"
    denied = advance("execute", save(tmp_path / "rejected-decision", deny))
    assert denied["status"] == "INCONCLUSIVE" and not calls
    decision = save(tmp_path / "fixture-approval", make_decision(run, source))
    result = advance("execute", decision)
    assert len(calls) == 1
    if fail:
        assert result["status"] == "REJECTED"
        assert advance("execute", decision) == result and len(calls) == 1
    else:
        assert result["status"] == "NOT_PREPARED", result
        (first_record,) = result["history"]
        assert first_record["status"] == "CONTINUE"
        assert first_record["observation"]["receipt_sha256"] == sha256_file(run / "ACCEPTED.json")
        assert advance("inspect") == result
        second = advance("prepare")
        assert second["status"] == "AWAITING_APPROVAL" and len(calls) == 1
        next_child = point.read(path.parent / second["member"] / "dataset.json")
        assert next_child["coverage_iteration"]["previous_receipt_sha256"] == first_record["observation"]["receipt_sha256"]
        assert advance("execute", decision)["status"] == "INCONCLUSIVE" and len(calls) == 1
        new_run = path.parent / second["member"]
        fresh = save(tmp_path / "second-approval", make_decision(new_run, source))
        final = advance("execute", fresh)
        assert final["status"] == "CONVERGED", final
        assert advance("inspect") == final and len(calls) == 2
        assert final["history"][-1]["native_initial"] == first_record["native_final"]
    with pytest.raises(ValueError, match="SHA"):
        study.advance(path, "0" * 64)


def test_two_molecular_axes_unequal_capacity_constrained_jacobian():
    from test_kinetic_parameters import case, dataset

    n, binding = case(system="oxide")
    parent = dataset(n, binding)

    def fit(f):
        f["capacities"]["top-Ni"] = 2
        f["axes"][0].update(x0=0.2, basis_inventory="bridge-Cu")
        f["axes"][1]["x0"] = 0.3
        f["W"] = [[0.04, -0.025], [-0.025, 0.015]]
        next(iter(f["reactions"].values()))["absolute_TS_slope"] = [0.01, -0.008]

    m = fixture_model(baseline=(n, parent), mutate=fit)
    from scripts.baseline_mkm.coverage_feedback import physical_source

    cfg = dict(partial_pressure_bar={})

    def rhs(v):
        x = np.array([v, 0.5 - v])
        return physical_source(m, m.child(m.fractions(x)), x, cfg)[0]

    a = brentq(rhs, 1e-5, 0.49999, xtol=1e-15)
    x = np.array([a, 0.5 - a])
    vacancies = m.check_x(x)
    assert vacancies["top-Ni"] == pytest.approx(0.75)
    assert vacancies["bridge-Cu"] == pytest.approx(1 - a)
    r = stability(m, m.fractions(x), cfg, dict(POL, source_per_s=1e-4))
    assert r["status"] == "STABLE", r
    assert np.shape(r["basis"]) == (2, 1)
    assert np.shape(r["fixed"]) == np.shape(r["feedback"]) == (2, 2)
    assert r["reduced"][0][0] == pytest.approx((rhs(a + 1e-6) - rhs(a - 1e-6)) / 2e-6, rel=1e-6)

    # Molecular populations from different conserved totals cannot be counted as two roots.
    def record(tag, state):
        return dict(status="CONVERGED", history=[dict(observation=dict(run=tag, coverage=m.fractions(state), residual=0))])

    out = compare_roots([record("a", x), record("b", 0.8 * x)], POLICY, m)
    assert out["comparisons"][0]["classification"] == "DIFFERENT_CONSERVED_TOTALS"


def test_analytic_frozen_map_multiple_independent_branches():
    kt = KB * 400
    base = example(explicit_reverse=True, reaction_g=kt * math.log(0.5))[:2]

    def fit(f):
        f["W"] = [[-6 * kt]]

    m = fixture_model(mutate=fit, baseline=base)
    cfg = dict(partial_pressure_bar={"H2-g": 1.0})
    policies = dict(POL, damping=0.8, stagnation_atol=1e-16)
    branches = []
    for index, start in enumerate((0.02, 0.5, 0.98)):
        history, theta = [], {"H2-ads": start}
        for iteration in range(150):
            child = m.child(theta)
            # Exact inner steady state of this one reversible frozen adsorption.
            y = 1 / (1 + math.exp(-6 * (theta["H2-ads"] - 0.5)))
            obs = observed(m, y, f"{index}-{iteration}")
            result = assess_step(m, child, obs, cfg, history, policies)
            history.append(dict(evaluation_coverage=theta, observation=obs, **result))
            if result["status"] == "CONVERGED":
                break
            assert result["status"] == "CONTINUE", result
            theta = result["next_coverage"]
        assert history[-1]["status"] == "CONVERGED"
        branches.append(dict(status="CONVERGED", history=history))
    assert compare_roots(branches, POLICY, m)["classification"] == "MULTIPLE_STEADY_STATES_OBSERVED"
    assert [b["history"][-1]["stability"]["status"] for b in branches] == ["STABLE", "UNSTABLE", "STABLE"]


def test_budget_and_duplicate_branch_rejection():
    m = fixture_model()
    b = dict(initial={"H2-ads": 0.2}, max_calls=2)
    req = dict(format="mkm-coverage-study/1", branches=[b], max_total_calls=1, iteration=POL, root_tolerances=POLICY)
    with pytest.raises(ValueError, match="budget"):
        study.check_request(req, m)
    with pytest.raises(ValueError, match="distinct"):
        study.check_request(dict(req, branches=[b, b], max_total_calls=4), m)


def test_unknown_mapping_preserves_root_evidence_and_native_qualification():
    def missing(f):
        f["axes"][0]["activity_inventory"] = None

    m = fixture_model(mutate=missing)
    obs = observed(m, 0.5, "fixed-point")
    cfg = {"partial_pressure_bar": {"H2-g": 1.0}}
    result = study.evaluate_observation(m, m.child(obs["coverage"]), obs, cfg, [], POL)
    assert result["status"] == "INCONCLUSIVE" and result["stability"]["status"] == "UNKNOWN"
    assert "activity mapping" in result["reason"]
    valid = fixture_model()
    assert "gas partial pressure" in stability(valid, obs["coverage"], {"partial_pressure_bar": {}}, POL)["reason"]


def test_identical_reference_rejects_inconsistent_capacities_and_units():
    m = fixture_model()
    ref = dict(reference_id=m.fit["reference_id"], sites_per_reference=m.fit["capacities"], denominator_value=1)
    study.check_reference(m, ref)
    with pytest.raises(ValueError, match="capacities"):
        study.check_reference(m, dict(ref, sites_per_reference={}))
    with pytest.raises(ValueError, match="extent"):
        study.check_reference(m, dict(ref, denominator_value=2))
    with pytest.raises(ValueError, match="different catalyst"):
        fixture_model(mutate=lambda f: f.update(system_sha256="1" * 64))


def test_budget_exhaustion_keeps_last_accepted_and_never_restarts(tmp_path, runtime, monkeypatch):  # noqa: F811
    tools = point.tools_for_run
    monkeypatch.setattr(point, "tools_for_run", lambda p: dict(tools(p), matlab_sha256="0" * 64))
    path, digest = create_study(tmp_path, runtime, limit=1)
    initial = study.advance(path, digest, "prepare", 1)["branches"][0]
    run = path.parent / initial["member"]
    calls = []

    def fake(directory, executable):
        calls.append(directory)
        return replay(directory)

    monkeypatch.setattr(point, "launch", fake)
    decision = save(tmp_path / "decision", make_decision(run, PHASE / "benchmark_ticket_fixture.json"))
    end = study.advance(path, digest, "execute", 1, decision)["branches"][0]
    assert end["status"] == "BUDGET_EXHAUSTED" and end["history"][0]["status"] == "CONTINUE"
    assert study.advance(path, digest, "prepare", 1)["branches"][0] == end and len(calls) == 1
    assessment = path.parent / (initial["member"] + "-assessment.json")
    record = point.read(assessment)
    record["native_final"] = {}
    assessment.write_text(json.dumps(record))
    invalid = study.advance(path, digest)["branches"][0]
    assert invalid["status"] == "INCONCLUSIVE" and "differs from replay" in invalid["reason"]
