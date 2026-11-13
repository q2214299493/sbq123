"""Reduce a resource-queued continuation point inside its 15-GiB ceiling."""
from __future__ import annotations

import argparse
import importlib.util
import math
from pathlib import Path
import re
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.neb_agent import mz73_static, submission
from scripts.neb_agent.mz73_continuation import NAMES, validate_request
from scripts.neb_agent.mz73_timebudget import TIMEOUT_LEAF
from scripts.neb_agent.utils_structure import read_poscar
from scripts.slurm_force_label import parse_scontrol_job

spec = importlib.util.spec_from_file_location('continuous_static_memory_legacy', Path(__file__).with_name('reduce_pending_static_memory.py'))
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
require, ref = legacy.require, legacy.ref


def checked_peak_kB(value):
    require(type(value) in (int, float) and math.isfinite(value) and 0 < value * 1.5 < 7 * 1024 * 1024,
            '7 GiB lacks a 1.5-fold margin above the identical VASP setup peak')
    return value


def amend(case, leaf):
    require(leaf in NAMES, 'not an authorized continuation label')
    directory = case / 'labels' / leaf
    record_path = directory / 'submission_record.json'
    record = load_json_object(record_path)
    require(record['status'] == 'SUBMITTED' and record['server_alias'] == mz73_static.BACKEND_ID, 'no known submitted point')
    backend = mz73_static.load_mz73_static_backend(leaf)
    require(record['remote_dir'] == backend['remote_root'] + '/' + leaf, 'wrong static job directory')
    request = load_json_object(directory / mz73_static.PAPER_REQUEST)
    budget = validate_request(directory, request, backend)
    require(budget['resources']['memory'] == '15G', 'approved continuation cap changed')
    bundle = submission.InputBundle.from_preflight(load_json_object(directory / 'submission_preflight.json'))
    bundle.verify(directory)
    require(bundle.bundle_sha256 == record['bundle_sha256'] and sha256_file(directory / 'submission_decision.json')
            == record['gate_decision_sha256'], 'submitted input/gate bytes changed')
    source = case / 'labels' / TIMEOUT_LEAF
    label = load_json_object(source / 'force_label_review_v2/paper_force_label.json')
    outcar = source / 'OUTCAR'
    require(sha256_file(outcar) == label['outcar']['sha256'], 'reference OUTCAR changed')
    for name in ('INCAR', 'KPOINTS', 'POTCAR.spec', 'POTCAR'):
        require(sha256_file(source / name) == sha256_file(directory / name), 'VASP memory reference parameters differ')
    old, current = read_poscar(source / 'POSCAR'), read_poscar(directory / 'POSCAR')
    require(old.labels == current.labels and np.allclose(old.cell, current.cell, atol=1e-8, rtol=0)
            and old.flags == current.flags, 'basis/system/mask memory dimensions changed')
    peaks = []
    with outcar.open(errors='replace') as stream:
        for line in stream:
            found = re.search(r'Maximum memory used \(kb\):\s*([\d.]+)', line)
            if found:
                peaks.append(float(found.group(1)))
    require(bool(peaks), 'no measured reference memory peak')
    peak = checked_peak_kB(peaks[-1])

    def query():
        return legacy.memory.primary.run(mz73_static.ssh_argv(backend, 'scontrol -o show job ' + record['job_id']))

    before = query()
    parsed = parse_scontrol_job(before.stdout, record['job_id'])
    if parsed['job_state'] == 'RUNNING':
        return {'job_id': record['job_id'], 'status': 'already_running_no_change', 'new_jobs': 0}
    requested = legacy.field(before.stdout, 'MinMemoryNode')
    require(requested in ('15G', '16G'), 'unexpected pending memory allocation')
    legacy.validate_job(before.stdout, record, memory_value=requested, pending=True)
    attempt, receipt = directory / 'pending_memory_reduction_attempt.json', directory / 'pending_memory_reduction.json'
    binding = {'job_id': record['job_id'], 'remote_dir': record['remote_dir'], 'submission': ref(record_path),
               'decision': ref(directory / 'submission_decision.json'), 'bundle_sha256': bundle.bundle_sha256,
               'authorization': request['execution_budget_authorization'], 'memory_reference_OUTCAR': ref(outcar),
               'previous_identical_setup_peak_kB': peak, 'observed_original_request': requested,
               'approved_memory_ceiling_GiB': 15, 'amended_memory_GiB': 7,
               'legacy_renderer_cap_mismatch': requested == '16G', 'new_jobs': 0,
               'scientific_inputs_changed': False, 'time_limit_changed': False, 'before_stdout': before.stdout,
               'memory_review': 'Same species/count/cell/ENCUT/kmesh/POTCAR/spin/rank setup; 7 GiB exceeds 1.5 times measured 4.394 GiB.'}
    write_json_exclusive(attempt, {'status': 'UNKNOWN', **binding})
    argv = mz73_static.ssh_argv(backend, 'scontrol update JobId=' + record['job_id'] + ' MinMemoryNode=7168')
    update = legacy.memory.primary.run(argv)
    after = query()
    legacy.validate_job(after.stdout, record, memory_value='7G', pending=False)
    bundle.verify(directory)
    write_json_exclusive(receipt, {'status': 'native_pending_RAM_reduction_verified', **binding,
        'update': {'argv': argv, 'returncode': update.returncode, 'stdout': update.stdout, 'stderr': update.stderr},
        'after_stdout': after.stdout, 'implementation': ref(__file__)})
    return {'job_id': record['job_id'], 'memory_GiB': 7, 'previous_measured_peak_GiB': peak / 1024**2,
            'new_jobs': 0, 'receipt': ref(receipt)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-root', type=Path, required=True)
    parser.add_argument('--workdir-name', required=True)
    args = parser.parse_args()
    print(amend(args.case_root.resolve(strict=True), args.workdir_name))


if __name__ == '__main__':
    main()
