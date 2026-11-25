"""Exercise native assembly in clean interpreters with the other engine unavailable."""
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("engines", [
    ("catkinas",), ("zacros",), ("catkinas", "zacros"), ("zacros", "catkinas"),
])
def test_only_selected_native_packages_load(engines):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-m", "tests.test_native_imports", *engines],
                            cwd=root, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def probe(engines):
    import importlib
    import json

    packages = {"catkinas": "scripts.baseline_mkm", "zacros": "scripts.surface_kmc"}
    blocked = set(packages.values())

    class BlockUnselected:
        def find_spec(self, fullname, path, target=None):
            if any(fullname == name or fullname.startswith(name + ".") for name in blocked):
                raise AssertionError(f"Import of unselected engine: {fullname}")
            return None

    sys.meta_path.insert(0, BlockUnselected())
    from scripts.native_model import assemble
    importlib.import_module("scripts.rate_output_v2")

    reports = Path("reports/multiphase")
    dataset = json.loads((reports / "phase2_4/synthetic_interface_dataset.json").read_bytes())
    config = json.loads(Path("tests/fixtures/multiphase/native_interface_config.json").read_bytes())
    for engine in engines:
        package = packages[engine]
        blocked.remove(package)
        files, manifest = assemble(engine, dataset, config)
        assert package + ".native" in sys.modules
        importlib.import_module(package + ".rate_adapter")
        assert blocked.isdisjoint(sys.modules)
        reference = reports / "phase2_5" / engine
        assert manifest == json.loads((reference / "manifest.json").read_bytes())
        assert all(data.encode() == (reference / name).read_bytes() for name, data in files.items())


if __name__ == "__main__":
    probe(sys.argv[1:])
