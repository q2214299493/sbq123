# P3 第一组 Windows 验收回执

发布基线 `046dd867f6e75a021263f9fa32f4bbd49ae81935`。开发树 HEAD 为 `233d5a6c`，保留了未提交的工作。交付补丁 SHA-256 为 `bd1a170cc74568238225d326ff2800e936b72168186fb767f5ef9aea5cd44e41`，与交付清单和说明一致。两树的 git apply --check 通过；在独立发布树使用 git am 得到 `1edf9364dba8d4b18b43c9da23447d489113284d`，树对象为交付声明的 `349f8bc59bde6ca7d3ac98d870072601acf60019`。开发树应用同一补丁。交付包的三个 Linux 报告在两树均逐字节一致。

| 检查 | Windows 开发树 | Windows 发布树 |
|---|---:|---:|
| 修改前四组 DRC 回归 | 137 通过 | 137 通过 |
| 单独复核 pilot plan | 1 通过 | 1 通过 |
| 修改后交付要求的全部用例 | 140 通过，0 失败 | 140 通过，0 失败 |
| 强连通分量 | 3 → 2 | 3 → 2 |
| 模块 / 导入边 | 329 / 1151 → 330 / 1156 | 288 / 1047 → 289 / 1052 |

按交付包 verification/snapshot.py 在每树的前、后现场分别执行。22 个原函数的 AST、21 个正反行为探针和 9 类 CLI 调用结果均相同。4 份 comparison.md 的渲染字节与归档一致，覆盖 phase3_2_0、phase3_2_0_1、phase3_2_0_2/coarse 及 fine。五个改动 Python 文件的 Ruff、py_compile 通过。旧公开导入复用记录模块的实现；执行、时钟、预算、停首错和 CLI 在原编排层。剩余两组循环是批次与灵敏度。

Linux 独立快照记录修改前 136 通过、1 失败，修改后 139 通过、同一项失败。`test_pilot_plan_is_reproducible_without_native_execution` 的 desorb/minus 0.005 eV 正向系数差 1 ULP。Windows 两树基线及本组修改后都通过此测试。根因仍待跨环境复核，单独记录于 backlog-kinetic-rate-identity-20261121；原始速率、运行 ID、批准哈希及断言均未调整。所有检查均离线，未写生产 SQLite。
