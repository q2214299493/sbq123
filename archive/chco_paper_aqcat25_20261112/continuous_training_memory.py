"""Lower an unstarted continuous training job from its 15-GiB cap to 7 GiB."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


training = module('memory_continuous_training', 'continuous_training.py')
legacy = module('memory_continuous_validator', 'reduce_pending_training_memory.py')
require, ref = training.require, training.ref


def validate_preflight(report):
    peak = report.get('peak_RSS_bytes')
    require(report.get('document_kind') == 'readonly_host_memory_preflight'
            and report.get('training_performed') is False and report.get('GPU_model_constructed') is False,
            'not the read-only CPU checkpoint memory preflight')
    require(type(peak) in (int, float) and math.isfinite(peak) and 0 < peak < 2 * 2**30,
            'CPU checkpoint inspection does not leave adequate 7-GiB headroom')
    inspection = report.get('inspection', {})
    require(inspection.get('status') == 'passed_candidate_only', 'full checkpoint/database inspection failed')
    return peak


def amend(path, digest):
    manifest, checked = training.verify(path, digest)
    require(manifest['resources']['memory'] == '15G', 'original approved cap changed')
    case, leaf, backend = checked['case'], checked['leaf'], checked['backend']
    record_path = case / (leaf + '_submission_record.json')
    record = load_json_object(record_path)
    require(record['status'] == 'SUBMITTED' and record['manifest_sha256'] == digest
            and record['remote_dir'] == checked['target'], 'missing exact primary submission')
    root = case / 'continuation_force003_20261113'
    preflight_path = root / 'host_memory_preflight.stdout.json'
    report = load_json_object(preflight_path)
    peak = validate_preflight(report)
    preflight_receipt = root / 'host_memory_preflight.receipt.json'
    receipt_data = load_json_object(preflight_receipt)
    require(receipt_data['returncode'] == 0 and receipt_data['stdout_sha256'] == sha256_file(preflight_path)
            and receipt_data['source_sha256'] == sha256_file(Path(__file__).with_name('inspect_trained_checkpoint.py')),
            'memory preflight source/receipt changed')

    def query():
        return training.primary.run(training.primary.remote.ssh_argv(backend, 'scontrol -o show job ' + record['job_id']))

    before = query()
    parsed = legacy.parse_scontrol_job(before.stdout, record['job_id'])
    if parsed['job_state'] == 'RUNNING':
        return {'job_id': record['job_id'], 'changed': False, 'reason': 'already running; no modification'}
    legacy.validate_job(before.stdout, record, pending=True, memory='15G')
    attempt, receipt = case / (leaf + '_memory_reduction_attempt.json'), case / (leaf + '_memory_reduction.json')
    binding = {'job_id': record['job_id'], 'remote_dir': record['remote_dir'], 'manifest': ref(path),
               'submission': ref(record_path), 'authorization': manifest['authorization'], 'implementation': ref(__file__),
               'CPU_memory_preflight': ref(preflight_path), 'CPU_memory_preflight_receipt': ref(preflight_receipt),
               'CPU_preflight_peak_RSS_bytes': peak, 'actual_training_peak_measured': False,
               'original_requested_memory_MiB': 15360, 'amended_requested_memory_MiB': 7168,
               'new_jobs': 0, 'scientific_input_changes': False,
               'before': {'stdout': before.stdout, 'stderr': before.stderr, 'returncode': before.returncode},
               'review': 'Same 49-atom worker/base/recipe; CPU full-checkpoint inspection below 2 GiB, 7 GiB chosen inside the 15-GiB ceiling. Actual training must still pass.'}
    write_json_exclusive(attempt, {'status': 'UNKNOWN', **binding})
    argv = training.primary.remote.ssh_argv(backend, 'scontrol update JobId=' + record['job_id'] + ' MinMemoryNode=7168')
    result = training.primary.run(argv)
    after = query()
    legacy.validate_job(after.stdout, record, pending=False, memory='7G')
    proof = {'document_kind': 'continuous_pending_training_memory_reduction',
             'status': 'native_scheduler_change_verified', 'checked_at': datetime.now(timezone.utc).isoformat(),
             **binding, 'update': {'argv': argv, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr},
             'after': {'returncode': after.returncode, 'stdout': after.stdout, 'stderr': after.stderr}}
    write_json_exclusive(receipt, proof)
    return {'job_id': record['job_id'], 'memory_GiB': 7, 'new_jobs': 0, 'receipt': ref(receipt)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    print(amend(args.manifest.resolve(strict=True), args.manifest_sha256))


if __name__ == '__main__':
    main()
