# 9924387：独立C3低力候选包与单独复核

2026-11-09，Asia/Shanghai。用户授权仅为利用现有服务器数据建立24帧的独立来源绑定并复核，原512包保持冻结。没有训练、模型推理、新DFT、结构优化、注册或科学结果推广。

## 实际产物

本地候选目录：
`calculations/fe110_reico_pilot300_20261022/c3_lowforce_candidates_20261109_v1/`。

- `source/`：9924387的OUTCAR、XDATCAR、OSZICAR、POSCAR、CONTCAR、INCAR、KPOINTS及script.lsf原始字节快照。8个文件逐项远端/本地SHA核对；POTCAR只记录远端哈希，不复制正文。
- `structures/`、`force_tables/`：24份高精度轨迹结构及原始力表字节。
- `labels/source_labels.json`、`candidate_manifest.json`：逐帧结构/标签哈希、原始力表字节范围、作业/父作业/family、单位、SCF和磁性审核范围。
- `all_frame_qc.json`、`isolation_review.json`、`deduplication_review.json`：133帧物理质控及选帧依据。
- `provenance/`：父作业续算计划、原提交回执及原生PEND证据的原始文件副本。
- `reserved_geometry_binding.json`：只用于隔离的513份几何及依赖文件哈希，不导出保留集力或能量。
- `independent_verification.json`、`candidate_review.json`：分开的原始力/坐标回放与来源、隔离、去冗余复核结果。
- `frozen512_verification.json`：原manifest、两个数据库、两个metadata文件的前后哈希。

候选manifest SHA256：
`0e4eec5a48c5ed084bfdc230852226ac2f0b2ca55489c39d389fd58b18704c6a`。

## 结果

原始133帧均通过坐标—力、SCF、正Fe局域磁矩和完整C3连接检查。24份物化结构重新对应原始XDATCAR，最大坐标序列化误差4.070144838902081e-15 Å；24份原始力表的字节范围、六列表及ASE独立力数组一致。

主审核对133帧与210个同组成保留几何完成27930次比较，使用36个真实表面对称和同元素置换，0.20 Å下无冲突。单独复核对24份实际物化结构再完成5040次比较。当前78开发、53保留测试及16观察隔离帧的几何均包含在513份参考内。

规范去冗余同时要求同作业几何距离≤0.02 Å及最大逐原子力差≤0.02 eV/Å。133帧中14帧冗余；32个≤0.05 eV/Å低力帧保留24个。独立回放得到相同的成员和顺序：

`15,82,84,90,91,92,97,99,104,106,110,114,115,116,118,119,121,123,124,125,126,128,131,133`。

父作业9922624的CONTCAR哈希与9924387输入POSCAR完全相同；原提交bundle绑定一致。新样本名含job9924387，避免与父轨迹的相同离子步编号碰撞。保留family_0099及reico_family_0099训练分区血缘；这24帧不是24个独立极小值，不能作为新的盲测家族。

## 范围和未执行项

所有帧保持`LOCAL_MOMENTS_REVIEWED_POSITIVE_FE`范围；没有声称全局磁基态、吸附能精度或优化加速。仅第133帧达到0.02 eV/Å；其余是合法的过程力标签候选。

历史LSF终态缺失继续如实记录为null/Unknown，原生提交PEND证据单独保留，不制造DONE。本包走力标签候选审核，不调用正式吸附能登记的DONE门，也不放宽原有登记协议。

三阶段输出均不代表正式训练数据准入：`training_authorized=false`、`merged_into_existing_manifest=false`、`accepted_endpoint=false`、`reportable_final_energy=false`。未创建训练数据库、heldout loader或可执行训练请求。原512/78/53和16帧隔离、模型、注册库及工作簿未改动。

## 复现与验证

在现有canonical work运行环境中：

```powershell
python -m archive.fe110_c3_lowforce_candidates_20261109.prepare
python -m archive.fe110_c3_lowforce_candidates_20261109.verify
python -m archive.fe110_c3_lowforce_candidates_20261109.review
```

原始源文件及现有产物按字节复用，遇不同内容拒绝覆盖。源码路径/hash改变需新的复核绑定，不编辑既有证据来伪装一致。隔离参考按哈希绑定现有只读本地几何；移动工作区时需保留或明确重新绑定这些来源。

已执行语法、限定Ruff及24项直接相关回归，全部通过；另完成上述24份真实标签与高精度结构回放，以及5040次独立隔离比较。没有运行全仓库测试，也没有为验证启动任何科学计算。

下一步仅为单独决定是否将这些候选纳入新的数据包；不自动修改冻结512包或启动训练。
