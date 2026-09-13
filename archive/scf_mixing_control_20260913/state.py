"""Prepare one immutable current-task status event from verified receipts."""
from copy import deepcopy
from datetime import datetime, timezone

from scripts.artifact_io import sha256_file, write_json
from scripts.state_manager.models import StateEvent
from scripts.state_manager.store import EventStore
from archive.scf_mixing_control_20260913.execute import ROOT, NEW, CONTROL


def main():
    source = EventStore().current_task_source()
    if source.event_id != 'task-scf9753825-dispatch-failure-20260913':
        raise RuntimeError('Current task changed; inspect before preparing another event.')
    event = deepcopy(source.payload)
    now = datetime.now(timezone.utc).isoformat()
    document = ROOT/'docs/reviews/int06_mid_scf9754110_mixing_control_20260913.md'
    event.update(event_id='task-scf9754110-mixing-control-submitted-20260913',
                 occurred_at=now, recorded_at=now, supersedes=[source.event_id],
                 summary='SCF9753825 user-stopped EXIT; two-parameter mixing control SCF9754110 submitted PEND.')
    evidence = [(document, 'repository_document'),
                (NEW/'old_scheduler_terminal.json', 'scheduler'),
                (NEW/'scheduler_checkpoint.json', 'scheduler'),
                (NEW/'submission_record.json', 'repository_document'),
                (NEW/'execution_gate_decision.json', 'module_validation'),
                (NEW/'registry_receipt.json', 'calculation_registry'),
                (CONTROL/'stop9753825/stop_receipt.json', 'repository_document')]
    event['evidence'] = [{'locator': p.relative_to(ROOT).as_posix(),
                          'sha256': sha256_file(p), 'authority': authority, 'observed_at': now}
                         for p, authority in evidence]
    event['payload']['current_evidence'] = [
        'User authorized stop of SCF9753825; canonical stop receipt and live EXIT confirmed; outputs preserved.',
        'One reviewed mixing-control SCF9754110 submitted; initial scheduler PEND in Gkn_normal, 80 cores, excludes gknew0440.',
        'Only AMIX0.4->0.2 and AMIX_MAG1.6->0.8 changed; exact geometry, physical inputs, ALGO Normal, EDIFF1e-7 and NELM200 preserved.',
        'Fresh directory; no failed restart state copied. MPI/SCF startup, convergence and saved electronic state not yet verified.',
        'Old and new job/status provenance recorded through a reviewed registry batch; no accepted result added.',
        'Require output integrity, normal electronic convergence, unchanged geometry and completed WAVECAR/CHGCAR before restart validation.',
        'SuccessfulSCF9752745 remains comparison only; INT06 endpoint and MID-to-FS O-H TS remain accepted. Earlier migration TS unresolved.',
    ]
    event['payload']['one_executable_step'] = 'Check SCF9754110 MPI/SCF startup and output integrity, then assess convergence before saved-state restart validation.'
    event['payload']['submission_boundary'] = 'SCF9753825 stopped and one SCF9754110 submitted under explicit user authority. No further retry, restart-validation job or Dimer submission authorized.'
    event['payload']['authoritative_references'] = [document.relative_to(ROOT).as_posix(),
        'docs/reviews/scf_mixing_control_20260913/README.md',
        'docs/reviews/int06_mid_scf9752745_20260912.md',
        'docs/reviews/oh_ts_accepted_barrier_20260910.md']
    StateEvent.from_mapping(event)
    write_json(NEW/'task_state_event.json', event)
    print(NEW/'task_state_event.json')


if __name__ == '__main__':
    main()
