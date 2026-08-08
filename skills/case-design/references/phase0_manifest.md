# 第0阶段：需求定位（必读·必须首先执行）

> 本参考文件为第0阶段（需求定位）与索引文件管理（原 ch6 第0阶段 + ch32）的**唯一细则来源**。进入第0阶段前读取本文件。SKILL.md 仅含流程入口与速记，细则以本文件为准。

---

## 设计目标

解决多需求场景下快速定位已有产出物。通过索引文件 `case-design-out/MANIFEST.md` 实现**一次读取定位所有相关文件**，避免逐一扫描所有文件。

## 输出位置约定（全局·强制）

> **所有需求产出物统一写入当前项目根目录下的 `case-design-out/` 子目录**（即 `<项目根目录>/case-design-out/`），包括：需求文档 `REQ_*.md`、澄清台账 `Clarification_Ledger_*.md`、测试用例 `TestCases_*.md`/`TestCases_*.xlsx`、知识总结 `Knowledge_*.md`；**索引文件 `MANIFEST.md` 亦位于该目录，但由 Runtime 在 gate PASS 时自动维护（模型禁止 Write/Edit，铁律 4）**。本约定为全局行为，贯穿第0阶段至第15阶段（Excel）及知识总结生成。

* **读取/写入统一加 `case-design-out/` 前缀**：凡涉及上述产出物的读写，路径均为 `case-design-out/<文件名>`
* **目录自动创建**：`case-design-out/` 目录不存在时，按需创建（首次写入产出物前）
* **索引表路径列**：填写**相对 `case-design-out/` 的文件名**（不含目录前缀），读写时统一加前缀
* **临时文件**：Excel 生成/校验用的 ad-hoc 脚本与中间产物（CSV/JSON/txt）同样置于 `case-design-out/` 下，用完即删（见 `references/output_write.md` ch30）
* **skill 自带资产除外**：`scripts/`、`config/`、`references/` 位于 skill 安装目录（`.claude/skills/case-design/`），**不在 `case-design-out/` 产出目录内**，不删除

## 核心原则

* **必须首先执行第0阶段**，禁止跳过直接进入第1阶段
* **必须先读取索引文件**，禁止逐一扫描所有文件来定位需求
* **索引文件是权威入口**：所有需求-文件映射以索引文件为准
* **一次读取定位**：禁止多次读取定位
* **匹配成功必须读取已有文件**：避免重复澄清/重复生成
* **MANIFEST 由 Runtime 维护**（铁律 4）：索引文件 `case-design-out/MANIFEST.md` 是多需求共享索引，由 Runtime 在各 gate PASS 时按里程碑自动更新（Phase 0 `add` / Phase 1 `update` 台账 / Phase 13 `update` 用例文件 / Phase 14 `complete`）。**模型禁止 Write/Edit MANIFEST.md**；失步时执行 `python runtime/qamaster_runtime.py manifest reconcile` 从磁盘重建。模型只在第0阶段读取索引做定位匹配，不做写入。
* **需求标识由 bootstrap 派生**：`req_id` 在 `/case-design` 入口时由 `bootstrap` 派生并写入 `state.req_id`（见 SKILL.md "入口协议"），模型从 state 读取，不在阶段内派生 id——消除"先有鸡还是先有蛋"。

---

## 执行步骤（强制）

### 步骤零：需求文档落盘（强制·#4/#5 反向追溯基准）+ 设计文档落盘（v0.8.0·#8 反向设计文档测试要点追溯基准）

> **根因**：`scripts/verify_cases.py` 的 #4 反向需求追溯 / #5 业务行为来源追溯，**唯一可靠基准是已落盘的需求文档文件**（无文件 → 解析 0 条目 → 返回 `(None,0)` 静默跳过，覆盖退化为依赖 LLM 自查）。故用户的需求文档必须在进入第 1 阶段前落盘。

#### 非 Markdown 文档解析落盘（v0.9.0·根因5 修复：case-design 内置文档解析器）

> **根因**：case-design 原无自己的文档解析器，.docx/.pdf/.pptx/.png 全靠 harness Read 工具——Word 丢页眉页脚/文本框/形状/批注、PDF 复杂版式 OCR 文末汇总丢顺序、扫描件/低置信 OCR 返回空。内容在**进入流水线之前**就部分丢失，后续门禁补不回来。v0.9.0 把 requirement-review 的 `extract_text.py` 能力下沉为 case-design 可直接调用的落盘入口 `scripts/extract_doc.py`：非 .md 输入强制全文抽取并落盘 REQ/DESIGN；检测到降级标记（OCR 失败/空文本）时**硬阻断**要求用户补文本，而非静默继续。

