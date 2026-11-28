"""Offline public MKM analysis controls using the archived single-point calculation."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sbq123.common.evidence import trust
from sbq123.common.evidence.mkm_mass import compare_mass_turnover
from sbq123.common.kinetic_model.contracts import identity


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf8")
    return path


@pytest.fixture(scope="module")
def archived(tmp_path_factory):
    pytest.importorskip("sbq123.mkm")
    source = Path(__file__).resolve().parents[2]
    if os.environ.get("SBQ123_ROLE_DATA"):
        root = Path(os.environ["SBQ123_ROLE_DATA"])
    else:
        root = tmp_path_factory.mktemp("mass-archive") / "mkm"
        subprocess.run([sys.executable, "-I", "-B", source / "tools/v32/prepare_history.py",
                        source / "v31", "mkm", root], check=True)
    from sbq123.common.compat import historical_module

    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("SBQ123_ROLE_DATA", str(root))
        api = historical_module("mkm", "scripts.baseline_mkm.analysis")
        from scripts.baseline_mkm import normalization
        patch.setattr(normalization, "SOURCE_ROOT", root)
        phase = root / "reports/multiphase/phase3_0"
        inputs = dict(network=phase / "closed_cycle_network.json", dataset=phase.parent / "phase2_5_2/cycle_dataset.json",
                      configuration=phase / "workflow_configuration.json", result=phase / "result.json",
                      receipt=read(phase / "benchmark_manifest.json"))
        profile = phase.parent / "phase3_1/benchmark_normalization.json"
        options = read(profile)
        options["source"]["path"] = str((profile.parent / options["source"]["path"]).resolve())
        yield api, inputs, options


def check_native(report):
    assert report["tof"]["overall"]["per_site_pair_s"] == pytest.approx(81.5127701616477)
    assert report["coverage"] and report["rates"]["reactions"]
    assert report["selectivity"]["molar"] == {"HNO-g": 1}


@pytest.mark.parametrize("factor", [None, 0.02, 0.20])
def test_unapproved_mass_is_local(archived, tmp_path, factor):
    api, args, options = archived
    values = dict(options)
    if factor is not None:
        values["reference_mol_per_kg"] = factor
    args = dict(args, options=save(tmp_path / "options.json", values))
    report = api.analyze(**args)
    check_native(report)
    assert "reference_mol_per_kg" in report["validation"]["missing_normalization"]
    for row in [report["tof"]["overall"], *report["tof"]["products"].values()]:
        assert row["mol_per_kg_s"] is None
    mass = report["mass_normalization"]
    assert mass["status"] == "unavailable" and "approval" in mass["reason"]
    if factor is not None:
        assert mass["hypothetical"]["reference_mol_per_kg"] == factor
    assert compare_mass_turnover((report, args), (report, args))["difference_mol_per_kg_s"] is None


def test_area_factor_does_not_grant_mass(archived, tmp_path):
    api, args, options = archived
    opts = dict(options, reference_mol_per_catalyst_m2=1e-5, catalyst_m2_per_kg=2000,
                reference_mol_per_reactor_m3=3.0)
    report = api.analyze(**args, options=save(tmp_path / "options.json", opts))
    check_native(report)
    row = report["tof"]["overall"]
    assert row["mol_per_kg_s"] is None
    assert row["mol_per_m2_s"] == pytest.approx(row["per_site_pair_s"] * 1e-5)
    assert row["mol_per_m3_reactor_s"] == pytest.approx(row["per_site_pair_s"] * 3)


@pytest.fixture
def calibrated(archived, tmp_path, monkeypatch):
    api, args, options = archived
    profile = save(tmp_path / "options.json", options)
    native = api.analyze(**args, options=profile)["native_reference"]
    network = read(args["network"])
    context = dict(dataset_sha256=digest(args["dataset"]), network_sha256=digest(args["network"]),
                   point_sha256=digest(args["result"]), configuration_sha256=digest(args["configuration"]),
                   catalyst_project_id=network["project_id"], catalyst_catalog_sha256=identity(network["catalog"]),
                   reference_sha256=identity(native), validity_scope=read(args["result"])["scope"])
    calibration = dict(mass_basis="kg_total_catalyst", unit="mol_reference/kg", value=0.02)
    approval = dict(format="mkm-mass-conversion/1", decision="approved", reviewer="test-only independent fixture",
                    context=context)

    def issue(*, change_context=None, change_factor=None, approved=True):
        evidence = save(tmp_path / "calibration.json", calibration | (change_factor or {}))
        reviewed = approval | {"context": context | (change_context or {}),
                               "calibration": {"path": evidence.name, "sha256": digest(evidence)}}
        receipt = save(tmp_path / "review.json", reviewed)
        if approved:
            monkeypatch.setattr(trust, "MKM_MASS_APPROVALS", frozenset({digest(receipt)}))
        loc = {"path": receipt.name, "sha256": digest(receipt)}
        save(profile, dict(options, mass_conversion_approval=loc))
        return dict(args, options=profile), evidence

    return api, issue


def test_approved_and_serialized_comparison(calibrated):
    api, issue = calibrated
    args, _ = issue()
    report = api.analyze(**args)
    check_native(report)
    saved = json.loads(json.dumps(report))
    assert saved["mass_normalization"]["status"] == "available"
    assert saved["tof"]["overall"]["mol_per_kg_s"] == pytest.approx(1.630255403232954)
    assert saved["tof"]["products"]["HNO-g"]["mol_per_kg_s"] == pytest.approx(3.260510806465908)
    assert compare_mass_turnover((saved, args), (report, args))["difference_mol_per_kg_s"] == 0
    changed = deepcopy(saved)
    changed["tof"]["overall"]["mol_per_kg_s"] *= 10
    assert compare_mass_turnover((changed, args), (report, args))["status"] == "unavailable"
    changed["result_sha256"] = identity(changed)
    assert compare_mass_turnover((changed, args), (report, args))["status"] == "unavailable"


@pytest.mark.parametrize("field", ["catalyst_project_id", "dataset_sha256", "catalyst_catalog_sha256",
                                   "reference_sha256", "point_sha256", "configuration_sha256", "validity_scope"])
def test_mismatched_approved_context(calibrated, field):
    api, issue = calibrated
    args, _ = issue(change_context={field: "different"})
    report = api.analyze(**args)
    check_native(report)
    assert report["tof"]["overall"]["mol_per_kg_s"] is None
    assert "cover" in report["mass_normalization"]["reason"]


@pytest.mark.parametrize("change", [{"mass_basis": "kg_active_metal"}, {"unit": "mol_reference/g"}, {"value": -1}])
def test_mismatched_mass_basis_or_units(calibrated, change):
    api, issue = calibrated
    args, _ = issue(change_factor=change)
    report = api.analyze(**args)
    check_native(report)
    assert report["mass_normalization"]["status"] == "unavailable"


def test_modified_source_and_self_issued_review(calibrated):
    api, issue = calibrated
    args, evidence = issue(approved=False)
    assert "pinned" in api.analyze(**args)["mass_normalization"]["reason"]
    args, evidence = issue()
    original = api.analyze(**args)
    save(evidence, read(evidence) | {"value": 0.20})
    modified = api.analyze(**args)
    check_native(modified)
    assert "SHA-256" in modified["mass_normalization"]["reason"]
    assert compare_mass_turnover((original, args), (original, args))["status"] == "unavailable"

@pytest.mark.parametrize("factor", [-1, 10**400, "invalid"])
def test_invalid_optional_factor_preserves_other_observables(archived, tmp_path, factor):
    api, args, options = archived
    report = api.analyze(**args, options=save(tmp_path / "profile.json", dict(options, reference_mol_per_kg=factor)))
    check_native(report)
    assert "invalid hypothetical" in report["mass_normalization"]["reason"]
    assert report["tof"]["overall"]["mol_per_kg_s"] is None


def test_conflicting_request_cannot_override_review(calibrated):
    api, issue = calibrated
    args, _ = issue()
    profile = args["options"]
    save(profile, read(profile) | {"reference_mol_per_kg": 0.20})
    report = api.analyze(**args)
    check_native(report)
    assert report["tof"]["overall"]["mol_per_kg_s"] is None
    assert "differs" in report["mass_normalization"]["reason"]
