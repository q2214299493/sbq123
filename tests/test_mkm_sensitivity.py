"""Deterministic derivative, sign, eligibility, feed and execution-boundary regressions."""

from copy import deepcopy
from math import exp, log

import pytest

from scripts.artifact_io import load_json_object as read
from scripts.baseline_mkm import drc_pair as pair, single_point as point
from scripts.baseline_mkm import sensitivity_inputs as inputs
from scripts.baseline_mkm.sensitivity_report import estimates, step_comparison
from scripts.baseline_mkm.sensitivity_study import LIMITS, specifications
from scripts.thermochemistry.harmonic import KB


@pytest.fixture
def parent():
    return read(inputs.BASE / "closed_cycle_network.json"), read(pair.REPORTS / "phase2_5_2/cycle_dataset.json"), inputs.baseline_config()


def intermediate(sid="HNO-top", step=0.01):
    return dict(kind="intermediate_G", species_id=sid, step=step)


@pytest.mark.parametrize("sid", ["HNO-top", "H2-top", "H2-bridge"])
@pytest.mark.parametrize("sign", [1, -1])
def test_all_incident_steps_follow_fixed_ts(parent, sid, sign):
    n, d, c = parent
    original = deepcopy(d)
    x, config = inputs.derive(n, d, c, intermediate(sid), sign)
    assert inputs.reproduce(n, x) == x and d == original
    info = x["sensitivity_perturbation"]
    assert len(info["affected"]) >= 2 and info["identity"]["site_occupancy"]
    assert x["species_formation_G_eV"][sid] == pytest.approx(info["identity"]["formation_G_eV"] + sign * 0.01)
    for old, new in zip(d["reactions"], x["reactions"], strict=True):
        rid = old["reaction_id"]
        if rid not in info["affected"]:
            assert old == new
            continue
        side = old["direction"]["forward"]
        ni, nf = (side[k].get(sid, 0) for k in ("reactants", "products"))
        g, h = old["energies"]["gibbs_ev"], new["energies"]["gibbs_ev"]
        assert h["reaction"] == pytest.approx(g["reaction"] + (nf - ni) * sign * 0.01)
        assert h["forward"] == pytest.approx(g["forward"] - ni * sign * 0.01)
        assert h["reverse"] == pytest.approx(g["reverse"] - nf * sign * 0.01)
        assert h["forward"] - h["reverse"] == pytest.approx(h["reaction"])
        assert abs(new["equilibrium"]["log_ratio_residual"]) < 1e-12
    assert config["partial_pressure_bar"] == c["partial_pressure_bar"]


@pytest.mark.parametrize("sid", ["H2-g", "top-Ni", "not_registered"])
def test_nonintermediate_rejected(parent, sid):
    n, d, c = parent
    with pytest.raises(ValueError, match="registered surface"):
        inputs.derive(n, d, c, intermediate(sid), 1)


@pytest.mark.parametrize("fault", ["missing G", "draft", "site", "reference", "temperature"])
def test_missing_thermochemistry_or_binding(parent, fault):
    n, d, _ = parent
    thermo, _ = inputs.checked_thermo(n)
    selected = next(s for s in n["species"] if s["species_id"] == "HNO-top")
    if fault == "missing G":
        del thermo["formation_G_eV"]["HNO-top"]
    elif fault == "draft":
        selected["thermochemistry_status"] = "missing"
    elif fault == "site":
        selected["site_occupancy"] = {"unknown": 1}
    elif fault == "reference":
        d["reactions"][2]["parameter_set"]["energy_reference_id"] = "different"
    else:
        thermo["temperature_K"] = 500
    with pytest.raises((ValueError, TypeError)):
        inputs.intermediate_identity(n, d, "HNO-top", thermo)


@pytest.mark.parametrize("constraint", [inputs.FIXED_OTHERS, inputs.FIXED_TOTAL])
@pytest.mark.parametrize("gas", ["CO", "H2O", "CH4", "CO2", "custom"])
def test_gases_from_project_and_two_distinct_experiments(constraint, gas):
    feed = {gas: 0.5, "other": 0.9, "product": 0.2}
    out, total = inputs.pressure_feed(set(feed), feed, 1.6, gas, 0.02, constraint)
    assert log(out[gas] / feed[gas]) == pytest.approx(0.02)
    assert sum(out.values()) == pytest.approx(total)
    if constraint == inputs.FIXED_OTHERS:
        assert total > 1.6 and out["other"] == 0.9 and out["product"] == 0.2
    else:
        assert total == 1.6 and out["other"] / out["product"] == pytest.approx(4.5)


@pytest.mark.parametrize("fault", ["missing gas", "wrong sum", "zero selected", "negative gas", "unknown species", "impossible remainder"])
def test_pressure_rejects_inconsistent_inputs(fault):
    gases = {"A", "B"}
    feed = {"A": 0.5, "B": 0.5}
    sid = "A"
    total = 1
    shift = 0.02
    if fault == "missing gas":
        feed.pop("B")
    elif fault == "wrong sum":
        total = 2
    elif fault == "zero selected":
        feed = {"A": 0, "B": 1}
    elif fault == "negative gas":
        feed = {"A": -0.5, "B": 1.5}
    elif fault == "unknown species":
        sid = "C"
    else:
        shift = 1
    with pytest.raises(ValueError):
        inputs.pressure_feed(gases, feed, total, sid, shift, inputs.FIXED_TOTAL)