* **触发条件**：用户提供的需求/设计文档是文件路径且后缀非 `.md`/`.txt`（即 `.docx/.doc/.pdf/.pptx/.xlsx/.png/.jpg/.html` 等），不得用 harness Read 工具直接读（会丢内容），必须经 `extract_doc.py` 落盘
* **命令（cwd = 用户项目根目录）**：
  ```
  python skills/case-design/scripts/extract_doc.py <输入文件> --kind req|design --req-id <需求标识> --out-dir case-design-out
  ```
  * `--kind req` → 落盘 `case-design-out/REQ_<需求标识>.md`
  * `--kind design` → 落盘 `case-design-out/DESIGN_<需求标识>.md`
* **退出码处理**：
  * `[OK]`（exit 0）→ 文档已全文落盘，继续后续步骤零流程
  * `[SKIP]`（exit 0）→ 目标文件已存在（既有需求匹配），读入为权威基准，不覆盖
  * `[FAIL]`（exit 1）→ 文档解析降级/失败（扫描版 OCR 空/Word 文本框未抽取/超时）。**硬阻断，不得静默继续**：请用户将该文档转为 Markdown/纯文本后以 `<<<需求文档开始>>>…<<<需求文档结束>>>` 内联提供，或直接给 .md 文件路径。不得绕过此阻断用 Read 工具读原文（会引入丢内容）
* **内联文本/已有 .md/.txt 路径**：不经 `extract_doc.py`，直接走下方"落盘时机"流程整表 Write 落盘

* **落盘时机**：在第 0 阶段读索引（步骤一）之后、步骤二匹配需求标识确定后，**立即**把用户提供的原始需求文档内容（无论用户内联粘贴于 `<<<需求文档开始>>>…<<<需求文档结束>>>`、还是给出文件路径；非 .md 路径先经 `extract_doc.py`）落盘为 `case-design-out/REQ_<需求标识>.md`
* **格式强制（为 #4 可解析·P0-2 修复）**：落盘内容须为可被 `parse_requirement_items_from_lines` 解析的结构——优先保留原始 Markdown 的 `## 二级标题`/`### 三级标题` 分节。**禁止 LLM 创造性补标题（脑补风险）**：`parse_requirement_items_from_lines` 已对纯散文做语义分解（按行为信号词把正文切成"要点:<标题> > <内容>"子条目，v0.9.0 RC6），无标题散文本就可解析，无须臆造标题。若原文确为无结构纯散文，**机械编号分节**而非创造性命名：按段落/句切分后落盘为 `## 需求1`/`## 需求2`（仅编号，标题不复述/不概括/不脑补业务术语），或保留散文原样让解析器分解。文档根 `# 一级标题` 不计入条目（脚本跳过一级）
* **既有文件处理**：若 `case-design-out/REQ_<需求标识>.md` 已存在（已有需求匹配成功，步骤三），读入为权威基准，不覆盖；用户本轮若提供修订版需求，整表覆盖落盘并标注
* **与索引关系**：索引"需求文档"列填 `REQ_<需求标识>.md`（强制，不再"若有"）；Runtime 在 Phase 0 gate PASS 时 `manifest add` 新增索引条目，该列确定性填 `REQ_<需求标识>.md`（模型不写索引）
* **为何强制**：#4/#5 在第 8 出口 gate（写前内存内）与第 13 回读（写后）均以该文件为第 2 参数；不落盘则 #4 静默跳过、#5 退回无 token 核对的弱判定，"需求条目级覆盖未校验"无人知晓——这是"完整覆盖无遗漏"承诺的真实破口

#### 设计文档落盘（v0.8.0·#8-H 反向设计文档测试要点追溯基准；v0.9.0·根因2/3 修复：全量落盘+等价补章节）

> **根因**：设计文档自带的"测试要点"章节（如设计文档 §6/§8）是开发作者视角的最小测试集，但框架事实来源通道里**只有 REQ 需求文档**，设计文档不是正式追溯源——SpEL 扩展/Apollo 热更新/MDC 上下文/字段透传/安全脱敏这类"设计文档明列但需求文档没写"的测试要点从第2阶段起就不在覆盖矩阵，一路失守到第11阶段。v0.8.0 把设计文档升级为正式追溯源。
>
> **v0.9.0 根因2 修复**：旧版只把设计文档的"测试要点/测试点"章节提取落盘，其余章节（技术方案/调用链路/字段映射/异常处理/错误码表）不作为追溯基准 → 设计文档大量内容不进覆盖矩阵。现版**全量落盘**设计文档整文，`parse_design_testpoints` 拓宽识别 `测试要点/测试点/验证点/测试关注/验收标准/检查点/异常处理/错误码/异常分支/边界约束` 等多类可追溯章节并支持多章节散布全文。
> **v0.9.0 根因3 修复**：设计文档本无任何可追溯章节标题时，要求 LLM 按"## 测试要点"等可追溯结构补建（从正文/字段映射/异常处理抽取测试关注点），不再 SKIP 了事。

