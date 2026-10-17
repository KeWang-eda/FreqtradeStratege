# 量化训练可信度治理：本轮总报告

**最终结论：FAIL，不允许开展正式样本外模型研究。** 本轮确实修复了研究数据构建问题，新增了自动化契约、防泄漏检测和正式训练拒绝入口；但原生 FreqAI 训练与早停验证之间仍存在标签跨界。你已明确选择“保留现有生产训练，本轮准入据此判 FAIL，列明修复方案”，因此没有修改生产模型，也没有越过失败 Gate 执行后续阶段。

**这份文档是本轮唯一的人类阅读入口。** 测试、JSON、Parquet 与命令记录保存在 `docs/acceptance/training_readiness_20261017T135525Z/`，属于证据附件，无须逐个阅读。旧离线回测报告不作为本轮训练可信度通过证明。

## 1. 六阶段实际状态

| 阶段 | 本轮状态 | 实际完成与阻断原因 |
| --- | --- | --- |
| Phase 1 数据治理 | PASS，有明确范围 | 研究样本身份、排除原因、缺口隔离、只读与重建验证通过；216 份数据均有审计结论。未知 funding schedule 明确隔离，不代表原生资金费率数据全面准入 |
| Phase 2 防泄漏 | **FAIL** | BTC/ETH 研究特征精确扰动/截断通过；原生训练/早停验证各存在 3 个标签跨界，违反零违规要求。完整原生展开与跨币动态审计也未完成 |
| Phase 3 切分与 Walk-Forward | BLOCKED | 前置 Gate 失败，未实施或宣称本轮完整三种切分、holdout 解锁及真实逐折验收 |
| Phase 4 模型与交易评估 | BLOCKED | 未启动本轮正式多折模型/朴素基准/成本后交易/不确定性评估，不引用旧收益作为新结论 |
| Phase 5 实验与复现 | BLOCKED | 未越过前置 Gate 实施新实验管理验收；已有实现的缺口保留为下一阶段任务 |
| Phase 6 独立总验收 | **FAIL** | 总验收程序实际执行，返回退出码 1，明确拒绝正式研究；正式训练入口也实际拒绝并返回 2 |

**398 项自动化测试通过，和正式准入失败是两件事。** 测试证明故障能被检测和准入能被拒绝，并不证明原生训练问题已经修好。本轮未完成全部六阶段的工程准入；受阻部分没有被算作 PASS。

## 2. 当前仓库与实际生效设置

起点为 `main@a378f7e`，首次检查工作区干净。随后新增的文件和修改均为本任务产生，未 reset/checkout/clean，未丢弃用户改动。旧报告中的 `0c31df8 / 298 passed` 只作历史参考；本轮在起始代码上重新执行，结果确为 **298 passed / 0 failed / 0 skipped，52.70 秒**。

| 项目 | 独立研究默认配置 | 生产 FreqAI 配置 |
| --- | --- | --- |
| 标签 | raw，未来 close-to-close 收益 | volnorm，未来收益除以当前 ATR(14)/close |
| K 线 / 预测跨度 | 4h / 3 根 | 4h / 3 根 |
| 特征 | 实际 26 列；周期 6/14/24，无可选技术指标 | 原生相关币/shift 展开；本轮未将 26 列等同于完整展开 schema |
| 训练与评估 | 默认 Ridge；purged walk-forward 3 折、embargo 3、最终 holdout 15% | XGBoostRegressorES；训练 365 天、回测窗口 7 天；内部 test_size=0.2、shuffle=false，用于早停 |
| 本轮正式模型选择 | 未启动 | 未修改原有训练 |

实际环境：Python 3.13.13、Freqtrade 2026.7、CCXT 4.5.75、pandas 3.0.5、NumPy 2.5.2、XGBoost 3.4.1、scikit-learn 1.9.0、pytest 9.1.1、Ruff 0.15.22。未升级依赖。

## 3. 已解决的问题和代码改动

