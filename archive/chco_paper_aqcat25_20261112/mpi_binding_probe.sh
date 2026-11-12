#!/bin/bash
#SBATCH --partition=gpu
#SBATCH --nodelist=MZ73
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=16G
#SBATCH --time=00:02:00
#SBATCH --no-requeue
set -euo pipefail
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export TMPDIR="$PWD/tmp" XDG_CACHE_HOME="$PWD/cache/xdg" CUDA_CACHE_PATH="$PWD/cache/cuda"
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$CUDA_CACHE_PATH"
export LD_LIBRARY_PATH=/opt/nvidia/hpc_sdk/Linux_x86_64/25.7/cuda/lib64:/opt/nvidia/hpc_sdk/Linux_x86_64/25.7/compilers/extras/qd/lib:/opt/nvidia/hpc_sdk/Linux_x86_64/25.7/compilers/lib:/opt/nvidia/hpc_sdk/Linux_x86_64/25.7/math_libs/lib64:/opt/nvidia/hpc_sdk/Linux_x86_64/25.7/comm_libs/nccl/lib:/opt/nvidia/hpc_sdk/Linux_x86_64/25.7/comm_libs/nvshmem/lib"${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
/opt/nvidia/hpc_sdk/Linux_x86_64/25.7/comm_libs/12.9/hpcx/hpcx-2.22.1/ompi/bin/mpirun --bind-to none --report-bindings -np 1 /home/sbq/sbq/ml_ts_acceleration/venv/bin/python -c 'import os,json,torch; assert torch.cuda.is_available(); x=torch.tensor([1.,2.,3.],device='"'"'cuda'"'"'); value=(x*x).sum().item(); assert value==14.; print(json.dumps({'"'"'cuda'"'"':torch.cuda.is_available(),'"'"'device'"'"':torch.cuda.get_device_name(0),'"'"'value'"'"':value,'"'"'allowed_cpus'"'"':sorted(os.sched_getaffinity(0)),'"'"'visible'"'"':os.environ.get('"'"'CUDA_VISIBLE_DEVICES'"'"')}))' > probe.json 2> mpi.log
