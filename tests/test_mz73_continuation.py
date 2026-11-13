from __future__ import annotations

import copy
import shlex

import pytest
import yaml

from scripts.neb_agent import mz73_continuation as continuation
from scripts.neb_agent import mz73_static as static


@pytest.mark.parametrize("name", [continuation.NAMES[0], continuation.NAMES[-1]])
def test_exact_boundary_rounds_keep_single_GPU_and_60minute_limit(name):
    backend = static.load_mz73_static_backend(name)
    assert backend["requires_continuation_authorization"]
    assert backend["memory"] == "15G" and backend["time_limit"] == "01:00:00"
    assert backend["gpus"] == backend["mpi_ranks"] == 1
    assert backend["cpus_per_task"] == 4 and backend["automatic_retries"] == 0
    assert not backend["automatic_remote_submission"]
    assert not backend["final_energy_or_ts_acceptance"]


@pytest.mark.parametrize("name", [continuation.PREFIX + "000_label", continuation.PREFIX + "001_label",
                                 continuation.NAMES[0], continuation.NAMES[-1]])
def test_actual_launcher_and_submit_command_use_the_approved_memory_cap(name):
    backend = static.load_mz73_static_backend(name)
    expected = backend['memory']
    assert f'#SBATCH --mem={expected}\n' in static.render_launcher(backend)
    command = shlex.split(static.sbatch_command(backend, backend['remote_root'] + '/' + name))
    assert [arg for arg in command if arg.startswith('--mem=')] == ['--mem=' + expected]


def test_a_stale_16GiB_header_cannot_pass_a_15GiB_continuation_preflight(tmp_path):
    backend = static.load_mz73_static_backend(continuation.NAMES[0])
    path = tmp_path / 'script.sbatch'
    path.write_text(static.render_launcher(backend).replace('#SBATCH --mem=15G', '#SBATCH --mem=16G'))
    with pytest.raises(ValueError, match='launcher'):
        static.validate_launcher(backend, path)


@pytest.mark.parametrize("name", ["paper_chco_aqcat25_ft512_20261112_r250_label", "other_r002_label"])
def test_round_ceiling_and_other_case_names_are_not_registered(name):
    with pytest.raises(ValueError, match="scoped"):
        static.load_mz73_static_backend(name)


@pytest.mark.parametrize(("key", "value"), [("force_target_eV_per_A", 0.05), ("last_round_index", 250),
                                          ("automatic_retries", 1), ("time_limit", "02:00:00"),
                                          ("authorization_sha256", "0" * 64)])
def test_continuation_scope_cannot_be_expanded(tmp_path, key, value):
    payload = yaml.safe_load(static.DEFAULT_CONFIG.read_text())
    payload["backends"][static.BACKEND_ID]["continuous_active_learning"][key] = value
    path = tmp_path / "backend.yaml"
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValueError, match="scope"):
        static.load_mz73_static_backend(continuation.NAMES[0], config_path=path)


def test_legacy_config_cannot_silently_adopt_continuation_rounds(tmp_path):
    payload = yaml.safe_load(static.DEFAULT_CONFIG.read_text())
    backend = payload["backends"][static.BACKEND_ID]
    backend.pop("continuous_active_learning")
    path = tmp_path / "unapproved.yaml"
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValueError, match="explicit"):
        static.load_mz73_static_backend(continuation.NAMES[0], config_path=path)
    backend["allowed_workdir_names"] = list(continuation.LEGACY_NAMES)
    path.write_text(yaml.safe_dump(payload))
    assert static.load_mz73_static_backend(continuation.PREFIX + "000_label", config_path=path)["time_limit"] == "00:30:00"
    with pytest.raises(ValueError, match="scoped"):
        static.load_mz73_static_backend(continuation.NAMES[0], config_path=path)


def test_added_or_missing_leaf_cannot_change_registered_continuation_scope():
    backend = yaml.safe_load(static.DEFAULT_CONFIG.read_text())["backends"][static.BACKEND_ID]
    for names in [backend["allowed_workdir_names"] + [continuation.PREFIX + "250_label"],
                  [name for name in backend["allowed_workdir_names"] if name != continuation.NAMES[0]]]:
        changed = copy.deepcopy(backend)
        changed["allowed_workdir_names"] = names
        with pytest.raises(ValueError, match="scope"):
            continuation.validate_scope(changed)


def test_future_index_cannot_skip_the_exact_prepared_round(tmp_path):
    directory = tmp_path / continuation.NAMES[0]
    directory.mkdir()
    backend = static.load_mz73_static_backend(directory.name)
    with pytest.raises(ValueError, match="index"):
        continuation.validate_request(directory, {"evaluation_index": 4}, backend)
    with pytest.raises(ValueError):
        continuation.validate_request(directory, {"evaluation_index": 3}, backend)
