# INCAR 调参建议

## 当前判断

- 状态：`{status}`
- 计算类型：`{calculation_type}`
- 材料/表面族：`{material}` / `{surface_family}`
- 失败类型：`{failure_type}`

## 是否适合通过 INCAR 调参解决

{fit_message}

## 推荐修改

| 参数 | 原值 | 新值 | 原因 |
|---|---|---|---|
{rows}

## 不建议自动修改

不要自动关闭自旋、发明 DFT+U 或氧化物磁序、改变 POTCAR/泛函、修复原子映射，或用 INCAR 掩盖碰撞和错误路径。

## 下一步

`{next_action}`

## 风险与缺失证据

{warnings}

本报告未提交或运行 VASP。
