from __future__ import annotations

import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from scripts.registry_write import plan_registry_batch, apply_registry_batch
from scripts.artifact_io import sha256_json
from scripts.registry_transactions import approve_plan
from scripts.registry_compatibility import create_compatibility_revision, register_calculation_compatibility
from scripts.registry_schema import migrate_registry, rollback_registry_v9
from scripts.state_manager.job_lifecycle import validate_job_transition
from scripts.ts_strategy_engine.registry import open_registry
from tests.test_registry_write import _batch, _database


def reviewed(db, batch):
    plan = plan_registry_batch(db, batch)
    approval = approve_plan(plan, reviewer=batch["reviewer"], reviewed_at="2026-09-09T00:00:00Z")
    return dict(plan=plan, approval=approval, confirmed_sha256=plan["plan_sha256"])


def test_invalid_complete_batch_never_mutates(tmp_path):
    db = _database(tmp_path)
    before = db.read_bytes()
    batch = _batch()
    batch["rows"]["jobs"][0]["calculation_id"] = "missing"
    with pytest.raises(sqlite3.IntegrityError):
        plan_registry_batch(db, batch)
    assert db.read_bytes() == before


def test_conflicting_duplicate_rows_rejected_during_plan(tmp_path):
    db = _database(tmp_path)
    batch = _batch()
    batch["rows"]["calculations"].append({**batch["rows"]["calculations"][0], "module": "other"})
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        plan_registry_batch(db, batch)


def test_mid_transaction_failure_rolls_back_and_retry_is_safe(tmp_path, monkeypatch):
    import scripts.registry_mutations as mutations

    db, batch = _database(tmp_path), _batch()
    request = reviewed(db, batch)
    execute = mutations._execute_actions
    def fail(connection, batch, plan):
        execute(connection, batch, plan)
        if connection.execute("PRAGMA database_list").fetchone()[2]:
            raise OSError("injected transaction failure")
    monkeypatch.setattr(mutations, "_execute_actions", fail)
    with pytest.raises(OSError, match="injected"):
        apply_registry_batch(db, batch, **request)
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT count(*) FROM calculations").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM registry_applications").fetchone()[0] == 0
        assert c.execute("SELECT event_type FROM registry_events").fetchone()[0] == "batch_failed"
    monkeypatch.setattr(mutations, "_execute_actions", execute)
    assert apply_registry_batch(db, batch, **request)["inserted"] == 7
    assert apply_registry_batch(db, batch, **request)["already_applied"]
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT count(*) FROM registry_applications").fetchone()[0] == 1


@pytest.mark.parametrize("damage", ["batch", "plan", "reviewer", "scope", "approval_hash", "database"])
def test_approval_binding_rejects_changes(tmp_path, damage):
    db, batch = _database(tmp_path), _batch()
    request = reviewed(db, batch)
    if damage == "batch":
        batch["reason"] = "changed after review"
    elif damage == "plan":
        request["plan"]["actions"][0]["action"] = "unchanged"
    elif damage == "reviewer":
        request["approval"]["reviewer"] = None
    elif damage == "scope":
        request["approval"]["scope"] = ["schema_metadata"]
    elif damage == "approval_hash":
        request["approval"]["plan_sha256"] = "0" * 64
    else:
        with sqlite3.connect(db) as c:
            c.execute("INSERT INTO calculations(calculation_id,module,purpose,workflow_status,created_at) VALUES ('outside','test','test','registered','now')")
    with pytest.raises(ValueError):
        apply_registry_batch(db, batch, **request)
    with sqlite3.connect(db) as c:
        assert not c.execute("SELECT 1 FROM calculations WHERE calculation_id='fixture-calc'").fetchone()


def test_concurrent_apply_has_one_mutation(tmp_path):
    db, batch = _database(tmp_path), _batch()
    request = reviewed(db, batch)
    with ThreadPoolExecutor(2) as pool:
        receipts = list(pool.map(lambda _: apply_registry_batch(db, batch, **request), range(2)))
    assert sorted(r["already_applied"] for r in receipts) == [False, True]
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT count(*) FROM job_status_history").fetchone()[0] == 1