* **落盘时机**：第0阶段探测到用户提供【设计文档】（`<<<设计文档开始>>>…<<<设计文档结束>>>` 或文件路径）时，在 REQ 落盘后**立即**把**设计文档整文**落盘为 `case-design-out/DESIGN_<需求标识>.md`（v0.9.0：全量落盘，不再只提取"测试要点"章节）。**非 .md 文件路径须经 `extract_doc.py --kind design` 落盘**（见上方"非 Markdown 文档解析落盘"，降级即硬阻断，不得用 Read 工具直读原文）
* **格式强制（为 #8 可解析）**：保留原始 Markdown 章节结构；`scripts/verify_cases.py::parse_design_testpoints` 识别 `## 测试要点`/`## 验证点`/`## 验收标准`/`## 检查点`/`## 异常处理`/`## 错误码`/`## 异常分支`/`## 边界约束` 等可追溯章节及其表格/编号列表/项目符号切分条目。**设计文档无任何上述可追溯章节时（根因3）：不得 SKIP 了事**——须从正文/字段映射/异常处理等章节抽取测试关注点，补建 `## 测试要点` 章节（每条为可被用例覆盖的独立陈述，如"- 重复支付须幂等拦截"），使 #8 可解析出 ≥1 条
* **既有文件处理**：若 `case-design-out/DESIGN_<需求标识>.md` 已存在，读入为权威基准，不覆盖；用户本轮若提供修订版设计文档，整表覆盖落盘
* **与索引关系**：索引新增"设计文档"列填 `DESIGN_<需求标识>.md`（提供设计文档时强制填；未提供时填 `-`）
* **为何强制**：#8-H 在第8/10/13阶段以该文件为 `--design` 参数（v0.9.0：runtime phase_gate 与 Phase13 回读均传 `--design`，旧版漏传致 #8-H/safety_coverage 沦为死代码）；不落盘则 #8 SKIP、safety_coverage 触发条件缺设计文档信号——"设计文档测试要点级覆盖未校验"无人知晓

### 步骤一：读取索引文件

**必须首先读取** `case-design-out/MANIFEST.md`：
* 索引文件存在 → 读入全部索引表
* 索引文件不存在（或 `case-design-out/` 目录不存在）→ 视为首次处理，按需创建 `case-design-out/` 目录（供 REQ 落盘），进入新需求完整设计流程。**MANIFEST 由 Runtime 在 Phase 0 gate PASS 时自动创建（`manifest add`），模型不预写空索引文件**（铁律 4）。

### 步骤二：匹配需求标识

根据用户提供的【需求标识】或从需求文档提取的关键词，在索引表中匹配：
* **精确匹配**：需求标识完全一致 → 定位已有需求，读取对应台账/用例/知识总结
* **关键词匹配**：需求简称匹配 → 定位已有需求，读取对应文件
* **无匹配**：视为新需求，进入完整设计流程

### 步骤三：定位已有文件（若匹配成功）

> 以下文件均位于 `case-design-out/` 子目录下：

* **澄清台账**：`case-design-out/Clarification_Ledger_<需求标识>.md`
* **测试用例**：默认 `case-design-out/TestCases_<需求标识>.md`（单文件，追溯性 section 全需求一份）；仅合并体压缩后仍 > 24000 token 才拆最小 PART `case-design-out/TestCases_<需求标识>_PARTn.md`（按风险排序、不按模块拆），此时索引列逗号分隔全部 PART 文件
* **知识总结**：`case-design-out/Knowledge_<需求标识>.md`

### 步骤四：判断处理模式

| 匹配结果 | 处理模式 | 后续流程 | 索引更新（Runtime 自动·gate PASS 副作用） |
| -- | -- | -- | -- |
| 索引文件不存在 | 新需求（首次） | 进入第1阶段完整设计 | Phase 0 gate PASS 时 Runtime `add`（→进行中） |
| 无匹配 | 新需求 | 进入第1阶段完整设计 | Phase 0 gate PASS 时 Runtime `add`（→进行中） |
| 精确匹配 + 已有台账 | 已有需求（增量） | 读取已有台账 → 第1阶段仅澄清新缺口 | Phase 0 gate PASS 时 Runtime `update` 置进行中 |
| 精确匹配 + 已有用例 | 已有需求（修改） | 读取已有用例 → 按用户反馈进入修改流程 | Phase 0 gate PASS 时 Runtime `update` 置进行中 |
| 精确匹配 + 已有知识总结 | 已有需求（复用） | 读取知识总结 → 作为业务知识库输入 | Phase 0 gate PASS 时 Runtime `update` 置进行中 |

