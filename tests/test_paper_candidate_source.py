"""Local mock receipts and ASE structures only; no weights, GPU or real round one."""
from __future__ import annotations

import base64
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import read, write

from scripts.artifact_io import sha256_bytes, sha256_file
from scripts.neb_agent import mz73_timebudget, paper_candidate_source as owner
from scripts.neb_agent import mz73_static as static
from tests import test_mz73_static_geometry as static_tests


PREPARE = Path(__file__).resolve().parents[1] / 'archive/chco_paper_aqcat25_20261112/prepare_gate.py'
spec = importlib.util.spec_from_file_location('paper_gate_source_tests', PREPARE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.fixture
def chain(tmp_path):
    mapping = {}

    def reference(name):
        path = tmp_path / name
        remote = '/MOCK_GPU/' + name
        digest = sha256_file(path)
        mapping[remote] = {'source_path': remote, 'path': str(path), 'sha256': digest}
        return {'path': remote, 'sha256': digest}

    def document(name, payload):
        (tmp_path / name).write_text(json.dumps(payload), encoding='utf-8')
        return reference(name)

    def local_ref(name):
        return {'path': name, 'sha256': sha256_file(tmp_path / name)}

    initial = Atoms('Fe45C2OH', positions=np.arange(147).reshape(49, 3) / 100, cell=np.eye(3) * 20, pbc=True)
    initial.set_constraint(FixAtoms(indices=range(18)))
    previous = initial.copy()
    previous.positions[45:, 0] += 0.1
    previous.info.update(mode_TS=np.zeros((49, 3)), bonds_TS=[[45, 46, 'form']])
    previous.info['mode_TS'][45, 0] = 1.0
    write(tmp_path / 'IS.vasp', initial, format='vasp')
    write(tmp_path / 'previous.vasp', previous, format='vasp')
    write(tmp_path / 'previous.traj', previous, format='traj')
    candidate = previous.copy()
    candidate.positions[45, 0] += 0.01
    write(tmp_path / 'candidate.vasp', candidate, format='vasp')
    contract = {'contract_sha256': 'a' * 64, 'compatibility_sha256': 'b' * 64, 'atom_map_sha256': 'd' * 64,
                'compatibility': {'fixed_atom_indices_zero_based': list(range(18))}}
    rules = [{'name': 'CH', 'atoms_zero_based': [45, 48], 'minimum_A': 0.9, 'maximum_A': 1.2,
              'hard_minimum_A': 0.7, 'hard_maximum_A': 1.5}]
    guard = document('guards.json', {'geometry_guards': {'minimum_pair_distance_A': 0.7, 'preserved_bonds': rules}})
    original = {'checkpoint': {'path': '/MOCK_GPU/base.pt', 'sha256': owner.FROZEN_BASE}, 'initial': reference('IS.vasp'),
                'fixed_indices_zero_based': list(range(18)), 'reaction': {**{key: contract[key] for key in contract if key != 'compatibility'},
                    'bonds': [[45, 46, 'form']], 'adsorbate_indices': [45, 46, 47, 48]}, 'geometry_guard_source': guard,
                'geometry': {'minimum_pair_distance_A': 0.7, 'preserved_bonds': [{'name': 'CH', 'atoms': [45, 48],
                    'minimum_A': 0.7, 'maximum_A': 1.5, 'soft_minimum_A': 0.9, 'soft_maximum_A': 1.2}]}}
    label = {'structure': {'sha256': reference('previous.vasp')['sha256']}, 'forces_eV_per_A': [[0.1, 0.0, 0.0]] * 49}
    raw = json.dumps(label).encode()
    training = {'document_kind': 'paper_sequential_training_request', 'protocol_sha256': 'c' * 64,
                'base_checkpoint': original['checkpoint'], 'checkpoint_selection': 'final_epoch_only',
                **{key: True for key in ('reset_model_weights', 'reset_optimizer_state', 'reset_scheduler_state', 'reset_amp_state', 'reset_ema_state')},
                'training': {'target': 'forces_only', 'epochs': 100, 'energy_loss_coefficient': 0.0,
                    'initial_learning_rate': 1e-4, 'scheduler': 'cosine', 'train_on_all': False,
                    'train_finetuned': False, 'replay': False, 'validation_epoch_selection': False},
                'training_samples': [{'label': label, 'artifact_sha256': sha256_bytes(raw), 'raw_label_base64': base64.b64encode(raw).decode()}]}
    checkpoint = {'path': '/MOCK_GPU/new_checkpoint.pt', 'sha256': 'e' * 64}  # Deliberately absent locally.
    result = {'document_kind': 'aqcat25_paper_single_label_training_result', 'status': 'completed_candidate_only',
              'protocol_sha256': 'c' * 64, 'base_checkpoint_sha256': owner.FROZEN_BASE, 'checkpoint': checkpoint,
              'production_checkpoint_promotion': False, 'scientific_acceptance': False,
              'training_evidence': {'completed_epochs': 100.0, 'completed_steps': 100, 'observed_optimizer_updates': 100,
                                   'optimizer_update_events': [{'step': i, 'epoch': float(i)} for i in range(1, 101)]}}
    sources = []
    for name in ('next_candidate.py', 'initial_candidate.py', 'aqcat_ts_pilot.py', 'mlip_same_structure_benchmark.py', 'artifact_io.py', 'calculations.py'):
        (tmp_path / name).write_text('# MOCK SOURCE; never imported\n')
        sources.append(reference(name))

    def seal(*, result_change=None, request_change=None, report_change=None, binding_change=None):
        original_ref, training_ref = document('initial.json', original), document('training.json', training)
        receipt = copy.deepcopy(result)
        receipt['training_request_artifact_sha256'] = training_ref['sha256']
        if result_change:
            result_change(receipt)
        request = {'document_kind': 'paper_sequential_candidate_continuation_request', 'protocol_sha256': 'c' * 64,
                   'initial_request': original_ref, 'training_request': training_ref, 'training_result': document('result.json', receipt),
                   'checkpoint': checkpoint, 'previous_candidate': reference('previous.vasp'), 'previous_trajectory': reference('previous.traj'), 'source_files': sources}
        if request_change:
            request_change(request)
        document('request.json', request)
        report = {'protocol_sha256': 'c' * 64, 'request_sha256': sha256_file(tmp_path / 'request.json'),
                  'status': 'prediction_completed_pending_review', 'result_class': 'predicted_candidate_only',
                  **{key: False for key in ('DFT_performed', 'training_performed', 'scientifically_accepted', 'IDPP_performed')},
                  'geometry_initialization': 'previous_trajectory_last_frame', 'previous_mode_retained': True,
                  'optimizer_converged': True, 'optimizer_status': 'finished', 'calculator_failure': None,
                  'cuda': {'available': True, 'device_count': 1}, 'model_devices': ['cuda:0'],
                  'predicted_movable_fmax_eV_per_A': 0.009, 'fixed_indices_zero_based': list(range(18)),
                  'ba_sella': {'fmax': 0.01, 'min_steps': 10, 'max_steps': 1000, 'eta': 0.01,
                               'gamma': 0.05, 'delta0': 0.05, 'dot_prod_thr': 0.5, 'nsteps_per_diag': 1},
                  'input_bindings': {key: request[key] for key in ('initial_request', 'training_request', 'training_result', 'checkpoint', 'previous_candidate', 'previous_trajectory')},
                  'output_candidate': {'path': '/MOCK_GPU/output/predicted_candidate.vasp', 'sha256': sha256_file(tmp_path / 'candidate.vasp')},
                  'source_files': sources}
        if report_change:
            report_change(report)
        document('report.json', report)
        binding = {'document_kind': owner.BINDING_KIND, 'protocol_sha256': 'c' * 64,
                   'continuation_request': local_ref('request.json'), 'continuation_report': local_ref('report.json'),
                   'candidate': local_ref('candidate.vasp'), 'source_map': list(mapping.values())}
        if binding_change:
            binding_change(binding)
        document('binding.json', binding)
        return dict(binding_path=tmp_path / 'binding.json', binding_sha256=sha256_file(tmp_path / 'binding.json'),
                    candidate_path=tmp_path / 'candidate.vasp', initial_structure_path=tmp_path / 'IS.vasp',
                    expected_protocol_sha256='c' * 64, contract=contract)

    return SimpleNamespace(root=tmp_path, original=original, training=training, result=result, seal=seal, reference=reference)


def test_remote_raw_sources_map_to_local_without_weights_or_request_rewrite(chain):
    args = chain.seal()
    before = {path: path.read_bytes() for path in chain.root.iterdir()}
    resolved = owner.resolve_continuation_source(**args)
    view = resolved['effective_request']
    assert view['checkpoint']['sha256'] == 'e' * 64
    assert view['reaction'] == chain.original['reaction'] and view['geometry'] == chain.original['geometry']
    assert view['initial']['sha256'] == chain.original['initial']['sha256']
    assert not Path(view['checkpoint']['path']).exists()
    assert resolved['source_binding']['submission_allowed'] is False
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert {chain.root / name for name in ('training.json', 'result.json', 'request.json', 'report.json', 'previous.traj')} <= set(resolved['dependency_paths'])


def test_resealed_candidate_cannot_borrow_unchanged_worker_report(chain):
    args = chain.seal()
    report, request = chain.root / 'report.json', chain.root / 'request.json'
    originals = (report.read_bytes(), request.read_bytes())
    replacement = read(args['candidate_path'], format='vasp')
    replacement.positions[45, 0] += 0.01  # Still a finite, same-order/fixed-mask candidate.
    write(args['candidate_path'], replacement, format='vasp')
    binding = json.loads(args['binding_path'].read_text())
    binding['candidate']['sha256'] = sha256_file(args['candidate_path'])
    args['binding_path'].write_text(json.dumps(binding))
    args['binding_sha256'] = sha256_file(args['binding_path'])
    assert originals == (report.read_bytes(), request.read_bytes())
    with pytest.raises(ValueError, match='worker report output and returned candidate differ'):
        owner.resolve_continuation_source(**args)


@pytest.mark.parametrize('change', ['missing', 'wrong_sha', 'missing_path'])
def test_worker_report_requires_actual_output_descriptor(chain, change):
    def mutate(report):
        if change == 'missing':
            report.pop('output_candidate')
        elif change == 'wrong_sha':
            report['output_candidate']['sha256'] = '0' * 64
        else:
            report['output_candidate'].pop('path')
    with pytest.raises(ValueError, match='worker report output and returned candidate differ'):
        owner.resolve_continuation_source(**chain.seal(report_change=mutate))


@pytest.mark.parametrize('change', ['base', 'epochs', 'updates', 'events', 'raw_request', 'checkpoint', 'acceptance'])
def test_resealed_bad_training_receipt_is_rejected(chain, change):
    def mutate(result):
        if change == 'base':
            result['base_checkpoint_sha256'] = '0' * 64
        elif change in ('epochs', 'updates'):
            result['training_evidence']['completed_epochs' if change == 'epochs' else 'observed_optimizer_updates'] = 99
        elif change == 'events':
            result['training_evidence']['optimizer_update_events'].pop()
        elif change == 'raw_request':
            result['training_request_artifact_sha256'] = '0' * 64
        elif change == 'checkpoint':
            result['checkpoint']['path'] = '/MOCK_GPU/other.pt'
        else:
            result['scientific_acceptance'] = True
    with pytest.raises(ValueError):
        owner.resolve_continuation_source(**chain.seal(result_change=mutate))


@pytest.mark.parametrize('change', ['latest_label', 'raw_label', 'reset', 'replay', 'best_epoch', 'learning_rate', 'guards', 'contract'])
def test_resealed_request_cannot_replace_latest_label_or_original_controls(chain, change):
    if change == 'latest_label':
        label = chain.training['training_samples'][0]['label']
        label['structure']['sha256'] = 'f' * 64
        raw = json.dumps(label).encode()
        chain.training['training_samples'][0].update(raw_label_base64=base64.b64encode(raw).decode(), artifact_sha256=sha256_bytes(raw))
    elif change == 'raw_label':
        chain.training['training_samples'][0]['raw_label_base64'] = base64.b64encode(b'{}').decode()
    elif change == 'reset':
        chain.training['reset_optimizer_state'] = False
    elif change == 'replay':
        chain.training['training']['replay'] = True
    elif change == 'best_epoch':
        chain.training['checkpoint_selection'] = 'best'
    elif change == 'learning_rate':
        chain.training['training']['initial_learning_rate'] = 1e-2
    elif change == 'guards':
        chain.original['geometry']['minimum_pair_distance_A'] = 0.1
    else:
        chain.original['reaction']['contract_sha256'] = '0' * 64
    with pytest.raises(ValueError):
        owner.resolve_continuation_source(**chain.seal())


@pytest.mark.parametrize('change', ['position', 'mode', 'SD', 'bonds'])
def test_previous_frame_must_match_previous_poscar_with_usable_mode(chain, change):
    frame = read(chain.root / 'previous.traj', format='traj')
    if change == 'position':
        frame.positions[45, 0] += 1e-4
    elif change == 'mode':
        frame.info['mode_TS'][0, 0] = 1.0
    elif change == 'SD':
        frame.set_constraint(FixAtoms(indices=range(17)))
    else:
        frame.info['bonds_TS'] = [[45, 47, 'form']]
    write(chain.root / 'previous.traj', frame, format='traj')
    with pytest.raises(ValueError):
        owner.resolve_continuation_source(**chain.seal())


@pytest.mark.parametrize('change', ['report_hash', 'report_IDPP', 'report_cpu', 'report_force', 'missing_map', 'duplicate_map', 'candidate', 'code_bytes'])
def test_bound_source_or_worker_result_cannot_drift(chain, change):
    report_change = {'report_IDPP': lambda row: row.update(IDPP_performed=True),
                     'report_cpu': lambda row: row.update(model_devices=['cpu']),
                     'report_force': lambda row: row.update(predicted_movable_fmax_eV_per_A=0.02)}.get(change)
    binding_change = {'missing_map': lambda row: row['source_map'].pop(0),
                      'duplicate_map': lambda row: row['source_map'].append(row['source_map'][0])}.get(change)
    args = chain.seal(report_change=report_change, binding_change=binding_change)
    if change == 'report_hash':
        (chain.root / 'report.json').write_text('{}')
    elif change == 'candidate':
        (chain.root / 'candidate.vasp').write_bytes(b'MOCK CHANGED CANDIDATE')
    elif change == 'code_bytes':
        (chain.root / 'next_candidate.py').write_text('# changed')
    with pytest.raises(ValueError):
        owner.resolve_continuation_source(**args)


def gate_args(**updates):
    result = dict(round=0, launch_recovery=False, timebudget_restart=False, search_binding=None,
                  search_binding_sha256=None, candidate_review=None, geometry_evidence=None, review_image=None,
                  execution_source=None, execution_source_sha256=None)
    return SimpleNamespace(**{**result, **updates})


@pytest.mark.parametrize('round_index', [1, 2, 249])
def test_continuation_does_not_default_to_round_zero_review(chain, round_index):
    with pytest.raises(ValueError, match='continuation requires'):
        gate.candidate_inputs(gate_args(round=round_index), chain.root, sha256_file)
    inputs = gate.candidate_inputs(gate_args(round=round_index, search_binding=chain.root / 'binding.json',
        search_binding_sha256=chain.seal()['binding_sha256'], candidate_review=chain.root / 'report.json',
        geometry_evidence=chain.root / 'result.json', review_image=chain.root / 'candidate.vasp'), chain.root, sha256_file)
    assert inputs['search_request_path'] == chain.root / 'binding.json'


@pytest.mark.parametrize('updates', [{'round': 250}, {'round': 1, 'launch_recovery': True},
                                    {'launch_recovery': True, 'timebudget_restart': True}, {'round': 1, 'timebudget_restart': True}])
def test_unsupported_round_or_recovery_combination_refuses(chain, updates):
    with pytest.raises(ValueError):
        gate.candidate_inputs(gate_args(**updates), chain.root, sha256_file)


@pytest.mark.parametrize('new_leaf', ['next', 'timeout', 'continuous'])
def test_new_leaves_require_same_actual_external_budget_reply(chain, monkeypatch, new_leaf):
    label = chain.root
    (label / 'paper_DFT_request.json').write_text('{}')
    reply, unrelated = label / 'actual_user_reply.txt', label / 'unrelated.txt'
    reply.write_text('MOCK USER BUDGET FIXTURE; not authorization for a real job')
    unrelated.write_bytes(reply.read_bytes())  # Same text/hash is insufficient when another artifact is named.
    monkeypatch.setattr(mz73_timebudget, 'validate_budget_authorization', lambda *args: {
        'source': {'path': str(reply), 'sha256': sha256_file(reply)}})
    from scripts.neb_agent import mz73_continuation

    monkeypatch.setattr(mz73_continuation, 'validate_request', lambda *args: {
        'source': {'path': str(reply), 'sha256': sha256_file(reply)}})
    args = gate_args(round=2 if new_leaf == 'continuous' else int(new_leaf == 'next'), timebudget_restart=new_leaf == 'timeout')
    backend = {'requires_continuation_authorization': True} if new_leaf == 'continuous' else {'requires_budget_authorization': True}
    with pytest.raises(ValueError, match='actual external execution source'):
        gate.external_execution_source(args, label, backend)
    args.execution_source, args.execution_source_sha256 = unrelated, sha256_file(unrelated)
    with pytest.raises(ValueError, match='actual new budget reply source'):
        gate.external_execution_source(args, label, backend)
    args.execution_source = reply
    assert gate.external_execution_source(args, label, backend) == reply


def test_old_first_round_keeps_original_scope_without_new_budget(chain):
    assert gate.external_execution_source(gate_args(), chain.root, {}) is None


@pytest.fixture
def continuation_static(chain, tmp_path, monkeypatch):
    scope = static_tests.scope.__wrapped__(tmp_path, monkeypatch)
    old = scope['workdir']
    new = old.with_name(mz73_timebudget.NEXT_LEAF)
    old.rename(new)
    scope['workdir'] = scope['arguments']['workdir'] = new
    for name, source in [('IS.vasp', scope['arguments']['initial_structure_path']), ('previous.vasp', new / 'POSCAR'),
                         ('candidate.vasp', new / 'POSCAR'), ('guards.json', Path(scope['request']['geometry_guard_source']['path']))]:
        (chain.root / name).write_bytes(source.read_bytes())
    frame = read(chain.root / 'previous.vasp', format='vasp')
    frame.info.update(mode_TS=np.zeros((49, 3)), bonds_TS=[[45, 46, 'form']])
    frame.info['mode_TS'][45, 0] = 1.0
    write(chain.root / 'previous.traj', frame, format='traj')
    chain.original.clear()
    chain.original.update(copy.deepcopy(scope['request']))
    chain.original.update(checkpoint=copy.deepcopy(chain.training['base_checkpoint']),
                          initial=chain.reference('IS.vasp'), geometry_guard_source=chain.reference('guards.json'))
    sample = chain.training['training_samples'][0]
    sample['label']['structure']['sha256'] = sha256_file(chain.root / 'previous.vasp')
    raw = json.dumps(sample['label']).encode()
    sample.update(raw_label_base64=base64.b64encode(raw).decode(), artifact_sha256=sha256_bytes(raw))
    bound = chain.seal()
    scope['arguments'].update(search_request_path=bound['binding_path'], search_request_sha256=bound['binding_sha256'])
    scope['paper'].update(protocol_sha256='c' * 64, search_checkpoint_sha256='e' * 64, evaluation_index=1)
    reply = chain.root / 'TEST_ONLY_USER_REPLY.txt'
    reply.write_text('MOCK authorization fixture only; no real scientific computation authorized')
    budget = {'document_kind': 'user_execution_budget_authorization', 'decision': 'approved_bounded_DFT_budget',
              'protocol_sha256': 'c' * 64, 'failed_job_id': '13907', 'backend_id': static.BACKEND_ID, 'observed_hostname': 'MZ73',
              'allowed_workdir_names': mz73_timebudget.SCOPE['allowed_workdir_names'], 'resources': mz73_timebudget.RESOURCES,
              'limits': mz73_timebudget.LIMITS, 'allow_cold_restart': True, 'automatic_retries': 0,
              'source': {'path': str(reply), 'sha256': sha256_file(reply)}}
    budget_path = chain.root / 'TEST_ONLY_BUDGET.json'
    budget_path.write_text(json.dumps(budget))
    scope['paper']['execution_budget_authorization'] = {'path': str(budget_path), 'sha256': sha256_file(budget_path)}
    (new / static.PAPER_REQUEST).write_text(json.dumps(scope['paper']))
    return scope


def test_static_owner_recomputes_continuation_and_binds_all_local_dependencies(continuation_static, chain):
    scope = continuation_static
    geometry = static.diagnose_static_candidate_geometry(**scope['arguments'])
    assert geometry['status'] == 'PASS' and geometry['hard_errors'] == []
    assert geometry['continuation_source_binding']['checkpoint_sha256'] == 'e' * 64
    sources = {Path(row['path']) for row in geometry['source_files']}
    assert {chain.root / name for name in ('training.json', 'result.json', 'previous.traj', 'request.json', 'report.json')} <= sources
    assert Path(owner.__file__).resolve() in sources
    preflight = static_tests.minimal_preflight(scope)
    assert static.validate_static_evidence(geometry, preflight, name='geometry')
    (chain.root / 'result.json').write_text('{}')
    assert not static.validate_static_evidence(geometry, preflight, name='geometry')


def test_next_round_static_owner_refuses_original_request_fallback(continuation_static, chain):
    scope = continuation_static
    original = chain.root / 'initial.json'
    scope['arguments'].update(search_request_path=original, search_request_sha256=sha256_file(original))
    with pytest.raises(ValueError, match='explicit continuation source binding'):
        static.diagnose_static_candidate_geometry(**scope['arguments'])


def test_r002_static_owner_keeps_the_continuation_source_gate(continuation_static, chain, monkeypatch):
    scope = continuation_static
    old = scope['workdir']
    new = old.with_name('paper_chco_aqcat25_ft512_20261112_r002_label')
    old.rename(new)
    scope['arguments']['workdir'] = new
    # This test isolates source selection; real continuation approval/state
    # validation is covered by its own owner tests and real case preflight.
    monkeypatch.setattr(static, 'validate_paper_dft_request', lambda *args, **kwargs: scope['paper'])
    geometry = static.diagnose_static_candidate_geometry(**scope['arguments'])
    assert geometry['status'] == 'PASS' and 'continuation_source_binding' in geometry
    scope['arguments'].update(search_request_path=chain.root / 'initial.json',
                              search_request_sha256=sha256_file(chain.root / 'initial.json'))
    with pytest.raises(ValueError, match='explicit continuation source binding'):
        static.diagnose_static_candidate_geometry(**scope['arguments'])


def test_static_owner_rejects_new_candidate_bound_to_previous_checkpoint(continuation_static):
    scope = continuation_static
    scope['paper']['search_checkpoint_sha256'] = owner.FROZEN_BASE
    (scope['workdir'] / static.PAPER_REQUEST).write_text(json.dumps(scope['paper']))
    with pytest.raises(ValueError, match='another ML checkpoint'):
        static.diagnose_static_candidate_geometry(**scope['arguments'])


def test_first_round_static_owner_cannot_consume_continuation_binding(chain, monkeypatch):
    bound = chain.seal()
    monkeypatch.setattr(static, '_load_reviewed_contract', lambda *args: {})
    with pytest.raises(ValueError, match='original first-round request'):
        static._bound_search_inputs(bound['initial_structure_path'], bound['binding_path'], bound['binding_sha256'],
                                    chain.root / 'unused_contract', {})
