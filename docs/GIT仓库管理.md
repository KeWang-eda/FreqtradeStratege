# FreqtradeStratege Git 仓库管理规范

- 文档对象：`/home/wangke/project/FreqtradeStratege`
- 仓库用途：管理 Vtech/Freqtrade 策略源码、实验分支、回测依据和部署文件
- 更新时间：2026-09-27
- 当前状态：仓库只有初始 `README.md`，`main` 与 `origin/main` 一致

## 1. 管理目标

本仓库只管理策略项目，不复制完整的 Freqtrade 源码仓库。

每一轮策略迭代都必须满足以下原则：

1. 新实验必须从当前 `main` 的最优策略提交创建。
2. 每轮只改变一个主要变量，形成控制变量实验。
3. 实验必须记录父策略、代码提交、配置、数据区间和运行命令。
4. 实验结果必须与父策略使用完全相同的评价口径。
5. 只有通过晋级门槛的实验，才能合并并 push 到 `main`。
6. `main` 只允许存在已经晋级的版本；不存在“已进入 main 但尚未晋级”的状态。
7. 未晋级实验只能保留在旁系分支和标签中，不能进入 `main`。
8. 回测结果、模型和部署包必须能够追溯到具体 Git 提交。

仓库不承担以下职责：

- 不保存完整历史 K 线数据。
- 不保存所有实验生成的日志、SQLite、缓存和回测压缩包。
- 不把 `/home/wangke/project/freqtrade` 整个仓库复制进来。
- 不把 API key、密码、私钥或含密钥的配置提交到 Git。

## 2. 当前资料与仓库边界

现有资料分为三类：

| 资料 | 位置 | 管理方式 |
|---|---|---|
| 策略与 FreqAI 调优主记录 | `/home/wangke/note/Vtech多空与FreqAI调优记录.md` | 作为研究来源，不直接作为运行配置 |
| 历史实验包 | `/home/wangke/project/freqtrade/user_data/experiences` | 逐个审计后提取，不能整体搬运 |
| Todoist 任务与评论 | Todoist 任务 `6hVvf67cmFGC7Fmg` | 记录任务背景、执行过程和结论 |

当前 `experiences` 目录约有 57 个实验目录，大小约 107G。
其中包含 feather、pkl、joblib、FreqAI 模型、日志和回测产物，不适合整体进入 Git 仓库。

历史报告不能直接证明一个版本可以晋级。
如果父子实验的时间区间、数据目录、模型缓存或指标口径不同，必须重新跑控制组和候选组。

## 3. 推荐仓库结构

第一阶段只建立下面这套结构，不提前增加更多抽象目录：

```text
FreqtradeStratege/
├── README.md
├── .gitignore
├── .gitattributes
├── docs/
│   ├── GIT仓库管理.md
│   ├── 实验记录模板.md
│   ├── 晋级门槛.md
│   └── 部署说明.md
├── strategies/
│   ├── VtechCryptoLongShort.py
│   ├── util.py
│   └── freqaimodels/
│       └── XGBoostRegressorES.py
├── configs/
│   ├── backtest/
│   ├── dry-run/
│   └── freqai/
├── scripts/
│   ├── run_smoke.sh
│   ├── run_backtest.sh
│   ├── run_oos.sh
│   ├── calc_metrics.py
│   └── verify_candidate.sh
├── experiments/
│   ├── INDEX.md
│   └── EXP-000-baseline/
│       ├── README.md
│       ├── manifest.yaml
│       ├── metrics.json
│       ├── commands.txt
│       └── SHA256SUMS
└── deploy/
    ├── deploy.sh
    └── manifest.example.yaml
```

说明：

- `strategies/`：只放可运行的策略源码和策略依赖模块。
- `configs/`：只放脱敏配置和不同运行场景的配置模板。
- `scripts/`：放统一的冒烟、回测、指标和候选验证命令。
- `experiments/`：放实验的可审计记录，不放完整运行产物。
- `deploy/`：放远端部署脚本和部署清单，不放密钥。
- `docs/`：放仓库规则，不放逐次实验的大量结果。

可提交已批准的离线部署模型时，使用：

```text
artifacts/
└── model-packs/
    └── vtech-<identifier>/
        ├── manifest.yaml
        ├── SHA256SUMS
        └── models/
```

