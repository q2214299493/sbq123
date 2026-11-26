"""Public project inspection against fixed archive observations and independently edited inputs."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.kinetic_data.project_inspection import inspect_project

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "reports/workflow_design/stage_f1_2"
RID = "fe110_ch_co_to_chco_20261109"


def pair(case):
    folder = CASES / case
    return folder / "project.yaml", folder / "task.yaml"


def inputs(case):
    return [yaml.safe_load(p.read_bytes()) for p in pair(case)]


def inspect(tmp_path, project, task):
    project = dict(project, evidence_base=str(ROOT))
    project_path, task_path = tmp_path / "project.yaml", tmp_path / "task.yaml"
    project_path.write_text(yaml.safe_dump(project), encoding="utf8")
    task_path.write_text(yaml.safe_dump(task), encoding="utf8")
    return inspect_project(project_path, task_path)["contexts"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fe_acceptance():
    ctx = inspect_project(*pair("fe110"))["contexts"][0]
    obs = ctx["observables"]
    energies = obs["electronic_energies"]["value"]
    assert [energies[s]["value"]["value_ev"] for s in ("IS", "TS", "FS")] == [-385.14767079, -384.17406905, -384.48836276]
    structures = obs["structures"]["value"]
    assert [structures[s]["value"]["identity"] for s in ("IS", "TS", "FS")] == [
        "f8bc627180b430b3b64f748c05830a0372bc93a3750780cf7fe6c5eb0601762d",
        "0157a418cd1fba1be886426361d494ffbdce9a15d1a9132b996a3481ffcc1a6a",
        "11dab1631a99f1e444d4c7ab9ca242609e07c912f656874005696e6498f15ab2",
    ]
    assert all(record["validation"]["validation_status"] == "validated" for record in structures.values())
    assert obs["electronic_barriers"]["value"][RID] == pytest.approx(
        {"forward": 0.97360174, "reverse": 0.31429371, "reaction": 0.65930803})
    thermal = obs["thermochemistry"]
    assert thermal["value"]["states"]["TS"]["zpe_ev"] == pytest.approx(0.51405165)
    assert thermal["value"]["states"]["IS"] is thermal["value"]["states"]["FS"] is thermal["value"]["reaction"] is None
    assert thermal["value"]["gibbs_ev"] == dict(forward=None, reverse=None, reaction=None)
    assert {"IS.corrections", "FS.corrections"} <= set(thermal["missing"])
    assert obs["kinetic_parameters"]["value"][RID] == {"forward": None, "reverse": None}
    assert set(ctx["network"]["conservation"][RID]["unresolved"]) == {"Unknown charge balance", "Unknown site balance"}
    assert [ctx["engines"][engine]["status"] for engine in ("mkm", "kmc")] == ["blocked", "blocked"]


def test_nicu_acceptance():
    ctx = inspect_project(*pair("nicu"))["contexts"][0]
    assert ctx["network"]["version"] == "0978e2199dd35b1bae883edcfb6537376c3152d13fa1f54a4102cc4f035d8264"
    obs = ctx["observables"]
    rates = obs["native_rates"]["value"]
    assert rates["conditions"]["temperature_K"] == 400
    assert rates["native_normalization"]["basis_kind"] == "reference_site_pair"
    assert rates["native_normalization"]["denominator_value"] == 1
    assert rates["statistical_uncertainty"] is None
    assert "uncertainty was not measured" in obs["rate_uncertainty"]["value"]["scope"]
    assert obs["tof"]["value"]["value"] == pytest.approx(81.51277016)
    assert obs["tof"]["value"]["unit"] == "s^-1"
    assert {row["reaction_id"]: row["drc"] for row in obs["stable_drc"]["value"]} == pytest.approx(
        {"hydrogenate": 0.4502575521, "transfer": 0.0406904512})
    assert ctx["engines"]["mkm"] == dict(requested=True, execution_authorized=False, status="input_eligible", missing=[])


def test_oxide_acceptance():
    ctx = inspect_project(*pair("oxide"))["contexts"][0]
    obs = ctx["observables"]
    lattice = obs["lattice"]["value"]
    assert len(lattice["matrix_node_order"]) == 7
    assert len(lattice["initial_bridges"]) == 2
    assert lattice["inventories"] == {"acid-A": {"capacity": 4, "occupied": 2, "vacant": 2},
                                      "oxygen-B": {"capacity": 3, "occupied": 2, "vacant": 1}}
    assert lattice["classification"] == "synthetic_test_assumption"
    assert obs["native_initialization"]["value"]["fatal"]["code"] == 1002
    assert obs["native_initialization"]["value"]["approval_state"] == "consumed"
    assert obs["candidate_input"]["value"]["native_qualified"] is None
    assert all(v["status"] == "verified" for v in obs["candidate_input"]["value"]["files"].values())
    assert ctx["engines"]["kmc"]["status"] == "blocked"


def test_hash_mismatch_is_local_and_read_only(tmp_path):
    project, task = inputs("nicu")
    # Deliberately alter bytes after binding a previously valid copy.
    altered = tmp_path / "drc.json"
    altered.write_bytes((ROOT / task["sources"]["drc"]["path"]).read_bytes())
    expected = digest(altered)
    altered.write_bytes(altered.read_bytes() + b" ")
    # A bounded private case folder can include independent archived artifacts.
    for role, ref in task["sources"].items():
        target = tmp_path / role
        target.write_bytes((ROOT / ref["path"]).read_bytes())
        ref["path"] = role
    task["sources"]["drc"] = {"path": "drc.json", "sha256": expected}
    project["evidence_base"] = "."
    for name, data in (("project", project), ("task", task)):
        (tmp_path / (name + ".yaml")).write_text(yaml.safe_dump(data), encoding="utf8")
    before = {p.name: digest(p) for p in tmp_path.iterdir()}
    ctx = inspect_project(tmp_path / "project.yaml", tmp_path / "task.yaml")["contexts"][0]
    assert before == {p.name: digest(p) for p in tmp_path.iterdir()}
    assert ctx["evidence"]["drc"]["status"] == "hash_mismatch"
    assert ctx["observables"]["stable_drc"]["value"] is None
    assert ctx["observables"]["tof"]["value"]["value"] == pytest.approx(81.51277016)


def test_wrong_network_and_cross_project(tmp_path):
    project, task = inputs("fe110")
    task["network_version"] = "0" * 64
    ctx, = inspect(tmp_path, project, task)
    assert ctx["evidence"]["network"]["status"] == "invalid_reference"
    assert ctx["observables"]["electronic_barriers"]["value"] is None
    task["sources"]["network"] = inputs("nicu")[1]["sources"]["network"]
    del task["network_version"]
    ctx, = inspect(tmp_path, project, task)
    assert "Cross-project" in ctx["evidence"]["network"]["reason"]
    assert ctx["observables"]["structures"]["status"] == "unavailable"


def test_missing_optional_engine_and_required_science(tmp_path):
    project, task = inputs("nicu")
    del task["sources"]["configuration"]
    ctx, = inspect(tmp_path, project, task)
    assert ctx["engines"]["mkm"]["status"] == "unassessed"
    assert ctx["observables"]["tof"]["status"] == "missing_scientific_evidence"
    assert ctx["network"]["project_id"] == "demo"


def test_unsupported_format_and_missing_file(tmp_path):
    project, task = inputs("fe110")
    source = ROOT / task["sources"]["intake"]["path"]
    bad = json.loads(source.read_bytes())
    bad["schema_version"] = 9
    (tmp_path / "bad.json").write_text(json.dumps(bad), encoding="utf8")
    project["evidence_base"] = "."
    task["sources"] = {"intake": {"path": "bad.json", "sha256": digest(tmp_path / "bad.json")},
                       "raw_structure": {"path": "missing/CONTCAR", "sha256": "0" * 64}}
    for name, data in (("project", project), ("task", task)):
        (tmp_path / (name + ".yaml")).write_text(yaml.safe_dump(data), encoding="utf8")
    ctx = inspect_project(tmp_path / "project.yaml", tmp_path / "task.yaml")["contexts"][0]
    assert ctx["evidence"]["intake"]["status"] == "unsupported_format"
    assert ctx["evidence"]["raw_structure"]["status"] == "missing_local_file"


def test_traversal_and_role_ambiguity(tmp_path):
    project, task = inputs("fe110")
    task["sources"]["external"] = {"path": "../elsewhere/file", "sha256": "0" * 64}
    project["sources"] = {"dataset": task["sources"]["dataset"]}
    ctx, = inspect(tmp_path, project, task)
    assert ctx["evidence"]["external"]["reason"] == "Path outside evidence base"
    assert ctx["evidence"]["dataset"]["reason"] == "Ambiguous artifact role"
    assert ctx["observables"]["kinetic_parameters"]["value"] is None
    assert ctx["observables"]["electronic_barriers"]["status"] == "available"


def test_duplicate_yaml_role_rejected(tmp_path):
    project, task = pair("fe110")
    path = tmp_path / "ambiguous.yaml"
    path.write_bytes(task.read_bytes() + b"\nsources: {}\n")
    with pytest.raises(ValueError, match="duplicate"):
        inspect_project(project, path)


def test_original_context_only_cli():
    layout = ROOT / "calculations/fe110_co_dissociation_neb_20260718/.research"
    proc = subprocess.run([sys.executable, "-m", "scripts.scientific_intake", "--inspect-project",
                           layout / "project.yaml", layout / "tasks/01_co_dissociation.yaml"],
                          cwd=ROOT, capture_output=True, check=True)
    out = json.loads(proc.stdout)
    assert out["task_id"] == "fe110_co_dissociation_full_test"
    assert out["execution_authorized"] is False
    assert out["contexts"][0]["evidence"] == {}


def test_multiple_reactions_and_operating_points(tmp_path):
    project, task = inputs("nicu")
    task["requested_observables"] = ["electronic_barriers"]
    task["contexts"] = [{"reaction_id": r, "operating_point_id": point, "network_version": task["network_version"]}
                        for r, point in (("ads", "p1"), ("transfer", "p1"), ("ads", "p2"))]
    ctx = inspect(tmp_path, project, task)
    for entry, rid in zip(ctx, ["ads", "transfer", "ads"], strict=True):
        assert list(entry["observables"]["electronic_barriers"]["value"]) == [rid]
    assert [entry["operating_point_id"] for entry in ctx] == ["p1", "p1", "p2"]


def test_partial_intake_distinguishes_archive_and_missing_raw(tmp_path):
    project, task = inputs("fe110")
    task["sources"] = {"intake": task["sources"]["intake"]}
    task["requested_observables"] = ["structures", "electronic_barriers"]
    project["evidence_base"] = "."
    raw = (ROOT / task["sources"]["intake"]["path"]).read_bytes()
    (tmp_path / "intake.json").write_bytes(raw)
    task["sources"]["intake"]["path"] = "intake.json"
    for name, data in (("project", project), ("task", task)):
        (tmp_path / (name + ".yaml")).write_text(yaml.safe_dump(data), encoding="utf8")
    ctx, = inspect_project(tmp_path / "project.yaml", tmp_path / "task.yaml")["contexts"]
    structures = ctx["observables"]["structures"]
    assert structures["status"] == "available"
    assert structures["value"]["IS"]["local_source"]["status"] == "missing_local_file"
    assert ctx["observables"]["electronic_barriers"]["status"] == "missing_scientific_evidence"


def test_decoupled_rate_and_uncertainty_evidence(tmp_path):
    project, task = inputs("nicu")
    del task["sources"]["qualification"]
    ctx, = inspect(tmp_path, project, task)
    assert ctx["observables"]["rate_uncertainty"]["status"] == "missing_scientific_evidence"
    assert ctx["observables"]["native_rates"]["status"] == "available"


def test_cli_rejects_mixed_modes():
    p, t = pair("fe110")
    proc = subprocess.run([sys.executable, "-m", "scripts.scientific_intake", "--inspect-project",
                           p, t, "--operation", "electronic"], cwd=ROOT, capture_output=True)
    assert proc.returncode == 2
    assert b"separate from positional reaction intake" in proc.stderr


def test_independent_identity_catalog_with_no_network(tmp_path):
    file = "tests/fixtures/multiphase/synthetic_identity_domains.json"
    project = dict(version=1, project_id="structural-test")
    task = dict(task_id="catalog", sources={"catalog": {"path": file, "sha256": digest(ROOT / file)}})
    ctx, = inspect(tmp_path, project, task)
    assert ctx["network"] is None
    assert "ordered" in ctx["catalyst_ownership"]["phases"]
    assert ctx["catalyst_ownership"]["interfaces"]
    ctx, = inspect(tmp_path, dict(project, project_id="other"), task)
    assert ctx["catalyst_ownership"] is None
    assert ctx["evidence"]["catalog"]["status"] == "invalid_reference"
