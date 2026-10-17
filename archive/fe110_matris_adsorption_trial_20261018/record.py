"""Record the reviewed prediction experiment without accepting a DFT result."""
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.artifact_io import sha256_file, write_json_exclusive  # noqa: E402


def main():
    now = datetime.now(timezone.utc).isoformat()
    package = 'calculations/fe110_c2_adsorption_06_10_20261012/matris_direct_v1/'
    refs = [
        ('docs/reviews/fe110_matris_adsorption_trial_20261018.md', 'repository_document'),
        ('archive/fe110_matris_adsorption_trial_20261018/authorization.md', 'user_authorization'),
        (package + 'returned_review.json', 'module_validation'),
        (package + 'returned_v1/direct_batch_exit_record.json', 'calculation_file'),
    ]
    evidence = [dict(locator=path, sha256=sha256_file(ROOT / path), authority=kind, observed_at=now)
                for path, kind in refs]
    payload = dict(
        objective='Review the completed six-candidate MatRIS adsorption GPU trial before deciding on any further comparison; preserve the existing15 VASP calculations.',
        phase='active',
        current_evidence=[
            'User explicitly authorized one direct GPU2 trial:06_C,07_B,07_C,08_A,09_A,10_A;80 steps each,fmax0.10,max1800s;no VASP/training/default promotion.',
            'Provider-baseline MatRIS SHA1e6a85b33db075ad1637eca7537084024a694b1340358911212d8a5c518c6601;all source seeds identical to the prior AQCat batch.',
            'Direct run PID2398967 completed exit0 in59.653618s;canonical receipts and all6 outputs preserved;actual CUDA GPU2 UUID verified.',
            'All6 schema/source/cell/order/fixed-layer checks pass;5 ML-force-converged and5 original graphs preserved.06_C stopped at80 steps,fmax0.275277 and predicted CO+C+H.',
            'MatRIS ML steps exceed matched AQCat steps on all6 seeds;downstream VASP force agreement and acceleration are not measured. No model promoted.',
            'All15 existing VASP jobs9848799-9848813 remain untouched and are carried in backlog for monitoring/final eligible-result registration;not freshly polled in this GPU-only turn.',
        ],
        one_executable_step='Present the six predicted outcomes for user review; obtain separate authority before any new MatRIS→VASP comparison, further GPU run or training.',
        submission_boundary='Only the completed six-candidate GPU2 trial was authorized. No automatic retry,new VASP,training,model promotion,service modification or existing-job stop.',
        done_when=[
            'All6 canonical outputs and exact source/model/device/geometry reviews are preserved without DFT acceptance claims.',
            'User has reviewed the trial and selected a next scoped action or closed this model trial without promotion.',
        ],
        constraints=[
            '06_C is a changed-chemistry,not-ML-converged prediction;do not label it as intact C-O-CH or as a final DFT state.',
            'Existing VASP results retain their own completion/chemistry/compatibility/registry workflow;GPU trial cannot replace it.',
        ],
        authoritative_references=[
            'configs/execution_backends.yaml', 'modules/adsorption_workflow/README.md',
            'docs/reviews/fe110_matris_adsorption_trial_20261018.md', package + 'returned_review.json',
        ])
    event = dict(schema_version=1, event_id='task-fe110-matris-adsorption-trial-20261018',
        occurred_at=now, recorded_at=now, event_type='task_updated',
        entity=dict(kind='task', id='task-current', module='adsorption_workflow'),
        summary='Authorized MatRIS GPU2 six-seed trial completed and reviewed:5 model-converged/intact,06_C unfinished and reclassified;no VASP/training/model promotion.',
        evidence=evidence, review=dict(required=False, reason_codes=[], status='not_required'),
        supersedes=['task-fe110-c2-0610-vasp-submitted-20261013'], payload=payload)
    target = ROOT / 'modules/state_handoff/events/task-fe110-matris-adsorption-trial-20261018.json'
    write_json_exclusive(target, event)
    print(target)


if __name__ == '__main__':
    main()
