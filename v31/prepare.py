"""Materialize a checked pair in a fresh external directory. Uses only the standard library."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

BASE = Path(__file__).resolve().parent


def read(name):
    return json.loads((BASE / name).read_bytes())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def install(destination):
    destination = Path(destination).resolve()
    checkout = BASE.parent
    if destination.is_relative_to(checkout) or destination.exists():
        raise ValueError("Choose a new directory outside the source checkout")
    release = read("release.json")
    raw = (BASE / "roles.json").read_bytes()
    if digest(raw) != release["role_manifest_sha256"]:
        raise ValueError("Role manifest differs from release")
    entries = json.loads(raw)
    destination.mkdir(parents=True)
    with ExitStack() as files:
        evidence = files.enter_context(ZipFile(BASE / "offline-data.zip"))
        bundled = BASE / "role-sources.zip"
        sources = files.enter_context(ZipFile(bundled)) if bundled.is_file() else None
        for key, entry in entries.items():
            role, relative = key.split("/", 1)
            root = destination / role
            path = (root / relative).resolve()
            if role not in ("mkm", "kmc") or not path.is_relative_to(root):
                raise ValueError(f"Invalid role path {key}")
            if "source" in entry:
                source = (BASE / entry["source"]).resolve()
                if not source.is_relative_to(BASE):
                    raise ValueError(f"Invalid source {key}")
                data = sources.read(entry["source"]) if sources is not None else source.read_bytes()
            else:
                data = evidence.read(entry["sha256"])
            if digest(data) != entry["sha256"]:
                raise ValueError(f"Source or evidence differs: {key}")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as output:
                output.write(data)
    for role in ("mkm", "kmc"):
        (destination / role / "release-identity.json").write_text(
            json.dumps({"role": role, "versions": release["role_versions"]}), encoding="utf8")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    print(install(parser.parse_args().destination))