> **关键**：索引更新是 gate PASS 的确定性副作用，**模型不写 MANIFEST**（铁律 4）。已有需求匹配成功后，模型只读取已有产出物并确定处理模式；Runtime 在 Phase 0 gate PASS 时对该 req_id `add`（新需求）或 `update`（已有需求，置进行中），Phase 1 confirm 追加台账列，Phase 13 gate PASS 回填用例文件列，Phase 14 confirm 置已完成——确保跨会话中断时第0阶段能识别为"进行中"而非"新需求"，避免覆盖重生成已落盘产出物。详见下方「索引文件更新（Runtime 自动维护·gate PASS 副作用）」。

> **路径约定**：索引表"需求文档/台账文件/测试用例文件/知识总结"等列填写**相对 `case-design-out/` 子目录的文件名**（如 `TestCases_订单创建-20260702.md`，不含目录前缀）；实际读取/写入位置为 `<项目根目录>/case-design-out/<文件名>`，统一加 `case-design-out/` 前缀定位。本文件示例中的文件名均为相对 `case-design-out/` 的形式。

### 步骤五：判定需求规模（流程深度分级·方向4）

新需求或修改需求在进入第1阶段前，须判定需求规模，决定流程深度（见 `references/dedup_coverage.md` ch26）。用户可显式声明"完整/连跑/轻量"覆盖。

| 规模判定 | 触发条件 | 流程深度 | 阶段裁剪 |
| -- | -- | -- | -- |
| 重型 | 新建模块/新核心业务链路/需求涉及 P0 域信号（资金/支付/权限/状态流转/数据一致性等，第0阶段从需求文档直接可探测）/跨需求跨模块联动 | 完整 15 步 | 不裁剪，全部门禁 |
| 中型 | 已有模块新增功能点/涉及 P1 域信号（并发、幂等、缓存一致性、接口契约） | 中型流程 | 可合并建模阶段（3-4），保留澄清+风险+用例+自查+审核门禁 |
| 轻型 | 字段校验调整/文案变更/低风险参数调整/仅 P2/P3 | 轻型流程 | 可跳过完整规格建模（第4阶段）与覆盖矩阵（第10阶段），保留澄清(1-2)+用例生成(6-8)+断言自查(11)+完整输出(13)+审核门禁(14) |

> **强制**：不得以"轻型"为由跳过需求澄清（第1阶段）或输出模糊断言；不得以"中型/轻型"为由跳过自查（11）或审核门禁（14）。轻型只缩减过程，不降低输出质量底线（脑补禁令/断言可观测/存储合规/去重/覆盖率等全不变）。P0 风险必须走重型（完整15步），禁止降级。

> **P0-1 修复·两段式规模升级（破"P0 风险循环依赖"）**：旧版重型触发条件写"涉及 P0 风险"，但 P0 风险在第5阶段才定级——第0阶段无法判 P0，规模判定→P0→规模判定 形成循环。现版把触发条件改为**第0阶段可从需求文档直接探测的 P0 域信号**（资金/支付/权限/状态流转/数据一致性关键词），不依赖第5阶段产出。**两段式升级**：第0阶段按域信号初判规模并写入 `state.depth`；第5阶段风险分析产出 P0/P1 风险时，Runtime 在 Phase 5 gate PASS 后检测到 `depth != heavy` 且 `risk_p0p1 > 0` → **自动升级 `state.depth = heavy`**，使后续未达阶段（6-14）按重型全门禁运行（含轻型本会跳过的 phase 10 覆盖矩阵）；已合并/已过的阶段不回退，由下游全门禁兜底。即"P0 域信号"初判 + "P0 风险实测"兜底，两道闸都过才放行中型/轻型。

### 步骤六：输入形态探测（契约驱动分支判定）

读取用户提供的全部材料，探测是否含**接口文档**（信号：Swagger/OpenAPI JSON-YAML、`/api/` 路径、HTTP 方法表、入参/出参/错误码表、字段名+类型结构），判定是否启用契约驱动分支。**v0.8.0 触发放宽**：设计文档含接口描述（接口名/facade/方法签名/入参出参 JSON/错误码表/`@Service`/`@RestfulApi`/Dubbo 方法）亦作为契约驱动信号——避免 requirement 驱动下接口契约类测试点完全失守。

