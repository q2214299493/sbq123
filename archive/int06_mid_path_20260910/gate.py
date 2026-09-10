"""Bind current prepared inputs to the execution gate, without authorization."""
from archive.int06_mid_path_20260910.review_path import PATH, ROOT
from scripts.artifact_io import load_json_object, write_json_exclusive
from scripts.neb_agent.submission import InputBundle
from scripts.ts_strategy_engine.execution_gate import validate_decision
from scripts.ts_strategy_engine.execution_gate_cli import build_decision
from scripts.ts_strategy_engine.path_evidence import validate_path_review


def main() -> None:
    report = load_json_object(PATH/'submission_preflight.json')
    InputBundle.from_preflight(report).verify(PATH)
    reviewed, _ = validate_path_review(PATH/'path_review.json', PATH/'path_generation_report.json')
    assert reviewed
    request = {name+'_file': str(path) for name, path in {
        'geometry': PATH/'path_geometry_diagnosis.json',
        'analysis': PATH/'neb_analysis.json',
        'thresholds': ROOT/'configs/neb_agent/default_thresholds.yaml',
        'preflight': PATH/'submission_preflight.json',
    }.items()}
    request.update(climb=False, path_reviewed=reviewed)
    write_json_exclusive(PATH/'execution_gate_request.json', request)
    result = build_decision(PATH/'execution_gate_request.json', PATH/'execution_gate.json')
    validate_decision(result)
    assert result['DECISION'] == 'READY_FOR_ORDINARY_NEB_SUBMISSION'
    assert not result['SUBMISSION_ALLOWED'] and 'SUBMIT_VASP' not in result['ALLOWED_ACTIONS']
    print({k:result[k] for k in ('DECISION','ALLOWED_ACTIONS','SUBMISSION_ALLOWED','scientific_readiness','execution_authorization')})
    print('input bundle:', report['bundle_sha256'])


if __name__ == '__main__':
    main()
