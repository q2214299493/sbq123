import json

import pytest

from archive.fe110_five_c2_adsorption_20261006 import test_adsorption_finetune as legacy
from archive.fe110_adsorption_training_comparison_20261019.test_package import add_roles
from archive.fe110_adsorption_direct_training_20261020 import portable_preflight as portable
from scripts.adsorption.force_finetune import build_database

fixture_manifest = legacy.fixture_manifest


@pytest.fixture
def prepared(fixture_manifest):
    path, payload = fixture_manifest
    add_roles(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    for split in ("train", "development"):
        build_database(path, path.parent / (split + ".db"), split)
    return path, payload


@pytest.mark.parametrize("difference,accepted", [(0., True), (1e-15, True), (2e-12, False)])
def test_only_sub_picometer_decode_roundoff_is_allowed(prepared, monkeypatch, difference, accepted):
    path, _ = prepared
    original = portable.read
    def changed(*args, **kwargs):
        atoms = original(*args, **kwargs)
        atoms.positions[0, 0] += difference
        return atoms
    monkeypatch.setattr(portable, "read", changed)
    if accepted:
        result = portable.portable_database(path.parent, {"manifest_path": path.name})
        assert result["rows"] == 2 and result["raw_forces_cell_PBC_exact"]
    else:
        with pytest.raises(ValueError, match="coordinate"):
            portable.portable_database(path.parent, {"manifest_path": path.name})


def test_no_force_tolerance_is_introduced(prepared):
    path, payload = prepared
    payload["splits"]["train"][0]["forces_eV_per_A"][18][0] += 1e-12
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="raw forces"):
        portable.portable_database(path.parent, {"manifest_path": path.name})