先写的失败测试真实复现了：跨缺失 K 线构造标签、缺少逐行样本身份/排除清单、非法 metadata 被接受、零有效样本币种被其他币掩盖等问题，首轮 **6 failed**。另一个失败测试证明：原数据集哈希不包含特征列名，修改特征语义后哈希仍相同，结果 **1 failed / 2 passed**。修复后这些测试及全量测试通过，红测试记录保留。

| 文件 | 已实施的修改 |
| --- | --- |
| `market_data/contracts.py` | futures/mark/funding 契约；UTC 时间网格、单位、缺失范围、真实内容与有序 schema 指纹；未知 funding schedule 返回 BLOCKED |
| `market_data/validation.py`、`loader.py` | 非数值和 bool 字段拒绝；读取前后核对文件 SHA，检测读取期间修改 |
| `dataset/builder.py` | 稳定 sample_id/data_version、特征与标签时间；在断档处拆连续段，重置递归状态；跨缺口标签与 warm-up 样本逐行排除；空有效样本币种明确失败 |
| `experiments/runner.py` | 数据集哈希纳入列名、列序、dtype 和内容；记录读取/溯源之间输入变化；保存逐行排除清单。未提前实施 Phase 5 完整比较体系 |
| `validation/feature_contracts.py` | 每个研究特征的来源与最早/最晚依赖、close 可用时间；实际扰动/截断检测；未知、未审查或只有 NaN 证据的特征 BLOCKED |
| `validation/native_boundaries.py` | 调用实际安装的 DataKitchen 过滤/拆分方法，用真实标签完成时间核查原生隔离边界；不替换原生方法 |
| `tools/audit_training_data.py` | 216 数据源只读审计、实际研究样本与排除清单、输入/配置/数据集指纹 |
| `tools/accept_training_readiness.py` | 核对真实 JUnit 和退出码，重验原始输入与数据契约、重建样本，运行研究/原生边界检查，逐阶段阻断并输出机器结论 |
| `validation/admission.py`、`cli.py` | 新增显式 `formal-run --readiness`，在模型调用前拒绝 FAIL/PARTIAL/BLOCKED、缺失或不完整准入凭证 |

没有修改 `MyStrategy.py`、生产策略回调、特征公式、标签定义、`freqaimodels/`、原训练器/预处理器、配置中的模型参数或交易规则。生产代码/配置保护 diff 为空。未修改原始行情、全局网络、TLS 或虚拟环境源码。

原 `run` 作为既有研究命令保留；它的成功不构成正式准入。`formal-run` 是新增的正式受控入口，不是防止用户手动绕过程序的安全沙箱。

## 4. 数据与样本验收结果

| 检查项 | 实际结果与解释 |
| --- | --- |
| 原始数据范围 | 72 币 × futures/mark/funding，共 216 份实际文件 |
| 基础契约 | 144 份 futures/mark PASS；这里检查的是各文件已有观察区间，不表示任意回测窗口完整 |
| funding | 72 份 BLOCKED：现有文件没有已验证历史付款时刻表；不把观察到的 8h 或文件名 1h 当作已证明 schedule，不补零 |
| 研究输入 | 现配置 BTC/ETH 各 14880 行，均无内部时间缺口 |
| 有效研究样本 | 各 14853，总计 **29706**，26 列特征 |
| 排除样本 | 各 27：24 个特征 warm-up、3 个尾部标签不完整；合计 54，每行有 ID、币种、版本和原因 |
| 可用时间 | K 线 timestamp 表示 open；特征在 open+4h 可见；标签在未来第 3 根 K 线收盘完成 |
| 合法样本违规 | 已构建的有效样本中身份重复、时间边界违规为 0 |
| 文件和样本复现 | 读取前后 SHA 检查、原始输入复核与独立数据集重建通过；交换币种输入顺序不改变样本 |

缺失率没有全局必须为零的门槛。整 bar 缺口被识别后隔离受影响样本；乱序、重复、错网格、NaN/Inf、非法价格、负数量、非数值、有效样本为零等情况明确失败。故障注入只修改内存或临时副本，没有改真实源文件。

