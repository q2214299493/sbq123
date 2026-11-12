"""Prepare one exact-input gate for the scoped CH+CO static label; no submission."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


def candidate_inputs(args, case, digest):
    """Require explicit reviewed continuation sources for the only next round."""
    if args.round not in (0, 1) or (args.launch_recovery and args.timebudget_restart):
        raise ValueError('only rounds zero/one and one recovery mode are supported')
    if (args.launch_recovery or args.timebudget_restart) and args.round != 0:
        raise ValueError('a restart belongs only to the unchanged first candidate')
    explicit = (args.search_binding, args.search_binding_sha256, args.candidate_review,
                args.geometry_evidence, args.review_image)
    if args.round == 1:
        if not all(explicit):
            raise ValueError('round one requires its new search binding, review, geometry evidence and image')
        request = args.search_binding.resolve(strict=True)
        if digest(request) != args.search_binding_sha256:
            raise ValueError('continuation binding raw bytes changed')
        return dict(search_request_path=request, search_request_sha256=args.search_binding_sha256,
                    review_path=args.candidate_review.resolve(strict=True),
                    geometry_evidence_path=args.geometry_evidence.resolve(strict=True),
                    review_image_path=args.review_image.resolve(strict=True))
    if any(explicit):
        raise ValueError('the first round keeps its original reviewed search sources')
    request = case / 'initial_search/request.json'
    return dict(search_request_path=request, search_request_sha256=digest(request),
                review_path=case / 'candidate_work_review.json', geometry_evidence_path=case / 'work_geometry_evidence.json',
                review_image_path=case / 'candidate_geometry_review.png')


def external_execution_source(args, label, backend):
    """Use the same actual raw user reply as the typed budget; never invent one."""
    from scripts.artifact_io import load_json_object, sha256_file
    from scripts.neb_agent.mz73_timebudget import require_budget_execution_source, validate_budget_authorization

    needed = args.round == 1 or args.timebudget_restart or backend.get('requires_budget_authorization')
    if not needed:
        if args.execution_source or args.execution_source_sha256:
            raise ValueError('external budget source is only accepted by the explicitly bounded new leaves')
        return None
    if not args.execution_source or not args.execution_source_sha256:
        raise ValueError('a new bounded job requires its actual external execution source and raw SHA')
    source = args.execution_source.resolve(strict=True)
    if sha256_file(source) != args.execution_source_sha256:
        raise ValueError('external execution source raw bytes changed')
    budget = validate_budget_authorization(label, load_json_object(label / 'paper_DFT_request.json'), backend)
    require_budget_execution_source({'path': str(source), 'sha256': args.execution_source_sha256}, budget)
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository-root', type=Path, required=True)
    parser.add_argument('--case-root', type=Path, required=True)
    parser.add_argument('--learning-database', type=Path, required=True)
    parser.add_argument('--round', type=int, default=0)
    parser.add_argument('--revision', type=int, default=1)
    parser.add_argument('--launch-recovery', action='store_true',
                        help='use the single explicitly reviewed r000 MPI launch-recovery directory')
    parser.add_argument('--timebudget-restart', action='store_true', help='use only the fixed r000 TIMEOUT cold-restart leaf')
    parser.add_argument('--search-binding', type=Path)
    parser.add_argument('--search-binding-sha256')
    parser.add_argument('--candidate-review', type=Path)
    parser.add_argument('--geometry-evidence', type=Path)
    parser.add_argument('--review-image', type=Path)
    parser.add_argument('--execution-source', type=Path)
    parser.add_argument('--execution-source-sha256')
    args = parser.parse_args()
    repository = args.repository_root.resolve(strict=True)
    sys.path.insert(0, str(repository))
    import yaml
    from scripts.artifact_io import sha256_file, write_json
    from scripts.neb_agent import mz73_static, submission
    from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
    from scripts.ts_strategy_engine.execution_gate import decide_execution
    from scripts.ts_strategy_engine.execution_gate_cli import build_decision

    case = args.case_root.resolve(strict=True)
    label = case / 'labels' / f'paper_chco_aqcat25_ft512_20261112_r{args.round:03d}_label'
    if args.launch_recovery:
        label = case / 'labels/paper_chco_aqcat25_ft512_20261112_r000_launch_recovery01_label'
    if args.timebudget_restart:
        label = case / 'labels/paper_chco_aqcat25_ft512_20261112_r000_timebudget_restart01_label'
    inputs = candidate_inputs(args, case, sha256_file)
    backend = mz73_static.load_mz73_static_backend(label.name)
    source = external_execution_source(args, label, backend)
    if args.revision < 1:
        raise ValueError('binding revision must be positive')
    suffix = '' if args.revision == 1 else f'.binding_v{args.revision}'
    def artifact(stem, extension='json'):
        return label / f'{stem}{suffix}.{extension}'
    if any((label / name).exists() for name in ('submission_record.json', 'submission_attempt.json')) or artifact('submission_decision').exists():
        raise FileExistsError('an execution or decision already exists; inspect before generating another binding')
    geometry = mz73_static.diagnose_static_candidate_geometry(
        label, initial_structure_path=case / 'initial_search/IS.vasp',
        contract_path=case.parent / 'review_ready_v2/reaction_contract.json',
        **inputs,
    )
    analysis = mz73_static.analyze_static_candidate_outputs(label)
    if geometry['status'] != 'PASS' or analysis['status'] != 'NO_OUTPUT':
        raise ValueError('actual static input geometry or output-presence review did not pass')
    write_json(artifact('static_candidate_geometry'), geometry)
    write_json(artifact('static_output_presence'), analysis)
    rendered = mz73_static.render_launcher(backend).encode('ascii')
    launcher = label / mz73_static.LAUNCHER
    if launcher.exists() and launcher.read_bytes() != rendered:
        raise ValueError('existing launcher differs from reviewed scoped template')
    if not launcher.exists():
        with launcher.open('xb') as handle:
            handle.write(rendered)
    previous = label / f'submission_preflight.before_binding_v{args.revision}.json'
    if (label / 'submission_preflight.json').exists() and not previous.exists():
        previous.write_bytes((label / 'submission_preflight.json').read_bytes())
    report = submission.preflight(label, 'diagnostic_static', host=mz73_static.BACKEND_ID,
                                  learning_database=args.learning_database.resolve(strict=True))
    if not report['passed']:
        raise ValueError('canonical preflight failed: ' + repr(report['errors']))
    paths = {
        'geometry': artifact('static_candidate_geometry'),
        'analysis': artifact('static_output_presence'),
        'thresholds': repository / 'configs/neb_agent/default_thresholds.yaml',
        'preflight': label / 'submission_preflight.json',
    }
    thresholds = yaml.safe_load(paths['thresholds'].read_text(encoding='utf-8'))
    bindings = {name: {'path': str(path), 'sha256': sha256_file(path)} for name, path in paths.items()}
    base = decide_execution(geometry, analysis, thresholds, climb=False, path_reviewed=True,
                            preflight=report, source_bindings=bindings)
    if source is None:
        source = artifact('user_request_scope', 'txt')
        source.write_text(
        'Original user request: 我现在要测试一下进行文献这个流程 这个完全采用文献的方法去执行 完全使用在GPUvasp上的这个服务器\n'
        'User identified the server as BUCT / MZ73.\n'
        'User DFT choice: 沿用项目已验证的 Fe(110) VASP 设置，按论文执行 eSEN+BA-Sella 主动学习流程\n'
        'User then corrected the model choice: 势函数模型使用我自己已有的\n'
        'Final model choice: 使用已有 AQCat25 微调检查点\n'
        'Agent instantiation of this test: one exact-structure static DFT force label for the reviewed '
        'AQCat25 FT512 CH+CO candidate, on MZ73 GPU VASP; no ionic optimization.\n'
        'Agent-imposed conservative per-job ceiling: 1 MPI rank, 1 GPU, 4 CPU, 16 GB, 30 minutes, no requeue/retry. '
        'The user did not specify an open-ended total compute budget. The protocol 250-label ceiling is not '
        'permission to submit 250 jobs. This binding covers this one prepared label only.\n', encoding='utf-8')
    if args.launch_recovery:
        with source.open('a', encoding='utf-8') as handle:
            handle.write(
                'This is one explicitly reviewed infrastructure launch recovery for job 13901, '
                'which failed before VASP started (Open MPI hwloc_set_cpubind). '
                'The original candidate and scientific inputs are unchanged; the new launcher uses '
                'mpirun --bind-to none, independently tested in controlled probe job 13902. '
                'The original directory/reservation remains frozen; this new directory requires '
                'the source-bound launch_recovery.json and this fresh gate. '
                'This is not permission for general retry or another scientific round.\n')
    target = {'server_alias': mz73_static.BACKEND_ID, 'remote_dir': backend['remote_root'] + '/' + label.name}
    authorization = {
        'schema_version': 1, 'document_kind': 'user_execution_authorization',
        'action': 'SUBMIT_DIAGNOSTIC_VASP', 'calculation_kind': 'diagnostic_static',
        'authorized_at': datetime.now(timezone.utc).isoformat(),
        'source': {'path': str(source), 'sha256': sha256_file(source)}, 'target': target,
        'workdir_identity': workdir_identity(label), 'bundle_sha256': report['bundle_sha256'],
        'evidence_sha256': execution_evidence_sha256(base['EVIDENCE']),
        'potcar': {'source': '/home/sbq/sbq/chco_paper_aqcat25_ft512_20261112_v1/private/POTCAR',
                   'sha256': 'e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85',
                   'spec_sha256': report['files']['POTCAR.spec']},
    }
    auth_path = artifact('user_execution_authorization')
    write_json(auth_path, authorization)
    request = {name + '_file': str(path) for name, path in paths.items()}
    request.update(climb=False, path_reviewed=True, authorization_file=str(auth_path))
    request_path = artifact('execution_gate_request')
    write_json(request_path, request)
    decision = build_decision(request_path, artifact('submission_decision'))
    if decision['ALLOWED_ACTIONS'] != ['SUBMIT_DIAGNOSTIC_VASP']:
        raise ValueError('gate did not authorize the one static job: ' + str(decision.get('execution_authorization_error')))
    print(json.dumps({'geometry': geometry['status'], 'analysis': analysis['status'],
                      'preflight': report['passed'], 'decision': decision['DECISION'],
                      'allowed_actions': decision['ALLOWED_ACTIONS'], 'bundle_sha256': report['bundle_sha256'],
                      'decision_path': str(artifact('submission_decision')),
                      'decision_sha256': sha256_file(artifact('submission_decision'))}))


if __name__ == '__main__':
    main()
