"""Routine tests replay a MAT fixture. Native execution is a separate explicit opt-in."""

import os
from pathlib import Path
import shutil
import sqlite3
import subprocess

import pytest
from scipy.io import loadmat, savemat

from scripts.artifact_io import sha256_file, sha256_json, write_json_exclusive as save
from scripts.baseline_mkm import single_point as flow
from scripts.baseline_mkm.registration import registry_batch
from scripts.registry_mutations import plan_registry_batch
from scripts.registry_schema import migrate_registry
from test_catkinas_closed_cycle import OUT, cycle_model

PHASE = OUT.parent / "phase3_0"
MATLAB = Path("D:/BaiduNetdiskDownload/bin/matlab.exe")


def fixture_ticket(root):
    record = flow.read(PHASE / "benchmark_ticket_fixture.json")
    database = root / "synthetic-ticket.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE tickets (id TEXT PRIMARY KEY, question_id TEXT, status TEXT)")
        db.execute(
            "INSERT INTO tickets VALUES (?,?,?)", (record["ticket_id"], record["question_id"], "READY_FOR_REVIEW")
        )
    return database, record["ticket_id"]


def make_decision(run, source):
    p = flow.read(run / "plan.json")
    return dict(
        format="mkm-execution-approval/1",
        DECISION="approve",
        ALLOWED_ACTIONS=[flow.ACTION],
        state_sha256=sha256_json(p),
        question_id=p["question_id"],
        reviewer="Phase 3.0 synthetic benchmark only",
        source=dict(path=str(source.resolve()), sha256=sha256_file(source)),
    )


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    binary = tmp_path / "fixture.p"
    binary.write_bytes(b"mock binary for CI")
    monkeypatch.setattr(
        flow,
        "tools_for_run",
        lambda p: dict(
            catkinas=dict(source_path=str(binary), sha256=sha256_file(binary)),
            matlab_version="MATLAB 25.2.0.2998904 R2025b",
            matlab_path=str(p),
        ),
    )
    return fixture_ticket(tmp_path)


def start(root, ticket, *, paths=None, name="run"):
    files = paths or (
        PHASE / "closed_cycle_network.json",
        OUT / "cycle_dataset.json",
        PHASE / "workflow_configuration.json",
    )
    return flow.prepare(root / name, *files, *ticket, MATLAB)


def replay(directory, defect=None):
    if defect == "timeout":
        raise subprocess.TimeoutExpired("MATLAB", flow.LIMIT)
    if defect == "exit":
        return 7
    out = directory / "result_phase25"
    out.mkdir()
    shutil.copyfile(directory / flow.INPUT, out / "Input_phase25_1")
    if defect == "echo":
        (out / "Input_phase25_1").write_bytes(b"different")
    input_lines = (directory / flow.INPUT).read_text().splitlines()[:4]
    if defect == "ordering":
        input_lines[:2] = input_lines[1::-1]
    log = "CATKINAS is running now on MATLAB: 25.2.0.2998904 (R2025b) ...\n"
    log += "\n".join(input_lines) + "\n(1):H2+#1+#2<->H#1+H#2 0.785 ORI TST\n"
    log += (OUT / "native_log_extract.txt").read_text()
    for key, old, new in (
        ("convergence", "Succeed!!", "FAILED"),
        ("symbols", "Q1_HNO]", "Q1_H  ]"),
        ("unfinished", "CATKINAS is finished now", "incomplete"),
        ("temperature", "T = 400;", "T = 450;"),
    ):
        if defect == key:
            log = log.replace(old, new)
    (out / "log1").write_text(log, encoding="ascii")
    (directory / "console.log").write_text("CATKINAS version : 20230524", encoding="ascii")
    if defect == "missing_mat":
        return 0
    if defect in {"site", "mass", "negative", "flux", "steady", "pressure", "coefficient"}:
        data = {k: v for k, v in loadmat(OUT / "data1.mat").items() if not k.startswith("_")}
        if defect == "site":
            data["y"][0, 2] += 0.01
        elif defect == "mass":
            data["Rnets"][0, 1] += 1
        elif defect == "negative":
            data["R"][0, 0, 0] = -1
        elif defect == "flux":
            data["R"][0, 0, :2] += 1
        elif defect == "coefficient":
            data["kf"][0, 0] *= 1.01
        elif defect == "steady":
            data["y"][0, 0] += 0.01
            data["y"][0, 2] -= 0.01
            from test_catkinas_closed_cycle import independent_flux

            f, r = independent_flux(data["y"][0, [0, 1, 3]], data["kf"][0], data["kr"][0])
            data["R"][0, :, 0], data["R"][0, :, 1], data["R"][0, :, 2] = f, r, f - r
            data["Rnet"][0] = f - r
        else:
            data["params"][0, 0] += 0.1
        savemat(out / "data1.mat", data)
    else:
        shutil.copyfile(OUT / "data1.mat", out / "data1.mat")
    return 0


