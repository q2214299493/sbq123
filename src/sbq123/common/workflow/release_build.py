"""Setuptools build step: copy only enumerated runtime resources from their owners."""
from __future__ import annotations

import json
from pathlib import Path

from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self) -> None:
        super().run()
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "configs/release_resources.json").read_text(encoding="utf-8"))
        for relative in manifest["package_runtime_resources"]:
            source = (root / relative).resolve()
            if not source.is_relative_to(root) or not source.is_file():
                raise ValueError(f"invalid release resource: {relative}")
            target = Path(self.build_lib) / "scripts/_resources" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            self.copy_file(str(source), str(target))