def test_compatibility_revisions_do_not_rebind_old_calculations(tmp_path):
    db, batch = _database(tmp_path), _batch()
    del batch["rows"]["calculation_compatibility"]
    apply_registry_batch(db, batch, **reviewed(db, batch))
    old = register_calculation_compatibility(db, "fixture-calc", {"branch": "old"}, "reviewer", "2026-09-09T00:00:00Z")
    new = create_compatibility_revision(db, {"branch": "new"}, "reviewer", "2026-09-09T00:00:00Z", supersedes=old)
    assert old != new
    with pytest.raises(ValueError, match="immutable"):
        register_calculation_compatibility(db, "fixture-calc", {"branch": "new"}, "reviewer", "2026-09-09T00:00:00Z")
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT revision_id FROM calculation_compatibility_revisions").fetchone()[0] == old
        assert c.execute("SELECT count(*) FROM compatibility_revisions").fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            c.execute("UPDATE compatibility_revisions SET compatibility_json='{}'")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            c.execute("DELETE FROM registry_events")


@pytest.mark.parametrize("reviewed_at", [None, "", "not-a-time", "2026-09-09", "2026-09-09T12:00:00", "2026-99-09T00:00:00Z"])
@pytest.mark.parametrize("operation", ["create", "register"])
def test_compatibility_review_requires_timezone_timestamp_without_writes(tmp_path, reviewed_at, operation):
    db, batch = _database(tmp_path), _batch()
    del batch["rows"]["calculation_compatibility"]
    apply_registry_batch(db, batch, **reviewed(db, batch))
    before = db.read_bytes()
    with pytest.raises(ValueError, match="compatibility review time"):
        if operation == "create":
            create_compatibility_revision(db, {"branch": "fixture"}, "reviewer", reviewed_at)
        else:
            register_calculation_compatibility(db, "fixture-calc", {"branch": "fixture"}, "reviewer", reviewed_at)
    assert db.read_bytes() == before


@pytest.mark.parametrize("reviewed_at", ["2026-09-09T00:00:00Z", "2026-09-09T08:00:00+08:00"])
def test_compatibility_timestamp_preserves_identity_and_historical_review(tmp_path, reviewed_at):
    db, batch = _database(tmp_path), _batch()
    del batch["rows"]["calculation_compatibility"]
    apply_registry_batch(db, batch, **reviewed(db, batch))
    compatibility = {"branch": "fixture"}
    expected = sha256_json(compatibility)
    assert create_compatibility_revision(db, compatibility, "reviewer", reviewed_at) == expected
    assert register_calculation_compatibility(db, "fixture-calc", compatibility, "reviewer", reviewed_at) == expected
    before = db.read_bytes()
    later = "2026-09-10T00:00:00Z"
    assert create_compatibility_revision(db, compatibility, "reviewer", later) == expected
    assert register_calculation_compatibility(db, "fixture-calc", compatibility, "reviewer", later) == expected
    assert db.read_bytes() == before
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT reviewed_at FROM compatibility_revisions").fetchone()[0] == reviewed_at
        assert c.execute("SELECT reviewed_at FROM calculation_compatibility").fetchone()[0] == reviewed_at


@pytest.mark.parametrize("previous,new", [("DONE", "RUNNING"), ("FAILED", "DONE"), ("CREATED", "bogus"), ("FAILED", "UNKNOWN")])
def test_invalid_job_transition_rejected(previous, new):
    with pytest.raises(ValueError):
        validate_job_transition(previous, new)


def test_failed_job_recovery_requires_explicit_event():
    validate_job_transition("FAILED", "DONE", recovery_event={"event_id": "recovery-1", "timestamp": "2026-09-09T00:00:00Z", "actor": "reviewer", "reason": "reconciled scheduler report"})
    with pytest.raises(ValueError):
        validate_job_transition("FAILED", "DONE", recovery_event={"reason": "missing identity"})


def test_event_history_drives_recorded_job_validation(tmp_path):
    db, batch = _database(tmp_path), _batch()
    apply_registry_batch(db, batch, **reviewed(db, batch))
    later = copy.deepcopy(batch)
    later["batch_id"] = "regression"
    later["result_provenance"] = {}
    later["rows"] = {"job_status_history": [{"job_record_id": "fixture-job", "scheduler_status": "RUN", "checked_at": "2026-09-09T00:00:00Z"}]}
    with pytest.raises(ValueError, match="invalid job state"):
        plan_registry_batch(db, later)


