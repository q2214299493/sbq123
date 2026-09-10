"""Regression checks against the exact corrected GPU runtime artifact."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('case', ['interpreter_link', 'escaped_parent', 'escaped_output'])
def test_interpreter_and_write_boundaries(tmp_path, case):
    root = Path(__file__).resolve().parents[1]
    artifact = root / ('calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/'
                       'h_migration_int06_to_mid_gpu_20260910/attempt_gpu1_ready_20260910/'
                       'payload_updates/runtime/aqcat25_mz73_env.sh')
    allowed = tmp_path / 'allowed'
    allowed.mkdir()
    bin_path = allowed / 'venv/bin'
    bin_path.mkdir(parents=True)
    external = tmp_path / 'system-python'
    external.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8', newline='\n')
    external.chmod(0o700)
    interpreter = bin_path / 'python'
    interpreter.symlink_to(external)
    output = allowed / 'output'
    outside = tmp_path / 'outside'
    outside.mkdir()
    if case == 'escaped_parent':
        bin_path.rename(outside / 'bin')
        bin_path.symlink_to(outside / 'bin', target_is_directory=True)
    elif case == 'escaped_output':
        output.symlink_to(outside, target_is_directory=True)

    def posix(path):
        value = path.absolute().as_posix()
        return '/' + value[0].lower() + value[2:] if os.name == 'nt' else value

    helper = allowed / 'environment.sh'
    helper.write_text(artifact.read_text(encoding='utf-8').replace('/home/sbq/sbq', posix(allowed)),
                      encoding='utf-8', newline='\n')
    env = dict(os.environ)
    env.update({name: posix(allowed / name.lower()) for name in
                ['AQCAT_ROOT', 'AQCAT_PILOT_ROOT', 'XDG_CACHE_HOME', 'TORCH_HOME', 'HF_HOME', 'TMPDIR']})
    env['AQCAT_PYTHON'] = posix(interpreter)
    bash = shutil.which('bash') or 'C:/Program Files/Git/bin/bash.exe'
    result = subprocess.run([bash, '-c', f'. "{posix(helper)}"; aqcat25_setup_mz73_environment "{posix(output)}"'],
                            env=env, capture_output=True, text=True, timeout=20)
    assert (result.returncode == 0) == (case == 'interpreter_link'), result.stderr
    if case == 'escaped_output':
        assert not list(outside.iterdir())