| 输入形态 | 判定 | 处理 |
| -- | -- | -- |
| 需求文档 + 接口文档（Swagger/OpenAPI） | 启用契约驱动分支 | 第4阶段建"接口契约模型+变更影响清单"，对变更接口按 `references/methods.md` 统一接口测试矩阵设计契约/规则/场景三类用例；第10阶段 #6 反向接口追溯 |
| 需求文档 + 设计文档含接口描述（v0.8.0·新） | 启用契约驱动分支（设计文档驱动） | 第4阶段从设计文档提取接口契约模型+变更影响清单；变更接口按 methods.md 统一接口测试矩阵设计三类用例 |
| 需求文档 + 新旧两版接口文档 | 启用契约驱动分支（diff 驱动） | 字段级 diff 圈定变更接口（最强信号） |
| 仅接口文档（无需求） | 契约兜底 | 全量接口按"新增接口"处理 + 澄清问 @开发 本次范围 |
| 需求文档（无接口无设计文档接口描述） | 不启用 | 退回纯需求驱动（现有 15 步） |

* 变更接口圈定按 5 条信号合并去重（需求显式声明 / 接口文档变更标记 / 新旧 diff / 需求-接口交叉映射推断 / @开发 澄清兜底），详见 `references/modeling.md` 接口契约模型
* 契约驱动分支与规模分级（步骤五）、运行模式（SKILL.md 6.5）正交，可叠加
* 变更接口数 = 0 -> 不走契约分支，退回纯需求驱动

---

## 索引文件位置与命名

* 位置：**当前项目根目录下的 `case-design-out/` 子目录**（`<项目根目录>/case-design-out/MANIFEST.md`），固定命名 `MANIFEST.md`，禁止重命名或删除
* 与所有需求产出物同目录（即全部落盘到 `case-design-out/` 下，见 SKILL.md "输出位置约定"）
* 第0阶段读取索引：先在 `case-design-out/` 下读取 `MANIFEST.md`；该目录不存在时视为首次，按需创建 `case-design-out/` 并新建空索引

## 索引文件格式（强制）

```markdown
# 需求文件索引 MANIFEST

> 本文件为所有需求产出物的快速定位入口。处理任何需求前**必须先读取本文件**。
> 产出物均位于本目录（`case-design-out/`）下，索引列填相对文件名，读写时统一加 `case-design-out/` 前缀。

---

## 索引表

| 需求标识 | 需求名称 | 需求文档 | 设计文档 | 台账文件 | 测试用例文件 | 知识总结 | 状态 | 更新时间 |
| -- | -- | -- | -- | -- | -- | -- | -- | -- |
| `订单创建-20260702` | 订单创建功能 | REQ_订单创建-20260702.md | - | Clarification_Ledger_订单创建-20260702.md | TestCases_订单创建-20260702.md | Knowledge_订单创建-20260702.md | 已完成 | 2026-07-02 |
| `支付重构` | 支付流程重构 | REQ_支付重构.md | DESIGN_支付重构.md | Clarification_Ledger_支付重构.md | TestCases_支付重构.md | Knowledge_支付重构.md | 进行中 | 2026-07-03 |
```

> "设计文档"列：提供【设计文档】时填 `DESIGN_<需求标识>.md`（v0.8.0·#8-H 追溯基准）；未提供时填 `-`。既有索引（无该列）向后兼容——读取时缺该列视为 `-`。

## 文件命名规范（汇总）

> 以下命名均为相对 `case-design-out/` 子目录的文件名；实际落盘位置为 `<项目根目录>/case-design-out/<文件名>`。

| 文件类型 | 命名格式 |
| -- | -- |
| 需求文档 | `REQ_<需求标识>.md` |
| 设计文档（v0.8.0） | `DESIGN_<需求标识>.md`（提供【设计文档】时**全量落盘整文**；v0.9.0 不再只提取"测试要点"章节） |
| 澄清台账 | `Clarification_Ledger_<需求标识>.md` |
| 测试用例 | 默认：`TestCases_<需求标识>.md`（单文件）；仅压缩后仍超 24000 token 才拆最小 PART：`TestCases_<需求标识>_PARTn.md`（按风险排序、不按模块拆；多 PART 时索引列逗号分隔） |
| 测试用例Excel | `TestCases_<需求标识>.xlsx` |
| 知识总结 | `Knowledge_<需求标识>.md` |

> 上述命名均为相对 `case-design-out/` 的文件名；实际落盘位置为 `<项目根目录>/case-design-out/<文件名>`。

## 状态说明

| 状态 | 含义 |
| -- | -- |
| 进行中 | 需求正在处理，测试用例尚未全部完成 |
| 已完成 | 审核通过，知识总结已生成 |
| 已归档 | 需求已结束，不再修改 |

---

## 索引文件更新（Runtime 自动维护·gate PASS 副作用）

