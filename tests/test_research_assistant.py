"""Offline software/host-tool checks; no model, scientific job or production DB."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.research_assistant.catalog import Catalog
from scripts.research_assistant.cli import feedback
from scripts.research_assistant.contract import validate_response
from scripts.research_assistant.runner import ResearchRun
from scripts.research_assistant.tools import ToolRegistry
from scripts.ts_strategy_engine.review_live import _toml, settings


def request(tool, ids=(), query="", limit=5):
    return {"tool": tool, "target_ids": list(ids), "query": query, "limit": limit}


def final_answer(intent, identity="E001", observed="synthetic observation"):
    fact = {"statement": observed, "evidence_ids": [identity]}
    return {"kind": "final", "requests": [], "answer": {
        "intent": intent, "goal": "synthetic research goal", "facts": [fact], "uncertainties": [], "hypotheses": [],
        "options": [], "evidence_and_calculation_plan": [], "recommended_next": {"action": "Review the measured source.",
        "rationale": "The actual observation is available.", "evidence_ids": [identity],
        "outcomes": [{"if": "source corresponds", "then": "request owning scientific review"}]},
        "new_information": [fact], "draft_evidence_ids": [], "progress": None,
        "scientific_limits": "Synthetic software fixture; not scientific acceptance."}}


@pytest.fixture
def setup(tmp_path):
    scope = tmp_path / "scope"
    scope.mkdir()
    write_json_exclusive(scope / "measurement.json", {"value": 2.75})
    output = tmp_path / "run"
    output.mkdir()
    catalog = Catalog([scope], output)
    tools = ToolRegistry(catalog, scope, output)
    identity = catalog.listed(scope / "measurement.json")
    return scope, output, catalog, tools, identity


def test_catalog_is_metadata_until_read_and_injection_is_only_data(setup):
    scope, output, catalog, tools, identity = setup
    assert "2.75" not in json.dumps(catalog.snapshot())
    value = tools.execute(request("evidence.read", [identity], "/value"))
    assert value["data"][0]["value"] == 2.75
    assert value["sources"][0]["sha256"] == sha256_file(scope / "measurement.json")
    assert Path(value["sources"][0]["snapshot"]).read_bytes() == (scope / "measurement.json").read_bytes()
    with pytest.raises(ValueError, match="unlisted"):
        tools.execute(request("evidence.read", ["../../.ssh/id_ed25519"]))
    with pytest.raises(ValueError, match="unregistered"):
        tools.execute(request("shell", [identity], "submit_job"))
    assert not list(scope.glob("*submitted*"))


def test_evaluation_manifest_hides_reference_files_and_directories(tmp_path):
    scope, output = tmp_path / "scope", tmp_path / "output"
    scope.mkdir()
    output.mkdir()
    write_json_exclusive(scope / "raw.json", {"value": 4})
    hidden = scope / "private_reference"
    hidden.mkdir()
    write_json_exclusive(hidden / "answer.json", {"answer": "SECRET_REFERENCE"})
    manifest = tmp_path / "manifest.json"
    write_json_exclusive(manifest, {"schema_version": 1, "files": [{"path": str(scope / "raw.json"), "sha256": sha256_file(scope / "raw.json")}]})
    frozen = Catalog([scope], output, mode="evaluation", manifest=manifest)
    assert "private_reference" not in json.dumps(frozen.snapshot()) and frozen.listed(hidden / "answer.json") is None
    with pytest.raises(ValueError, match="withheld"):
        frozen.freeze(hidden / "answer.json")
    daily = Catalog([scope], output)
    assert daily.listed(hidden / "answer.json") is not None


def test_unknown_source_is_not_claimed_not_generated(setup):
    scope, _, catalog, _, _ = setup
    path, status = catalog.file(scope, "OUTCAR")
    assert path is None and status["availability"] == "not_found" and status["retention_elsewhere"] == "unknown"


def test_repeated_host_request_is_cached_and_source_tamper_rejected(setup):
    scope, _, catalog, tools, identity = setup
    call = request("evidence.read", [identity], "/value")
    first, second = tools.execute(call), tools.execute(call)
    assert first["host_executed"] and not second["host_executed"] and second["reused_from"] == "E001"
    (scope / "measurement.json").write_text('{"value":99}', encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        catalog.verify()


def test_sources_cannot_escape_or_include_credentials(setup):
    scope, _, catalog, _, _ = setup
    (scope / ".codex").mkdir()
    (scope / ".codex/auth.json").write_text("secret")
    catalog.discover(scope, 0, 2)
    assert "auth.json" not in json.dumps(catalog.snapshot())
    with pytest.raises(ValueError):
        catalog.freeze(scope / ".codex/auth.json")
    with pytest.raises(ValueError):
        catalog.freeze(scope / ".." / "outside.txt")


class Peer:
    def __init__(self, run, *, error=False, native=False):
        self.run, self.error, self.native = run, error, native
        self.messages, self.calls = [], 0

    def rpc(self, method, params):
        if method == "initialize":
            return {}
        if method == "thread/start":
            assert params["dynamicTools"] == []
            return {"model": params["model"], "reasoningEffort": "medium", "approvalPolicy": "never",
                    "sandbox": {"type": "readOnly"}, "thread": {"id": "thread", "sessionId": "session", "turns": [], "ephemeral": True}}
        assert method == "turn/start"
        self.calls += 1
        turn = "turn" + str(self.calls)
        if self.error:
            self.messages = [{"method": "error", "params": {"error": {"message": "HTTP429 synthetic software test"}, "willRetry": False}}]
        elif self.native:
            self.messages = [{"id": "forbidden", "method": "item/tool/call", "params": {}}]
        else:
            if self.calls == 1:
                identity = self.run.catalog.listed(self.run.catalog.scopes[0] / "measurement.json")
                value = {"kind": "request", "requests": [request("evidence.read", [identity], "/value")], "answer": None}
            else:
                observed = str(self.run.tools.results["E001"]["data"][0]["value"])
                value = final_answer(self.run.intent, observed=observed)
                if self.run.continuation:
                    value["answer"]["progress"] = {"changes": [{"previous_ref": "F001", "assessment": "unchanged",
                        "statement": observed, "evidence_ids": ["E001"]}], "completed_checks": [], "remaining_checks": [],
                        "next_product": "Synthetic independent owner review"}
            self.messages = [
                {"method": "item/completed", "params": {"threadId": "thread", "turnId": turn,
                    "item": {"id": turn + "-answer", "type": "agentMessage", "phase": "final_answer", "text": json.dumps(value)}}},
                {"method": "turn/completed", "params": {"threadId": "thread", "turn": {"id": turn, "status": "completed"}}}]
        return {"turn": {"id": turn}}

    def send(self, message):
        pass

    def receive(self):
        value = self.messages.pop(0)
        self.run.record("received", value)
        return value


@pytest.mark.parametrize("intent", ["diagnose", "compare", "plan"])
def test_one_orchestrator_three_intents_selects_real_host_tools_offline(setup, tmp_path, intent):
    scope, _, _, _, _ = setup
    run = ResearchRun("synthetic goal", intent, [scope], scope, tmp_path / intent)
    run.bind_workspace(tmp_path / "auth-home")
    peer = Peer(run)
    run.drive(peer, synthetic=True)
    result = run.finish()
    assert result["status"] == "OFFLINE_TEST_GENERATED"
    assert result["model_turns_started"] == 0 and peer.calls == 2
    assert result["host_tool_executions"] == 1 and result["native_tool_calls"] == 0
    assert run.answer["facts"][0]["statement"] == "2.75" and "failure_class" not in run.answer
    assert (run.output / "turn-001/model-response.txt").exists() and (run.output / "turn-002/model-response.txt").exists()


@pytest.mark.parametrize("native", [False, True])
def test_backend_or_native_failure_stops_without_retry(setup, tmp_path, native):
    scope, _, _, _, _ = setup
    run = ResearchRun("synthetic goal", "diagnose", [scope], scope, tmp_path / "blocked")
    run.bind_workspace(tmp_path / "auth")
    peer = Peer(run, error=not native, native=native)
    with pytest.raises(ValueError):
        run.drive(peer, synthetic=True)
    run.problem, run.first_failure_stage = "synthetic backend/native failure", run.stage
    receipt = run.finish()
    assert receipt["status"] == "OFFLINE_TEST_BLOCKED" and peer.calls == 1
    assert receipt["host_tool_executions"] == 0 and not (run.output / "research_result.json").exists()


def test_final_cannot_cite_unread_evidence_or_fabricate_cost():
    value = final_answer("compare")
    with pytest.raises(ValueError, match="never obtained"):
        validate_response(value, {}, "compare")
    validate_response(value, {"E001": {"data": []}}, "compare")
    value["answer"]["draft_evidence_ids"] = ["E001"]
    with pytest.raises(ValueError, match="draft not produced"):
        validate_response(value, {"E001": {"data": []}}, "compare")
    value["answer"]["draft_evidence_ids"] = []
    value["answer"]["options"] = [{"id": "candidate", "proposal": "hypothetical option", "evidence_ids": ["E001"],
        "conditions": ["independent owner review"], "risks": [], "acceptance_conditions": ["owning gates"], "blocking_gaps": [],
        "cost": {"status": "unknown", "value": 0, "unit": "hours", "basis": "not measured", "evidence_ids": []}}]
    with pytest.raises(ValueError, match="unknown cost"):
        validate_response(value, {"E001": {}}, "compare")


def test_missing_input_does_not_establish_non_generation():
    value = final_answer("diagnose")
    value["answer"]["uncertainties"] = [{"question": "Was the raw frame generated?", "availability": "not_generated",
        "scope_and_basis": "not found in this input", "evidence_ids": ["E001"]}]
    with pytest.raises(ValueError, match="explicit host production-state"):
        validate_response(value, {"E001": {"availability": "not_found"}}, "diagnose")
    value["answer"]["uncertainties"][0]["availability"] = "not_found"
    validate_response(value, {"E001": {"availability": "not_found"}}, "diagnose")


def test_scope_rebinding_preserves_native_boundary_and_rejects_personal_config(setup, tmp_path):
    scope, _, _, _, _ = setup
    home = tmp_path / "auth"
    home.mkdir()
    old = home.parent / "diagnosis-workspaces/old"
    old.mkdir(parents=True)
    before = settings(home, old, [old / "model_input.json"], credential_store="file")
    (home / "config.toml").write_text(_toml(before), encoding="utf-8")
    run = ResearchRun("goal", "plan", [scope], scope, tmp_path / "binding")
    run.bind_workspace(home)
    run.bind_existing_task_scope(home)
    import tomllib
    after = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
    assert after["permissions"]["review-model"]["filesystem"][home.as_posix()] == "deny"
    assert after["permissions"]["review-client"]["network"] == before["permissions"]["review-client"]["network"]
    assert after["cli_auth_credentials_store"] == "file"
    changed = deepcopy(after)
    changed["features"]["shell_tool"] = True
    (home / "config.toml").write_text(_toml(changed), encoding="utf-8")
    another = ResearchRun("other goal", "plan", [scope], scope, tmp_path / "reject")
    another.bind_workspace(home)
    with pytest.raises(ValueError, match="configuration differs"):
        another.bind_existing_task_scope(home)


def test_feedback_keeps_usage_separate_from_science(setup, tmp_path):
    scope, _, _, _, _ = setup
    run = ResearchRun("goal", "diagnose", [scope], scope, tmp_path / "feedback-run")
    run.bind_workspace(tmp_path / "auth")
    run.drive(Peer(run), synthetic=True)
    run.finish()
    data = {"adopted": None, "evidence_effectiveness": [{"evidence_id": "E001", "effective": None, "reason": "await user feedback"}],
            "repeated_checks": [], "followup_notes": "unknown", "scientific_result_reference": None}
    path = tmp_path / "feedback.json"
    write_json_exclusive(path, data)
    result = feedback(run.output, path)
    value = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert value["usage_feedback"]["adopted"] is None and not value["promotes_scientific_result"]
    assert value["scientific_result_reference"] is None and not value["strategy_approved"]
    data["evidence_effectiveness"][0]["evidence_id"] = "E001.presented"
    assert (run.output / "tools" / "E001.presented.json").is_file()
    rejected = tmp_path / "feedback-projection.json"
    write_json_exclusive(rejected, data)
    with pytest.raises(ValueError, match="actual host actions"):
        feedback(run.output, rejected)


def test_hashed_feedback_is_retrievable_as_history(tmp_path):
    scope, output = tmp_path / "run", tmp_path / "next"
    (scope / "feedback").mkdir(parents=True)
    write_json_exclusive(scope / "feedback" / "abc123.json", {"followup_notes": "terminal alignment resolved one evidence gap"})
    output.mkdir()
    catalog = Catalog([scope], output)
    registry = ToolRegistry(catalog, scope, output)
    result = registry.execute({"tool": "history.search", "target_ids": [], "query": "alignment", "limit": 5})
    assert result["status"] == "OK"
    source_id = result["data"]["matches"][0]["source_id"]
    assert catalog.entries[source_id]["type"] == "historical_interpretation"


def poscar_text(distance=1.0):
    return f"Synthetic Fe H\n1\n5 0 0\n0 5 0\n0 0 5\nFe H\n1 1\nSelective dynamics\nCartesian\n0 0 0 F F F\n{distance} 0 0 T T T\n"


def test_vasp_terminal_alignment_and_geometry_are_actual_measurements(tmp_path):
    scope, output = tmp_path / "calculation", tmp_path / "output"
    scope.mkdir()
    output.mkdir()
    (scope / "INCAR").write_text("NELM=200\nEDIFF=1E-5\nEDIFFG=-0.02\nNSW=80\n", encoding="utf-8")
    (scope / "OSZICAR").write_text("DAV: 1 -1.0 -1e-7 -1e-8 2 0.001\n1 F= -1.0 E0= -1.0\n", encoding="utf-8")
    (scope / "POSCAR").write_text(poscar_text(1.0), encoding="utf-8")
    (scope / "CONTCAR").write_text(poscar_text(1.01), encoding="utf-8")
    (scope / "OUTCAR").write_text("vasp.6\nIteration 1( 1)\naborting loop because EDIFF is reached\n"
        "POSITION TOTAL-FORCE (eV/Angst)\n--------------------------------\n0 0 0 0.1 0 0\n1 0 0 -0.1 0 0\n"
        "--------------------------------\nfree  energy   TOTEN = -1.0 eV\nenergy(sigma->0) = -1.0\n"
        "General timing and accounting informations for this job\n", encoding="utf-8")
    catalog = Catalog([scope], output)
    tools = ToolRegistry(catalog, scope, output)
    result = tools.execute(request("terminal.align", [catalog.listed(scope)]))
    assert result["status"] == "OK", result
    assert result["data"]["last_block_to_saved_structure"]["maximum_MIC_mismatch_A"] == pytest.approx(0.01)
    assert result["data"]["last_complete_force_block"]["maximum_movable_eV_per_A"] == pytest.approx(0.1)
    assert not result["scientific_acceptance"]
    measured = tools.execute(request("structures.measure", [catalog.listed(scope / "POSCAR"), catalog.listed(scope / "CONTCAR")]))
    assert measured["status"] == "OK", measured
    assert measured["data"]["comparisons"][0]["atom_zero_based"] == 1
    assert measured["data"]["comparisons"][0]["atom_one_based"] == 2
    assert measured["data"]["comparisons"][0]["maximum_same_index_MIC_A"] == pytest.approx(0.01)
    repeated = tools.execute(request("terminal.align", [catalog.listed(scope)], "different prose, same measurement"))
    assert not repeated["host_executed"] and repeated["reused_from"] == "E001"


def test_local_method_search_is_labelled_lexical_not_production_retrieval(setup):
    scope, _, catalog, tools, _ = setup
    (scope / "method.md").write_text("# Synthetic method\nFe(110) geometry force convergence review\n", encoding="utf-8")
    catalog.discover(scope, 0, 1)
    result = tools.execute(request("methods.search", query="geometry force"))
    assert result["status"] == "OK" and result["data"]["matches"]
    assert "not semantic" in result["data"]["ranking"] and not result["scientific_acceptance"]
    assert any(row["kind"] == "derived_corpus_receipt" for row in result["sources"])


def test_existing_history_reader_uses_copy_and_never_changes_original(tmp_path):
    from scripts.ts_strategy_engine.learning_store import append_event
    from scripts.ts_strategy_engine.registry import open_registry
    from scripts.registry_schema import migrate_registry
    from scripts.runtime_resources import resource_path
    scope, output = tmp_path / "scope", tmp_path / "output"
    scope.mkdir()
    output.mkdir()
    database = scope / "history.sqlite3"
    migrate_registry(database, resource_path("modules/calculation_registry/schema.sql"))
    with open_registry(database) as connection:
        append_event(connection, "attempt", "synthetic-attempt", {"task_id": "synthetic hydrogenation"})
    before = sha256_file(database)
    catalog = Catalog([scope], output)
    tools = ToolRegistry(catalog, scope, output)
    result = tools.execute(request("history.search", [catalog.listed(database)], "hydrogenation"))
    assert result["status"] == "OK" and result["data"]["events"][0]["id"] == "synthetic-attempt", result
    assert sha256_file(database) == before
    assert list(output.glob("history-copy-*.sqlite3"))


def test_turn_budget_preserves_first_request_without_repair(setup, tmp_path):
    scope, _, _, _, _ = setup
    run = ResearchRun("goal", "plan", [scope], scope, tmp_path / "budget", max_turns=1)
    run.bind_workspace(tmp_path / "auth")
    peer = Peer(run)
    with pytest.raises(ValueError, match="turn budget"):
        run.drive(peer, synthetic=True)
    assert peer.calls == 1 and len(run.tools.actions) == 1
    assert (run.output / "turn-001/model-response.txt").exists()


def test_different_goals_reuse_same_catalog_read_view(setup, tmp_path):
    scope, _, _, _, _ = setup
    first = ResearchRun("goal A", "diagnose", [scope], scope, tmp_path / "first")
    second = ResearchRun("goal B", "compare", [scope], scope, tmp_path / "second")
    home = tmp_path / "auth"
    assert first.bind_workspace(home) == second.bind_workspace(home)


def test_evaluation_scalar_reads_never_return_posthoc_siblings(tmp_path):
    scope, output = tmp_path / "scope", tmp_path / "output"
    scope.mkdir()
    output.mkdir()
    source = scope / "raw.json"
    write_json_exclusive(source, {"value": 8, "posthoc": "SECRET_REFERENCE_SIBLING"})
    manifest = tmp_path / "frozen.json"
    write_json_exclusive(manifest, {"schema_version": 1, "files": [{"path": str(source), "sha256": sha256_file(source)}]})
    catalog = Catalog([scope], output, mode="evaluation", manifest=manifest)
    tools = ToolRegistry(catalog, scope, output)
    identity = catalog.listed(source)
    ok = tools.execute(request("evidence.read", [identity], "/value"))
    assert ok["data"][0]["value"] == 8 and "SECRET" not in json.dumps(ok)
    for pointer in ["", "/posthoc"]:
        result = tools.execute(request("evidence.read", [identity], pointer))
        assert result["status"] == "ERROR" and "SECRET" not in json.dumps(result)
    assert tools.execute(request("history.search", query="value"))["status"] == "ERROR"


def test_structural_projection_keeps_measured_force_after_long_history():
    from scripts.research_assistant.presentation import present
    original = {"evidence_id": "E001", "tool": "vasp.inspect", "status": "OK", "data": {
        "long_history": list(range(20000)), "last_complete_force_block": {"maximum_movable_eV_per_A": 0.86},
        "owner_scf_oszicar_only": {"electronically_converged": True}, "incar": {"EDIFFG": "-0.02"}}}
    projected = present(original, {"path": "synthetic", "sha256": "a" * 64})
    assert projected["data"]["last_complete_force_block"]["maximum_movable_eV_per_A"] == 0.86
    assert projected["data"]["owner_scf_oszicar_only"]["electronically_converged"]
    assert projected["data"]["long_history"]["total_items"] == 20000
    assert len(original["data"]["long_history"]) == 20000
    assert len(json.dumps(projected)) < 24000


def test_methods_search_accepts_a_document_id_instead_of_misreading_jsonl(setup):
    scope, _, catalog, tools, _ = setup
    path = scope / "method.md"
    path.write_text("# Method\n" + "intro\n" * 60 + "Force convergence requires owner review.\n", encoding="utf-8")
    catalog.discover(scope, 0, 1)
    result = tools.execute(request("methods.search", [catalog.listed(path)], "force convergence"))
    assert result["status"] == "OK" and result["data"]["matches"], result
    assert "Force convergence" in result["data"]["matches"][0]["excerpt"]


@pytest.mark.parametrize("change", ["none", "source", "implementation", "snapshot"])
def test_continuation_revalidates_sources_versions_and_reuses_only_safe_results(setup, tmp_path, change):
    scope, _, _, _, _ = setup
    parent = ResearchRun("synthetic goal", "compare", [scope], scope, tmp_path / "parent")
    parent.bind_workspace(tmp_path / "auth")
    parent.drive(Peer(parent), synthetic=True)
    parent.finish()
    original = sha256_file(parent.output / "research_result.json")
    if change == "source":
        (scope / "measurement.json").write_text('{"value": 3.0}', encoding="utf-8")
    if change == "snapshot":
        next((parent.output / "sources").glob("*/measurement.json")).write_text("tampered")
    run = ResearchRun("synthetic goal", "compare", [scope], scope, tmp_path / "child", previous_run=parent.output, update="recheck")
    if change == "implementation":
        run.tools.implementation_sha256 = "different implementation"
    run.bind_workspace(tmp_path / "auth")
    run.drive(Peer(run), synthetic=True)
    receipt = run.finish()
    assert run.question_id == parent.question_id
    assert receipt["host_actions_reused_from_parent"] == (1 if change == "none" else 0)
    assert receipt["host_tool_executions"] == (0 if change == "none" else 1)
    assert run.answer["facts"][0]["statement"] == ("3.0" if change == "source" else "2.75")
    assert sha256_file(parent.output / "research_result.json") == original
    assert (run.output / "continuation.json").is_file()
    if change == "source":
        assert run.continuation["source_revalidation"][0]["sources"][0]["current_state"] == "changed"


def test_continuation_missing_source_remains_unknown_and_old_evidence_cannot_be_cited(setup, tmp_path):
    scope, _, _, _, _ = setup
    parent = ResearchRun("goal", "diagnose", [scope], scope, tmp_path / "parent")
    parent.bind_workspace(tmp_path / "auth")
    parent.drive(Peer(parent), synthetic=True)
    parent.finish()
    (scope / "measurement.json").unlink()
    run = ResearchRun("goal", "diagnose", [scope], scope, tmp_path / "child", previous_run=parent.output, update="new evidence")
    run.prepare_continuation()
    assert run.continuation["source_revalidation"][0]["sources"][0]["current_state"] == "missing_in_current_location"
    assert not run.tools.cache and not run.tools.results
    with pytest.raises(ValueError, match="never obtained"):
        validate_response(final_answer("diagnose"), run.tools.results, "diagnose")


def test_legacy_research_contract_is_explicitly_loadable():
    value = final_answer("plan")
    value["answer"].pop("progress")
    validate_response(value, {"E001": {}}, "plan", version="project_research_assistant_v1")


def test_usage_feedback_does_not_invent_human_time_or_adoption(setup, tmp_path):
    scope, _, _, _, _ = setup
    run = ResearchRun("goal", "plan", [scope], scope, tmp_path / "parent")
    run.bind_workspace(tmp_path / "auth")
    run.drive(Peer(run), synthetic=True)
    run.finish()
    data = {"adopted": None, "evidence_effectiveness": [], "repeated_checks": [], "followup_notes": "not measured",
            "scientific_result_reference": None, "human_review_seconds": None, "adopted_option_ids": []}
    path = tmp_path / "unknown-feedback.json"
    write_json_exclusive(path, data)
    value = json.loads(Path(feedback(run.output, path)["path"]).read_text(encoding="utf-8"))
    assert value["usage_feedback"]["human_review_seconds"] is None
    data["human_review_seconds"] = -1
    invalid = tmp_path / "invalid-time.json"
    write_json_exclusive(invalid, data)
    with pytest.raises(ValueError, match="measured or unknown"):
        feedback(run.output, invalid)


def test_directed_pairs_surface_and_target_comparison(tmp_path):
    scope, output = tmp_path / "scope", tmp_path / "out"
    scope.mkdir()
    output.mkdir()
    (scope / "POSCAR").write_text(poscar_text(1.0))
    (scope / "CONTCAR").write_text(poscar_text(2.0))
    catalog = Catalog([scope], output)
    tools = ToolRegistry(catalog, scope, output)
    ids = [catalog.listed(scope / name) for name in ("POSCAR", "CONTCAR")]
    query = json.dumps({"pairs_zero_based": [[0, 1]], "adsorbate_zero_based": [1], "surface_zero_based": [0]})
    result = tools.execute(request("structures.compare", ids, query))
    assert result["status"] == "OK"
    assert [row["directed_pairs"][0]["MIC_A"] for row in result["data"]["structures"]] == [1.0, 2.0]
    assert result["data"]["structures"][1]["nearest_selected_surface_contacts"][0]["surface_atom_one_based"] == 1
    assert result["data"]["comparisons"][0]["adsorbate_same_index_RMS_MIC_A"] == 1.0


def test_geometry_review_draft_reuses_owner_rules_without_parameters_or_execution(tmp_path):
    scope, output = tmp_path / "scope", tmp_path / "out"
    scope.mkdir()
    output.mkdir()
    for name in ("POSCAR", "CONTCAR"):
        (scope / name).write_text(poscar_text(1.0))
    project = Path(__file__).resolve().parents[1]
    catalog = Catalog([scope, project / "configs"], output)
    tools = ToolRegistry(catalog, project, output)
    ids = [catalog.listed(scope / name) for name in ("POSCAR", "CONTCAR")]
    result = tools.execute(request("workflow.review", ids, json.dumps({"option_id": "branch-a", "adsorbate_zero_based": [1]})))
    assert result["status"] == "OK", result
    document = json.loads(Path(result["data"]["draft"]["path"]).read_text(encoding="utf-8"))
    assert document["option_id"] == "branch-a" and document["owner"] == "adsmind_lite.relaxed_analysis"
    assert document["cost"] is None and not document["parameters_generated"] and not document["runnable"]
    assert document["owner_connectivity_observations"]["chemical_event"] == "none"
