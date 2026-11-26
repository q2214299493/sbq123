"""Replay immutable synthetic Phase 2.5.1 inputs and independently check the native observables."""
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.artifact_io import sha256_bytes, sha256_file, sha256_json
from scripts.native_model import assemble, with_checkpoint

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/multiphase/phase2_5_1"
MATRIX = json.loads((REPORT / "zacros_validation.json").read_bytes())
CASES = MATRIX["cases"]


def archive(case):
    return ZipFile(REPORT / CASES[case]["archive"])


def test_catkinas_target_attempt_distinguishes_native_read_from_solver_acceptance():
    record = json.loads((REPORT / "catkinas_target_attempt.json").read_bytes())
    console = REPORT / "catkinas_target_console.txt"
    assert sha256_file(console) == record["public_console_sha256"]
    original = ROOT / "reports/multiphase/phase2_5/catkinas/INPUT_phase25.m"
    assert record["native_echo_sha256"] == record["native_input_sha256"] == sha256_file(original)
    log = console.read_text(encoding="utf8")
    assert original.read_text().splitlines()[0] in log and "Find 2 reaction site(s) : #1 #2" in log
    assert "No total reaction found" in log and "sym/privsubsasgn" in log
    assert record["exit_code"] == 1 and record["output_mat_files"] == []
    assert all(record["native_read"][k] is None for k in ("native_kf_bar^-1_s^-1", "native_kr_s^-1"))


def inputs(source):
    return assemble("zacros", json.loads(source.read("dataset.json")), json.loads(source.read("configuration.json")))


def restored(source, files, manifest):
    receipt = json.loads(source.read("manifest.json"))["restart_receipt"]
    return with_checkpoint(files, manifest, source.read("input-checkpoint.inf"), receipt)


@pytest.mark.parametrize("case", CASES)
def test_native_archive_hashes_and_static_replay(case):
    record = CASES[case]
    assert sha256_file(REPORT / record["archive"]) == record["archive_sha256"]
    with archive(case) as src:
        files, manifest = inputs(src)
        if case == "resume":
            files, manifest = restored(src, files, manifest)
        assert json.loads(src.read("manifest.json")) == manifest
        for name, digest in manifest["files"].items():
            member = "input-checkpoint.inf" if name == "restart.inf" else name
            assert sha256_bytes(src.read(member)) == digest
        for name, digest in record["outputs_sha256"].items():
            assert sha256_bytes(src.read(name)) == digest
        assert b"> Normal termination <" in src.read("general_output.txt")


def samples(case):
    with archive(case) as src:
        lines = src.read("specnum_output.txt").decode("ascii").splitlines()
    return [list(map(float, line.split())) for line in lines if line.split()[0].isdigit()]


@pytest.mark.parametrize("case,matches,initial", [("mono", 16, [0, 1, 0]), ("dent", 16, [1, 0, 0]),
                                                   ("attractive", 15, [1, 1, 0]), ("interacting", 18, [9, 9, 0])])
def test_native_seed_counts_and_matches(case, matches, initial):
    with archive(case) as src:
        general = src.read("general_output.txt").decode()
    assert "Finished reading initial state input." in general
    assert int(re.search(r"(\d+) lattice events found", general)[1]) == matches
    rows = samples(case)
    assert rows[0][5:] == initial
    for row in rows:
        hcu, hni, h2 = row[5:]
        assert 2*h2 + (2*hcu if case == "dent" else hcu+hni) == (2*initial[0] if case == "dent" else sum(initial))


def test_pair_energetics_and_reverse_rate_response():
    initial, first = samples("interacting")[:2]
    assert initial[4] == pytest.approx(18*0.04)
    assert first[4] == pytest.approx((18-3)*0.04)
    assert first[5:] == [8, 8, 1]
    # All 18 first-event hazards change by the same factor under this shared random stream.
    expected = math.exp(0.75*(3-1)*0.04/(8.617333262145e-5*400))
    assert samples("full")[1][2]/first[2] == pytest.approx(expected, rel=3e-6)
    assert "804010" in CASES["interacting"]["native_warning_codes"]


def test_attractive_pair_absorbing_state():
    rows = samples("attractive")
    assert rows[0][4] == pytest.approx(-0.04)
    assert rows[-1][5:] == [9, 9, -8]
    assert rows[-1][4] == pytest.approx(-18*0.04)
    assert rows[-1][1] == 8 and "801002" in CASES["attractive"]["native_warning_codes"]


