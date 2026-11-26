"""Check a materialized scientific source version before using its role."""
import hashlib
import json
from pathlib import Path


def verify_role(root, expected):
    root = Path(root).resolve()
    raw = (root / "python-sources.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Different source role or Python version manifest")
    sources = json.loads(raw)
    installed = {p.relative_to(root).as_posix() for p in (root / "scripts").rglob("*.py")}
    if installed != {p for p in sources if p.startswith("scripts/")}:
        raise ValueError("Unexpected source in role environment")
    for relative, digest in sources.items():
        path = root / relative
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Changed role source: {relative}")
