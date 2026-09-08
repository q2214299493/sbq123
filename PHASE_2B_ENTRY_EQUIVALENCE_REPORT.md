# Phase 2B 五入口等价性复验

## 1. 比较对象

对相同输入和配置比较：

1. `path_quality_control.evaluate_quality`
2. `path_quality_service.build_path_quality_report`
3. `path_quality_cli.main`
4. `workflow._path_quality`
5. `pilot_validation.build_pilot_path_quality_result`

标准化范围仅限临时目录、绝对路径和写入位置。科学字段未标准化或忽略。比较内容包括最终状态、reason code 内容和顺序、全部 evaluator 字段、阈值、Schema/evaluator 版本、顶层键、嵌套结构和列表顺序；另行检查 CLI 退出码、workflow 返回值和 pilot 原 `passed` 语义。

## 2. 样例结果

| 样例 | evaluator/service/CLI/workflow/pilot | 退出与边界 | 判定 |
|---|---|---|---|
| 正常进展 | 五入口完整科学结果相同；现有 Schema 的正常状态名为 `ORDINARY_NEB_PROGRESS_EVIDENCE` | CLI 0，workflow 返回同一报告 | IDENTICAL |
| 单一 endpoint 警告 | 状态及 `UNVERIFIED_INVALID_ENDPOINT_FLAG` 的位置相同 | CLI 0 | IDENTICAL |
| 明确电子失败 | `ELECTRONIC_FAILURE` 及 reason 顺序相同 | CLI 0；科学失败仍是有效证据，不伪装 I/O 成功/失败 | IDENTICAL |
| 图像间位移异常 | `UNDERRESOLVED_REACTION_COORDINATE`、位移指标和 reason 顺序相同 | CLI 0 | IDENTICAL |
| 多问题同时出现 | 六个 reason 的内容和顺序、状态及全部指标相同 | CLI 0 | IDENTICAL |
| 真实临时 POSCAR/INCAR 采集 | collector 结果经五入口形成的完整报告相同 | 只读临时目录 | IDENTICAL |
| endpoint 缺失/异常输入 | workflow 的旧 `INVALID_ENDPOINTS` 三字段返回保持；可评价的 endpoint flag 走唯一 evaluator | 不触发第二套 evaluator | IDENTICAL |
| 碰撞或原子过近 | 真实临时结构由 geometry diagnosis 判为 `STOP` 和 `unphysical_contact_pair_0_1`；同一上下文经过五个 path-quality 入口不会被二次解释或生成新 reason | 未把 geometry 规则复制进 service/CLI/pilot | SEMANTICALLY_EQUIVALENT |
| 磁性连续性异常 | 属于 pilot 独有验收，原测试确认 `passed` 规则保持；path-quality 五入口不新增磁性科学判断 | pilot 原结果不被 adapter 重解释 | SEMANTICALLY_EQUIVALENT |
| 非法配置 | service 在采集前 `ValueError`；CLI 退出 1 且不写成功 JSON；workflow/pilot 传播错误 | 错误更明确，未降级为正常结果 | SEMANTICALLY_EQUIVALENT |
| 缺失配置文件 | `OSError`/`FileNotFoundError` 保留到外层；CLI 退出 1 | 无输出 artifact | SEMANTICALLY_EQUIVALENT |
| 缺失路径输入文件 | collector 异常传播；CLI 退出 1 | 无成功 artifact | SEMANTICALLY_EQUIVALENT |
| evaluator 异常 | service、workflow、pilot 不吞异常；CLI 仅在最外层转失败退出 | 无成功 artifact | SEMANTICALLY_EQUIVALENT |
| 输出写入失败 | evaluator 结果不被伪造成已持久化；CLI 退出 1，workflow 异常传播 | 原目标不产生部分成功文件 | SEMANTICALLY_EQUIVALENT |
| workflow 无输出 | 旧 `{}` 返回保持 | 不调用 evaluator、不写文件 | IDENTICAL |
| workflow 缺 primary reaction coordinate | 旧三字段 `INVALID_ENDPOINTS` 保持 | 不调用 evaluator、不写 path-quality 文件 | IDENTICAL |

没有样例被标记为 `INCOMPATIBLE`。

## 3. 字段级结论

- `PATH_QUALITY_STATUS`：所有可比较科学样例一致。
- `REASON_CODES`：内容和列表顺序一致；service 未排序、过滤或补造 reason。
- 指标与阈值：对完整 evaluator payload 做深比较，无差异。
- `schema_version`、`evaluator_version`、`producer`、`kind`、`source_manifest`：五入口一致；producer 仍为 `scripts.neb_agent.path_quality_control`。
- 顶层键、嵌套字段和列表顺序：回归测试完整比较通过。
- CLI：`--help` 退出 0；成功退出 0；已覆盖的输入/配置/evaluator/写入错误退出 1；argparse 语法错误语义未改。
- workflow：返回结构、输出文件名 `neb_path_quality.json`、无输出和缺 primary 分支保持。
- pilot：原 `build_pilot_result`/`validate_pilot_result` 未接收 adapter 结果，原 `passed` 规则、Schema-v2 和磁性独有规则保持。

## 4. 实际执行证据

```text
python -m pytest tests/test_neb_path_quality_control.py \
  tests/test_neb_path_quality_entrypoints.py \
  tests/test_neb_pilot_validation.py \
  tests/test_artifact_io.py \
  tests/test_ts_strategy_engine.py \
  tests/test_neb_execution_gate.py -q -ra
结果：59 passed，exit 0

python -m scripts.neb_agent.path_quality_cli --help
结果：exit 0

python -m scripts.ts_strategy_engine.cli --help
结果：exit 0
```

测试全部使用 mock、内存对象或 pytest 临时目录；没有执行真实 SSH、LSF、bsub、bkill、VASP、NEB、数据库写入或 migration。

## 5. 等价性结论

五入口共享同一科学 evaluator；可比较的科学结果均为 `IDENTICAL`。碰撞和磁性异常因权威归属分别在 geometry/pilot 层，只能做职责边界等价验证，结果为 `SEMANTICALLY_EQUIVALENT`，不存在科学字段差异或第二套 path-quality 判定。