def test_prediction_and_unreviewed_accepted_results_rejected(tmp_path):
    db, batch = _database(tmp_path), _batch()
    row = batch["rows"]["results"][0]
    row["validation_status"] = "accepted_compatible_final_energy"
    with pytest.raises(ValueError, match="reviewed evidence"):
        plan_registry_batch(db, batch)
    batch["result_provenance"] = {row["result_id"]: {"type": "model_prediction"}}
    with pytest.raises(ValueError, match="predictions"):
        plan_registry_batch(db, batch)


def test_migration_roundtrip_and_no_hidden_startup_upgrade(tmp_path):
    db = _database(tmp_path)
    assert rollback_registry_v9(db) == 8
    before = db.read_bytes()
    with pytest.raises(ValueError, match="version 9"):
        with open_registry(db, migrate=True):
            pass
    assert db.read_bytes() == before
    assert migrate_registry(db) == 9
    assert rollback_registry_v9(db) == 8


def test_migration_validation_failure_rolls_back_entire_upgrade(tmp_path, monkeypatch):
    import scripts.registry_schema as schema

    db = _database(tmp_path)
    rollback_registry_v9(db)
    before = db.read_bytes()
    monkeypatch.setattr(schema, "validate_schema", lambda c: (_ for _ in ()).throw(ValueError("injected validation")))
    with pytest.raises(ValueError, match="injected"):
        schema.migrate_registry(db)
    assert db.read_bytes() == before


def test_migration_rollback_refuses_to_discard_new_history(tmp_path):
    db, batch = _database(tmp_path), _batch()
    apply_registry_batch(db, batch, **reviewed(db, batch))
    with pytest.raises(ValueError, match="discard"):
        rollback_registry_v9(db)


def test_registry_cli_contains_no_sql_and_reuses_existing_owners():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "scripts/registry_write.py").read_text())
    assert not any(isinstance(node, ast.Attribute) and node.attr in {"execute", "executemany", "executescript"} for node in ast.walk(tree))
    source = (root / "scripts/registry_acceptance.py").read_text()
    assert "from scripts.adsmind_lite.evidence_lifecycle import" in source
    assert "from scripts.vasp_result_gate import" in source


def accepted_batch(tmp_path):
    from scripts.artifact_io import sha256_json, sha256_file
    from scripts.adsmind_lite.evidence_lifecycle import review_subject
    from tests.evidence_fixtures import bound_evidence

    batch = _batch()
    directory = tmp_path / "validated"
    directory.mkdir()
    files = {"INCAR": "NELM=60; EDIFF=1e-5\n", "POSCAR": "synthetic input\n", "CONTCAR": "synthetic output\n",
             "OSZICAR": "RMM: 5 -10 -1e-7 -1e-7 100 1e-4\n1 F= -10 E0= -10 d E= -1e-7\n",
             "OUTCAR": " free  energy   TOTEN  = -10.0 eV\n TOTAL-FORCE (eV/Angst)\n -----\n 0 0 0 0 0 0\n -----\n reached required accuracy\n General timing and accounting informations for this job\n"}
    for name, text in files.items():
        (directory / name).write_text(text)
    compatibility = {"final_energy_convention": "test_toten"}
    batch["rows"]["calculation_compatibility"][0].update(compatibility_fingerprint=sha256_json(compatibility), compatibility_json=json.dumps(compatibility))
    row = batch["rows"]["results"][0]
    row.update(validation_status="accepted_compatible_final_energy", result_name="final_toten", numeric_value=-10., reference_convention="test_toten")
    batch["rows"]["files"][0]["sha256"] = sha256_file(directory / "OUTCAR")
    validation = {"owner": "vasp_relaxation", "directory": str(directory),
                  "source_files": {name: sha256_file(directory / name) for name in files}}
    evidence = bound_evidence(kind="calculated_result", domain="test_module", scope="registry_acceptance", compatibility=compatibility)
    evidence["claim"].update(result_sha256=sha256_json(row), validation_sha256=sha256_json(validation))
    evidence["review"]["subject_sha256"] = review_subject(evidence)
    evidence["transfer"]["review_sha256"] = sha256_json(evidence["review"])
    batch["result_provenance"] = {"fixture-energy": {"type": "calculated_result", "registry_stage": "accepted_result",
                                                    "evidence": evidence, "scientific_validation": validation}}
    return batch


