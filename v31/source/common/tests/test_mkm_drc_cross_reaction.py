"""Cross-reaction displacements, pressure activities and fail-closed campaign scheduling."""

from copy import deepcopy
from math import exp

import pytest

from scripts.artifact_io import load_json_object as read, sha256_file, sha256_json, write_json_exclusive as save
from scripts.baseline_mkm import drc_cross_reaction as campaign, drc_pair as pair
from scripts.baseline_mkm.drc_report import cross_reaction_comparison, directional_audit
from scripts.baseline_mkm.ts_perturbation import derivative, reproduce, reviewed_reaction
from scripts.thermochemistry.harmonic import KB


@pytest.fixture
def parents():
    return read(pair.REPORTS / "phase3_0/closed_cycle_network.json"), read(pair.REPORTS / "phase2_5_2/cycle_dataset.json")


@pytest.mark.parametrize("rid", ["transfer", "hydrogenate"])
@pytest.mark.parametrize("step", [-0.010, 0.010, -0.005, 0.005])
def test_selected_displacement(parents, rid, step):
    network, parent = parents
    child = derivative(network, parent, 1 if step > 0 else -1, abs(step), rid)
    assert reproduce(network, child) == child and child["ts_perturbation"]["reaction_id"] == rid
    for old, new in zip(parent["reactions"], child["reactions"], strict=True):
        if old["reaction_id"] != rid:
            assert old == new
            continue
        assert old["energies"]["electronic_ev"] == new["energies"]["electronic_ev"]
        assert new["equilibrium"]["ln_K_standard"] == old["equilibrium"]["ln_K_standard"]
        assert abs(new["equilibrium"]["log_ratio_residual"]) < 1e-12
        assert new["energies"]["gibbs_ev"]["reaction"] == old["energies"]["gibbs_ev"]["reaction"]
        for side in ("forward", "reverse"):
            a, b = old["rates"][side], new["rates"][side]
            assert b["activity_orders"] == a["activity_orders"] and b["gas_orders"] == a["gas_orders"]
            assert b["activation_free_energy_ev"] == pytest.approx(a["activation_free_energy_ev"] + step)
            assert b["activity_coefficient_s^-1"] / a["activity_coefficient_s^-1"] == pytest.approx(exp(-step / (KB * 400)))


@pytest.mark.parametrize("fault", ["unknown", "duplicate network", "duplicate dataset", "missing TS", "wrong barrier", "wrong reference"])
def test_selection_rejects_bad_bindings(parents, fault):
    network, dataset = parents
    rid = "hydrogenate"
    entry, row = reviewed_reaction(network, dataset, rid)
    if fault == "unknown":
        rid = "unlisted"
    elif fault == "duplicate network":
        network["reactions"].append(entry)
    elif fault == "duplicate dataset":
        dataset["reactions"].append(row)
    elif fault == "missing TS":
        entry.pop("ts_review")
    elif fault == "wrong barrier":
        row["parameter_set"]["reverse"]["activation_energy"]["value"] = 4
    else:
        row["parameter_set"]["energy_reference_id"] = "unrelated"
    with pytest.raises(ValueError):
        reviewed_reaction(network, dataset, rid)


def test_native_pressure_factors_and_asymmetric_units(parents):
    _, dataset = parents
    baseline = read(pair.REPORTS / "phase3_1/closed_cycle/analysis.json")
    selected = directional_audit(dataset, baseline, "hydrogenate")
    f, r = selected["forward"], selected["reverse"]
    assert (f["gas_orders"], r["gas_orders"]) == ({"NO-g": 1}, {})
    assert (f["coefficient_unit"], r["coefficient_unit"]) == ("bar^-1 s^-1", "s^-1")
    assert f["reconstructed_flux"] == pytest.approx(f["native_coefficient"] * 0.5 * f["adsorbate_factor"])
    assert r["reconstructed_flux"] == pytest.approx(r["native_coefficient"] * r["adsorbate_factor"])
    transfer = directional_audit(dataset, baseline, "transfer")
    assert transfer["forward"]["gas_orders"] == transfer["reverse"]["gas_orders"] == {}
    broken = deepcopy(baseline)
    next(v for v in broken["rates"]["reactions"] if v["reaction_id"] == "hydrogenate")["forward_flux"] *= 2
    with pytest.raises(ValueError, match="flux"):
        directional_audit(dataset, broken, "hydrogenate")