> **设计原则（Runtime 控制协议铁律 4）**：`MANIFEST.md` 是多需求共享可变资源，其协调权属于 Runtime，不属于模型。索引不再由模型"整表 Write"维护，而是 Runtime 在各阶段 gate PASS 时作为确定性副作用自动更新——模型无法影响是否/何时更新多需求索引，"流程由 Runtime 严格控制、与模型无关"延伸到索引层。
> Runtime 在 `FileLock` 下做 read-modify-write（原子 `os.replace`），保证多需求并发更新不损坏不丢行；更新失败不阻断 gate（best-effort 索引），失步时 `manifest reconcile` 从磁盘重建。
> 状态语义：`进行中` = 明确的中间态（路径已填全，部分产出物已落盘）；`已完成` = 第14阶段审核通过（confirm）的提交点。

| gate PASS 触发点 | Runtime 副作用 | 状态变化 |
| -- | -- | -- |
| **Phase 0** gate PASS | `manifest add`：新增索引条目（需求标识=`req_id`；需求名称从 `REQ_<id>.md` 首个 `# ` 标题自动抽取；探测 `DESIGN_<id>.md` 存在则填，否则 `-`；需求文档列填 `REQ_<id>.md`） | → 进行中 |
| **Phase 1** confirm 通过 | `manifest update`：台账文件列填 `Clarification_Ledger_<id>.md` | 进行中 |
| **Phase 13** gate PASS | `manifest update`：用例文件列填实际落盘清单（glob `TestCases_<id>*.md`，拆 PART 时逗号分隔） | 进行中 |
| **Phase 14** confirm 通过 | `manifest complete`：状态置已完成 | → 已完成 |

> 关键：索引更新是 gate PASS 的确定性副作用——模型无需、也禁止自行 Write MANIFEST。模型在第0阶段**只读**索引做定位匹配；新增/进度/完成三态均由 Runtime 在对应 gate PASS 自动落盘。
> **跨会话中断兜底**：若 gate PASS 成功但 `manifest add` 锁超时失败（局部不一致，不阻断 gate），重跑同一需求时 bootstrap 会检测到在途状态走 RESUME；`status --all` 列出所有在途 req；失步严重时执行 `python runtime/qamaster_runtime.py manifest reconcile` 从磁盘 `REQ_*.md`/`TestCases_*.md` 重建索引（兜底）。

### 时机一：第0阶段 - 已有需求匹配成功（Runtime 在 Phase 0 gate PASS 时执行）

> 模型无需操作 MANIFEST。模型在第0阶段完成 REQ 落盘、`set --depth --input-kind --mode` 后跑 `gate`，gate PASS 时 Runtime 自动 `manifest add`（新需求）或 `manifest update`（已有需求，置进行中）。

```
[模型] 读 MANIFEST 做定位匹配 → 落盘/确认 REQ_<id>.md → set depth/input-kind/mode → gate
[Runtime gate PASS 副作用] FileLock 下 add 或 update 该 req_id 行（状态=进行中，更新时间=当前日期）
```

模型侧禁止：自写 MANIFEST、Edit 追加、跳过 gate 直接进第1阶段。

### 时机二：第1阶段 - 新需求澄清台账首次生成（Runtime 在 Phase 1 confirm 通过时执行）

> 模型在第1阶段生成并落盘 `Clarification_Ledger_<id>.md` 后，跑 `confirm`；confirm 通过时 Runtime 自动 `manifest update` 台账文件列。模型不写 MANIFEST。

```
[模型] 落盘 Clarification_Ledger_<id>.md → confirm --req-id <id>
[Runtime confirm 副作用] FileLock 下 update：台账文件列=Clarification_Ledger_<id>.md（幂等）
```

> 说明：新需求的索引条目在 Phase 0 gate PASS 时已由 Runtime `add` 创建（路径列：需求文档=`REQ_<id>.md`，设计文档=探测存在则填，其余 `-`，需求名称从 REQ 首个 `# ` 标题自动抽取，状态=进行中）。Phase 1 confirm 仅追加台账文件列，不重复新增。

### 时机三：第13阶段 - 测试用例 .md 落盘（Runtime 在 Phase 13 gate PASS 时执行）

> 模型在第13阶段一次性 Write 落盘 `TestCases_<id>.md`（或拆 PART）+ verify_md/verify_cases 回读通过后跑 `gate`；gate PASS 时 Runtime 自动 `manifest update` 用例文件列（glob `TestCases_<id>*.md` 回填实际落盘清单，拆 PART 时逗号分隔）。模型不写 MANIFEST。

```
[模型] Write TestCases_<id>.md (或各 PART) → verify_md.py + verify_cases.py 回读 → gate
[Runtime gate PASS 副作用] FileLock 下 update：用例文件列=glob(TestCases_<id>*.md) 实际清单（逗号分隔），状态保持进行中
```

