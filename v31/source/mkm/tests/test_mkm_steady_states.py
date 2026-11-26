"""Offline initialization and steady-state classification, including actual historical readback."""
from pathlib import Path

from jsonschema import Draft202012Validator
import numpy as np
import pytest
from scipy.io import loadmat, savemat

from scripts.baseline_mkm import steady_states as ss
from scripts.baseline_mkm import single_point as point
from scripts.artifact_io import write_json_exclusive as save
from test_mkm_single_point import OUT, PHASE, make_decision, replay, runtime  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
PROFILE = PHASE.parent / "phase3_1/benchmark_normalization.json"
N, D, C = PHASE / "closed_cycle_network.json", OUT / "cycle_dataset.json", PHASE / "workflow_configuration.json"
POLICY = dict(format="mkm-steady-tolerances/1", coverage=1e-7, vacancy=1e-7, net_rate=1e-6,
              tof=1e-6, relative=1e-8, max_residual=1e-7, separation_factor=5)


def study_request():
    bare = ss.read(C)["catkinas"]["initial_coverages"]
    return dict(format="mkm-initial-states/1", network_version=ss.read(N)["network_version"],
                dataset_version=ss.read(D)["dataset_version"], tolerances=POLICY,
                initial_coverages=[bare, dict(bare, **{"H2-top": 0.25})])


def prepare(tmp_path, runtime, spec, configuration=C, profile=PROFILE):  # noqa: F811
    return ss.prepare(tmp_path / "study", save(tmp_path / "spec.json", spec), N, D, configuration, *runtime,
                      tmp_path / "offline", profile)


@pytest.mark.parametrize("defect", ["unknown", "missing", "negative", "nan", "overflow", "network", "dataset", "duplicate"])
def test_prepare_rejects_invalid_before_creating_runs(tmp_path, runtime, defect):  # noqa: F811
    spec = study_request()
    state = spec["initial_coverages"][1]
    if defect in ("network", "dataset"):
        spec[defect + "_version"] = "f" * 64
    elif defect == "unknown":
        state["alien"] = 0
    elif defect == "missing":
        del state["H2-bridge"]
    elif defect == "duplicate":
        state["H2-top"] = 0
    else:
        state["H2-top"] = {"negative": -0.1, "nan": float("nan"), "overflow": 1.1}[defect]
    with pytest.raises(ValueError):
        prepare(tmp_path, runtime, spec)
    assert not (tmp_path / "study").exists()


@pytest.fixture
def pair(tmp_path, monkeypatch, runtime, request):  # noqa: F811
    tools = point.tools_for_run
    monkeypatch.setattr(point, "tools_for_run", lambda p: dict(tools(p), matlab_sha256="0" * 64))
    if getattr(request, "param", None) == "native_only":
        config = ss.read(C)
        del config["turnover_basis"]
        result = prepare(tmp_path, runtime, study_request(), save(tmp_path / "native-only.json", config), None)
    else:
        result = prepare(tmp_path, runtime, study_request())
    assert list(result["stages"].values()) == ["AWAITING_APPROVAL"] * 2
    path = Path(result["study"])

    def simulated(directory, executable):
        replay(directory)
        # Synthetic readback of the second requested start; all terminal data are the archived fixture.
        if directory.parent.name == "point-002":
            mat = directory / "result_phase25/data1.mat"
            data = {k: v for k, v in loadmat(mat).items() if not k.startswith("_")}
            data["yInits"] = np.array([[0.25, 0, 0.75, 0, 1]])
            savemat(mat, data)
        return 0

    monkeypatch.setattr(point, "launch", simulated)
    return path, result["study_sha256"]


def accept(path, name):
    run = path.parent / name
    decision = save(run / "fixture-decision.json", make_decision(run, PHASE / "benchmark_ticket_fixture.json"))
    return point.execute(run, decision)["stage"]


def test_full_offline_pair(pair):
    path, digest = pair
    for name in ("point-001", "point-002"):
        assert accept(path, name) == "ACCEPTED"
    report = ss.assess(path, digest)
    assert report["classification"] == ss.SINGLE, report["blockers"]
    Draft202012Validator(ss.read(ROOT / "configs/kinetics/mkm_steady_state_assessment.schema.json")).validate(report)
    a, b = report["members"]
    assert a["native_initial"] != b["native_initial"] and a["plan_sha256"] != b["plan_sha256"]
    assert a["tof"] == b["tof"] == {"per_reference_s": 81.5127701616477}
    assert report["comparisons"][0]["differences"] == []
    with pytest.raises(ValueError, match="manifest SHA"):
        ss.assess(path, "0" * 64)
    mat = path.parent / "point-002/runtime/result_phase25/data1.mat"
    with mat.open("ab") as stream:
        stream.write(b"altered")
    report = ss.assess(path, digest)
    assert report["classification"] == ss.UNKNOWN and "Changed native evidence" in report["blockers"][0]["reason"]


def test_rejected_pending_and_wrong_native_start(pair, monkeypatch):
    path, digest = pair
    monkeypatch.setattr(point, "launch", lambda d, e: 7)
    assert accept(path, "point-001") == "REJECTED"
    report = ss.assess(path, digest)
    assert [g["reason"] for g in report["blockers"]] == ["Expected ACCEPTED, found REJECTED",
                                                         "Expected ACCEPTED, found AWAITING_APPROVAL"]
    monkeypatch.setattr(point, "launch", lambda d, e: replay(d))
    assert accept(path, "point-002") == "ACCEPTED"
    report = ss.assess(path, digest)
    assert report["classification"] == ss.UNKNOWN and "yInits" in report["blockers"][1]["reason"]


