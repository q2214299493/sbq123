"""Read-only native exit evidence if SSH returns after Slurm's retention window.

Controller exit events are not a reconstructed native COMPLETED enum. This
never validates training, submits work, or accepts a checkpoint on its own.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import slurm_controller_events as controller
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.slurm_force_label import parse_scontrol_job

spec = importlib.util.spec_from_file_location('training_native_exit_primary', Path(__file__).with_name('paper_training_job.py'))
primary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(primary)


def scope(record_path, initial_capture):
    record = load_json_object(record_path)
    primary.require(record['status'] == 'SUBMITTED', 'no actual training submission')
    manifest_path = Path(record['manifest']['path']).resolve(strict=True)
    primary.require(sha256_file(manifest_path) == record['manifest']['sha256'], 'training manifest bytes changed')
    manifest = load_json_object(manifest_path)
    primary.require(record_path.resolve(strict=True).parent == manifest_path.parent.parent
        and manifest['document_kind'] == 'paper_single_metadata_recovery_manifest'
        and record['remote_dir'] == manifest['remote_dir'], 'not the exact metadata training recovery')
    initial = load_json_object(initial_capture)
    native = initial['native_scontrol']
    primary.require(native['returncode'] == 0 and initial['hostname'] == 'MZ73', 'missing earlier native training identity')
    parsed = parse_scontrol_job(native['stdout'], record['job_id'])
    primary.require(parsed['remote_dir'] == record['remote_dir']
        and parsed['command'] == record['remote_dir'] + '/job.sh', 'earlier native identity belongs to another job')
    times = re.findall(r'(?:^|\s)SubmitTime=(\S+)', native['stdout'])
    primary.require(len(times) == 1, 'ambiguous native submit time')
    backend = primary.remote.load_mz73_static_backend(primary.budget_owner.TIMEOUT_LEAF)
    backend['time_limit'] = manifest['resources']['time_limit']
    return record, backend, times[0]


def verified_exit(packet, record, backend, submit_time):
    primary.require(packet['hostname'] == backend['node'], 'native training evidence comes from another host')
    native = packet['job_query']
    if native['returncode'] == 0:
        parsed = parse_scontrol_job(native['stdout'], record['job_id'])
        primary.require(parsed['remote_dir'] == record['remote_dir']
            and parsed['command'] == record['remote_dir'] + '/job.sh'
            and parsed['job_state'] == 'COMPLETED' and parsed['exit_code'] == '0:0', 'no native successful terminal training state')
        return {'result_class': 'native_scheduler_terminal_state_only', 'scheduler_terminal_state': 'COMPLETED', 'native_exit_code': '0:0'}
    summary = controller._events(packet, record['job_id'], submit_time, backend)
    return {'result_class': 'native_controller_exit_events_only', 'scheduler_terminal_state': None, **summary}


def collect(record_path, initial_capture, output):
    record, backend, submit_time = scope(record_path, initial_capture)
    program = controller._REMOTE.replace('__JOB_ID__', record['job_id'])
    argv = primary.remote.ssh_argv(backend, shlex.join(['python3', '-B', '-c', program]))
    result = subprocess.run(argv, capture_output=True, timeout=30, check=False)
    primary.require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 65536,
                    'native training exit query failed: ' + result.stderr.decode(errors='replace')[:1000])
    packet = json.loads(result.stdout)
    summary = verified_exit(packet, record, backend, submit_time)
    case = record_path.resolve(strict=True).parent
    primary.require(output.resolve().is_relative_to(case), 'exit evidence output escapes the case')
    proof = {'document_kind': 'paper_training_native_exit_evidence', 'job_id': record['job_id'],
        'remote_dir': record['remote_dir'], 'checked_at': datetime.now(timezone.utc).isoformat(),
        'submission': primary.ref(record_path), 'initial_native_capture': primary.ref(initial_capture),
        'source': primary.ref(__file__), 'controller_parser_source': primary.ref(controller.__file__),
        'query': {'argv': argv, 'returncode': result.returncode, 'stdout_base64': base64.b64encode(result.stdout).decode(),
                  'stdout_sha256': hashlib.sha256(result.stdout).hexdigest()},
        'training_completion_validated': False, 'checkpoint_accepted': False, **summary}
    write_json_exclusive(output, proof)
    return primary.ref(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('record', 'initial-capture', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(collect(args.record, args.initial_capture, args.output)))


if __name__ == '__main__':
    main()
