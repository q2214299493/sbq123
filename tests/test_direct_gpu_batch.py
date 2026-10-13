import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.adsorption.direct_gpu_batch import (
    checked_request, cuda_binding, environment, gpu_available, require_cuda_keyword,
)


def test_changed_request_is_rejected(tmp_path):
    request = tmp_path / 'request.json'
    request.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='request changed'):
        checked_request(request, '0' * 64)


def test_direct_environment_never_invents_slurm_id(monkeypatch):
    monkeypatch.setenv('SLURM_JOB_ID', 'old')
    monkeypatch.setenv('SLURM_JOB_NODELIST', 'old')
    env = environment(Path('/home/sbq/sbq/test'), {'gpu_uuid': 'GPU-real'})
    assert not any(k.startswith('SLURM_') for k in env)
    assert env['CUDA_VISIBLE_DEVICES'] == 'GPU-real'
    assert env['OMP_NUM_THREADS'] == '4'


@pytest.mark.parametrize('free,processes,error', [
    (24000, '', None), (1000, '', 'insufficient'),
    (24000, 'GPU-real, 123', 'compute process'),
])
def test_gpu_checks_do_not_stop_existing_processes(monkeypatch, free, processes, error):
    calls = []

    def command(args, **_kwargs):
        calls.append(args)
        if '--query-gpu=index,uuid,memory.free' in args:
            return f'1, GPU-real, {free}\n'.encode()
        return processes.encode()

    monkeypatch.setattr(subprocess, 'check_output', command)
    request = {'gpu_uuid': 'GPU-real', 'gpu_index': 1}
    if error:
        with pytest.raises(ValueError, match=error):
            gpu_available(request)
    else:
        gpu_available(request)
    assert all(cmd[0] == 'nvidia-smi' for cmd in calls)


@pytest.mark.parametrize('kind', ['cpu', 'cuda'])
def test_cuda_binding_checks_actual_parameter_device(monkeypatch, kind):
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES', 'GPU-real')
    device = SimpleNamespace(type=kind)
    model = SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device=device)]))
    calculator = SimpleNamespace(trainer=SimpleNamespace(model=model))
    if kind == 'cpu':
        with pytest.raises(RuntimeError, match='model parameters'):
            cuda_binding(calculator)
    else:
        assert cuda_binding(calculator)['physical_gpu_uuid'] == 'GPU-real'


@pytest.mark.parametrize('call', ['patched_calc()', 'patched_calc(cpu=True)'])
def test_cpu_default_cannot_pass_gpu_preflight(tmp_path, call):
    source = tmp_path / 'runner.py'
    source.write_text(call, encoding='utf-8')
    with pytest.raises(ValueError, match='cpu=False'):
        require_cuda_keyword(source)


def test_explicit_cuda_keyword_passes(tmp_path):
    source = tmp_path / 'runner.py'
    source.write_text('patched_calc(cpu=False)', encoding='utf-8')
    require_cuda_keyword(source)
