"""Accepted point fixtures use a mocked CATKINAS launcher and replayed MAT data."""

from copy import deepcopy

from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file
from scripts.baseline_mkm.result_binding import bind_result
from scripts.kinetic_data.scientific_identity import check_binding
from test_mkm_single_point import runtime  # noqa: F401
from test_mkm_steady_states import PROFILE, accept, pair  # noqa: F401


def test_observed_root_conditions_and_execution(pair):  # noqa: F811
    path, _ = pair
    points = []
    for name in ("point-001", "point-002"):
        assert accept(path, name) == "ACCEPTED"
        run = path.parent / name
        result = bind_result(run)
        assert result["execution"]["result_sha256"] == sha256_file(run / "result.json")
        assert result["execution"]["receipt_sha256"] == sha256_file(run / "ACCEPTED.json")
        assert result["conditions"]["temperature_K"] == 400
        points.append(result)
    a, b = points
    assert a["root"]["native_initial"] != b["root"]["native_initial"]
    assert a["root_state_sha256"] == b["root_state_sha256"]
    assert a["binding_sha256"] != b["binding_sha256"]
    check_binding(a, bind_result(path.parent / "point-001"))
    for key in ("conditions", "root", "execution"):
        forged = deepcopy(a)
        forged[key] = {}
        with pytest.raises(ValueError, match="reconstructed"):
            check_binding(forged, a)


@pytest.mark.parametrize("filename", ["network.json", "dataset.json", "configuration.json"])
def test_changed_input_bytes_fail_even_with_same_json(pair, filename):  # noqa: F811
    path, _ = pair
    assert accept(path, "point-001") == "ACCEPTED"
    run = path.parent / "point-001"
    with (run / filename).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="approved plan"):
        bind_result(run)

def test_legacy_profile_is_separately_attributed():
    run = Path(__file__).resolve().parents[1] / "archive/v221_catkinas/nicu-v221-400k-001"
    binding = bind_result(run, normalization_profile=PROFILE)
    assert binding["profile_bound_by_plan"] is False
    assert binding["normalization_profile_sha256"] == sha256_file(PROFILE)
    assert binding["execution"]["result_sha256"] == sha256_file(run / "result.json")
