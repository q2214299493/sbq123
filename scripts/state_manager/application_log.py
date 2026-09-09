"""Durable state-projection attempts; serialize applies and never retry an unknown crash."""
from contextlib import contextmanager
import json
import os
from uuid import uuid4

from scripts.artifact_io import sha256_json
from .models import utc_now
from .store import _write_immutable_json


class ReconciliationRequired(RuntimeError):
    """A partial application could not be rolled back; preserve its reservation."""


@contextmanager
def reserved_application(cache, proposal):
    cache.mkdir(parents=True, exist_ok=True)
    lock = cache / "application.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError("state apply locked or UNKNOWN_NEEDS_RECONCILIATION; never automatically retry") from exc
    digest = sha256_json({key: proposal[key] for key in ("proposal_id", "event_sha256", "actions", "review_required")})
    receipt_path = cache / "applications" / (proposal["proposal_id"] + ".json")
    preserve_lock = False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"proposal_sha256": digest, "status": "UNKNOWN_NEEDS_RECONCILIATION"}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt["proposal_sha256"] != digest:
                raise ValueError("applied proposal content changed")
            yield {"receipt": receipt}
            return
        attempt = uuid4().hex
        event = {"proposal_id": proposal["proposal_id"], "proposal_sha256": digest, "timestamp": utc_now()}
        _write_immutable_json(cache / "applications" / (attempt + ".started.json"), {**event, "status": "APPLY_STARTED"})
        try:
            yield {"receipt": None, "finish": lambda: _write_immutable_json(receipt_path, {**event, "status": "APPLIED"})}
        except BaseException as error:
            preserve_lock = isinstance(error, ReconciliationRequired)
            _write_immutable_json(cache / "applications" / (attempt + ".failed.json"),
                                  {**event, "status": "UNKNOWN_NEEDS_RECONCILIATION" if preserve_lock else "FAILED", "error": str(error)})
            raise
    finally:
        if not preserve_lock:
            lock.unlink(missing_ok=True)
