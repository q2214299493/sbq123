from pathlib import Path
import sqlite3

import pytest

from scripts.artifact_io import sha256_json
from scripts.scientific_priority.benchmark import synthetic
from scripts.scientific_priority.engine import rank
from scripts.scientific_priority.evidence import OPERATIONS, match_evidence, registry_inventory, reliability
from scripts.scientific_priority.proposals import proposals, review

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def pilot():
    return synthetic(ROOT)


def test_benchmark_changes_with_objective(pilot):
    data, p = pilot
    a = rank(data, p["activity"])
    b = rank(data, p["interface"])
    assert [r["candidate"]["id"] for r in a["ranked"]] == ["hydrogenate", "HNO-top", "transfer"]
    assert b["ranked"][0]["candidate"]["id"] == "transfer"
    assert [x["sensitivity"]["value"] for x in a["ranked"]] == pytest.approx([0.4502575521, 0.401377874, 0.04069045116])
    assert a["context_evidence"][0]["value"] == pytest.approx(0.494841688)
    assert a["deferred"][0]["status"] == "reuse"
    for r in a["ranked"]:
        assert sum(r["weighted_contributions"].values()) == pytest.approx(r["score"])
        assert r["score_bounds"] == pytest.approx([r["score"]] * 2)
    assert a == rank(data, p["activity"])


@pytest.mark.parametrize(
    "kind,target", [("product_selectivity", "C3H6"), ("carbon_chain_selectivity", "C3+"), ("phase_comparison", "alpha vs beta")]
)
def test_cannot_transfer_tof_to_other_observables(pilot, kind, target):
    data, p = pilot
    obj = dict(p["activity"], kind=kind, target=target)
    assert not rank(data, obj)["ranked"]
    m = dict(data["metrics"][0], observable_kind=kind, target=target, kind="selectivity_sensitivity")
    data["metrics"].append(m)
    assert rank(data, obj)["ranked"][0]["candidate"]["id"] == "transfer"


def test_condition_and_missing_data(pilot):
    d, p = pilot
    d["metrics"][0] = dict(d["metrics"][0], scope=dict(d["metrics"][0]["scope"], temperature_K=450))
    d["candidates"][1]["cost"] = None
    absent = {r["candidate"]["id"]: r for r in rank(d, p["activity"])["deferred"]}
    assert absent["transfer"]["raw_metrics"]["kinetic_importance"] is None
    assert absent["hydrogenate"]["score"] is None
    assert absent["hydrogenate"]["score_bounds"][0] < absent["hydrogenate"]["score_bounds"][1]


def test_uncertainty_is_not_validation_error_or_disagreement(pilot):
    d, p = pilot
    a = rank(d, p["activity"])
    rs = {r["candidate"]["id"]: r for r in a["ranked"]}
    assert rs["hydrogenate"]["expected_information_value"] is None
    assert rs["transfer"]["expected_information_value"] == pytest.approx(0.00111483151)
    u = rs["hydrogenate"]["reliability"]
    assert u["calibration_status"] == "uncalibrated" and u["ensemble_sd_eV"] == 0.012
    assert u["validation_errors"]["relative_energy_rmse_eV"] == 0.035
    c = d["candidates"][0]
    rec = d["reliability"][0]
    rec.update(
        aqcat25_force_review=dict(
            checkpoint_sha256=c["model_version"],
            samples=[dict(structure_sha256=c["targets"]["TS"])],
            metrics=dict(vector_rmse_eV_per_A=0.31),
            status="out_of_domain",
        )
    )
    out = reliability(c, [rec])
    assert out["calibration"] is None and out["validation_errors"]["vector_rmse_eV_per_A"] == 0.31
    assert reliability(dict(c, model_version="another-model"), [rec])["validation_errors"]["relative_energy_rmse_eV"] is None