该目录只保存已批准的部署模型包，不保存所有实验模型。
完整模型包总大小不超过 200 MiB 时，可以直接提交普通 Git；单个文件超过 GitHub 普通 Git 的限制时，按第 9 节使用 Git LFS 或独立制品存储。

## 4. 分支模型

### 4.1 `main`

`main` 是唯一的主迭代路线，而且只保存已经晋级的版本。

`main` 中不能存在“候选”“待验证”“暂存”或“未晋级”版本。
仓库初次建立时的基线也必须先完成登记和门禁确认，确认后才能作为 `main` 的正式基线。
只要一个提交被合并并 push 到 `main`，就代表该版本已经正式晋级。

不得直接在 `main` 上修改策略参数和交易逻辑。

### 4.2 实验分支

每次实验都从当前 `main` 创建独立旁系分支：

```bash
git switch main
git pull --ff-only origin main
git switch -c experiment/EXP-001-entry-score
```

命名格式：

```text
experiment/EXP-编号-变量名
```

实验分支只承载一个实验变量和它的完整记录。

- 实验通过晋级门槛：合并并 push 到 `main`，该提交正式成为主线晋级版本。
- 实验未通过晋级门槛：保留在该旁系分支，不合并到 `main`。
- 实验阻塞或数据无效：保留分支并标记原因，不得当作策略结果。
- 淘汰分支可以打 `rejected/EXP-XXX` 标签，但标签和分支都不能改变 `main`。

如果实验中发现了独立的代码缺陷，应先记录为修复任务，不要顺手加入实验变量。

### 4.3 修复分支

与策略收益无关的代码修复使用：

```text
fix/描述
```

例如：

```text
fix/freqai-path
fix/metrics-wallet-drawdown
```

修复分支合并后，必须重新生成受影响的父策略基线。
修复前后的结果不能混在同一个实验结论里。

### 4.4 标签

每个实验完成后创建不可变标签：

```text
experiment/EXP-001-result
promoted/EXP-001
rejected/EXP-002
baseline/EXP-000
```

标签用于定位实验最终状态。
标签创建后不得移动到其他提交。

## 5. 一次实验的标准流程

### 第一步：冻结父策略

```bash
git switch main
git pull --ff-only origin main
git rev-parse HEAD
```

把输出的提交哈希写入实验 `manifest.yaml` 的 `parent_commit` 字段。

### 第二步：创建实验分支

```bash
git switch -c experiment/EXP-XXX-variable-name
```

先写实验记录，再改策略代码。

### 第三步：写实验假设

实验记录至少说明：

- 实验编号。
- 父策略提交。
- 唯一改变的变量。
- 修改前的值。
- 修改后的值。
- 为什么要做这个实验。
- 预期改善什么指标。
- 哪些内容明确不改变。
- Todoist 任务 ID。

### 第四步：先跑冒烟回测

先验证以下内容：

- 策略可以加载。
- 配置指向了正确的策略和模型。
- 数据路径正确。
- FreqAI 模型或缓存可以加载。
- 没有 `ERROR`、`Traceback`、`No common dates`。
- 有实际交易或明确记录无交易原因。

冒烟失败时，实验状态为 `blocked`，不能评价收益，也不能进入晋级判断。

### 第五步：跑父策略和候选策略

父策略和候选策略必须使用相同的：

- Freqtrade 版本或提交。
- Python 和关键依赖版本。
- 交易所和交易模式。
- 时间周期。
- 币池。
- 时间区间。
- 初始资金。
- 杠杆。
- 手续费。
- 最大持仓数。
- 订单和止损配置。
- FreqAI 训练窗口和模型规则。
- 指标计算脚本。

如果改变了特征、标签、模型类或模型训练配置，必须使用新的 FreqAI `identifier`。
如果只改变入场、出场或非特征参数，才可以复用相同模型缓存，但必须在记录中写明原因。

### 第六步：保存可审计结果

Git 中保存小型、可读、可比较的结果：

- `metrics.json`：机器可读指标。
- `README.md`：实验结论。
- `commands.txt`：完整命令和运行环境。
- `SHA256SUMS`：外部结果文件和模型包的校验和。

原始 ZIP、日志、SQLite 和 K 线数据保存到本地归档或专门的对象存储，不直接提交普通 Git。

