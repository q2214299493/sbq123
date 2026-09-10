"""Register the observed GPU0 model start and project its checkpoint status."""
from copy import deepcopy
from datetime import datetime, timezone

from archive.int06_mid_gpu_20260910.gpu0_attempt import attempt
from archive.int06_mid_gpu_20260910.inspect_remote import BASE, ROOT
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.state_manager.models import validate_event

LOCAL = attempt.ATTEMPT


def prepare():
    cp = LOCAL / 'checkpoint_job1517'
    observed = load_json_object(cp / 'checkpoint.json')
    record = load_json_object(cp / 'gpu_submission_record.json')
    binding = load_json_object(cp / 'gpu_binding.json')
    assert binding['scheduler_allocation_matches_target'] and binding['physical_index'] == 0
    scheduler = observed['queries']['scheduler']['stdout']
    assert 'JobState=RUNNING' in scheduler
    job_pids = {line.split()[0] for line in observed['queries']['job_pids']['stdout'].splitlines()[1:] if line.strip()}
    gpu_pids = {line.split(',')[0].strip() for line in observed['queries']['gpu_processes']['stdout'].splitlines()
                if binding['target_uuid'] in line}
    assert job_pids & gpu_pids
    log = observed['logs']['output/production/ordinary_ml_neb.log']
    assert 'FIRE:    1' in log
    now = datetime.now(timezone.utc).isoformat()
    report = ROOT / 'docs/reviews/int06_mid_gpu1517_started_20260910.md'
    with report.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(f'''# INT06→MID GPU1517 已启动（2026-09-10）

用户指令“提交gpu0”。作业 1517 于北京时间 16:29:07 提交。

- {observed['observed_at']}：Slurm RUNNING；GPU0 UUID={binding['target_uuid']}，调度分配与实际 CUDA 卡一致。
- scontrol listpids 和 nvidia-smi 的 PID 交集 {sorted(job_pids & gpu_pids)} 证明本作业模型进程在 GPU0，非仅队列接收。
- ordinary_ml_neb.log 已有 FIRE 第 0、1 步；fmax 从 0.361267 到 0.296261 eV/A。尚未证明达到请求中的 0.1 eV/A 收敛条件；这些都是 ML 预测，不是 VASP 势垒或 TS 验证。
- 启动时 GPU0 空闲 12169 MiB，通过 12000 MiB 门槛。1 GPU、4 CPU、40 GB、6 小时、400 步上限不变。
- 请求 SHA256 {record['request_sha256']}；复用修正后的解释器符号链接处理和任务内 TMPDIR。此次没有运行时错误、重提、GPU 分配覆盖或 VASP 提交。
- 本地 Python/Ruff/shell 语法与 GPU0 正常、错误分配、低显存三项保护检查通过；远端环境检查与 23 文件输入、模型文件、几何预检通过。未重复运行已经通过且未变化的模型测试。

下一步：检查该作业输出，完成后将完整预测路径带回 work 进行路径、几何和后续 VASP 路线审查。此文是上述时刻的启动快照。
''')
    calc, job = 'fe110_h_migration_int06_mid_gpu1517', 'slurm_mz73_1517'
    rows = {'calculations': [{'calculation_id': calc, 'module': 'transition_state_search',
        'purpose': 'INT06 to MID ordinary ML-NEB candidate on scheduler-assigned physical GPU0',
        'scientific_system': 'Fe45 C2 O H2 on Fe(110)',
        'parent_calculation_id': 'fe110_h_migration1357_valley06_relax_9748648',
        'workflow_status': 'running', 'created_at': record['submitted_at'], 'source_record': str(report),
        'notes': 'Predicted candidate only; model process and first ML steps verified.'}],
        'jobs': [{'job_record_id': job, 'calculation_id': calc, 'scheduler_job_id': '1517',
        'scheduler': 'Slurm', 'server_alias': 'MZ73', 'queue': 'normal',
        'remote_directory': record['remote_root'], 'submit_script': record['remote_root'] + '/execution/allocated_gpu_guard.sh',
        'submitted_at': record['submitted_at']}], 'job_status_history': [], 'files': []}
    for status, when, source in [('SUBMITTED', record['submitted_at'], str(cp / 'sbatch_raw.json')),
                               ('RUNNING', observed['observed_at'], scheduler)]:
        rows['job_status_history'].append({'job_record_id': job, 'scheduler_status': status,
            'scientific_status': 'Not assessed', 'checked_at': when, 'source_command': 'sbatch / scontrol',
            'source_text': source, 'reviewer': 'Codex'})
    updates, package = LOCAL / 'payload_updates', BASE / 'payload'
    manifest = load_json_object(updates / 'payload_manifest.json')
    files = []
    for name in list(manifest['files']) + ['payload_manifest.json']:
        path = updates / name if (updates / name).exists() else package / name
        files.append((path, record['remote_root'] + '/' + name, 'input'))
    files += [(p, record['remote_root'] + '/execution/' + p.name, 'input') for p in (LOCAL / 'execution').iterdir() if p.is_file()]
    files += [(p, None, 'validation') for p in cp.rglob('*') if p.is_file()]
    files.append((report, None, 'validation'))
    for i, (path, remote, role) in enumerate(files):
        rows['files'].append({'file_id': calc + '_' + str(i), 'calculation_id': calc, 'job_record_id': job,
            'role': role, 'filename': path.name, 'local_path': str(path), 'remote_path': remote,
            'storage_mode': 'local_and_remote' if remote else 'local', 'byte_size': path.stat().st_size,
            'sha256': sha256_file(path), 'existence_status': 'confirmed'})
    write_json_exclusive(LOCAL / 'registry_batch.json', {'schema_version': 1,
        'document_kind': 'calculation_registry_batch', 'batch_id': 'gpu1517_started_20260910',
        'created_at': now, 'reviewer': 'Codex', 'reason': 'Record explicitly requested GPU0 start and first model steps.', 'rows': rows})
    print({k: len(v) for k, v in rows.items()})


