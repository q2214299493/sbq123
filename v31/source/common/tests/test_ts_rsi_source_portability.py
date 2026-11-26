"""Operator-controlled portable RSI source selection; no models or scientific calculations."""
from pathlib import Path
import subprocess

import pytest

from scripts.artifact_io import load_json_object, write_json
from scripts.ts_strategy_engine import rsi_advice, workflow
from tests.test_ts_rsi_integration import ACTUAL_RUNTIME_CHECK, run_plan, trial as synthetic_trial


trial = synthetic_trial


def test_without_rsi_options_keeps_original_behavior(monkeypatch, tmp_path):
    monkeypatch.delenv(rsi_advice.RSI_SOURCE_ROOT_ENV, raising=False)
    assert rsi_advice.prepare_advice(None, None, None) is None
    with pytest.raises(ValueError, match="requires an explicit RSI request"):
        rsi_advice.prepare_advice(None, None, None, source_root=tmp_path)


def test_operator_must_configure_a_source(monkeypatch):
    monkeypatch.delenv(rsi_advice.RSI_SOURCE_ROOT_ENV, raising=False)
    with pytest.raises(ValueError, match="source not configured"):
        rsi_advice._source_root()


def test_operator_source_portable_path_and_precedence(tmp_path, monkeypatch):
    from_env, explicit = tmp_path / "deployed-one", tmp_path / "deployed-two"
    from_env.mkdir()
    explicit.mkdir()
    monkeypatch.setenv(rsi_advice.RSI_SOURCE_ROOT_ENV, str(from_env.resolve()))
    assert rsi_advice._source_root() == from_env.resolve()
    assert rsi_advice._source_root(explicit) == explicit.resolve()
    assert rsi_advice._source_root(explicit) != rsi_advice._source_root()


def test_untrusted_remote_url_relative_and_file_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv(rsi_advice.RSI_SOURCE_ROOT_ENV, "https://example.invalid/rsi")
    with pytest.raises(ValueError, match="absolute directory"):
        rsi_advice._source_root()
    with pytest.raises(ValueError, match="absolute directory"):
        rsi_advice._source_root(Path("relative/checkout"))
    f = tmp_path / "not-a-directory"
    f.write_text("fixture", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory"):
        rsi_advice._source_root(f)


def test_missing_checked_out_directory_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        rsi_advice._source_root(tmp_path / "not-installed")


def test_runtime_rejects_non_git_directory_and_checkout_subdirectory(tmp_path):
    plain = tmp_path / "not git"
    plain.mkdir()
    with pytest.raises(ValueError, match="Git checkout root"):
        rsi_advice._runtime(plain)
    checkout = tmp_path / "synthetic checkout"
    subprocess.run(["git", "init", "--quiet", str(checkout)], check=True, capture_output=True)
    child = checkout / "subdirectory"
    child.mkdir()
    with pytest.raises(ValueError, match="Git checkout root"):
        rsi_advice._runtime(child)


@pytest.mark.parametrize("kind", ["unconfigured", "missing", "relative", "non_git", "wrong_revision"])
def test_invalid_operator_source_stops_real_handler_before_producer(trial, monkeypatch, kind):
    monkeypatch.delenv(rsi_advice.RSI_SOURCE_ROOT_ENV, raising=False)
    monkeypatch.setattr(rsi_advice, "_runtime", ACTUAL_RUNTIME_CHECK)
    root = trial["root"] / "operator checkout"
    if kind == "relative":
        root = Path("relative/checkout")
    elif kind in {"non_git", "wrong_revision"}:
        root.mkdir()
        if kind == "wrong_revision":
            # An actual synthetic Git repository with no approved HEAD must fail.
            subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True)
    args = [] if kind == "unconfigured" else ["--rsi-source-root", str(root)]
    with pytest.raises(ValueError, match="RSI"):
        run_plan(trial, extra_args=args)
    receipt = load_json_object(next(trial["request"].workdir.glob("rsi/*/invocation-result.json")))
    assert receipt["status"] == "unavailable" and receipt["producer_launch_attempted"] is False
    assert not (trial["request"].workdir / "ts_strategy.json").exists()
    assert not (trial["request"].workdir / "rsi_integration.json").exists()


