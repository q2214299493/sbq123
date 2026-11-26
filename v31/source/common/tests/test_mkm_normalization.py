"""Offline denominator contracts and normal single-point entry points with an inert MAT replay."""
from copy import deepcopy

import pytest

from scripts.artifact_io import load_json_object as read, sha256_file, sha256_json, write_json_exclusive as save
from scripts.baseline_mkm import single_point as flow
from scripts.baseline_mkm.analysis import analyze
from scripts.baseline_mkm.network_mapping import map_network
from scripts.baseline_mkm.normalization import NATIVE_RATE_UNIT, individual_rate, normalization, reference_rate
from scripts.baseline_mkm.rate_adapter import adapt
from scripts.baseline_mkm.registration import registry_batch
from scripts.kinetic_data.project_inspection import inspect_project
from scripts.kinetic_parameters.engine import generate
from scripts.rate_output_v2 import validate_network_bound_rate_output
from test_kinetic_parameters import signed
from test_mkm_single_point import OUT, PHASE, approved, replay, runtime  # noqa: F401


def definition(kind, counts, magnitude=1):
    unit = {"reference_site": "site", "reference_site_pair": "site pair", "other": "surface ensemble"}[kind]
    return dict(reference_basis=kind, reference_id="fixture-unit", denominator_value=magnitude,
                denominator_unit=unit, sites_per_reference=counts, inventory_ids=sorted(counts),
                extent_unit="event", time_unit="s")


def bind_fixture(tmp_path, net, declaration):
    evidence = save(tmp_path / "reviewed.json", {"normalization": declaration})
    source = dict(path=evidence.name, sha256=sha256_file(evidence))
    net["source_artifacts"].append(dict(role="verified_evidence", file=evidence.name, sha256=source["sha256"]))
    net["network_version"] = sha256_json({k: v for k, v in net.items() if k != "network_version"})
    return save(tmp_path / "profile.json", dict(network_version=net["network_version"], source=source))


@pytest.mark.parametrize(("kind", "counts", "magnitude", "raw", "unit_rate", "mean"), [
    ("reference_site", {"Fe110-bridge": 1}, 1, 36, 36, 36),
    ("reference_site_pair", {"Ni-top": 1, "Cu-bridge": 1}, 1, 81.5127701616477, 81.5127701616477, 40.75638508082385),
    ("reference_site_pair", {"Fe110-bridge": 2}, 3, 36, 12, 6),
    ("other", {"metal-top": 1, "oxide-bridge": 1, "interface": 1}, 4, 36, 9, 3),
    ("other", {"metal-top": 2, "oxide-bridge": 4, "interface": 3}, 2, 36, 18, 2),
])
def test_reviewed_physical_unit(tmp_path, kind, counts, magnitude, raw, unit_rate, mean):
    net = {"catalog": {"sites": [{"site_id": sid} for sid in counts]}, "source_artifacts": []}
    path = bind_fixture(tmp_path, net, definition(kind, counts, magnitude))
    ref = normalization(path, net, {"turnover_basis": kind})
    assert (ref["network_version"], ref["evidence_sha256"]) == (net["network_version"], sha256_file(tmp_path / "reviewed.json"))
    assert ref["sites_per_reference"] == counts and ref["denominator_value"] == magnitude
    assert reference_rate(raw, ref) == unit_rate and individual_rate(unit_rate, ref) == mean


@pytest.mark.parametrize("defect", ["network", "not_reviewed", "hash", "label", "count", "bool", "zero",
                                    "fraction", "unknown_inventory", "duplicate_id", "time", "extent", "unit",
                                    "zero_denominator", "string_denominator", "missing_id", "missing_source_definition"])
def test_invalid_physical_contract(tmp_path, defect):
    net = {"catalog": {"sites": [{"site_id": "a"}]}, "source_artifacts": []}
    d = definition("reference_site", {"a": 1})
    if defect == "label":
        d["reference_basis"] = "reference_site_pair"
    elif defect in ("count", "bool", "zero", "fraction"):
        d["sites_per_reference"]["a"] = {"count": 2, "bool": True, "zero": 0, "fraction": 0.5}[defect]
    elif defect in ("duplicate_id", "unknown_inventory"):
        d["inventory_ids"] = ["a", "a"] if defect == "duplicate_id" else ["b"]
    elif defect in ("time", "extent", "unit", "zero_denominator", "string_denominator"):
        key, value = {"time": ("time_unit", "days"), "extent": ("extent_unit", "mol"),
                      "unit": ("denominator_unit", "kg"), "zero_denominator": ("denominator_value", 0),
                      "string_denominator": ("denominator_value", "2")}[defect]
        d[key] = value
    elif defect == "missing_id":
        del d["reference_id"]
    elif defect == "missing_source_definition":
        d = {}
    path = bind_fixture(tmp_path, net, d)
    if defect == "hash":
        (tmp_path / "reviewed.json").write_bytes(b"changed")
    elif defect == "network":
        net["network_version"] = "0" * 64
    elif defect == "not_reviewed":
        net["source_artifacts"][0]["role"] = "input"
    with pytest.raises(ValueError):
        normalization(path, net)