def test_structural_matching_and_conflicts(pilot):
    d, _ = pilot
    c = d["candidates"][0]
    rec = dict(d["evidence"][0], need=c["need"])
    new = sha256_json("other geometry")
    orig = c["targets"]["TS"]
    other = dict(rec, targets={"TS": new})
    assert match_evidence(c, [other], []) == []
    eq = dict(
        protocol=c["protocol"],
        hashes=[orig, new],
        review="accepted",
        rule="documented PBC translation with atom mapping",
        review_sha256=sha256_json("independent reviewed equivalence fixture"),
    )
    assert match_evidence(c, [other], [eq]) == [rec["id"]]
    assert not match_evidence(c, [dict(other, protocol="different slab")], [eq])
    assert not match_evidence(c, [dict(rec, review="rejected")], [])
    assert not match_evidence(c, [other], [dict(eq, review="draft")])
    d["candidates"].append(dict(c, id="duplicate"))
    rows = rank(d, _["activity"])
    assert sum(r["status"] == "duplicate" for r in rows["deferred"]) == 1


def test_ordered_gaps_and_novelty(pilot):
    d, p = pilot
    c = d["candidates"][0]
    c.update(needs=["minimum_geometry", "electronic_energy"], cost_by_need={"electronic_energy": c["cost"]})
    obj = dict(p["activity"], weights={"novelty": 1}, scales={"novelty": 0.5}, distance_definition="mock descriptor distance")
    r = next(r for r in rank(d, obj)["ranked"] if r["candidate"]["id"] == "transfer")
    assert r["recommendation"] == OPERATIONS["electronic_energy"]
    assert r["covered_requirements"]["minimum_geometry"] and r["normalized_scores"]["novelty"] == pytest.approx(0.2)
    assert not rank(d, dict(obj, distance_definition="different fingerprint"))["ranked"]


@pytest.mark.parametrize("need", sorted(OPERATIONS))
def test_operations_and_strategy_gates(pilot, need):
    d, p = pilot
    c = d["candidates"][0]
    c["need"] = need
    d["candidates"] = [c]
    d["evidence"] = []
    if need in ("saddle_refinement", "reaction_path"):
        assert not rank(d, p["activity"])["ranked"]
        c["targets"].update(IS=sha256_json("IS"), FS=sha256_json("FS"))
        c["strategy"] = dict(
            status="NEEDS_GPU_PATH_OR_VASP_PATH_REVIEW",
            source_sha256=sha256_json("strategy"),
            reaction_family=c["reaction_family"],
            automatic_submission=False,
        )
    r = rank(d, p["activity"])["ranked"][0]
    assert r["recommendation"] == OPERATIONS[need]


def test_pareto_and_general_surface(pilot):
    d, p = pilot
    for c in d["candidates"]:
        c.update(
            phase_ids=["oxide-A", "carbide-B"],
            surface_ids=["facet-X", "facet-Y"],
            interface_id="Z",
            site_context={"X-vac": 2, "Y-threefold": 1},
        )
    rows = rank(d, p["activity"])["ranked"]
    assert all(r["candidate"]["site_context"]["X-vac"] == 2 for r in rows)
    assert rows[0]["pareto_front"] == 1
    d["candidates"][0]["cost"] = dict(value=999, unit="core_hour", source="fixture")
    d["reliability"][0]["validation_errors"]["relative_energy_rmse_eV"] = 0
    assert rank(d, p["activity"])["ranked"][-1]["pareto_front"] > 1


@pytest.mark.parametrize("decision", ["approve", "reject", "defer", "modify"])
def test_immutable_human_review(pilot, tmp_path, decision):
    d, p = pilot
    items = proposals(rank(d, p["activity"]), tmp_path)
    item = items[0]
    record = dict(decision=decision, proposal_id=item["proposal_id"], reviewer="researcher", reason="reviewed fixture")
    if decision == "modify":
        new = proposals(rank(d, p["interface"]), tmp_path)
        record["replacement_proposal_id"] = next(v["proposal_id"] for v in new if v["candidate_id"] == item["candidate_id"])
    receipt = review(tmp_path, record)
    assert not receipt["execution_authorized"] and not item["runnable"]
    assert bool(receipt["handoff"]) == (decision == "approve")
    assert review(tmp_path, record) == receipt
    with pytest.raises(ValueError):
        review(tmp_path, dict(record, reason="silently overwrite"))
    with pytest.raises(ValueError):
        review(tmp_path, dict(record, proposal_id="../foreign"))