@pytest.mark.parametrize("fault", ["none", "fourth unapproved", "first pair failed", "total expired"])
def test_campaign_four_approvals_and_budget(tmp_path, monkeypatch, fault):
    decisions = {}
    digests = {}
    for name, step in campaign.STEPS:
        root = tmp_path / name
        root.mkdir()
        plan = dict(reaction_id="hydrogenate", delta_eV=step, baseline_result_sha256="base")
        save(root / "pair.json", plan)
        digests[name] = sha256_json(plan)
        decisions[name] = {label: root / label for label, _ in pair.SIGNS}
    checked, invoked = [], []
    if fault == "total expired":
        save(tmp_path / "started.json", dict(pairs_sha256=sha256_json(digests), utc_epoch_s=20))
    monkeypatch.setattr(pair, "baseline", lambda _: ({"result_sha256": "base"}, {}))
    monkeypatch.setattr(pair, "clock", lambda: 1000)
    monkeypatch.setattr(pair, "check_member", lambda root, base, label, sign: root / label)
    monkeypatch.setattr(pair.point, "status", lambda _: {"stage": "AWAITING_APPROVAL"})

    def preflight(member, decision):
        assert decision == member
        checked.append(member)
        if len(checked) == 4 and fault == "fourth unapproved":
            raise PermissionError("refused")

    def run(root, base, approvals, *, campaign_deadline):
        assert len(checked) == 4 and 0 < campaign_deadline - campaign.monotonic() <= 960
        invoked.append(root.name)
        if fault == "first pair failed":
            raise ValueError("failed")

    monkeypatch.setattr(pair.point, "preflight", preflight)
    monkeypatch.setattr(pair, "run_pair", run)
    if fault == "none":
        assert campaign.run(tmp_path, tmp_path, "hydrogenate", decisions)["total_budget_s"] == 960
        assert invoked == ["coarse", "fine"]
    else:
        with pytest.raises((ValueError, PermissionError, TimeoutError)):
            campaign.run(tmp_path, tmp_path, "hydrogenate", decisions)
        assert invoked == (["coarse"] if fault == "first pair failed" else [])
        assert not (tmp_path / "finished.json").exists()


def test_published_cross_type_result_and_step_stability(parents):
    from jsonschema import Draft202012Validator

    _, dataset = parents
    output = pair.REPORTS / "phase3_2_0_2"
    paths = [(pair.REPORTS / "phase3_2_0/result.json", pair.REPORTS / "phase3_2_0_1/result.json"),
             (output / "coarse/result.json", output / "fine/result.json")]
    result = cross_reaction_comparison(paths, dataset, read(pair.REPORTS / "phase3_1/closed_cycle/analysis.json"))
    assert result == read(output / "result.json")
    schema = read(pair.REPORTS.parents[1] / "configs/kinetics/mkm_cross_reaction_drc.schema.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)
    assert set(result["reactions"]) == {"transfer", "hydrogenate"}
    for row in result["reactions"].values():
        first, second = (row["estimates"][k]["central"] for k in ("coarse", "fine"))
        assert row["step_stable"] == (abs(first - second) <= max(0.002, 0.05 * abs(second)))


@pytest.mark.parametrize("name,step", campaign.STEPS)
@pytest.mark.parametrize("label,sign", pair.SIGNS)
def test_portable_native_pressure_evidence(parents, name, step, label, sign):
    from scripts.baseline_mkm.results import read_single_point

    network, parent = parents
    folder = pair.REPORTS / "phase3_2_0_2" / name
    run = folder / label
    report, receipt = read(folder / "result.json"), read(run / "accepted.json")
    case = report["cases"][label]
    child = derivative(network, parent, sign, step, "hydrogenate")
    assert case["dataset_version"] == child["dataset_version"]
    approval = read(run / "approval.json")
    assert sha256_json(read(run / "plan.json")) == approval["state_sha256"] == case["source_hashes"]["plan"]
    assert sha256_json(approval) == receipt["approval_reference"]
    assert sha256_file(run / "user-reply.json") == approval["source"]["sha256"]
    assert sha256_file(run / "data1.mat") == receipt["output_hashes"]["runtime/result_phase25/data1.mat"]
    native = read_single_point(run / "data1.mat", run / "native_log_extract.txt")
    audit = case["pressure_validation"]
    row = next(row for row in native["reactions"] if row["index"] == audit["native_index"])
    assert row["forward_flux"] == pytest.approx(row["kf"] * native["partial_pressures_bar"]["P_NO"] * native["coverages"]["Q1_H"])
    assert row["reverse_flux"] == pytest.approx(row["kr"] * native["coverages"]["Q1_HNO"])
    assert native["net_gas_flux_per_reference_site_s"]["HNO"] / 2 == pytest.approx(case["net_tof_per_site_pair_s"])