@pytest.mark.parametrize("mode", ["environment", "explicit_over_environment"])
def test_real_handler_forwards_operator_selection_to_synthetic_transport(trial, monkeypatch, mode):
    synthetic_runtime = rsi_advice._runtime
    selected = []
    root = trial["backend"].resolve()
    monkeypatch.setenv(rsi_advice.RSI_SOURCE_ROOT_ENV,
                       str(root) if mode == "environment" else "https://example.invalid/not-a-checkout")
    def record_selection(operator_root=None):
        selected.append(rsi_advice._source_root(operator_root))
        return synthetic_runtime(operator_root)
    monkeypatch.setattr(rsi_advice, "_runtime", record_selection)
    args = ["--rsi-source-root", str(root)] if mode == "explicit_over_environment" else []
    plan = run_plan(trial, extra_args=args)
    assert selected == [root]
    review = plan["workflow_review"]
    assert review["status"] == "ADOPTED_FOR_REVIEW_PLANNING"
    assert review["scientific_review_completed"] is False and review["execution_authorized"] is False
    assert all(item["check_status"] == "PENDING" for item in review["items"])
    binding = load_json_object(trial["request"].workdir / "rsi_integration.json")
    assert binding["execution"] is None and binding["outcome"] is None
    assert binding["invocation"]["runtime"]["synthetic_fixture"] is True


def test_disabled_handler_ignores_source_environment_without_starting_rsi(trial, monkeypatch):
    monkeypatch.setenv(rsi_advice.RSI_SOURCE_ROOT_ENV, "relative/nonexistent")
    def forbidden(*args, **kwargs):
        raise AssertionError("disabled RSI must not resolve or launch a producer")
    monkeypatch.setattr(rsi_advice, "_runtime", forbidden)
    monkeypatch.setattr(rsi_advice, "_source_root", forbidden)
    plan = run_plan(trial, enabled=False)
    assert "workflow_review" not in plan and plan["automatic_submission"] is False
    assert not (trial["request"].workdir / "rsi").exists()


def test_source_flag_without_request_stops_before_workflow(trial, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid explicit options must stop before planning")
    monkeypatch.setattr(workflow, "plan", forbidden)
    with pytest.raises(ValueError, match="requires an explicit RSI request"):
        run_plan(trial, enabled=False, extra_args=["--rsi-source-root", str(trial["backend"])])
    assert not (trial["request"].workdir / "ts_strategy.json").exists()


def test_task_json_cannot_select_executable_source(trial):
    spec = load_json_object(trial["spec"])
    spec["source_root"] = str(trial["backend"])
    write_json(trial["spec"], spec)
    with pytest.raises(ValueError, match="RSI"):
        run_plan(trial)
    receipt = load_json_object(next(trial["request"].workdir.glob("rsi/*/invocation-result.json")))
    assert receipt["producer_launch_attempted"] is False


def test_producer_source_manifest_is_rechecked_before_consumption(trial, monkeypatch):
    original = rsi_advice.prepare_advice
    def changed_producer(*args, **kwargs):
        context = original(*args, **kwargs)
        producer = trial["backend"] / "scripts/ts_strategy_engine/learning_cli.py"
        producer.write_bytes(producer.read_bytes() + b"\n# changed synthetic source\n")
        return context
    monkeypatch.setattr(rsi_advice, "prepare_advice", changed_producer)
    with pytest.raises(ValueError, match="producer source changed"):
        run_plan(trial)
    receipt = load_json_object(trial["request"].workdir / "rsi_rejection.json")
    assert receipt["status"] == "unavailable" and receipt["automatic_execution"] is False
    assert not (trial["request"].workdir / "ts_strategy.json").exists()
