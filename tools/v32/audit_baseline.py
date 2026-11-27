"""Inventory the V3.1 Git tree, sealed role bytes, and both generations of variants."""

import argparse
import ast
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

BASE = "1e899d0d91e0948ed3739b9d623dbbe9e31de637"
TREE = "88528eba2de8903ab161e64493abbb846cf94a41"
ROOT = Path(__file__).resolve().parents[2]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_rows(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def inventory(output):
    def git(*args):
        return subprocess.check_output(["git", "-C", ROOT, *args])

    if git("rev-parse", BASE + "^{tree}").decode().strip() != TREE:
        raise ValueError("Incorrect release tree")
    output.mkdir(parents=True, exist_ok=True)
    tracked = [entry.split(b"\t", 1) for entry in git("ls-tree", "-rz", BASE).split(b"\0") if entry]
    blobs = {name.decode(): meta.decode().split()[-1] for meta, name in tracked}

    def blob(name):
        return git("cat-file", "blob", blobs[name])

    release = json.loads(blob("v31/release.json"))
    manifests = {}
    for name, identity in [("roles", "role_manifest_sha256"), ("accepted-frozen", "frozen_manifest_sha256")]:
        data = blob(f"v31/{name}.json")
        if digest(data) != release[identity]:
            raise ValueError(name)
        manifests[name] = json.loads(data)
    active = manifests["roles"]
    archived = manifests["accepted-frozen"]
    active_sha = {n: v["sha256"] for n, v in active.items()}
    variants = []
    for name, manifest in [("frozen", archived), ("release", active_sha)]:
        for key in sorted(manifest):
            role, rel = key.split("/", 1)
            other = "kmc/" + rel
            if role == "mkm" and other in manifest and manifest[key] != manifest[other]:
                variants.append((name, rel, manifest[key], manifest[other]))
    write_rows(output / "role-variants.csv", ("generation", "path", "mkm_sha256", "kmc_sha256"), variants)
    source_keys = {}
    assets = []
    edges = set()
    with zipfile.ZipFile(io.BytesIO(blob("v31/offline-data.zip"))) as z:
        names = set(z.namelist())
        if len(names) != len(z.namelist()):
            raise ValueError("Duplicate evidence archive members")
        for key, entry in sorted(active.items()):
            role, rel = key.split("/", 1)
            other = ("mkm" if role == "kmc" else "kmc") + "/" + rel
            owner = "common" if active_sha.get(other) == entry["sha256"] else role
            locator = entry.get("source")
            if locator:
                source = "v31/" + locator
                # The release catalogue also pins every working-tree byte.
                raw = (ROOT / source).read_bytes()
                source_keys.setdefault(source, set()).add(owner)
            else:
                source = "v31/offline-data.zip!/" + entry["sha256"]
                raw = z.read(entry["sha256"])
            if digest(raw) != entry["sha256"]:
                raise ValueError(key)
            assets.append((role, rel, owner, source, entry["sha256"]))
            if rel.endswith(".py"):
                for node in ast.walk(ast.parse(raw, filename=key)):
                    imports = []
                    if isinstance(node, ast.ImportFrom):
                        imports.append("." * node.level + (node.module or ""))
                    elif isinstance(node, ast.Import):
                        imports.extend(i.name for i in node.names)
                    edges.update((role, rel, i) for i in imports)
    write_rows(output / "role-assets.csv", ("role", "path", "owner", "v31_locator", "sha256"), assets)
    write_rows(output / "baseline-imports.csv", ("role", "source", "imports"), sorted(edges))
    rows = []
    for source, oid in sorted(blobs.items()):
        owners = source_keys.get(source, set())
        owner = "common" if owners == {"common"} else ",".join(sorted(owners)) or "legacy"
        rows.append((source, oid, owner))
    write_rows(output / "baseline-ownership.csv", ("git_path", "git_blob", "role_ownership"), rows)
    print(len(rows), "tracked paths;", len(assets), "verified role assets;", len(edges), "static import edges")
    print({g: sum(s == g and p.endswith(".py") for s, p, *_ in variants) for g in ("frozen", "release")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    inventory(parser.parse_args().output)
