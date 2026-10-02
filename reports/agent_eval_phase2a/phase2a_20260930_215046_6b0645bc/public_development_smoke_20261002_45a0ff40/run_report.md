# 公开开发集受控试运行

- evaluation_mode = public_development_smoke
- reference_access_isolation_verified = false
- capability_improvement_established = false

使用 286ad0c 的 revision_03_user_approved_20261001；public_sha256 = 500d33ac92a838371e1f76e096e6bc0db95ec8d864c0993495a2467a191d9ba2。

## 执行

Codex CLI 0.159.0-alpha.12.1，新建独立 exec 任务，不使用 resume/fork，也未提交当前审核对话。CLI 模型配置为 gpt-6.1-sol、reasoning effort high、service tier default；可见事件未提供后端实际模型快照标识，记为未知。耗时 52.164 秒，CLI 退出码 0，未超时。一个答题任务、一个完成回合；底层模型请求数未知，不能写成一次模型请求。

三个公开文件以完整文本一次性提交，输入文本和文件哈希已保存。单次配置禁用了可关闭的搜索、连接器、Shell/统一命令执行、记忆、多代理、插件、Hook、浏览器、计算机操作、图像、Code Mode、技能搜索等功能；忽略用户配置、零字节项目指令、跳过主机技能发现，使用 read-only 沙箱，不绕过规则、不提升权限。完整 argv 见 control/execution_settings.json。用户全局配置及登录凭据文件内容前后哈希一致。未安装服务或框架。

## 原始结果与可见活动

首次原始回答：control/first_raw_answer.txt；完整 CLI 可见 stdout 事件：control/first_events.jsonl；stderr：control/first_stderr.txt。没有重新生成、补答或修正答案。预先约定的机械提取只接受整个 JSON 或整个响应唯一 JSON 围栏；此次是直接 JSON，评分输入 control/answers.json 与原始回答逐字节相同。

可见事件中只有 thread.started、两条启动 warning/error item、turn.started、一条 agent_message、turn.completed；未观察到命令、连接器或其他工具调用，也未观察到私有参考读取。整体污染状态未知：可见事件没有完整后端输入/工具能力快照，不能证明不存在外部上下文注入或技术上不可能访问参考。两条启动 item 分别是未稳定技能开关告警、Code Mode 关闭后不可用；另有 PowerShell shell snapshot 告警。均原样保存，未启用功能或重跑来消除告警。

## 接口评分

现有 cases-evaluate 调用一次，退出码 0。integrity_ok=true、comparison_ready=true；完整性错误/缺失回答为0，5题可评分，3题匹配。comparison_ready 只表示评分器的数据与参考条件满足，不表示隔离通过。

| 案例 | 原评分状态 |
| --- | --- |
| c001 | match |
| c002 | diagnosis_mismatch |
| c003 | match |
| c004 | match |
| c005 | diagnosis_mismatch |

c002、c005 仅 root_cause_status 与参考不同：首次回答 confirmed，参考 hypothesis。此比较只发生在独立答题结束后的评分阶段，没有据此修答案。实际原评分报告：control/score_report.json；执行参数和退出码：control/scoring_execution.json。

## 边界与未验证

结果限于五题、单反应组、已公开开发/回归集的接口试运行；不是严格隔离能力基线，未建立能力改善或跨反应泛化。后端完整上下文、实际模型快照标识、底层请求次数、参考访问技术隔离仍未验证。

28份原 revision 产物哈希保持不变，两个代码/发布工作树 HEAD 和干净状态未变。不修改源码、科学标准、题面或参考；不访问生产数据库，不运行 SSH/HPC/VASP/GPU/Sella 科学计算或训练、不运行 sync、不 commit/push/merge。仅新增本轮本地产物和 CLI 自身的任务运行状态文件。

下一步：保留本次原始结果供复核，不用其宣称诊断能力提升。
