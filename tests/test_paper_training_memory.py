"""Synthetic native records only; never contact Slurm."""
import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'archive/chco_paper_aqcat25_20261112/reduce_pending_training_memory.py'
spec = importlib.util.spec_from_file_location('paper_training_memory_tests', SOURCE)
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)
TARGET = '/home/sbq/sbq/MOCK_CASE/training_r000'
RECORD = {'job_id': '14279', 'remote_dir': TARGET}
NATIVE = (f'JobId=14279 JobState=PENDING Reason=Resources ExitCode=0:0 WorkDir={TARGET} Command={TARGET}/job.sh '
          'ReqNodeList=MZ73 TimeLimit=00:10:00 NumCPUs=4 NumTasks=1 CPUs/Task=4 '
          'TresPerNode=gres/gpu:1 Requeue=0 MinMemoryNode=16G\n')


def test_exact_pending_request_then_actual_15GiB_record():
    assert memory.validate_job(NATIVE, RECORD, pending=True, memory='16G')['job_state'] == 'PENDING'
    changed = NATIVE.replace('MinMemoryNode=16G', 'MinMemoryNode=15G').replace('JobState=PENDING', 'JobState=RUNNING')
    assert memory.validate_job(changed, RECORD, pending=False, memory='15G')['job_state'] == 'RUNNING'


@pytest.mark.parametrize('old,new', [('JobState=PENDING', 'JobState=RUNNING'), ('Reason=Resources', 'Reason=Dependency'),
    ('MinMemoryNode=16G', 'MinMemoryNode=32G'), ('ReqNodeList=MZ73', 'ReqNodeList=FOREIGN'),
    ('TimeLimit=00:10:00', 'TimeLimit=01:00:00'), ('NumCPUs=4', 'NumCPUs=8'), ('Requeue=0', 'Requeue=1'),
    ('TresPerNode=gres/gpu:1', 'TresPerNode=gres/gpu:2'), ('Command=' + TARGET, 'Command=/foreign'),
    ('JobId=14279', 'JobId=99999')])
def test_scope_drift_cannot_be_amended(old, new):
    with pytest.raises(ValueError):
        memory.validate_job(NATIVE.replace(old, new), RECORD, pending=True, memory='16G')


def test_duplicate_native_field_is_rejected():
    with pytest.raises(ValueError, match='ambiguous'):
        memory.validate_job(NATIVE.strip() + ' MinMemoryNode=16G', RECORD, pending=True, memory='16G')
