"""Bounded dependency/checkpoint check; --cuda requires a Slurm GPU allocation."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cuda', action='store_true')
    parser.add_argument('--checkpoint', type=Path, default=Path('/home/sbq/sbq/compute_pool_20261117/deployed/models/aqcat25_ft512_development.pt'))
    args = parser.parse_args()
    names = ['torch', 'torch_scatter', 'torch_sparse', 'torch_geometric', 'numpy', 'scipy', 'ase', 'sella', 'arkimede', 'mlps_finetuning', 'fairchem.core.common.flags', 'fairchem.core.common.utils']
    modules = {name: getattr(importlib.import_module(name), '__file__', None) for name in names}
    import torch
    assert hashlib.sha256(args.checkpoint.read_bytes()).hexdigest() == 'cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0'
    data = torch.load(args.checkpoint, map_location='cpu', weights_only=False)
    state = data['state_dict']
    assert all(bool(torch.isfinite(v).all()) for v in state.values() if torch.is_tensor(v))
    module_hashes = {name: hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None for name, path in modules.items()}
    result = {'python': sys.version, 'torch': torch.__version__, 'torch_cuda_build': torch.version.cuda, 'modules': modules, 'module_file_sha256': module_hashes, 'checkpoint_finite': True, 'state_tensor_count': len(state), 'cuda_in_allocation_validated': False, 'scientific_job_run': False, 'model_promoted': False}
    if args.cuda:
        assert os.environ.get('SLURM_JOB_ID'), 'GPU check requires Slurm allocation'
        assert torch.cuda.is_available() and torch.cuda.device_count() == 1
        nvml = subprocess.run(['nvidia-smi', '--query-gpu=uuid,name', '--format=csv,noheader'], capture_output=True, text=True, check=True)
        from torch_scatter import scatter
        from torch_sparse import SparseTensor
        values = torch.tensor([1., 2.], device='cuda')
        assert scatter(values, torch.zeros(2, dtype=torch.long, device='cuda')).item() == 3.
        edge = torch.tensor([[0, 1], [1, 0]], device='cuda')
        matrix = SparseTensor.from_edge_index(edge, torch.ones(2, device='cuda'), sparse_sizes=(2, 2))
        assert bool(torch.allclose(matrix.matmul(torch.ones((2, 1), device='cuda')), torch.ones((2, 1), device='cuda')))
        dense = torch.arange(4096, device='cuda', dtype=torch.float32).reshape(64, 64)
        assert bool(torch.allclose(dense @ torch.eye(64, device='cuda'), dense))
        torch.cuda.synchronize()
        result.update(cuda_in_allocation_validated=True, assigned_job_id=os.environ['SLURM_JOB_ID'], cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'), slurm_job_gpus=os.environ.get('SLURM_JOB_GPUS'), nvml_gpu_uuids=nvml.stdout.strip(), gpu_name=torch.cuda.get_device_name(0))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
