"""Offline acceptance controls for the common analysis and optional one-state balance."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from scripts.artifact_io import sha256_bytes, sha256_json
from scripts.kinetic_data.analysis_contracts import local_species_sources
from scripts.kinetic_data import analysis_evidence
from scripts.reactor_balance import gas_accumulation
from scripts.scientific_interpretation import summarize_comparison

ROOT = Path(__file__).resolve().parents[1]
NETWORK = ROOT / "reports/multiphase/phase3_0/closed_cycle_network.json"
RATES = ROOT / "reports/multiphase/stage_b1_4/replay/catkinas-phase3_0.json"
# Exact raw-file digest in the sealed MKM source inventory, also bound in KMC's role manifest.
RATE_PROOF = {"path": str(RATES), "sha256": "eb73c3b756ad88316b792df4919c0e08cbe9e0967bcd4d6e2277a5eefcac2ec6"}


def write_fixture(path, document):
    raw = json.dumps(document).encode()
    path.write_bytes(raw)
    return {"path": str(path), "sha256": sha256_bytes(raw)}


TEST_MAPPING = ROOT / "tests/fixtures/v31_conversion"
TEST_APPROVAL_SHA256 = "96c255232f181f1a4f087592051f04c101ac874589dc746db01185831ee182aa"


@pytest.fixture
def fixture_authority(monkeypatch):
    # Only this test process installs the independently pinned synthetic receipt.
    monkeypatch.setattr(analysis_evidence, "_MAPPING_APPROVAL_SHA256", TEST_APPROVAL_SHA256)


def operating_point(tmp_path):
    data = json.loads(RATES.read_bytes())
    target = dict(data["native_normalization"], basis_kind="reactor_volume", denominator_unit="m³",
                  extent_unit="mol", reference_id="audit-test-volume",
                  definition="One cubic metre in the independent software control")
    for name in ("mapping.json", "capacity-source.json", "test-only-approval.json"):
        (tmp_path / name).write_bytes((TEST_MAPPING / name).read_bytes())
    path = tmp_path / "mapping.json"
    proof = {"path": str(path), "sha256": sha256_bytes(path.read_bytes()),
             "approval": {"path": str(tmp_path / "test-only-approval.json"), "sha256": TEST_APPROVAL_SHA256}}
    gas = dict.fromkeys(("H2-g", "NO-g", "HNO-g"), 0)
    return data, dict(conditions=data["conditions"], volume_m3=3, target=target, evidence=proof,
                      rate_evidence=RATE_PROOF, inlet_mol_s=dict(gas), outlet_mol_s=dict(gas))


def test_local_gas_balance(tmp_path, fixture_authority):
    data, inputs = operating_point(tmp_path)
    inputs["inlet_mol_s"]["H2-g"] = 7
    result = gas_accumulation(data, NETWORK, **inputs)
    assert result["accumulation_mol_s"]["H2-g"] == pytest.approx(7 - 6 * 81.5127701616477)
    assert result["rate_dataset_id"] == data["output_binding"]["dataset_id"]


@pytest.mark.parametrize("defect", ["state", "scale", "unit", "flow", "source", "network"])
def test_gas_balance_rejects_unqualified_input(tmp_path, fixture_authority, defect):
    data, args = operating_point(tmp_path)
    network = NETWORK
    if defect == "state":
        args["conditions"] = dict(args["conditions"], temperature_K=410)
    elif defect == "scale":
        args["evidence"] = None
    elif defect == "unit":
        args["target"]["time_unit"] = "min"
    elif defect == "flow":
        args["inlet_mol_s"].pop("H2-g")
    elif defect == "source":
        Path(args["evidence"]["path"]).write_text("{}")
    else:
        network = tmp_path / "changed-network.json"
        network.write_bytes(NETWORK.read_bytes() + b" ")
    if defect == "flow":
        with pytest.raises(ValueError, match="flows"):
            gas_accumulation(data, network, **args)
    else:
        result = gas_accumulation(data, network, **args)
        assert result["status"] == "insufficient_evidence" and result["reason_code"]
        assert result["accumulation_mol_s"] is None


@pytest.mark.parametrize("denominator", [-1, 0, True, "1", None])
def test_source_denominator_must_be_positive(tmp_path, denominator):
    data, args = operating_point(tmp_path)
    target = dict(data["native_normalization"], denominator_value=denominator)
    local = local_species_sources(data, NETWORK, conditions=args["conditions"], target=target, rate_evidence=RATE_PROOF)
    args["target"]["denominator_value"] = denominator
    result = gas_accumulation(data, NETWORK, **args)
    for record, field in [(local, "species"), (result, "accumulation_mol_s")]:
        assert record["status"] == "insufficient_evidence" and record["reason_code"] == "invalid_normalization"
        assert record[field] is None and "denominator_value" in record["reason"]


@pytest.mark.parametrize("defect", ["no_source", "missing_origin", "changed_origin", "negative_factor"])
def test_conversion_requires_bound_factor_source(tmp_path, fixture_authority, defect):
    data, args = operating_point(tmp_path)
    path = Path(args["evidence"]["path"])
    mapping = json.loads(path.read_bytes())
    if defect == "no_source":
        del mapping["source"]
    elif defect == "missing_origin":
        mapping["source"]["path"] = "absent.json"
    elif defect == "changed_origin":
        (tmp_path / mapping["source"]["path"]).write_text("{}")
    else:
        mapping["value"] = -2
    if defect != "changed_origin":
        args["evidence"].update(write_fixture(path, mapping))
    assert_both_refuse(data, args, "conversion_approval_unverified")


@pytest.mark.parametrize("label", ["prefixed", "ordinary"])
@pytest.mark.parametrize("defect", ["none", "missing_binding", "missing_digest", "changed_file",
                                     "changed_payload", "relabel", "unreadable"])
def test_rate_content_identity(tmp_path, fixture_authority, label, defect):
    data, args = operating_point(tmp_path)
    proof = dict(RATE_PROOF)
    if label == "ordinary":
        # A caller digest does not grant independent approval to an ordinary label.
        data["output_binding"]["dataset_id"] = "legacy-case"
        proof = write_fixture(tmp_path / "original.json", data)
    if defect == "missing_binding":
        proof = None
    elif defect == "missing_digest":
        proof.pop("sha256")
    elif defect == "changed_file":
        path = tmp_path / "reserialized.json"
        path.write_bytes(Path(proof["path"]).read_bytes() + b" ")
        proof["path"] = str(path)
    elif defect == "changed_payload":
        data["source_terms"]["species"][0]["net_production_rate"] = 12345
    elif defect == "relabel":
        data["output_binding"]["dataset_id"] = "unrelated"
    elif defect == "unreadable":
        proof["path"] = str(tmp_path / "absent")
    args["rate_evidence"] = proof
    result = gas_accumulation(data, NETWORK, **args)
    if defect == "none" and label == "prefixed":
        assert result["status"] == "available"
        assert result["rate_sha256"] == proof["sha256"]
        assert result["rate_dataset_id"] == data["output_binding"]["dataset_id"]
        assert result["accumulation_mol_s"]["HNO-g"] == pytest.approx(6 * 163.0255403232954)
    else:
        assert result["status"] == "insufficient_evidence" and result["reason"]
        assert result["accumulation_mol_s"] is None


def test_external_digest_does_not_replace_prefixed_identity(tmp_path):
    data, args = operating_point(tmp_path)
    data["output_binding"]["dataset_id"] = "rates-" + "0" * 64
    args["rate_evidence"] = write_fixture(tmp_path / "stale-id.json", data)
    result = gas_accumulation(data, NETWORK, **args)
    assert result["status"] == "insufficient_evidence"
    assert result["reason_code"] == "rate_evidence_unverified"
    assert result["accumulation_mol_s"] is None


def test_source_signs_and_scaling_from_archived_gas_log(tmp_path, fixture_authority):
    data, args = operating_point(tmp_path)
    log = (ROOT / "reports/multiphase/phase2_5_2/native_log_extract.txt").read_text()
    names = next(line.split()[1:] for line in log.splitlines() if line.startswith("Species"))
    values = next(line.split(":")[1].split() for line in log.splitlines() if line.startswith("Rate :"))
    native = {name.replace("(gas)", "-g"): float(value) for name, value in zip(names, values, strict=True)}
    assert set(native) == {"H2-g", "HNO-g", "NO-g"}
    for target, factor, evidence in [(data["native_normalization"], 1, None), (args["target"], 2, args["evidence"])]:
        result = local_species_sources(data, NETWORK, conditions=args["conditions"], target=target,
                                       evidence=evidence, rate_evidence=RATE_PROOF)
        assert result["status"] == "available"
        for gas, signed_rate in native.items():
            assert result["species"][gas]["value"] == pytest.approx(signed_rate * factor)



def assert_both_refuse(data, args, code):
    analysis = local_species_sources(data, NETWORK, **{k: args[k] for k in
                                     ("conditions", "target", "evidence", "rate_evidence")})
    reactor = gas_accumulation(data, NETWORK, **args)
    for result, field in [(analysis, "species"), (reactor, "accumulation_mol_s")]:
        assert result["status"] == "insufficient_evidence"
        assert result["reason_code"] == code and result["reason"] and result[field] is None


def test_no_production_mapping_approval(tmp_path):
    data, args = operating_point(tmp_path)
    assert_both_refuse(data, args, "conversion_approval_unverified")


@pytest.mark.parametrize("fault", ["factor", "no_approval", "approval_repin", "origin_path", "target_basis"])
def test_detached_mapping_approval(tmp_path, fixture_authority, fault):
    data, args = operating_point(tmp_path)
    reference = args["evidence"]
    if fault == "no_approval":
        del reference["approval"]
    elif fault == "approval_repin":
        receipt = json.loads(Path(reference["approval"]["path"]).read_bytes())
        receipt["scope"] = "caller replacement"
        reference["approval"] = write_fixture(tmp_path / "replacement.json", receipt)
    elif fault == "target_basis":
        args["target"]["reference_id"] = "another-bed"
    else:
        mapping = json.loads(Path(reference["path"]).read_bytes())
        if fault == "factor":
            mapping["value"] = 3
        else:
            mapping["source"]["path"] = "another.json"
            (tmp_path / "another.json").write_bytes((tmp_path / "capacity-source.json").read_bytes())
        reference.update(write_fixture(tmp_path / "modified-mapping.json", mapping))
    assert_both_refuse(data, args, "conversion_approval_unverified")


@pytest.mark.parametrize("fault", ["ordinary_double", "prefixed_double", "whitespace_repin", "replace_review"])
def test_rate_provider_cannot_approve_replacement(tmp_path, fixture_authority, fault):
    data, args = operating_point(tmp_path)
    path = tmp_path / "replacement.json"
    if fault == "whitespace_repin":
        path.write_bytes(RATES.read_bytes() + b" ")
    else:
        for reaction in data["reaction_rates"]:
            for direction in ("forward", "reverse", "net"):
                reaction[direction] *= 2
        for group, field in [("species", "net_production_rate"), ("site_inventories", "net_vacancy_rate")]:
            for row in data["source_terms"][group]:
                row[field] *= 2
        data["output_binding"].pop("dataset_id")
        label = "rates-" + sha256_json(data) if fault == "prefixed_double" else "ordinary-case"
        data["output_binding"]["dataset_id"] = label
        path.write_text(json.dumps(data), encoding="utf8")
    args["rate_evidence"] = {"path": str(path), "sha256": sha256_bytes(path.read_bytes())}
    if fault == "replace_review":
        args["rate_evidence"]["approval"] = write_fixture(tmp_path / "my-review.json", args["rate_evidence"])
    assert_both_refuse(data, args, "rate_evidence_unverified")


def test_interpretation_retains_unavailable_measurement():
    row = dict(observable={"kind": "tof"}, compatibility="insufficient_evidence",
               difference=None, reasons=["missing time window"])
    data = dict(format="mkm-kmc-comparison-result/1", comparisons=[row],
                uncertainty={"difference_interval": None}, interpretation="Descriptive comparison")
    original = deepcopy(data)
    data["comparison_sha256"] = sha256_json(data)
    assert summarize_comparison(data)["observations"] == [row]
    assert original["comparisons"] == data["comparisons"]
    data["comparisons"][0]["difference"] = 0
    with pytest.raises(ValueError, match="identity"):
        summarize_comparison(data)


@pytest.mark.parametrize("entry", ["native_analysis", "converted_analysis", "reactor"])
@pytest.mark.parametrize("when", ["at_first_evidence_read", "after_return"])
def test_caller_mutations_leave_calculation_snapshot_intact(tmp_path, monkeypatch, fixture_authority, entry, when):
    from scripts.kinetic_data import analysis_contracts

    data, args = operating_point(tmp_path)
    args["rate_evidence"] = dict(RATE_PROOF)
    args["inlet_mol_s"]["H2-g"] = 7
    if entry == "native_analysis":
        args.update(target=data["native_normalization"], evidence=None)

    def calculate():
        if entry == "reactor":
            return gas_accumulation(data, NETWORK, **args)
        return local_species_sources(data, NETWORK, conditions=args["conditions"], target=args["target"],
                                     evidence=args["evidence"], rate_evidence=args["rate_evidence"])

    def reuse_inputs():
        args["conditions"]["temperature_K"] = 773
        pressures = args["conditions"]["partial_pressures"]
        pressures[0]["pressure_Pa"] = 13
        pressures.pop()
        args["target"]["denominator_value"] = 2
        args["target"]["inventory_ids"][0] = "another-site"
        args["target"]["reference_scope"]["project_id"] = "another-project"
        data["source_terms"]["species"][0]["net_production_rate"] = 12345
        data["reaction_rates"].clear()
        args["rate_evidence"]["path"] = tmp_path / "changed"
        if args["evidence"] is not None:
            args["evidence"]["approval"]["sha256"] = "0" * 64
        args["inlet_mol_s"]["H2-g"] = 900
        args["outlet_mol_s"].clear()

    expected = json.dumps(calculate(), sort_keys=True)
    if when == "at_first_evidence_read":
        review = analysis_contracts.reviewed_rates

        def reuse_then_review(payload, reference):
            reuse_inputs()
            return review(payload, reference)

        monkeypatch.setattr(analysis_contracts, "reviewed_rates", reuse_then_review)
    result = calculate()
    if when == "after_return":
        reuse_inputs()

    encoded = json.dumps(result, sort_keys=True)
    assert encoded == expected
    decoded = json.loads(encoded)
    assert decoded == result
    assert decoded.pop("result_sha256") == sha256_json(decoded)
    assert decoded["status"] == "available"
    assert decoded["conditions"]["temperature_K"] == 400
    assert decoded["basis"]["denominator_value"] == 1
    assert decoded["rate_sha256"] == RATE_PROOF["sha256"]
    if entry == "reactor":
        assert decoded["accumulation_mol_s"]["H2-g"] == pytest.approx(7 - 6 * 81.5127701616477)
    else:
        scale = 1 if entry == "native_analysis" else 2
        assert decoded["species"]["H2-g"]["value"] == pytest.approx(-scale * 81.5127701616477)
