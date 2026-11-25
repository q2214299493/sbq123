"""Offline checks of the review artifact and its discriminators; never starts MATLAB."""
import hashlib
import json
import math

import pytest

from reports.workflow_development.stage_v2_4_0_a.native_probe import prepare as probe
from scripts.baseline_mkm.coverage_ts import evaluate

REVIEW = probe.HERE / "review"


def load(name):
    return json.loads((REVIEW / name).read_bytes())


def test_plan_and_staged_dependencies():
    plan = load("review-plan.json")
    assert hashlib.sha256((REVIEW / "review-plan.json").read_bytes()).hexdigest() == (
        REVIEW / "review-plan.sha256").read_text().split()[0]
    for root, mapping in ((probe.HERE, plan["source_sha256"]), (REVIEW, plan["artifact_sha256"])):
        for path, digest in mapping.items():
            assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest
    assert set(plan["deployment"]["shared_files"]) == {p.name for p in (probe.HERE / "callbacks").glob("*.m")}
    assert all("callbacks/" + name in plan["source_sha256"] for name in plan["deployment"]["shared_files"])
    assert plan["state"] == "BLOCKED" and plan["executable_cases"] == []
    assert plan["permitted_native_calls"] == plan["automatic_retries"] == 0
    assert not plan["execution_authorized"]


@pytest.mark.parametrize("case", ["A", "B", "C"])
def test_callback_is_only_energy_source(case):
    native = (REVIEW / case / probe.INPUT).read_text().splitlines()
    base = (REVIEW / "fixed-baseline.m").read_text().splitlines()
    assert native[0] == "(1): H2 + # <-> H2#"
    assert native[1:len(base)] == base[1:]
    assert native[len(base):] == ["fun2GetGE = @sbq_energy;",
                                  "OdeOption = {'AbsTol',1e-30,'RelTol',1e-10,'Refine',1,'OutputFcn',@sbq_output};"]
    cfg = load(f"{case}/case.json")
    inputs = probe.load_fixture()
    if case == "C":
        assert cfg["frozen_coverage"] is None
    else:
        theta = cfg["frozen_coverage"]
        assert theta == pytest.approx(.1 if case == "A" else 1 / 3)
        expect = evaluate(*inputs, theta)["expected_native_apparent"]
        assert cfg["reference_Ea_eV"] + cfg["w_eV"] * (theta-cfg["reference_coverage"]) == pytest.approx(expect["Ea_eV"])
        assert cfg["reference_G0_eV"] == pytest.approx(expect["G0_eV"])


@pytest.mark.parametrize("theta", [.2, .25])
def test_transient_and_trajectory_distinguish_both_frozen_hypotheses(theta):
    rows = {x["case_id"]: x for x in load("predictions.json") if x["state_fraction"] == theta}
    for case in ("A", "B", "C"):
        row = rows[case]
        f, r = row["kf_per_bar_s"], row["kr_per_s"]
        assert f/r == pytest.approx(.5)
        assert row["residual_fraction_per_s"] == pytest.approx(f*(1-theta)-r*theta)
        assert row["physical_barriers_eV"]["forward"] == row["physical_barriers_eV"]["reverse"]
        if case != "C":
            fixed_time = math.log((1/3-.1)/(1/3-theta))/(f+r)
            assert row["predicted_time_from_initial_s"] == pytest.approx(fixed_time, rel=1e-9)
            for field in ("kf_per_bar_s", "kr_per_s", "residual_fraction_per_s", "predicted_time_from_initial_s"):
                assert abs(rows["C"][field]/row[field]-1) > .05
    assert rows["A"]["predicted_time_from_initial_s"] < rows["C"]["predicted_time_from_initial_s"] < rows["B"]["predicted_time_from_initial_s"]


def test_no_historical_dynamic_observation():
    org = load("interface_evidence.json")
    assert org["CalMode"] == 0
    assert org["callback_sizes"] == dict(fun2GetGE=0, fun2E1=0, fun2E2=0)
    assert org["data_shapes"]["y"] == [1, 5]
    assert not list(REVIEW.rglob("callback_trace.jsonl"))

