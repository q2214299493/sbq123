"""Inspect an installed distribution without scientific or external execution."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from scripts import runtime_resources
from scripts.release_smoke import run_smoke

DEPENDENCIES = ("jsonschema", "numpy", "PyYAML", "ase", "sella", "pymatgen",
                "matplotlib", "sentence-transformers", "setuptools", "build", "wheel")


def dependency_versions() -> dict:
    result = {}
    for name in DEPENDENCIES:
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = "NOT_INSTALLED"
    return result


def inspect_install(source: Path, mode: str, outside: Path) -> dict:
    package = Path(runtime_resources.__file__).resolve()
    if mode == "wheel":
        assert package.is_relative_to(Path(sys.prefix).resolve()), package
        assert not any(Path(p).resolve().is_relative_to(source) for p in sys.path if p), sys.path
    else:
        assert package.is_relative_to(source), package
    distribution = metadata.distribution("sbq-catalyst-agent-workflow")
    commands = {}
    binary_dir = Path(sys.executable).parent
    for entry in sorted(distribution.entry_points, key=lambda item: item.name):
        if entry.group != "console_scripts":
            continue
        executable = binary_dir / (entry.name + (".exe" if sys.platform == "win32" else ""))
        result = subprocess.run([str(executable), "--help"], cwd=outside, text=True, encoding="utf-8", capture_output=True)
        if result.returncode:
            raise RuntimeError(f"installed entrypoint failed: {entry.name}\n{result.stderr}")
        commands[entry.name] = {"exit_code": 0, "help_sha256": hashlib.sha256(result.stdout.encode()).hexdigest()}
    resource_list = json.loads(runtime_resources.resource_path("configs/release_resources.json").read_text(encoding="utf-8"))
    resources = {}
    for name in resource_list["package_runtime_resources"]:
        data = runtime_resources.resource_path(name).read_bytes()
        assert data == (source / name).read_bytes(), name
        resources[name] = hashlib.sha256(data).hexdigest()
    smoke_root = outside / (mode + "-smoke")
    smoke_root.mkdir()
    smoke = run_smoke(smoke_root)
    return {"evidence_kind": "SOFTWARE_ENVIRONMENT", "python": platform.python_version(),
            "os": platform.platform(), "package_version": distribution.version,
            "requires_python": distribution.metadata["Requires-Python"], "dependencies": dependency_versions(),
            "installation": mode, "console_scripts": commands, "resources": resources, "smoke": smoke}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--mode", choices=("wheel", "editable"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = inspect_install(args.source.resolve(), args.mode, Path.cwd())
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