旧文件未记录真实采集时间，报告保留 `captured_at=null`，审计时间不冒充采集时间。单位按源格式声明，未推测额外换算或历史规则。数据版本和文件 SHA 也不能证明外部来源签名或历史完整性。

## 5. 防泄漏实际证据与阻断根因

研究链路：对真实 BTC/ETH 各 600 根数据、实际 26 列特征，各执行 3 个截断点 × 未来扰动/截断两类检查，均为 **6 项检查、0 差异**。阈值预先定为 `rtol=atol=0`，相同确定性前缀必须精确一致。故意加入 future shift、全局均值、backfill 和约 `1e-13` 的未来依赖均能检出。递归指标依赖从连续段起点开始，不能错误地只标注为最近 N 根。

原生问题来自 `BaseRegressionModel.train → DataKitchen.filter_features → make_train_test_datasets → sklearn.train_test_split(shuffle=false)`。已标注样本直接按 80%/20% 拆分，没有按标签完成时间 purge。XGBoostRegressorES 使用该 test 集进行早停，因此它是早停验证集，不能称为未接触的外层最终测试集。

真实 BTC/ETH 最近 600 根中，早停验证可用时间均从 `2026-09-26 12:00 UTC` 开始，训练集内以下 3 个样本越过边界：

| 原始行位置，每币相同 | 样本 open UTC | 标签完成 UTC | 判断 |
| --- | --- | --- | --- |
| 479 | 2026-09-25 20:00 | 2026-09-26 12:00 | 等于隔离边界，必须 purge |
| 480 | 2026-09-26 00:00 | 2026-09-26 16:00 | 超过边界 |
| 481 | 2026-09-26 04:00 | 2026-09-26 20:00 | 超过边界 |

BTC/ETH 合计 **6 个违规样本**，零违规硬门槛失败。这是训练/早停验证隔离问题，不等同于证明实盘预测看到了未来回测行情；原生先截取外层训练历史、再生成标签，末 3 行标签缺失，这一外层机制检查正确。

本轮原生诊断运行的是实际 DataKitchen 方法和真实数据，没有用 mock 替代拆分。它使用基础特征定位边界问题，**不声称已完成原生 92/136 列展开、跨币相关特征及排名的全面动态审计**。研究预处理隔离既有测试本轮重新执行通过，也不替代完整原生拟合边界验收。

## 6. 测试、命令、退出码与产物

最终完整测试：**398 passed / 0 failed / 0 skipped，55.69 秒**。Lint 通过，95 个 Python 文件格式检查通过；867 条依赖弃用 warning 保留，没有屏蔽。类型检查未配置，不算通过。

交付复核确认 91 份已测试代码与 216 份原始数据的 SHA 均未变化，命令记录、JUnit 和 Gate 产物指纹一致。源码、测试、工具与阅读文档的 `git diff --cached --check` 通过；包含全部证据附件时返回 2，仅因两次失败测试的原始日志/XML 保留了 pytest 堆栈自带的行尾空格，没有为格式检查重写失败证据。

本轮新增测试文件：

| 文件 | 职责 |
| --- | --- |
| `tests/unit/test_training_data_contracts.py` | 源类型、时间网格、指纹、缺失/funding 规则 |
| `tests/unit/test_sample_governance.py` | 样本身份、边界、排除、断档、零样本与只读 |
| `tests/integration/test_dataset_governance.py` | 实际数据重建、读取中变化、schema 哈希 |
| `tests/leakage/test_feature_time_contracts.py` | 依赖契约、未来扰动/截断、微小泄漏注入 |
| `tests/integration/test_native_training_boundaries.py` | 原生真实拆分缺陷、外层尾部、shuffle 检出 |
| `tests/unit/test_training_readiness_gate.py` | 证据篡改、缺失、skip、P0 否决和独立重建 |
| `tests/integration/test_formal_training_admission.py` | 正式入口在任何训练前拒绝非法凭证 |

