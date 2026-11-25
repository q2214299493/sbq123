"""Replay synthetic Zacros 4.0 outputs and inject a subprocess double; never invoke Zacros."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from scripts.artifact_io import sha256_file, sha256_json
from scripts.native_model import assemble
from scripts.surface_kmc import workflow
from scripts.surface_kmc.observations import check_lattice_output, join_samples, read_trajectory
from scripts.kinetic_parameters.export import zacros as event_table
from scripts.surface_kmc.study import replay
from scripts.surface_kmc.topology import topology
from test_kinetic_parameters import ROOT

BENCH = ROOT / "reports/multiphase/phase2_5_1/benchmarks"


def bundle(case):
    with ZipFile(BENCH / (case + ".zip")) as z:
        return {n: z.read(n) for n in z.namelist()}


def inputs(raw):
    return [json.loads(raw[k + ".json"]) for k in ("dataset", "configuration")]


def parse(blob, parent=None, limit=20):
    d, c = inputs(blob)
    return read_trajectory(
        blob,
        d,
        assemble("zacros", d, c)[1]["validation"],
        event_table(d)["events"],
        max_steps=limit,
        parent=parent,
    )


def test_native_split_join_replays_every_sample():
    continuous, writer, reader = (bundle(k) for k in ("continuous", "split", "resume"))
    d, c = inputs(continuous)
    walk = topology(c["zacros"], d["catalog"])[3]
    check_lattice_output(continuous["lattice_output.txt"], walk)
    changed_cell = continuous["lattice_output.txt"].replace(
        b"9.0000000000000000E+00", b"7.0000000000000000E+00", 1
    )
    with pytest.raises(ValueError, match="cell vectors"):
        check_lattice_output(changed_cell, walk)
    reference, start = parse(continuous), parse(writer, limit=8)
    end = parse(reader, start)
    for key in ("specnum", "procstat"):
        assert join_samples(start[key], end[key]) == reference[key]
        assert join_samples(start[key], start[key][-1:]) == start[key]
    assert end["terminal_step"] == 20 and end["specnum"][-1][0] == 19
    assert parse(bundle("attractive"))["absorbing"]


@pytest.mark.parametrize(
    "file,mutation",
    [
        ("general_output.txt", lambda b: b.replace(b"Finished reading simulation", b"Skipped simulation")),
        ("general_output.txt", lambda b: b + b"\nError code 1002"),
        ("general_output.txt", lambda b: b.replace(b"Events occurred:  20", b"Events occurred:  21")),
        ("procstat_output.txt", lambda b: b.rsplit(b"configuration", 1)[0]),
        ("specnum_output.txt", lambda b: b.replace(b"HNi*", b"HCu*")),
    ],
)
def test_reject_corrupt_zero_exit_streams(file, mutation):
    raw = bundle("continuous")
    raw[file] = mutation(raw[file])
    with pytest.raises(ValueError):
        parse(raw)


@pytest.fixture
def dispatch(tmp_path, monkeypatch):
    executable = tmp_path / "inert-file"
    executable.write_bytes(b"synthetic test only")
    monkeypatch.setattr(workflow, "ENGINE", sha256_file(executable))
    import scripts.surface_kmc.study as study

    monkeypatch.setattr(study, "ENGINE", workflow.ENGINE)
    raw = bundle("continuous")
    d, c = inputs(raw)
    calls = []

    def args(run, limit, parent=None):
        return dict(
            dataset=d,
            config=c,
            executable=executable,
            run=tmp_path / run,
            max_steps=limit,
            timeout_s=2,
            output_bytes=1_000_000,
            parent=parent,
        )

    def approve(a):
        plan = workflow.prepare(**a)[0]
        src = tmp_path / (Path(a["run"]).name + "-review.txt")
        src.write_text("test-only human review of " + sha256_json(plan))
        decision = src.with_suffix(".json")
        decision.write_text(
            json.dumps(
                dict(
                    format="zacros-4-single-call-approval/1",
                    DECISION="approve",
                    ALLOWED_ACTIONS=[plan["action"]],
                    reviewer="synthetic reviewer",
                    state_sha256=sha256_json(plan),
                    source=dict(path=str(src), sha256=sha256_file(src)),
                )
            )
        )
        return decision

    def stub(mode):
        def call(command, **kw):
            calls.append(command)
            assert kw["env"]["OMP_NUM_THREADS"] == "1" and kw["timeout"] == 2
            if mode == "timeout":
                raise subprocess.TimeoutExpired(command, 2)
            if mode == "error":
                return SimpleNamespace(returncode=3)
            for name, body in bundle(mode).items():
                if name in {*workflow.STREAMS, "restart.inf", "lattice_output.txt"}:
                    (kw["cwd"] / name).write_bytes(body)
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(workflow.subprocess, "run", call)

    return args, approve, stub, calls


def test_controller_claim_resume_and_offline_analysis(dispatch):
    args, approve, stub, calls = dispatch
    a = args("first", 8)
    dec = approve(a)
    stub("split")
    with pytest.raises(ValueError, match="stale"):
        workflow.execute(**dict(a, max_steps=9), decision=dec)
    assert not calls
    assert workflow.execute(**a, decision=dec)["status"] == "validated_output"
    b = args("second", 20, a["run"])
    with pytest.raises(PermissionError):
        workflow.execute(**b, decision=dec)
    stub("resume")
    result = workflow.execute(**b, decision=approve(b))
    assert result["terminal_step"] == 20 and result["status"] == "validated_output"
    series = replay(a["dataset"], a["config"], b["run"])
    assert series["trajectory"]["procstat"] == parse(bundle("continuous"))["procstat"]
    (a["run"] / "restart.inf").write_bytes(b"changed")
    with pytest.raises(ValueError):
        workflow.prepare(**b)
    assert len(calls) == 2


@pytest.mark.parametrize("mode,status", [("timeout", "timeout"), ("error", "failed"), ("split", "failed")])
def test_one_call_even_after_failure_or_run_directory_move(dispatch, mode, status):
    args, approve, stub, calls = dispatch
    a = args("first", 8)
    if mode == "split":
        a["output_bytes"] = 16
    dec = approve(a)
    stub(mode)
    assert workflow.execute(**a, decision=dec)["status"] == status
    a["run"].rename(a["run"].with_name("moved"))
    with pytest.raises(FileExistsError):
        workflow.execute(**a, decision=dec)
    assert len(calls) == 1


def test_changed_external_review_denies_before_claim(dispatch):
    args, approve, _, calls = dispatch
    a = args("first", 8)
    dec = approve(a)
    dec.with_suffix(".txt").write_text("superseded")
    with pytest.raises(PermissionError, match="source"):
        workflow.execute(**a, decision=dec)
    assert not calls and not a["run"].exists()


def test_concurrent_approvals_consume_one_call(dispatch):
    from concurrent.futures import ThreadPoolExecutor

    args, approve, stub, calls = dispatch
    a = args("race", 8)
    decision = approve(a)
    stub("error")

    def attempt():
        try:
            return workflow.execute(**a, decision=decision)["status"]
        except FileExistsError:
            return "consumed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(attempt) for _ in range(2)]
    assert sorted(f.result() for f in results) == ["consumed", "failed"]
    assert len(calls) == 1


def test_explicit_native_collection_checks_seed_locations(tmp_path):
    from test_kmc_spatial_core import open_model

    d, c = open_model()
    c["zacros"]["seeds"] = [["H2-bridge", [1, 2]]]
    manifest = assemble("zacros", d, c)[1]
    walk = manifest["validation"]["topology"]
    general = (
        "ZACROS 4.0\nTotal number of lattice sites: 7\n"
        + "".join(
            f"Finished reading {key} input.\n"
            for key in ("simulation", "lattice", "energetics", "mechanism", "initial state")
        )
        + "Events occurred: 0\nCurrent KMC time: 0.0\n> Normal termination <\n"
    )
    (tmp_path / "general_output.txt").write_text(general)
    (tmp_path / "procstat_output.txt").write_text(
        "Overall r1_forward r2_reverse\nconfiguration 1 0 0.0\n0 0 0\n0 0 0\n"
    )
    (tmp_path / "specnum_output.txt").write_text(
        "Entry Nevents Time Temperature Energy HCu* HNi* H2\n1 0 0.0 400.0 0.0 1 0 0\n"
    )
    lattice = []
    for node in walk["nodes"]:
        i = node["index"]
        links = [j for j in (i - 1, i + 1) if 1 <= j <= 7]
        lattice.append(" ".join(map(str, [i, i, 0, node["type_index"], len(links), *links])))
    (tmp_path / "lattice_output.txt").write_text("\n".join(lattice))
    path = tmp_path / "history_output.txt"
    history = (
        "Surface_Species: HCu* HNi*\nconfiguration 1 0 0.0 400.0 0.0\n"
        "1 1 1 1\n2 1 1 2\n3 3 0 1\n4 4 0 1\n5 5 0 1\n6 6 0 1\n7 7 0 1\n"
    )
    path.write_text(history)
    plan = dict(max_output_bytes_per_file=4096, max_steps=1, lineage=None)
    assert workflow._collect(tmp_path, plan, d, c, manifest)["last_snapshot_step"] == 0
    path.write_text(
        history.replace("1 1 1 1\n2 1 1 2\n3 3 0 1\n4 4 0 1", "1 3 0 1\n2 4 0 1\n3 1 1 1\n4 1 1 2")
    )
    with pytest.raises(ValueError, match="seed locations"):
        workflow._collect(tmp_path, plan, d, c, manifest)


@pytest.fixture
def spatial_segment(dispatch, monkeypatch):
    """Inert dispatcher with event-one native text, global events and segment-local configuration ordinals."""
    from test_kmc_spatial_core import open_model

    args, approve, _, calls = dispatch
    d, c = open_model()
    c["zacros"].update(snapshot_every_events=4, write_restart=True)
    mapping = assemble("zacros", d, c)[1]["validation"]
    walk = mapping["topology"]

    def segment(
        name,
        end,
        frames,
        parent=None,
        *,
        include_terminal=False,
        truncate=False,
        event_offset=0,
        bad_clock=False,
        clock_offset=0,
        interrupt=False,
    ):
        a = dict(args(name, end, parent), dataset=d, config=c)
        start = json.loads((parent / "result.json").read_bytes())["terminal_step"] if parent else 0

        def call(command, **kw):
            calls.append(command)
            folder = kw["cwd"]
            if parent:
                general = (
                    f"This is restart No 1 from KMC step {start} and t = {start + clock_offset}.0\n"
                    "Restart information successfully read from file restart.inf.\n"
                )
            else:
                general = "ZACROS 4.0\nTotal number of lattice sites: 7\n" + "".join(
                    f"Finished reading {k} input.\n"
                    for k in ("simulation", "lattice", "energetics", "mechanism")
                )
                lattice = []
                for node in walk["nodes"]:
                    i = node["index"]
                    links = [j for j in (i - 1, i + 1) if 1 <= j <= 7]
                    lattice.append(" ".join(map(str, [i, i, 0, node["type_index"], len(links), *links])))
                (folder / "lattice_output.txt").write_text("\n".join(lattice))
            (folder / "general_output.txt").write_text(
                general + f"Events occurred: {end}\nCurrent KMC time: {end + clock_offset}.0\n"
                "Restart information successfully written in file restart.inf.\n> Normal termination <\n"
            )
            (folder / "restart.inf").write_bytes(f"synthetic checkpoint {end}".encode())
            proc = [] if parent else ["Overall r1_forward r2_reverse"]
            spec = [] if parent else ["Entry Nevents Time Temperature Energy HCu* HNi* H2"]
            for entry, n in enumerate(range(start, end + int(include_terminal)), 1):
                state = n % 2
                spec.append(f"{entry} {n} {n + clock_offset}.0 400.0 0.0 {state} 0 {-state}")
                proc.extend(
                    [
                        f"configuration {entry} {n} {n + clock_offset}.0",
                        "0 0 0",
                        f"{n} {(n + 1) // 2} {n // 2}",
                    ]
                )
            (folder / "specnum_output.txt").write_text("\n".join(spec))
            (folder / "procstat_output.txt").write_text("\n".join(proc))
            if frames is not None:
                history = [] if parent else ["Surface_Species: HCu* HNi*"]
                for entry, n in enumerate(frames, 1):
                    history.append(
                        f"configuration {entry} {n + event_offset} {n + clock_offset + int(bad_clock)}.0 400.0 0.0"
                    )
                    sites = [f"{i} {i} 0 1" for i in range(1, 8)]
                    if n % 2:
                        sites[:2] = ["1 1 1 1", "2 1 1 2"]
                    history.extend(sites)
                if truncate:
                    history.pop()
                (folder / "history_output.txt").write_text("\n".join(history))
            if interrupt:
                raise subprocess.TimeoutExpired(command, kw["timeout"])
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(workflow.subprocess, "run", call)
        return a, workflow.execute(**a, decision=approve(a))

    return segment


def test_spatial_lineage_across_short_and_multiple_segments(spatial_segment):
    parent = None
    for name, end, frames, first, last in [
        ("writer", 5, [0, 4], 0, 4),
        ("short", 7, None, None, 4),
        ("boundary", 8, [], None, 4),
        ("resume", 13, [8, 12], 8, 12),
        ("later", 18, [16], 16, 16),
    ]:
        a, result = spatial_segment(name, end, frames, parent)
        assert result["status"] == "validated_output", result
        assert (result["first_snapshot_step"], result["last_snapshot_step"]) == (first, last)
        if parent:
            writer = json.loads((parent / "result.json").read_bytes())
            assert (
                json.loads((a["run"] / "claim.json").read_bytes())["plan"]["lineage"]["last_snapshot_step"]
                == writer["last_snapshot_step"]
            )
        parent = a["run"]
    trajectory = replay(a["dataset"], a["config"], parent)["trajectory"]
    assert [n for n, _, _ in trajectory["specnum"]] == list(range(18))
    assert trajectory["procstat"][-1][2] == {"r1_forward": 9, "r2_reverse": 8}
    path = parent / "history_output.txt"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="Spatial output differs"):
        replay(a["dataset"], a["config"], parent)


@pytest.mark.parametrize(
    "frames,kwargs,message",
    [
        ([4, 8, 12], {}, "Expected global snapshot"),  # writer's last frame repeated
        ([12], {}, "Expected global snapshot"),  # first eligible child frame omitted
        ([8, 8, 12], {}, "Nonmonotone history"),
        ([8], {}, "Missing scheduled snapshot"),  # last due frame absent
        (None, {}, "Missing scheduled snapshot"),
        ([8, 12], {"event_offset": -6}, "Expected global snapshot"),  # local Nevents without a global binding
        ([8, 12], {"bad_clock": True}, "event clock"),
        ([8, 12], {"clock_offset": 1}, "terminal clock"),
        ([8, 12], {"truncate": True}, "Truncated"),
    ],
)
def test_invalid_spatial_continuation_is_consumed(spatial_segment, frames, kwargs, message):
    a, parent = spatial_segment("writer", 6, [0, 4])
    assert parent["status"] == "validated_output"
    b, child = spatial_segment("reader", 14, frames, a["run"], **kwargs)
    assert child["status"] == "failed" and message in child["error"]
    with pytest.raises(ValueError, match="Incompatible checkpoint writer"):
        workflow.prepare(**dict(b, run=b["run"].with_name("next"), parent=b["run"], max_steps=18))
    assert (b["run"] / "claim.json").is_file()


def test_sampled_terminal_and_legacy_writer(spatial_segment):
    a, parent = spatial_segment("writer", 8, [0, 4, 8], include_terminal=True)
    assert parent["last_snapshot_step"] == 8
    # Reproduce the old root receipt layout in this temporary fixture.
    del parent["first_snapshot_step"]
    path = a["run"] / "result.json"
    path.write_text(json.dumps(parent))
    before = path.read_bytes()
    b, child = spatial_segment("reader", 14, [12], a["run"])
    assert (child["first_snapshot_step"], child["last_snapshot_step"]) == (12, 12)
    assert replay(b["dataset"], b["config"], b["run"])["trajectory"]["terminal_step"] == 14
    assert path.read_bytes() == before
    parent.pop("last_snapshot_step")
    path.write_text(json.dumps(parent))
    with pytest.raises(ValueError, match="writer last_snapshot_step"):
        workflow.prepare(**dict(b, run=b["run"].with_name("missing")))


def test_interruption_preserves_writer_and_consumes_child(spatial_segment):
    a, _ = spatial_segment("writer", 6, [0, 4])
    path = a["run"] / "result.json"
    before = path.read_bytes()
    b, child = spatial_segment("partial", 14, [8], a["run"], interrupt=True)
    assert child["status"] == "timeout" and "last_snapshot_step" not in child
    with pytest.raises(FileExistsError):
        spatial_segment("partial", 14, [8, 12], a["run"])
    with pytest.raises(ValueError, match="Incompatible checkpoint writer"):
        workflow.prepare(**dict(b, run=b["run"].with_name("next"), parent=b["run"], max_steps=18))
    assert path.read_bytes() == before


def test_legacy_child_is_revalidated_before_a_new_continuation(spatial_segment):
    a, _ = spatial_segment("writer", 6, [0, 4])
    b, receipt = spatial_segment("legacy", 14, [8, 12], a["run"])
    folder = b["run"]
    claim_path = folder / "claim.json"
    claim = json.loads(claim_path.read_bytes())
    plan = claim["plan"]
    for key in ("last_snapshot_step", "terminal_time_s"):
        del plan["lineage"][key]
    del receipt["first_snapshot_step"]
    receipt["plan_sha256"] = claim["approval"]["state_sha256"] = sha256_json(plan)
    claim["decision_sha256"] = sha256_json(claim["approval"])
    claim_path.write_text(json.dumps(claim))
    (folder.parent / f".zacros-{sha256_json(plan)}.claim.json").write_bytes(claim_path.read_bytes())
    receipt_path = folder / "result.json"
    receipt_path.write_text(json.dumps(receipt))
    before = receipt_path.read_bytes()
    child, result = spatial_segment("third", 18, [16], folder)
    assert result["first_snapshot_step"] == 16 and receipt_path.read_bytes() == before
    assert replay(child["dataset"], child["config"], child["run"])["trajectory"]["terminal_step"] == 18
    # A self-consistent legacy receipt could have skipped the first child frame.
    history = folder / "history_output.txt"
    history.write_bytes(b"configuration" + history.read_bytes().split(b"configuration")[-1])
    receipt["outputs"]["history_output.txt"] = sha256_file(history)
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="Expected global snapshot step 8"):
        workflow.prepare(**dict(child, run=folder.with_name("invalid")))
