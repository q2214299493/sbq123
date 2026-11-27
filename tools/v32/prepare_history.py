"""Export authenticated V3.1 test and data fixtures without its runtime source modules."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import zipfile

from sbq123.common.artifacts.legacy_views import launchers
from sbq123.common.artifacts.materialize import materialize

ROLE_MANIFEST = "07ae334171b65f1f55bd1d6c314d0b7219151abe29af14016957d769ef4e769f"


def prepare(source, role, target):
    raw = (source / "roles.json").read_bytes()
    if sha256(raw).hexdigest() != ROLE_MANIFEST:
        raise ValueError("Different V3.1 role inventory")
    selected = {}
    for key, e in json.loads(raw).items():
        side, rel = key.split("/", 1)
        if side != role or rel.startswith("scripts/") or ("/" not in rel and rel.endswith(".py")):
            continue
        selected[rel] = e
    stubs = launchers(role)
    manifest = {rel: e["sha256"] for rel, e in selected.items()}
    manifest.update({rel: sha256(data).hexdigest() for rel, data in stubs.items()})
    with zipfile.ZipFile(source / "offline-data.zip") as archive:

        def read(rel):
            if rel in stubs:
                return stubs[rel]
            e = selected[rel]
            return (source / e["source"]).read_bytes() if "source" in e else archive.read(e["sha256"])

        return materialize(target, manifest, read)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("v31", type=Path)
    parser.add_argument("role", choices=["mkm", "kmc"])
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    print(prepare(args.v31, args.role, args.target))
