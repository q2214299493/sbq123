import pytest


@pytest.fixture
def approve_project_record(tmp_path, monkeypatch):
    """Provision a detached test operator store independently of the calculation request."""
    import hashlib
    import json

    def select(kind, pin):
        row = dict(kind=kind, id="test-review", sha256=pin, reviewer="test operator", decision="approved",
                   reviewed_at="2026-11-28T00:00:00Z")
        raw = json.dumps(dict(format="sbq123-project-trust/1", project="manufactured-control", records=[row])).encode()
        path = tmp_path / "operator-review.json"
        path.write_bytes(raw)
        monkeypatch.setenv("SBQ123_PROJECT_TRUST_STORE", str(path))
        monkeypatch.setenv("SBQ123_PROJECT_TRUST_SHA256", hashlib.sha256(raw).hexdigest())
    return select