### 第七步：执行晋级判断

候选策略只有同时满足以下条件才允许晋级：

```text
候选 Calmar × 候选 Sharpe
    > 父策略 Calmar × 父策略 Sharpe

并且：

候选最大回撤 < 30%
```

比较必须使用同一指标口径。
推荐统一使用每日钱包余额曲线计算 Sharpe、Calmar 和回撤。

需要特别区分：

- `max_relative_drawdown`：用于本项目的最大回撤晋级门槛。
- Calmar 计算内部使用的最大回撤定义：必须在指标文档中固定，不能混用。
- 闭仓交易口径指标：只能作为辅助诊断，不能替代钱包口径晋级指标。

以下情况一律不能晋级：

- 任意一个核心指标缺失、不是有限数值或无法复算。
- 父子策略使用不同回测口径。
- 只跑了候选，未跑同条件父策略控制组。
- 只在已经用于选参的数据上得到改善，且没有保留段验证。
- 最大回撤达到或超过 30%。
- 结果依赖未记录的本地文件、模型或手工改动。
- 发现未来函数、时间错位、模型路径错误或配置覆盖问题。

### 第八步：合并或淘汰

通过晋级：

```bash
git switch main
git pull --ff-only origin main
git merge --no-ff experiment/EXP-XXX-variable-name \
  -m "promote: EXP-XXX variable-name"
git tag -a promoted/EXP-XXX -m "Promote EXP-XXX"
git push origin main --follow-tags
```

未通过晋级：

```bash
git tag -a rejected/EXP-XXX -m "Reject EXP-XXX"
git push origin experiment/EXP-XXX-variable-name --tags
```

未通过的实验分支不合并策略代码到 `main`，但必须保留实验记录和淘汰原因。

## 6. 实验目录文件规范

### 6.1 `experiments/EXP-XXX/README.md`

每个实验 README 使用以下结构：

```markdown
# EXP-XXX：实验名称

## 状态

- 状态：proposed / running / passed / rejected / blocked
- 父策略：
- 父提交：
- 实验分支：
- Todoist 任务：

## 实验假设

## 控制变量

| 项目 | 父策略 | 候选策略 |
|---|---|---|
| 唯一改变的变量 |  |  |

## 不变条件

## 数据与运行口径

## 执行命令

## 结果

| 指标 | 父策略 | 候选策略 | 变化 |
|---|---:|---:|---:|
| Sharpe |  |  |  |
| Calmar |  |  |  |
| Calmar × Sharpe |  |  |  |
| 最大回撤 |  |  |  |

## 晋级判断

## 失败原因或限制

## 结论
```

### 6.2 `manifest.yaml`

`manifest.yaml` 保存结构化实验元数据：

```yaml
id: EXP-XXX
status: proposed
branch: experiment/EXP-XXX-variable-name
parent_commit: <git-commit>
todoist_task_id: <todoist-id>

hypothesis: "一句话说明实验假设"

single_variable:
  name: "参数或逻辑名称"
  before: "旧值"
  after: "新值"

protocol:
  freqtrade_commit: "版本或提交"
  timeframe: "1h"
  timerange: "YYYYMMDD-YYYYMMDD"
  pairlist: "配置文件或币池版本"
  initial_balance: 100
  leverage: 2
  fee: 0.0005
  max_open_trades: 5
  freqai_identifier: "identifier"

metrics:
  source: "wallet"
  sharpe: null
  calmar: null
  calmar_sharpe_product: null
  max_relative_drawdown: null

promotion:
  parent_product: null
  candidate_product: null
  drawdown_limit: 0.30
  decision: pending
  reason: null

artifacts:
  metrics: metrics.json
  commands: commands.txt
  checksums: SHA256SUMS
```

### 6.3 `metrics.json`

只保存可由脚本生成的数值，不手工填写：

```json
{
  "strategy": "VtechCryptoLongShort",
  "timerange": "YYYYMMDD-YYYYMMDD",
  "starting_balance": 100.0,
  "final_balance": null,
  "trade_count": null,
  "sharpe_wallet_daily": null,
  "calmar_wallet_daily": null,
  "calmar_sharpe_product": null,
  "max_relative_drawdown": null,
  "drawdown_start": null,
  "drawdown_end": null,
  "source_commit": null,
  "generated_by": "scripts/calc_metrics.py"
}
```