| 本轮命令/检查 | 退出码 | 实际结果 |
| --- | ---: | --- |
| 起始完整 pytest | 0 | 298/0/0，新执行，不是复制旧报告 |
| 首轮样本治理红测试 | 1 | 6 failed；旧代码缺口已被证明 |
| schema 指纹红测试 | 1 | 1 failed / 2 passed；旧哈希遗漏列名 |
| 修复后 Phase 1 定向 | 0 | 94/0/0 |
| 最终完整 pytest | 0 | 398/0/0 |
| 数据源与样本审计 | 0 | 29706 个样本；144 PASS/72 funding BLOCKED |
| 独立总验收程序 | **1** | P1 PASS/P2 FAIL/P3–5 BLOCKED/P6 FAIL，准入 false |
| 使用该凭证执行 formal-run | **2** | 模型调用前拒绝，未创建训练输出目录 |
| Ruff / format / 保护 diff | 0 | 通过；生产策略、模型、配置未变化 |

完整测试包含既有研究小样本训练和原生离线回测回归，它们是兼容性复验；**不是前置 Gate 失败后新开展的 Phase 3–5 正式模型评估**，本轮没有从它们选择模型或获取新正式 holdout 结论。

中间 390、397 项通过属于新增正式入口/缺证据测试前的运行，保留记录但不相加、不作为最终统计。第一份数据报告未包含输入配置文件 SHA，随后在新目录重新完整审计，旧报告作为 attempt1 保留，没有补写参考结果冒充原先记录。

### 从项目根复现

当前机器已有环境在相邻目录。输出目录每次新建，下面同一个 shell 中的变量可以连续使用；数据仍从本地读取。

```bash
export FREQTRADE_PYTHON="$PWD/../freqtrade/.venv/bin/python"
export PYTHONPATH=src:.
readiness_run=$(mktemp -d)
"$FREQTRADE_PYTHON" -m pytest -q --junitxml="$readiness_run/tests.xml"
"$FREQTRADE_PYTHON" tools/audit_training_data.py \
  --output "$readiness_run/source_sample_audit"
```

总 Gate 还要求真实测试执行凭证 `test_run.json`。成功跑完上述 pytest 后生成与该 JUnit 绑定的凭证；不是手写一个 PASS 文件：

```bash
"$FREQTRADE_PYTHON" - "$readiness_run" <<'PY'
import hashlib, json, sys
from pathlib import Path
from xml.etree import ElementTree as ET
root = Path(sys.argv[1])
junit = root / "tests.xml"
suite = ET.parse(junit).getroot().find("testsuite")
assert int(suite.get("tests")) > 0
assert all(int(suite.get(k, 0)) == 0 for k in ("failures", "errors", "skipped"))
(root / "test_run.json").write_text(json.dumps({
    "command": ["python", "-m", "pytest", "-q", "--junitxml=tests.xml"],
    "exit_code": 0, "junit": junit.name,
    "junit_sha256": hashlib.sha256(junit.read_bytes()).hexdigest(),
}))
PY
"$FREQTRADE_PYTHON" tools/accept_training_readiness.py \
  --evidence "$readiness_run" --test-run "$readiness_run/test_run.json" \
  --output "$readiness_run/final_gate"
# 当前生产训练未修复，预期总 Gate 返回 1，而不是 0。
"$FREQTRADE_PYTHON" -m quant_strategy.cli formal-run \
  -c configs/base.yaml -c configs/environment/local.yaml \
  --readiness "$readiness_run/final_gate/readiness.json" \
  --output "$readiness_run/formal_training"
# 预期返回 2，且 formal_training 不会创建。
```

`--phase 1/2/3/4/5/6` 可查询指定阶段及其前置 Gate；失败前置会阻断后续，不会用空壳 PASS 通过。Phase 3–5 的新正式实现/验收仍待恢复工作后完成。

