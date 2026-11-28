"""Release-owned content identity of installed scientific configuration."""

TRUST_SHA256 = "9520bb05adb7b10afec4374bf970ab726a7a1e431ecd01b23fd44c431ac1e1da"

SCHEMAS_SHA256 = "978386524e3c24fda0fef6c589b01c5ae2a9a9cdb398cdd892f6623d6dec514c"

# Producer result IDs from the 011b62c trace-correction numerical archive (Windows).
REACTOR_CONTROL_RESULTS = frozenset({
    "bd46dc8bf44c99f026fb4fba0c162bc952e45fbfe7bfeb93be276367d181c8b7",
    "a3f78508a1ba041ba9fd06c6961837a876b42c9c3da1357c30a89fe622ec5593",
})

# Project trust is provisioned by the process operator, outside scientific requests.
# The store cannot authenticate itself. Its exact bytes are pinned by deployment configuration.
def project_records(kind):
    from datetime import datetime
    from hashlib import sha256
    import json
    import os
    from pathlib import Path

    path = os.environ.get("SBQ123_PROJECT_TRUST_STORE")
    digest = os.environ.get("SBQ123_PROJECT_TRUST_SHA256")
    if path is None and digest is None:
        return {}
    if not path or not Path(path).is_absolute() or not digest:
        raise ValueError("Incomplete operator project trust configuration")
    raw = Path(path).read_bytes()
    if sha256(raw).hexdigest() != digest:
        raise ValueError("Project trust store differs from operator pin")
    def unique(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("Duplicate project trust key")
        return result
    store = json.loads(raw, object_pairs_hook=unique)
    if store.get("format") != "sbq123-project-trust/1" or not isinstance(store.get("project"), str) or not store["project"].strip():
        raise ValueError("Unknown project trust format or project")
    result = {}
    for record in store["records"]:
        if record["kind"] != kind:
            continue
        name = record["id"]
        pin = record["sha256"]
        if (not isinstance(name, str) or not name.strip() or name in result or record["decision"] != "approved"
                or not isinstance(record["reviewer"], str) or not record["reviewer"].strip()
                or datetime.fromisoformat(record["reviewed_at"]).utcoffset() is None
                or not isinstance(pin, str) or len(pin) != 64 or any(ch not in "0123456789abcdef" for ch in pin)):
            raise ValueError("Invalid or ambiguous project review")
        result[name] = record
    return result


def approved(kind, digest):
    return any(row["sha256"] == digest for row in project_records(kind).values())


def project_path(locator):
    from pathlib import Path
    import os
    directory = Path(os.environ["SBQ123_PROJECT_TRUST_STORE"]).parent.resolve()
    path = (directory / locator).resolve()
    if not path.is_relative_to(directory):
        raise ValueError("Project record outside trust directory")
    return path


def project_document(kind, key):
    """Read only the independently selected record, relative to the operator-owned store."""
    import json
    from hashlib import sha256

    row = project_records(kind).get(key)
    if row is None:
        return None
    path = project_path(row["path"])
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != row["sha256"]:
        raise ValueError("Project record differs from independent review")
    return json.loads(raw), row["sha256"]
