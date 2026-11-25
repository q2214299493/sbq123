"""Integration boundaries for the shared development snapshot. No native launches."""
import json

import pytest

from scripts.execution_backends import load_execution_backends
from scripts.neb_agent import submission
from tests.test_state_sync_safe_only import command, registered_projection, tree_hashes


def test_bare_sync_is_a_read_only_preview(tmp_path, capsys):
    registered_projection(tmp_path)
    before = tree_hashes(tmp_path)
    status, default = command(tmp_path, capsys, "sync")
    preview_status, explicit = command(tmp_path, capsys, "sync", "--safe-only")
    assert status == preview_status
    assert json.loads(default.out) == json.loads(explicit.out)
    assert json.loads(default.out)["applied"] == []
    assert tree_hashes(tmp_path) == before


def test_historical_vasp_host_cannot_receive_new_mutations(tmp_path, monkeypatch):
    assert load_execution_backends().vasp.server_alias == "sunboquan-codex"
    monkeypatch.setattr(submission, "_run", lambda *args: pytest.fail("unexpected transport"))
    with pytest.raises(ValueError, match="evidence-only"):
        submission.submit(tmp_path, tmp_path / "decision.json", "sunboquan-cdj1-temp",
                          "~/sbq/test", "~/sbq/pot", "0" * 64, "SUBMIT_VASP")
    with pytest.raises(ValueError, match="evidence-only"):
        submission.stop_job(tmp_path / "decision.json", "sunboquan-cdj1-temp", "123", tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("declared_parent", ["ads_static", "unrelated"])
def test_reclassified_result_requires_its_own_parent_job(tmp_path, declared_parent):
    from scripts.registry_excel_promotion import _adsorption_context
    from scripts.registry_schema import migrate_registry
    from tests.registry_fixture_mutation import fixture_connection
    from tests.test_registry_excel_promotion import _seed_accepted_adsorption
    import sqlite3

    database = tmp_path / "fixture.sqlite"
    migrate_registry(database)
    _seed_accepted_adsorption(database)
    with fixture_connection(database) as db:
        db.row_factory = sqlite3.Row
        for identifier in ("unrelated", "child"):
            db.execute(
                "INSERT INTO calculations(calculation_id,module,purpose,workflow_status,created_at) "
                "VALUES (?, 'adsorption_workflow', 'reviewed fixture', 'accepted', '2026-01-01')",
                (identifier,),
            )
        db.execute("UPDATE calculations SET parent_calculation_id=? WHERE calculation_id='child'", (declared_parent,))
        db.execute("INSERT INTO calculation_compatibility VALUES ('child','fingerprint','{}','reviewer','2026-01-01')")
        db.execute("UPDATE files SET calculation_id='child' WHERE file_id='outcar'")
        db.execute("UPDATE results SET calculation_id='child' WHERE result_id='ads_energy'")
        if declared_parent == "ads_static":
            assert _adsorption_context(db, "child")["calculation_id"] == "child"
        else:
            with pytest.raises(ValueError, match="recorded scheduler"):
                _adsorption_context(db, "child")
