"""Synthetic allocation checks only; no scheduler or VASP operation."""
import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'archive/chco_paper_aqcat25_20261112/reduce_pending_static_memory.py'
spec = importlib.util.spec_from_file_location('pending_static_memory_tests', SOURCE)
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)
TARGET = '/home/sbq/sbq/MOCK/labels/MOCK_STATIC'
RECORD = {'job_id': '14307', 'remote_dir': TARGET}
ROW = (f'JobId=14307 JobState=PENDING Reason=Resources ExitCode=0:0 WorkDir={TARGET} Command={TARGET}/script.sbatch '
       'ReqNodeList=MZ73 TimeLimit=01:00:00 NumCPUs=4 NumTasks=1 CPUs/Task=4 TresPerNode=gres/gpu:1 Requeue=0 MinMemoryNode=16G')


def test_exact_pending_static_allocation_and_smaller_native_request():
    assert memory.validate_job(ROW, RECORD, memory_value='16G', pending=True)['job_state'] == 'PENDING'
    assert memory.validate_job(ROW.replace('16G', '15G'), RECORD, memory_value='15G', pending=False)['job_id'] == '14307'


@pytest.mark.parametrize('old,new', [('PENDING', 'RUNNING'), ('Reason=Resources', 'Reason=Dependency'),
    ('TimeLimit=01:00:00', 'TimeLimit=02:00:00'), ('NumCPUs=4', 'NumCPUs=8'), ('ReqNodeList=MZ73', 'ReqNodeList=OTHER'),
    ('Command=' + TARGET, 'Command=/foreign'), ('gres/gpu:1', 'gres/gpu:2')])
def test_foreign_or_changed_allocation_is_rejected(old, new):
    with pytest.raises(ValueError):
        memory.validate_job(ROW.replace(old, new), RECORD, memory_value='16G', pending=True)
