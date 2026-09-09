"""Build and test a real wheel plus editable parity in clean disposable environments."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import os
import re
import subprocess
import sys
import venv
import zipfile
from pathlib import Path


def run(arguments: list[str], cwd: Path, log: Path, *, expected: int = 0) -> str:
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(arguments, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != expected:
        raise RuntimeError(f"release check exit {result.returncode}: {arguments}; see {log}")
    return result.stdout


def audit_wheel(wheel: Path, resource_names: list[str]) -> dict:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        safe_data = {"scripts/_resources/" + name for name in resource_names}
        for name in names:
            allowed = name in safe_data or (name.startswith("scripts/") and name.endswith(".py")) or ".dist-info/" in name
            if not allowed:
                raise ValueError(f"unreviewed wheel member: {name}")
            if any(token in name.lower() for token in (".sqlite", ".pem", "id_ed25519", "/potcar", "/wavecar", "/chgcar", ".safetensors", ".ckpt")):
                raise ValueError(f"excluded wheel member: {name}")
            if re.search(rb"(?m)^-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\r?$", archive.read(name)):
                raise ValueError(f"private key in artifact: {name}")
        wheel_metadata = archive.read(next(name for name in names if name.endswith(".dist-info/WHEEL"))).decode("utf-8")
        if not safe_data <= set(names):
            raise ValueError("wheel is missing enumerated runtime resources")
    return {"filename": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "file_count": len(names), "members": names, "wheel_metadata": wheel_metadata, "excluded_artifacts": []}


def clean_source(source: Path, destination: Path) -> None:
    # Only versioned/indexed release files; never copy development runtime leftovers.
    destination.mkdir(parents=True, exist_ok=False)
    subprocess.run(["git", "checkout-index", "--all", "--prefix", destination.as_posix() + "/"], cwd=source, check=True)


def validate(source: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    checkout, outside = output / "source", output / "outside"
    outside.mkdir()
    clean_source(source, checkout)
    run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(output / "wheels"), str(checkout)],
        outside, output / "build.log")
    wheel, = (output / "wheels").glob("*.whl")
    manifest = json.loads((checkout / "configs/release_resources.json").read_text(encoding="utf-8"))
    artifact = audit_wheel(wheel, manifest["package_runtime_resources"])
    reports = {}
    for mode in ("wheel", "editable"):
        environment = output / (mode + "-venv")
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        install = [str(wheel)] if mode == "wheel" else ["-e", str(checkout)]
        run([str(python), "-m", "pip", "install", *install], outside, output / (mode + "-install.log"))
        report = output / (mode + ".json")
        run([str(python), "-m", "scripts.release_environment", "--source", str(checkout), "--mode", mode, "--output", str(report)],
            outside, output / (mode + "-probe.log"))
        reports[mode] = json.loads(report.read_text(encoding="utf-8"))
        # Repository-only tools must be explicit; they still work with a clean source root.
        if mode == "wheel":
            run([str(python), "-m", "scripts.document_governance", "README.md", "--root", str(checkout), "--links"],
                outside, output / "document-links.log")
            run([str(python), "-m", "scripts.generate_capability_readiness", "--root", str(checkout)],
                outside, output / "readiness.log")
            for module, args in (("scripts.generate_capability_readiness", []), ("scripts.state_manager.cli", ["audit"])):
                log = output / (module.rsplit(".", 1)[-1] + "-context.log")
                run([str(python), "-m", module, *args], outside, log, expected=2 if args else 1)
                assert "REPOSITORY_CONTEXT_REQUIRED" in log.read_text(encoding="utf-8")
    for key in ("console_scripts", "resources", "smoke"):
        assert reports["wheel"][key] == reports["editable"][key], f"editable/wheel parity failed: {key}"
    from scripts.release_environment import dependency_versions
    result = {"builder": {"python": platform.python_version(), "os": platform.platform(), "dependencies": dependency_versions()},
              "evidence_kind": "SOFTWARE_ENVIRONMENT", "status": "PASS", "clean_checkout": True,
              "parity": True, "wheel": artifact, "environments": reports}
    (output / "release_environment.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New disposable output directory, outside the checkout")
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if output.is_relative_to(source):
        raise ValueError("release validation output must be outside the source checkout")
    result = validate(source, output)
    print(json.dumps({"status": result["status"], "parity": result["parity"], "wheel_files": result["wheel"]["file_count"]}))


if __name__ == "__main__":
    main()
