"""Scientific claims, original source identity and approval boundaries across partial workflows."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from sbq123.analysis.observations.rates import directional_sources
from sbq123.analysis.observations.reactor_profiles import analyze_profile, compare_local_mkm, compare_operating_points
from sbq123.common.compat import historical_module
from sbq123.common.evidence import trust
from sbq123.common.kinetic_model.contracts import GAS_CONSTANT
from sbq123.reactor import simulate


def test_gross_traffic_keeps_exchanged_species_and_unknowns():
    reaction = dict(reactants={"A": 1, "X": 1}, products={"B": 2, "X": 1}, forward=5, reverse=4)
    values = directional_sources([reaction])
    assert values["X"] == dict(gross_production=9, gross_consumption=9)
    assert values["B"] == dict(gross_production=10, gross_consumption=8)
    assert directional_sources([dict(reaction, reverse=None)])["B"] == dict(gross_production=10, gross_consumption=None)
    assert directional_sources([dict(reaction, reverse="not_applicable")])["B"]["gross_consumption"] == 0


def case(**changes):
    params = dict(dataset_id="first-order", mode="fixed", temperature_K=400, pressure_Pa=400 * GAS_CONSTANT,
                  composition={"A": 1., "B": 0.}, volume_m3=1., inlet_mol_s=1., area_m2=1., points=3, reactant="A", product="B")
    return simulate("PFR", **(params | changes))


@pytest.mark.parametrize("variable,value", [("temperature_K", 410), ("pressure_Pa", 4000)])
def test_controlled_contrast_and_partial_outputs(variable, value):
    a = case()
    b = case(**{variable: value})
    def p(r):
        return r, r["result_sha256"]
    out = compare_operating_points(p(a), p(b), variable)
    assert out["status"] == "available"
    assert out["change"]["conversion"] == pytest.approx(b["points"][-1]["conversion"] - a["points"][-1]["conversion"])
    assert compare_operating_points(p(a), p(case(**{variable: value}, volume_m3=2)), variable)["change"] is None
    profile = analyze_profile(*p(a))
    assert profile["points"][-1]["coverage"] is None
    assert profile["points"][-1]["conversion"] > 0 and profile["coordinate_unit"] == "m"
    assert compare_local_mkm(*p(a))["differences"] is None
    forged = deepcopy(a)
    forged["points"][-1]["conversion"] = 0.1
    with pytest.raises(ValueError):
        analyze_profile(forged, p(a)[1])


def test_local_source_agrees_with_dynamic_reactor():
    r = case(dataset_id="langmuir", mode="dynamic_mkm", catalyst="analytical", catalyst_loading_kg=1,
             conversion_id="analytic-unit-site", initial_coverage=[0.5])
    comparison = compare_local_mkm(r, r["result_sha256"])
    assert comparison["status"] == "available" and len(comparison["differences"]) == len(r["points"])
    for row in comparison["differences"]:
        assert max(map(abs, row["reactor_minus_local"].values())) < 1e-12


@pytest.fixture(scope="module")
def study_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("study") / "mkm"
    source = Path(__file__).resolve().parents[2]
    subprocess.run([sys.executable, "-I", "-B", source / "tools/v32/prepare_history.py", source / "v31", "mkm", root], check=True)
    return root


def test_qualified_study_and_hypotheses(study_root, tmp_path, monkeypatch):
    # A long-lived worker may already have imported the resource owner before the study is selected.
    historical_module("mkm", "scripts.runtime_resources")
    monkeypatch.setenv("SBQ123_ROLE_DATA", str(study_root))
    historical_module("mkm", "scripts.scientific_priority.benchmark")
    from sbq123.analysis.interpretation.kinetics import interpret_sensitivity
    from sbq123.discovery.ranking.scientific_priority.exchange import follow_up_study, investigate
    data = study_root / "reports/multiphase/stage_b1_4/replay/catkinas-phase3_0.json"
    pin = sha256(data.read_bytes()).hexdigest()
    summary = investigate("mkm", data, expected_sha256=pin)
    assert summary["hypotheses"] and summary["alternative_routes"]
    assert summary["analysis"]["rate_control"] is None
    for row in summary["alternative_routes"]:
        assert sum(x["gross_fraction"] for x in row["routes"]) == pytest.approx(1)
    forged = tmp_path / "changed.json"
    altered = json.loads(data.read_bytes())
    altered["reaction_rates"][0]["net"] *= 2
    forged.write_text(json.dumps(altered))
    with pytest.raises(ValueError):
        investigate("mkm", forged, expected_sha256=sha256(forged.read_bytes()).hexdigest())
    effects = interpret_sensitivity(study_root)["direct_observations"]
    assert {r["kind"] for r in effects} == {"ts_drc", "gas_order", "intermediate_G"}
    assert next(r["value"] for r in effects if r["parameter"] == "hydrogenate") == pytest.approx(0.45025755212448)
    plan = follow_up_study(study_root, data, pin, tmp_path / "issued")
    assert plan["proposals"] and all(not p["execution_authorized"] for p in plan["proposals"])
    assert any(h["local_responses"] for h in plan["hypotheses"])
    assert {"NEB", "MLIP candidate structure generation"} <= {r["calculation"] for r in plan["deferred"]}


def test_return_requires_independent_review_and_preserves_parent(study_root, tmp_path, monkeypatch):
    monkeypatch.setenv("SBQ123_ROLE_DATA", str(study_root))
    api = historical_module("mkm", "scripts.scientific_priority.proposals")
    from sbq123.discovery.ranking.scientific_priority.returned_result import ingest
    from sbq123.discovery.ranking.scientific_priority.exchange import follow_up_study
    from scripts.artifact_io import sha256_json
    data = study_root / "reports/multiphase/stage_b1_4/replay/catkinas-phase3_0.json"
    items = follow_up_study(study_root, data, sha256(data.read_bytes()).hexdigest(), tmp_path)["proposals"]
    item = items[0]
    key = item["proposal_id"]
    api.review(tmp_path, dict(proposal_id=key, decision="approve", reviewer="synthetic test operator", reason="test owner handoff"))
    def ref(path):
        return dict(path=str(path), sha256=sha256(path.read_bytes()).hexdigest())
    def put(name, obj):
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(obj, allow_nan=False))
        return ref(path)
    parent_path = study_root / "reports/multiphase/phase3_0/closed_cycle_network.json"
    parent = json.loads(parent_path.read_bytes())
    child = deepcopy(parent)
    returned = put("measurement", dict(scope="synthetic_benchmark", datum="fixture geometry review"))
    child["source_artifacts"].append(dict(role="test_control", file="measurement.json", sha256=returned["sha256"]))
    child["network_version"] = sha256_json({k: v for k, v in child.items() if k != "network_version"})
    owner = dict(status="validated_within_scope", proposal_id=key, calculation=item["calculation"], targets=item["targets"],
                 protocol=item["protocol"], scope=item["scope_label"], result_sha256=returned["sha256"],
                 parent_network_version=parent["network_version"], successor_network_version=child["network_version"])
    review = dict(format="scientific-return-review/1", origin="archived_result", decision="accept_revision",
                  reviewer="independent synthetic reviewer", scope=item["scope_label"], proposal=ref(tmp_path / (key + ".json")),
                  ranking_sha256=item["report_sha256"], planning_decision=ref(tmp_path / "decisions" / (key + ".json")),
                  owner_validation=put("owner", owner), result=returned, parent_network=ref(parent_path), successor_network=put("child", child))
    receipt = put("review", review)
    dest = tmp_path / "networks"
    with pytest.raises(ValueError, match="independent"):
        ingest(tmp_path, receipt["path"], receipt["sha256"], dest)
    monkeypatch.setattr(trust, "DISCOVERY_RETURN_APPROVALS", frozenset({receipt["sha256"]}))
    published = ingest(tmp_path, receipt["path"], receipt["sha256"], dest)
    assert not published["execution_authorized"] and published["network_version"] == child["network_version"]
    assert ingest(tmp_path, receipt["path"], receipt["sha256"], dest) == published
    assert json.loads(parent_path.read_bytes()) == parent and published["validation"] == parent["validation_report"]
    for change, message in [({"scope": "real_catalyst"}, "scope"),
                            ({"origin": "completed_calculation"}, "execution_authorization")]:
        altered = put("changed_review", review | change)
        monkeypatch.setattr(trust, "DISCOVERY_RETURN_APPROVALS", frozenset({altered["sha256"]}))
        with pytest.raises(ValueError, match=message):
            ingest(tmp_path, altered["path"], altered["sha256"], dest)
    monkeypatch.setattr(trust, "DISCOVERY_RETURN_APPROVALS", frozenset({receipt["sha256"]}))
    put("measurement", {"forged": True})
    with pytest.raises(ValueError, match="SHA-256"):
        ingest(tmp_path, receipt["path"], receipt["sha256"], dest)
