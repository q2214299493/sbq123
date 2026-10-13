"""One explicitly authorized MZ73 batch; no scheduler IDs or scientific acceptance."""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

try:
    from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
except ModuleNotFoundError:
    from artifact_io import load_json_object, sha256_file, write_json_exclusive


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def checked_request(path, digest):
    if sha256_file(path) != digest:
        raise ValueError('direct request changed')
    request = load_json_object(path)
    if not re.fullmatch(r'direct-[a-z0-9-]+', request['run_id']):
        raise ValueError('direct ID must not emulate a scheduler job ID')
    canonical_root = path.parent.resolve()
    policy_path = canonical_root / request['policy']['path']
    if sha256_file(policy_path) != request['policy']['sha256']:
        raise ValueError('backend authority changed')
    policy = yaml.safe_load(policy_path.read_text(encoding='utf-8'))
    exception = policy['backends']['aqcat_gpu']['direct_execution_exceptions'][request['exception_id']]
    root = Path(exception['remote_root'])
    if canonical_root != root.resolve() or socket.gethostname() != 'MZ73':
        raise ValueError('direct execution outside authorized host/root')
    boundary = Path('/home/sbq/sbq').resolve()
    if str(boundary) != exception['canonical_remote_boundary'] or not canonical_root.is_relative_to(boundary):
        raise ValueError('direct root escaped remote write boundary')
    if request['gpu_uuid'] != exception['gpu_uuid'] or request['gpu_index'] != exception['gpu_index']:
        raise ValueError('unauthorized GPU')
    if request['max_wall_seconds'] != exception['max_wall_seconds']:
        raise ValueError('unauthorized walltime')
    if request['execution_mode'] != 'direct_no_scheduler' or request['scheduler_job_id'] is not None:
        raise ValueError('direct execution has no scheduler job ID')
    if request['authorization']['user_request'] != '你试试':
        raise ValueError('missing task-specific user authorization')
    manifest = root / 'batch_manifest.json'
    if sha256_file(manifest) != request['batch_manifest_sha256']:
        raise ValueError('candidate batch changed')
    batch = load_json_object(manifest)
    if len(batch['handoffs']) != exception['candidate_count']:
        raise ValueError('unauthorized candidate count')
    if len({r['name'] for r in batch['handoffs']}) != len(batch['handoffs']):
        raise ValueError('duplicate candidate names')
    for item in batch['files']:
        target = (root / item['path']).resolve()
        if not target.is_relative_to(canonical_root) or sha256_file(target) != item['sha256']:
            raise ValueError('stale or escaping input file')
    require_cuda_keyword(root / 'runtime/relax_endpoint_candidates.py')
    return request, root, batch


def require_cuda_keyword(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == 'patched_calc']
    if len(calls) != 1 or not any(k.arg == 'cpu' and isinstance(k.value, ast.Constant)
                                  and k.value.value is False for k in calls[0].keywords):
        raise ValueError('GPU calculator must explicitly set cpu=False')


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
    return env


def cuda_binding(calculator):
    """Check actual model tensors, not CUDA availability or a GPU request label."""
    device = next(calculator.trainer.model.parameters()).device
    if device.type != 'cuda':
        raise RuntimeError(f'GPU request has model parameters on {device}; refuse optimization')
    visible = os.environ.get('CUDA_VISIBLE_DEVICES', '')
    if not visible.startswith('GPU-') or ',' in visible:
        raise RuntimeError('direct model must bind one physical GPU UUID')
    return {'model_device': str(device), 'physical_gpu_uuid': visible,
            'pid': os.getpid(), 'execution_mode': 'direct_no_scheduler',
            'scheduler_job_id': None}


def preflight(request, root):
    gpu_available(request)
    env = environment(root, request)
    subprocess.run(['bash', '-n', str(root / 'runtime/aqcat25_gpu_job.sh')], check=True, timeout=10)
    subprocess.run([env['AQCAT_PYTHON'], str(root / 'preflight.py'), '--remote'],
                   env=env, cwd=root, check=True, timeout=45)


