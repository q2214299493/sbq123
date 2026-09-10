"""Record the GPU-first preparation correction and its actual validation."""
from copy import deepcopy
from datetime import datetime, timezone

from archive.int06_mid_gpu_20260910.inspect_remote import BASE, ROOT
from archive.int06_mid_gpu_20260910.prepare import REMOTE
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.state_manager.models import validate_event


def main():
    request_hash = sha256_file(BASE/'payload/request.json')
    preflight = load_json_object(BASE/'remote_preflight.json')
    assert preflight['status']=='PASS' and preflight['request_sha256']==request_hash
    report = ROOT/'docs/reviews/int06_mid_gpu_prepared_20260910.md'
    content = f'''# INT06 → MID GPU 路径加速包（2026-09-10）

## 当前状态

GPU 请求已在本地准备并部署到 MZ73；本地与远端无模型预检通过。未运行模型、未提交 Slurm 或 VASP，无新作业号。

原普通 VASP NEB 包保留为备用。此前以缺少 VASP 峰值三图像证据为由直接推荐普通 NEB，未充分执行统一流程的 GPU 完整路径加速环节；三图像缺失只阻止直接 Dimer。本次按用户要求修正后续顺序，不改变已批准的 INT06 或 O–H TS 结果。

## 输入与方法

- 精确复用已审查 INT06(9748648)→MID(9737143) 的 5 帧初始路径，含 3 个中间图像；GPU1357 image07 只作为初始几何参考。
- 保留 50 原子顺序、H50 和底部 18 个 Fe 固定；C₂HO 内部不指定成断键。记录 H50–Fe39 接触距离，不把它强制为单调成键过程。
- MatRIS 原模型优化普通 ML-NEB，随后 AQCat25 对同一固定路径作能量/力对照。两个远端模型哈希均与原 GPU1357 请求一致。
- 不加临时键长约束，不启用 ML-CI、Sella、训练或自动重试。模型对本迁移段的 TS 域仍标为未校准；双模型差异仅作后续取样参考。
- 普通 ML-NEB：400 步上限，目标 fmax=0.10 eV/Å，弹簧常数 1.0 eV/Å²。
- 资源上限：1 个 GPU、4 CPU、40 GB 主存、6 小时；这是调度上限，不是运行时间预测。

## 校验

- 原始路径的 VTST dist.pl、nebmovie.pl 0、精确 MIC、可视化审查按哈希复用。
- 当前请求加载、结构哈希、原子映射、固定层和几何守卫均通过；相邻最大原子位移 0.465841 Å。
- 本地独立部署包导入/预检通过；MZ73 复核全部 23 个清单文件、两个模型哈希、脚本语法和同样的结构守卫通过，没有加载模型。
- `tests/test_dual_model_ml_neb.py`：17 项通过（软件测试，不是本反应的 GPU 计算）。任务脚本语法及 Ruff 检查通过。
- 首次远端库存检查因旧 Python 不提供 hashlib.file_digest 失败；改用分块哈希后通过，失败记录保留。

## 精确执行对象

- 本地：`{BASE.relative_to(ROOT).as_posix()}/payload/request.json`
- MZ73：`{REMOTE}`
- 请求 SHA256：`{request_hash}`
- 部署清单 SHA256：`{sha256_file(BASE/'payload/payload_manifest.json')}`

## 下一步与边界

待用户批准这个确切 GPU 请求后，绑定本包授权、复核执行门及重复提交状态，再提交单项 GPU 路径优化。返回后先审查完整路径、峰值、几何和模型偏差，再选择 VASP 标注/短程 NEB/符合条件的 Dimer。

未验证：真实 GPU 运行、路径收敛、峰值三图像 VASP 力证据和迁移势垒。IS-A→INT06 的第一段仍待后续处理；已完成的 MID→FS O–H 工作不重复。
'''
    with report.open('x',encoding='utf-8',newline='\n') as handle:
        handle.write(content)
    now = datetime.now(timezone.utc).isoformat()
    fact = ('INT06 -> MID GPU-first preparation corrected: five-frame MatRIS ML-NEB + exact-fixed-path '
            'AQCat25 request staged on MZ73; local and remote no-model preflights passed. '
            'One GPU, 4 CPUs, 40 GB, 6-hour limit, at most 400 ordinary ML-NEB steps. '
            'No GPU job submitted; previous VASP NEB inputs are fallback only.')
    next_action = (f'Obtain exact-package GPU execution authority for request {request_hash}; '
                   'then bind the reviewed request, recheck applicable execution gate and duplicate-job state, '
                   'and submit one MZ73 ordinary ML-NEB job. Review the returned complete path before choosing VASP refinement.')
    for kind in ('task','state'):
        old_id = kind+'-int06-mid-inputs-prepared-20260910'
        event = deepcopy(load_json_object(ROOT/'modules/state_handoff/events'/(old_id+'.json')))
        event.update(event_id=kind+'-int06-mid-gpu-prepared-20260910',supersedes=[old_id],
                     occurred_at=now,recorded_at=now,
                     summary='User-directed procedural correction: GPU path package staged and preflighted before VASP method selection.')
        event['evidence'].append({'locator':report.relative_to(ROOT).as_posix(),'sha256':sha256_file(report),
                                  'authority':'repository_document','observed_at':now})
        event['evidence'].append({'locator':(BASE/'remote_preflight.json').relative_to(ROOT).as_posix(),
                                  'sha256':sha256_file(BASE/'remote_preflight.json'),
                                  'authority':'repository_document','observed_at':now})
        payload = event['payload']
        if kind=='task':
            payload['current_evidence'][-1] = fact
            payload['one_executable_step'] = next_action
            payload['authoritative_references'].append(report.relative_to(ROOT).as_posix())
        else:
            payload['facts'][-1] = fact
            payload['next_action'] = next_action
            payload['title'] = 'Active Gate - 2026-09-10 INT06-to-MID GPU Package Preflighted; Execution Authority Pending'
        write_json_exclusive(BASE/(kind+'_event.json'),validate_event(event))
    print('GPU preparation review and procedural state events written')


if __name__ == '__main__':
    main()
