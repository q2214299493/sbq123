# State Handoff 与未决治理事项

两树各自通过正式 propose 流程登记此次历史验收。投入待审的动作是在 `docs/08_HISTORICAL_RESULTS.md` 追加 A.2.6 结果，并更新受管理的投影清单。研究者可分别选择 `approve` 或 `reject`。

| 工作树 | 当前待审提案 | 本次 safe-only 结果 |
| --- | --- | --- |
| 开发 | `proposal-ba754199d145d12f978c90da` | 退出 2。旧事件绑定的 `configs/kinetics/scientific_intake.schema.json` 哈希与现场不同。 |
| 发布 | `proposal-77cfa10f887fe1a56d0927e8` | 退出 2。历史压缩事件绑定的 `docs/02_CURRENT_STATE.md` 源文件已变更。 |

开发树额外核实 reaction_network 模块记录的旧来源。发布树还核实 transition_state_search 受管理行漂移，以及 TS、kinetic_data 和 reaction_network 事件的证据先决条件。发布树的 TS 行期望哈希为 `f3f03bb7b41b2fddcc5883521c5c10dda58baea3fef97c3455e773cc50905fd0`，当前为 `8e98d61bb3f91afe73c2a4b6527abff15c26c6aa372f68aa4d3e9a109d73512c`。[按工作树列出的原事件、目标、期望与实测哈希](governance.json)

复核人需判定现行文件修订的来源，以及旧历史区段或模块行是否仍可投影。需要反映新证据时应提交继任事件。启动审计在开发树得到 0 错误、81 警告，在发布树得到 1 错误、80 警告。发布树启动错误指向上述受管理 TS 行。

本次未选择提案决定。对照 propose 和 sync 前后的历史事件、清单、State Handoff 证据及选定状态文件，开发树的 464 条记录、发布树的 326 条记录均保持原值，唯一增加的是本次历史事件。两次全仓与专项测试前后，两个工作树各自的 Git 状态清单字节一致。
