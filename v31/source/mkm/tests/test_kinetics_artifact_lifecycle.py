import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scripts.kinetics_test_artifacts import cleanup_proposal, create_run, seal_run


def start(parent, suite="mkm"):
    return create_run(parent, suite, nodeid="tests::case", revision="synthetic-test",
                      command=["pytest", "tests::case"], versions={"pytest": pytest.__version__},
                      seed=123)


def alias_case(run):
    target = run / "scratch/case0"
    target.mkdir()
    alias = run / "scratch/casecurrent"
    alias.symlink_to(target, target_is_directory=True)
    return alias.relative_to(run).as_posix()


def review(run, digest, refs=None):
    return cleanup_proposal(run, digest, current_references=refs or {})


def test_concurrent_runs(tmp_path):
    suites = ["mkm", "kmc"] * 6
    with ThreadPoolExecutor(6) as pool:
        runs = list(pool.map(lambda suite: start(tmp_path, suite), suites))
    assert len(set(runs)) == len(suites)
    for i, run in enumerate(runs):
        (run / "inputs/model").write_text(str(i))
        meta = json.loads((run / "run.json").read_bytes())
        assert meta["suite"] == suites[i] and meta["run_id"] == run.name
        assert meta["seed"] == 123 and meta["versions"]["pytest"] == pytest.__version__
    assert [int((p / "inputs/model").read_text()) for p in runs] == list(range(12))


def test_process_interruption_preserves_partial_output(tmp_path):
    code = """
import os, sys
from pathlib import Path
from scripts.kinetics_test_artifacts import create_run
run = create_run(Path(sys.argv[1]), 'kmc', nodeid='x', revision='test',
                 command=['pytest'], versions={'fixture':'1'})
(run / 'outputs/partial').write_bytes(b'partial')
os._exit(27)
"""
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], check=False,
                            cwd=Path(__file__).resolve().parents[1])
    assert result.returncode == 27
    run, = tmp_path.iterdir()
    with pytest.raises(FileNotFoundError):
        review(run, "0" * 64)
    assert (run / "outputs/partial").read_bytes() == b"partial"
    assert start(tmp_path) != run


def test_equal_hashes_keep_identity_and_accepted(tmp_path):
    run = start(tmp_path)
    files = ["inputs/fixture", "outputs/replay", "scratch/ACCEPTED.json"]
    for name in files:
        (run / name).write_bytes(b'{"fixture":true}')
    digest = seal_run(run, classes={files[0]: "fixture", files[2]: "pytest-alias"}, references={})
    entries = json.loads((run / "manifest.json").read_bytes())["entries"]
    assert len({entries[k]["sha256"] for k in files}) == 1
    assert [entries[k]["class"] for k in files] == ["fixture", "unknown", "historical-evidence"]
    assert review(run, digest)["candidates"] == []
    with pytest.raises(FileExistsError):
        seal_run(run, classes={}, references={})


def test_alias_to_accepted_bundle_is_held(tmp_path):
    run = start(tmp_path)
    alias = alias_case(run)
    (run / "scratch/case0/ACCEPTED.json").write_text("{}")
    digest = seal_run(run, classes={alias: "pytest-alias"}, references={})
    proposal = review(run, digest)
    assert proposal["held_aliases"] == {alias: "protected evidence or fixture directory"}
    assert not proposal["candidates"]


def test_reference_blocks_and_missing_source_fails_closed(tmp_path):
    run = start(tmp_path)
    alias = alias_case(run)
    source = tmp_path / "historical-index"
    source.write_text(alias)
    with pytest.raises(FileNotFoundError):
        seal_run(run, classes={}, references={alias: [tmp_path / "missing"]})
    with pytest.raises(ValueError, match="missing target"):
        seal_run(run, classes={}, references={"scratch/absent": [source]})
    digest = seal_run(run, classes={alias: "pytest-alias"}, references={alias: [source]})
    proposal = review(run, digest)
    assert proposal["held_aliases"] == {alias: "referenced path"} and not proposal["candidates"]
    source.rename(tmp_path / "relocated")
    with pytest.raises(FileNotFoundError):
        review(run, digest)


def test_proposal_is_bound_and_never_executes(tmp_path):
    run = start(tmp_path)
    alias = alias_case(run)
    (run / "scratch/fakecurrent").write_text("regular")
    outside = run / "scratch/escapecurrent"
    outside.symlink_to(tmp_path, target_is_directory=True)
    names = (alias, "scratch/fakecurrent", "scratch/escapecurrent")
    digest = seal_run(run, classes=dict.fromkeys(names, "pytest-alias"), references={})
    proposal = review(run, digest)
    assert proposal["candidates"] == [alias]
    assert set(proposal["held_aliases"]) == set(names[1:])
    assert proposal["approval_required"] and not proposal["deletion_authorized"]
    assert os.path.islink(run / alias)
    index = tmp_path / "later-index"
    index.write_text("scratch")
    assert review(run, digest, {"scratch": [index]})["candidates"] == []
    with pytest.raises(ValueError, match="binding"):
        review(run, "0" * 64)
    (run / "scratch/case0/new").touch()
    with pytest.raises(ValueError, match="contents changed"):
        review(run, digest)


@pytest.mark.parametrize("suite", ["mkm", "kmc"])
def test_backup_and_restore_to_fresh_location(tmp_path, suite):
    run = start(tmp_path, suite)
    (run / "inputs/model").write_text("reference")
    (run / "outputs/result").write_text("result")
    (run / "logs/run.log").write_text("done")
    digest = seal_run(run, classes={"outputs/result": "regression"}, references={})
    backup = shutil.copytree(run, tmp_path / "backup" / run.name)
    with pytest.raises(FileExistsError):
        shutil.copytree(run, backup)
    restored = shutil.copytree(backup, tmp_path / "restore" / run.name)
    assert review(restored, digest) == review(run, digest)
    (restored / "outputs/result").write_text("corrupt")
    with pytest.raises(ValueError, match="contents changed"):
        review(restored, digest)
    assert (backup / "outputs/result").read_text() == "result"

