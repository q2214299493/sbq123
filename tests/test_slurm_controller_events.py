"""Synthetic daemon events test provenance, never production scheduler states."""
import base64
import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts import slurm_controller_events as events
from scripts import slurm_force_label as native
from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.neb_agent.mz73_static import load_mz73_static_backend

LEAF = 'paper_chco_aqcat25_ft512_20261112_r000_label'
JOB = '13880'
RAW = (
    '[2026-11-12T12:00:00.100] _slurm_rpc_submit_batch_job: JobId=13880 SLUID=test InitPrio=1 usec=1\n'
    '[2026-11-12T12:01:00.001] sched: Allocate JobId=13880 NodeList=MZ73 #CPUs=4 Partition=gpu\n'
    '[2026-11-12T12:02:00.001] _job_complete: JobId=13880 WEXITSTATUS 0\n'
    '[2026-11-12T12:02:00.002] _job_complete: JobId=13880 done\n'
)


def encoded(text):
    raw = text.encode()
    return {'events_base64': base64.b64encode(raw).decode(), 'events_sha256': hashlib.sha256(raw).hexdigest()}


@pytest.fixture
def case(tmp_path, monkeypatch):
    config = tmp_path / 'execution_backends.yaml'
    config.write_bytes((Path(__file__).resolve().parents[1] / 'configs/execution_backends.yaml').read_bytes())
    backend = load_mz73_static_backend(LEAF, config_path=config)
    target = backend['remote_root'] + '/' + LEAF
    args = dict(job_id=JOB, remote_dir=target, workdir_name=LEAF, config_path=config)
    raw = (f'JobId={JOB} JobState=PENDING ExitCode=0:0 WorkDir={target} Command={target}/script.sbatch '
           'SubmitTime=2026-11-12T12:00:00\n')
    monkeypatch.setattr(native.subprocess, 'run', lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, raw.encode(), b''))
    initial = native.query_slurm_force_label(**args)
    path = tmp_path / 'first_query.json'
    write_json_exclusive(path, initial)
    packet = {'hostname': 'MZ73', 'timezone_offset': '+0800',
              'job_query': {'returncode': 1, 'stdout': '', 'stderr': 'slurm_load_jobs error: Invalid job id specified\n'},
              'controller_config': {'AccountingStorageType': '(null)', 'JobCompType': '(null)',
                                    'MinJobAge': '300 sec', 'SlurmctldLogFile': '/var/log/slurm/slurmctld.log'},
              'log': {'path': '/var/log/slurm/slurmctld.log', 'regular': True, 'owner_uid': 0,
                      'reader_uid': 1000, 'mode': 0o644, 'reader_can_write': False,
                      'prefix_bytes': 10000, 'prefix_sha256': 'a' * 64, **encoded(RAW)}}
    calls = []

    def transport(argv, **kwargs):
        assert argv == events._argv(backend, JOB)
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, json.dumps(packet).encode(), b'')

    monkeypatch.setattr(events.subprocess, 'run', transport)
    return args, path, packet, calls


def collect(case):
    args, path, _, _ = case
    return events.collect_controller_events(initial_evidence=path, **args)


def test_controller_events_remain_distinct_from_unavailable_native_enum(case):
    evidence = collect(case)
    assert evidence['scheduler_terminal_state'] is None and 'job_state' not in evidence
    assert evidence['controller_exit_status'] == 0 and evidence['elapsed_seconds'] == 60.0
    assert evidence['initial_native_evidence']['sha256'] == sha256_file(case[1])
    assert events.verify_controller_events_live(evidence, **case[0])['events_sha256'] == encoded(RAW)['events_sha256']
    assert len(case[3]) == 2


@pytest.mark.parametrize('change', [
    lambda p: p['job_query'].update(returncode=0),
    lambda p: p['job_query'].update(stderr='controller unreachable'),
    lambda p: p.update(hostname='other'),
    lambda p: p['controller_config'].update(AccountingStorageType='accounting_storage/slurmdbd'),
    lambda p: p['controller_config'].update(JobCompType='jobcomp/filetxt'),
    lambda p: p['log'].update(path='/tmp/fake'),
    lambda p: p['log'].update(owner_uid=1000),
    lambda p: p['log'].update(reader_can_write=True),
    lambda p: p['log'].update(mode=0o666),
    lambda p: p['log'].update(events_sha256='0' * 64),
    lambda p: p['log'].update(**encoded(RAW.replace('WEXITSTATUS 0', 'WEXITSTATUS 1'))),
    lambda p: p['log'].update(**encoded(RAW.replace('WEXITSTATUS 0', 'WTERMSIG 15'))),
    lambda p: p['log'].update(**encoded(RAW.replace('13880', '13881'))),
    lambda p: p['log'].update(**encoded(RAW.replace('#CPUs=4', '#CPUs=8'))),
    lambda p: p['log'].update(**encoded(RAW.replace('12:00:00.100', '11:00:00.100'))),
    lambda p: p['log'].update(**encoded(RAW.replace('12:02:00', '13:02:00'))),
    lambda p: p['log'].update(**encoded(RAW.splitlines(keepends=True)[0])),
    lambda p: p['log'].update(**encoded(RAW + '[2026-11-12T12:02:01] cancel JobId=13880\n')),
    lambda p: p['log'].update(**encoded('{"document_kind":"producer_exit_record","exit_code":0}\n')),
])
def test_not_a_replacement_for_missing_or_conflicting_scheduler_events(case, change):
    change(case[2])
    with pytest.raises(ValueError):
        collect(case)


def test_original_live_directory_identity_cannot_be_resealed(case):
    original = json.loads(case[1].read_bytes())
    original['remote_dir'] += '/other'
    case[1].write_text(json.dumps(original))
    with pytest.raises(ValueError):
        collect(case)
    assert not case[3]


def test_stored_summary_tampering_is_rejected_before_live_query(case):
    e = collect(case)
    e['elapsed_seconds'] = 61
    before = len(case[3])
    with pytest.raises(ValueError):
        events.verify_controller_events_live(e, **case[0])
    assert len(case[3]) == before


def test_new_live_controller_event_invalidates_previously_cached_completion(case):
    e = collect(case)
    case[2]['log'].update(**encoded(RAW + '[2026-11-12T12:03:00] requeue JobId=13880\n'))
    with pytest.raises(ValueError):
        events.verify_controller_events_live(e, **case[0])


def test_unrelated_log_growth_does_not_change_the_same_native_job_events(case):
    e = collect(case)
    case[2]['log']['prefix_sha256'] = 'b' * 64
    assert events.verify_controller_events_live(e, **case[0])['events_sha256'] == e['events_sha256']


def test_force_label_verifier_routes_controller_proof_without_a_fabricated_scontrol_record(case):
    e = collect(case)
    assert native.verify_slurm_force_label_live(e, **case[0])['controller_exit_status'] == 0


def test_resealed_raw_query_cannot_change_the_link_to_the_initial_source(case):
    e = collect(case)
    altered = copy.deepcopy(e)
    altered['initial_native_evidence']['sha256'] = '0' * 64
    with pytest.raises(ValueError):
        events.validate_controller_events(altered, **case[0])
