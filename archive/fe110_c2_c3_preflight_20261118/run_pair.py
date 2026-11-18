"""Fixed-structure AQCat25 force inference for the two reviewed CHCO poses."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess


MODEL_SHA256 = '2aaed376a1d5ad66999710f7d252aff79c45569f2a6a95510d4bff9bbc70acc0'
SAMPLES = {
    'paper_round000': '3b417e26a30c6205bab5bb21947d9e4235e711679ae98711d8caecb711b38d59',
    'paper_round001': 'd57d1fea02710745aa23276a765210f67f306fa845a9e5f2dc6c74c13afdc6b2',
}
ACTION = 'FROZEN536_CHCO_PAIR_FIXED_FORCES'
SYMBOLS = ['Fe'] * 45 + ['C', 'C', 'O', 'H']
FIXED = list(range(18))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read_bound_json(path: Path, expected: str) -> dict:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f'Hash mismatch: {path.name}')
    return json.loads(raw)


def verify_inputs(request_path: Path, request_sha: str, checkpoint: Path) -> list[tuple[str, Path]]:
    request = read_bound_json(request_path, request_sha)
    if (request['action'] != ACTION or request['checkpoint_sha256'] != MODEL_SHA256
            or request['samples'] != SAMPLES or request['automatic_submission'] is not False):
        raise ValueError('Request must bind exactly the two reviewed coordinates and the frozen536 checkpoint')
    if digest(Path(__file__)) != request['runner_sha256']:
        raise ValueError('Runner bytes differ from the reviewed request')
    from ase.io import read
    import numpy as np

    root = request_path.resolve().parent
    inputs = []
    for sample, expected in SAMPLES.items():
        path = (root / 'structures' / f'{sample}.vasp').resolve()
        if not path.is_relative_to(root) or digest(path) != expected:
            raise ValueError(f'Coordinate binding failed: {sample}')
        atoms = read(path, format='vasp')
        fixed = sorted(int(i) for constraint in atoms.constraints for i in constraint.get_indices())
        if (atoms.get_chemical_symbols() != SYMBOLS or fixed != FIXED
                or not np.isfinite(atoms.positions).all() or not np.isfinite(atoms.cell.array).all()):
            raise ValueError(f'Invalid atom order, coordinates or constraints: {sample}')
        inputs.append((sample, path))
    if digest(checkpoint) != MODEL_SHA256:
        raise ValueError('Checkpoint bytes differ from frozen536')
    return inputs


def resolve_allocation_gpu() -> str:
    assigned = os.environ.get('SLURM_STEP_GPUS') or os.environ.get('SLURM_JOB_GPUS', '')
    if not re.fullmatch(r'(?:[0-9]+|GPU-[A-Fa-f0-9-]+)', assigned):
        raise ValueError('Exactly one native Slurm GPU is required')
    output = subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid', '--format=csv,noheader'],
                                     text=True, timeout=10)
    matches = [uuid for index, uuid in csv.reader(output.splitlines(), skipinitialspace=True)
               if assigned in (index, uuid)]
    if len(matches) != 1:
        raise ValueError('Cannot bind the allocated device to a physical GPU UUID')
    return matches[0]


def validate_run(args, authorized: dict) -> tuple[Path, str]:
    root = args.request.resolve().parent
    boundary = Path('/home/sbq/sbq').resolve()
    job_id = os.environ.get('SLURM_JOB_ID', '')
    request = read_bound_json(args.request, args.request_sha256)
    seconds = authorized.get('max_wall_seconds')
    if (os.name != 'posix' or not job_id.isascii() or not job_id.isdigit()
            or authorized.get('user_authorized') is not True
            or authorized.get('action') != ACTION or authorized.get('request_sha256') != args.request_sha256
            or authorized.get('hostname') != socket.gethostname().split('.')[0]
            or authorized.get('execution_root') != str(root)
            or root == boundary or not root.is_relative_to(boundary)
            or not args.checkpoint.resolve().is_relative_to(boundary)
            or authorized.get('checkpoint_path') != str(args.checkpoint.resolve())
            or authorized.get('native_source_sha256') != request['native_source_sha256']
            or type(seconds) is not int or seconds <= 0):
        raise ValueError('A fresh exact request authorization and native Slurm allocation on its bound host are required')
    root_out = (root / f'output_job_{job_id}').resolve()
    if root_out.parent != root or root_out.exists():
        raise ValueError('Output must be a new directory inside the bound execution root')
    return root_out, job_id


def predict_pair(args, inputs, root_out, job_id, authorized):
    uuid = resolve_allocation_gpu()
    if uuid != authorized.get('allocated_gpu_uuid'):
        raise ValueError('Allocated UUID differs from the run authorization')
    os.environ['CUDA_VISIBLE_DEVICES'] = uuid
    root_out.mkdir(exist_ok=False)
    for name in ('TMPDIR', 'XDG_CACHE_HOME', 'TORCH_HOME', 'HF_HOME', 'MPLCONFIGDIR', 'TORCH_EXTENSIONS_DIR'):
        directory = root_out / name.lower()
        directory.mkdir()
        os.environ[name] = str(directory)
    os.environ.update(HF_HUB_OFFLINE='1', WANDB_MODE='disabled')
    import numpy as np
    import torch
    from ase.io import read
    from fairchem.core.common.relaxation import ase_utils
    from fairchem.core.models.equiformer_v2 import equiformer_v2_film

    native_hashes = {Path(module.__file__).name: digest(Path(module.__file__))
                     for module in (ase_utils, equiformer_v2_film)}
    if native_hashes != authorized.get('native_source_sha256'):
        raise ValueError('Installed native AQCat25 sources differ from the authorized runtime')
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1 or torch.ones(1, device='cuda:0').item() != 1:
        raise RuntimeError('Allocated CUDA kernel check failed')
    torch.set_num_threads(4)
    torch.manual_seed(42)
    calculator = ase_utils.patched_calc(checkpoint_path=str(args.checkpoint.resolve()), is_spin_off=False,
                                       is_low_fi=False, cpu=False)
    model = calculator.trainer.model
    parameter = next(model.parameters())
    if parameter.device.type != 'cuda' or parameter.dtype != torch.float32:
        raise RuntimeError('Model must run as native FP32 on the assigned GPU')
    model.eval()
    rows = []
    for sample, path in inputs:
        if digest(path) != SAMPLES[sample]:
            raise ValueError(f'Coordinate changed before prediction: {sample}')
        atoms = read(path, format='vasp')
        positions, cell = atoms.positions.copy(), atoms.cell.array.copy()
        atoms.set_tags(np.zeros(len(atoms), dtype=int))
        atoms.info.update(is_spin_off=False, is_low_fi=False)
        atoms.calc = calculator
        forces = np.asarray(atoms.get_forces(apply_constraint=False))
        if (forces.shape != (49, 3) or not np.isfinite(forces).all()
                or not np.array_equal(positions, atoms.positions) or not np.array_equal(cell, atoms.cell.array)):
            raise RuntimeError(f'Invalid force output or modified geometry: {sample}')
        rows.append({'sample_id': sample, 'structure_sha256': SAMPLES[sample], 'predicted_forces_eV_per_A': forces.tolist()})
    if digest(args.checkpoint) != MODEL_SHA256:
        raise ValueError('Checkpoint changed during inference')
    result = {'request_sha256': args.request_sha256, 'checkpoint_sha256': MODEL_SHA256,
              'authorization_sha256': args.authorization_sha256, 'samples': rows,
              'scheduler_job_id': job_id, 'allocated_gpu_uuid': uuid, 'native_source_sha256': native_hashes,
              'model_parameter_dtype': str(parameter.dtype), 'model_parameter_device': str(parameter.device),
              'training_or_optimization': False}
    payload = json.dumps(result, indent=2, allow_nan=False) + '\n'
    temporary = root_out / 'predictions.tmp'
    with temporary.open('x', encoding='utf8') as stream:
        stream.write(payload)
    temporary.rename(root_out / 'predictions2.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('verify', 'run'))
    parser.add_argument('--request', required=True, type=Path)
    parser.add_argument('--request-sha256', required=True)
    parser.add_argument('--checkpoint', required=True, type=Path)
    parser.add_argument('--authorization', type=Path)
    parser.add_argument('--authorization-sha256')
    args = parser.parse_args()
    if args.mode == 'run' and (args.authorization is None or args.authorization_sha256 is None):
        parser.error('run requires a fresh host-bound authorization and its SHA256')
    inputs = verify_inputs(args.request, args.request_sha256, args.checkpoint)
    if args.mode == 'verify':
        print(json.dumps({'status': 'PASS_LOCAL_INPUTS_ONLY', 'samples': [sample for sample, _ in inputs]}))
        return
    authorization = read_bound_json(args.authorization, args.authorization_sha256)
    root_out, job_id = validate_run(args, authorization)
    def timeout(*_):
        raise TimeoutError('Authorized inference time limit reached')

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(authorization['max_wall_seconds'])
    try:
        predict_pair(args, inputs, root_out, job_id, authorization)
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    main()
