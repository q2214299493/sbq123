import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('candidate_return', Path(__file__).resolve().parents[1] /
                                            'archive/chco_paper_aqcat25_20261112/return_candidate.py')
returned = importlib.util.module_from_spec(spec)
spec.loader.exec_module(returned)


@pytest.mark.parametrize(('state', 'exit_code', 'passes'), [('RUNNING', '0:0', False), ('COMPLETED', '1:0', False),
                                                         ('COMPLETED', '0:0', True)])
def test_candidate_return_requires_native_success_not_only_a_zero_field(state, exit_code, passes):
    root = '/home/sbq/sbq/test-only'
    packet = {'hostname': 'MZ73', 'native_scontrol': {'returncode': 0,
              'stdout': f'JobId=123 JobState={state} ExitCode={exit_code} WorkDir={root} Command={root}/job.sh'}}
    record = {'job_id': '123', 'remote_dir': root}
    if passes:
        returned.validate_native(packet, record)
    else:
        with pytest.raises(ValueError):
            returned.validate_native(packet, record)


def test_another_native_directory_cannot_qualify_as_this_candidate():
    packet = {'hostname': 'MZ73', 'native_scontrol': {'returncode': 0,
              'stdout': 'JobId=123 JobState=COMPLETED ExitCode=0:0 WorkDir=/other Command=/other/job.sh'}}
    with pytest.raises(ValueError, match='identity'):
        returned.validate_native(packet, {'job_id': '123', 'remote_dir': '/home/sbq/sbq/test-only'})
