"""Bundle the active sources as resources to avoid deep intermediate paths in Windows wheel builds."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from setuptools.command.build import build
from setuptools.command.build_py import build_py


class BuildRelease(build_py):
    def run(self):
        super().run()
        base = Path(__file__).resolve().parent
        roles = json.loads((base / "roles.json").read_bytes())
        sources = {entry["source"]: entry["sha256"] for entry in roles.values() if "source" in entry}
        target = Path(self.build_lib) / "sbq123_v31" / "role-sources.zip"
        with ZipFile(target, "w") as archive:
            for relative, expected in sorted(sources.items()):
                data = (base / relative).read_bytes()
                if hashlib.sha256(data).hexdigest() != expected:
                    raise ValueError(f"Changed release source {relative}")
                archive.writestr(ZipInfo(relative), data, compress_type=ZIP_DEFLATED)

# Read next to the installed role code by verify_role, compare and evidence_path.
ROLE_METADATA = ("python-sources.json", "release-identity.json", "evidence-mounts.json")


class BuildRole(build):
    """Retain the role's existing build_py resource hook and install its runtime identities."""

    def run(self):
        super().run()
        for name in ROLE_METADATA:
            self.copy_file(name, str(Path(self.build_lib) / name))


def stage_role(source, checkout, stage):
    """Select only approved Python modules and declared runtime resources for one wheel."""
    manifest = json.loads((source / "python-sources.json").read_bytes())
    top_modules = []
    for relative, expected in sorted(manifest.items()):
        path = source / relative
        if path.suffix != ".py" or not path.resolve().is_relative_to(source):
            raise ValueError(f"Invalid role source: {relative}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Changed role source: {relative}")
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if path.parent == source:
            top_modules.append(path.stem)

    resource_map = "configs/release_resources.json"
    resources = json.loads((source / resource_map).read_bytes())
    for relative in [resource_map, *resources["package_runtime_resources"]]:
        origin = source if (source / relative).is_file() else checkout
        path = (origin / relative).resolve()
        if not path.is_relative_to(origin) or not path.is_file():
            raise ValueError(f"Missing or invalid declared role resource: {relative}")
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)

    for name in ROLE_METADATA:
        shutil.copyfile(source / name, stage / name)
    # Extend the verified role metadata only in the disposable distribution source.
    metadata = (source / "pyproject.toml").read_text(encoding="utf8")
    sections = {
        "[tool.setuptools]": "py-modules = " + json.dumps(top_modules),
        "[tool.setuptools.cmdclass]": 'build = "_v31_wheel_build.BuildRole"',
    }
    for header, setting in sections.items():
        marker = header + "\n"
        if metadata.count(marker) != 1:
            raise ValueError(f"Expected one {header} section in role metadata")
        metadata = metadata.replace(marker, marker + setting + "\n")
    (stage / "pyproject.toml").write_text(metadata, encoding="utf8")
    shutil.copyfile(__file__, stage / "_v31_wheel_build.py")


def check_role_wheel(wheel, source):
    expected = json.loads((source / "python-sources.json").read_bytes())
    with ZipFile(wheel) as archive:
        modules = {name for name in archive.namelist() if name.endswith(".py")}
        if modules != expected.keys():
            raise ValueError(f"Role wheel Python inventory differs: {sorted(modules ^ expected.keys())}")
        for name, digest in expected.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f"Role wheel source differs: {name}")
        for name in ROLE_METADATA:
            if archive.read(name) != (source / name).read_bytes():
                raise ValueError(f"Role wheel metadata differs: {name}")


def build_role_wheel(role, output):
    """Build from a clean release checkout, using the role's own entry points and dependencies."""
    from prepare import install

    checkout = Path(__file__).resolve().parents[1]
    output = output.resolve() / role
    if output.is_relative_to(checkout):
        raise ValueError("Choose a wheel destination outside the checkout")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v31-role-") as temporary:
        work = Path(temporary).resolve()
        pair = install(work / "pair")
        stage = work / "build"
        stage.mkdir()
        stage_role(pair / role, checkout, stage)
        # Keep publication on one filesystem. An existing output is never replaced.
        with tempfile.TemporaryDirectory(dir=output) as publish:
            subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-index",
                            "--no-build-isolation", "-w", publish, str(stage)], check=True)
            wheel, = Path(publish).glob("*.whl")
            check_role_wheel(wheel, pair / role)
            destination = output / wheel.name
            os.link(wheel, destination)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build an independent V3.1 wheel from the release checkout.")
    parser.add_argument("role", choices=("mkm", "kmc"))
    parser.add_argument("output", type=Path, help="external directory; wheels are separated by role")
    args = parser.parse_args()
    print(build_role_wheel(args.role, args.output))
