# case-design — 企业级测试用例设计 Skill（Claude Code）

一套跑在 **Claude Code** 上的测试用例设计 Skill：输入需求文档，自动走「需求定位 → 澄清 → 规格建模 → 风险分析 → 方法匹配 → 测试点 → 用例生成 → 去重 → 覆盖率 → 自查 → 写入 → 人工审核 → 知识总结 → Excel」全流程，产出 Markdown / Excel 测试用例、澄清台账、知识总结，并维护多需求索引。

采用**渐进式加载**：常驻核心 ~6K tokens，各阶段细则按需读取 `references/`，回读核对与知识综合用 `scripts/` 脚本返回摘要，显著降低每次请求的 token 消耗。

---

## 目录

1. [适用场景](#1-适用场景)
2. [环境要求](#2-环境要求)
3. [安装步骤](#3-安装步骤)
4. [依赖安装与验证](#4-依赖安装与验证)
5. [验证 Skill 已生效](#5-验证-skill-已生效)
6. [使用步骤](#6-使用步骤)
7. [产出物说明](#7-产出物说明)
8. [注意事项](#8-注意事项)
9. [Skill 目录结构](#9-skill-目录结构)
10. [常见问题 FAQ](#10-常见问题-faq)

---

## 1. 适用场景

- 根据需求文档 / 原型图说明 / 流程图说明设计测试用例
- 将已有 Markdown 测试用例转为 Excel
- 测试覆盖分析、测试点挖掘、风险用例识别
- 多需求批量设计、需求增量修改、回归影响分析

---

## 2. 环境要求

| 组件 | 要求 | 说明 |
|---|---|---|
| **Claude Code** | 较新版本（支持 Skills） | 桌面端 / CLI / VS Code 扩展均可 |
| **Python** | 3.7+ | 跑自带脚本（回读核对、知识综合投影）与 Excel 生成脚本 |
| **openpyxl** | 仅生成 Excel 时需要 | 缺失时 Skill 会自动尝试 `pip install` 并兜底报错 |
| **操作系统** | Windows / macOS / Linux 均可 | Windows 用 `python`，macOS/Linux 用 `python3` |

> 四个自带脚本（`scripts/verify_md.py`、`scripts/verify_cases.py`、`scripts/verify_knowledge.py`、`scripts/project_cases.py`）只用 Python 标准库，**无 openpyxl 也能运行**（只是不能产出 Excel）。

---

## 3. 安装步骤

### 3.1 获取 Skill 文件

拿到 `case-design/` 整个目录（或 `case-design-skill.zip` 解压后得到该目录）。目录结构见 [第9节](#9-skill-目录结构)。

### 3.2 选择安装位置

Claude Code 会从两个位置加载 Skills，任选其一：

#### 方式 A：项目级（推荐）

放进**项目根目录**下的 `.claude/skills/`，仅在该项目运行 Claude Code 时可用，随项目走、可提交 git：

```
<你的项目根目录>/
└── .claude/
    └── skills/
        └── case-design/        ← 把整个目录放这里
            ├── SKILL.md
            ├── references/
            └── scripts/
```

**路径示例**：
- Windows：`D:\my-project\.claude\skills\case-design\`
- macOS/Linux：`/home/you/my-project/.claude/skills/case-design/`

#### 方式 B：用户级（全局，所有项目可用）

放进用户主目录下的 `.claude/skills/`：

- Windows：`C:\Users\<你的用户名>\.claude\skills\case-design\`
- macOS/Linux：`~/.claude/skills/case-design/`

> 区别：项目级随仓库走、团队协作时人人可用；用户级只对你本机所有项目生效。

### 3.3 重启 Claude Code

安装后，**在该目录（重新）打开一个 Claude Code 会话**，Skill 即被识别（已开会话需新开一个或重启，以重新扫描 skills 目录）。

---

## 4. 依赖安装与验证

### 4.1 安装 Python

- Windows：从 https://www.python.org/downloads/ 下载安装，安装时勾选 **Add Python to PATH**。
- macOS：`brew install python`
- Linux：`sudo apt install python3`（或对应发行版包管理器）

### 4.2 验证 Python

打开终端（Terminal / PowerShell / Git Bash），执行：

```bash
# Windows
python --version

# macOS / Linux
python3 --version
```

能正常打印版本号（≥ 3.7）即可。

### 4.3 安装 openpyxl（生成 Excel 才需要）

```bash
# Windows
pip install openpyxl

# macOS / Linux
pip3 install openpyxl
```

### 4.4 验证依赖

```bash
# Windows
python --version
python -c "import openpyxl; print('openpyxl', openpyxl.__version__)"

# macOS / Linux
python3 --version
python3 -c "import openpyxl; print('openpyxl', openpyxl.__version__)"
```

- 第一条打印 Python 版本 → Python OK。
- 第二条打印 `openpyxl x.x.x` → Excel 依赖 OK；若报 `ModuleNotFoundError`，说明未装 openpyxl（不生成 Excel 可忽略，要生成则按 4.3 安装）。

> **不必手动验证自带脚本**：`scripts/` 下的脚本由 Skill 在运行时自动调用，无需你手动运行。它们只用标准库，装好 Python 即可。

---

## 5. 验证 Skill 已生效

在装好 Skill 的目录打开 Claude Code，任选其一验证：

1. **显式触发**：输入 `/case-design`，若 Skill 被加载，Claude 会按本 Skill 流程响应。
2. **自然语言**：输入"列出当前可用的 skills"或"有没有 case-design skill"，确认 `case-design` 在列。
3. **任务触发**：描述一个测试用例设计任务，看 Claude 是否进入本 Skill 流程（先读 `case-design-out/MANIFEST.md`、再澄清、再生成用例）。

若以上均无反应，检查：
- 目录路径是否正确（`SKILL.md` 是否在 `.claude/skills/case-design/` 下）。
- 是否重启了 Claude Code 会话。
- frontmatter 是否完整（见 [8.1](#81-关于-disable-model-invocation)）。

---

## 6. 使用步骤

### 6.1 准备产出目录

Skill 会把产出物写到**当前项目根目录下的 `case-design-out/` 子目录**（Claude Code 运行所在的项目根目录下自动创建该目录）。无需手动建目录；建议在**专用项目文件夹**里运行，避免与其它文件混杂：

```
D:\qa\order-cases\        ← 在这里打开 Claude Code（项目根目录）
└── case-design-out\          ← Skill 自动创建，所有产出物落在这里
    ├── MANIFEST.md
    ├── TestCases_<需求标识>.md
    ├── Clarification_Ledger_<需求标识>.md
    ├── Knowledge_<需求标识>.md
    └── TestCases_<需求标识>.xlsx
```

> 若 `case-design-out/` 下已有 `MANIFEST.md`，Skill 会当作多需求索引读入；若没有，首次运行会创建。**产出物统一写入 `case-design-out/`，不散落到项目根目录。**

### 6.2 触发 Skill

两种方式：

**方式一：显式触发（默认，当前 SKILL.md 设了 `disable-model-invocation: true`）**

直接输入：

```
/case-design
```

或在消息中说明：

```
使用 case-design skill，帮我设计下面的需求的测试用例。
```

**方式二：自动触发（需先改配置，见 [8.1](#81-关于-disable-model-invocation)）**

删掉 frontmatter 里的 `disable-model-invocation: true` 后，直接描述任务即可自动加载：

```
帮我设计测试用例，需求如下：……
```

### 6.3 按输入协议提供需求

Skill 有固定输入协议，最简形式如下（直接粘贴给 Claude）：

```
【需求标识】
订单创建-20260702

【业务需求描述】
<<<需求文档开始>>>
用户在购物车点击"提交订单"，系统创建订单，状态为"待支付"，扣减库存，发送订单创建消息。
订单金额 = 商品单价 × 数量。数量需为 1-99 整数。
<<<需求文档结束>>>

【业务知识库摘要】
无

【测试规范知识库摘要】
无
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| **需求标识** | 是 | `<需求简称>-<YYYYMMDD>` 或 `<需求简称>`，作为所有产出文件命名前缀；未提供则从需求文档标题提取 |
| **业务需求描述** | 是 | 用 `<<<需求文档开始>>>` / `<<<需求文档结束>>>` 包裹；支持 Markdown / Word 文本 / 原型图说明 / 流程图说明 |
| **业务知识库摘要** | 否 | 系统架构、历史逻辑、上下游依赖；无则填"无" |
| **测试规范知识库摘要** | 否 | 公司测试规范、历史缺陷模型；无则填"无" |
| **技术实现摘要** | 否（开发提供） | 存储设计/接口契约/状态机实现/异常重试补偿——提供后可在用例中直接断言真实表/字段/Key，闭合"禁止杜撰存储信息"（见 SKILL.md §5） |
| **业务规则与历史缺陷** | 否（业务/产品提供） | 隐含规则/合规红线/运营异常/真实边界——补隐含规则与运营现实，闭合"禁止脑补业务规则" |
| **历史缺陷摘要** | 否（缺陷反哺） | 从 bug tracker 导出的历史缺陷，每条强制映射为≥1 用例覆盖，是最高发现力来源 |

### 6.4 配合 Skill 的交互流程

提交后，Skill 会依次：

1. **第0阶段**：读取/创建 `case-design-out/MANIFEST.md` 索引，判断新需求或已有需求。
2. **澄清**：扫描缺口，输出【待确认问题与假设清单】（问题 Q 与假设 A 统一展示）。若有 **P0/P1** 未确认项，会**暂停等回复**；请逐条回答（可批量，如"Q1 按方案A，Q2 按方案B"）。P2/P3 缺口在连跑/轻量模式下登记为假设（回显本清单）。答复会落盘到 `case-design-out/Clarification_Ledger_<需求标识>.md`，后续不再重复提问。
3. **建模/风险/方法/测试点/用例生成**：默认不展示过程（仅调试模式可见）。
4. **对话展示**：在对话里完整展示本轮用例表。
5. **写入**：一次性写入 `case-design-out/TestCases_<需求标识>.md`，并用 `scripts/verify_md.py`（结构）+ `scripts/verify_cases.py`（内容/覆盖）回读核对。对话中只展示用例紧凑投影 + 覆盖矩阵，明细见文件。
6. **人工审核**：提示你审核。回复方式：
   - **"审核通过" / "无问题"** → 自动生成知识总结 `case-design-out/Knowledge_<需求标识>.md`，再询问是否生成 Excel。
   - **指出问题**（如"TestCases_xxx 断言模糊，改为返回400"）→ 按修改流程重走相应阶段并重新提示审核。
7. **Excel**（可选）：回复要 Excel → Skill 用 openpyxl 脚本生成 `case-design-out/TestCases_<需求标识>.xlsx`，并自动做结构校验 + 数据完整性校验，输出核对报告。

### 6.5 运行模式（在输入中声明，可改默认行为）

| 模式 | 触发词 | 行为 |
|---|---|---|
| **完整模式**（默认） | 无 | 全部门禁等人工确认 |
| **连跑模式** | `连跑` / `自动跑` / `批量` | 仅 P0/P1 澄清阻断，.md 标注"待审核"后自动推进，适合多模块批量 |
| **轻量模式** | `轻量` / `小改` / `低风险` | 仅阻断 P0，适合字段校验/文案类 |

声明方式：在输入开头写，例如：

```
连跑模式
【需求标识】支付重构
...
```

### 6.6 调试模式（可选）

在输入中加 `调试模式` 或 `展示分析过程`，Skill 会额外输出规格建模摘要、风险分析摘要、测试覆盖摘要，再输出用例。排查问题或想看推理时使用。

### 6.7 仅转 Excel（已有 .md 时）

如果 `case-design-out/` 下已有 `TestCases_<需求标识>.md`，只想转 Excel：

```
/case-design
把 case-design-out/TestCases_订单创建-20260702.md 转成 Excel
```

Skill 会跳过完整设计流程，先做源 .md 一致性校验，通过后直接生成 Excel（仍走脚本产出 + 两段校验，输出到 `case-design-out/`）。

---

## 7. 产出物说明

运行后**项目根目录下的 `case-design-out/` 子目录**会出现以下文件（**正式产出物，请勿手动删除**）：

| 文件 | 命名 | 内容 |
|---|---|---|
| 索引 | `case-design-out/MANIFEST.md` | 所有需求的快速定位入口（一个文件，跨需求） |
| 需求文档 | `case-design-out/REQ_<需求标识>.md` | （可选）保存你提供的需求文档 |
| 澄清台账 | `case-design-out/Clarification_Ledger_<需求标识>.md` | 澄清问答，跨会话保留，避免重复提问 |
| 测试用例 | `case-design-out/TestCases_<需求标识>.md`（默认单文件）/ `case-design-out/TestCases_<需求标识>_PARTn.md`（压缩后仍超预算才拆） | 15 列用例表；默认单文件，仅超 24000 token 才拆最小 PART |
| 测试用例 Excel | `case-design-out/TestCases_<需求标识>.xlsx` | 与 .md 字段完全一致，用户确认后生成 |
| 知识总结 | `case-design-out/Knowledge_<需求标识>.md` | 13 维度业务知识沉淀，审核通过后生成 |

> 用例 ID 通过功能缩写区分模块（如 `TestCases_订单创建-20260702_CREATE_001`、`..._PAY_001`）。**默认写入同一个** `case-design-out/TestCases_<需求标识>.md`；仅合并体压缩后仍 > 24000 token 才拆最小 PART `case-design-out/TestCases_<需求标识>_PARTn.md`（写前规模评估，不按模块拆）。

---

## 8. 注意事项

### 8.1 关于 `disable-model-invocation`

当前 `SKILL.md` 设了 `disable-model-invocation: true`，含义：**模型不会自动加载本 Skill，必须用 `/case-design` 显式触发**。

- 想保留"按需手动触发、避免误触"→ **保持现状**。
- 想让"用户一提测试用例设计就自动激活"→ 用文本编辑器打开 `SKILL.md`，**删除 frontmatter 里的这一行**：
  ```
  disable-model-invocation: true
  ```
  保存后重启 Claude Code 会话即可。

### 8.2 产出目录会被写入文件

Skill 会在**项目根目录下的 `case-design-out/` 子目录**写 `MANIFEST.md`、`TestCases_*.md`、`Clarification_Ledger_*.md`、`Knowledge_*.md`、`TestCases_*.xlsx`（目录不存在时自动创建）。建议：
- 在**专用项目文件夹**运行，不要在系统目录或代码仓库根目录直接跑（除非你确要这么用）。
- Excel 生成会临时在 `case-design-out/` 下建 `.py` 脚本和中间文件，用完即自动删除；正式产出物不会被删。

### 8.3 Excel 依赖 openpyxl

- 要生成 Excel 必须装 openpyxl（见 [4.3](#43-安装-openpyxl生成-excel-才需要)）。
- 缺失时 Skill 会尝试 `pip install openpyxl` 自动安装；自动安装失败会**显式报错**，不会静默降级为文本表格。
- 严禁用文本工具直接写 `.xlsx`（会产出损坏文件）——Skill 已强制走 openpyxl 脚本生成。

### 8.4 Windows 用 `python`

- Windows 环境调用 Python 用 `python`（不是 `python3`）。Skill 内部脚本调用已适配。
- 若系统里 `python` 指向 Microsoft Store 占位符，请从 python.org 安装真实 Python 并加入 PATH。

### 8.5 跨会话状态保留

- `case-design-out/` 下的 `MANIFEST.md`、`Clarification_Ledger_*.md`、`Knowledge_*.md` **跨会话有效**。
- 新会话处理同一需求时，Skill 第0阶段会读入索引和台账，**不会重复提问已解决问题**。
- 若换了项目根目录（`case-design-out/` 下文件不存在），视为首次处理，会重新澄清——属正常行为。

### 8.6 完整输出与门禁

- 每轮用例**一次性写入**文件（不增量、不分条），写入后回读核对。
- 完整模式下，.md 写入后**必须等人工审核通过**才进 Excel；连跑/轻量模式可标注"待审核"后自动推进，但 **P0 风险模块仍守审核门禁**。
- 自动放行**只放宽"等待人工"时点，不放宽任何质量底线**（脑补禁令、断言可观测、存储合规、去重、覆盖率等全不变）。

### 8.7 不要手动改产出物格式

- 测试用例表的 15 列字段顺序、4 个固定值列（编辑模式=STEP / 标签=AI / 责任人=AI / 用例状态=Completed）**不可改动**，否则 Excel 转换校验会不通过。
- 要改用例内容请走"修改流程"（告诉 Claude 问题点），不要手动编辑 `case-design-out/TestCases_*.md` 再转 Excel（会因一致性校验失败被拒）。

### 8.8 关于"16 列 / 15 列"

原版文档多处文字写"16 列"，但字段顺序表实际为 **15 个字段**，系原文计数不一致。本 Skill 已统一为 **15 列**，`scripts/verify_md.py` 按权威 15 字段清单校验。

---

## 9. Skill 目录结构

```
case-design/
├── SKILL.md                    # 常驻核心（frontmatter + 主流程 + ref 索引）
├── README.md                   # 本说明
├── references/                 # 各阶段细则（按需读取，不常驻）
│   ├── phase0_manifest.md      # 第0阶段：需求定位 + MANIFEST 索引管理
│   ├── clarification.md        # 第1阶段：澄清机制 + 澄清台账
│   ├── coverage.md             # 第2/7阶段：覆盖矩阵 + 需求/测试点维度
│   ├── modeling.md             # 第3-4/8阶段：SDD + G/W/T + 字段规范
│   ├── risk.md                 # 第5阶段：风险优先级 P0-P3
│   ├── methods.md              # 第6阶段：方法动态匹配决策表
│   ├── quality_rules.md        # 第8阶段：避坑 + AI友好 + 存储保护
│   ├── dedup_coverage.md       # 第9-10阶段：去重 + 覆盖率 + 停止条件 + 规模分级
│   ├── selfcheck.md            # 第11阶段：15项自查（含断言完整性/对抗生成遍/业务行为来源追溯）+ 自修/阻断决策
│   ├── output_write.md         # 第12-13阶段：完整输出 + 写入机制 + 修改流程 + 临时文件清理
│   ├── review_gate.md          # 第14阶段：人工审核门禁 + 质量门禁 checkbox
│   ├── excel.md                # Excel 输出协议 + 脚本生成机制 + 校验
│   ├── safety_perf.md          # 安全 / 性能 / 兼容 / 本地化（按需）
│   ├── knowledge.md            # 知识总结 13 维度 + 生成机制 + 范例
│   └── example.md              # 端到端范例（不确定格式时读）
└── scripts/                    # 降本脚本（Skill 自动调用）
    ├── verify_md.py            # 回读核对·结构：返回行数/表头/末行/列宽摘要，不把整份 .md 读进上下文
    ├── verify_cases.py         # 回读核对·内容与覆盖：枚举/四段/固定列/等级/ID + 断言/存储/重复/过度设计/需求追溯 + 覆盖统计与规则/风险/测试点追溯（ID精确+token兜底）
    ├── verify_knowledge.py     # 知识总结结构校验：13维度齐全+顺序/元数据/来源统计
    └── project_cases.py        # 知识综合：抽 5 列紧凑投影，不把整份 15 列 .md 读进上下文

case-design/config/             # 领域配置（可选，方向3）
└── domain_config.json          # 业务锚点/关键词维度/异常子类/过度设计豁免类型，缺失用内置默认
```

> `references/` 与 `scripts/` 是 Skill 资产，**不要删除**。运行中产生的临时脚本（如 Excel 生成用的 `.py`）用完会自动删除，与此处的自带脚本不同。

---

## 10. 常见问题 FAQ

**Q1：Skill 没被识别 / `/case-design` 无效？**
检查：① `SKILL.md` 是否在 `.claude/skills/case-design/` 下；② 是否重启了 Claude Code 会话；③ frontmatter 的 `name` 和 `description` 是否完整。

**Q2：提示找不到 Python / `python` 命令？**
Windows 从 python.org 装真实 Python 并勾选 Add to PATH；macOS/Linux 用 `python3`，并确认 `python3 --version` 可用。

**Q3：生成 Excel 失败，报 openpyxl 缺失？**
按 [4.3](#43-安装-openpyxl生成-excel-才需要) 执行 `pip install openpyxl`（Windows）/ `pip3 install openpyxl`（macOS/Linux）后重试。

**Q4：每次都重复问已经回答过的问题？**
说明 `case-design-out/Clarification_Ledger_<需求标识>.md` 未落盘或项目根目录变了。确认：① 完整模式下回答后 Skill 已写台账；② 在同一项目根目录续跑。换项目根目录会视为首次。

**Q5：用例很多，一次写不完怎么办？**
Skill 会做写前规模评估（输出 token 预算）：**默认单文件** `case-design-out/TestCases_<需求标识>.md`；单次 Write `content` 预估 > 24000 token 先压缩，压缩后仍超才拆最小 PART（`case-design-out/TestCases_<需求标识>_PART1.md` 等，按风险排序、不按模块拆），每个仍一次性完整写入。

**Q6：想把 Skill 提供给团队？**
把 `case-design/` 目录（或打包的 zip）放进项目仓库的 `.claude/skills/` 并提交 git，团队成员 clone 后即可用；或各自放进用户级 `~/.claude/skills/`。

**Q7：能否同时跑多个需求？**
可以。每个需求有独立的需求标识，产出物按标识命名互不冲突，`case-design-out/MANIFEST.md` 统一索引。连跑模式适合批量。

**Q8：怎么减少 token 消耗？**
本 Skill 已做渐进式加载（核心 ~6K 常驻）+ 脚本化回读（不把整份 .md 读进上下文）。进一步降本：用连跑/轻量模式减少人工等待与门禁往返；单个需求用例数大时让它按 Feature 拆文件。

---

如需进一步了解各阶段规则细则，参见 `references/` 下对应文件；如需查看用例与知识总结的实际样例，参见 `references/example.md` 与 `references/knowledge.md`（31.15 范例）。
