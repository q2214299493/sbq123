from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

import pytest

from scripts import artifact_io
from scripts.artifact_io import write_json_atomic


def _concurrent_writer(
    target: str,
    writer: int,
    start: multiprocessing.synchronize.Event,
) -> None:
    start.wait()
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


def test_concurrent_atomic_json_writes_produce_one_complete_document(
    tmp_path: Path,
) -> None:
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    target = tmp_path / "shared.json"
    processes = [
        context.Process(target=_concurrent_writer, args=(str(target), index, start))
        for index in range(4)
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=15)
        assert process.exitcode == 0

    payload = json.loads(target.read_text(encoding="utf-8"))
    writer = payload["writer"]
    assert writer in range(4)
    assert payload["payload"] == str(writer) * 100_000
    assert list(tmp_path.glob(".shared.json.*.tmp")) == []