def approved(root):
    path = root / "decision.json"
    save(path, make_decision(root / "run", PHASE / "benchmark_ticket_fixture.json"))
    return path


@pytest.mark.parametrize("project", ["interface", "oxide", "Fe110"])
def test_mocked_multiphase_point(tmp_path, runtime, monkeypatch, project):
    n, d, c = cycle_model(project, with_network=True)
    c.update(
        {
            k: v
            for k, v in flow.read(PHASE / "workflow_configuration.json").items()
            if k in ("overall_stoichiometry", "turnover_basis", "selectivity_products")
        }
    )
    paths = [save(tmp_path / (k + ".json"), v) for k, v in zip(("n", "d", "c"), (n, d, c), strict=True)]
    assert start(tmp_path, runtime, paths=paths)["stage"] == "AWAITING_APPROVAL"
    run = tmp_path / "run"
    monkeypatch.setattr(flow, "launch", lambda directory, executable: replay(directory))
    decision = approved(tmp_path)
    view = flow.execute(run, decision)
    assert view["stages"] == list(flow.STAGES[:-1])
    handoff = view["ticket_handoff"]
    assert set(handoff) == {"ticket_id", "status", "note"}
    assert handoff["ticket_id"] == runtime[1] and handoff["status"] == "READY_FOR_REVIEW"
    assert str((run / "result.json").resolve()) in handoff["note"] and len(handoff["note"]) <= 1000
    assert view["catalyst_project_id"] == n["project_id"] and view["tof_s_inverse"] == pytest.approx(81.51277)
    result = flow.read(run / "result.json")
    assert result["molar_selectivity"] == {"HNO-g": 1} and result["steady_state_residual"] < 1e-8
    assert {s["site_type"] for s in n["catalog"]["sites"]} == {
        t for s in result["species"] for t in s["site_types"]
    }
    assert result["plan_sha256"] == sha256_json(flow.read(run / "plan.json"))
    with pytest.raises(FileExistsError):
        flow.execute(run, decision)
    db = tmp_path / "registry.sqlite"
    migrate_registry(db)
    batch = registry_batch(run, "synthetic reviewer")
    assert plan_registry_batch(db, batch)["insert_count"] == sum(map(len, batch["rows"].values()))
    (run / "runtime/result_phase25/log1").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Changed registered artifact"):
        registry_batch(run, "synthetic reviewer")


@pytest.mark.parametrize(
    "defect,stage",
    [
        ("timeout", "RUNNING"),
        ("exit", "RUNNING"),
        ("missing_mat", "COLLECTING"),
        ("echo", "COLLECTING"),
        ("convergence", "PARSING"),
        ("unfinished", "PARSING"),
        ("symbols", "PARSING"),
        ("negative", "PARSING"),
        ("ordering", "VALIDATING"),
        ("temperature", "VALIDATING"),
        ("site", "VALIDATING"),
        ("mass", "VALIDATING"),
        ("flux", "VALIDATING"),
        ("coefficient", "VALIDATING"),
        ("pressure", "VALIDATING"),
        ("steady", "VALIDATING"),
    ],
)
def test_rejected_run_retains_evidence(tmp_path, runtime, monkeypatch, defect, stage):
    start(tmp_path, runtime)
    monkeypatch.setattr(flow, "launch", lambda directory, executable: replay(directory, defect))
    v = flow.execute(tmp_path / "run", approved(tmp_path))
    assert (v["stage"], v.get("failure_stage")) == ("REJECTED", stage), v
    assert not (tmp_path / "run/result.json").exists()
    if defect == "timeout":
        assert v["execution"] == "timed_out"
    if stage == "VALIDATING":
        assert v["convergence"] == "converged" and v["execution"] == "exited_successfully"


@pytest.mark.parametrize(
    "defect", ["denied", "state", "source", "question", "configuration", "directory", "ticket"]
)
def test_gate_does_not_dispatch(tmp_path, runtime, monkeypatch, defect):
    start(tmp_path, runtime)
    run = tmp_path / "run"
    decision = make_decision(run, PHASE / "benchmark_ticket_fixture.json")
    if defect == "denied":
        decision["ALLOWED_ACTIONS"] = []
    elif defect == "state":
        decision["state_sha256"] = "0" * 64
    elif defect == "source":
        decision["source"]["sha256"] = "0" * 64
    elif defect == "question":
        decision["question_id"] = "0" * 64
    elif defect == "configuration":
        (run / "configuration.json").write_bytes(b"{}")
    elif defect == "ticket":
        with sqlite3.connect(runtime[0]) as db:
            db.execute("update tickets set status='PAUSED'")
    else:
        run = Path(shutil.copytree(run, tmp_path / "copied"))
    p = save(tmp_path / "decision.json", decision)
    monkeypatch.setattr(flow, "launch", lambda *a: pytest.fail("gate dispatched"))
    with pytest.raises((ValueError, PermissionError)):
        flow.execute(run, p)
    assert not (run / "runtime").exists()