def test_bound_reviewed_scientific_result_enters_registry_and_is_immutable(tmp_path):
    db, batch = _database(tmp_path), accepted_batch(tmp_path)
    apply_registry_batch(db, batch, **reviewed(db, batch))
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT numeric_value FROM results").fetchone()[0] == -10.
        stored = json.loads(c.execute("SELECT payload_json FROM registry_events WHERE event_type='batch_applied'").fetchone()[0])
        assert stored["batch"]["result_provenance"] == batch["result_provenance"]
        for table in ("results", "files", "reviews", "job_status_history"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                c.execute(f"DELETE FROM {table}")


@pytest.mark.parametrize("damage", ["source", "review", "compatibility", "value", "incomplete"])
def test_acceptance_fails_closed_after_evidence_changes(tmp_path, damage):
    from scripts.artifact_io import sha256_json, sha256_file
    from scripts.adsmind_lite.evidence_lifecycle import review_subject

    db, batch = _database(tmp_path), accepted_batch(tmp_path)
    provenance = batch["result_provenance"]["fixture-energy"]
    evidence = provenance["evidence"]
    if damage == "source":
        (tmp_path / "validated/OUTCAR").write_text("changed")
    elif damage == "review":
        evidence["review"]["decision"] = "rejected"
    elif damage == "compatibility":
        evidence["transfer"]["compatibility"] = {"branch": "other"}
    elif damage == "value":
        row = batch["rows"]["results"][0]
        row["numeric_value"] = 900.
        evidence["claim"]["result_sha256"] = sha256_json(row)
    else:
        path = tmp_path / "validated/OSZICAR"
        path.write_text(path.read_text() + "RMM: 1 -11 -1e-1 -1e-1 100 1e-4\n")
        provenance["scientific_validation"]["source_files"]["OSZICAR"] = sha256_file(path)
        evidence["claim"]["validation_sha256"] = sha256_json(provenance["scientific_validation"])
    evidence["review"]["subject_sha256"] = review_subject(evidence)
    evidence["transfer"]["review_sha256"] = sha256_json(evidence["review"])
    with pytest.raises(ValueError):
        plan_registry_batch(db, batch)


def test_recovery_is_persisted_with_failed_to_done_transition(tmp_path):
    db, batch = _database(tmp_path), _batch()
    batch["rows"]["job_status_history"][0]["scheduler_status"] = "FAILED"
    apply_registry_batch(db, batch, **reviewed(db, batch))
    recovery = {"event_id": "recovery-1", "status_event_id": 2, "timestamp": "2026-09-09T01:00:00Z", "actor": "reviewer", "reason": "reconciled terminal evidence"}
    next_batch = {**batch, "batch_id": "recover-1", "result_provenance": {}, "rows": {
        "job_status_history": [{"status_event_id": 2, "job_record_id": "fixture-job", "scheduler_status": "DONE", "checked_at": recovery["timestamp"]}],
        "job_recovery_events": [recovery]}}
    apply_registry_batch(db, next_batch, **reviewed(db, next_batch))
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT scheduler_status FROM job_current_state").fetchone()[0] == "DONE"
        assert c.execute("SELECT count(*) FROM job_status_history").fetchone()[0] == 2
        assert c.execute("SELECT actor FROM job_recovery_events").fetchone()[0] == "reviewer"


def test_replace_cannot_overwrite_historical_scientific_record(tmp_path):
    db, batch = _database(tmp_path), _batch()
    apply_registry_batch(db, batch, **reviewed(db, batch))
    with sqlite3.connect(db) as c:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            c.execute("INSERT OR REPLACE INTO results(result_id,calculation_id,result_name,numeric_value,validation_status,created_at) VALUES ('fixture-energy','fixture-calc','changed',100,'accepted','now')")
        assert c.execute("SELECT numeric_value FROM results").fetchone()[0] == -1.


def test_complete_plan_supports_new_calculation_and_its_transition(tmp_path):
    db, batch = _database(tmp_path), _batch()
    batch["workflow_status_changes"] = [{"status_change_id": "transition-1", "calculation_id": "fixture-calc",
        "expected_workflow_status": "registered", "new_workflow_status": "submitted", "changed_at": "2026-09-09T00:00:00Z",
        "reviewer": "reviewer", "reason": "recorded submitted job"}]
    request = reviewed(db, batch)
    assert request["plan"]["update_count"] == 1
    apply_registry_batch(db, batch, **request)
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT workflow_status FROM calculations").fetchone()[0] == "submitted"


def test_current_version_without_integrity_guards_is_incompatible(tmp_path):
    db = _database(tmp_path)
    with sqlite3.connect(db) as c:
        c.execute("DROP TRIGGER immutable_results_update")
    with pytest.raises(ValueError, match="guards missing"):
        with open_registry(db):
            pass


@pytest.mark.parametrize("failure", [None, "commit", "database_drift"])
def test_promotion_rechecks_database_and_recovers_commit_failure(tmp_path, monkeypatch, failure):
    from contextlib import contextmanager
    import scripts.registry_excel_promotion as promotion
    from tests.test_registry_excel_promotion import _seed_accepted_adsorption, _request

    db = _database(tmp_path)
    _seed_accepted_adsorption(db)
    monkeypatch.setattr(promotion, "ROOT", tmp_path)
    workbook, receipt = tmp_path / "book.xlsx", tmp_path / "receipt.json"
    workbook.write_bytes(b"original workbook")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request(workbook, receipt)))
    plan = promotion.build_plan(request_path, db)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    def writer(plan_path, output, **kwargs):
        output.write_bytes(b"published workbook")
        if failure == "database_drift":
            with sqlite3.connect(db) as c:
                c.execute("INSERT INTO calculations(calculation_id,module,purpose,workflow_status,created_at) VALUES ('drift','test','test','registered','now')")
        return {"row_number": 2}
    monkeypatch.setattr(promotion, "_run_writer", writer)
    original_open = promotion.open_registry
    if failure == "commit":
        @contextmanager
        def failed_commit(database, **kwargs):
            with original_open(database, **kwargs) as connection:
                yield connection
                if connection.execute("SELECT 1 FROM excel_promotions").fetchone():
                    raise sqlite3.OperationalError("injected commit failure")
        monkeypatch.setattr(promotion, "open_registry", failed_commit)
    if failure:
        with pytest.raises((ValueError, sqlite3.OperationalError)):
            promotion.apply_plan(plan_path, database=db, node=tmp_path / "fake", node_modules=tmp_path)
        assert workbook.read_bytes() == b"original workbook"
        assert not receipt.exists()
        with sqlite3.connect(db) as c:
            assert c.execute("SELECT count(*) FROM excel_promotions").fetchone()[0] == 0
    else:
        promotion.apply_plan(plan_path, database=db, node=tmp_path / "fake", node_modules=tmp_path)
        assert workbook.read_bytes() == b"published workbook"
        with sqlite3.connect(db) as c:
            assert c.execute("SELECT count(*) FROM excel_promotions").fetchone()[0] == 1
            assert c.execute("SELECT event_type FROM registry_events").fetchone()[0] == "result_published"


def test_null_primary_identity_rejected_before_mutation(tmp_path):
    db = _database(tmp_path)
    batch = _batch()
    batch["rows"] = {"calculations": [{**batch["rows"]["calculations"][0], "calculation_id": None}]}
    batch["result_provenance"] = {}
    with pytest.raises(ValueError, match="calculation_id"):
        plan_registry_batch(db, batch)


@pytest.mark.parametrize("compatibility", [None, {}, {"encut": float("nan")}])
def test_invalid_compatibility_cannot_create_revision(tmp_path, compatibility):
    db = _database(tmp_path)
    with pytest.raises(ValueError):
        create_compatibility_revision(db, compatibility, "reviewer", "2026-09-09T00:00:00Z")
    with pytest.raises(ValueError):
        register_calculation_compatibility(db, "missing", compatibility, "reviewer", "2026-09-09T00:00:00Z")
