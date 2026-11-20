from hashlib import sha256

import pytest
import yaml

from scripts.fe110_mlip_selection import ROLES, select_model


@pytest.fixture
def binding(tmp_path):
    checkpoint = tmp_path / "user.model"
    checkpoint.write_bytes(b"selected checkpoint")
    authority = tmp_path / "execution_backends.yaml"
    authority.write_text(yaml.safe_dump({"fe110_mlip_default": {
        "roles": list(ROLES),
        "family": "mace",
        "model": {
            "path": str(checkpoint),
            "sha256": sha256(checkpoint.read_bytes()).hexdigest(),
            "head": "Default",
            "dtype": "float64",
            "required_atomic_numbers": [1, 6, 8, 26],
        },
        "calibration": "uncalibrated",
        "remote_gpu": "not_validated",
        "training": "not_connected",
    }}), encoding="utf-8")
    return authority, checkpoint


@pytest.mark.parametrize("role", ROLES)
def test_new_tasks_select_mace_without_inheriting_calibration(binding, role):
    authority, checkpoint = binding
    selected = select_model(role, authority=authority)
    assert selected["model"]["path"] == str(checkpoint)
    assert selected["family"] == "mace"
    assert selected["calibration"] == "uncalibrated"
    assert selected["remote_gpu"] == "not_validated"
    assert selected["training"] == "not_connected"


def test_modified_checkpoint_fails_closed(binding):
    authority, checkpoint = binding
    checkpoint.write_bytes(b"wrong file")
    with pytest.raises(ValueError, match="hash mismatch; no model fallback"):
        select_model("ts_path_search", authority=authority)


def test_cannot_relabel_mace_as_old_model(binding):
    authority, _ = binding
    authority.write_text(authority.read_text(encoding="utf-8").replace("family: mace", "family: aqcat25"),
                         encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported Fe"):
        select_model("adsorption_prerelaxation", authority=authority)
