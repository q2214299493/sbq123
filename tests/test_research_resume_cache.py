"""Three-round provenance and changing collection tests; no model/science jobs."""
from pathlib import Path
import json

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.research_assistant.runner import ResearchRun


def request(tool, ids=(), query=""):
    return {"tool": tool, "target_ids": list(ids), "query": query, "limit": 5}


def begin(tmp_path, scope, name, parent=None, extra=(), project=None):
    run = ResearchRun("Synthetic cache-only research", "diagnose", [scope, *extra], project or scope, tmp_path / name,
                      previous_run=parent.output if parent else None, update="synthetic cache test")
    run.prepare_continuation()
    return run


def finish(run):
    fact = {"statement": "Synthetic host-only software fixture", "evidence_ids": ["E001"]}
    run.answer = {"intent": "diagnose", "goal": run.goal, "facts": [fact], "uncertainties": [], "hypotheses": [],
        "options": [], "evidence_and_calculation_plan": [], "recommended_next": {"action": "Review fixture", "rationale": "Offline only",
        "evidence_ids": ["E001"], "outcomes": [{"if": "fixture valid", "then": "inspect source"}]},
        "new_information": [fact], "draft_evidence_ids": [], "scientific_limits": "No scientific acceptance", "progress": None}
    run.run_mode = "OFFLINE_TEST_TRANSPORT"
    run.finish()


def setup_scope(tmp_path):
    scope = tmp_path / "data"
    scope.mkdir()
    write_json_exclusive(scope / "measurement.json", {"value": 2.75})
    (scope / "method.md").write_text("energy evidence review", encoding="utf-8")
    return scope


def test_three_round_file_and_search_reuse_bind_each_current_round(tmp_path):
    scope = setup_scope(tmp_path)
    parent = None
    for number in range(1, 4):
        run = begin(tmp_path, scope, f"round{number}", parent)
        file_request = request("evidence.read", [run.catalog.listed(scope / "measurement.json")], "/value")
        a = run.tools.execute(file_request)
        b = run.tools.execute(request("methods.search", query="energy"))
        assert a["host_executed"] is (number == 1)
        assert b["host_executed"] is (number == 1)
        assert a["data"][0]["value"] == 2.75
        for result in (a, b):
            for reference in result["sources"]:
                if reference.get("kind") == "derived_corpus_receipt":
                    assert Path(reference["path"]).is_relative_to(run.output / "tools")
                    assert sha256_file(Path(reference["path"])) == reference["sha256"]
                    leaves = load_json_object(Path(reference["path"]))["sources"]
                else:
                    leaves = [reference]
                for leaf in leaves:
                    assert Path(leaf["snapshot"]).is_relative_to(run.output / "sources")
                    assert sha256_file(Path(leaf["snapshot"])) == leaf["sha256"]
        if number > 1:
            assert len(b["cache_lineage"]) == number - 1
        finish(run)
        parent = run


def test_resume_output_schema_uses_actual_single_previous_references(tmp_path):
    scope = setup_scope(tmp_path)
    parent = begin(tmp_path, scope, "first")
    parent.tools.execute(request("evidence.read", [parent.catalog.listed(scope / "measurement.json")], "/value"))
    finish(parent)
    child = begin(tmp_path, scope, "second", parent)

    def reference_schema(run):
        answer = run.prompt_for(1)["response_schema"]["properties"]["answer"]["anyOf"][0]
        return answer["properties"]["progress"]["anyOf"][0]["properties"]["changes"]["items"]["properties"]["previous_ref"]

    assert reference_schema(child) == {"enum": ["F001"]}
    assert "enum" not in reference_schema(parent)


def test_new_optional_vasp_file_invalidates_result(tmp_path):
    scope = setup_scope(tmp_path)
    (scope / "INCAR").write_text("EDIFF=1e-5\nNELM=100\n")
    (scope / "OSZICAR").write_text("RMM: 1 -10 1e-7 1e-8\n1 F= -10 E0= -10\n")
    parent = begin(tmp_path, scope, "first")
    req = request("vasp.inspect", [parent.catalog.listed(scope)])
    parent.tools.execute(req)
    finish(parent)
    (scope / "vasp.out").write_text("newly persisted stdout\n")
    child = begin(tmp_path, scope, "second", parent)
    result = child.tools.execute(req)
    assert result["host_executed"] and "newly persisted" in result["data"]["stdout_tail"]
    assert not child.continuation["source_revalidation"][0]["dependencies_compatible"]


