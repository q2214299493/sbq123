"""Preserve GPU1512 startup failure and prepare factual registry records."""
from datetime import datetime, timezone
import re
import subprocess

from archive.int06_mid_gpu_20260910.inspect_remote import BASE, ROOT
from archive.int06_mid_gpu_20260910.prepare import REMOTE
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

CALC = 'fe110_h_migration_int06_mid_gpu1512'
JOB = 'slurm_mz73_1512'


def main():
    checkpoint=BASE/'checkpoint_job1512'
    observed=load_json_object(checkpoint/'checkpoint.json')
    scheduler=observed['queries']['scontrol']
    assert scheduler['exit_code']==0 and 'JobState=FAILED' in scheduler['stdout']
    assert 'ExitCode=3:0' in scheduler['stdout']
    source=checkpoint/'production-1512.out'
    assert not source.exists()
    command=['scp','-P','36039','-i','C:/Users/86177/.ssh/id_ed25519_fe_agent',
             '-o','IdentitiesOnly=yes','-o','BatchMode=yes',
             'sbq@10sx4jr711576.vicp.fun:'+REMOTE+'/logs/production-1512.out',str(source)]
    subprocess.run(command,check=True,capture_output=True,timeout=30)
    log=source.read_text(encoding='utf-8')
    assert 'only 7465 MiB free; require 12000 MiB' in log
    record=load_json_object(checkpoint/'gpu_submission_record.json')
    report=ROOT/'docs/reviews/int06_mid_gpu1512_startup_failure_20260910.md'
    with report.open('x',encoding='utf-8',newline='\n') as handle:
        handle.write(f'''# INT06→MID GPU1512 提交及启动失败（2026-09-10）

- 用户“提交”已绑定已审查请求 `{record['request_sha256']}`，资源为 1 GPU、4 CPU、40 GB、6 小时，400 个普通 ML-NEB 步上限。
- Slurm 接受提交并分配作业 1512；提交回执时间 `{record['submitted_at']}`。
- `{observed['observed_at']}` 的 scontrol 证据明确为 `FAILED`，`ExitCode=3:0`，运行时长 0 秒；不是仅由队列消失推断失败。
- 已分配 GPU0 的启动检查只见 7465 MiB 空闲显存，小于 12000 MiB；guard 在调用模型运行器前退出。没有执行模型或 ML-NEB 步，也没有可用于判断模型误差的结果。
- 请求、模型和已部署输入校验通过。问题位于分配卡的即时显存条件，不是输入几何或模型收敛失败。
- 保留原请求、授权、防重复记录、sbatch 回执、scontrol 原文与原始启动日志。未停止他人进程、未改变 GPU 绑定、未重提作业，未提交 VASP。

## 未解决问题与下一步

需要为后续尝试获得至少 12000 MiB 空闲显存的实际分配卡；整机有其他空闲卡不能证明本次分配满足条件。重提须有单次明确授权，并创建新的尝试/回执，保留 1512 失败记录。不得重复调用已有提交器或把失败路径作为训练样本。

原 VASP NEB 输入仅备用；第一段 IS-A→INT06 和迁移势垒仍未完成。
''')
    now=datetime.now(timezone.utc).isoformat()
    rows={'calculations':[{
        'calculation_id':CALC,'module':'transition_state_search',
        'purpose':'INT06 to MID initial GPU ML-NEB predicted candidate; startup aborted before model execution',
        'scientific_system':'Fe45 C2 O H2 on Fe(110)',
        'parent_calculation_id':'fe110_h_migration1357_valley06_relax_9748648',
        'workflow_status':'failed','created_at':record['submitted_at'],
        'source_record':str(report),'notes':'GPU memory guard failure, no predicted energies/forces or TS claim.',
    }], 'jobs':[{
        'job_record_id':JOB,'calculation_id':CALC,'scheduler_job_id':'1512','scheduler':'Slurm',
        'server_alias':'MZ73','queue':'normal','remote_directory':REMOTE,
        'submit_script':REMOTE+'/execution_20260910/allocated_gpu_guard.sh','submitted_at':record['submitted_at'],
    }], 'job_status_history':[
        {'job_record_id':JOB,'scheduler_status':'SUBMITTED','scientific_status':'Not assessed',
         'checked_at':record['submitted_at'],'source_command':'sbatch --parsable',
         'source_text':str(checkpoint/'sbatch_raw.json'),'reviewer':'Codex','notes':'Scheduler accepted job 1512.'},
        {'job_record_id':JOB,'scheduler_status':'FAILED','scientific_status':'Not assessed',
         'checked_at':observed['observed_at'],'source_command':'scontrol show job 1512 -o',
         'source_text':scheduler['stdout'],'reviewer':'Codex','notes':'Exit3: assigned GPU0 7465 MiB free <12000; no model execution.'},
    ], 'files':[]}
    package=BASE/'payload'
    names=list(load_json_object(package/'payload_manifest.json')['files'])+['payload_manifest.json']
    records=[(package/name,REMOTE+'/'+name,'input') for name in names]
    records += [(BASE/'execution_20260910'/name,REMOTE+'/execution_20260910/'+name,'input')
                for name in ['authorization.json','submit_remote.py','allocated_gpu_guard.sh']]
    records += [(checkpoint/name,REMOTE+'/'+name,'output') for name in
                ['gpu_submission_record.json','gpu_submission_reservation.json','sbatch_raw.json']]
    records += [(source,REMOTE+'/logs/production-1512.out','output'),
                (checkpoint/'checkpoint.json',None,'validation'),(report,None,'validation')]
    for index,(path,remote,role) in enumerate(records):
        rows['files'].append({'file_id':CALC+'_'+str(index)+'_'+re.sub('[^A-Za-z0-9_.-]','_',path.name),
             'calculation_id':CALC,'job_record_id':JOB,'role':role,'filename':path.name,
             'local_path':str(path),'remote_path':remote,'storage_mode':'local_and_remote' if remote else 'local',
             'byte_size':path.stat().st_size,'sha256':sha256_file(path),'existence_status':'confirmed',
             'notes':'Operational provenance only; no scientific result promotion.'})
    write_json_exclusive(BASE/'registry_1512_batch.json',{
        'schema_version':1,'document_kind':'calculation_registry_batch','batch_id':'gpu1512_startup_failure_20260910',
        'created_at':now,'reviewer':'Codex','reason':'Record user-authorized submission and evidenced pre-model startup failure.',
        'rows':rows,
    })
    print('Failure evidence preserved; registry batch has '+str(sum(len(v) for v in rows.values()))+' factual rows, no results.')


if __name__=='__main__':
    main()
