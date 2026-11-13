"""Reduce the existing queued MZ73 training allocation within its memory cap.

No job cancellation, new submission, change to scientific inputs, or retry.
Keep the original manifest frozen and record the scheduler amendment separately.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.artifact_io import load_json_object, write_json_exclusive
from scripts.slurm_force_label import parse_scontrol_job

spec = importlib.util.spec_from_file_location('paper_training_memory_primary', Path(__file__).with_name('paper_training_job.py'))
primary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(primary)
require, ref, bound = primary.require, primary.ref, primary.bound


def field(raw, key):
    matches = re.findall(r'(?:^|\s)' + re.escape(key) + r'=(\S+)', raw)
    require(len(matches) == 1, 'missing or ambiguous Slurm field: ' + key)
    return matches[0]


def validate_job(raw, record, *, pending, memory):
    parsed = parse_scontrol_job(raw, record['job_id'])
    require(parsed['remote_dir'] == record['remote_dir'] and parsed['command'] == record['remote_dir'] + '/job.sh', 'job identity drift')
    if pending:
        require(parsed['job_state'] == 'PENDING' and field(raw, 'Reason') == 'Resources', 'only a resource-queued job may be amended')
    required = {'ReqNodeList': 'MZ73', 'TimeLimit': '00:10:00', 'NumCPUs': '4', 'NumTasks': '1',
                'CPUs/Task': '4', 'TresPerNode': 'gres/gpu:1', 'Requeue': '0', 'MinMemoryNode': memory}
    require(all(field(raw, key) == value for key, value in required.items()), 'training resources differ from the exact amendment scope')
    return parsed


def amend(path, digest):
    manifest, checked = primary.verify(path, digest)
    require(manifest['resources'] == primary.RESOURCES and primary.RESOURCES['memory'] == '16G', 'original memory cap changed')
    case = checked['case']
    record_path = case / 'training_submission_record.json'
    record = load_json_object(record_path)
    require(record['status'] == 'SUBMITTED' and record['manifest_sha256'] == digest
            and record['remote_dir'] == checked['remote_dir'], 'missing exact original training receipt')
    backend = checked['backend']

    def query():
        return primary.run(primary.remote.ssh_argv(backend, 'scontrol -o show job ' + record['job_id']))

    before = query()
    validate_job(before.stdout, record, pending=True, memory='16G')
    receipt = case / 'training_memory_amendment.json'
    attempt = case / 'training_memory_amendment_attempt.json'
    require(not receipt.exists(), 'memory amendment already recorded')
    binding = {'primary_manifest': {'path': str(path.resolve(strict=True)), 'sha256': digest},
               'primary_receipt': ref(record_path), 'budget': manifest['inputs']['budget'],
               'implementation': ref(__file__), 'job_id': record['job_id'], 'remote_dir': record['remote_dir'],
               'original_requested_memory_MiB': 16384, 'amended_requested_memory_MiB': 15360,
               'new_jobs': 0, 'scientific_input_changes': False,
               'authorization_interpretation': 'Reduce pending allocation below the user-approved 16 GiB ceiling; retain 1 GPU/4 CPU/100 epochs/10 minutes.',
               'before': {'stdout': before.stdout, 'stderr': before.stderr, 'returncode': before.returncode}}
    write_json_exclusive(attempt, {'status': 'UNKNOWN', **binding})
    argv = primary.remote.ssh_argv(backend, 'scontrol update JobId=' + record['job_id'] + ' MinMemoryNode=15360')
    result = primary.run(argv)
    after = query()
    validate_job(after.stdout, record, pending=False, memory='15G')
    proof = {'document_kind': 'pending_training_memory_reduction', 'status': 'native_scheduler_change_verified',
             'checked_at': datetime.now(timezone.utc).isoformat(), **binding,
             'update': {'argv': argv, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr},
             'after': {'returncode': after.returncode, 'stdout': after.stdout, 'stderr': after.stderr}}
    write_json_exclusive(receipt, proof)
    return {'job_id': record['job_id'], 'status': proof['status'], 'requested_memory_GiB': 15,
            'new_jobs': 0, 'receipt': ref(receipt)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(amend(args.manifest.resolve(strict=True), args.manifest_sha256)))


if __name__ == '__main__':
    main()
