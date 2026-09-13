"""Plan/apply this submitted control's provenance using the canonical registry."""
import argparse
import json
from datetime import datetime, timezone

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.registry_write import apply_registry_batch, plan_registry_batch
from scripts.registry_transactions import approve_plan
from archive.scf_mixing_control_20260913.execute import ROOT, NEW, OLD, CONTROL


def plan():
    now = datetime.now(timezone.utc).isoformat()
    rows = {'calculations': [], 'jobs': [], 'job_status_history': [], 'files': []}
    for job, directory, evidence_name, workflow, scientific in [
        ('9753825', OLD, 'old_scheduler_terminal.json', 'needs_review', 'user_stopped_unconverged'),
        ('9754110', NEW, 'scheduler_checkpoint.json', 'submitted', 'not_yet_validated'),
    ]:
        cid, jid = 'fe110_int06_mid_scf_' + job, 'lsf_sunboquan_' + job
        record = load_json_object(directory/'submission_record.json')
        evidence = load_json_object(NEW/evidence_name)
        timestamp = evidence['observed_at'] if 'observed_at' in evidence else now
        rows['calculations'].append({
            'calculation_id': cid, 'module': 'transition_state_search',
            'purpose': 'fixed_geometry_scf_diagnostic_not_TS', 'scientific_system': 'Fe110_C2HO_H',
            'workflow_status': workflow, 'created_at': now,
            'source_record': str(directory/'submission_record.json'),
            'notes': 'Historical submission timestamp not inferred; created_at is registry insertion time.',
        })
        rows['jobs'].append({
            'job_record_id': jid, 'calculation_id': cid, 'scheduler_job_id': job,
            'scheduler': 'LSF', 'server_alias': 'sunboquan-codex', 'queue': 'Gkn_normal',
            'remote_directory': record['remote_dir'], 'submit_script': 'script.lsf',
        })
        rows['job_status_history'].append({
            'job_record_id': jid, 'scheduler_status': evidence['status'],
            'scientific_status': scientific, 'checked_at': timestamp,
            'source_command': 'canonical query_lsf_job',
            'source_text': json.dumps(evidence, ensure_ascii=True), 'reviewer': 'codex_user_authorized',
        })
        files = [directory/'submission_record.json', NEW/evidence_name]
        if job == '9754110':
            files += [NEW/'execution_gate_decision.json', NEW/'mixing_control_identity.json', NEW/'INCAR']
        else:
            files += [CONTROL/'stop9753825/stop_receipt.json']
        for index, path in enumerate(files):
            rows['files'].append({
                'file_id': cid + '_control_' + str(index), 'calculation_id': cid,
                'job_record_id': jid, 'role': 'submission_or_status_evidence',
                'filename': path.name, 'local_path': str(path), 'storage_mode': 'local',
                'byte_size': path.stat().st_size, 'sha256': sha256_file(path),
                'existence_status': 'confirmed',
            })
    batch = {'schema_version': 1, 'document_kind': 'calculation_registry_batch',
             'batch_id': 'scf_mixing9754110_stop9753825_20260913', 'created_at': now,
             'reviewer': 'codex_user_authorized',
             'reason': 'Record user-authorized old-job stop and one reviewed mixing-control submission; no accepted results.',
             'rows': rows}
    write_json(NEW/'registry_batch.json', batch)
    proposal = plan_registry_batch(ROOT/'data/project_registry.sqlite3', batch)
    write_json(NEW/'registry_plan.json', proposal)
    print(json.dumps({'insert_count': proposal['insert_count'], 'scope': proposal['scope'],
                      'plan_sha256': proposal['plan_sha256']}))


def apply():
    proposal = load_json_object(NEW/'registry_plan.json')
    approval = approve_plan(proposal, reviewer='codex_user_authorized',
                            reviewed_at=datetime.now(timezone.utc).isoformat())
    write_json(NEW/'registry_approval.json', approval)
    receipt = apply_registry_batch(ROOT/'data/project_registry.sqlite3',
        load_json_object(NEW/'registry_batch.json'), confirmed_sha256=proposal['plan_sha256'],
        plan=proposal, approval=approval)
    write_json(NEW/'registry_receipt.json', receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['plan', 'apply'])
    args = parser.parse_args()
    {'plan': plan, 'apply': apply}[args.stage]()