def test_fe110_blocked(tmp_path, runtime):
    dataset = OUT.parent / "phase2_4/fe110_parameters.json"
    net = next((OUT.parent / "networks").glob("network-2a80*.json"))
    v = start(tmp_path, runtime, paths=(net, dataset, PHASE / "workflow_configuration.json"))
    assert v["stage"] == "REJECTED" and v["execution"] == "not_started"
    gaps = "; ".join(next(iter(v["missing_data"].values())))
    assert all(s in gaps for s in ("IS:", "FS:", "site occupancies", "phase unconfirmed", "review"))
    assert not (tmp_path / "run/input").exists()


def test_inconsistent_rehashed_dataset(tmp_path, runtime):
    d = flow.read(OUT / "cycle_dataset.json")
    d["reactions"][0]["rates"]["forward"]["activity_coefficient_s^-1"] *= 2
    d["dataset_version"] = sha256_json({k: v for k, v in d.items() if k != "dataset_version"})
    v = start(
        tmp_path,
        runtime,
        paths=(
            PHASE / "closed_cycle_network.json",
            save(tmp_path / "d", d),
            PHASE / "workflow_configuration.json",
        ),
    )
    assert v["stage"] == "REJECTED" and "reviewed rates" in v["missing_data"]


@pytest.mark.skipif(
    not os.environ.get("SBQ_MKM_NATIVE_APPROVAL_SOURCE"),
    reason="explicit native exact-benchmark approval required",
)
def test_live_closed_cycle(tmp_path):
    root = Path(os.environ.get("SBQ_MKM_NATIVE_RUN_ROOT", tmp_path))
    root.mkdir(parents=True, exist_ok=True)
    source = Path(os.environ["SBQ_MKM_NATIVE_APPROVAL_SOURCE"])
    ticket = fixture_ticket(root)
    v = start(root, ticket)
    assert v["stage"] == "AWAITING_APPROVAL", v
    run = root / "run"
    archived = flow.read(OUT / "catkinas_closed_cycle_validation.json")["closed_cycle"]
    assert (
        sha256_file(run / "input" / flow.INPUT)
        == sha256_file(OUT / "catkinas_closed_cycle_input.m")
        == archived["source_sha256"]
    )
    assert sha256_file(OUT / "data1.mat") == archived["result_sha256"]["result_closed_cycle/data1.mat"]
    v = flow.execute(run, save(root / "benchmark_decision.json", make_decision(run, source)))
    assert v["stage"] == "ACCEPTED", v.get("reason")
    assert v["tof_s_inverse"] == pytest.approx(81.51277016, rel=1e-4)
    assert v["validation"]["max_relative_coefficient_error"] < 1e-4


@pytest.mark.parametrize("key,value", [("temperature_K", 500), ("total_pressure_bar", 2)])
def test_requested_conditions_must_match_review(tmp_path, runtime, key, value):
    c = flow.read(PHASE / "workflow_configuration.json")
    c[key] = value
    v = start(
        tmp_path,
        runtime,
        paths=(PHASE / "closed_cycle_network.json", OUT / "cycle_dataset.json", save(tmp_path / "c", c)),
    )
    assert v["stage"] == "REJECTED" and key in v["missing_data"]


def test_published_native_result_replays():
    from scripts.baseline_mkm.single_point_result import validate_result
    from scripts.baseline_mkm.results import read_single_point
    from scripts.native_model import assemble

    d, c = flow.read(OUT / "cycle_dataset.json"), flow.read(PHASE / "workflow_configuration.json")
    files, adapter = assemble("catkinas", d, c)
    manifest = flow.read(PHASE / "benchmark_manifest.json")
    assert all(sha256_file(PHASE / k) == h for k, h in manifest["published_evidence_sha256"].items())
    parsed = read_single_point(PHASE / "data1.mat", PHASE / "native_log_extract.txt")
    r = validate_result(
        d, c, adapter["validation"], parsed, (PHASE / "native_log_extract.txt").read_text(), files[flow.INPUT]
    )
    approved = flow.read(PHASE / "result.json")
    assert all(approved[k] == v for k, v in r.items())
    weights = flow.read(OUT.parents[2] / "tests/fixtures/multiphase/closed_cycle_reference.json")[
        "turnover_stoichiometry"
    ]
    assert sum(
        x["applied_reaction_energy_eV"] * weights[x["reaction_id"]] for x in r["reactions"]
    ) == pytest.approx(-0.16)
