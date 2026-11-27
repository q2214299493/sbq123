"""Build four disjoint wheels in an external directory using the locked build environment."""

import argparse
import base64
import csv
import io
import time
from zipfile import ZipFile, ZipInfo, ZIP_STORED
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DISTS = {"common": ["common", "analysis", "discovery"], "mkm": ["mkm"], "kmc": ["kmc"], "reactor": ["reactor"]}


def portable_wheel(source, output, epoch):
    """Canonical UTC timestamp, modes, ordering and RECORD for pure-Python wheels."""
    stamp = time.gmtime(max(315532800, int(epoch)))[:6]
    with ZipFile(source) as original, ZipFile(output, "x") as target:
        names = original.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate wheel archive path")
        (record,) = (n for n in names if n.endswith(".dist-info/RECORD"))
        expected = {n: (digest, size) for n, digest, size in csv.reader(io.StringIO(original.read(record).decode()))}
        if set(expected) != set(names):
            raise ValueError("Wheel inventory mismatch")
        rows = io.StringIO(newline="")
        writer = csv.writer(rows, lineterminator="\n")

        def write(name, data):
            info = ZipInfo(name, stamp)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            target.writestr(info, data, compress_type=ZIP_STORED)

        for name in sorted((n for n in names if n != record), key=lambda n: (".dist-info/" in n, n)):
            data = original.read(name)
            digest = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
            if expected[name] != (digest, str(len(data))):
                raise ValueError("Invalid built wheel hash: " + name)
            if name == record.rsplit("/", 1)[0] + "/METADATA":
                # Setuptools uses the platform newline in this generated text member.
                data = data.replace(b"\r\n", b"\n")
                digest = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
            write(name, data)
            writer.writerow((name, digest, len(data)))
        writer.writerow((record, "", ""))
        write(record, rows.getvalue().encode())


def build(owner, dest):
    dest = dest.resolve()
    if dest.is_relative_to(ROOT):
        raise ValueError("Choose an external output directory")
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest) as temp:
        tmp = Path(temp)
        package = tmp / "packages" / owner
        package.mkdir(parents=True)
        shutil.copyfile(ROOT / "packages" / owner / "pyproject.toml", package / "pyproject.toml")
        for name in DISTS[owner]:
            shutil.copytree(
                ROOT / "src/sbq123" / name, tmp / "src/sbq123" / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info")
            )
        env = os.environ.copy()
        env.setdefault("SOURCE_DATE_EPOCH", "1795600000")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-build-isolation",
                "--no-index",
                "--no-deps",
                "--wheel-dir",
                str(tmp / "wheel"),
                str(package),
            ],
            check=True,
            env=env,
        )
        (wheel,) = (tmp / "wheel").glob("*.whl")
        canonical = tmp / wheel.name
        portable_wheel(wheel, canonical, env["SOURCE_DATE_EPOCH"])
        wheel = canonical
        output = dest / wheel.name
        try:
            os.link(wheel, output)
        except FileExistsError:
            if hashlib.sha256(output.read_bytes()).digest() != hashlib.sha256(wheel.read_bytes()).digest():
                raise ValueError(f"Existing wheel differs: {output}")
        return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--role", choices=DISTS)
    args = parser.parse_args()
    for role in [args.role] if args.role else DISTS:
        print(build(role, args.output))