def events():
    now = datetime.now(timezone.utc).isoformat()
    report = ROOT / 'docs/reviews/int06_mid_gpu1517_started_20260910.md'
    for kind in ['task', 'state']:
        previous = kind + '-gpu1-startup-blocked-20260910'
        event = deepcopy(load_json_object(ROOT / 'modules/state_handoff/events' / (previous + '.json')))
        event.update(event_id=kind + '-gpu1517-running-20260910', supersedes=[previous],
                     occurred_at=now, recorded_at=now, summary='GPU1517 RUNNING on scheduler-assigned GPU0 with model PID and first ML steps verified.')
        event['evidence'] += [{'locator': p.relative_to(ROOT).as_posix(), 'sha256': sha256_file(p),
                              'authority': 'repository_document', 'observed_at': now} for p in
                             [report, LOCAL / 'registry_receipt.json', LOCAL / 'checkpoint_job1517/checkpoint.json']]
        payload = event['payload']
        facts = payload['current_evidence'] if kind == 'task' else payload['facts']
        facts[-1] = 'Prior GPU1 jobs1513/1514/1516 failed before model; diagnostic1515 identified inherited TMPDIR. Failures retained; Python symlink and task-local TMPDIR corrections now exercised successfully by GPU1517.'
        facts.append('User-requested GPU0 job1517 submitted 16:29:07; at16:29:16 Slurm RUNNING, scheduler GPU0 and model GPU UUID agree, PID2591707 verified. ML-NEB FIRE step1 completed, fmax0.296261 eV/A; prediction-only, not converged or validated TS.')
        next_action = 'Check GPU1517 on MZ73 at /home/sbq/sbq/aqcat25_ts_pilot/handoffs/int06_mid_ml_neb_20260910_gpu0; retrieve and review the complete ML path when it finishes before selecting any VASP route.'
        if kind == 'task':
            payload['one_executable_step'] = next_action
            payload['submission_boundary'] = 'One GPU0 job1517 is running under explicit user authority. No automatic VASP submission or model retry authorized.'
            payload['authoritative_references'].append(report.relative_to(ROOT).as_posix())
        else:
            payload['title'] = 'Active Gate - 2026-09-10 GPU1517 Running on GPU0; First ML Steps Verified'
            payload['next_action'] = next_action
        write_json_exclusive(LOCAL / (kind + '_event.json'), validate_event(event))


if __name__ == '__main__':
    prepare()