def test_historical_point_replay():
    run = ROOT / "archive/v221_catkinas/nicu-v221-400k-001"
    if not run.is_dir():
        pytest.skip("Complete historical receipt and outputs required")
    m = ss.observe(run, PROFILE)
    assert m["native_initial"] == {"Q1_H": 0, "Q1_HNO": 0, "Q1_v": 1, "Q2_H": 0, "Q2_v": 1}
    assert m["residual"] == max(m["analysis_residual"], m["single_point_residual"]) < POLICY["max_residual"]
    assert m["single_point_residual"] == point.read(run / "result.json")["steady_state_residual"]
    assert m["tof"]["per_reference_s"] == 81.5127701616477


@pytest.mark.parametrize(("change", "expected"), [
    ("same", ss.SINGLE), ("resolved", ss.MULTIPLE), ("borderline", ss.UNKNOWN), ("flux_only", ss.UNKNOWN),
    ("network_sha256", ss.UNKNOWN), ("dataset_sha256", ss.UNKNOWN), ("fixed_config_sha256", ss.UNKNOWN),
    ("normalization", ss.UNKNOWN), ("runtime", ss.UNKNOWN), ("residual", ss.UNKNOWN), ("missing_rate", ss.UNKNOWN),
])
def test_classification_of_controlled_endpoints(pair, monkeypatch, change, expected):
    path, digest = pair
    study = ss.read(path)
    # Exercise only the decision algorithm here. Native replay is tested separately above.
    def observation(run, profile):
        index = int(run.name[-1]) - 1
        planned = study["members"][index]
        member = {k: study[k] for k in ("network_sha256", "dataset_sha256", "fixed_config_sha256", "normalization")}
        theta = 0.2
        if index and change == "resolved":
            theta = 0.8
        if index and change == "borderline":
            theta += 2e-7
        member.update(planned, execution_id=run.name, mat_sha256=ss.sha256_json(index), log_sha256=ss.sha256_json("log"), residual=0, runtime=["same"], coverage={"X": theta}, vacancy={"v": 1-theta},
                      net_rate={"r": 1}, tof={"per_reference_s": 1})
        if index and change in ("network_sha256", "dataset_sha256", "fixed_config_sha256", "runtime"):
            member[change] = "different"
        if index and change == "normalization":
            member["normalization"] = dict(member["normalization"], reference_basis="reference_site")
        if index and change == "residual":
            member["residual"] = 1
        if index and change == "flux_only":
            member["net_rate"]["r"] = 2
        if index and change == "missing_rate":
            member["net_rate"] = {}
        return member

    for member in study["members"]:
        save(path.parent / member["run"] / "ACCEPTED.json", {"fixture": True})
    monkeypatch.setattr(ss, "observe", observation)
    report = ss.assess(path, digest)
    assert report["classification"] == expected
    if change in ("resolved", "borderline", "flux_only"):
        assert report["comparisons"][0]["differences"]


def test_missing_native_initial_evidence(pair, monkeypatch):
    path, digest = pair

    def no_start(directory, executable):
        replay(directory)
        mat = directory / "result_phase25/data1.mat"
        data = {k: v for k, v in loadmat(mat).items() if not k.startswith("_") and k != "yInits"}
        savemat(mat, data)
        return 0

    monkeypatch.setattr(point, "launch", no_start)
    assert accept(path, "point-001") == "ACCEPTED"
    report = ss.assess(path, digest)
    assert report["classification"] == ss.UNKNOWN and "yInits" in report["blockers"][0]["reason"]


def test_fixed_config_excludes_only_starting_fractions():
    cfg = ss.read(C)
    baseline = ss.fixed_config(cfg)
    cfg["catkinas"]["initial_coverages"]["H2-top"] = 0.2
    assert ss.fixed_config(cfg) == baseline
    cfg["partial_pressure_bar"]["NO-g"] *= 2
    assert ss.fixed_config(cfg) != baseline


@pytest.mark.parametrize("pair", ["native_only"], indirect=True)
def test_native_only_states_with_unavailable_tof(pair):
    path, digest = pair
    for name in ("point-001", "point-002"):
        assert accept(path, name) == "ACCEPTED"
    report = ss.assess(path, digest)
    assert report["classification"] == ss.SINGLE, report["blockers"]
    Draft202012Validator(ss.read(ROOT / "configs/kinetics/mkm_steady_state_assessment.schema.json")).validate(report)
    for member in report["members"]:
        assert member["normalization"] is None and member["tof"]["per_reference_s"] is None
        assert "model-native" in member["net_rate_unit"]


def test_conservation_classes_and_nontransitive_clusters():
    step = dict(reaction_id="exchange", reactants={"A": 1}, products={"B": 1}, sites_consumed={}, sites_released={})
    network = dict(reactions=[dict(definition=step)], species=[dict(species_id=s, phase="surface") for s in "AB"])
    starts = [dict(run=k, initial_coverages={"A": a, "B": b}) for k, a, b in [("1", .2, .1), ("2", .1, .1)]]
    with pytest.raises(ValueError, match="conserved surface totals"):
        ss.compare_starts(network, starts, POLICY)
    pairs = [dict(runs=p, classification=c) for p, c in [(("a", "b"), ss.SINGLE), (("b", "c"), ss.SINGLE),
                                                         (("a", "c"), ss.MULTIPLE)]]
    assert ss.root_partition(["a", "b", "c"], pairs)["distinct_observed_roots"] is None
