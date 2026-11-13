"""Native scheduler branch only; controller packet edge cases have owner tests."""
import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'archive/chco_paper_aqcat25_20261112/collect_training_native_exit.py'
spec = importlib.util.spec_from_file_location('training_native_exit_tests', SOURCE)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
TARGET = '/home/sbq/sbq/MOCK_CASE/training_r000_metadata_recovery01'
RECORD = {'job_id': '14292', 'remote_dir': TARGET}
ROW = f'JobId=14292 JobState=COMPLETED ExitCode=0:0 WorkDir={TARGET} Command={TARGET}/job.sh'


def test_native_success_remains_scheduler_evidence_only():
    result = native.verified_exit({'hostname': 'MZ73', 'job_query': {'returncode': 0, 'stdout': ROW}}, RECORD, {'node': 'MZ73'}, 'unused')
    assert result == {'result_class': 'native_scheduler_terminal_state_only',
                      'scheduler_terminal_state': 'COMPLETED', 'native_exit_code': '0:0'}


@pytest.mark.parametrize('old,new', [('COMPLETED', 'RUNNING'), ('COMPLETED', 'FAILED'), ('0:0', '1:0'),
    ('JobId=14292', 'JobId=99999'), ('WorkDir=' + TARGET, 'WorkDir=/foreign'),
    ('Command=' + TARGET, 'Command=/foreign')])
def test_nonterminal_failed_or_foreign_job_cannot_pass(old, new):
    with pytest.raises(ValueError):
        native.verified_exit({'hostname': 'MZ73', 'job_query': {'returncode': 0, 'stdout': ROW.replace(old, new)}}, RECORD, {'node': 'MZ73'}, 'unused')


def test_foreign_native_host_is_rejected():
    with pytest.raises(ValueError, match='another host'):
        native.verified_exit({'hostname': 'FOREIGN', 'job_query': {'returncode': 0, 'stdout': ROW}}, RECORD, {'node': 'MZ73'}, 'unused')
