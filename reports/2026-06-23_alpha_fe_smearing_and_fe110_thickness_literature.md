# alpha-Fe 展宽收敛与 Fe(110) 文献厚度

日期：2026-06-23（Asia/Shanghai）。

## alpha-Fe bulk 测试设置

- conventional bcc，2个Fe原子，`a=2.8665 A`
- `ENCUT=400 eV`，Gamma `15x15x15`
- `ISPIN=2`，`MAGMOM=2*2.2`
- 8个静态作业：`9542651-9542658`
- 远程目录：`~/sbq/agent/jobs/convergence/alpha_fe_bulk_smearing_20260623`

全部作业为 `DONE`，OUTCAR 均正常结束，未检出致命电子错误关键词。

## 展宽结果

| ISMEAR | SIGMA (eV) | 相对 ISMEAR=-5 的能差 (meV/atom) | 绝对熵项 (meV/atom) | 两原子磁矩 (mu_B) |
|---:|---:|---:|---:|---:|
| -5 | 0.05（忽略） | 0.000 | 0.000 | 4.4805 |
| 0 | 0.05 | 0.488 | 1.522 | 4.4785 |
| 0 | 0.10 | 0.400 | 5.752 | 4.4853 |
| 0 | 0.20 | 0.265 | 20.652 | 4.4884 |
| 1 | 0.10 | 0.490 | 0.239 | 4.4826 |
| 1 | 0.20 | 0.275 | 1.323 | 4.4811 |
| 1 | 0.30 | 0.586 | 0.280 | 4.4712 |
| 2 | 0.20 | 0.518 | 1.417 | 4.4864 |

所有方案的零展宽能差都小于 `0.6 meV/atom`。综合能量、熵项与不必要的展宽宽度，bulk 优化推荐 `ISMEAR=1`、`SIGMA=0.10 eV`；最终静态 bulk 能量推荐 `ISMEAR=-5`。磁矩变化小于 `0.009 mu_B/atom`，未观察到磁态改变。

## 文献中的 Fe(110) 层数

alpha-Fe bulk 是三维周期体系，本身不存在 slab 厚度。层数只适用于由 alpha-Fe 切出的 Fe(110) 表面。

| 代表性研究 | 用途 | Fe(110) 层数 | 固定/松弛信息 |
|---|---|---:|---|
| [Xu et al., Surface Science 667 (2018)](https://www.osti.gov/biblio/1398766) | 原子和分子吸附 | 4 | 四层周期 slab |
| [Hu et al., Coatings 8, 51 (2018)](https://www.mdpi.com/2079-6412/8/2/51) | H2O/H+/Cl-/OH- 吸附 | 4 | 固定底部2层 |
| [Wong et al., Chem Catalysis (2022)](https://www.cell.com/chem-catalysis/fulltext/S2667-1093(22)00154-3) | Fe(110) 电催化反应 | 4 | 固定底部2层 |
| [Slezak et al., Phys. Rev. Lett. 99, 066103 (2007)](https://link.aps.org/doi/10.1103/PhysRevLett.99.066103) | Fe(110) 表面声子 | 5 | 五层 slab |
| [P adsorption on Fe(110), J. Phys. Chem. C (2018)](https://pubs.acs.org/doi/10.1021/acs.jpcc.8b08831) | P吸附与表面性质 | 5 | 文中报告功函数在5层收敛 |
| [Wei et al., H2/Fe(110) (2025)](https://www.osti.gov/servlets/purl/2586650) | H2解离吸附 | 5 | 2x2五层 slab |
| [Jiang and Carter, Phys. Rev. B 71, 045402 (2005)](https://link.aps.org/doi/10.1103/PhysRevB.71.045402) | C吸附、表面/体相扩散 | 7 | 七层 slab |
| [Chakrabarty et al., J. Appl. Phys. 120, 055301 (2016)](https://arxiv.org/abs/1603.04662) | CO吸附、解离与有限尺寸效应 | 8 | 上5层全松弛，另3层仅法向松弛 |

在这8篇代表性原始研究中，6篇采用4或5层，因此**一般吸附计算的主流厚度是4-5层**。但涉及C插入Fe晶格、CO解离势垒或有限尺寸效应时，代表性研究采用**7-8层**。

## 对当前工作的结论

- 当前5层、固定底部2层的Fe(110)属于文献常见吸附模型，可继续用于路径开发和日常NEB。
- 5层测试不能证明CO解离势垒已达到发表级厚度收敛。
- 普通NEB得到可信路径后，应对同一IS/TS/FS至少补做7层或8层静态复核；只有差分势垒稳定后，才需要考虑是否整条更厚slab NEB重算。
