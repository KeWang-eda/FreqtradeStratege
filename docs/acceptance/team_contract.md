# 本轮阶段接口与文件归属

基线为 Phase 0 冻结的 `5ce05d6`。用户补发完整 Phase 3–6 后启用独立 Agent；Phase 0–2 的先期工作由主线程顺序完成，没有虚构早期并行结果。

| 负责人 | 独占范围 | 输出 / 依赖 |
| --- | --- | --- |
| Agent A；之后承担 B 的独立复核任务 | 只读快照、适配器、比较器和相应测试；`adapter_independent_review.md` | 报告阻断缺陷和真实复现，核心修复由主线程集成 |
| Agent C | `tools/audit_historical_coverage.py`、`tests/unit/test_historical_coverage.py`、Phase 3 报告/机器清单 | 只读数据；`minimum_scope_ready` 明确 BTC/ETH 既定区间是否具备完整原始数据与 metadata |
| Agent D | 独立验收 runner、`test_mode_isolation_acceptance.py`、Phase 4–5 报告与工件 | Phase 3 最低数据范围和 Phase 2 阻断修复通过后正式验收；先准备，不提前标 PASS |
| 主 Agent | 共享核心、原 Phase 0–2 测试、Phase 0–2/最终文档、集成 | 冲突控制、阶段门槛、全量检查、策略指纹、提交 push |

受并发槽位限制，B 作为独立任务由 A 完成适配器复核后接续执行；未声称同时运行四个子 Agent。不得跨越上表范围修改文件；需要共享改动先通知主 Agent。

稳定接口：snapshot schema 仍为 1，只加强验证，不添加默默回退；审计 JSON 明确 `completed/exit_code/denied_operations/http_requests/socket_events/process_events`；比较 JSON 明确 `passed/differences/comparison_policy`。数据审计将行情可用性与 metadata 范围分开，不据其他币缺规则否定 BTC/ETH 的已验证范围。

全量比较必须读取唯一原生 `_config.json`，不豁免训练/特征/模型/交易所配置。为和历史联网参考保持配置一致，受验离线运行也加载同一 mihomo overlay；它仅提供相同的配置值，离线客户端仍拒绝 HTTP，系统网络被隔离。实际离线使用可不配置代理，但不能将不同配置作为“严格同配置”对照。原始工件比较通过后才发布脱敏副本；路径脱敏过程及 SHA 单列，不能隐藏交易差异。

新证据仅使用项目相对路径与环境变量命令，不公开用户名/本机绝对根；原始运行证据保留本机，对外副本明确脱敏。旧的历史验收目录不删除。阶段结论统一为 PASS/PARTIAL/BLOCKED/FAIL，失败尝试保留并解释；无 skip 才能把对应隔离检查算作已执行。
