"""Portable qualification controls and the platform-specific archived-point replay."""
import json
import os
from pathlib import Path
import subprocess
import sys
from hashlib import sha256

import pytest

from sbq123.common.compat import historical_module
from sbq123.common.evidence.mkm_mass import mass_options, project_mass_turnover
from sbq123.common.kinetic_model.contracts import identity


def store(path, obj):
    raw = json.dumps(obj, sort_keys=True).encode()
    path.write_bytes(raw)
    return {"path": path.name, "sha256": sha256(raw).hexdigest()}


@pytest.mark.parametrize("basis", ["reference_site", "reference_site_pair", "other"])
@pytest.mark.parametrize("case", ["approved", "missing", "wrong_basis", "changed_source", "wrong_catalyst"])
def test_mass_contract_after_native_analysis(tmp_path, monkeypatch, basis, case, approve_project_record):
    historical_module("mkm", "scripts.multiphase_contracts")
    native = {"reference_basis": basis, "reference_id": "ref", "evidence_sha256": "1"*64}
    network = {"project_id": "control", "catalog": {"materials": ["M"]}}
    hashes = {"network": "2"*64, "dataset": "3"*64, "configuration": "4"*64}
    point = {"scope": "synthetic_control"}
    context = dict(dataset_sha256=hashes["dataset"], network_sha256=hashes["network"],
                   configuration_sha256=hashes["configuration"], point_sha256="5"*64,
                   reference_sha256=identity(native), validity_scope=point["scope"],
                   catalyst_project_id="different" if case == "wrong_catalyst" else network["project_id"],
                   catalyst_catalog_sha256=identity(network["catalog"]))
    factor = dict(mass_basis="kg_active_metal" if case == "wrong_basis" else "kg_total_catalyst",
                  unit="mol_reference/kg", value=0.02)
    file = tmp_path / "source.json"
    calibration = store(file, factor)
    approval = store(tmp_path / "approval.json", dict(format="mkm-mass-conversion/1", decision="approved",
                     reviewer="isolated analytical control", context=context, calibration=calibration))
    approve_project_record("mass_conversion", approval["sha256"])
    opt = {"reference_mol_per_kg": 0.02}
    if case != "missing":
        opt["mass_conversion_approval"] = approval
    if case == "changed_source":
        store(file, factor | {"value": 0.2})
    clean, qual = mass_options(opt, tmp_path / "options.json", network, hashes, "5"*64, point, native)
    overall = dict(per_reference_s=8.0, mol_per_kg_s=None)
    report = dict(tof=dict(overall=overall, products={}), normalization=clean,
                  validation=dict(missing_normalization=["reference_mol_per_kg"]))
    project_mass_turnover(report, qual)
    assert overall["per_reference_s"] == 8
    if case == "approved":
        assert qual["status"] == "available" and overall["mol_per_kg_s"] == pytest.approx(0.16)
    else:
        assert qual["status"] == "unavailable" and qual["reason"] and overall["mol_per_kg_s"] is None


def test_original_archive_boundary(tmp_path, monkeypatch):
    """Only the exact original calculation may enter the historical analysis controls."""
    source = Path(__file__).resolve().parents[2]
    root = tmp_path / "mkm"
    subprocess.run([sys.executable, "-I", "-B", source / "tools/v32/prepare_history.py",
                    source / "v31", "mkm", root], check=True)
    monkeypatch.setenv("SBQ123_ROLE_DATA", str(root))
    api = historical_module("mkm", "scripts.baseline_mkm.analysis")
    folder = root / "reports/multiphase"
    net = folder / "phase3_0/closed_cycle_network.json"
    data = folder / "phase2_5_2/cycle_dataset.json"
    original = json.loads(data.read_bytes())
    rebuilt = api.reproduce(json.loads(net.read_bytes()), original)
    assert rebuilt == original
    subprocess.run([sys.executable, "-I", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                    "-c", source / "packages/mkm/pyproject.toml", source / "tools/v32/mass_archive_controls.py"],
                   cwd=tmp_path, env=dict(os.environ, SBQ123_ROLE_DATA=str(root)), check=True)
