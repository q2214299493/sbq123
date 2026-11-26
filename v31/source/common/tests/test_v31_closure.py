"""Release boundaries across the two qualified rate families and optional balance."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file, sha256_json
from scripts.kinetic_data.observations import rate_observation
from scripts.neb_agent.utils_structure import Poscar
from scripts.reactor_balance import balance_observation
from scripts.scientific_interpretation import interpret_observation
from scripts.scientific_priority.proposals import proposals_for_observation, verify
from scripts.scientific_priority.structure_binding import endpoint_records
from test_v31_architecture import NETWORK, fixture_authority, operating_point  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def observation(case):
    path = ROOT / "reports/multiphase/stage_b1_4/replay" / (case + ".json")
    data = json.loads(path.read_bytes())
    return rate_observation(data, ROOT / data["provenance"]["network"]["path"], conditions=data["conditions"],
                            target=data["native_normalization"], rate_evidence={"path": path, "sha256": sha256_file(path)})


@pytest.mark.parametrize(("case", "kind"), [("catkinas-phase3_0", "mkm_local_source"), ("zacros-mono", "kmc_sampled_source")])
def test_signed_sources_by_engine(case, kind):
    result = observation(case)
    description = interpret_observation(result, expected_sha256=result["observation_sha256"])
    assert description["kind"] == kind and description["values"] and description["result_sha256"]
    assert description["evidence_scope"] == "archived_software_benchmark"
    expected = result["observation_sha256"]
    result["conditions"]["temperature_K"] += 1
    result["observation_sha256"] = sha256_json({k: v for k, v in result.items() if k != "observation_sha256"})
    with pytest.raises(ValueError, match="expected calculation"):
        interpret_observation(result, expected_sha256=expected)


@pytest.mark.usefixtures("fixture_authority")
def test_optional_balance_observation(tmp_path):
    data, args = operating_point(tmp_path)
    result = balance_observation(data, NETWORK, **args)
    assert result["kind"] == "instantaneous_gas_balance"
    assert result["values"]["accumulation_mol_s"]["H2-g"] == pytest.approx(-489.07662096988616)
    args["rate_evidence"] = None
    assert balance_observation(data, NETWORK, **args)["accumulation_mol_s"] is None


def planning_inputs():
    point = observation("catkinas-phase3_0")
    scope = dict(network_version=point["network_version"], dataset_version=point["dataset_version"],
                 baseline_result_sha256=point["result_sha256"], temperature_K=400, normalization=point["basis"],
                 feed_bar={"H2-g": 1, "HNO-g": .1, "NO-g": .5})
    obj = dict(kind="overall_activity", id="inspect-source", observable="local-source", scope=scope,
               weights={"evidence_deficiency": 1}, scales={"evidence_deficiency": 1}, cost_unit="CPUh")
    row = next(r for r in json.loads(NETWORK.read_bytes())["reactions"] if r["definition"]["reaction_id"] == "ads")
    reaction = row["definition"]
    endpoints = endpoint_records(row, "forward")
    candidates = []
    for need in ("minimum_geometry", "reaction_path", "candidate_geometry"):
        c = dict(id=need, need=need, scope=scope, parent_run_id=point["run_id"], scope_label="synthetic_benchmark",
                 structures=deepcopy(endpoints), reaction_structures={"ads": deepcopy(endpoints)}, parameter="geometry", parameter_type="structure", reaction_family=reaction["reaction_type"],
                 targets={state: sha256_json(endpoints[state]) for state in ("IS", "FS")}, protocol="fixture", reaction_ids=["ads"],
                 species_ids=["H2-g"], phase_ids=reaction["phase_ids"], site_context=reaction["required_sites"],
                 interface_id=reaction["interface_id"],
                 strategy={"reaction_family": reaction["reaction_type"], "status": "NEEDS_GPU_PATH_OR_VASP_PATH_REVIEW",
                           "source_sha256": "3"*64, "automatic_submission": False})
        candidates.append(c)
    data = dict(candidates=candidates, metrics=[], reliability=[], evidence=[], inventory_source="fixture",
                sources={"fixture": "synthetic planning control"})
    return point, obj, data


def test_followup_uses_evidence_scope_and_existing_review(tmp_path):
    point, obj, data = planning_inputs()
    candidates = data["candidates"]
    records = proposals_for_observation(point, expected_sha256=point["observation_sha256"], data=data,
                                       objective=obj, directory=tmp_path)
    assert {r["candidate_id"] for r in records} == {c["id"] for c in candidates}
    for row in records:
        verify(row, directory=tmp_path)
        report = json.loads((tmp_path/"reports"/(row["report_sha256"]+".json")).read_bytes())
        assert sha256_json(report) == row["report_sha256"]
        assert report["interpretation"]["observation_sha256"] == point["observation_sha256"]
        assert row["review_required"] and not row["execution_authorized"]
    obj["scope"] = dict(obj["scope"], temperature_K=401)
    with pytest.raises(ValueError, match="observed model"):
        proposals_for_observation(point, expected_sha256=point["observation_sha256"], data=data,
                                  objective=obj, directory=tmp_path)


@pytest.mark.parametrize("counts", [[], [2, 1]])
def test_atom_count_pairing_rejects_mismatch(counts):
    structure = Poscar("fixture", None, ["Ni"], counts, None, False, [])
    with pytest.raises(ValueError):
        _ = structure.labels


def test_qualification_profile_is_optional():
    from scripts.baseline_mkm.drc_report import qualification_context
    assert qualification_context(None) == {}
    context = qualification_context("configs/kinetics/nicu_drc_report_context.json")
    assert context["fe110"]["drc"] is None and context["fe110"]["gaps"]


@pytest.mark.parametrize("fault", ["parent_and_reaction", "parent", "absent_reaction", "unrelated_species",
                                   "phase", "scope", "self_rehashed_observation"])
def test_planning_requires_related_approved_evidence(tmp_path, fault):
    point, objective, packet = planning_inputs()
    for c in packet["candidates"]:
        if fault in ("parent_and_reaction", "parent"):
            c["parent_run_id"] = "audit-independent-other-run"
        if fault in ("parent_and_reaction", "absent_reaction"):
            c["reaction_ids"] = ["audit-reaction-absent-from-network"]
        if fault == "unrelated_species":
            c["reaction_ids"] = ["desorb"]  # Genuine network step with no H2-g contribution.
        if fault == "phase":
            c["phase_ids"] = ["unobserved phase"]
        if fault == "scope":
            c["scope_label"] = "project"
    if fault == "self_rehashed_observation":
        point["values"]["H2-g"]["value"] *= 2
        point["observation_sha256"] = sha256_json({k: v for k, v in point.items() if k != "observation_sha256"})
    with pytest.raises(ValueError):
        proposals_for_observation(point, expected_sha256=point["observation_sha256"],
                                  data=packet, objective=objective, directory=tmp_path)
    assert not list(tmp_path.iterdir())


def test_observed_proposals_isolate_inputs_and_recheck_links(tmp_path):
    point, objective, packet = planning_inputs()
    pin = point["observation_sha256"]
    records = proposals_for_observation(point, expected_sha256=pin, data=packet, objective=objective, directory=tmp_path)
    before = json.dumps(records, sort_keys=True)
    objective["scope"]["temperature_K"] = 401
    packet["candidates"][0]["targets"]["IS"] = "9" * 64
    packet["candidates"][0]["reaction_ids"].append("unrelated")
    point["values"].clear()
    assert json.dumps(records, sort_keys=True) == before
    for item in records:
        assert item == json.loads((tmp_path / (item["proposal_id"] + ".json")).read_bytes())
        verify(item, directory=tmp_path, expected_observation_sha256=pin)
        wrong = deepcopy(item)
        wrong["reaction_ids"] = ["desorb"]
        wrong["proposal_id"] = sha256_json({k: v for k, v in wrong.items() if k != "proposal_id"})
        with pytest.raises(ValueError, match="no measured net contribution"):
            verify(wrong, directory=tmp_path, expected_observation_sha256=pin)


def test_comparison_interpretation_owns_nested_values():
    from scripts.scientific_interpretation import summarize_comparison

    record = dict(format="mkm-kmc-comparison-result/1", interpretation="bounded", uncertainty={"interval": [0, 1]},
                  comparisons=[dict(observable={"kind": "coverage"}, compatibility="comparable",
                                    difference={"signed": 1}, reasons=["initial"])])
    record["comparison_sha256"] = sha256_json(record)
    result = summarize_comparison(record)
    before = json.dumps(result, sort_keys=True)
    record["uncertainty"]["interval"].append(2)
    record["comparisons"][0]["reasons"].clear()
    record["comparisons"][0]["difference"]["signed"] = 2
    record["comparisons"][0]["observable"]["kind"] = "OTHER"
    assert json.dumps(result, sort_keys=True) == before
    assert result["comparison_sha256"] == record["comparison_sha256"]


def _rehash(proposal):
    proposal["proposal_id"] = sha256_json({k: v for k, v in proposal.items() if k != "proposal_id"})


def _change_endpoint(candidate, fault):
    refs = candidate["reaction_structures"]["ads"]
    if fault in ("IS", "TS", "FS"):
        refs[fault]["id"] = "fixture-" + fault.lower() + "-desorb"
    elif fault == "full":
        for state in refs:
            refs[state]["id"] = candidate["structures"][state]["id"] = "fixture-" + state.lower() + "-desorb"
    elif fault == "selector":
        refs["IS"]["selector"]["reaction_id"] = "desorb"
    elif fault == "record":
        refs["TS"]["record_sha256"] = "0" * 64
    elif fault == "target":
        candidate["targets"]["IS"] = "0" * 64
    elif fault == "site_geometry":
        candidate["site_geometry"] = {"site_ids": ["top-Ni"], "neighbors_zero_based": [], "initial": [None], "final": [None]}
    else:
        candidate["direction"] = "reverse"


@pytest.mark.parametrize("fault", ["IS", "TS", "FS", "full", "selector", "record", "target", "direction", "site_geometry"])
def test_originating_structure_controls(tmp_path, fault):
    point, objective, data = planning_inputs()
    pin = point["observation_sha256"]
    for candidate in data["candidates"]:
        packet = dict(data, candidates=[deepcopy(candidate)])
        destination = tmp_path / candidate["id"]
        item, = proposals_for_observation(point, expected_sha256=pin, data=packet, objective=objective, directory=destination)
        verify(item, directory=destination, expected_observation_sha256=pin)
        _change_endpoint(packet["candidates"][0], fault)
        with pytest.raises(ValueError):
            proposals_for_observation(point, expected_sha256=pin, data=packet, objective=objective, directory=destination/"invalid")
        assert not (destination/"invalid").exists()
        _change_endpoint(item, fault)
        _rehash(item)
        with pytest.raises(ValueError):
            verify(item, directory=destination, expected_observation_sha256=pin)


def test_structure_hypotheses_and_reverse(tmp_path):
    point, objective, packet = planning_inputs()
    for c in packet["candidates"]:
        c["direction"] = "reverse"
        for roles in [c["structures"], c["reaction_structures"]["ads"]]:
            roles["FS"], roles["IS"] = roles["IS"], roles["FS"]
        c["targets"]["FS"], c["targets"]["IS"] = c["targets"]["IS"], c["targets"]["FS"]
    pin = point["observation_sha256"]
    items = proposals_for_observation(point, expected_sha256=pin, data=packet, objective=objective, directory=tmp_path/"reverse")
    assert len(items) == 3
    for item in items:
        verify(item, directory=tmp_path/"reverse")
    for c in packet["candidates"]:
        c["structure_status"] = "unverified_hypothesis"
        c["structures"]["IS"] = {"id": "new-trial-geometry"}
    assert proposals_for_observation(point, expected_sha256=pin, data=packet, objective=objective, directory=tmp_path/"new") == []
    report = json.loads(next((tmp_path/"new/reports").glob("*.json")).read_bytes())
    assert len(report["deferred"]) == 3
    assert all(r["score"] is None and "hypothesis" in str(r["reasons"]) for r in report["deferred"])


@pytest.mark.parametrize("fault", ["score", "rank", "reasons", "rationale", "report_hash", "no_reference", "other_report",
                                   "report_row", "report_inputs", "report_explanation", "whitespace", "missing_report"])
def test_originating_report_controls(tmp_path, fault):
    from scripts.scientific_priority.proposals import proposals
    point, objective, data = planning_inputs()
    pin = point["observation_sha256"]
    items = proposals_for_observation(point, expected_sha256=pin, data=data, objective=objective, directory=tmp_path)
    origin = next((tmp_path/"reports").glob("*.json"))
    report = json.loads(origin.read_bytes())
    newer = proposals_for_observation(point, expected_sha256=pin, data=data, objective=dict(objective, id="second"),
                                      directory=tmp_path)
    if fault.startswith("report_") and fault != "report_hash":
        if fault == "report_row":
            report["ranked"][0]["score"] += .25
        elif fault == "report_inputs":
            report["ranking_inputs"]["candidates"][0]["protocol"] = "changed"
        else:
            report["ranked"][0]["rationale"] += " changed"
        with pytest.raises(ValueError):
            proposals(report, tmp_path/"modified")
        origin.write_text(json.dumps(report), encoding="utf8")
    if fault == "whitespace":
        origin.write_bytes(origin.read_bytes() + b" ")
    if fault == "missing_report":
        # A separate verifier store with the original issuance and no ranking report.
        import shutil
        shutil.copytree(tmp_path/"issued", tmp_path/"partial/issued")
    for raw in items:
        item = deepcopy(raw)
        if fault == "score":
            assert item["score"] == 1.0
            item["score"] = 1.25
        elif fault == "rank":
            item["rank"] += 1
        elif fault == "reasons":
            item["reasons"].append("changed")
        elif fault == "rationale":
            item["rationale"] += " changed"
        elif fault == "report_hash":
            item["report_sha256"] = "0"*64
        elif fault == "other_report":
            item["report_sha256"] = newer[0]["report_sha256"]
        elif fault == "no_reference":
            del item["report_sha256"]
        _rehash(item)
        directory = tmp_path/"partial" if fault == "missing_report" else tmp_path
        with pytest.raises(ValueError):
            verify(item, directory=directory, expected_observation_sha256=pin)


def _ads_event():
    rates = json.loads(Path("reports/multiphase/stage_b1_4/replay/catkinas-phase3_0.json").read_bytes())
    ref = rates["provenance"]["dataset"]
    assert sha256_file(Path(ref["path"])) == ref["sha256"]
    dataset = json.loads(Path(ref["path"]).read_bytes())
    model, = [r["model"] for r in dataset["reactions"] if r["reaction_id"] == "ads"]
    return model["local_event"]


def _issue(point, objective, packet, folder):
    return proposals_for_observation(point, expected_sha256=point["observation_sha256"], data=packet,
                                     objective=objective, directory=folder)


@pytest.mark.parametrize("case", ["forward", "reverse", "unknown_site", "additional_vacancy", "occupied_neighbor",
                                   "deferred_environment", "false_multiplicity"])
def test_local_event_evidence_at_both_boundaries(tmp_path, case):
    point, objective, packet = planning_inputs()
    event = _ads_event()
    if case == "reverse":
        event["initial"], event["final"] = event["final"], event["initial"]
        for c in packet["candidates"]:
            c["direction"] = "reverse"
            for mapping in (c["targets"], c["structures"], c["reaction_structures"]["ads"]):
                mapping["IS"], mapping["FS"] = mapping["FS"], mapping["IS"]
    elif case == "false_multiplicity":
        event["patterns_per_reference_site"]["forward"] += 1
    elif case != "forward":
        site = "unknown" if case == "unknown_site" else "top-Ni"
        state = [["H2-top", 1]] if case == "occupied_neighbor" else [None]
        event["environment"] = dict(site_ids=[site], state=state, neighbors_zero_based=[[1, 2]])
    for c in packet["candidates"]:
        c["event_geometry"] = deepcopy(event)
        if case == "deferred_environment":
            c["structure_status"] = "unverified_hypothesis"
    if case in ("forward", "reverse"):
        issued = _issue(point, objective, packet, tmp_path)
        assert len(issued) == 3
        for p in issued:
            verify(json.loads((tmp_path/(p["proposal_id"]+".json")).read_bytes()), directory=tmp_path)
        return
    if case == "deferred_environment":
        assert _issue(point, objective, packet, tmp_path) == []
        report = json.loads(next((tmp_path/"reports").glob("*.json")).read_bytes())
        assert len(report["deferred"]) == 3 and all(row["score"] is None for row in report["deferred"])
        assert not (tmp_path/"issued").exists()
        return
    with pytest.raises(ValueError, match="approved (catalog|local event)"):
        _issue(point, objective, packet, tmp_path/"invalid")
    assert not (tmp_path/"invalid").exists()
    for c in packet["candidates"]:
        c["event_geometry"] = _ads_event()
    for item in _issue(point, objective, packet, tmp_path/"good"):
        item["event_geometry"] = event
        _rehash(item)
        with pytest.raises(ValueError, match="approved (catalog|local event)"):
            verify(item, directory=tmp_path/"good")


def test_approved_occupied_environment_must_be_preserved(monkeypatch, tmp_path):
    from scripts.scientific_priority import structure_binding

    point, objective, packet = planning_inputs()
    approved = _ads_event()
    approved["environment"] = dict(site_ids=["top-Ni"], state=[["H2-top", 1]], neighbors_zero_based=[[1, 2]])
    # A scoped test model for the occupied-neighbor case absent in the archived Ni/Cu control.
    monkeypatch.setattr(structure_binding, "reviewed_event", lambda *args: deepcopy(approved))
    for c in packet["candidates"]:
        c["event_geometry"] = deepcopy(approved)
    items = _issue(point, objective, packet, tmp_path/"ok")
    assert len(items) == 3
    for p in items:
        verify(p, directory=tmp_path/"ok")
    for case in ("absent", "vacant", "edge"):
        for c in packet["candidates"]:
            c["event_geometry"] = deepcopy(approved)
            if case == "absent":
                del c["event_geometry"]["environment"]
            elif case == "vacant":
                c["event_geometry"]["environment"]["state"] = [None]
            else:
                c["event_geometry"]["environment"]["neighbors_zero_based"] = [[0, 2]]
        with pytest.raises(ValueError, match="approved local event"):
            _issue(point, objective, packet, tmp_path/case)


@pytest.mark.parametrize("case", ["null", "missing", "true", "false", "float", "string", "zero", "negative", "wrong"])
def test_current_issued_rank_is_strict_and_bound(tmp_path, case):
    point, objective, packet = planning_inputs()
    items = _issue(point, objective, packet, tmp_path)
    for item in items:
        receipt = tmp_path/"issued"/(item["proposal_id"]+".json")
        data = json.loads(receipt.read_bytes())
        rank = data["rank"]
        if case == "missing":
            del data["rank"]
        else:
            data["rank"] = {"null": None, "true": True, "false": False, "float": float(rank), "string": str(rank),
                            "zero": 0, "negative": -1, "wrong": rank+1}[case]
        receipt.write_text(json.dumps(data), encoding="utf8")
        with pytest.raises(ValueError):
            verify(item, directory=tmp_path, expected_report_sha256=item["report_sha256"])
    with pytest.raises(ValueError, match="Immutable evidence conflict"):
        _issue(point, objective, packet, tmp_path)


@pytest.mark.parametrize("schema", [None, "unknown", "scientific-priority/2", "scientific-priority/1"])
def test_historical_schema_and_independent_report_pin(tmp_path, schema):
    from scripts.scientific_priority.proposals import _proposal

    point, obj, packet = planning_inputs()
    first = _issue(point, obj, packet, tmp_path/"current")[0]
    report = json.loads((tmp_path/"current/reports"/(first["report_sha256"]+".json")).read_bytes())
    # Format-conformance fixture only. Actual retained historical evidence is replayed separately.
    del report["ranking_inputs"]
    if schema is None:
        del report["format"]
    else:
        report["format"] = schema
    pin = sha256_json(report)
    directory = tmp_path/"archive"
    (directory/"reports").mkdir(parents=True)
    (directory/"reports"/(pin+".json")).write_text(json.dumps(report), encoding="utf8")
    item = _proposal(report, report["ranked"][0], 1, pin)
    with pytest.raises(ValueError):
        verify(item, directory=directory)
    if schema == "scientific-priority/1":
        verify(item, directory=directory, expected_report_sha256=pin)
    else:
        with pytest.raises(ValueError):
            verify(item, directory=directory, expected_report_sha256=pin)


_OMIT_GEOMETRY_FIELD = object()


@pytest.mark.parametrize(("path", "value"), [
    pytest.param(("final", 0, 1), True, id="entity-bool"),
    pytest.param(("final", 0, 1), 1.0, id="entity-float"),
    pytest.param(("final", 0, 1), 0, id="entity-zero"),
    pytest.param(("final", 0, 0), "unregistered-species", id="unknown-species"),
    pytest.param(("neighbors_zero_based", 0, 1), True, id="edge-bool"),
    pytest.param(("neighbors_zero_based", 0, 1), 1.0, id="edge-float"),
    pytest.param(("neighbors_zero_based", 0, 1), 2, id="edge-range"),
    pytest.param(("neighbors_zero_based",), [[0, 1], [1, 0]], id="duplicate-edge"),
    pytest.param(("neighbors_zero_based",), _OMIT_GEOMETRY_FIELD, id="missing-required-field"),
    pytest.param(("neighbours",), [], id="unknown-field"),
    pytest.param(("environment",), dict(site_ids=["top-Ni"], state=[None], neighbors_zero_based=[[1, 2]],
                                       extra="unknown"), id="unknown-environment-field"),
    pytest.param(("environment",), dict(site_ids=["top-Ni"], neighbors_zero_based=[[1, 2]]),
                 id="missing-environment-state"),
    pytest.param(("site_ids", 0), 1, id="invalid-site-id"),
    pytest.param((), None, id="null-declaration"),
    pytest.param(("patterns_per_reference_site", "forward"), True, id="pattern-bool"),
    pytest.param(("patterns_per_reference_site", "forward"), "2", id="pattern-text"),
    pytest.param(("patterns_per_reference_site", "forward"), float("nan"), id="pattern-nan"),
    pytest.param(("patterns_per_reference_site", "reversed"), 2, id="unknown-pattern-key"),
    pytest.param(("forward_proximity_factor",), False, id="proximity-bool"),
    pytest.param(("energetics_sha256",), 1, id="digest-type"),
    pytest.param(("coefficient_basis",), None, id="basis-type"),
    pytest.param(("patterns_per_reference_site", "forward"), 2.0, id="different-numeric-representation"),
    pytest.param(("patterns_per_reference_site",), _OMIT_GEOMETRY_FIELD, id="different-valid-declarations"),
])
def test_geometry_alias_types_at_public_boundaries(tmp_path, path, value):
    point, objective, packet = planning_inputs()
    candidate = packet["candidates"][0]
    packet["candidates"] = [candidate]
    geometry = _ads_event()
    candidate["event_geometry"] = deepcopy(geometry)
    original, = _issue(point, objective, packet, tmp_path/"original")
    claim = deepcopy(geometry)
    if path:
        parent = claim
        for key in path[:-1]:
            parent = parent[key]
        if value is _OMIT_GEOMETRY_FIELD:
            del parent[path[-1]]
        else:
            parent[path[-1]] = value
    else:
        claim = value
    # Check both field orderings. Hypotheses must also pass the typed declaration boundary.
    for name, other in (("event_geometry", "site_geometry"), ("site_geometry", "event_geometry")):
        candidate[name], candidate[other] = claim, geometry
        candidate["structure_status"] = "unverified_hypothesis"
        with pytest.raises(ValueError):
            _issue(point, objective, packet, tmp_path/name)
        assert not (tmp_path/name).exists()
        altered = deepcopy(original)
        altered[name], altered[other] = claim, geometry
        _rehash(altered)
        with pytest.raises(ValueError):
            verify(altered, directory=tmp_path/"original", expected_report_sha256=original["report_sha256"])


@pytest.mark.parametrize("shape", ["event", "site", "both"])
def test_valid_geometry_field_forms_roundtrip(tmp_path, shape):
    point, objective, packet = planning_inputs()
    event = _ads_event()
    for candidate in packet["candidates"]:
        if shape != "site":
            candidate["event_geometry"] = deepcopy(event)
        if shape != "event":
            candidate["site_geometry"] = dict(reversed(list(event.items())))
    items = _issue(point, objective, packet, tmp_path)
    assert len(items) == 3
    for p in items:
        saved = json.loads((tmp_path/(p["proposal_id"]+".json")).read_bytes())
        assert saved["score"] == 1.0
        verify(saved, directory=tmp_path, expected_observation_sha256=point["observation_sha256"])