## 7. README 的职责

根目录 `README.md` 只做入口，不复制完整实验日志。

应包含：

1. 项目用途。
2. 当前 `main` 对应的策略类和版本标签。
3. 当前主线的运行前提。
4. 最短的冒烟、回测和部署命令。
5. 仓库目录说明。
6. 分支和晋级规则链接。
7. 当前晋级版本和关键指标链接。
8. 风险提示：历史回测不等于未来收益。

详细规则分别放在 `docs/`，实验细节放在 `experiments/EXP-XXX/`。

## 8. `.gitignore` 规则

文件名是 `.gitignore`，不是 `.ignoregit`。

建议排除：

```gitignore
# Python
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.venv/
venv/

# IDE
.vscode/
.idea/
*.swp

# Secrets and private configuration
.env
.env.*
!.env.example
config-private*.json
secrets/
*.pem
*.key

# Freqtrade runtime data
user_data/data/
user_data/logs/
user_data/*.sqlite
user_data/*.sqlite-journal
user_data/backtest_results/
user_data/hyperopt_results/
user_data/grid_results/
user_data/models/
user_data/notebooks/

# Generated FreqAI data
**/backtesting_predictions/
**/historic_predictions*.pkl
**/*.feather
**/*.joblib
**/*.pkl

# Generated result files
*.zip
*.tar
*.tar.gz
*.tgz
*.log
*.meta.json

# Local experiment scratch space
.tmp/
reports/generated/

# 允许提交：已批准的小型离线部署模型包
# 这些规则必须放在通用模型排除规则之后
!artifacts/
!artifacts/model-packs/
!artifacts/model-packs/**/
!artifacts/model-packs/**/*.json
!artifacts/model-packs/**/*.joblib
!artifacts/model-packs/**/*.pkl
!artifacts/model-packs/**/*.feather
```

不要使用过宽的规则，例如 `*.json`、`*.md` 或 `*.csv`。
仓库需要提交脱敏配置、实验清单、指标 JSON、文档和批准的小型离线部署模型包。

如果批准的模型包超过普通 Git 的合理体积，再使用 Git LFS。
不要把所有历史模型都加入 LFS。

## 9. 训练模型与离线部署

FreqAI 运行过程中生成的全部模型缓存不应直接提交。
FreqAI 的模型目录由 `identifier` 管理，模型、metadata、预测缓存和训练数据之间存在关联。

但是，**体积较小且已经通过验证、确实用于远端离线部署的模型，可以随策略仓库一起提交**。
这样远端只需要克隆仓库和安装匹配的 Freqtrade 环境，不需要联网重新训练模型。

### 9.1 可以直接提交的模型

满足以下条件时，模型包可以进入普通 Git：

- 这是明确批准的离线部署版本，不是训练过程中的临时缓存。
- 模型包包含完整的 FreqAI `identifier` 目录，而不是只复制某个 `.joblib` 文件。
- 模型包与策略提交、配置、Freqtrade 版本和特征定义匹配。
- 单个文件不超过 50 MiB，适合直接进入普通 Git。
- 整个完整模型包不超过 200 MiB，可以直接随仓库提交。
- 如果模型包中存在 50 MiB 以上的单个文件，优先对该类型使用 Git LFS。
- 如果存在 100 MiB 以上的单个文件，必须使用 Git LFS 或独立制品存储。
- 已完成一次本地加载或离线部署冒烟验证。
- 已生成 `SHA256SUMS`，远端部署前会校验。
- 模型包不含 API key、密码、私钥或其他秘密。

“200 MB 以内”指完整模型目录的总大小，不是把整个目录压缩成一个 200 MB 的 zip 文件。
FreqAI 模型目录中通常包含许多较小的 JSON、feather、metadata 和模型文件，完整目录可以直接提交。
如果打包成单个超过 50 MiB 的 zip 或 tar 文件，则应使用 Git LFS，而不是直接提交普通 Git。

当前经验中，约 21 MiB 的完整模型目录属于可以直接进入 Git 的范围；约 200 MiB 仍属于可接受上限，但是否提交仍以“已批准并可部署”为前提，而不是只看体积。

### 9.2 模型包目录

