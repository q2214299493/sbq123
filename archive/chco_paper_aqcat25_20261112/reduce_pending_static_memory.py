"""Lower only the queued next static label's RAM request inside its budget cap.

The previous identical VASP setup actually peaked below 4.5 GiB. Keep every
scientific input, GPU/CPU count, 60-minute limit, job ID and gate unchanged.
No new job, cancellation, restart or automatic retry is performed.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.neb_agent import mz73_static, submission
from scripts.neb_agent.mz73_timebudget import NEXT_LEAF, TIMEOUT_LEAF, validate_budget_authorization
from scripts.slurm_force_label import parse_scontrol_job

spec = importlib.util.spec_from_file_location('static_memory_field_owner', Path(__file__).with_name('reduce_pending_training_memory.py'))
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)
require, field, ref = memory.require, memory.field, memory.ref


def validate_job(raw, record, *, memory_value, pending):
    parsed = parse_scontrol_job(raw, record['job_id'])
    require(parsed['remote_dir'] == record['remote_dir'] and parsed['command'] == record['remote_dir'] + '/script.sbatch', 'static job identity drift')
    if pending:
        require(parsed['job_state'] == 'PENDING' and field(raw, 'Reason') == 'Resources', 'only the resource-queued static label may be amended')
    expected = {'ReqNodeList': 'MZ73', 'TimeLimit': '01:00:00', 'NumCPUs': '4', 'NumTasks': '1',
        'CPUs/Task': '4', 'TresPerNode': 'gres/gpu:1', 'Requeue': '0', 'MinMemoryNode': memory_value}
    require(all(field(raw, key) == value for key, value in expected.items()), 'static allocation is outside the exact bounded scope')
    return parsed


def amend(case):
    directory = case / 'labels' / NEXT_LEAF
    record_path = directory / 'submission_record.json'
    record = load_json_object(record_path)
    require(record['status'] == 'SUBMITTED' and record['server_alias'] == mz73_static.BACKEND_ID, 'no actual next-label submission')
    backend = mz73_static.load_mz73_static_backend(NEXT_LEAF)
    require(record['remote_dir'] == backend['remote_root'] + '/' + NEXT_LEAF, 'wrong static target')
    budget = validate_budget_authorization(directory, load_json_object(directory / mz73_static.PAPER_REQUEST), backend)
    require(budget['resources']['memory'] == '16G', 'approved memory cap is not 16 GiB')
    bundle = submission.InputBundle.from_preflight(load_json_object(directory / 'submission_preflight.json'))
    bundle.verify(directory)
    require(bundle.bundle_sha256 == record['bundle_sha256']
        and sha256_file(directory / 'submission_decision.json') == record['gate_decision_sha256'], 'submitted scientific input/gate changed')
    source = case / 'labels' / TIMEOUT_LEAF
    old_label = load_json_object(source / 'force_label_review_v2/paper_force_label.json')
    outcar = source / 'OUTCAR'
    require(sha256_file(outcar) == old_label['outcar']['sha256'], 'reference VASP memory evidence changed')
    for name in ('INCAR', 'KPOINTS', 'POTCAR.spec'):
        require(sha256_file(source / name) == sha256_file(directory / name), 'memory reference has different scientific parameters')
    peak = []
    with outcar.open(errors='replace') as stream:
        for line in stream:
            match = re.search(r'Maximum memory used \(kb\):\s*([\d.]+)', line)
            if match:
                peak.append(float(match.group(1)))
    require(peak and 0 < peak[-1] < 7.5 * 1024 * 1024, '15 GiB lacks the required twofold observed RAM margin')
    job_id = record['job_id']

    def query():
        return memory.primary.run(mz73_static.ssh_argv(backend, 'scontrol -o show job ' + job_id))

    before = query()
    parsed = parse_scontrol_job(before.stdout, job_id)
    if parsed['job_state'] == 'RUNNING':
        return {'status': 'already_running_no_change', 'job_id': job_id, 'new_jobs': 0}
    validate_job(before.stdout, record, memory_value='16G', pending=True)
    attempt, receipt = directory / 'pending_memory_reduction_attempt.json', directory / 'pending_memory_reduction.json'
    require(not receipt.exists(), 'static memory amendment already recorded')
    binding = {'job_id': job_id, 'remote_dir': record['remote_dir'], 'submission': ref(record_path),
        'decision': ref(directory / 'submission_decision.json'), 'bundle_sha256': bundle.bundle_sha256,
        'budget': ref(case / 'execution_budget_authorization_60min.json'), 'memory_reference_OUTCAR': ref(outcar),
        'previous_identical_setup_peak_kB': peak[-1], 'original_memory_GiB': 16, 'amended_memory_GiB': 15,
        'before_stdout': before.stdout, 'new_jobs': 0, 'scientific_inputs_changed': False, 'time_limit_changed': False}
    write_json_exclusive(attempt, {'status': 'UNKNOWN', **binding})
    argv = mz73_static.ssh_argv(backend, 'scontrol update JobId=' + job_id + ' MinMemoryNode=15360')
    result = memory.primary.run(argv)
    after = query()
    validate_job(after.stdout, record, memory_value='15G', pending=False)
    bundle.verify(directory)
    write_json_exclusive(receipt, {'status': 'native_pending_RAM_reduction_verified', **binding,
        'update': {'argv': argv, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr},
        'after_stdout': after.stdout, 'implementation': ref(__file__)})
    return {'status': 'native_pending_RAM_reduction_verified', 'job_id': job_id, 'memory_GiB': 15,
        'previous_setup_peak_GiB': peak[-1] / (1024 * 1024), 'new_jobs': 0, 'receipt': ref(receipt)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-root', type=Path, required=True)
    print(json.dumps(amend(parser.parse_args().case_root.resolve(strict=True))))


if __name__ == '__main__':
    main()