def launch(path, digest):
    request, root, _ = checked_request(path, digest)
    if (root / 'direct_launch_marker.json').exists():
        raise FileExistsError('existing launch marker; inspect receipt/PID instead of relaunching')
    preflight(request, root)
    write_json_exclusive(root / 'direct_launch_marker.json', {
        'run_id': request['run_id'], 'request_sha256': digest, 'created_at': timestamp(),
        'execution_mode': 'direct_no_scheduler', 'scheduler_job_id': None})
    env = environment(root, request)
    with (root / 'direct_batch.log').open('xb') as log:
        child = subprocess.Popen([env['AQCAT_PYTHON'], str(root / 'direct_gpu_batch.py'),
                                  'run', str(path), '--request-sha256', digest],
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 cwd=root, env=env, start_new_session=True)
    receipt = {'run_id': request['run_id'], 'pid': child.pid,
               'request_sha256': digest, 'launched_at': timestamp(),
               'execution_mode': 'direct_no_scheduler', 'scheduler_job_id': None,
               'gpu_index': request['gpu_index'], 'gpu_uuid': request['gpu_uuid']}
    write_json_exclusive(root / 'direct_launch_receipt.json', receipt)
    return receipt


def run(path, digest):
    import fcntl

    request, root, batch = checked_request(path, digest)
    marker = load_json_object(root / 'direct_launch_marker.json')
    if marker['request_sha256'] != digest or marker['run_id'] != request['run_id']:
        raise ValueError('launch marker mismatch')
    started = timestamp()
    code, reason, completed, child = 1, 'startup', [], None

    def interrupted(signum, _frame):
        raise InterruptedError(f'direct batch received signal {signum}')

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, interrupted)
    locks = Path('/home/sbq/sbq/aqcat25_ts_pilot/direct_gpu_locks')
    locks.mkdir(exist_ok=True)
    try:
        with (locks / (request['gpu_uuid'] + '.lock')).open('a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            preflight(request, root)
            write_json_exclusive(root / 'direct_started.json', {
                'run_id': request['run_id'], 'pid': os.getpid(), 'started_at': started,
                'execution_mode': 'direct_no_scheduler', 'scheduler_job_id': None})
            deadline = time.monotonic() + request['max_wall_seconds']
            for item in batch['handoffs']:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('authorized batch walltime exhausted')
                gpu_available(request)
                env = environment(root, request)
                env.update(AQCAT_RUN_ID=request['run_id'], HANDOFF_ROOT=str(root / item['name']),
                           SOURCE_HANDOFF_SHA256=item['handoff_sha256'])
                print(json.dumps({'candidate_started': item['name'], 'run_id': request['run_id']}), flush=True)
                with (root / item['name'] / 'direct_model.log').open('xb') as log:
                    child = subprocess.Popen(['bash', str(root / 'runtime/aqcat25_gpu_job.sh')],
                                             env=env, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                             start_new_session=True)
                    exit_code = child.wait(timeout=remaining)
                    child = None
                write_json_exclusive(root / item['name'] / 'direct_candidate_receipt.json', {
                    'candidate': item['name'], 'run_id': request['run_id'], 'exit_code': exit_code,
                    'finished_at': timestamp(), 'execution_mode': 'direct_no_scheduler',
                    'scheduler_job_id': None})
                if exit_code:
                    raise RuntimeError(f"candidate {item['name']} producer failed with exit {exit_code}")
                binding = load_json_object(root / item['name'] / 'output' /
                                           ('job_' + request['run_id']) / 'execution_device.json')
                if not binding['model_device'].startswith('cuda') or binding['physical_gpu_uuid'] != request['gpu_uuid']:
                    raise RuntimeError('candidate did not prove execution on the authorized CUDA device')
                completed.append(item['name'])
                print(json.dumps({'candidate_completed': item['name'], 'count': len(completed)}), flush=True)
            code, reason = 0, 'all candidate producers returned zero; scientific review pending'
    except Exception as exc:
        reason = str(exc)
        print(json.dumps({'batch_error': reason}), flush=True)
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
    finally:
        write_json_exclusive(root / 'direct_batch_exit_record.json', {
            'run_id': request['run_id'], 'pid': os.getpid(), 'started_at': started,
            'finished_at': timestamp(), 'exit_code': code, 'reason': reason,
            'completed_candidates': completed, 'execution_mode': 'direct_no_scheduler',
            'scheduler_job_id': None, 'evidence_class': 'producer_process_only_not_scheduler_accounting',
            'scientific_acceptance': False})
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'launch', 'run'))
    parser.add_argument('request', type=Path)
    parser.add_argument('--request-sha256', required=True)
    args = parser.parse_args()
    if args.action == 'launch':
        print(json.dumps(launch(args.request, args.request_sha256)), flush=True)
    elif args.action == 'preflight':
        request, root, _ = checked_request(args.request, args.request_sha256)
        preflight(request, root)
        print(json.dumps({'status': 'PASS_NO_MODEL_RUN', 'run_id': request['run_id']}))
    else:
        sys.exit(run(args.request, args.request_sha256))


if __name__ == '__main__':
    main()