批准的模型包放在仓库的 `artifacts/model-packs/`，不要放回被整体排除的 `user_data/models/`：

```text
artifacts/
└── model-packs/
    └── vtech-<identifier>/
        ├── manifest.yaml
        ├── SHA256SUMS
        └── models/
            └── <identifier>/
                ├── config_*.json
                ├── pair_dictionary.json
                ├── historic_predictions.pkl
                ├── backtesting_predictions/
                └── sub-train-*/
```

FreqAI 自动生成的目录结构必须整体保留，不要手工删除 metadata、pair dictionary、训练数据或预测文件。
部署时使用包内的相对路径，不要保留训练机器的绝对路径。

### 9.3 不能直接提交的模型

以下内容继续排除：

- 所有未筛选的 `user_data/models/`。
- 每次训练自动生成的临时模型。
- 只为了回测缓存而生成的模型。
- 无法说明对应策略提交和配置的模型。
- 单文件超过 50 MiB 的模型包，除非明确改用 Git LFS。
- 单文件超过 GitHub 普通仓库 100 MiB 限制的文件。
- 包含秘密或本地绝对路径的模型 metadata。

### 9.4 超过普通 Git 体积时的处理

如果单个模型文件超过 50 MiB，优先选择以下方案之一：

1. 用 Git LFS 保存已批准的模型包。
2. 将模型包放到独立的离线制品存储，并在 Git 中保存 manifest 和下载说明。
3. 减少模型包内容，但不能删除 FreqAI 运行所需的文件。

如果使用 Git LFS，必须在 `.gitattributes` 中只匹配批准的目录，例如：

```gitattributes
artifacts/model-packs/**/*.joblib filter=lfs diff=lfs merge=lfs -text
artifacts/model-packs/**/*.pkl filter=lfs diff=lfs merge=lfs -text
```

不要把 `user_data/models/**` 整体加入 LFS。

### 9.5 离线部署清单

模型包的 `manifest.yaml` 至少记录：

- Git 策略提交。
- Freqtrade 提交或版本。
- Python 和依赖版本。
- 策略类。
- 配置文件。
- FreqAI `identifier`。
- 币池和时间周期。
- 模型生成时间。
- 模型目录相对路径。
- 模型包总大小。
- 每个文件的 SHA256。
- 本地加载或部署冒烟结果。

远端部署必须先校验 Git 提交、模型 `identifier` 和配置是否属于同一个候选版本。
校验失败时停止部署，不允许使用旧模型继续运行。

当前 `/home/wangke/project/freqtrade` 中存在 Freqtrade 引擎源码修改。
这些修改不能隐含在策略仓库中。
如果策略依赖引擎修复，必须额外记录 Freqtrade 提交或补丁文件，否则不能声称“仅克隆策略仓库即可完整部署”。

## 10. 提交信息规范

所有提交必须使用 Conventional Commits 形式：

```text
<type>(<scope>): <summary>
```

规则：

- `type` 必须使用下表之一：`feat`、`fix`、`refactor`、`docs`、`test`、`chore`、`perf`、`build`、`revert`。
- `scope` 必须写受影响区域，例如 `baseline`、`strategy`、`freqai`、`config`、`metrics`、`experiment`、`docs`。
- `summary` 使用英文祈使句，首字母小写，不加句号，尽量控制在 72 个字符以内。
- 一次提交只做一件事，不把代码、参数、文档、模型和部署混成一个无关提交。
- 提交正文用于说明原因、父提交、唯一变量和验证命令；实验数据的完整结论放在实验报告，不塞进标题。
- 不使用无法表达含义的标题，例如 `update`、`test`、`修改一下`、`finally`、`临时保存`。

允许的示例：

```text
docs(repo): add git workflow and promotion rules
feat(baseline): add Vtech FreqAI risk control
fix(freqai): reject invalid wallet risk fallback
refactor(strategy): extract causal feature helpers
config(baseline): freeze 1h three-slot control
exp(EXP-001): record parent control and candidate
report(EXP-001): add wallet metrics and OOS decision
promote(EXP-001): merge verified candidate into main
chore(repo): add Python cache ignore rules
revert: revert "feat(baseline): add Vtech FreqAI risk control"
```

实验提交必须携带对应编号：