def replayed_point(tmp_path, runtime, monkeypatch, kind):  # noqa: F811
    # Keep archived bytes immutable. A different reference is reviewed only for this synthetic fixture.
    net = read(PHASE / "closed_cycle_network.json")
    dataset = read(OUT / "cycle_dataset.json")
    cfg = read(PHASE / "workflow_configuration.json")
    del cfg["turnover_basis"]
    profile = None
    if kind:
        counts = {"reference_site": {"top-Ni": 1}, "reference_site_pair": {"bridge-Cu": 1, "top-Ni": 1},
                  "other": {"bridge-Cu": 2, "top-Ni": 3}}[kind]
        profile = bind_fixture(tmp_path, net, definition(kind, counts, 2))
        models = []
        for row in dataset["reactions"]:
            model = deepcopy(row["model"])
            del model["scientific_review"]
            models.extend(signed(net, model)["models"])
        dataset = generate(net, {"network_version": net["network_version"], "models": models})
        cfg.update(turnover_basis=kind, dataset_version=dataset["dataset_version"])
    source = [save(tmp_path / (k + ".json"), v) for k, v in (("n", net), ("d", dataset), ("c", cfg))]
    run = tmp_path / "run"
    files, mapping = map_network(net, dataset, cfg, normalization_path=profile)
    assert files and mapping["physical_tof_eligibility"] == ("eligible" if kind else "unavailable")
    view = flow.prepare(run, *source, *runtime, tmp_path / "inert", normalization_path=profile)
    assert view["stage"] == "AWAITING_APPROVAL", view.get("missing_data")
    monkeypatch.setattr(flow, "launch", lambda folder, executable: replay(folder))
    assert flow.execute(run, approved(tmp_path))["stage"] == "ACCEPTED"
    return source, run, profile


@pytest.mark.parametrize("kind", [None, "reference_site", "other"])
def test_prepare_replay_analysis_and_adapter(tmp_path, runtime, monkeypatch, kind):  # noqa: F811
    source, run, profile = replayed_point(tmp_path, runtime, monkeypatch, kind)
    receipt, result = flow.accepted_receipt(run), read(run / "result.json")
    raw = result["overall_rate"]
    assert raw == 81.5127701616477 and len(result["reactions"]) == 4
    a = analyze(*source, run / "result.json", receipt)
    assert len(a["coverage"]) == 3 and len(a["rates"]["reactions"]) == 4
    rows = registry_batch(run, "fixture reviewer")["rows"]["results"]
    if kind is None:
        assert result["normalization"] is result["tof_s_inverse"] is result["turnover_basis"] is None
        assert result["physical_tof_status"] == "unavailable" and result["flux_unit"] == NATIVE_RATE_UNIT
        assert a["tof"]["extent_per_reference_s"] is a["tof"]["overall"]["per_site_s"] is None
        assert a["tof"]["model_native_extent"] == pytest.approx(raw)
        assert [r["unit"] for r in rows] == [NATIVE_RATE_UNIT]
        return
    expected = raw / 2
    assert result["normalization"]["reference_basis"] == kind and result["tof_s_inverse"] == expected
    assert result["mean_tof_per_individual_site_s"] == pytest.approx(expected / (1 if kind == "reference_site" else 5))
    assert a["tof"]["overall"]["per_reference_s"] == pytest.approx(expected)
    assert a["tof"]["overall"]["per_site_pair_s"] is None and a["native_reference"] == result["normalization"]
    tof_row = next(row for row in rows if row["result_name"] == "tof_s_inverse")
    assert tof_row["numeric_value"] == expected
    assert tof_row["reference_convention"] == "fixture-unit"
    assert tof_row["unit"] == f"events per {result['normalization']['denominator_unit']} per second"
    payload, qual = adapt(run / "ACCEPTED.json", network_path=source[0], dataset_path=source[1], config_path=source[2],
                          input_path=run / "input" / flow.INPUT, normalization_path=profile, root=tmp_path)
    validate_network_bound_rate_output(payload, source[0])
    basis = payload["native_normalization"]
    assert basis["basis_kind"] == kind and basis["denominator_value"] == 2
    assert qual["overall_turnover_per_reference_s"] == expected and "overall_turnover_per_pair_s" not in qual
    if kind == "other":
        assert basis["basis_evidence"]["sha256"] == result["normalization"]["evidence_sha256"]


def test_physical_request_without_evidence_preserves_native_input_eligibility(tmp_path, runtime):  # noqa: F811
    net, data, cfg = PHASE / "closed_cycle_network.json", OUT / "cycle_dataset.json", PHASE / "workflow_configuration.json"
    view = flow.prepare(tmp_path / "point", net, data, cfg, *runtime, tmp_path / "inert")
    assert view["stage"] == "REJECTED" and view["native_input_eligibility"] == "eligible"
    assert "requested physical TOF" in view["missing_data"]
    assert view["execution"] == "not_started"


