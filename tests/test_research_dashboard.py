"""Local projections and CLI hooks on isolated synthetic runs; no live model/jobs."""
from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
import json
import sys

import pytest

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive, write_json_atomic
from scripts.research_assistant import cli, dashboard_cli
from scripts.research_assistant.dashboard_data import build_run
from scripts.research_assistant.dashboard_registry import rebuild
from scripts.research_assistant.dashboard_render import render, write_html
from scripts.research_assistant.dashboard_sources import costs, bounded_paths
from scripts.research_assistant.policy_cli import policy_command, usage_record

from test_research_policies import execute, propose, run_for, ref, PolicyPeer

pytest_plugins = ["test_research_policies"]


@pytest.fixture
def completed(environment):
    propose(environment, status="trial")
    run = run_for(environment, "completed", trial_policy_ids=["check_registered_material"])
    execute(run)
    return environment, run


def hashes(run):
    return {name: sha256_file(run.output / name) for name in ("run_receipt.json", "research_result.json", "rsi_application.json", "turn-001/model_input.json")}


def request_file(environment, **extra):
    payload = {"adopted": None, "evidence_effectiveness": [], "repeated_checks": [],
               "followup_notes": "Synthetic feedback fixture only", "scientific_result_reference": None,
               "human_review_seconds": None, "human_preparation_seconds": None, "human_correction_seconds": None, **extra}
    path = environment[0] / ("feedback-" + str(len(list(environment[0].glob('feedback-*.json')))) + ".json")
    write_json_exclusive(path, payload)
    return path


def test_actual_input_action_output_correspondence_and_costs_are_projected(completed):
    _, run = completed
    before = hashes(run)
    data = build_run(run.output)
    assert not data["source_errors"] and data["provided_count"] == 1
    assert data["selected_policies"][0]["status_at_run"] == "trial"
    assert data["applications"][0]["action_details"][1]["evidence_id"] == "E002"
    assert data["applications"][0]["outputs"][0]["pointer"] == "/recommended_next"
    assert data["comparison"]["kind"] == "unpaired"
    assert data["value"]["controlled_benefit"] is None and not data["feedback"]
    assert hashes(run) == before
    assert costs({})["host_tool_requests"] is None
    assert costs({"host_tool_requests": 0, "tokens": {"total": {"totalTokens": 0}}})["tokens_total"] == 0
    assert costs({"tokens": {"unexpected": 99}})["tokens_total"] is None


def test_unselected_and_accepted_only_do_not_relabel_current_trial_as_historical_reason(completed):
    environment, _ = completed
    run = run_for(environment, "accepted-only")
    execute(run)
    data = build_run(run.output)
    assert data["provided_count"] == 0 and data["no_policy_explanation"]["recorded_reasons"] == []
    assert "当前" in data["no_policy_explanation"]["current_library_note"]
    assert environment[2].read()["policies"][0]["status"] == "trial"


def test_feedback_refresh_preserves_originals_and_does_not_adopt_policy(completed):
    environment, run = completed
    before = hashes(run)
    path = request_file(environment, adopted=True, rsi_feedback=[{"policy_id": "check_registered_material", "helpful": True,
        "reason": "Synthetic concrete help fixture", "action_refs": ["E002"], "output_refs": ["/recommended_next"]}])
    result = cli.feedback(run.output, path)
    assert "rsi_index_error" not in result
    view = load_json_object(run.output / "views/rsi_view.json")
    assert view["feedback"][0]["usage_feedback"]["adopted"] is True
    assert hashes(run) == before and environment[2].read()["policies"][0]["status"] == "trial"


def test_saved_feedback_is_visible_even_when_project_index_is_pending(completed):
    environment, run = completed
    lock = environment[2].root / "write.lock"
    lock.write_text("synthetic occupied lock", encoding="utf-8")
    result = cli.feedback(run.output, request_file(environment))
    assert result["rsi_index_error"]["status"] == "RSI_INDEX_PENDING_RECONCILIATION"
    view = load_json_object(run.output / "views/rsi_view.json")
    assert view["feedback"] and "待恢复" in view["feedback_index"][0]["label"]
    lock.unlink()


def test_independent_review_refreshes_current_status_and_preserves_frozen_trial(completed):
    environment, run = completed
    dashboard_cli.refresh_run(run.output)
    before = hashes(run)
    record = environment[2].read()["policies"][0]
    request = {"policy_id": record["definition"]["policy_id"], "version": 1, "content_sha256": record["content_sha256"],
        "status": "disabled", "reviewer": "synthetic reviewer", "validation_scope": "synthetic fixture", "validation_refs": [], "reason": "fixture disable"}
    path = environment[0] / "disable.json"
    write_json_exclusive(path, request)
    policy_command(Namespace(store=environment[2].root, project_root=environment[1], action="review", request=path, no_dashboard=False))
    view = load_json_object(run.output / "views/rsi_view.json")
    assert view["current_policies"]["policies"][0]["status"] == "disabled"
    assert view["selected_policies"][0]["status_at_run"] == "trial" and hashes(run) == before


