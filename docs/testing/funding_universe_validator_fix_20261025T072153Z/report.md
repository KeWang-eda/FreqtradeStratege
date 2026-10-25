# Funding / Point-in-Time Universe 验证器完整性修复

生成时间：2026-10-25T07:21:53Z UTC。

## 结论

- Funding 验证器完整性修复：PASS（合成 fixture 与直接相关回归通过）。
- Point-in-Time Universe 验证器完整性修复：PASS（合成 fixture 与直接相关回归通过）。
- 真实历史 Funding 证据：BLOCKED。现有本地 1h 文件仍不是可验证的 payment-event 证据。
- 真实历史 point-in-time universe：BLOCKED。当前 exchangeInfo 快照仍不能证明历史状态。
- 正式研究准入：继续 BLOCKED。

## 修改范围

修改文件：

- `src/quant_strategy/research/evidence.py`
  - Funding 事件身份和规则边界统一使用解析后的 UTC 时间。
  - 规则匹配同时检查 venue、instrument_id、settlement_rule_id、settlement_rule_version 和有效区间。
  - 区间重叠/空档按完整规则身份分组。
  - 覆盖必须来自独立 `coverage_documents` 原始来源，不再信任包内 `expected_event_times`。
  - 分离 `source_integrity_status` 与 `source_authority_status`。
  - 需要独立 authority document；`source_type`/`evidence_grade` 单独不足以证明权威性。
  - 校验哈希原始记录中的 source_record_id、时间、费率、venue 和 instrument 内容。
  - Universe 没有 candle_times、存在未知状态或窗口内 as-of 缺口时保持 BLOCKED。
- `tools/validate_evidence.py`
  - 保留现有 CLI，并支持精确 Mark 时间输入。
- `tests/unit/test_evidence_packages.py`
  - 新增 UTC offset、规则身份隔离、独立权威证明、独立覆盖来源、原始记录内容一致性和 Universe candle 覆盖回归。

未修改生产策略、标签、特征、模型、生产配置或正式准入逻辑。

## 测试证据

- `tests/unit/test_evidence_packages.py`：退出码 0，22 passed，0 failed，0 skipped。
- `tests/unit/test_controlled_governance.py`：退出码 0，21 passed，0 failed，0 skipped；证明既有 Funding/universe gate 行为未被削弱。
- `python -m py_compile ...`：退出码 0。
- `git diff --check`：退出码 0。
- Ruff：未执行；本地没有可用 Ruff executable，不能声称 Ruff 通过。

## 剩余限制

本轮所有 PASS 均来自合成证据和现有治理回归。没有下载或调用交易所 API，也没有制造真实历史来源。当前仓库没有独立权威 Funding payment archive、规则变更证据或历史合约状态区间，因此验证器会正确返回 BLOCKED，不能解除正式研究锁定。

详细机器记录见 `commands.json` 和 `test_results.json`。