def test_directory_addition_invalidates_search_but_preserves_explicit_file(tmp_path):
    scope = setup_scope(tmp_path)
    parent = begin(tmp_path, scope, "first")
    search = request("methods.search", query="decisive")
    fixed = request("evidence.read", [parent.catalog.listed(scope / "measurement.json")], "/value")
    parent.tools.execute(search)
    parent.tools.execute(fixed)
    finish(parent)
    (scope / "new.md").write_text("decisive new observation")
    child = begin(tmp_path, scope, "second", parent)
    result = child.tools.execute(search)
    assert result["host_executed"] and result["data"]["matches"]
    assert not child.tools.execute(fixed)["host_executed"]


def test_added_search_scope_invalidates_global_search_only(tmp_path):
    scope = setup_scope(tmp_path)
    parent = begin(tmp_path, scope, "first")
    search = request("methods.search", query="decisive")
    fixed = request("evidence.read", [parent.catalog.listed(scope / "measurement.json")], "/value")
    parent.tools.execute(search)
    parent.tools.execute(fixed)
    finish(parent)
    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "new.md").write_text("decisive extra-scope observation")
    child = begin(tmp_path, scope, "second", parent, extra=[extra])
    assert child.tools.execute(search)["host_executed"]
    assert not child.tools.execute(fixed)["host_executed"]


def test_expanded_catalog_invalidates_same_scope_search(tmp_path):
    scope = setup_scope(tmp_path)
    deep = scope / "one/two/three"
    deep.mkdir(parents=True)
    (deep / "new.md").write_text("decisive deeply stored observation")
    parent = begin(tmp_path, scope, "first")
    req = request("methods.search", query="decisive")
    parent.tools.execute(req)
    finish(parent)
    child = begin(tmp_path, scope, "second", parent)
    child.tools.execute(request("evidence.list", [child.catalog.listed(deep)]))
    result = child.tools.execute(req)
    assert result["host_executed"] and result["data"]["matches"]


def test_same_round_directory_growth_is_not_hidden_by_cache(tmp_path):
    scope = setup_scope(tmp_path)
    run = begin(tmp_path, scope, "first")
    req = request("methods.search", query="decisive")
    run.tools.execute(req)
    (scope / "new.md").write_text("decisive after first request")
    result = run.tools.execute(req)
    assert result["host_executed"] and result["data"]["matches"]
    assert run.tools.actions[-1]["cache_invalidated"]


def test_exact_search_file_with_no_matches_remains_reusable(tmp_path):
    scope = setup_scope(tmp_path)
    parent = begin(tmp_path, scope, "first")
    req = request("methods.search", [parent.catalog.listed(scope / "method.md")], "not-in-file")
    assert not parent.tools.execute(req)["data"]["matches"]
    finish(parent)
    (scope / "unrelated.md").write_text("not-in-file, outside the specified file")
    child = begin(tmp_path, scope, "second", parent)
    result = child.tools.execute(req)
    assert not result["host_executed"] and not result["data"]["matches"]


def test_three_round_review_draft_sources_are_rebound(tmp_path):
    scope = setup_scope(tmp_path)
    poscar = "Fe H\n1\n5 0 0\n0 5 0\n0 0 5\nFe H\n1 1\nDirect\n0 0 0\n0.2 0 0\n"
    for name in ("POSCAR", "CONTCAR"):
        (scope / name).write_text(poscar)
    project = Path(__file__).resolve().parents[1]
    parent = None
    for number in range(3):
        run = begin(tmp_path, scope, f"round{number}", parent, extra=[project / "configs"], project=project)
        req = request("workflow.review", [run.catalog.listed(scope / name) for name in ("POSCAR", "CONTCAR")],
                      json.dumps({"option_id": "review", "adsorbate_zero_based": [1]}))
        result = run.tools.execute(req)
        assert result["status"] == "OK", result
        assert result["host_executed"] is (number == 0)
        draft = result["data"]["draft"]
        assert Path(draft["path"]).is_relative_to(run.output / "drafts")
        assert sha256_file(Path(draft["path"])) == draft["sha256"]
        document = load_json_object(Path(draft["path"]))
        assert all(Path(ref["snapshot"]).is_relative_to(run.output / "sources") for ref in document["sources"])
        finish(run)
        parent = run
