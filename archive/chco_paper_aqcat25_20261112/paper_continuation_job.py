"""One bounded, user-requested BA-Sella continuation; no training or VASP.

Prepare requires the owner-registered 100-epoch checkpoint. The initial IDPP
request and all returned JSON bytes stay unchanged. No automatic retry.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shlex
import sys
from uuid import uuid4

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.neb_agent.paper_candidate_source import _previous_geometry
from scripts.neb_agent.mz73_continuation import authorization as continuation_authorization
from scripts.slurm_force_label import parse_scontrol_job
from scripts.ts_strategy_engine.paper_stopping import effective_force_target
from scripts.ts_strategy_engine.paper_sequential import validate_state

spec = importlib.util.spec_from_file_location('paper_continuation_primary', Path(__file__).with_name('paper_training_job.py'))
primary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(primary)
require, bound, ref = primary.require, primary.bound, primary.ref
LEAF = 'continuation_r001'
NEXT = '18cc5c17d957eb75d2c38188084932e84ae7a2a37f36b47a10ffa27fa4f91b83'
RESOURCES = {**primary.RESOURCES, 'memory': '15G'}


def leaf_for(state):
    return f"continuation_r{state['completed_label_count']:03d}"


def binding_path(case, state):
    if state['completed_label_count'] == 1:
        return case / 'training14292_candidate_checkpoint_binding.json'
    return case / f"training_r{state['completed_label_count'] - 1:03d}_force003_checkpoint_binding.json"


def resources_for(state):
    return {**RESOURCES, 'memory': '7G'} if state['completed_label_count'] > 1 else RESOURCES


def backend(case):
    result = primary.remote.load_mz73_static_backend(primary.budget_owner.TIMEOUT_LEAF)
    configured = yaml.safe_load(Path(primary.remote.DEFAULT_CONFIG).read_text(encoding='utf-8'))['backends']['aqcat_gpu']
    require('ba_sella_candidate_search' in configured['allowed'] and configured['observed_hostname'] == 'MZ73', 'BA-Sella GPU role unavailable')
    require((case.name, PurePosixPath(result['remote_root']).parent.name) ==
            ('paper_aqcat25_ft512_20261112_v1', 'chco_paper_aqcat25_ft512_20261112_v1'),
            'continuation belongs to another case')
    return result


def context(case, state_path, state_sha256):
    state = load_json_object(bound({'path': str(state_path.resolve(strict=True)), 'sha256': state_sha256}))
    validate_state(state)
    require(state['status'] == 'awaiting_candidate' and state['completed_label_count'] >= 1
            and state['reserved_dft_slots'] < state['protocol']['maximum_dft_evaluations'], 'not the sole next candidate phase')
    current = case / ('paper_state.v2.json' if state['completed_label_count'] == 1 else 'paper_state.v3.json')
    require(sha256_file(current) == state_sha256, 'current scientific state differs from the reviewed snapshot')
    binding = load_json_object(binding_path(case, state))
    require(binding['eligible_for_next_BA_Sella_prediction_only'] is True and binding['model_promotion'] is False
            and binding['checkpoint'] == state['search_checkpoint'], 'checkpoint has not been separately verified')
    for name in ('training_result', 'native_exit', 'checkpoint_inspection', 'input_state', 'output_state'):
        bound(binding[name])
    result = load_json_object(bound(binding['training_result']))
    require(result['checkpoint'] == state['search_checkpoint'] and result['training_evidence']['observed_optimizer_updates'] == 100,
            'training checkpoint/result mismatch')
    if state['completed_label_count'] > 1:
        approval, _ = continuation_authorization(ref(case / 'continuation_force003_20261113/authorization.json'))
        require(effective_force_target(state) == 0.03 and binding['authorization'] == ref(case / 'continuation_force003_20261113/authorization.json'), 'missing approved strict0.03 continuation')
        inspection = load_json_object(bound(binding['checkpoint_inspection']))
        require(inspection['status'] == 'passed_candidate_only' and inspection['checkpoint'] == state['search_checkpoint']
                and inspection['checkpoint_epoch'] == inspection['checkpoint_step'] == 100
                and inspection['model_state_finite'] is True and inspection['raw_forces_and_geometry_match'] is True,
                'checkpoint has not passed actual CPU inspection')
        native = load_json_object(bound(binding['native_exit']))
        record = load_json_object(bound(binding['training_submission']))
        require(native['native_scontrol']['returncode'] == 0, 'missing native training query')
        parsed = parse_scontrol_job(native['native_scontrol']['stdout'], record['job_id'])
        require(parsed['job_state'] == 'COMPLETED' and parsed['exit_code'] == '0:0'
                and parsed['remote_dir'] == record['remote_dir'] and parsed['command'] == record['remote_dir'] + '/job.sh',
                'training native completion/identity mismatch')
        memory = load_json_object(bound(binding['host_memory_preflight']))
        require(0 < memory['peak_RSS_bytes'] < 2 * 2**30 and memory['training_performed'] is False
                and approval['resources']['search']['memory'] == '15G', 'missing CPU headroom review for the smaller search request')
    original_path = case / 'initial_search/request.json'
    original = load_json_object(original_path)
    if state['completed_label_count'] == 1:
        previous = case / 'return_13883/output/predicted_candidate.vasp'
    else:
        label_directory = Path(state['latest_label']['label']['structure']['path']).parent
        provenance = load_json_object(label_directory / 'parameter_reuse_provenance.json')
        previous = bound(provenance['new_candidate'])
    trajectory = previous.parent / 'aqcat25_ba_sella.traj'
    require(sha256_file(previous) == state['latest_label']['label']['structure']['sha256'], 'previous candidate is not the accepted training label')
    _previous_geometry(previous, trajectory, case / 'initial_search/IS.vasp', original)
    return state, binding, original, previous, trajectory


def launcher(target, request_sha256, resolved):
    q = shlex.quote
    checks = '\n'.join(check for suffix in ('', '/tmp', '/cache', '/output')
                       for check in primary.remote.remote_path_checks(resolved, target + suffix))
    return f'''#!/bin/bash
set -euo pipefail
record_exit() {{
  code=$?
  trap - EXIT
  set -C
  printf '{{"document_kind":"paper_continuation_producer_exit","job_id":"%s","exit_code":%d,"request_sha256":"{request_sha256}","evidence_class":"process_only_not_scheduler_authority","DFT_performed":false,"training_performed":false}}\\n' "${{SLURM_JOB_ID:-unknown}}" "$code" > {q(target + '/producer_exit_record.json')}
  exit "$code"
}}
trap record_exit EXIT
test "$(hostname -s)" = MZ73
test -n "${{SLURM_JOB_ID:-}}"
test "${{SLURM_NTASKS:-0}}" = 1
case "${{CUDA_VISIBLE_DEVICES:-}}" in ''|*,*) exit 2 ;; esac
{checks}
test "$(pwd -P)" = "$(realpath -e {q(target)})"
test ! -e {q(target + '/output')}
export PYTHONDONTWRITEBYTECODE=1 CUDA_CACHE_DISABLE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4
export PYTHONPATH={q(target + ':' + primary.PYTHONPATH)}
export TMPDIR={q(target + '/tmp')} XDG_CACHE_HOME={q(target + '/cache')} TORCH_HOME={q(target + '/cache/torch')}
export HF_HOME={q(target + '/cache/huggingface')} MPLCONFIGDIR={q(target + '/cache/matplotlib')}
export TORCH_EXTENSIONS_DIR={q(target + '/cache/extensions')} TRITON_CACHE_DIR={q(target + '/cache/triton')} NUMBA_CACHE_DIR={q(target + '/cache/numba')}
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 WANDB_MODE=disabled
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME"
{q(primary.PYTHON)} -B {q(target + '/next_candidate.py')} --request {q(target + '/request.json')} --request-sha256 {request_sha256} --output {q(target + '/output')}
'''.encode('ascii')


def prepare(args):
    case = args.case_root.resolve(strict=True)
    state, binding, original, previous, trajectory = context(case, args.state, args.state_sha256)
    resolved = backend(case)
    leaf = leaf_for(state)
    target = str(PurePosixPath(resolved['remote_root']).parent / leaf)
    worker = Path(__file__).with_name('next_candidate.py')
    require(sha256_file(worker) == NEXT, 'continuation algorithm source changed')
    execution_source = ref(args.execution_source)
    require(0 < args.execution_source.stat().st_size < 10000, 'missing actual continuation instruction')
    if state['completed_label_count'] > 1:
        approval, _ = continuation_authorization(ref(case / 'continuation_force003_20261113/authorization.json'))
        require(execution_source == approval['source'], 'continuation must bind the actual new user instruction')
    directory = case / leaf
    directory.mkdir(exist_ok=False)
    copied = {'next_candidate.py': worker, 'original_request.json': case / 'initial_search/request.json',
        'training_request.json': (case / 'training_r000_metadata_recovery01/request.json'
                                  if state['completed_label_count'] == 1 else bound(binding['training_request'])),
        'training_result.json': bound(binding['training_result']), 'previous_candidate.vasp': previous,
        'previous_trajectory.traj': trajectory}
    old_sources = {PurePosixPath(row['path']).name: row for row in original['source_files']}
    for name in ('initial_candidate.py', 'aqcat_ts_pilot.py', 'mlip_same_structure_benchmark.py', 'artifact_io.py'):
        source = case / 'initial_search' / name
        require(sha256_file(source) == old_sources[name]['sha256'], 'frozen initial helper changed')
        copied[name] = source
    for name, source in copied.items():
        (directory / name).write_bytes(source.read_bytes())
    author = case / 'author_runtime_sources/calculations.py'
    require(sha256_file(author) == old_sources['calculations.py']['sha256'], 'author implementation mismatch')
    source_files = [{'path': target + '/' + name, 'sha256': sha256_file(directory / name)}
                    for name in ('next_candidate.py', 'initial_candidate.py', 'aqcat_ts_pilot.py', 'mlip_same_structure_benchmark.py', 'artifact_io.py')]
    source_files.append(old_sources['calculations.py'])
    request = {'document_kind': 'paper_sequential_candidate_continuation_request', 'protocol_sha256': state['protocol_sha256'],
               'source_files': source_files, 'checkpoint': state['search_checkpoint'],
               **{key: {'path': target + '/' + name, 'sha256': sha256_file(directory / name)} for key, name in {
                   'initial_request': 'original_request.json', 'training_request': 'training_request.json',
                   'training_result': 'training_result.json', 'previous_candidate': 'previous_candidate.vasp',
                   'previous_trajectory': 'previous_trajectory.traj'}.items()}}
    write_json_exclusive(directory / 'request.json', request)
    (directory / 'job.sh').write_bytes(launcher(target, sha256_file(directory / 'request.json'), resolved))
    mapping = [{'source_path': target + '/' + name, **ref(directory / name)} for name in copied]
    mapping += [{'source_path': old_sources['calculations.py']['path'], **ref(author)},
                {'source_path': original['initial']['path'], **ref(case / 'initial_search/IS.vasp')},
                {'source_path': original['geometry_guard_source']['path'], **ref(original['geometry_guard_source']['path'])}]
    write_json_exclusive(directory / 'source_map_seed.json', {'source_map': mapping})
    manifest = {'document_kind': 'paper_one_BA_Sella_continuation_job', 'state': ref(args.state),
                'checkpoint_binding': ref(binding_path(case, state)),
                'backend_config': ref(primary.remote.DEFAULT_CONFIG), 'implementation': ref(__file__),
                'execution_source': execution_source, 'resources': resources_for(state), 'backend_role': 'aqcat_gpu',
                'remote_dir': target, 'checkpoint': state['search_checkpoint'], 'author_source': ref(author),
                'automatic_retries': 0, 'DFT_submission_allowed': False,
                'files': {p.name: sha256_file(p) for p in directory.iterdir() if p.is_file()}}
    path = directory / 'manifest.json'
    write_json_exclusive(path, manifest)
    return ref(path)


def verify(path, digest):
    manifest = load_json_object(bound({'path': str(path.resolve(strict=True)), 'sha256': digest}))
    case = path.parent.parent
    state, _, original, _, _ = context(case, bound(manifest['state']), manifest['state']['sha256'])
    resolved = backend(case)
    require(manifest['document_kind'] == 'paper_one_BA_Sella_continuation_job' and manifest['implementation'] == ref(__file__)
        and manifest['backend_config'] == ref(primary.remote.DEFAULT_CONFIG) and manifest['resources'] == resources_for(state)
        and manifest['automatic_retries'] == 0 and manifest['DFT_submission_allowed'] is False
        and manifest['checkpoint'] == state['search_checkpoint'], 'continuation scope/source changed')
    require(manifest['checkpoint_binding'] == ref(binding_path(case, state)), 'continuation checkpoint binding changed')
    for key in ('checkpoint_binding', 'execution_source', 'author_source'):
        bound(manifest[key])
    if state['completed_label_count'] > 1:
        approval, _ = continuation_authorization(ref(case / 'continuation_force003_20261113/authorization.json'))
        require(manifest['execution_source'] == approval['source'], 'continuation execution source changed')
    leaf = leaf_for(state)
    target = str(PurePosixPath(resolved['remote_root']).parent / leaf)
    require(path.parent == case / leaf and manifest['remote_dir'] == target, 'continuation path changed')
    require(set(p.name for p in path.parent.iterdir()) == set(manifest['files']) | {'manifest.json'}, 'unbound continuation payload')
    require(all(sha256_file(path.parent / name) == value for name, value in manifest['files'].items()), 'continuation staged bytes changed')
    require((path.parent / 'job.sh').read_bytes() == launcher(target, manifest['files']['request.json'], resolved), 'launcher changed')
    request = load_json_object(path.parent / 'request.json')
    require(request['protocol_sha256'] == state['protocol_sha256'] and request['checkpoint'] == state['search_checkpoint']
        and request['initial_request']['sha256'] == sha256_file(case / 'initial_search/request.json')
        and manifest['files']['next_candidate.py'] == NEXT, 'continuation request identity changed')
    require(original['checkpoint']['sha256'] != request['checkpoint']['sha256'], 'continuation did not use the new checkpoint')
    return manifest, resolved


def submit(path, digest):
    manifest, resolved = verify(path, digest)
    case, target = path.parent.parent, manifest['remote_dir']
    leaf = path.parent.name
    attempt, receipt = case / (leaf + '_submission_attempt.json'), case / (leaf + '_submission_record.json')
    require(not receipt.exists(), 'continuation already has a submission receipt')
    reservation = uuid4().hex
    write_json_exclusive(attempt, {'status': 'UNKNOWN', 'manifest': ref(path), 'reservation_id': reservation, 'automatic_retry': False})
    try:
        lock = str(PurePosixPath(target).parent / (leaf + '_submission.reservation'))
        checks = [*primary.remote.remote_path_checks(resolved, target), *primary.remote.remote_path_checks(resolved, lock),
                  'mkdir ' + shlex.quote(lock), 'test ! -e ' + shlex.quote(target)]
        primary.run(primary.remote.ssh_argv(resolved, 'set -eu; ' + ' && '.join(checks)))
        primary.run(primary.remote.scp_argv(resolved, str(path.parent), str(PurePosixPath(target).parent)))
        verify(path, digest)
        checks = []
        for name, value in {**manifest['files'], 'manifest.json': digest}.items():
            p = target + '/' + name
            checks += primary.remote.remote_path_checks(resolved, p)
            checks.append(f'test "$(sha256sum {shlex.quote(p)} | cut -d\' \' -f1)" = {value}')
        request = load_json_object(path.parent / 'request.json')
        for descriptor in [request['checkpoint'], request['source_files'][-1]]:
            checks += primary.remote.remote_path_checks(resolved, descriptor['path'])
            checks.append(f'test "$(sha256sum {shlex.quote(descriptor["path"])} | cut -d\' \' -f1)" = {descriptor["sha256"]}')
        checks += ['test ! -e ' + shlex.quote(target + '/output'), 'bash -n ' + shlex.quote(target + '/job.sh')]
        argv = ['sbatch', '--parsable', '--no-requeue', '--partition=gpu', '--nodelist=MZ73', '--nodes=1', '--ntasks=1',
                '--cpus-per-task=4', '--gres=gpu:1', '--mem=' + manifest['resources']['memory'], '--time=00:10:00', '--job-name=chco-paper-' + leaf,
                '--chdir=' + target, '--output=' + target + '/slurm-%j.out', '--error=' + target + '/slurm-%j.err', target + '/job.sh']
        result = primary.run(primary.remote.ssh_argv(resolved, 'set -eu; ' + ' && '.join([*checks, shlex.join(argv)])))
        record = {'status': 'SUBMITTED', 'job_id': primary.remote.parse_sbatch_job_id(result.stdout), 'scheduler': 'Slurm',
                  'remote_dir': target, 'manifest': ref(path), 'DFT_submitted': False, 'training_performed': False,
                  'submit_stdout': result.stdout, 'submit_stderr': result.stderr}
        write_json_exclusive(receipt, record)
        return record
    except BaseException:
        if not receipt.exists():
            write_json_exclusive(receipt, {'status': 'UNKNOWN', 'reservation_id': reservation, 'automatic_retry': False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    for name in ('case-root', 'state', 'execution-source'):
        prep.add_argument('--' + name, type=Path, required=True)
    prep.add_argument('--state-sha256', required=True)
    execute = commands.add_parser('submit')
    execute.add_argument('--manifest', type=Path, required=True)
    execute.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args) if args.command == 'prepare' else submit(args.manifest.resolve(strict=True), args.manifest_sha256)))


if __name__ == '__main__':
    main()