def test_bad_feedback_is_isolated_and_strict_usage_still_rejects(completed):
    environment, run = completed
    cli.feedback(run.output, request_file(environment), no_dashboard=True)
    assert not (run.output / "views").exists()
    (run.output / "feedback/broken.json").write_text("{broken", encoding="utf-8")
    data = build_run(run.output)
    assert len(data["feedback"]) == 1 and data["provided_count"] == 1
    assert data["source_errors"][0]["role"] == "feedback"
    with pytest.raises(ValueError):
        usage_record(run.output)


def test_bad_result_binding_never_supplies_recommendation_or_verified_application(completed):
    _, run = completed
    (run.output / "research_result.json").write_text('{"answer":{"recommended_next":{"action":"FORGED"}}}', encoding="utf-8")
    data = build_run(run.output)
    assert data["recommendation"] is None and data["run"]["status"] == "OFFLINE_TEST_GENERATED"
    assert all(not row["source_verified"] for row in data["applications"])
    assert any(row["role"] == "research_result" for row in data["source_errors"])


def test_missing_or_legacy_freeze_is_unknown_and_missing_costs_stay_unknown(tmp_path):
    run = tmp_path / "legacy"
    run.mkdir()
    write_json_exclusive(run / "run_receipt.json", {"goal": "synthetic failure", "status": "BLOCKED", "first_failure_stage": "test", "problem": "fixture"})
    data = build_run(run)
    assert data["provided_count"] is None and data["usage_state"] == "unknown"
    assert data["costs"]["elapsed_seconds"] is None and data["run"]["problem"] == "fixture"


def pair_document(environment):
    propose(environment)
    rows = []
    runs = {}
    for arm in ("baseline", "candidate"):
        run = run_for(environment, "fixture_" + arm, exclude_policy_ids=["check_registered_material"] if arm == "baseline" else [])
        execute(run)
        rows.append({"name": "fixture_" + arm, "receipt_ref": ref(run.output / "run_receipt.json"),
            "result_ref": ref(run.output / "research_result.json"), "application_ref": ref(run.output / "rsi_application.json"),
            "initial_input_ref": ref(run.output / "turn-001/model_input.json")})
        runs[arm] = run
    path = environment[0] / "paired.json"
    write_json_exclusive(path, {"schema_version": 1, "runs": rows, "condition_checks": [{"task": "fixture", "both_complete": True}],
        "content_review": {"scope": "synthetic fixture"}, "controlled_benefit": True})
    (runs["candidate"].output / "comparisons").mkdir()
    write_json_exclusive(runs["candidate"].output / "comparisons/pair.json", {"run_receipt_sha256": rows[1]["receipt_ref"]["sha256"], "comparison_reference": ref(path)})
    return runs


def test_registered_pair_requires_real_bindings_and_never_promotes_claim_to_benefit(environment):
    runs = pair_document(environment)
    data = build_run(runs["candidate"].output)
    pair = data["comparison"]["paired"][0]
    assert pair["input_conditions_rechecked"] and pair["baseline"]["answer"]
    assert pair["reported_controlled_benefit"] is True and pair["controlled_benefit"] is None
    (runs["baseline"].output / "research_result.json").write_text("{}", encoding="utf-8")
    data = build_run(runs["candidate"].output)
    assert not data["comparison"]["paired"] and any(r["role"] == "paired_run" for r in data["source_errors"])


def test_unknown_comparison_format_is_explicitly_unsupported(completed):
    environment, run = completed
    path = environment[0] / "unknown-pair.json"
    write_json_exclusive(path, {"schema_version": 999, "benefit": True})
    (run.output / "comparisons").mkdir()
    write_json_exclusive(run.output / "comparisons/unknown.json", {"run_receipt_sha256": sha256_file(run.output / "run_receipt.json"), "comparison_reference": ref(path)})
    data = build_run(run.output)
    assert data["comparison"]["unsupported"][0]["status"] == "unsupported_format"
    assert data["value"]["controlled_benefit"] is None


def test_resume_is_a_continuation_with_revalidation_and_cache_not_a_pair(environment):
    propose(environment)
    parent = run_for(environment, "parent")
    execute(parent)
    child = run_for(environment, "child", parent=parent)
    execute(child)
    data = build_run(child.output)
    assert data["comparison"]["kind"] == "continuation"
    assert data["comparison"]["continuation"]["available"]
    assert data["costs"]["host_actions_reused_from_parent"] == 2
    assert data["run"]["question_id"] == load_json_object(parent.output / "run_receipt.json")["question_id"]


def test_registry_concurrent_updates_preserve_both_receipts_and_changed_hash_is_invalid(environment):
    runs = pair_document(environment)
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(lambda r: dashboard_cli.refresh_run(r.output), runs.values()))
    assert all(r["status"] == "DASHBOARD_GENERATED" for r in outcomes)
    folder = environment[2].root / "dashboard"
    data = load_json_object(folder / "index.json")
    assert len(data["runs"]) == 2 and len({r["run"]["id"] for r in data["runs"]}) == 2
    write_json_atomic(runs["baseline"].output / "run_receipt.json", {"goal": "changed fixture"})
    rebuild(folder)
    data = load_json_object(folder / "index.json")
    invalid = next(r for r in data["runs"] if r["run"]["name"] == "fixture_baseline")
    assert invalid["usage_state"] == "unknown" and invalid["run"]["status"] == "unknown"