## 7. 独立总验收和证据入口

主要产物均属于本轮：

- [总验收 JSON](acceptance/training_readiness_20261017T135525Z/final_gate/readiness.json)：实际逐阶段结果及准入 false。
- [数据质量与样本报告](acceptance/training_readiness_20261017T135525Z/source_sample_audit/phase1_data.json)：输入/配置/数据集 SHA、29706 样本与排除统计。
- 同目录 `sample_metadata.parquet`、`sample_exclusions.parquet`、`source_audit.json`：逐样本和逐数据源明细。
- [原生缺陷复现](acceptance/training_readiness_20261017T135525Z/native_boundary_reproduction.json)：BTC/ETH 实际违规行与边界。
- [最终 JUnit](acceptance/training_readiness_20261017T135525Z/quant-training-delivery-20261017T135525Z.xml)、[测试运行历史](acceptance/training_readiness_20261017T135525Z/test_history.json)：最终与失败尝试分开记录。
- [需求—测试追踪矩阵 JSON](acceptance/training_readiness_20261017T135525Z/requirement_traceability.json)：46 项逐条说明，测试 node ID、故障场景、单元测试结果与验收状态分离。

追踪登记覆盖 46/46；硬性验收项为 **17 PASS、2 FAIL、3 PARTIAL、24 BLOCKED**，通过比例 17/46，并非“全部完成”。这些统计与阶段 Gate 粒度不同：即使检测器单元测试通过，被检测的原生隔离要求仍为 FAIL。

## 8. 保留生产训练后的修复方案与下一步

本轮按你的选择不应用以下生产修复：在原生数据拆分后、任何特征/标签预处理 fit 前，根据每个训练样本实际 `label_end_time >= validation_start` 排除跨界行；同步处理 features、labels、weights 和索引，记录被 purge 的样本 ID。不能只在模型 fit 末端删行，因为预处理器届时可能已经看过这些行。

后续若授权实施，应独立变更并使用新的 FreqAI 模型缓存标识，避免与旧模型混用；保持标签、特征公式、模型参数及交易规则，真实比较修复前后预测、模型、订单和回测指标。预期结果可能变化，不能为追求历史交易一致而隐瞒差异。

完成该修复并通过 Phase 2 后，再按顺序补齐：完整原生展开/相关币扰动审计；三种真实切分及 holdout 程序保护；均值/不交易等基准、成本与不确定性评估；不可比实验拒绝、失败保留、两引擎独立复现。尤其是既有比较器并未满足本轮全部可比性治理要求，不能当作 Phase 5 已通过。

当前没有设置 Sharpe>1、准确率>60% 等通用门槛，没有访问最终测试结果来改阈值。本轮只使用零时间违规、零意外输入变化和精确特征不变性等工程契约；预测能力、成本后交易效果及生产运行准入均为 **BLOCKED/未验证**。