def test_checkpoint_continues_exact_reference_trajectory():
    with archive("continuous") as ref, archive("split") as writer, archive("resume") as reader:
        assert writer.read("restart.inf") == reader.read("input-checkpoint.inf")
        assert b"from KMC step 8" in reader.read("general_output.txt")
        assert b"Events occurred:  20" in reader.read("general_output.txt")
        for name in ("procstat_output.txt", "specnum_output.txt"):
            assert writer.read(name) + reader.read(name) == ref.read(name)


@pytest.mark.parametrize("issue", ["source_model", "checkpoint", "receipt_model", "input_file", "absent_file"])
def test_mismatched_checkpoint_rejected(issue):
    with archive("split") as src:
        f, m = inputs(src)
        raw = src.read("restart.inf")
        c = json.loads(src.read("configuration.json"))
        receipt = {"model_sha256": sha256_json(m), "checkpoint_sha256": sha256_bytes(raw)}
        if issue == "checkpoint":
            raw = raw[:-1]
        elif issue == "receipt_model":
            receipt["model_sha256"] = "0"*64
        elif issue == "input_file":
            f["mechanism_input.dat"] += "\n"
        elif issue == "absent_file":
            del f["lattice_input.dat"]
        else:
            c["zacros"]["seed"] += 1
            f, m = assemble("zacros", json.loads(src.read("dataset.json")), c)
        with pytest.raises(ValueError, match="receipt|checkpoint-producing"):
            with_checkpoint(f, m, raw, receipt)


def test_reversed_dentate_seed_rejected_before_publication():
    with archive("dent") as src:
        c = json.loads(src.read("configuration.json"))
        c["zacros"]["seeds"][0][1].reverse()
        with pytest.raises(ValueError, match="dentate order"):
            assemble("zacros", json.loads(src.read("dataset.json")), c)


def test_restart_cli_preserves_checkpoint_and_rejects_wrong_receipt(tmp_path):
    with archive("resume") as src:
        receipt = json.loads(src.read("manifest.json"))["restart_receipt"]
        for name in ("dataset.json", "configuration.json", "input-checkpoint.inf"):
            (tmp_path / name).write_bytes(src.read(name))
    receipt_file = tmp_path / "receipt.json"
    receipt_file.write_text(json.dumps(receipt))
    bundle = tmp_path / "bundle"
    args = [sys.executable, "-m", "scripts.native_model", "zacros", tmp_path/"dataset.json", tmp_path/"configuration.json",
            bundle, "--checkpoint", tmp_path/"input-checkpoint.inf", "--checkpoint-receipt", receipt_file]
    subprocess.run(args, cwd=ROOT, check=True, capture_output=True)
    assert sha256_file(bundle/"restart.inf") == receipt["checkpoint_sha256"]
    receipt_file.write_text(json.dumps(dict(receipt, checkpoint_sha256="0"*64)))
    before = (bundle/"manifest.json").read_bytes()
    bad = subprocess.run(args, cwd=ROOT, capture_output=True)
    assert bad.returncode and b"Checkpoint receipt differs" in bad.stderr
    assert (bundle/"manifest.json").read_bytes() == before


@pytest.mark.parametrize("case", CASES)
def test_archived_zacros_event_count(case):
    # These Ni/Cu dynamic runs have archived evidence, but no current execution plan.
    with archive(case) as src:
        general = src.read("general_output.txt")
    count = int(re.search(rb"Events occurred:\s+(\d+)", general)[1])
    assert count == CASES[case]["native_events_reported"]
    assert CASES[case]["exit_code"] == 0 and b"> Normal termination <" in general


def test_inherited_native_settings_cannot_dispatch(tmp_path):
    # Use inert, non-executable sentinel paths, including flags injected from the environment.
    sentinel = tmp_path / "unapproved"
    env = dict(os.environ, SBQ_ZACROS_BENCHMARK_EXE=str(sentinel), SBQ_MKM_NATIVE_APPROVAL_SOURCE=str(sentinel),
               SBQ_MKM_NATIVE_RUN_ROOT=str(sentinel), PYTEST_ADDOPTS="--catkinas-reviewed-run absent-run absent-decision")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "-q", "-rs",
         "tests/test_mkm_single_point.py::test_live_closed_cycle",
         "tests/test_native_advanced.py::test_archived_zacros_event_count"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "8 passed, 1 skipped" in result.stdout and "on the command line" in result.stdout
    assert not sentinel.exists()
