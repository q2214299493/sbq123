from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_workflow_scripts_are_packaged_without_runtime_path_injection() -> None:
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    included = configuration["tool"]["setuptools"]["packages"]["find"]["include"]

    assert included == ["scripts", "scripts.*"]
    offenders = []
    for path in (ROOT / "scripts").rglob("*.py"):
        if "sys.path.insert" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
