"""Authoritative recorded job/workflow transitions; no scheduler or scientific authority."""
from scripts.provenance_fields import required_text, timestamp

JOB_ALIASES = {"PEND": "SUBMITTED", "RUN": "RUNNING", "EXIT": "FAILED"}
JOB_TRANSITIONS = {
    "CREATED": {"SUBMITTED", "RUNNING", "DONE", "FAILED", "UNKNOWN"},
    "SUBMITTED": {"RUNNING", "DONE", "FAILED", "UNKNOWN"},
    "RUNNING": {"DONE", "FAILED", "UNKNOWN"},
    "UNKNOWN": {"SUBMITTED", "RUNNING", "DONE", "FAILED"},
    "DONE": set(), "FAILED": set(),
}
WORKFLOW_TRANSITIONS = {
    "registered": {"submitted", "running", "accepted", "needs_review", "failed", "unknown"},
    "submitted": {"running", "done", "failed", "unknown", "needs_review", "accepted"},
    "running": {"done", "failed", "unknown", "needs_review", "accepted"},
    "done": {"needs_review", "accepted", "duplicate", "static_needed"},
    "needs_review": {"accepted", "rejected", "static_needed", "duplicate"},
    "static_needed": {"submitted", "needs_review", "accepted"},
    "accepted": {"excel_promoted"}, "excel_promoted": set(), "rejected": set(),
    "duplicate": set(), "failed": set(), "unknown": {"submitted", "running", "done", "failed"},
}


def validate_job_transition(previous, new, *, recovery_event=None):
    previous, new = JOB_ALIASES.get(previous, previous), JOB_ALIASES.get(new, new)
    if previous not in JOB_TRANSITIONS or new not in JOB_TRANSITIONS:
        raise ValueError("unknown job state")
    if previous == new:
        return
    if previous == "FAILED" and new in {"SUBMITTED", "RUNNING", "DONE"} and recovery_event:
        for field in ("event_id", "actor", "reason"):
            required_text(recovery_event.get(field), f"recovery {field}")
        timestamp(recovery_event.get("timestamp"), "recovery timestamp")
        return
    if new not in JOB_TRANSITIONS[previous]:
        raise ValueError(f"invalid job state transition: {previous} -> {new}")


def validate_job_history(connection, job_id):
    rows = connection.execute("SELECT * FROM job_status_history WHERE job_record_id=? ORDER BY status_event_id", (job_id,)).fetchall()
    previous = "CREATED"
    last_time = None
    for row in rows:
        observed = timestamp(row["checked_at"], "job observation time")
        if last_time and observed < last_time:
            raise ValueError("job event timestamp regresses")
        recovery = connection.execute("SELECT * FROM job_recovery_events WHERE status_event_id=?", (row["status_event_id"],)).fetchone()
        recovery = dict(recovery) if recovery else None
        if recovery and timestamp(recovery["timestamp"], "recovery timestamp") < observed:
            raise ValueError("recovery event predates observation")
        validate_job_transition(previous, row["scheduler_status"], recovery_event=recovery)
        previous, last_time = row["scheduler_status"], observed


def validate_workflow_transition(change):
    for key in ("status_change_id", "calculation_id", "reviewer", "reason"):
        required_text(change.get(key), key)
    timestamp(change.get("changed_at"), "transition timestamp")
    previous, new = change["expected_workflow_status"], change["new_workflow_status"]
    if new not in WORKFLOW_TRANSITIONS.get(previous, set()):
        raise ValueError(f"invalid workflow state transition: {previous} -> {new}")