def test_partial_pressure_validity_is_checked_before_native(parent):
    n, d, c = parent
    spec = dict(kind="gas_order", species_id="NO-g", step=0.04, constraint=inputs.FIXED_OTHERS)
    with pytest.raises(ValueError, match="validity range"):
        inputs.derive(n, d, c, spec, 1)
    x, y = inputs.derive(n, d, c, spec, -1)
    point.qualify(n, x, y)
    assert y["total_pressure_bar"] < 1.6 and y["partial_pressure_bar"]["H2-g"] == 1
    assert all(r["rates"] == q["rates"] for r, q in zip(d["reactions"], x["reactions"], strict=True))


def test_single_point_gate_rejects_tampered_configuration(parent):
    n, d, c = parent
    x, y = inputs.derive(n, d, c, dict(kind="gas_order", species_id="NO-g", step=0.02, constraint=inputs.FIXED_TOTAL), 1)
    point.qualify(n, x, y)
    y["partial_pressure_bar"] = c["partial_pressure_bar"]
    with pytest.raises(ValueError, match="Feed or conditions"):
        point.qualify(n, x, y)


@pytest.mark.parametrize("kind,expected", [("gas_order", -0.6), ("intermediate_G", 0.7)])
def test_derivative_sign_and_renormalization(kind, expected):
    t = 400
    h = 0.01
    scale = KB * t if kind == "intermediate_G" else 1
    r = estimates(8, 8 * exp(expected * h / scale), 8 * exp(-expected * h / scale), dict(kind=kind, step=h), t)
    assert list(r.values()) == pytest.approx([expected] * 3)


@pytest.mark.parametrize("rates", [(0, 1, 1), (1, 0, 1), (1, 1, -1)])
def test_log_response_requires_positive_tof(rates):
    with pytest.raises(ValueError):
        estimates(*rates, intermediate(), 400)


def test_missing_or_unstable_pair_cannot_pass():
    assert step_comparison(None, 0)["status"] == "unavailable"
    assert step_comparison(0, 0)["status"] == "stable"
    assert step_comparison(-1, -2)["status"] == "unstable"


def test_scope_and_budget():
    specs = dict(
        specifications(
            dict(
                intermediate_G=dict(species_id="HNO-top", coarse=0.01, fine=0.005),
                gas_order=dict(species_id="NO-g", coarse=0.04, fine=0.02, constraint=inputs.FIXED_TOTAL),
            )
        )
    )
    assert 2 * len(specs) == LIMITS["max_runs"] == 8
    assert 8 * point.LIMIT == LIMITS["native_s"] == 1680 and LIMITS["wall_s"] == 1920
    with pytest.raises(ValueError):
        list(specifications(dict(gas_order=dict(species_id="NO-g", coarse=0.01, fine=0.04))))


def test_real_fe_remains_blocked():
    d = read(pair.REPORTS / "phase2_4/fe110_parameters.json")
    n = read(pair.REPORTS / "networks" / ("network-" + d["network_version"] + ".json"))
    with pytest.raises(ValueError, match="blocked"):
        inputs.derive(n, d, dict(dataset_version=d["dataset_version"]), intermediate(), 1)


@pytest.mark.parametrize("fault", ["fourth pair unapproved", "first pair fails", "all accepted"])
def test_entire_study_preflight_and_first_failure(tmp_path, monkeypatch, fault):
    from scripts.artifact_io import sha256_json, write_json_exclusive as save
    from scripts.baseline_mkm import sensitivity_study as study

    experiments = dict(
        intermediate_G=dict(species_id="HNO-top", coarse=0.01, fine=0.005),
        gas_order=dict(species_id="NO-g", coarse=0.04, fine=0.02, constraint=inputs.FIXED_TOTAL),
    )
    jobs, decisions = {}, {}
    for name, spec in study.specifications(experiments):
        folder = tmp_path / name
        folder.mkdir()
        part = dict(sensitivity=spec, baseline_result_sha256="base")
        save(folder / "pair.json", part)
        jobs[name] = dict(spec=spec, pair_sha256=sha256_json(part))
        decisions[name] = {label: str(folder / (label + "-approval")) for label, _ in pair.SIGNS}
    plan = dict(experiments=experiments, jobs=jobs, baseline_hashes={"result": "base"})
    save(tmp_path / "study.json", plan)
    approvals = dict(plan_sha256=sha256_json(plan), decisions=decisions)
    monkeypatch.setattr(study, "prepare", lambda *_: plan)
    verified, invoked = [], []

    def preflight(directory, *args, **kwargs):
        verified.append(directory.name)
        if fault == "fourth pair unapproved" and len(verified) == 4:
            raise PermissionError("unapproved")

    def run(directory, base, decisions, *, campaign_deadline):
        from time import monotonic

        assert 0 < campaign_deadline - monotonic() <= 1920
        assert len(verified) == 4 and set(decisions) == {"plus", "minus"}
        invoked.append(directory.name)
        if fault == "first pair fails":
            raise ValueError("failed pair")

    monkeypatch.setattr(study, "verify_members", preflight)
    monkeypatch.setattr(pair, "run_pair", run)
    if fault == "all accepted":
        assert study.execute(tmp_path, tmp_path, approvals)["total_budget_s"] == 1920
        assert invoked == list(jobs)
    else:
        with pytest.raises((ValueError, PermissionError)):
            study.execute(tmp_path, tmp_path, approvals)
        assert invoked == (["intermediate_G-coarse"] if fault == "first pair fails" else [])
        assert not (tmp_path / "finished.json").exists()


def test_study_legacy_specifications_share_plan_owner():
    from scripts.baseline_mkm import sensitivity_plan

    assert LIMITS is sensitivity_plan.LIMITS
    assert specifications is sensitivity_plan.specifications