def test_html_serialization_escapes_script_closers_and_has_no_network_assets():
    malicious = '</script><img src=x onerror="globalThis.BAD=1"><script>__JS____DATA__'
    text = render({"schema_version": 1, "kind": "rsi_dashboard_project", "runs": [], "payload": malicious})
    assert malicious not in text and "\\u003c/script\\u003e" in text
    assert "__JS____DATA__" in text
    assert '<script src=' not in text and '<link href=' not in text
    assert "connect-src 'none'" in text and "@media (max-width: 400px)" in text


def test_unrelated_html_is_not_overwritten(tmp_path):
    path = tmp_path / "index.html"
    path.write_text("user page", encoding="utf-8")
    with pytest.raises(ValueError, match="not owned"):
        write_html(path, "replacement")
    assert path.read_text() == "user page"


def test_directory_bound_stops_after_201_entries():
    consumed = []
    def endless():
        while True:
            consumed.append(1)
            yield "fixture"
    with pytest.raises(ValueError, match="bound of 200"):
        bounded_paths(endless())
    assert len(consumed) == 201


def test_bad_registration_keeps_other_complete_runs_visible(completed):
    environment, run = completed
    dashboard_cli.refresh_run(run.output)
    folder = environment[2].root / "dashboard"
    write_json_exclusive(folder / "registrations/bad.json", {"schema_version": 1, "run_receipt_ref": None})
    result = rebuild(folder)
    data = load_json_object(folder / "index.json")
    assert result["runs"] == 1 and data["runs"][0]["provided_count"] == 1
    assert data["source_errors"][0]["role"] == "registration"


def test_open_option_targets_generated_page_without_calling_research(completed, monkeypatch):
    _, run = completed
    opened = []
    if sys.platform == "win32":
        monkeypatch.setattr(dashboard_cli.os, "startfile", opened.append)
    else:
        monkeypatch.setattr(dashboard_cli.webbrowser, "open", opened.append)
    result = dashboard_cli.execute(Namespace(run=run.output, runs_root=None, output_dir=None, open_page=True))
    assert opened and result["run_view"].endswith("rsi_view.html")


def invoke(monkeypatch, environment, command, output, parent=None, disabled=False):
    tmp, project, store, _ = environment
    args = ["research-assist", command, "--workdir", str(project), "--project-root", str(project), "--auth-home", str(tmp / "auth"),
        "--codex", "OFFLINE_TEST_ONLY", "--rsi-store", str(store.root), "--output-dir", str(output), "--intent", "plan"]
    args += ["--from-run", str(parent), "--update", "synthetic update"] if parent else ["--goal", "prepare structure in synthetic test"]
    if disabled:
        args.append("--no-dashboard")
    monkeypatch.setattr(sys, "argv", args)
    cli.main()


def test_run_resume_hooks_no_dashboard_and_stdout_compatibility(environment, monkeypatch, capsys):
    def offline(run, *_):
        run.bind_workspace(environment[0] / "auth")
        run.drive(PolicyPeer(run), synthetic=True)
        return run.finish()
    monkeypatch.setattr(cli, "run_research", offline)
    first = environment[0] / "cli-run"
    invoke(monkeypatch, environment, "run", first)
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == "OFFLINE_TEST_GENERATED" and (first / "views/rsi_view.html").exists()
    second = environment[0] / "cli-resume"
    invoke(monkeypatch, environment, "resume", second, parent=first)
    assert json.loads(capsys.readouterr().out)["status"] == "OFFLINE_TEST_GENERATED"
    assert load_json_object(second / "views/rsi_view.json")["comparison"]["kind"] == "continuation"
    index = load_json_object(environment[2].root / "dashboard/index.json")
    assert index["preferred_run_id"] == sha256_file(second / "run_receipt.json")
    third = environment[0] / "disabled"
    invoke(monkeypatch, environment, "run", third, disabled=True)
    assert json.loads(capsys.readouterr().out)["status"] == "OFFLINE_TEST_GENERATED" and not (third / "views").exists()


def test_display_failure_never_changes_completed_research_or_retries(environment, monkeypatch, capsys):
    calls = []
    def offline(run, *_):
        calls.append(1)
        run.bind_workspace(environment[0] / "auth")
        run.drive(PolicyPeer(run), synthetic=True)
        return run.finish()
    monkeypatch.setattr(cli, "run_research", offline)
    monkeypatch.setattr(dashboard_cli, "refresh_run", lambda *_: (_ for _ in ()).throw(OSError("synthetic display failure")))
    output = environment[0] / "display-fail"
    invoke(monkeypatch, environment, "run", output)
    captured = capsys.readouterr()
    assert len(calls) == 1 and json.loads(captured.out)["status"] == "OFFLINE_TEST_GENERATED"
    assert "display failed" in captured.err and load_json_object(output / "run_receipt.json")["status"] == "OFFLINE_TEST_GENERATED"
