"""Frozen existing device/environment/force-metric helpers for one validation.

Not an independent scientific acceptance or submission authority.
"""
from __future__ import annotations

import os
import subprocess

import numpy as np


# Source scripts/adsorption/direct_gpu_batch.py SHA256 0a8fb8fc50659de437057b3f0e535f4e89a1295fd0c3ffc1ca71c3a4ea676ee7


def gpu_available(request):
    output = subprocess.check_output([
        'nvidia-smi', '--query-gpu=index,uuid,memory.free', '--format=csv,noheader,nounits'
    ], timeout=10).decode()
    matches = [line.split(',') for line in output.splitlines()
               if line.split(',')[1].strip() == request['gpu_uuid']]
    if len(matches) != 1 or int(matches[0][0]) != request['gpu_index']:
        raise ValueError('GPU identity changed')
    if int(matches[0][2]) < 20000:
        raise ValueError('insufficient free GPU memory; no model started')
    processes = subprocess.check_output([
        'nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader'
    ], timeout=10).decode()
    if any(line.split(',')[0].strip() == request['gpu_uuid'] for line in processes.splitlines()):
        raise ValueError('authorized GPU has an existing compute process; no process stopped')


def environment(root, request):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith('SLURM_'):
            env.pop(key)
    env.update(AQCAT_PILOT_ROOT=str(root / 'runtime'), AQCAT_ROOT='/home/sbq/sbq/aqcat25',
               AQCAT_PYTHON='/home/sbq/sbq/ml_ts_acceleration/venv/bin/python',
               DOMAIN_CALIBRATION='/home/sbq/sbq/aqcat25_ts_pilot/aqcat25_domain_calibration.json',
               TMPDIR=str(root / 'tmp'), XDG_CACHE_HOME=str(root / 'cache/xdg'),
               TORCH_HOME=str(root / 'cache/torch'), HF_HOME=str(root / 'cache/huggingface'),
               CUDA_VISIBLE_DEVICES=request['gpu_uuid'], OMP_NUM_THREADS='4',
               MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4', PYTHONUNBUFFERED='1')
    env['PYTHONPATH'] = ':'.join([str(root), str(root / 'runtime'), '/home/sbq/sbq/aqcat25/python_pkgs',
                                '/home/sbq/sbq/aqcat25/vendor'])
    if request.get('model_backend') == 'matris':
        env['MATRIS_CHECKPOINT'] = request['checkpoint_path']
        env['PYTHONPATH'] += ':/home/sbq/sbq/mlip_same_structure_benchmark_20260825/vendor/MatRIS'
    return env


def cuda_binding(calculator):
    """Check actual model tensors, not CUDA availability or a GPU request label."""
    model = getattr(calculator, 'model', None)
    if model is None:
        model = calculator.trainer.model
    device = next(model.parameters()).device
    if device.type != 'cuda':
        raise RuntimeError(f'GPU request has model parameters on {device}; refuse optimization')
    visible = os.environ.get('CUDA_VISIBLE_DEVICES', '')
    if not visible.startswith('GPU-') or ',' in visible:
        raise RuntimeError('direct model must bind one physical GPU UUID')
    return {'model_device': str(device), 'physical_gpu_uuid': visible,
            'pid': os.getpid(), 'execution_mode': 'direct_no_scheduler',
            'scheduler_job_id': None}


# Source calculations/fe110_five_c2_adsorption_20261006/adsorption_finetune_review_v6/runtime/force_finetune.py SHA256 e93693044bb8a3dd99d52cb1648f3676dbb121c8b5027c2b1341124124f6b5f4


def force_metrics(reference: np.ndarray, predicted: np.ndarray, symbols: list[str], fixed: list[int]) -> dict:
    reference, predicted = np.asarray(reference), np.asarray(predicted)
    if reference.shape != predicted.shape or reference.shape != (len(symbols), 3):
        raise ValueError("prediction shape mismatch")
    if not np.isfinite(reference).all() or not np.isfinite(predicted).all():
        raise ValueError("nonfinite force prediction")
    free = [i for i in range(len(symbols)) if i not in fixed]
    groups = {"movable": free, "adsorbate": [i for i in free if symbols[i] != "Fe"]}
    groups.update({s: [i for i in free if symbols[i] == s] for s in ("Fe", "C", "O", "H")})
    result = {}
    for name, indices in groups.items():
        if not indices:
            result[name] = {"atom_count": 0, "vector_rmse_eV_A": None}
            continue
        delta = predicted[indices] - reference[indices]
        norm = np.linalg.norm(delta, axis=1)
        rnorm, pnorm = np.linalg.norm(reference[indices], axis=1), np.linalg.norm(predicted[indices], axis=1)
        directional = (rnorm > 1e-8) & (pnorm > 1e-8)
        cos = np.sum(reference[indices] * predicted[indices], axis=1)[directional] / (rnorm*pnorm)[directional]
        result[name] = {"atom_count": len(indices), "component_mae_eV_A": float(np.abs(delta).mean()),
                        "vector_rmse_eV_A": float(np.sqrt(np.mean(norm**2))),
                        "vector_max_eV_A": float(norm.max()),
                        "mean_cosine_nonzero_forces": float(cos.mean()) if len(cos) else None}
    return result
