from __future__ import annotations

import errno
import json
import multiprocessing
from pathlib import Path
import sys
import threading

import pytest

from scripts import artifact_io
from scripts.artifact_io import write_json_atomic


def _concurrent_writer(
    target: str,
    writer: int,
    start: multiprocessing.synchronize.Event,
    writes: int = 1,
) -> None:
    assert start.wait(timeout=10)
    for _ in range(writes):
        write_json_atomic(
            Path(target),
            {"writer": writer, "payload": str(writer) * 100_000},
        )


def test_atomic_json_write_replaces_content_without_leaving_temporary_files(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state.json"
    target.write_text('{"old": true}\n', encoding="utf-8")

    assert write_json_atomic(target, {"new": "值"}) == target
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": "值"}
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


def test_atomic_json_output_format_remains_byte_compatible(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    payload = {"unicode": "值", "nested": [1, True, None]}

    write_json_atomic(target, payload)

    expected = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    assert target.read_text(encoding="utf-8") == expected


def test_atomic_json_write_cleans_temporary_file_after_serialization_failure(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state.json"
    target.write_text('{"preserved": true}\n', encoding="utf-8")

    with pytest.raises(TypeError):
        write_json_atomic(target, {"invalid": object()})

    assert json.loads(target.read_text(encoding="utf-8")) == {"preserved": True}
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


def test_atomic_json_write_uses_a_unique_temporary_file_per_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names: list[str] = []
    original = artifact_io.tempfile.mkstemp

    def capture_name(*args: object, **kwargs: object) -> tuple[int, str]:
        descriptor, name = original(*args, **kwargs)
        names.append(name)
        return descriptor, name

    monkeypatch.setattr(artifact_io.tempfile, "mkstemp", capture_name)
    target = tmp_path / "state.json"
    write_json_atomic(target, {"value": 1})
    write_json_atomic(target, {"value": 2})

    assert len(names) == len(set(names)) == 2


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_atomic_write_retries_windows_conflicts_using_the_same_complete_temporary_file(tmp_path, monkeypatch, winerror):
    target = tmp_path / "state.json"
    original_bytes = b'{"old": true}\n'
    target.write_bytes(original_bytes)
    payload = {"new": "值"}
    expected_bytes = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    sources = []
    waits = []
    original_replace = artifact_io.os.replace

    def replace(source, destination):
        sources.append(source)
        assert source.read_bytes() == expected_bytes
        if len(sources) <= 2:
            assert target.read_bytes() == original_bytes
            error = OSError(errno.EACCES, "simulated Windows contention")
            error.winerror = winerror
            raise error
        return original_replace(source, destination)

    monkeypatch.setattr(artifact_io.os, "replace", replace)
    monkeypatch.setattr(artifact_io.time, "sleep", waits.append)
    assert write_json_atomic(target, payload) == target
    assert len(sources) == 3 and len(set(sources)) == 1
    assert len(waits) == 2 and all(delay > 0 for delay in waits)
    assert target.read_bytes() == expected_bytes
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_persistent_windows_conflict_has_bounded_retries_and_preserves_original(tmp_path, monkeypatch, winerror):
    target = tmp_path / "state.json"
    original_bytes = b'{"preserved": true}\n'
    target.write_bytes(original_bytes)
    error = OSError(errno.EACCES, "persistent Windows denial")
    error.winerror = winerror
    attempts = []
    waits = []

    def fail_replace(source, destination):
        attempts.append(source)
        raise error

    monkeypatch.setattr(artifact_io.os, "replace", fail_replace)
    monkeypatch.setattr(artifact_io.time, "sleep", waits.append)
    with pytest.raises(OSError) as caught:
        write_json_atomic(target, {"replacement": True})
    assert caught.value is error
    assert 1 < len(attempts) <= 10
    assert len(waits) == len(attempts) - 1 and 0 < sum(waits) <= 1.0
    assert target.read_bytes() == original_bytes
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


@pytest.mark.parametrize(("error_number", "winerror"), [
    (errno.EACCES, None), (errno.ENOENT, None), (errno.ENOSPC, None),
    (errno.EACCES, 19), (errno.ENOSPC, 112), (errno.EINVAL, 123),
])
def test_unrelated_replace_errors_fail_immediately_without_touching_original(tmp_path, monkeypatch, error_number, winerror):
    target = tmp_path / "state.json"
    original_bytes = b'{"preserved": true}\n'
    target.write_bytes(original_bytes)
    error = OSError(error_number, "unrelated failure")
    if winerror is not None:
        error.winerror = winerror
    attempts = []
    waits = []

    def fail_replace(source, destination):
        attempts.append(source)
        raise error

    monkeypatch.setattr(artifact_io.os, "replace", fail_replace)
    monkeypatch.setattr(artifact_io.time, "sleep", waits.append)
    with pytest.raises(OSError) as caught:
        write_json_atomic(target, {"replacement": True})
    assert caught.value is error
    assert len(attempts) == 1 and waits == []
    assert target.read_bytes() == original_bytes
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows file-sharing semantics")
def test_atomic_write_recovers_after_windows_destination_handle_is_closed(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "state.json"
    original_bytes = b'{"old": true}\n'
    target.write_bytes(original_bytes)
    blocked = threading.Event()
    released = threading.Event()
    failures: list[BaseException] = []
    native_errors: list[int | None] = []
    original_replace = artifact_io.os.replace
    original_sleep = artifact_io.time.sleep

    def observe_replace(source, destination):
        try:
            return original_replace(source, destination)
        except OSError as exc:
            native_errors.append(exc.winerror)
            blocked.set()
            raise

    def write():
        try:
            write_json_atomic(target, {"new": True})
        except BaseException as exc:
            failures.append(exc)

    def wait_for_reader(delay):
        # Synchronize lock release rather than depending on runner scheduling.
        assert released.wait(timeout=5)
        original_sleep(delay)

    monkeypatch.setattr(artifact_io.os, "replace", observe_replace)
    monkeypatch.setattr(artifact_io.time, "sleep", wait_for_reader)
    worker = threading.Thread(target=write)
    try:
        # Python's Windows file handle does not share delete/rename access.
        with target.open("rb") as reader:
            worker.start()
            assert blocked.wait(timeout=5), "Expected a real Windows rename conflict"
            assert reader.read() == original_bytes
    finally:
        released.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert native_errors and all(code in {5, 32, 33} for code in native_errors)
    assert failures == []
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


@pytest.mark.parametrize("writes", [1, 20])
def test_concurrent_atomic_json_writes_produce_one_complete_document(
    tmp_path: Path,
    writes: int,
) -> None:
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    target = tmp_path / "shared.json"
    processes = [
        context.Process(target=_concurrent_writer, args=(str(target), index, start, writes))
        for index in range(4)
    ]
    try:
        for process in processes:
            process.start()
        start.set()
        for process in processes:
            process.join(timeout=30)
        assert [process.exitcode for process in processes] == [0] * len(processes)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)

    payload = json.loads(target.read_text(encoding="utf-8"))
    writer = payload["writer"]
    assert writer in range(4)
    assert payload["payload"] == str(writer) * 100_000
    assert list(tmp_path.glob(".shared.json.*.tmp")) == []



def _exclusive_writer(target: str, writer: int, start, result) -> None:
    start.wait(timeout=10)
    try:
        artifact_io.write_json_exclusive(Path(target), {"writer": writer})
    except FileExistsError:
        result.put("blocked")
    else:
        result.put("reserved")


def test_exclusive_reservation_across_processes(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    path = tmp_path / "reservation.json"
    workers = [context.Process(target=_exclusive_writer, args=(str(path), i, start, results)) for i in range(4)]
    for worker in workers:
        worker.start()
    start.set()
    statuses = [results.get(timeout=20) for _ in workers]
    for worker in workers:
        worker.join(timeout=20)
        assert worker.exitcode == 0
    assert statuses.count("reserved") == 1
    assert statuses.count("blocked") == 3
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        artifact_io.write_json_exclusive(path, {"replacement": True})
    assert path.read_bytes() == original


def test_exclusive_writer_keeps_interrupted_marker(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "reservation.json"

    def fail_sync(descriptor):
        raise OSError("simulated crash during fsync")

    monkeypatch.setattr(artifact_io.os, "fsync", fail_sync)
    with pytest.raises(OSError, match="fsync"):
        artifact_io.write_json_exclusive(path, {"reserved": True})
    assert path.exists()
    with pytest.raises(FileExistsError):
        artifact_io.write_json_exclusive(path, {"retry": True})