> 跨会话兜底：若 Phase 13 gate PASS 成功但 `manifest update` 锁超时失败（best-effort，不阻断 gate），`manifest reconcile` 从磁盘重建。跨会话中断在第13阶段后，bootstrap 检测到在途状态走 RESUME，模型按 `status --req-id <id>` 输出的用例文件列定位已落盘用例走"修改流程"而非"重新生成覆盖"。

### 时机四：第14阶段审核通过后 - 新需求首次完成 / 已有需求修改完成（Runtime 在 Phase 14 confirm 通过时执行·提交点）

> 模型在第14阶段输出审核提示、用户 confirm 后跑 `confirm`；confirm 通过时 Runtime 自动 `manifest complete`（状态置已完成）。模型不写 MANIFEST。

```
[模型] 输出审核提示 → 用户答复审核通过 → confirm --req-id <id>
[Runtime confirm 副作用] FileLock 下 complete：状态=已完成，更新时间=当前日期
```

审核通过后顺序：用户 confirm → Runtime `manifest complete`（状态=已完成）→ 生成/更新知识总结 `Knowledge_<id>.md`（POST_CONFIRM_KNOWLEDGE 后置动作，`verify_knowledge.py` 校验）→ 询问是否生成 Excel。MANIFEST 置已完成由 Runtime 在 confirm 时自动完成，先于知识总结生成。

### 更新方式

* 所有索引变更由 Runtime 在 gate PASS 副作用中完成（FileLock + 原子 `os.replace`），**模型禁止 Write/Edit MANIFEST.md**
* 失步时执行 `python runtime/qamaster_runtime.py manifest reconcile` 从磁盘重建
* 模型侧仅在第0阶段读取索引做定位匹配（只读），不参与写入

---

## 需求标识生成逻辑（由 bootstrap 执行·模型不派生 id）

> **由 `/case-design` 入口的 `bootstrap` 步骤执行**（见 SKILL.md "入口协议"）。模型在第0阶段直接读取 `state.req_id` 使用，不在阶段内派生 id——消除"先有鸡还是先有蛋"。以下为 bootstrap 内部的派生规则（供理解，模型无需手动执行）：

```
步骤一：提取需求简称
  1. 文件路径输入 → extract_doc.py 落盘后从首个 `# ` 标题提取核心关键词
     内联文本输入 → 取首个非空行清洗
  2. 去除特殊字符（保留中文、英文、数字、连字符）
  3. 保留核心业务词汇（如"订单创建"、"支付重构"）
  4. 简称长度建议 ≤ 15字符

步骤二：去重与碰撞处理
  1. 查 list_active_reqs（在途需求）+ MANIFEST 已归档索引去重
  2. 碰撞则加日期后缀 `-YYYYMMDD`（开始处理日期）
  3. 无碰撞直接用简称

步骤三：输出
  1. bootstrap 输出 BOOTSTRAP OK req_id=<id>（命令文件据之跑 start）
  2. 检测到进行中状态则输出 BOOTSTRAP RESUME req_id=<id> phase=N status=S
