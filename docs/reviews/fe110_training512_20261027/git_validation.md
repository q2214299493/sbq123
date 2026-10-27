# Git空白检查说明

默认 `git diff --cached --check` 对两份原样复用的历史依赖提示文件末尾空行：`scripts/adsorption/force_role_runtime.py:70`、`scripts/adsorption/role_force_trainer.py:56`。这不是语法、测试或科学数据检查失败。为保持已经绑定并提交用户确认的请求 fbc1fb2d7b8753e5429db2253559cff5a68669a0f620eebe515f01ad6c1c84e7，保留源字节，没有修改请求、输入或哈希。

本次限定忽略 `blank-at-eof` 后的Git空白检查通过；默认检查的两条提示明确保留。语法、限定Ruff及两份工作区各44项测试通过。