def test_registry_readonly_and_exact_hash(pilot, tmp_path):
    d, p = pilot
    c = d["candidates"][0]
    h = c["targets"]["TS"]
    f = tmp_path / "fixture.sqlite"
    db = sqlite3.connect(f)
    db.executescript(
        "CREATE TABLE calculations(calculation_id,module,purpose);CREATE TABLE files(calculation_id,role,sha256);"
        "CREATE TABLE results(calculation_id,result_id,result_name,unit,reference_convention,validation_status);"
    )
    db.execute("INSERT INTO calculations VALUES ('calc','DFT','electronic energy')")
    db.execute("INSERT INTO files VALUES ('calc','input',?)", (h,))
    db.commit()
    db.close()
    before = f.read_bytes()
    d["registry_hits"] = registry_inventory(f, [h, sha256_json("another-geometry")])
    assert f.read_bytes() == before and not d["registry_hits"][sha256_json("another-geometry")]
    row = next(r for r in rank(d, p["activity"])["deferred"] if r["candidate"]["id"] == "transfer")
    assert "calc" in str(row["reasons"])


def test_unknown_cost_unit_and_unbound_metric(pilot):
    d, p = pilot
    d["candidates"][0]["cost"]["unit"] = "GPU_hours"
    assert "transfer" not in [r["candidate"]["id"] for r in rank(d, p["activity"])["ranked"]]
    d["metrics"][0]["source"] = "unknown"
    with pytest.raises(ValueError, match="source"):
        rank(d, p["activity"])


def test_fe_inventory_protects_missing_science():
    from scripts.artifact_io import load_json_object as read, sha256_file

    output = ROOT / "reports/multiphase"
    record = read(output / "phase3_2_3/fe110_inventory.json")
    assert record["status"] == "blocked" and record["proposed_native_runs"] == 0
    for key in (
        "scientific_importance",
        "model_uncertainty",
        "score",
        "drc",
        "intermediate_sensitivity",
        "gas_order",
        "free_energy_barriers",
        "rate_constants",
    ):
        assert record[key] is None
    assert record["thermal_routes"] == {"IS": None, "TS": "TS.spectrum", "FS": None}
    assert all(record["registry_exact_matches"][r["sha256"]] for r in record["structures"].values())
    assert all(sha256_file(output / name) == h for name, h in record["sources"].items())


def test_descriptor_distance_uses_only_compatible_training_features():
    from scripts.scientific_priority.evidence import novelty

    descriptor = dict(
        query=[1, 3],
        scales=[2, 3],
        definition="cartesian-v1",
        training=[
            dict(definition="unrelated", vector=[1, 3], structure_sha256=sha256_json(1)),
            dict(definition="cartesian-v1", vector=[3, 6], structure_sha256=sha256_json(2)),
        ],
    )
    assert novelty(dict(descriptor_comparison=descriptor))[0] == pytest.approx(2**0.5)
    descriptor["training"] = []
    assert novelty(dict(descriptor_comparison=descriptor))[0] is None


