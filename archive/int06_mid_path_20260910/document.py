"""Record prepared artifacts and procedural progress, preserving approved science."""
from copy import deepcopy
from datetime import datetime, timezone

from archive.int06_mid_path_20260910.review_path import BASE, PATH, ROOT
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.state_manager.models import validate_event


def main() -> None:
    bundle = load_json_object(PATH/'submission_preflight.json')['bundle_sha256']
    report = ROOT/'docs/reviews/int06_mid_path_prepared_20260910.md'
    content = f'''# INT06 → MID：局部普通 NEB 输入审查（2026-09-10）

状态：本地准备完成；未提交 VASP。此前 INT06 结果及 MID→FS O–H TS 的用户批准不变。

## 输入与范围

- 起点：9748648 最终 CONTCAR（INT06）；终点：9737143 最终 CONTCAR（MID）。两个登记结构均以字节副本保留在新包 IS.vasp、FS.vasp。
- 原 GPU1357 image07 只提供几何参考点；3 个中间图像由分段 IDPP 初始化。登记查询未找到 GPU06/07/08 的完整同构 VASP 峰值三图像证据，不能直接用于 Dimer。
- 保留 50 原子顺序、H50 身份及底部 18 个 Fe 固定；独立检查使用 ASE 精确 MIC、仅 xy 周期边界。

## 已执行检查

- 端点、路径绑定、C₂HO 连通性、固定层、碰撞和周期连续性检查通过。
- 四次 dist.pl 和 nebmovie.pl 0 均 exit 0；生成的 5 帧 XYZ 与输入结构逐帧匹配；已查看 path_review.png 顶视图和侧视图。
- 相邻图像最大原子位移 0.465841、0.465841、0.330580、0.330580 Å；固定层漂移为 0。
- H50–Fe39 距离由 3.288013 单调降至 1.821733 Å，H50–Fe40 由 1.784730 单调增至 3.214591 Å；C₂HO 内部连通性保持。
- 仓库 VASP builder 生成输入；INCAR custodian：PASS，无错误或警告；submission preflight：PASS。
- 使用分析完成后的 geometry 文件刷新输入包绑定；canonical execution gate 自校验通过。

## 待批准计算

- 后端：sunboquan-codex；普通 NEB，3 个中间图像，96 核（每图像 32 核），NSW=300，LCLIMB=False。
- 锁定参数：PBE、ENCUT=400 eV、Gamma 5×5×1、SIGMA=0.20 eV、EDIFFG=-0.05 eV/Å、ISPIN=2、Fe MAGMOM=2.2、NPAR=4。
- 输入包：`{PATH.relative_to(ROOT).as_posix()}`。
- bundle SHA256：`{bundle}`。
- 执行门：`READY_FOR_ORDINARY_NEB_SUBMISSION`；scientific_readiness 允许候选动作 SUBMIT_VASP，但 `ALLOWED_ACTIONS=[]`、`SUBMISSION_ALLOWED=false`，因为没有本包的提交授权。

## 未验证与下一步

本路径没有 VASP 能量或力剖面，不能报告迁移势垒或 TS；IS-A→INT06 及其 image02 分支仍未解决。POTCAR 目前仅有规格文件，正式提交前须核验后端势文件与完整输入包。

下一步：用户批准上述确切输入包后，在 sunboquan-codex 核验 POTCAR、绑定授权并重评执行门，通过后提交这一项普通 NEB。
'''
    with report.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(content)
    now = datetime.now(timezone.utc).isoformat()
    previous = ROOT/'calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration1357_valley06_relax_20260909/completed_review_20260910'
    addition = ('INT06 -> MID local input package prepared: 3 interior images, 96 cores; '
                'VTST movie/distance, exact-MIC geometry, INCAR and input preflight checks completed. '
                'Execution gate has no allowed submission action without exact-package user authority. '
                'No new calculation was submitted.')
    next_action = ('Obtain exact-package authorization for INT06 -> MID ordinary NEB (3 images, 96 cores, '
                   f'NSW=300; bundle {bundle}); then verify backend POTCAR, bind authorization, '
                   'reevaluate the execution gate and submit only if SUBMIT_VASP is allowed.')
    for kind, old_name, new_id in [
        ('task','task_state_event.json','task-int06-mid-inputs-prepared-20260910'),
        ('state','current_gate_event.json','state-int06-mid-inputs-prepared-20260910'),
    ]:
        event = deepcopy(load_json_object(previous/old_name))
        event['supersedes'] = [event['event_id']]
        event.update(event_id=new_id, occurred_at=now, recorded_at=now,
                     summary='Procedural update: prepared local NEB inputs; existing approved scientific results unchanged.',
                     review={'required':False,'reason_codes':[],'status':'not_required'})
        event['evidence'].append({'locator':report.relative_to(ROOT).as_posix(),
                                  'sha256':sha256_file(report),'authority':'repository_document','observed_at':now})
        payload = event['payload']
        if kind == 'task':
            payload['current_evidence'].append(addition)
            payload['one_executable_step'] = next_action
            payload['authoritative_references'].append(report.relative_to(ROOT).as_posix())
        else:
            payload['facts'].append(addition)
            payload['next_action'] = next_action
            payload['title'] = 'Active Gate - 2026-09-10 INT06-to-MID Inputs Prepared; Submission Authority Pending'
        write_json_exclusive(BASE/(kind+'_prepared_event.json'), validate_event(event))
    print('review document and two procedural state events written')


if __name__ == '__main__':
    main()
