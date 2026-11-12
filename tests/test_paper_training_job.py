"""Synthetic owner-accepted labels and mocked transport; no real case or jobs."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import write

from scripts.artifact_io import sha256_bytes, sha256_file, sha256_json

SOURCE = Path(__file__).resolve().parents[1] / 'archive/chco_paper_aqcat25_20261112/paper_training_job.py'
spec = importlib.util.spec_from_file_location('paper_training_job_tests', SOURCE)
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)


def save(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def args(tmp_path):
    case = tmp_path / 'MOCK_CASE'
    label_dir = case / 'labels' / job.budget_owner.TIMEOUT_LEAF
    label_dir.mkdir(parents=True)
    structure = label_dir / 'POSCAR'
    atoms = Atoms('Fe45C2OH', positions=np.arange(147).reshape(49, 3) / 100, cell=np.eye(3) * 20, pbc=True)
    atoms.set_constraint(FixAtoms(indices=range(18)))
    write(structure, atoms, format='vasp')
    caps = job.remote.load_mz73_static_backend(label_dir.name)['reviewed_contract']
    protocol = job.paper.create_protocol(initial_checkpoint_path='/home/sbq/sbq/MOCK_FROZEN.pt', initial_checkpoint_sha256=job.BASE,
        contract_sha256=caps['contract_sha256'], compatibility_sha256=caps['compatibility_sha256'], atom_count=49,
        movable_atom_indices=list(range(18, 49)), formed_bonds_1based=[[46, 47]], broken_bonds_1based=[], maximum_dft_evaluations=3,
        model_adaptation='MOCK AQCat25 model adaptation fixture', dft_adaptation='MOCK Fe110 DFT fixture')
    state = job.paper.prepare_dft_evaluation(job.paper.initialize_state(protocol), candidate_structure_sha256=sha256_file(structure), search_checkpoint_sha256=job.BASE)
    state = job.paper.record_execution(state, job_id='100000', bundle_sha256='a' * 64, gate_sha256='b' * 64)
    label = {'document_kind': 'vasp_ts_force_label', 'result_class': 'vasp_completed_electronic_converged_force_label_only',
             'normal_completion': True, 'electronically_converged': True, 'eligible_for_force_only_training': True,
             'reportable_final_energy': False, 'dft_toten_eV_force_label_only': -100.0,
             'contract_sha256': caps['contract_sha256'], 'compatibility_sha256': caps['compatibility_sha256'],
             'structure': {'sha256': sha256_file(structure)}, 'scheduler_evidence': {'job_id': '100000'},
             'paper_sequential_request_sha256': state['evaluations'][-1]['request_sha256'], 'geometry_sha256': 'c' * 64,
             'fixed_atom_indices_zero_based': list(range(18)), 'forces_eV_per_A': [[0.1, 0.0, 0.0]] * 49}
    raw = json.dumps(label).encode()
    state = job.paper.accept_force_label(state, raw, expected_sha256=sha256_bytes(raw))
    state_path, budget_path, reply = case / 'state.json', case / 'budget.json', case / 'MOCK_USER_REPLY.txt'
    save(state_path, state)
    reply.write_text('TEST FIXTURE ONLY: not a real authorization or scientific result')
    budget = {'document_kind': 'user_execution_budget_authorization', 'decision': 'approved_bounded_DFT_budget',
              'protocol_sha256': state['protocol_sha256'], 'failed_job_id': '13907', 'backend_id': job.remote.BACKEND_ID,
              'observed_hostname': 'MZ73', 'allowed_workdir_names': job.budget_owner.SCOPE['allowed_workdir_names'],
              'resources': copy.deepcopy(job.budget_owner.RESOURCES), 'limits': copy.deepcopy(job.budget_owner.LIMITS),
              'allow_cold_restart': True, 'automatic_retries': 0, 'training_time_limit': '00:10:00', 'source': job.ref(reply)}
    save(budget_path, budget)
    paper_request = copy.deepcopy(state['evaluations'][-1]['request'])
    paper_request['execution_budget_authorization'] = job.ref(budget_path)
    save(label_dir / job.remote.PAPER_REQUEST, paper_request)
    return SimpleNamespace(state=state_path, state_sha256=sha256_file(state_path), label_workdir=label_dir,
        budget=budget_path, budget_sha256=sha256_file(budget_path), structure=structure,
        template=SOURCE.parent / 'runtime_sources/force_only_config.yml', worker=SOURCE.with_name('train_latest_label.py'),
        config_path=job.remote.DEFAULT_CONFIG, job_dir=case / job.LEAF, remote_dir=None)


def prepared(args):
    result = job.prepare(args)
    return Path(result['path']), result['sha256']


def test_prepare_uses_real_owner_single_label_raw_and_canonical_hashes_without_execution(args, monkeypatch):
    monkeypatch.setattr(job, 'run', lambda *_: pytest.fail('prepare must not contact any remote service'))
    before = args.state.read_bytes()
    path, digest = prepared(args)
    manifest, checked = job.verify(path, digest)
    request = json.loads((path.parent / 'request.json').read_text())
    assert args.state.read_bytes() == before
    assert len(request['training_samples']) == 1 and request['training_samples'][0]['label']['structure']['sha256'] == sha256_file(args.structure)
    assert manifest['training_request_sha256'] == sha256_json(request)
    assert manifest['training_request_artifact_sha256'] == sha256_file(path.parent / 'request.json')
    assert manifest['training_request_sha256'] != manifest['training_request_artifact_sha256']
    assert checked['remote_dir'] == job.REMOTE_CASE + '/training_r000'
    assert not (args.state.parent / 'training_submission_attempt.json').exists()
    assert not (path.parent / 'output').exists()
    assert (path.parent / 'train_latest_label.py').read_bytes() == args.worker.read_bytes()


@pytest.mark.parametrize('phase', ['no_label', 'already_converged'])
def test_no_eligible_training_phase_cannot_prepare_or_create_jobdir(args, phase):
    state = json.loads(args.state.read_text())
    if phase == 'no_label':
        state = job.paper.initialize_state(state['protocol'])
    else:
        initial = job.paper.initialize_state(state['protocol'])
        initial = job.paper.prepare_dft_evaluation(initial, candidate_structure_sha256=sha256_file(args.structure), search_checkpoint_sha256=job.BASE)
        initial = job.paper.record_execution(initial, job_id='100001', bundle_sha256='a' * 64, gate_sha256='b' * 64)
        label = copy.deepcopy(state['latest_label']['label'])
        label.update(forces_eV_per_A=[[0.0, 0.0, 0.0]] * 49, scheduler_evidence={'job_id': '100001'})
        raw = json.dumps(label).encode()
        state = job.paper.accept_force_label(initial, raw, expected_sha256=sha256_bytes(raw))
    save(args.state, state)
    args.state_sha256 = sha256_file(args.state)
    with pytest.raises(ValueError, match='no training'):
        job.prepare(args)
    assert not args.job_dir.exists()


@pytest.mark.parametrize('change', ['budget_count', 'budget_epochs', 'training_time', 'raw_reply', 'wrong_protocol', 'worker', 'template', 'structure', 'other_remote', 'other_local'])
def test_prepare_rejects_unreviewed_inputs_and_budget_scope(args, tmp_path, change):
    budget = json.loads(args.budget.read_text())
    if change == 'budget_count':
        budget['limits']['max_training_jobs'] = 2
    elif change == 'budget_epochs':
        budget['limits']['training_epochs'] = 101
    elif change == 'training_time':
        budget['training_time_limit'] = '00:30:00'
    elif change == 'wrong_protocol':
        budget['protocol_sha256'] = 'f' * 64
    elif change == 'raw_reply':
        Path(budget['source']['path']).write_text('changed reply')
    elif change in ('worker', 'template'):
        fake = tmp_path / ('unreviewed.py' if change == 'worker' else 'unreviewed.yml')
        fake.write_text('not reviewed')
        setattr(args, change, fake)
    elif change == 'structure':
        args.structure.write_text('not the accepted structure')
    elif change == 'other_remote':
        args.remote_dir = '/home/sbq/sbq/other/training_r000'
    else:
        args.job_dir = tmp_path / 'other_training'
    if change in ('budget_count', 'budget_epochs', 'training_time', 'wrong_protocol'):
        save(args.budget, budget)
        args.budget_sha256 = sha256_file(args.budget)
        paper_path = args.label_workdir / job.remote.PAPER_REQUEST
        paper_request = json.loads(paper_path.read_text())
        paper_request['execution_budget_authorization'] = job.ref(args.budget)
        save(paper_path, paper_request)
    with pytest.raises(ValueError):
        job.prepare(args)
    assert not args.job_dir.exists()


def mock_transport(monkeypatch, args, *, final_stdout='24680\n', fail=None, mutate_after_upload=None):
    calls = []

    def run(argv):
        assert (args.state.parent / 'training_submission_attempt.json').is_file()
        calls.append(argv)
        if fail == 'remote_reservation' and len(calls) == 1:
            raise subprocess.CalledProcessError(1, argv)
        if argv[0] == 'scp' and mutate_after_upload:
            mutate_after_upload()
        if argv[0] == 'ssh' and 'sbatch --parsable' in argv[-1]:
            if fail == 'lost_receipt':
                raise subprocess.TimeoutExpired(argv, 30)
            return SimpleNamespace(stdout=final_stdout, stderr='')
        return SimpleNamespace(stdout='', stderr='')

    monkeypatch.setattr(job, 'run', run)
    return calls


def test_explicit_submit_uses_one_reservation_bounded_sbatch_and_no_duplicate(args, monkeypatch):
    path, digest = prepared(args)
    calls = mock_transport(monkeypatch, args)
    receipt = job.submit(path, digest)
    assert receipt['status'] == 'SUBMITTED' and receipt['job_id'] == '24680' and receipt['training_completed'] is False
    assert len(calls) == 3 and [call[0] for call in calls] == ['ssh', 'scp', 'ssh']
    assert 'mkdir ' + job.REMOTE_CASE + '/training_submission.reservation' in calls[0][-1]
    command = calls[-1][-1]
    for expected in ('--time=00:10:00', '--no-requeue', '--partition=gpu', '--nodelist=MZ73', '--gres=gpu:1', '--ntasks=1', '--cpus-per-task=4', '--mem=16G', 'test -x ' + job.PYTHON):
        assert expected in command
    assert command.count('sbatch --parsable') == 1 and 'new_trainer_context' in command
    assert 'manifest.json' in command and job.BASE in command
    with pytest.raises(ValueError, match='receipt'):
        job.submit(path, digest)
    assert len(calls) == 3


@pytest.mark.parametrize('failure', ['remote_reservation', 'lost_receipt', 'invalid_job_id'])
def test_uncertain_or_failed_submit_keeps_unknown_and_never_retries(args, monkeypatch, failure):
    path, digest = prepared(args)
    calls = mock_transport(monkeypatch, args, fail=failure, final_stdout='Submitted batch job 24680' if failure == 'invalid_job_id' else '24680\n')
    with pytest.raises((ValueError, subprocess.TimeoutExpired, subprocess.CalledProcessError)):
        job.submit(path, digest)
    assert json.loads((args.state.parent / 'training_submission_record.json').read_text())['status'] == 'UNKNOWN'
    assert (args.state.parent / 'training_submission_attempt.json').exists()
    count = len(calls)
    with pytest.raises(ValueError, match='receipt'):
        job.submit(path, digest)
    assert len(calls) == count


def test_orphan_attempt_blocks_without_transport_or_automatic_cleanup(args, monkeypatch):
    path, digest = prepared(args)
    (args.state.parent / 'training_submission_attempt.json').write_bytes(b'partial write')
    monkeypatch.setattr(job, 'run', lambda *_: pytest.fail('orphan reservation must block transport'))
    with pytest.raises(FileExistsError):
        job.submit(path, digest)
    assert (args.state.parent / 'training_submission_attempt.json').read_bytes() == b'partial write'


def test_copied_local_case_cannot_submit_again_past_same_remote_budget_reservation(args, monkeypatch):
    path, digest = prepared(args)
    second_case = args.state.parent.with_name('MOCK_CASE_COPY')
    shutil.copytree(args.state.parent, second_case, ignore=shutil.ignore_patterns(job.LEAF))
    second = copy.copy(args)
    second.state, second.budget = second_case / args.state.name, second_case / args.budget.name
    second.label_workdir = second_case / 'labels' / args.label_workdir.name
    second.structure, second.job_dir = second.label_workdir / 'POSCAR', second_case / job.LEAF
    paper_path = second.label_workdir / job.remote.PAPER_REQUEST
    paper_request = json.loads(paper_path.read_text())
    paper_request['execution_budget_authorization'] = job.ref(second.budget)
    save(paper_path, paper_request)
    second_path, second_digest = prepared(second)
    locks, submits = set(), []

    def transport(argv):
        if argv[0] == 'ssh' and 'mkdir ' + job.REMOTE_CASE + '/training_submission.reservation' in argv[-1]:
            lock = job.REMOTE_CASE + '/training_submission.reservation'
            if lock in locks:
                raise subprocess.CalledProcessError(1, argv)
            locks.add(lock)
        if argv[0] == 'ssh' and 'sbatch --parsable' in argv[-1]:
            submits.append(argv)
            return SimpleNamespace(stdout='24680\n', stderr='')
        return SimpleNamespace(stdout='', stderr='')

    monkeypatch.setattr(job, 'run', transport)
    job.submit(path, digest)
    with pytest.raises(subprocess.CalledProcessError):
        job.submit(second_path, second_digest)
    assert len(submits) == 1 and len(locks) == 1
    assert json.loads((second_case / 'training_submission_record.json').read_text())['status'] == 'UNKNOWN'


def test_another_backend_config_cannot_move_the_case_reservation(args, tmp_path):
    import yaml

    config = yaml.safe_load(Path(args.config_path).read_text())
    config['backends'][job.remote.BACKEND_ID]['remote_root'] = '/home/sbq/sbq/another_case/labels'
    replacement = tmp_path / 'different_backend.yaml'
    replacement.write_text(yaml.safe_dump(config))
    args.config_path = replacement
    with pytest.raises(ValueError, match='cannot move the sole case reservation'):
        job.prepare(args)
    assert not args.job_dir.exists()


@pytest.mark.parametrize('source', ['state', 'budget', 'reply', 'structure', 'request', 'launcher'])
def test_upload_time_source_change_is_rechecked_before_sbatch(args, monkeypatch, source):
    path, digest = prepared(args)
    files = {'state': args.state, 'budget': args.budget, 'reply': args.state.parent / 'MOCK_USER_REPLY.txt',
             'structure': args.structure, 'request': path.parent / 'request.json', 'launcher': path.parent / 'job.sh'}
    changed = files[source]
    calls = mock_transport(monkeypatch, args, mutate_after_upload=lambda: changed.write_bytes(changed.read_bytes() + b' '))
    with pytest.raises(ValueError):
        job.submit(path, digest)
    assert len(calls) == 2 and all('sbatch --parsable' not in call[-1] for call in calls)
    assert json.loads((args.state.parent / 'training_submission_record.json').read_text())['status'] == 'UNKNOWN'


def test_launcher_keeps_cache_tmp_separate_from_new_output_and_checks_frozen_worker(args):
    path, _ = prepared(args)
    script = (path.parent / 'job.sh').read_text()
    assert 'trap record_exit EXIT' in script and script.index('trap record_exit EXIT') < script.index('hostname -s')
    assert 'process_only_not_scheduler_or_training_completion' in script and job.WORKER in script
    assert 'TMPDIR=' + job.REMOTE_CASE + '/training_r000/tmp' in script
    assert 'mkdir -p -- "$TMPDIR"' in script and 'mkdir' not in next(line for line in script.splitlines() if line.startswith('test ! -e') and '/output' in line)
    assert '--output-root ' + job.REMOTE_CASE + '/training_r000/output' in script
    assert '--execute-authorized' in script and '--checkpoint' not in script and 'best_checkpoint' not in script


def test_prepare_does_not_overwrite_existing_training_directory(args):
    prepared(args)
    marker = args.job_dir / 'KEEP_USER_FILE'
    marker.write_text('keep')
    with pytest.raises(FileExistsError):
        job.prepare(args)
    assert marker.read_text() == 'keep'
