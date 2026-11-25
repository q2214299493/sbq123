"""Fail closed before native mutation when one-job authority is not current."""
import pytest

from archive.fe110_c3_submission_20261027 import submit as controller


@pytest.mark.parametrize(("key", "value"), [
    ("cores", 64), ("maximum_additional_steps", 600), ("force_convergence_eV_A", .05),
    ("source_job_id", "9922625"), ("bundle_sha256", "0" * 64),
    ("remote_target", "~/sbq/Fe110/another_target"),
])
def test_changed_scope_cannot_use_one_job_confirmation(monkeypatch, tmp_path, key, value):
    plan = {"bundle_sha256": controller.BUNDLE, "source_job_id": "9922624", "cores": 32,
            "maximum_additional_steps": 300, "force_convergence_eV_A": .02,
            "changes": {"NSW": ["80", "300"]}, "remote_target": controller.REMOTE}
    plan[key] = value
    monkeypatch.setattr(controller, "load_json_object", lambda _: plan)
    monkeypatch.setattr(controller, "source_file_manifest_valid", lambda _: True)
    authorization = tmp_path / "authority.md"
    authorization.write_text("> 提交", encoding="utf-8")
    monkeypatch.setattr(controller, "AUTH", authorization)
    with pytest.raises(ValueError, match="exact reviewed"):
        controller.approved_plan()


@pytest.mark.parametrize("status", ["SUBMITTED", "UNKNOWN"])
def test_existing_attempt_never_calls_native_submit(monkeypatch, status):
    monkeypatch.setattr(controller, "approved_plan", lambda: {})
    monkeypatch.setattr(controller, "load_json_object", lambda _: {"remote_dir": controller.REMOTE})
    monkeypatch.setattr(controller, "source_file_manifest_valid", lambda _: True)
    monkeypatch.setattr(controller, "submission_status", lambda _: {"status": status})
    monkeypatch.setattr(controller, "submit", lambda *args: pytest.fail("native mutation called"))
    with pytest.raises(ValueError, match="never retry"):
        controller.execute()


def test_stale_gate_never_calls_native_submit(monkeypatch):
    monkeypatch.setattr(controller, "approved_plan", lambda: {})
    monkeypatch.setattr(controller, "load_json_object", lambda _: {})
    monkeypatch.setattr(controller, "source_file_manifest_valid", lambda _: False)
    monkeypatch.setattr(controller, "submit", lambda *args: pytest.fail("native mutation called"))
    with pytest.raises(ValueError, match="binding changed"):
        controller.execute()
