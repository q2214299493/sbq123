"""Recover native controller exit events without inventing a purged job state.

A recorded zero-exit controller event can accompany a force-only VASP label.
It is not a reconstructed scontrol COMPLETED record. The actual scientific
output, input identity and electronic/geometry checks remain mandatory.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file
from scripts.execution_backends import DEFAULT_CONFIG
from scripts.slurm_force_label import _target, validate_stored_slurm_force_label
from scripts.neb_agent.mz73_static import BACKEND_ID, ssh_argv

DOCUMENT_KIND = "slurm_native_controller_exit_events"
_REMOTE = r'''
import base64,hashlib,json,os,re,socket,stat,subprocess,time
from pathlib import Path
job=__JOB_ID__
query=subprocess.run(['scontrol','-o','show','job',str(job)],capture_output=True)
config=subprocess.run(['scontrol','show','config'],capture_output=True,check=True).stdout.decode()
keys=('AccountingStorageType','JobCompType','MinJobAge','SlurmctldLogFile')
fields={}
for line in config.splitlines():
 parts=line.split('=',1)
 if len(parts)==2 and parts[0].strip() in keys:fields[parts[0].strip()]=parts[1].strip()
p=Path(fields['SlurmctldLogFile'])
with p.open('rb') as f:
 s=os.fstat(f.fileno())
 if not stat.S_ISREG(s.st_mode) or s.st_size>20000000:raise ValueError('unsupported controller log size/type')
 data=f.read(s.st_size)
 after=os.fstat(f.fileno())
 if len(data)!=s.st_size or after.st_size<s.st_size:raise ValueError('controller log changed while reading')
pattern=re.compile(rb'\bJobId='+str(job).encode()+rb'\b')
events=b''.join(line for line in data.splitlines(keepends=True) if pattern.search(line))
if len(events)>16000:raise ValueError('oversized job event excerpt')
print(json.dumps({'hostname':socket.gethostname().split('.')[0], 'timezone_offset':time.strftime('%z'),
 'job_query':{'returncode':query.returncode,'stdout':query.stdout.decode(),'stderr':query.stderr.decode()},
 'controller_config':fields,'log':{'path':str(p),'regular':stat.S_ISREG(s.st_mode),'owner_uid':s.st_uid,
 'reader_uid':os.geteuid(),'mode':stat.S_IMODE(s.st_mode),'reader_can_write':os.access(p,os.W_OK),
 'prefix_bytes':len(data),'prefix_sha256':hashlib.sha256(data).hexdigest(),
 'events_base64':base64.b64encode(events).decode(),'events_sha256':hashlib.sha256(events).hexdigest()}}))
'''


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _argv(backend, job_id):
    return ssh_argv(backend, shlex.join(['python3', '-c', _REMOTE.replace('__JOB_ID__', job_id)]))


def _initial(reference, arguments):
    path = Path(reference['path']).resolve(strict=True)
    _require(sha256_file(path) == reference['sha256'], 'initial native job evidence changed')
    evidence = load_json_object(path)
    validate_stored_slurm_force_label(evidence, **arguments, require_completed=False)
    match = re.search(r'(?:^|\s)SubmitTime=(\S+)', evidence['query']['stdout'])
    _require(match is not None, 'initial native evidence has no submission time')
    return match.group(1)


def _events(packet, job_id, submit_time, backend):
    native = packet['job_query']
    _require(native['returncode'] == 1 and native['stdout'] == ''
             and 'Invalid job id specified' in native['stderr'], 'job is not confirmed purged from scontrol')
    config, log = packet['controller_config'], packet['log']
    _require(packet['hostname'] == backend['node'] and log['path'] == config['SlurmctldLogFile'],
             'controller log host/path mismatch')
    _require(config['AccountingStorageType'] in ('(null)', 'accounting_storage/none')
             and config['JobCompType'] in ('(null)', 'jobcomp/none'), 'use the available native accounting instead')
    _require(log['regular'] is True and log['owner_uid'] != log['reader_uid']
             and log['reader_can_write'] is False and not log['mode'] & 0o002,
             'controller events must come from a non-user-writable daemon log')
    raw = base64.b64decode(log['events_base64'], validate=True)
    _require(len(raw) <= 16000 and hashlib.sha256(raw).hexdigest() == log['events_sha256'],
             'controller event raw bytes changed')
    rows = raw.decode('utf-8').splitlines()
    _require(len(rows) == 4, 'ambiguous/missing/extra job events; manual review required')
    stamps = []
    bodies = []
    for row in rows:
        match = re.fullmatch(r'\[([^]]+)\] (.*)', row)
        _require(match is not None, 'malformed native controller event')
        stamps.append(datetime.fromisoformat(match.group(1)))
        bodies.append(match.group(2))
    job = re.escape(job_id)
    _require(re.search(r'_slurm_rpc_submit_batch_job: JobId=' + job + r'\b', bodies[0]) is not None
             and stamps[0].isoformat().startswith(submit_time), 'controller submit event belongs to another job lifetime')
    _require(re.fullmatch(r'sched: Allocate JobId=' + job + r' NodeList=' + re.escape(backend['node'])
                         + r' #CPUs=' + str(backend['cpus_per_task']) + r' Partition=' + re.escape(backend['partition']), bodies[1]) is not None,
             'controller allocation does not match the authorized host/resources')
    _require(re.fullmatch(r'_job_complete: JobId=' + job + r' WEXITSTATUS 0', bodies[2]) is not None
             and re.fullmatch(r'_job_complete: JobId=' + job + r' done', bodies[3]) is not None,
             'missing native controller zero-exit/done events')
    _require(stamps == sorted(stamps) and stamps[0] < stamps[1] < stamps[2], 'controller event order is invalid')
    limit = sum(int(value) * factor for value, factor in zip(backend['time_limit'].split(':'), (3600, 60, 1), strict=True))
    _require((stamps[2] - stamps[1]).total_seconds() <= limit, 'controller run exceeds the bounded force-label job')
    return {'events_sha256': log['events_sha256'], 'allocated_at_controller_local': stamps[1].isoformat(),
            'ended_at_controller_local': stamps[2].isoformat(), 'controller_timezone_offset': packet['timezone_offset'],
            'elapsed_seconds': (stamps[2] - stamps[1]).total_seconds(), 'controller_exit_status': 0}


def collect_controller_events(job_id: str, remote_dir: str, workdir_name: str, *,
                              initial_evidence: Path, config_path: Path = DEFAULT_CONFIG) -> dict:
    job_id, backend, _ = _target(job_id, remote_dir, workdir_name, config_path)
    arguments = dict(job_id=job_id, remote_dir=remote_dir, workdir_name=workdir_name, config_path=config_path)
    initial = {'path': str(initial_evidence.resolve(strict=True)), 'sha256': sha256_file(initial_evidence)}
    submit_time = _initial(initial, arguments)
    argv = _argv(backend, job_id)
    result = subprocess.run(argv, capture_output=True, timeout=30, check=False)
    _require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 65536,
             'native controller event query failed')
    packet = json.loads(result.stdout)
    summary = _events(packet, job_id, submit_time, backend)
    return {'schema_version': 1, 'document_kind': DOCUMENT_KIND, 'scheduler': 'Slurm', 'backend_id': BACKEND_ID,
            'backend_config_sha256': backend['config_sha256'], 'result_class': 'native_controller_exit_events_only',
            'job_id': job_id, 'remote_dir': remote_dir, 'workdir_name': workdir_name,
            'scheduler_terminal_state': None, 'initial_native_evidence': initial,
            'checked_at': datetime.now(timezone.utc).isoformat(), **summary,
            'query': {'argv': argv, 'returncode': result.returncode, 'stdout_base64': base64.b64encode(result.stdout).decode(),
                      'stdout_sha256': hashlib.sha256(result.stdout).hexdigest()}}


def validate_controller_events(evidence, *, job_id, remote_dir, workdir_name, config_path=DEFAULT_CONFIG):
    job_id, backend, _ = _target(job_id, remote_dir, workdir_name, config_path)
    arguments = dict(job_id=job_id, remote_dir=remote_dir, workdir_name=workdir_name, config_path=config_path)
    for key, value in {'schema_version': 1, 'document_kind': DOCUMENT_KIND, 'scheduler': 'Slurm',
                       'backend_id': BACKEND_ID, 'backend_config_sha256': backend['config_sha256'],
                       'result_class': 'native_controller_exit_events_only', 'job_id': job_id,
                       'remote_dir': remote_dir, 'workdir_name': workdir_name, 'scheduler_terminal_state': None}.items():
        _require(evidence.get(key) == value, 'controller evidence identity/scope mismatch: ' + key)
    query = evidence['query']
    raw = base64.b64decode(query['stdout_base64'], validate=True)
    _require(query['argv'] == _argv(backend, job_id) and query['returncode'] == 0
             and hashlib.sha256(raw).hexdigest() == query['stdout_sha256'], 'controller query source changed')
    summary = _events(json.loads(raw), job_id, _initial(evidence['initial_native_evidence'], arguments), backend)
    _require(all(evidence.get(key) == value for key, value in summary.items()), 'controller summary differs from raw native events')
    return summary


def verify_controller_events_live(evidence, **arguments):
    validate_controller_events(evidence, **arguments)
    live = collect_controller_events(initial_evidence=Path(evidence['initial_native_evidence']['path']), **arguments)
    _require(live['events_sha256'] == evidence['events_sha256'], 'native job event history changed on live recheck')
    return live