```

**强制**：需求简称必须来自需求文档核心内容禁止杜撰；需求标识必须唯一；带日期标识时日期必须准确；简称长度 ≤ 15字符。bootstrap **不创建状态**（幂等可重跑）；`start --req-id <id>` 才创建/续跑状态。

---

## 新需求 vs 已有需求处理差异

| 处理阶段 | 新需求 | 已有需求 |
| -- | -- | -- |
| 入口（bootstrap） | bootstrap 派生 req_id（不创状态）；输出 OK | bootstrap 检测到在途状态，输出 RESUME |
| 第0阶段（步骤零） | **落盘 `REQ_<需求标识>.md`（强制）**；索引待 Phase 0 gate PASS 由 Runtime `add` | 落盘或确认 `REQ_<需求标识>.md` 已存在；Phase 0 gate PASS 由 Runtime `update`（置进行中） |
| 第1阶段 | confirm 通过由 Runtime `manifest update`（台账文件列） | 增量澄清（仅澄清新缺口）；confirm 通过由 Runtime `update` 台账文件列 |
| 第2-12阶段 | 完整设计流程 | 增量/修改流程 |
| 第13阶段 | gate PASS 由 Runtime `manifest update`（用例文件列，状态进行中） | 同左 |
| 第14阶段审核通过后 | confirm 通过由 Runtime `manifest complete`（状态=已完成） | 同左 |

---

## 强制要求（汇总）

* **所有产出物统一写入 `case-design-out/` 子目录**；索引文件固定位于 `case-design-out/MANIFEST.md`（由 Runtime 在 gate PASS 时自动维护，模型不写），读写产出物统一加 `case-design-out/` 前缀
* **需求标识由 bootstrap 派生**：入口 bootstrap 派生 `req_id` 写入 `state.req_id`，模型从 state 读取，不在阶段内派生 id
* **需求文档 `case-design-out/REQ_<需求标识>.md` 强制落盘**（第0阶段步骤零）：用户内联提供或给文件路径的需求文档，必须在进入第1阶段前落盘为 `REQ_<需求标识>.md`（为 #4/#5 反向追溯提供唯一可靠基准；纯散文/无标题文档落盘前须补 `## 二级标题` 分节使其可被 `parse_requirement_items_from_lines` 解析，见步骤零格式强制。v0.9.0：解析器已增强为按标题+正文语义分解，标题下编号项/项目符号/含行为信号词的散文句均切为独立子条目，无需人工逐句拆分）
* **设计文档 `case-design-out/DESIGN_<需求标识>.md` 强制全量落盘**（v0.9.0·根因2）：提供【设计文档】时必须落盘**整文**（非仅"测试要点"章节）；设计文档无任何可追溯章节标题时（根因3）须补建 `## 测试要点` 章节，不得 SKIP
* **非 Markdown 文档须经 `scripts/extract_doc.py` 落盘**（v0.9.0·根因5）：用户提供 .docx/.pdf/.pptx/.xlsx/.png 等非 .md 文件路径时，禁止用 harness Read 工具直读（丢页眉/文本框/OCR 顺序），必须运行 `python skills/case-design/scripts/extract_doc.py <文件> --kind req|design --req-id <需求标识> --out-dir case-design-out` 落盘；解析降级（`[FAIL]` exit 1）即硬阻断请用户补 Markdown/纯文本，不得静默继续
* 必须首先读取索引文件；一次读取定位，禁止逐一扫描所有文件、禁止多次读取定位
* 匹配成功必须读取已有文件，避免重复澄清/重复生成
* 跨需求（不同需求标识）复用 `case-design-out/MANIFEST.md` 中其他条目的知识总结前，必须先过 `references/knowledge.md` §31.11 相关性门槛 + 收益预检；同域不同子系统（如 CDR 监控告警 vs 外呼任务系统）不构成相关，禁止凭泛域词联想读取
* **MANIFEST 由 Runtime 在 gate PASS 时自动维护**（铁律 4）：索引按里程碑（Phase 0 add / Phase 1 update 台账 / Phase 13 update 用例文件 / Phase 14 complete）由 Runtime 在 FileLock 下自动更新；**模型禁止 Write/Edit MANIFEST.md**；失步时 `manifest reconcile` 重建
* 进行中条目是明确的中间态，不视为"半成品"；路径列禁止填"待生成"占位
* 需求标识必须唯一，必要时添加日期区分（由 bootstrap 处理碰撞）
* 索引文件禁止删除；文件命名必须包含需求标识

## 禁止（汇总）

* 把产出物写入 `case-design-out/` 之外的目录（须统一写入 `case-design-out/` 下）
* 在项目根目录散落 `MANIFEST.md`/`TestCases_*.md` 等产出物（须置于 `case-design-out/` 下）
* 用 harness Read 工具直读 .docx/.pdf/.pptx/.xlsx/.png 等非 Markdown 文档原文（须经 `scripts/extract_doc.py` 落盘，避免丢页眉/文本框/OCR 顺序；降级即硬阻断请用户补文本，不得静默继续）
* 跳过第0阶段直接进入第1阶段
* **跳过第0阶段步骤零需求文档落盘**（不落盘 `REQ_<需求标识>.md` 直接进第1阶段 → #4/#5 无基准静默跳过，"完整覆盖"承诺失效）
* 逐一扫描所有文件来定位需求（必须先读索引）
* 索引文件存在却不读取
* 匹配成功却不读取已有台账/用例/知识总结
* **Write/Edit `case-design-out/MANIFEST.md`**（铁律 4：索引由 Runtime 在 gate PASS 时自动维护，模型禁止任何 Write/Edit；失步用 `manifest reconcile`）
* **跳过 gate 直接进入下一阶段**（索引更新是 gate PASS 的确定性副作用，不跑 gate 则 Runtime 不会 add/update/complete 索引）
* 在阶段内自行派生需求标识（由 bootstrap 派生写入 `state.req_id`，模型从 state 读取）
* 删除或重命名索引文件
* 文件命名不包含需求标识
* 索引表内容与实际文件不一致（失步时执行 `python runtime/qamaster_runtime.py manifest reconcile` 重建）
* 需求标识与已有需求冲突
* 需求标识随意杜撰
* 文件路径字段填写"待生成"等中间状态（Runtime 在各 gate PASS 时一次性确定性填全）
* 把索引中其他需求（不同需求标识）的知识总结/台账/用例自动当作本需求业务知识库读取——跨需求复用须先过 `references/knowledge.md` §31.11 相关性门槛 + 收益预检；用户在【业务知识库摘要】显式提供者除外