资料：当前实际安装的 Freqtrade `BaseRegressionModel/DataKitchen` 源码、本仓库特征与标签实现、[sklearn 防泄漏说明](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage)、[pandas 时间序列语义](https://pandas.pydata.org/docs/user_guide/timeseries.html)。

## 9. 完整需求—测试追踪表

以下“结果”是对应要求的验收状态。括号中的测试通过不能替代该要求所需的真实集成验收；空白测试表示尚未实施，不是 skip 或 PASS。

| Requirement ID | 硬性要求 | 对应测试 | 故障注入或未执行场景 | 实际结果 |
| --- | --- | --- | --- | --- |
| DATA-001 | 合法样本身份、币种、特征与标签时间及数据版本 | `test_every_input_row_has_eligibility_identity_and_exclusion_reason`（1 passed） | 伪造metadata、重复ID、倒置时间 | PASS |
| DATA-002 | 逐样本排除原因 | `test_every_input_row_has_eligibility_identity_and_exclusion_reason`（1 passed） | warmup不足与尾部标签不完整 | PASS |
| DATA-003 | 缺失funding不得补零 | `test_funding_missing_event_never_becomes_zero_rate`（1 passed） | 删除付款事件；未知或变频schedule | PASS |
| DATA-004 | 时间戳、频率、单位由契约验证 | `test_invalid_candle_grid_fails_closed`（6 passed） | 乱序、重复、错网格、无时区 | PASS |
| DATA-005 | 相同输入与配置数据集可重复 | `test_same_real_data_rebuilds_identical_schema_samples_and_exclusions`（1 passed） | 交换币种输入顺序后重建真实样本 | PASS |
| DATA-006 | 损坏、缺失或零有效样本必须失败或隔离 | `test_an_empty_pair_cannot_be_silently_hidden_by_other_pair`（1 passed） | 一币有效样本0、NaN/Inf/非法价格/非数值 | PASS |
| DATA-007 | 原始数据只读并具有内容与schema指纹 | `test_file_change_during_read_fails_before_dataset`（1 passed） | 读文件期间修改、重命名特征列 | PASS |
| DATA-008 | 数据质量不过不启动正式训练 | `test_formal_entry_does_not_train_with_failed_engineering_gate`（3 passed） | FAIL/PARTIAL/BLOCKED凭证 | PASS |
| LEAK-001 | 全部实际输入特征有时间依赖契约 | `test_contracts_match_actual_schema_and_explicit_close_availability`（1 passed） | 未知列与未审查版本 | PARTIAL |
| LEAK-002 | 未来扰动与截断不改变历史特征 | `test_baseline_all_columns_pass_actual_future_perturbation_and_truncation`（1 passed） | 扰动t之后价格和数量、截断未来 | PASS |
| LEAK-003 | 标签不得跨训练和早停验证边界 | `test_actual_native_split_exposes_overlapping_training_labels`（1 passed） | 真实原生拆分：BTC/ETH各3个跨界标签 | FAIL |
| LEAK-004 | 预处理拟合局限当前训练折 | `test_test_distribution_cannot_change_fit_parameters`（1 passed） | 改变外层test分布和标签 | PARTIAL |
| LEAK-005 | 已知泄漏植入必须被检出 | `test_injected_known_schema_leak_is_detected_by_values_not_registry`（3 passed） | future shift、全局均值、backfill、约1e-13泄漏 | PASS |
| LEAK-006 | 动态原生展开特征必须运行时验证 | 尚未实施 | 完整原生92/136列未来扰动尚未完成 | BLOCKED |
| LEAK-007 | 长历史与递归状态边界精确定义 | `test_recursive_state_starts_at_continuous_segment`（1 passed） | 断档后重置；短段无证据不能被长段掩盖 | PASS |
| LEAK-008 | 跨币未来扰动和排名不受未来影响 | 尚未实施 | 完整原生相关特征与排名动态验证尚未完成 | BLOCKED |
| SPLIT-001 | 三种切分各有真实数据集成 | `test_split_contract_global_pair_boundaries`（4 passed） | 依赖Phase2，未启动本轮正式切分集成 | BLOCKED |
| SPLIT-002 | 每折边界及样本ID导出 | 尚未实施 | 待阶段准入后实施/验收 | BLOCKED |
| SPLIT-003 | 每项purge与embargo可追溯 | `test_split_contract_global_pair_boundaries`（4 passed） | 待真实样本逐项审计 | BLOCKED |
| SPLIT-004 | 切分泄漏与错误索引负测 | 尚未实施 | 待索引映射和越界故障注入 | BLOCKED |
| SPLIT-005 | 最终holdout程序级访问保护 | 尚未实施 | 待独立解锁与访问账本 | BLOCKED |
| SPLIT-006 | 不得随机切分冒充时序评估 | `test_native_shuffle_is_detected_not_reinterpreted_as_walk_forward`（1 passed） | 原生shuffle检出；正式协议仍未准入 | BLOCKED |
| SPLIT-007 | 不得根据最终holdout挑模型 | 尚未实施 | 未访问最终holdout选模型；新协议未验收 | BLOCKED |
| MODEL-001 | 核心预测和交易指标手工样本验证 | 尚未实施 | 未进入本轮指标工程 | BLOCKED |
| MODEL-002 | 真实多折训练预测及离线回测 | 尚未实施 | 未启动正式Walk-Forward流程 | BLOCKED |
| MODEL-003 | 朴素基准与候选同数据同折 | 尚未实施 | 待Ridge/XGBoost/均值和交易基准对照 | BLOCKED |
| MODEL-004 | 逐折逐币逐窗口完整输出 | 尚未实施 | 本轮未生成正式模型评估 | BLOCKED |
| MODEL-005 | 成本和信号成交时点强制测试 | 尚未实施 | 待手续费/funding/滑点核算测试 | BLOCKED |
| MODEL-006 | 基准差异及考虑自相关的不确定性 | 尚未实施 | 待区块重采样和成本敏感性方案预注册 | BLOCKED |
| MODEL-007 | 不得仅凭训练或单次收益宣称有效 | 尚未实施 | 未作模型有效性结论 | BLOCKED |
| EXP-001 | 实验具有完整输入代码模型输出指纹 | 尚未实施 | 本轮正式实验管理未准入 | BLOCKED |
| EXP-002 | 定位每份真实实验产物 | 尚未实施 | 待原生与研究独立lineage验收 | BLOCKED |
| EXP-003 | 不可比实验程序拒绝直接排名 | 尚未实施 | 既有compare不足，未在本轮越过Gate修改 | BLOCKED |
| EXP-004 | 重复实验差异可解释 | 尚未实施 | 未启动正式重复训练比较 | BLOCKED |
| EXP-005 | 失败实验与历史成功记录不覆盖 | 尚未实施 | 既有测试继续运行，不代替新阶段验收 | BLOCKED |
| EXP-006 | 研究和FreqAI分别完成集成 | 尚未实施 | 原生隔离失败，禁止合并声明通过 | BLOCKED |
| EXP-007 | 可复现结论来自真实重复执行 | 尚未实施 | 仅数据重建已验证，正式模型复现未验收 | BLOCKED |
| GATE-001 | 验收核对实际内容与输入指纹 | `test_independent_data_gate_rebuilds_instead_of_trusting_pass_string`（1 passed） | 报告写PASS但dataset哈希篡改 | PASS |
| GATE-002 | P0失败必须否决准入 | `test_p0_failure_dominates_blocked_downstream`（1 passed） | P0 FAIL且后续BLOCKED | PASS |
| GATE-003 | 缺失证据不得标PASS | `test_missing_real_evidence_is_blocked_not_invented_pass_or_test_failure`（1 passed） | 无真实JUnit/报告 | PASS |
| GATE-004 | 全量测试本轮实际执行 | `test_skipped_case_is_not_executed_gate_evidence`（1 passed） | skip不得算执行；最终398/0/0 | PASS |
| GATE-005 | 真实多折端到端是总验收必需项 | 尚未实施 | 因Phase2 FAIL未执行，禁止继承旧报告 | BLOCKED |
| GATE-006 | 独立目录保留失败和阻断证据 | 尚未实施 | 本轮实际保留红测试和失败Gate；专门覆盖拒写测试未新增 | PARTIAL |
| GATE-007 | 工程预测交易生产结论严格区分 | `test_engineering_gate_does_not_grant_profitability_or_live_admission`（1 passed） | 即便工程PASS也不授予效果或实盘准入 | PASS |
| GATE-008 | 正式训练在调用模型前受程序保护 | `test_formal_entry_does_not_train_with_failed_engineering_gate`（3 passed） | 实际FAIL凭证CLI exit2且无输出目录 | PASS |
| GATE-009 | 所有必需阶段均执行通过才授权 | `test_passing_only_one_phase_or_empty_evidence_cannot_authorize_training`（1 passed） | 只有部分阶段PASS、其他未执行 | FAIL |