def test_input_evidence_binding_and_portable_benchmark(pilot, tmp_path):
    from scripts.scientific_priority.__main__ import emit, import_packet
    from scripts.artifact_io import load_json_object as read, write_json_exclusive

    data, policies = pilot
    data["sources"] = {k: dict(ref, path=str(ROOT / ref["path"])) for k, ref in data["sources"].items()}
    from scripts.artifact_io import sha256_file

    reviews = [dict(m, value_source_sha256=data["sources"][m["source"]]["sha256"]) for m in data["metrics"]]
    review_file = write_json_exclusive(tmp_path / "reviews.json", {"rows": reviews})
    data["sources"]["reviews"] = dict(path=review_file.name, sha256=sha256_file(review_file))
    for i, metric in enumerate(data["metrics"]):
        metric["scope_record"] = dict(source="reviews", path=["rows", i])
    f = write_json_exclusive(tmp_path / "packet.json", data)
    loaded = import_packet(f)
    index = emit(loaded, policies["activity"], tmp_path / "output")
    assert len(index["proposal_ids"]) == 3
    report = read(tmp_path / "output/reports" / (index["report_sha256"] + ".json"))
    assert sha256_json(report) == index["report_sha256"] and report["ranked"][0]["candidate"]["id"] == "hydrogenate"
    data["candidates"][0]["surface_ids"] = ["unrelated_facet"]
    changed = import_packet(write_json_exclusive(tmp_path / "wrong-surface.json", data))
    row = next(r for r in rank(changed, policies["activity"])["deferred"] if r["candidate"]["id"] == "transfer")
    assert "surface_ids" in str(row["reasons"])
    data["metrics"][0]["target"] = "C3+"
    with pytest.raises(ValueError, match="scope"):
        import_packet(write_json_exclusive(tmp_path / "relabeled.json", data))
    del data["metrics"][0]["target"]
    data["metrics"][0]["value"] += 1
    with pytest.raises(ValueError, match="source field"):
        import_packet(write_json_exclusive(tmp_path / "stale.json", data))


def test_defer_can_be_resolved_without_mutating_receipt(pilot, tmp_path):
    d, p = pilot
    proposal = proposals(rank(d, p["activity"]), tmp_path)[0]
    choice = dict(proposal_id=proposal["proposal_id"], reviewer="R", reason="review", decision="defer")
    old = review(tmp_path, choice)
    approved = review(tmp_path, dict(choice, decision="approve", after_defer=sha256_json(old)))
    assert approved["handoff"]["runnable"] is False and review(tmp_path, choice) == old
    with pytest.raises(ValueError):
        review(tmp_path, dict(choice, decision="approve", after_defer=sha256_json("stale")))


@pytest.mark.parametrize("metric,expected", [("ensemble_sd_eV", 0.018), ("calibrated_sd_eV", 0.03), ("extrapolation_grade", 0.25)])
def test_objective_selects_one_reliability_measure(pilot, metric, expected):
    d, p = pilot
    obj = dict(p["activity"], reliability_metric=metric, grade_scores={"mock_interpolation": 0.25})
    row = next(r for r in rank(d, obj)["ranked"] if r["candidate"]["id"] == "transfer")
    assert row["raw_metrics"]["reliability_gap"] == pytest.approx(expected)


def test_unverified_protocol_does_not_trigger_reuse(pilot):
    d, p = pilot
    c = dict(d["candidates"][0], protocol=None)
    d["candidates"] = [c]
    d["evidence"] = [dict(d["evidence"][0], protocol=None, need=c["need"])]
    row = rank(d, p["activity"])["deferred"][0]
    assert row["status"] == "deferred" and not row["matching_evidence"]


def test_approved_project_ts_reaches_existing_gate_only(pilot, tmp_path):
    d, p = pilot
    c = d["candidates"][0]
    c.update(
        scope_label="test_project",
        need="saddle_refinement",
        strategy=dict(
            status="NEEDS_GPU_PATH_OR_VASP_PATH_REVIEW",
            source_sha256=sha256_json("review"),
            automatic_submission=False,
            reaction_family=c["reaction_family"],
        ),
    )
    d["candidates"] = [c]
    item = proposals(rank(d, p["activity"]), tmp_path)[0]
    receipt = review(tmp_path, dict(proposal_id=item["proposal_id"], decision="approve", reviewer="fixture", reason="test routing"))
    assert receipt["handoff"]["destination"] == "scripts.ts_strategy_engine.execution_gate"
    assert not receipt["execution_authorized"] and "ALLOWED_ACTIONS" not in receipt