```text
exp(EXP-001): record single-variable hypothesis
feat(EXP-001): change max open trades from five to three
report(EXP-001): record main and early OOS metrics
```

晋级提交必须单独完成，且只能发生在门禁通过之后：

```text
promote(EXP-001): merge verified candidate into main
```

`promote(...)` 提交不是“申请晋级”，而是“已经完成晋级并进入 main”的事实记录。
未晋级实验不得创建 `promote(...)` 提交，不得把实验分支合并到 `main`。

推荐的实验提交顺序：

```text
1. docs(EXP-001): add experiment manifest
2. feat(EXP-001): implement one controlled variable
3. test(EXP-001): verify strategy loads and variable is active
4. report(EXP-001): record control and candidate metrics
5. promote(EXP-001): merge verified candidate into main
```

如果实验失败，最后一个提交只记录失败结论，分支不合并：

```text
report(EXP-002): reject candidate after early OOS regression
```

一次提交只做一件事。
不要把参数调整、代码重构、文档整理和部署修复混成一个提交。

## 11. 历史实验压缩迁移规则

现有调优记录包含大量重复网格、细扫、失败尝试和后来被新父版本覆盖的历史父线。
本仓库不机械重放所有历史实验。

如果当前生产源码已经包含多个连续晋级节点，并且能够用主记录、experience 报告、Todoist 记录和当前配置交叉核对，就把这些连续节点压缩登记为一个已验证基线（例如 `EXP-000`），不要创建没有行为变化的空分支。

只有下列情况才单独创建新的实验分支：

- 当前 `main` 之后出现新的代码或配置变量。
- 该变量是一个明确的大改动，而不是重复网格中的小点。
- 父提交、控制组、候选组和独立窗口结果都能复现。
- 通过门禁后才合并并 push 到 `main`。

历史实验仍可在 `experiments/INDEX.md` 中保留摘要和来源，但不因此进入仓库代码链。

## 12. 第一次建立仓库时的顺序

暂不搬运全部历史实验，按以下顺序执行：

1. 提交仓库管理文档、`.gitignore` 和最小 README。
2. 从当前资料中确定唯一的 `EXP-000` 基线来源。
3. 只提取基线运行所需的策略、配置、FreqAI 模型类和脚本。
4. 跑一次最小冒烟回测。
5. 固化基线的 Git 提交、配置、指标和模型标识。
6. 创建 `baseline/EXP-000` 标签。
7. 之后每轮只从 `main` 创建一个 `experiment/EXP-XXX-*` 分支。

不要先把 `experience1` 到 `experience61` 全部复制进仓库。
历史资料先作为审计来源，只有需要复现或继承的实验才按实验编号逐个提取。

## 12. 完成一轮实验的检查清单

- [ ] 实验分支来自当前 `main`。
- [ ] 已记录父提交哈希。
- [ ] 只改变了一个主要变量。
- [ ] 父策略和候选策略使用同一评价口径。
- [ ] 冒烟回测通过。
- [ ] 父策略控制组已重新运行。
- [ ] 候选策略已运行。
- [ ] 回测无未解决的 ERROR、Traceback、时间错位和模型路径问题。
- [ ] 已生成 `metrics.json`、`commands.txt` 和 `SHA256SUMS`。
- [ ] `Calmar × Sharpe` 严格高于父策略。
- [ ] 最大回撤严格小于 30%。
- [ ] 已在 Todoist 任务中记录调研、执行、结果和思考。
- [ ] 通过才合并 `main`，失败则保留旁系分支并标记 `rejected`。
- [ ] 合并后已创建不可变 `promoted/EXP-XXX` 标签。

## 13. 参考资料

- Freqtrade 策略定制：
  <https://www.freqtrade.io/en/stable/strategy-customization/>
- Freqtrade 回测：
  <https://www.freqtrade.io/en/stable/backtesting/>
- FreqAI 配置：
  <https://www.freqtrade.io/en/stable/freqai-configuration/>
- FreqAI 运行和模型复用：
  <https://www.freqtrade.io/en/stable/freqai-running/>
- Git 分支工作流：
  <https://git-scm.com/book/en/v2/Git-Branching-Branching-Workflows>
- GitHub 忽略文件：
  <https://docs.github.com/en/get-started/git-basics/ignoring-files>
- GitHub 大文件与 Git LFS：
  <https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github>
