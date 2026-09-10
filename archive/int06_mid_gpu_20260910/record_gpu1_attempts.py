"""Record the GPU1 launch attempts and their evidenced startup failures."""
import base64
import json
import re
from datetime import datetime, timezone

from archive.int06_mid_gpu_20260910.inspect_remote import BASE, ROOT
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

FINAL = BASE / 'attempt_gpu1_ready_20260910'


def main():
    report = ROOT / 'docs/reviews/int06_mid_gpu1_attempts_20260910.md'
    assert not report.exists()
    now = datetime.now(timezone.utc).isoformat()
    report.write_text('''# GPU 1 提交与启动失败（2026-09-10）

用户重复指令“提交gpu1”用于本次 GPU 1 启动工作。未完成模型启动；没有新的 ML-NEB 步、预测能量或 VASP 结果。

| 作业 | 调度状态 | 启动结果 |
|---|---|---|
| 1513 | FAILED / 2:0 | 选定 GPU1 UUID，空闲 14723 MiB；虚拟环境 Python 链接至 /usr/bin/python3.10，被写入边界检查误拒绝。 |
| 1514 | FAILED / 2:0 | 选定 GPU1 UUID；解释器检查修正后，Slurm 注入 TMPDIR=/tmp，被写入边界检查拒绝。 |
| 1515 | FAILED / 2:0 | 仅运行启动诊断，确认 /tmp 根因；未加载模型。原计划只用 CPU，但复制脚本继承了 SBATCH gres=gpu:1，实际仍申请了 1 GPU，须以调度证据为准。 |
| 1516 | FAILED / 1:0 | 已准备解释器修正与任务内 TMPDIR；GPU1 出现新增约 4 GiB 进程，启动显存检查失败，尚未进入环境设置或模型执行。 |

16:12:54（北京时间）GPU1 空闲 10641 MiB，利用率 100%。12000 MiB 是当前启动脚本门槛，未通过实测证明是该模型最低需求；本次未降低门槛。

GPU1 的 UUID 为 GPU-450609b3-d1fd-ac33-d03a-79891be402da。1513/1514 启动证据分别保留 Slurm 分配 GPU0 与用户明确指定物理 GPU1 的信息，不能宣称调度器分配了 GPU1，也未证明模型进程在 GPU1 运行。启动前拒绝其他活动 Slurm GPU 作业；未修改调度器配置或停止他人进程。

环境修正仅允许虚拟环境解释器的末端符号链接指向系统 Python，仍校验其父目录和全部写入路径。第三次计算启动脚本显式设置 TMPDIR 到任务根目录。结构、模型、优化参数和计算上限（1 GPU、4 CPU、40 GB、6 小时、400 步）不变；新请求哈希仅反映运行环境绑定变化。

验证：GPU 选择保护的正常、显存不足、错误卡号和其他 Slurm GPU 作业四项检查通过；Python 编译、Ruff、相关 shell 语法检查通过；tests/test_gpu_execution_lifecycle.py 与 tests/test_dual_model_ml_neb.py 联合测试退出码 0。修正后的远端环境设置与 23 文件请求/几何/模型文件哈希预检通过。任务内 TMPDIR 方案尚未在完整模型启动中验证。

原 1512 与本次失败记录全部保留。当前没有本任务运行中的计算。下一步是在 GPU1 满足显存门槛时，对修正后的完整启动流程进行一次确认，再推进 ML 路径计算；模型收敛和迁移 TS 仍未验证。
''', encoding='utf-8', newline='\n')
    rows = {name: [] for name in ['calculations', 'jobs', 'job_status_history', 'files']}
    attempts = [('1513', BASE / 'attempt_gpu1_20260910'),
                ('1514', BASE / 'attempt_gpu1_envfix_20260910'), ('1516', FINAL)]
    for job, local in attempts:
        calc = 'fe110_h_migration_int06_mid_gpu' + job
        job_record = 'slurm_mz73_' + job
        checkpoint = local / ('checkpoint_job' + job)
        observed = load_json_object(checkpoint / 'checkpoint.json')
        record = load_json_object(checkpoint / 'gpu_submission_record.json')
        remote = record['remote_root']
        scheduler = observed['queries']['scheduler']['stdout']
        assert 'JobState=FAILED' in scheduler
        rows['calculations'].append({'calculation_id': calc, 'module': 'transition_state_search',
            'purpose': 'User-requested GPU1 ML-NEB candidate launch; pre-model startup failure',
            'scientific_system': 'Fe45 C2 O H2 on Fe(110)',
            'parent_calculation_id': 'fe110_h_migration1357_valley06_relax_9748648',
            'workflow_status': 'failed', 'created_at': record['submitted_at'],
            'source_record': str(report), 'notes': 'No model execution or scientific promotion.'})
        rows['jobs'].append({'job_record_id': job_record, 'calculation_id': calc,
            'scheduler_job_id': job, 'scheduler': 'Slurm', 'server_alias': 'MZ73', 'queue': 'normal',
            'remote_directory': remote, 'submit_script': remote + '/execution/allocated_gpu_guard.sh',
            'submitted_at': record['submitted_at']})
        for status, time, source in [('SUBMITTED', record['submitted_at'], str(checkpoint / 'sbatch_raw.json')),
                                     ('FAILED', observed['observed_at'], scheduler)]:
            rows['job_status_history'].append({'job_record_id': job_record, 'scheduler_status': status,
                'scientific_status': 'Not assessed', 'checked_at': time, 'source_command': 'sbatch / scontrol',
                'source_text': source, 'reviewer': 'Codex', 'notes': 'Operational evidence only.'})
        updates = local / 'payload_updates'
        package = BASE / 'payload'
        manifest = load_json_object((updates if updates.exists() else package) / 'payload_manifest.json')
        records = []
        for name in list(manifest['files']) + ['payload_manifest.json']:
            path = updates / name if (updates / name).exists() else package / name
            records.append((path, remote + '/' + name, 'input'))
        records += [(p, remote + '/execution/' + p.name, 'input') for p in (local / 'execution').iterdir()
                    if p.is_file()]
        records += [(p, None, 'validation') for p in checkpoint.rglob('*') if p.is_file()]
        records.append((report, None, 'validation'))
        for index, (path, remote_path, role) in enumerate(records):
            rows['files'].append({'file_id': calc + '_' + str(index), 'calculation_id': calc,
                'job_record_id': job_record, 'role': role, 'filename': path.name,
                'local_path': str(path), 'remote_path': remote_path,
                'storage_mode': 'local_and_remote' if remote_path else 'local',
                'byte_size': path.stat().st_size, 'sha256': sha256_file(path), 'existence_status': 'confirmed'})
    diagnostic = BASE / 'attempt_gpu1_envfix_20260910'
    result = json.loads((diagnostic / 'environment_diagnostic_result.stdout').read_bytes())
    source = diagnostic / 'environment_diagnostic_1515.log'
    with source.open('xb') as handle:
        handle.write(base64.b64decode(result['log_base64']))
    # The diagnostic was a distinct, short scheduler job, not another model run.
    calc = 'fe110_h_migration_int06_mid_env1515'
    when = re.search(r'SubmitTime=(\S+)', result['scheduler']).group(1) + '+08:00'
    rows['calculations'].append({'calculation_id': calc, 'module': 'transition_state_search',
        'purpose': 'Startup-only environment diagnostic; inherited GPU allocation, no model execution',
        'parent_calculation_id': 'fe110_h_migration_int06_mid_gpu1514', 'workflow_status': 'failed',
        'created_at': when, 'source_record': str(report)})
    remote = load_json_object(diagnostic / 'checkpoint_job1514/gpu_submission_record.json')['remote_root']
    rows['jobs'].append({'job_record_id': 'slurm_mz73_1515', 'calculation_id': calc,
        'scheduler_job_id': '1515', 'scheduler': 'Slurm', 'server_alias': 'MZ73', 'queue': 'normal',
        'remote_directory': remote, 'submitted_at': when,
        'submit_script': remote + '/execution/environment_diagnostic.sh'})
    rows['job_status_history'].append({'job_record_id': 'slurm_mz73_1515', 'scheduler_status': 'FAILED',
        'scientific_status': 'Not assessed', 'checked_at': now, 'source_command': 'scontrol show job 1515 -o',
        'source_text': result['scheduler'], 'reviewer': 'Codex'})
    for i, path in enumerate([source, diagnostic / 'environment_diagnostic_submit.stdout',
                              diagnostic / 'environment_diagnostic_result.stdout']):
        rows['files'].append({'file_id': calc + '_' + str(i), 'calculation_id': calc,
            'job_record_id': 'slurm_mz73_1515', 'role': 'validation', 'filename': path.name,
            'local_path': str(path), 'storage_mode': 'local', 'byte_size': path.stat().st_size,
            'sha256': sha256_file(path), 'existence_status': 'confirmed'})
    write_json_exclusive(FINAL / 'registry_batch.json', {'schema_version': 1,
        'document_kind': 'calculation_registry_batch', 'batch_id': 'gpu1_startup_attempts_20260910',
        'created_at': now, 'reviewer': 'Codex', 'reason': 'Record requested GPU1 submissions and exact startup failures.',
        'rows': rows})
    print({name: len(value) for name, value in rows.items()})


if __name__ == '__main__':
    main()