def test_legacy_singular_request_cannot_authorize_a_new_pair(tmp_path):
    net = {"catalog": {"sites": [{"site_id": "a"}]}, "source_artifacts": []}
    path = bind_fixture(tmp_path, net, definition("reference_site_pair", {"a": 2}))
    with pytest.raises(ValueError):
        normalization(path, net, {"turnover_basis": "one_event_per_reference_site"})


def inspect_tof(root, project_id, sources):
    refs = {k: {"path": p.relative_to(root).as_posix(), "sha256": sha256_file(p)} for k, p in sources.items()}
    project = save(root / "project.json", {"version": 1, "project_id": project_id, "evidence_base": "."})
    task = save(root / "task.json", {"task_id": "inspect", "requested_observables": ["tof"], "sources": refs})
    return inspect_project(project, task)["contexts"][0]["observables"]["tof"]


@pytest.mark.parametrize("legacy", [False, True], ids=["bound-result", "legacy-result"])
@pytest.mark.parametrize("change", ["valid", "missing", "wrong_hash", "changed_counts", "reference_id",
                                    "denominator_value", "denominator_unit", "inventory_ids"])
def test_inspected_custom_tof(tmp_path, runtime, monkeypatch, legacy, change):  # noqa: F811
    source, run, profile = replayed_point(tmp_path, runtime, monkeypatch, "other")
    network, dataset, config = source
    receipt, result = flow.accepted_receipt(run), read(run / "result.json")
    rates, qual = adapt(run / "ACCEPTED.json", network_path=network, dataset_path=dataset,
                        config_path=config, input_path=run / "input" / flow.INPUT,
                        normalization_path=profile, root=tmp_path)
    expected = result["tof_s_inverse"]
    if legacy:
        del result["normalization"], receipt["normalization"]
        result["tof_s_inverse"] = result["overall_rate"]
    result_path = save(tmp_path / "result.json", result)
    receipt["result_sha256"] = sha256_file(result_path)
    receipt_path = save(tmp_path / "receipt.json", receipt)
    qual["receipt"]["sha256"] = sha256_file(receipt_path)
    qual["result_record"]["sha256"] = sha256_file(result_path)
    native = rates["native_normalization"]
    if change == "missing":
        del native["basis_evidence"]
    elif change == "wrong_hash":
        native["basis_evidence"]["sha256"] = "0" * 64
    elif change == "changed_counts":
        # Same reference ID, unit, inventory IDs and total sites. Only their distribution changes.
        alternative = read(tmp_path / "reviewed.json")
        alternative["normalization"]["sites_per_reference"] = {"bridge-Cu": 3, "top-Ni": 2}
        path = save(tmp_path / "other-counts.json", alternative)
        native["basis_evidence"] = {"path": path.name, "sha256": sha256_file(path)}
    elif change != "valid":
        native[change] = {"reference_id": "another-unit", "denominator_value": 3,
                          "denominator_unit": "another ensemble", "inventory_ids": ["top-Ni"]}[change]
    # Rebind the envelope and manifest so the TOF check has to compare the two physical definitions.
    del rates["output_binding"]["dataset_id"]
    rates["output_binding"]["dataset_id"] = "rates-" + sha256_json(rates)
    sources = dict(network=network, dataset=dataset, configuration=config, result=result_path, mkm_receipt=receipt_path,
                   rates=save(tmp_path / "rates.json", rates),
                   qualification=save(tmp_path / "qualification.json", {"point": qual}))
    obs = inspect_tof(tmp_path, receipt["catalyst_project_id"], sources)
    if change == "valid":
        assert obs["status"] == "available", obs
        assert obs["value"]["value"] == expected
    else:
        assert obs["status"] == "invalid_reference" and obs["value"] is None, obs
        label = {"missing": "basis_evidence", "changed_counts": "sha256", "wrong_hash": "sha256",
                 "inventory_ids": "inventories"}.get(change, change)
        assert label in obs["blocker"]


@pytest.mark.parametrize("kind", ["reference_site", "reference_site_pair", "other"])
def test_inspected_tof_without_native_basis_evidence(tmp_path, runtime, monkeypatch, kind):  # noqa: F811
    source, run, _ = replayed_point(tmp_path, runtime, monkeypatch, kind)
    receipt = flow.accepted_receipt(run)
    paths = dict(zip(("network", "dataset", "configuration"), source, strict=True),
                 result=run / "result.json", mkm_receipt=save(tmp_path / "manifest.json", receipt))
    obs = inspect_tof(tmp_path, receipt["catalyst_project_id"], paths)
    if kind == "other":
        assert obs["status"] == "invalid_reference" and obs["value"] is None
        assert "basis_evidence" in obs["blocker"]
    else:
        assert obs["status"] == "available" and obs["value"]["turnover_basis"] == kind
        assert obs["value"]["value"] == read(run / "result.json")["tof_s_inverse"]
