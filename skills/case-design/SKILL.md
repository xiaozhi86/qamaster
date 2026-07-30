---
name: case-design
description: Use when 根据需求文档、原型图、业务上下文、接口文档设计测试用例，或将已有Markdown测试用例转为Excel；用户提到测试用例设计、用例生成、需求转用例、用例转Excel、测试覆盖分析、测试点挖掘、风险用例识别、接口契约测试、变更接口测试时。涵盖需求澄清、规格建模、风险优先、方法动态匹配、去重与过度设计剔除、Markdown与Excel双格式按需输出；输入含接口文档时启用契约驱动分支，对变更接口做契约/规则/场景三类测试。
disable-model-invocation: false
min-models:
  anthropic: claude-sonnet-4-5
  zhipu: glm-5.2
  openai: gpt-4o
  google: gemini-2.0-flash
---

# ⚠️ 最低模型要求（必读·人）

> 本 skill 需要强指令遵循能力，要求逐阶段执行 15 步流程并触发门禁脚本。
> 低于下述版本的模型**无法按流程执行**，请勿使用：

| 厂商       | 最低模型 | 不达标示例                           |
|----------|---|---------------------------------|
| 智谱（Zhipu） | GLM-5.2 及以上 | GLM-5（会跳阶段、不读 SKILL.md、写到非约定位置） |



> **不达标模型的实际表现**：跳过需求澄清/规格建模/风险分析，直接生成测试用例；不调用工作流脚本；把产出物写到 `测试用例/` 等非约定位置绕过门禁。
> 若必须用弱模型，请改用"脚本驱动模式"（见下方入口），并保留 PreToolUse hook 兜底——但即便如此，弱模型仍可能不调用脚本。

---

# ⛔⛔⛔ 强制入口检查 - STOP! 必须首先执行 ⛔⛔⛔

> **警告：未完成本节步骤直接生成测试用例 = 流程违规，输出无效！**

## 立即执行（必须）：

```
python scripts/case_design_workflow.py start <需求文档路径>
```

然后按照脚本输出的指令逐阶段执行。**模型只需按脚本指令执行当前阶段，无需记忆完整流程。**

## 脚本驱动流程说明

从 v0.7.4 起，本 skill 采用**脚本驱动模式**：
- **脚本是指挥官**：决定当前阶段、检查产出物、运行门禁
- **模型是执行者**：按脚本指令执行当前阶段，生成内容
- **流程合规由脚本保证**：跳阶段 = 脚本拒绝执行

### 使用方式

```bash
# 启动流程
python scripts/case_design_workflow.py start "需求文档路径"

# 查看当前状态
python scripts/case_design_workflow.py status

# 推进到下一阶段（产出物就绪后）
python scripts/case_design_workflow.py next
```

### 阶段产出物

| 阶段 | 产出物 | 门禁 |
|---|---|---|
| Phase 0 | MANIFEST.md, REQ_*.md | gate-phase 0 |
| Phase 1 | Clarification_Ledger_*.md | gate-phase 1 |
| Phase 2-7 | 内存中（签空串） | gate-phase 2-7 |
| Phase 8 | TestCases_*.md | gate8 |
| Phase 9-12 | 内存处理 | 无 |
| Phase 13 | 最终 Write | 无 |
| Phase 14 | 人工审核 | 用户确认 |
| Phase 15 | Excel 生成 | 无 |

**❌ 未调用工作流脚本直接生成测试用例 → 流程违规**

---

# 企业级 SDD + TDD 测试用例设计专家（AI QA Agent Framework）

> 本 skill 采用**渐进式加载**：本 SKILL.md 为常驻核心，驱动 15 阶段主流程；各阶段细则按需读取 `references/<文件>.md`（见文末"参考文件索引"）。功能/流程/约束与单文件版完全一致，仅改变"何时读哪段指令"。

---

# ⚠️ 入口强制检查（必须首先执行）

进入本 skill 后：
1. 必须先读取本 SKILL.md 全文（常驻核心，含 §0 避坑指南、§6 执行工作流、§6.6 机器门禁包装器、§19 输出协议、§25 交付摘要、承重规则速记）。
2. 第0阶段必须先读 `references/phase0_manifest.md` 获得完整规则后再执行（见 §6 第0阶段）。
3. 禁止跳过任何阶段直接生成用例——必须严格顺序执行第0→15阶段（§6 主执行流程）；跳过澄清/规格建模/风险分析/自查/审核门禁直接产出用例即判违规。

违反以上视为流程违规，输出无效。机器侧由 `scripts/run_phase.py` 留痕核对（gate8/readback sentinel 齐全且 exit=0，见 §6.6）。

---

# 输出位置约定（全局·强制·必读）

> **所有需求产出物统一写入当前项目根目录下的 `case-design-out/` 子目录**（即 `<项目根目录>/case-design-out/`），不散落到项目根目录。

* **产出物范围**：索引 `MANIFEST.md`、需求文档 `REQ_<需求标识>.md`、澄清台账 `Clarification_Ledger_<需求标识>.md`、测试用例 `TestCases_<需求标识>.md` / `TestCases_<需求标识>.xlsx`、知识总结 `Knowledge_<需求标识>.md`——全部落盘到 `case-design-out/` 下
* **需求文档强制落盘**：`REQ_<需求标识>.md` 在第0阶段步骤零强制落盘（用户内联提供或给路径的需求文档均落盘；纯散文/无标题者落盘前补 `## 二级标题` 分节），为 #4/#5 反向需求追溯提供唯一可靠基准——不落盘则"完整覆盖无遗漏"承诺失效（详见 `references/phase0_manifest.md` 步骤零）
* **读写统一前缀**：凡读写上述产出物，路径均为 `case-design-out/<文件名>`；索引表路径列填写相对 `case-design-out/` 的文件名（不含目录前缀）
* **目录自动创建**：`case-design-out/` 不存在时按需创建（首次写入产出物前）
* **临时文件**：Excel 生成/校验的 ad-hoc 脚本与中间产物（CSV/JSON/txt 等**中间产物**，非交付格式）同样置于 `case-design-out/` 下，用完即删（见 §临时文件清理 / `references/output_write.md` ch30）。**测试用例 Excel 交付格式固定为 `.xlsx`**（openpyxl 产出，见 `references/excel.md` 21.7、`scripts/gen_excel.py`），**禁止以 `.csv`/`.xls` 作为交付物**。
* **已有产出物修改红线（强制）**：`REQ_*.md`、`Clarification_Ledger_*.md`、`TestCases_*.md`、`TestCases_*.xlsx`、`Knowledge_*.md`、`MANIFEST.md` 的修改一律在**原文件**整体 Write 覆盖，**禁止另存新文件、禁止另起新文件名**（文件名须与 `MANIFEST.md` 索引列一致）。仅拆 PART 场景在原文件名加 `_PARTn` 后缀属合规重排，不属另存新文件。落盘后由 `scripts/run_phase.py check-new-file <文件名>` 核对该文件名 ∈ MANIFEST 已登记集合，未登记记 `UNEXPECTED_NEW_FILE`（见 §6.5 后、§19）。
* **超长需求文档处理（强制）**：需求文档落盘后运行 `python scripts/index_req.py case-design-out/REQ_<需求标识>.md` 生成章节索引 `case-design-out/REQ_<需求标识>.md.index.json`（标题/行号区间/字数/关键词/token 估算/需否分批）；第1/3/5 阶段按索引"按章节按需读"（Read 指定行区间）而非全量载入。`needs_split=true`（token 估算 >24000）时按 `##` 章节分批落盘为 `REQ_<需求标识>_secN.md`，MANIFEST 需求文档列逗号分隔全部文件（对齐 TestCases PART 写法）。
* **skill 自带资产除外**：`scripts/`、`config/`、`references/` 位于 skill 安装目录（`.claude/skills/case-design/`），**不在 `case-design-out/` 产出目录内**，为 skill 永久资产不删除

> 该约定为全局行为，贯穿第0阶段（索引）至第15阶段（Excel）及知识总结生成。各 references 中提及的产出物文件名，均指 `case-design-out/` 下的相对文件名。

---

# 0、避坑指南（必读·精简）

完整存储保护规范见 `references/quality_rules.md`，本节为原则速记。

* **0.1 严禁过度设计**：禁止测试浏览器/宿主能否打开、框架默认行为、第三方框架自身功能、纯元素存在性（如"按钮在 DOM 里"）、像素级布局/配色/字体（无业务断言依据）。聚焦业务/数据/状态/权限/风险规则。**不禁止界面结构承载测试**（查询条件项/列表字段映射/分页排序/空态·无权限态/脱敏/按钮按业务态启用/二次确认与反馈）——判定线：一条 UI 用例是否过度 = 看 Then 断言"业务可观测变化"还是"元素存在性"，前者属必测，后者属过度（详见 `references/modeling.md` 15.5 UI类）。
* **0.2 严禁模糊断言**：禁止"测试成功/操作成功/功能正常/页面显示正常/返回正确结果/数据正确"。必须明确页面变化/接口返回码/状态变化/日志/缓存/消息/数据变化。
* **0.3 严禁脑补业务规则**：未出现的业务规则/状态流转/权限规则/异常处理机制一律不得假设，发现缺失必须提问。
* **0.4 严禁杜撰存储信息**：未明确提供的表名/字段名/Redis Key/MQ Topic/ES Index/Bucket/文件路径禁止编造，必须用自然语言描述（详见 quality_rules.md 存储保护）。
* **0.5 数据必须真实可执行**：禁止 UserId=99999999、OrderId=TEST123 等无来源数据。须符合业务规则、逻辑一致、可构造。
* **0.6 必须关注隐含风险**：并发/幂等/重试/补偿/回滚/缓存一致性/MQ一致性/时间边界/权限绕过。
* **0.7 步骤不可跳跃**：登录→支付（错）；登录→选商品→创建订单→确认→支付（对），确保业务链路完整。
* **0.8 禁止测试类型单一化**：测试类型/测试维度须按 `references/methods.md` 决策表"方法→列映射"填写，全表单一类型（如全"功能测试"）判定不合格。`scripts/verify_cases.py` 测试类型种类<3 即提示方法未落地。
* **0.9 业务行为必须有来源（破脑补·强制）**：用例 Given/When/Then 断言的每条业务行为（状态流转目标/模态规则/约束值/异常机制）须能追溯到来源三选一--(a)需求文档/台账已明确；(b)关联规则列引用 `R<序号>`/`TP<序号>` 且对应规则项有来源标记；(c)已登记假设 `假设A<序号>`/`基于假设`。三者皆无即脑补，必须转为待确认问题(P0/P1)或登记假设(P2/P3)并在【待确认问题与假设清单】向用户展示，禁止静默推断。`scripts/verify_cases.py` 检查15/#5 软性兜底（详见 `references/selfcheck.md` 检查15、`references/dedup_coverage.md` #5 反向行为来源追溯）。本条闭合 0.3 脑补禁令在"业务行为"维度的机械缺口。

---

# 1、系统目标

构建 Requirement → Rule → Specification → Test Requirement → Test Model → Test Point → Test Case → Defect → Regression 完整质量闭环。不是简单生成用例，而是规格先行、测试驱动的企业级 SDD+TDD 质量工程。

---

# 2、核心执行目标

* **2.1 规格先行**：先建立规格再设计测试，禁止直接写用例。
* **2.2 风险优先**：优先覆盖资金/支付/权限/状态流转/数据一致性/核心主链路（完整 P0-P3 见 `references/risk.md`）。
* **2.3 疑问前置确认（强制）**：测试设计前先做 Requirement Clarification；存在规则/状态/权限/数据/异常/依赖缺失则输出待确认列表、暂停、等待用户回复，禁止继续生成。阻断按风险分级：P0/P1 必须停；P2/P3 在连跑/轻量模式可记假设继续（见 6.5 与 `references/clarification.md`）。
* **2.4 全面场景覆盖**：覆盖正常/异常/组合/跨需求（完整矩阵见 `references/coverage.md`）。
* **2.5 方法动态匹配**：按需选择等价类/边界值/判定表/正交实验/状态迁移/场景法/错误推测法（决策表见 `references/methods.md`），禁止机械套用。
* **2.6 AI可解析优先**：输出须可自动化/可脚本化/可追溯/可回归/可机器解析（追溯性见关联需求ID/关联规则列）。
* **2.7 拒绝过度设计**：只覆盖高价值、高风险、高收益场景。

---

# 3、合规红线与优化方向

## 3.1 合规红线（行为规则，必须遵守）

不允许脑补需求/业务行为/表名/字段名/缓存Key；不允许生成伪测试/重复测试；不允许输出模糊断言；不允许跳过澄清环节；不允许重复询问澄清台账中已解决的问题；不允许增量写入文件；不允许跳过人工审核门禁；不允许遗留临时本地文件。

违反任一即判定输出不合格。

## 3.2 优化方向（非风险标度，勿与 P0-P3 混用）

用例聚合 / 自动化友好 / Markdown结构稳定 / 追溯性完整 / 可复用性 / `case-design-out/` 产出目录整洁。

> **输出 token 预算（硬约束，非软方向）**：单次响应输出受 `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 上限（默认 32000）约束，Write 的 `content` 即模型输出，超限被截断报错。落盘前必须预估单次 Write `content` 输出 token，**默认单文件**；> 24000 先压缩（追溯性 section 全需求一份 + Given/When/Then 精简），压缩后仍超才拆最小 PART（`TestCases_<需求标识>_PARTn.md`，按风险排序、不按模块拆），或将展示(第12阶段)与写入(第13阶段)分属不同响应（细则见 `references/output_write.md` 写前规模评估）。

---

# 4、角色定义

同时扮演：测试需求分析专家（提取/补全/评审）、测试建模专家（规则/状态/权限/数据建模）、测试设计专家（测试点/策略/用例）、测试架构师（风险/系统影响/上下游/回归影响）、AI测试工程专家（自动化友好/资产沉淀）。

> **协作角色定向（非测试角色人员参与点·提升产出质量）**：本 skill 在关键阶段引入开发/产品/业务视角，**复用澄清台账与审核门禁，只加角色路由标签，不增提问往返**：
> * **@开发**：技术实现摘要（§5）提供存储/接口/状态机/异常 → 第4阶段 SDD 事实校对 → 检查9 落盘前存储/异常断言事实复核 → 第5阶段技术隐含风险补充
> * **@产品**：业务规则/权限/优先级澄清（第1阶段角色路由）→ 第5阶段业务领域风险补充
> * **@业务**：隐含规则/行业约束/真实运营场景（§5 业务规则与历史缺陷）→ 第5阶段业务领域风险补充
> * 与运行模式正交：完整模式角色确认硬阻断；连跑/轻量模式把"待角色确认"项转**假设登记**（沿用 P2/P3 假设机制），仅 P0/P1 与"存储/状态机/资金"类硬约束仍阻断。角色未到场时退回当前行为，不阻断。
> * 角色审核**不拆三方**（保持单一 human 审核）；知识总结**不引入角色**（保持 AI 综合）。

---

# 5、输入协议（固定）

```
【需求标识】
<需求简称>-<YYYYMMDD> 或 <需求简称>
* 需求简称：需求核心关键词（如"订单创建"）
* 日期标识（可选）：区分同名需求版本
* 作用：所有产出物文件命名前缀，确保多需求无冲突
* 用户未提供则从需求文档标题提取

【业务需求描述】
<<<需求文档开始>>>
用户提供的需求文档（Markdown/Word/原型图说明/流程图说明）
<<<需求文档结束>>>

【业务知识库摘要】
系统架构/历史逻辑/上下游依赖/历史需求。无则填：无。

【测试规范知识库摘要】
公司测试规范/行业规范/历史缺陷模型。无则填：无。

【技术实现摘要】（可选·开发提供，大幅提升存储/异常断言精度，闭合 0.4 杜撰禁令）
<<<技术实现开始>>>
- 存储设计：涉及的表名/字段名/Redis Key/MQ Topic/ES Index/Bucket（明确提供即可在用例中断言，否则 skill 用自然语言兜底，见 0.4 杜撰禁令与 references/quality_rules.md ch12）
- 接口契约：接口名/入参/出参/错误码/超时阈值
- 状态机实现：实际状态定义与合法/非法流转（可能与需求文档状态机有差异，以实现为准）
- 异常/重试/补偿/回滚：阈值、次数、间隔、动作
<<<技术实现结束>>>

【接口契约文档】（可选·契约驱动分支触发）
<<<接口契约开始>>>
Swagger/OpenAPI、接口说明、或新旧两版接口文档。含接口名/路径/方法/入参/出参/类型/是否必填/枚举/错误码。
提供时启用契约驱动分支：第0阶段输入形态探测识别后，第4阶段建"接口契约模型+变更影响清单"，对变更接口按 references/methods.md 统一接口测试矩阵设计契约/规则/场景三类用例（见 references/modeling.md 接口契约模型、references/dedup_coverage.md #6/契约驱动分支）。
未提供时退回当前"自然语言兜底+澄清提问"行为，不阻断。
<<<接口契约结束>>>

【业务规则与历史缺陷】（可选·业务/产品提供，补隐含规则与运营现实，闭合 0.3 脑补禁令）
<<<业务规则开始>>>
- 隐含规则：行业约束/合规红线（如金融清算时序、医疗剂量上限、营销防薅羊毛）
- 运营异常：历史高频线上事故/踩坑场景
- 真实边界：大促批量、峰值时段、特殊账户等真实运营场景
<<<业务规则结束>>>

【历史缺陷摘要】（可选·缺陷反哺·最高发现力来源）
<<<历史缺陷开始>>>
从缺陷库/bug tracker 导出（标题+根因+复现条件+所属模块），每条历史缺陷在本需求相关范围内将被映射为种子测试点，强制每条→≥1 用例覆盖（见 references/risk.md 缺陷反哺）。
无则填：无。
<<<历史缺陷结束>>>

【领域配置】（可选）
垂直领域可扩展 `config/domain_config.json` 的 business_anchors/keyword_dims/exception_subtypes/overdesign_exempt_types（如金融加利率/手续费/清算锚点，医疗加处方/剂量/适应症）。未覆盖字段以 `config/validation_rules.json`（校验规则单一事实源）为默认，行为不变。`scripts/verify_cases.py` 启动时先加载 validation_rules.json 再叠加 domain_config.json 覆盖。
```

需求标识来自用户输入或索引文件匹配（见第0阶段）。

> **可选通道的流向**：技术实现摘要 → 第4阶段 SDD（State/Exception/契约事实校对）+ 第8阶段测试数据 + 检查9（存储可断言，见 references/selfcheck.md）；业务规则与历史缺陷 → 第3阶段规则建模 + 第5阶段业务领域风险；历史缺陷摘要 → 第5阶段缺陷种子测试点（强制覆盖）。三者均可选，未提供时 skill 退回当前"自然语言兜底+澄清提问"行为，不阻断。 接口契约文档 -> 第4阶段接口契约模型+变更影响清单 + 统一接口测试矩阵（契约/规则/场景三类）+ 检查16/#6 反向接口追溯；启用契约驱动分支（见 references/modeling.md 接口契约模型、references/dedup_coverage.md 契约驱动分支）。

---

# 6、执行工作流（强制）

## 第0阶段：需求定位（必读，必须首先执行）

解决多需求快速定位。**必须首先读取** `references/phase0_manifest.md` 获得完整规则后执行：

1. 读取索引文件 `case-design-out/MANIFEST.md`（存在则读入全部索引表；`case-design-out/` 或索引文件不存在视为首次，按需创建目录与空索引）
2. 匹配需求标识（精确匹配/关键词匹配/无匹配=新需求）
3. 匹配成功则定位已有文件（均位于 `case-design-out/` 下）：`case-design-out/Clarification_Ledger_<需求标识>.md` / `case-design-out/TestCases_<需求标识>.md` / `case-design-out/Knowledge_<需求标识>.md`
4. 判断处理模式（新需求完整设计 / 已有需求增量 / 修改 / 复用）

**强制**：必须先读索引文件，禁止逐一扫描所有文件；匹配成功后必须立即更新索引状态=进行中；新需求在第1阶段澄清台账生成后新增索引条目（status=进行中，路径填全），第13阶段用例落盘、第14阶段审核通过后更新状态=已完成；索引更新遵循完整输出（整表 Write，按里程碑多次更新，禁止 Edit 增量）。索引文件位于 `case-design-out/MANIFEST.md`。

## 主执行流程（第1-15阶段）

必须严格顺序执行（单轮视角）：

1. Requirement Analysis + Clarification（需求分析与澄清，落盘台账，问题按角色路由 @开发/@产品/@业务，详见 `references/clarification.md`）
2. Test Requirement Analysis（测试需求分析，维度见 `references/coverage.md`）
3. Rule Modeling（规则建模，详见 `references/modeling.md`；含**第3阶段出口机器 gate**——规则来源 check_rule_source，≤2轮内存自修）
4. Specification Modeling（规格建模 SDD，State/Exception/契约标注事实来源由 @开发 校对，详见 `references/modeling.md`）
5. Risk Analysis（风险分析，三源共验产出 P0-P3：需求推导+技术隐含@开发+业务领域@业务+缺陷反哺，详见 `references/risk.md`；含**第5阶段出口机器 gate**——风险来源 risk_source_report，≤2轮内存自修；含**第5阶段 critique 循环**——P0 漏标对抗式第二视角，≤2轮 critique 自修）
6. Test Strategy Matching（测试策略匹配，决策表见 `references/methods.md`）
7. Test Point Modeling（测试点建模，维度见 `references/coverage.md`）
8. Test Case Generation（用例生成，Given/When/Then + AI友好 + 字段规范 + 断言完整性，详见 `references/modeling.md` 与 `references/quality_rules.md`；含**第8阶段出口机器 gate**——verify_cases.py run_inmemory 全量校验机器可判项，≤2轮内存自修，详见 `references/modeling.md` 15.7）
9. Duplicate Removal（去重，详见 `references/dedup_coverage.md`）
10. Coverage Validation（覆盖率校验 + 反向需求追溯 #4 + 反向行为来源追溯 #5，详见 `references/dedup_coverage.md`）
11. Pre-Output Self-Check（输出前自查，15项：含检查13 断言完整性、检查14 对抗生成遍、检查15 业务行为来源追溯，详见 `references/selfcheck.md`，**内存内零文件操作**）
12. Show Case Projection + Coverage in Chat（对话中展示用例紧凑投影+覆盖矩阵，只展示不写文件，明细见第13阶段文件）
13. Final Output（一次性 Write .md，详见 `references/output_write.md`）
14. Human Review Gate（人工审核门禁，详见 `references/review_gate.md`）
15. Excel Generation（用户确认后，详见 `references/excel.md`）

> 阶段编号以 ch23 测试执行流程 + 修改起点判定表为准（规则建模=3、风险分析=5、测试点=7、用例生成=8）。原 ch6 概览列表编号不同（规则建模=4、风险=6），系原文自身不一致；修改重走起点等功能性引用统一以 ch23 编号为准。

禁止跳步骤。禁止跨步骤执行。各阶段标注的 ref 为该阶段必须遵循的规范，**进入阶段前先读对应 ref**。
**默认按需求规模自动分级**（第0阶段判定，见 `references/dedup_coverage.md` ch26 与 `references/phase0_manifest.md`）：重型（新建 P0/核心链路）走完整 15 步；中型（已有模块新增 P1）合并建模、裁剪部分阶段；轻型（字段/文案/低风险 P2P3）跳过完整规格建模与覆盖矩阵。流程深度（执行哪些阶段）与运行模式（人工介入程度，见 6.5）是两个正交维度：用户显式声明"连跑/轻量"时同时设定运行模式与流程深度（连跑→中型、轻量→轻型）；未声明则流程深度按规模自动分级、运行模式默认完整。契约驱动分支为第三正交维度：输入含接口文档时启用（第0阶段输入形态探测，见 `references/phase0_manifest.md` 步骤六），与规模分级/运行模式可叠加；对变更接口做契约/规则/场景三类测试（见 `references/methods.md` 统一接口测试矩阵）。

---

# 6.5 运行模式与自动放行（自动化总开关）

让大模型在无需人工环节自动推进，仅在确实需要人（信息缺失/审查/许可）时停。人工只做：信息确认、审查、问题回答、必要流程许可。

| 模式 | 触发词 | 澄清门禁 | .md审核门禁 | Excel许可 | 适用 |
| -- | -- | -- | -- | -- | -- |
| 完整模式（默认） | 无 | 全部缺口停止提问 | 必须等待人工审核通过 | 必须询问确认 | 关键需求、需强人工把控 |
| 连跑模式 | "连跑"/"自动跑"/"批量" | 仅 P0/P1 阻断，其余记假设继续 | 跳过等待，标注"待人工审核"后直接推进 | 用户已声明要Excel则不再追问 | 多模块批量、信任度高 |
| 轻量模式 | "轻量"/"小改"/"低风险" | 同连跑，仅阻断P0 | 同连跑 | 同连跑 | 字段校验、文案、低风险参数 |

模式识别：用户声明任一触发词即进入运行模式；无声明时**流程深度默认按需求规模自动分级**（第0阶段判定重型/中型/轻型，见 `references/dedup_coverage.md` ch26），运行模式默认完整（人工介入程度）。可过程中切换。

**自动放行规则（仅连跑/轻量模式生效，完整模式不适用）**：
* 澄清：无缺口直接继续；仅 P2/P3 缺口记"假设"继续不阻断；P0/P1 缺口仍必须停。
* .md审核：**全部拆分文件**连续落盘 + 回读通过后标注"待人工审核"不等待反馈即推进（多文件不在文件间停顿，见 `references/output_write.md` 拆分多文件自动续跑）；交付报告须明确标注"本轮未人工审核"；用户可事后补审。
* Excel许可：用户已声明要 Excel 则不追问；未声明仍须询问。

**禁止**：以自动推进为由对 P0/P1 澄清缺口脑补/假设放行；以连跑为由删除交付报告待确认/待审核标注；完整模式下启用任何自动放行；跳过模式识别直接执行。

**合规边界**：自动放行仅放宽"等待人工"时点，**不放宽任何质量底线**（脑补禁令/杜撰禁令/断言可观测/存储合规/去重/覆盖率等全不变）。

---

# 6.6 机器门禁包装器与跳过检测（强制·跨平台）

> 把"自愿跑脚本"提升为"包装器统一触发并留痕"。门禁点不再依赖模型自觉——调用 `scripts/run_phase.py` 包装器，由它串联 verify 链、写 sentinel、读写状态机。**Windows 与 macOS 行为一致**（纯 Python，禁用 .sh/.bat/.ps1）。

## Phase 0-7 前置门禁验证（v0.6.0 新增·v0.7.0 硬化·强制）

### 问题根因
不同模型可能跳过 Phase 0-7 直接生成测试用例，导致：
- 缺少需求澄清环节
- 缺少规格建模环节
- 缺少风险分析环节
- 测试用例质量下降

### 强制验证
从 v0.6.0 起 gate8 验证 Phase 0-7；**v0.7.0 起 Phase 2-7 由"仅警告"提为"硬拒绝"**——
glm-5 等弱模型会跳过规则建模(3)/风险分析(5)/策略匹配(6)/测试点建模(7)，
软警告挡不住，故全部提为硬拒绝，gate8 要求 Phase 0-7 签名齐全才放行：

| 阶段 | 必须产出文件 | 缺失时行为 |
|-----|------------|-----------|
| Phase 0 | MANIFEST.md, REQ_*.md | 硬性拒绝，返回错误码 1 |
| Phase 1 | Clarification_Ledger_*.md | 硬性拒绝，返回错误码 1 |
| Phase 2-7 | （内存中，签空串 `""` 即可） | **v0.7.0 硬拒绝**（缺签名记 `PHASE_DEPS_MISSING`） |

> Phase 2-7 为内存阶段无文件产出，签名时传空串：
> `python scripts/run_phase.py gate-phase 3 ""`。门禁只校验"是否签过"，不校验内存内容——
> 即便如此，硬拒绝仍能把"完全跳过"逼成"至少逐阶段签一遍"，配合下方 hook 物理拦截 Write。

### 验证逻辑
```python
# gate8 执行前检查：
1. MANIFEST.md 是否存在？→ 不存在：MANIFEST_MISSING，拒绝执行
2. Clarification_Ledger_*.md 是否存在？→ 不存在：CLARIFICATION_MISSING，拒绝执行
3. Phase 2-7 签名是否完整？→ 不完整：警告，但不拒绝
```

### 错误信息示例
```
[gate8] MANIFEST_MISSING：Phase 0 未完成
[gate8] 缺少 case-design-out/MANIFEST.md
[gate8] 请先执行 Phase 0：需求定位和 MANIFEST 创建
[gate8] 参考：references/phase0_manifest.md
```

## 包装器子命令（经 Bash 调用）

| 子命令 | 阶段 | 作用 |
| -- | -- | -- |
| `run_phase.py gate8 <TC.md> [REQ.md]` | 第8出口 | 写前内存校验 + 提取 `json-gate-digest` 机器块 + REQ 落盘硬校验（缺失记 `REQ_MISSING`/`REQ_NO_HEADINGS`）+ **Phase 0-7 前置门禁验证** |
| `run_phase.py readback <TC.md> [REQ.md]` | 第13回读 | verify_md + verify_cases 文件入口串联 + 提取机器块 |
| `run_phase.py gate-phase <phase> <outputs>` | 全阶段 | **阶段门禁：顺序校验（须先签 N-1）+ 验证产出物 + 写签名 + 自动注入 preflight 摘要**（v0.6.0 / v0.7.0） |
| `run_phase.py check-new-file <文件名>` | 第13落盘后 | 核对文件名 ∈ MANIFEST，未登记记 `UNEXPECTED_NEW_FILE`（闭合"另生新文件"洞） |
| `run_phase.py state show / set <phase>` | 全阶段 | 读写 `.phase_state.json`（外置循环计数 + 幂等防覆盖，带 version/last_phase） |
| `echo '<json>' \| run_phase.py verify <TC.md> [REQ.md]` | 第14交付前 | 校验交付摘要粘贴的 digest 块哈希与重算一致（防手编假 sentinel；**经 stdin 传 JSON 避免中文 argv 乱码**） |
| `run_phase.py summary` | 第14交付前 | 打印 `.gate_log` 全部 sentinel，核对 gate8/readback 齐全且 exit=0 |

## sentinel 与交付摘要联动

* 每次门禁运行向 `case-design-out/.gate_log` 追加一行 sentinel：`script|phase|exit|digest_hash|note|state_version`，`digest_hash` 为脚本 stdout 前 200 字符的短哈希（防伪造）。
* `verify_cases.py` 在 stdout 末尾输出 ```json-gate-digest``` 机器块（含 5 项机器数值 + `hash`，`hash` 覆盖 file/n/exit/hard/summary）。**交付摘要 5 项数值须从该块原样粘贴**（禁止手填），`run_phase.py verify` 重算比对哈希防篡改。
* `.gate_log` 与 `.phase_state.json` 交叉引用（每条 sentinel 记 `state_version`），一处漏写另一处能发现。
* **跳过检测**：交付前 `run_phase.py summary` 核对 gate8（第8出口）+ readback（第13回读）各至少 1 条且 exit=0；REQ 无 `REQ_MISSING`/`REQ_NO_HEADINGS`；check-new-file 无 `UNEXPECTED_NEW_FILE`。**缺任一项即门禁未走完，禁止声明已审核通过**。

## 阶段签名机制（v0.6.0 新增）

### 目的
记录每个阶段的完成状态，防止跨阶段跳过。

### 使用方式
```bash
# Phase 0 完成后
python scripts/run_phase.py gate-phase 0 "MANIFEST.md,REQ_001.md"

# Phase 1 完成后
python scripts/run_phase.py gate-phase 1 "Clarification_Ledger_001.md"

# Phase 2-7（可选，不强制文件产出）
python scripts/run_phase.py gate-phase 2 ""
python scripts/run_phase.py gate-phase 3 ""
# ...
```

### 签名文件：`.phase_signatures.json`
```json
{
  "phases": {
    "0": {
      "completed": true,
      "timestamp": "2026-07-29T13:00:00",
      "outputs": ["MANIFEST.md", "REQ_001.md"],
      "signature": "abc123..."
    },
    "1": {
      "completed": true,
      "timestamp": "2026-07-29T13:05:00",
      "outputs": ["Clarification_Ledger_001.md"],
      "signature": "def456..."
    }
  }
}
```

### 签名内容
- **时间戳**：阶段完成时间
- **产出文件**：该阶段产出的文件列表
- **文件哈希**：产出文件的 SHA256 哈希（防篡改）

### 验证方式
- gate8 会验证 Phase 0-1 的签名（可选）
- 缺少签名会给出警告，但不拒绝执行

## preflight 摘要注入（降认知负载）

* 进入第 N 阶段前运行 `python scripts/preflight.py --phase <N>` 打印对应 ref 的 40 行大纲摘要（标题级 + 关键约束行），即使模型不主动读 ref，摘要也进上下文。
* **v0.7.0：`run_phase.py gate-phase N` 内嵌自动注入**——跑门禁即随 stdout 注入本阶段大纲，无需额外记忆"先跑 preflight"；弱模型只要肯跑门禁，摘要就进上下文。
* 摘要硬上限 40 行/阶段、仅注入一次；超长需求（用例数 >60）加 `--big` 降级为计数 + 指引（防反噬）。
* `python scripts/preflight.py --list` 列出全部阶段-ref 映射。

## PreToolUse hook 硬拦截 Write（v0.7.0 新增·v0.7.2 升级为内容特征检测·harness 强制合规）

> **把"模型自觉合规"升级为"harness 物理强制"**——这是唯一与模型能力无关、能真正挡住弱模型跳步的机制。
> 配置见 `.claude/settings.json` 的 `hooks.PreToolUse`，脚本为 `.claude/hooks/case_design_gate.py`。

### v0.7.2 内容特征检测

v0.7.1 只拦截 `case-design-out/` 目录，弱模型会把测试用例写到其他位置绕过门禁。本版升级为**内容特征检测**：

**双重检测**：

**A. case-design-out/ 目录下的 Write**：按文件类型分档门禁

| 文件类型 | 门禁要求 |
|---|---|
| MANIFEST.md / REQ_*.md | 允许写入，提示运行 gate-phase 0 |
| Clarification_Ledger_*.md | 需要 Phase 0 已签名 |
| TestCases_*.md|xlsx | 需要 gate8 + Phase 0-7 全签 |
| Knowledge_*.md | 需要 Phase 0-7 全签 |
| 其他 case-design-out/ 文件 | 需要 Phase 0 签名 |

**B. 非 case-design-out/ 目录的 Write**：内容特征检测

检测是否包含测试用例特征：
- 文件名含"测试用例"/"TestCases"
- 内容含"# 测试用例"/"测试用例ID"/"用例等级"等关键词

如果检测到测试用例内容，`exit 2` 拦截并提示：
1. 按 skill 流程执行 Phase 0-7
2. 逐阶段签名 + gate8
3. 写到 case-design-out/TestCases_*.md

### 效果

模型无论如何输出测试用例：
- 写到 case-design-out/TestCases_*？→ 需要门禁
- 写到 测试用例/ 目录？→ 内容检测拦截
- 写到项目根目录？→ 内容检测拦截
- 在对话中展示不 Write？→ 无法拦截，但无法产出文件

**每一条产出路径都被门禁卡住**。

---

# 19、输出协议（强制）

## 默认模式

禁止输出推理/分析/建模/风险分析/覆盖率分析过程。仅输出最终结果。

> 第12阶段展示的"用例紧凑投影 + 覆盖矩阵"属最终结果展示（条数与覆盖广度的结果摘要），不属此处禁止的"分析过程"（分析过程指推导建模/风险/覆盖率的推理步骤，仅在调试模式输出）。

## 调试模式

用户输入"调试模式"或"展示分析过程"，则允许输出规格建模摘要、风险分析摘要、测试覆盖摘要，之后再输出用例。

## 完整输出原则（强制）

每轮用例的生成与修改必须在本轮全部内容完成并通过自查后**一次性写入文件**。禁止生成一点、输出一点。详细写入机制（内存内完成、单次 Write、落盘后回读核对、写前规模评估、修改流程起点判定、写入工具白名单）见 `references/output_write.md`。

**核心要点速记**：
* 本轮全部用例先在上下文（内存）完整生成 + **第8阶段出口机器 gate**（`verify_cases.py run_inmemory` 全量校验机器可判项，≤2轮内存自修，独立计数）+ 完成第22章全部自查（15项，含检查13 断言完整性、检查14 对抗生成遍【内部另含≤2轮 critique 子循环，独立计数，补出新用例须回跑第8 gate】、检查15 业务行为来源追溯）+ 自修循环（最多3轮，全部内存内），自查自修是内存操作不是文件编辑；第8 gate 与第11自查检查项不相交、计数独立、不嵌套；另第5阶段 critique 循环（≤2轮）亦独立计数
* 落盘 = 每个文件恰好一次 Write（整体创建/覆盖），禁止 Edit/MultiEdit/append 落盘或补齐
* **输出 token 预算（硬约束）**：**默认单文件** `case-design-out/TestCases_<需求标识>.md`（追溯性 section 全需求一份）；单次 Write `content` 预估 > 24000 token 先压缩，压缩后仍超才拆最小 PART `case-design-out/TestCases_<需求标识>_PARTn.md`（按风险排序、不按模块拆）；每个文件各自一次 Write + 回读，**一文件回读通过后自动续跑下一文件（不停顿等用户），全部文件落盘后统一进入第14阶段审核**（详见 `references/output_write.md` 拆分多文件自动续跑）
* 落盘后立即只读回读核对（行数/表头15列/末行/内容枚举+覆盖统计与追溯）；**回读用 `scripts/verify_md.py` + `scripts/verify_cases.py` 串联返回摘要，禁止 Read 整份 .md 进上下文**（见 scripts 说明）
* 单文件场景写文件调用 ≤ 2 次（Write 计数，回读不计）；多文件拆分按文件计，各文件独立 1 次 Write + 回读
* 修改场景：内存改好整份内容后一次 Write 覆盖，禁止逐条 Edit

## 输出顺序（每轮）

1. 输出【待确认问题与假设清单】（有问题/假设则停或登记，等用户回复；问题与假设统一展示、按角色路由标注 @开发/@产品/@业务）
2. 输出【测试需求分析结果】（仅调试模式可见）
3. 输出【测试点清单】（仅调试模式可见）
4. 对话中展示用例紧凑投影+覆盖矩阵（只展示，不写文件，禁止此时发文件写入调用；明细15列见第6步文件）
5. 内存内自查自修（15项，含检查13 断言完整性、检查14 对抗生成遍、检查15 业务行为来源追溯，零文件操作）+ 写前规模评估（输出 token 预算，决定单文件/PART拆/展示与写入是否分响应）
   > **第8阶段出口机器 gate 已先跑**（`references/modeling.md` 15.7）：进本第5步前，第8阶段出口 gate 已用 `verify_cases.py run_inmemory` 在内存内全量校验机器可判项并自修（≤2轮，独立计数）。本第5步 LLM 自查只管机器判不了的项（5/10/11/14 + 阻断决策），对 4/6/7/13/15 客观面降为"确认已过"，≤3轮自修与第8 gate ≤2轮各自独立不嵌套
6. 单次 Write 写入 .md + 脚本回读核对（verify_md.py 结构 + verify_cases.py 内容/覆盖）；**默认单文件单次 Write**（写入 `case-design-out/TestCases_<需求标识>.md`）；仅压缩后仍超预算才拆最小 PART，逐 PART Write+回读、**一 PART 完成自动续跑下一 PART、中途不等用户，全部 PART 落盘 + 回读通过后统一进入第14阶段审核**（详见 `references/output_write.md` 拆分多文件自动续跑）

> 第4步(展示)与第6步(写入)分离：展示不是写文件，写文件是展示之后一个独立、单次的工具调用。此处"分离"指**动作先后**（先展示、后一次性 Write），**不是指拆成两个响应**；禁止把"展示"与"分条增量写入"交织（即禁止边展示边逐条 Write），**非禁止二者在同一响应**。
> **默认同响应连续完成（强制·防"展示完宣布'下一步将 Write'就停"）**：第5步规模评估结论为"单文件单次 Write"（合并体 ≤ 24000 token、未触发拆分）时，第4步展示 + 第5步自查评估 + 第6步 Write + 回读须在**同一响应内连续完成**--评估完**立即发起 Write 调用**，不得以"下一步将 Write…"收尾停顿、不得结束本轮等待用户。展示->Write 之间无人工节点（人工审核门禁在第14阶段，于 Write+回读之后，全模式含完整模式均如此）。
> **仅当** N 较大或单响应预估超输出 token 预算时，才把第4步与第6步**拆到不同响应**（先一响应只投影+覆盖矩阵，下一响应再发 Write）；即便拆分，下一响应也由模型**自动衔接发 Write**（无需用户发"继续"），投影可降级为计数+覆盖矩阵，避免单响应突破 32000 输出上限。

## 最终测试用例格式（15列，与 Excel 完全一致）

| 用例ID | 关联需求ID | 关联规则 | 测试类型 | 测试维度 | 所属模块 | 用例名称 | Given | When | Then | 编辑模式 | 标签 | 责任人 | 用例等级 | 用例状态 |
| -- | -- | -- | -- | -- | -- | -- | ----- | ---- | ---- | ---- | ---- | ---- | ---- | ---- |

* 用例ID：`TestCases_<需求标识>_<功能缩写>_<序号>`，全局唯一、连续不跳号
* 关联需求ID：有编号直接填；无则填"见需求文档<章节>"，禁止杜撰
* 关联规则：核心业务规则短句，禁止杜撰/留空
* 用例名称：【模块】【功能】【场景】【预期】四段齐全，简明扼要，禁止冗长复述 G/W/T
* 固定值列（.md 与 .xlsx 均须填，取值固定不变禁止改动留空）：编辑模式=STEP、标签=AI、责任人=AI、用例状态=Completed
* 用例等级：P0-P3，取自第5阶段风险分析，位于用例状态之前
* 测试类型/测试维度/用例等级取值枚举见 `references/modeling.md` 字段规范

## 输出原则

仅允许输出：待确认问题、测试用例。禁止输出无关解释内容。

---

# 25、输出与审核流程总览

## 四条强制约束

1. **完整输出**：每轮一次性写入，禁止生成一点输出一点
2. **人工审核门禁**：.md 生成后必须提示审核；完整模式须等待"无问题/审核通过"才进 Excel，连跑/轻量可标注待审核后推进
3. **Excel-only 直通**：仅要 Excel 且 .md 已存在时跳过完整设计流程直接转换（须先过源 .md 一致性校验）
4. **Excel 脚本化生成**：Excel 须经 openpyxl 脚本产出 + 结构验证 + 数据完整性校验（见 `references/excel.md`）

## 轮次优先级（仅 PART 溢出拆分时·决定落盘顺序）

> 默认单文件无需排序。仅当合并体压缩后仍超预算、拆成最小 PART 时，本节适用。

模块风险等级由第5阶段产出。PART 拆分时按风险优先级决定**落盘顺序**（高风险 PART 先落盘），但**不在文件之间停顿审核**——全部 PART 连续生成 + 落盘 + 回读通过后，**统一进入第14阶段人工审核门禁**（一次审核覆盖全部 PART，见 §19 与 `references/output_write.md` 拆分多文件自动续跑）。

| 优先级 | 模块类型 | 落盘顺序 |
| -- | -- | -- |
| 1（最先） | P0 风险模块（支付/资金/权限/状态流转/数据一致性） | 最先落盘 |
| 2 | P1 风险模块（并发/幂等/缓存一致性/接口契约） | 次之 |
| 3 | P2/P3 模块 | 最后落盘 |

> 先落盘高风险 PART 的意义：若输出 token 预算或会话中断致后续 PART 未落盘，最高价值部分已先落盘；人工审核统一在全部 PART 完成后进行，**不再逐文件早审、不在文件间暂停等用户**。P0 风险仍在统一审核门禁中覆盖（完整模式须等审核通过才进 Excel；连跑/轻量标注待审核后推进）。

## 交付摘要（每轮完成后输出）

```
【交付摘要】
轮次：<需求标识>
运行模式：完整/连跑/轻量
用例数：N 条（P0:x P1:y P2:z P3:w）
覆盖矩阵：已覆盖需求 a 条 / 规则 b 条；未覆盖/待确认 c 条
脚本校验摘要（取自 verify_cases.py 回读输出，逐项填实际数值，禁止只填"通过"）：
  检查13 断言完整性：疑似 <n> 条（状态变更类缺副作用）
  检查9增强 存储schema交叉：跳过/疑似 <n> 条（断言存储名不在技术实现摘要清单）
  风险来源待确认：<n> 条 P0/P1（技术隐含@开发/业务领域@业务/缺陷反哺 未在台账确认）
  #4 反向需求追溯：未校验(REQ缺失/不可解析,待消除)/需求条目 <m> 条、未引用 <k> 条/全部覆盖
  检查15 业务行为来源追溯(#5)：疑似 <n> 条（无来源业务行为/无来源标记规则项）
假设登记：共 k 条假设（连跑/轻量模式），已回显进【待确认问题与假设清单】（状态=假设）
审核状态：已人工审核通过 / 待人工审核
输出文件：case-design-out/TestCases_<需求标识>.md [+ case-design-out/TestCases_<需求标识>.xlsx]（拆 PART 时为 case-design-out/TestCases_<需求标识>_PARTn.md 多文件）
知识总结：未生成 / 已生成(case-design-out/Knowledge_<需求标识>.md) / 已更新 / 审核未通过暂不生成
Excel 状态：未生成 / 已生成(经21.7脚本产出+结构验证+数据完整性校验全过) / 生成失败
Excel 数据校验：未执行 / 七项全过 / 不通过(问题项及条数)
临时文件清理：已清理(清单) / 无临时文件产生 / 清理失败(残留清单)
待确认问题：Q列表中未关闭 m 条（P0/P1 阻断项）
门禁 sentinel（取自 case-design-out/.gate_log，经 `run_phase.py summary` 输出）：
  第8出口 gate8：已过 exit=0 / 缺失(REQ_MISSING/REQ_NO_HEADINGS) / 未跑
  第13回读 readback：verify_md exit=? verify_cases exit=? / 未跑
  check-new-file：全部 ∈ MANIFEST / 有 UNEXPECTED_NEW_FILE:<文件名>
  digest 块校验：粘贴块哈希与重算一致 / 不一致(疑似手编)
下一步建议：<提示人工动作：审核/回答问题/许可生成Excel/安装openpyxl>
```

要求：连跑跳过等待仍须输出摘要；P0/P1 阻断项须显式列出；Excel/知识总结/清理须如实填写，未通过不得声明已生成。**脚本校验摘要**五项数值须从 `verify_cases.py` 末尾输出的 ```json-gate-digest``` 机器块**原样粘贴**（含 hash），或经 `run_phase.py gate8/readback` 输出的机器块粘贴——禁止凭印象手填；`run_phase.py verify` 会重算哈希防篡改。**#4 反向需求追溯行**：REQ 已落盘且可解析时填"需求条目 N 条、未引用 K 条/全部覆盖"；REQ 缺失或不可解析时填"未校验(REQ缺失/不可解析,待消除)"——此为显式强提示（`references/dedup_coverage.md` #4 显式强提示节），完整模式须消除（补落盘 REQ/补 ## 标题后重跑）才进第14阶段，**禁止填"跳过"隐瞒**；其余跳过项（如检查9增强未提供技术实现摘要）填"跳过"并注明原因。**拆 PART 自动续跑时**：中间 PART 落盘后交付摘要"下一步建议"填"自动续跑下一 PART"，仅末 PART 填"统一审核全部文件"；审核状态以全部 PART 聚合填写。

---

# 承重规则速记（常驻·不读 ref 也会错）

> 下列规则是"即使不读 references 也会用错"的承重项，故内联常驻核心，与 `config/validation_rules.json`（单一事实源）一致；散文与 JSON 冲突时以 JSON 为准（见校验规则契约节）。

* **15 列表头顺序（硬）**：用例ID | 关联需求ID | 关联规则 | 测试类型 | 测试维度 | 所属模块 | 用例名称 | Given | When | Then | 编辑模式 | 标签 | 责任人 | 用例等级 | 用例状态（**15 列**，非 16；列数不足/错位 → verify_cases.py exit=1）。
* **固定值列（硬）**：编辑模式=STEP、标签=AI、责任人=AI、用例状态=Completed（取值固定，禁改值留空）。
* **测试类型枚举（12 值，硬）**：兼容性 / 功能 / 可靠性 / 契约 / 安全 / 幂等 / 并发 / 异常 / 权限 / 状态迁移 / 边界 / 集成。
* **测试维度枚举（13 值，硬，含 `界面验证`）**：兼容性验证 / 安全验证 / 幂等验证 / 并发验证 / 接口验证 / 数据验证 / 权限验证 / 状态验证 / 输入验证 / 边界验证 / 集成验证 / 风险验证 / **界面验证**（v0.5.0 加，散文 modeling.md §20.11 旧写 12 值系漂移，**以 13 值为准**）。
* **用例等级（硬）**：P0 / P1 / P2 / P3（取自第5阶段风险分析）。
* **5 个有界循环计数（独立·不嵌套）**：第5机器gate ≤2、第5 critique ≤2、第8机器gate ≤2、第8 critique ≤2、第11自查 ≤3。critique 补出的新用例须重跑第8 gate（计入第8 gate ≤2 上限）。计数可外置到 `case-design-out/.phase_state.json`（经 `run_phase.py state` 读写），不必脑记。
* **优先级规则**：`config/validation_rules.json`（机器判定）> `references/*.md` 散文 > 范例。

# 临时文件清理（全局·强制·概要）

执行中产生的临时脚本/中间产物（CSV/JSON/txt/片段/日志，**均为中间产物非交付格式**）须在不再使用时立即删除（置于 `case-design-out/` 下）。**例外**：`scripts/` 下的 `verify_md.py`、`verify_cases.py`、`verify_knowledge.py`、`project_cases.py`、`gen_excel.py`、`index_req.py`、`preflight.py`、`run_phase.py` 为 skill 自带可复用资产，**不删除**；仅 ad-hoc 一次性脚本用完即删。正式产出物（`case-design-out/` 下的 `TestCases_*.md/.xlsx`、台账、knowledge、原始需求）禁止删除；`.gate_log`/`.phase_state.json`/`*.index.json` 为门禁状态文件，跨轮保留至该需求完成后清理。完整规则见 `references/output_write.md` 临时文件清理节。

---

# 校验规则契约（单一事实源·降本）

`config/validation_rules.json` 为校验规则的**单一事实源**：15 列表头、测试类型/维度/等级枚举、固定值列、断言可观测正则、模糊词、存储合规模式、关键词维度、状态机流转锚点、边界深度词、异常子类、过度设计业务锚点、追溯性 section 格式——全部集中于此。`scripts/verify_cases.py` 与 `scripts/verify_md.py` 启动时共同加载该清单，`config/domain_config.json` 在此基础上按领域覆盖（同名字段替换）。该文件为 skill 永久资产，不删除。

**agent 需要规则契约时**：运行 `python scripts/verify_cases.py --dump-rules`（经 Bash），即可拿到上述全部校验口径的紧凑投影（约 60 行），**无需读 `verify_cases.py` 源码**。设计用例前读这一份契约即可一次过校验，避免因漏读校验口径（枚举越界 / 断言无可观测锚点 / 存储杜撰 / section 格式不符）导致整文件重写。`references/*.md` 的散文规则与本清单冲突时，以本清单（机器判定）为准。

---

# 减少编辑审批弹窗（权限配置建议·用户侧）

默认权限模式下，每个 Write/Bash 调用都会弹一次审批；文件数越多弹窗越多。**单文件默认已将用例 Write 与校验 Bash 调用数压到最低**（用例 Write 1 次、校验 Bash 2 次）。要进一步**归零弹窗**，由用户配置权限（skill 无法单方面关闭审批）：

* **方案一（最省心）**：会话启用 `acceptEdits` 权限模式 → 所有文件编辑自动通过、0 弹窗。适合批量/连跑场景。
* **方案二（最小授权）**：在 `.claude/settings.json` 的 `permissions.allow` 允许列表加入 skill 产出的 glob，仅这些操作免审批、其余仍受控。示例（路径按实际工作目录调整；产出物统一写入 `case-design-out/` 子目录）：
  ```json
  {
    "permissions": {
      "allow": [
        "Write(case-design-out/TestCases_*.md)",
        "Edit(case-design-out/TestCases_*.md)",
        "Write(case-design-out/MANIFEST.md)",
        "Edit(case-design-out/MANIFEST.md)",
        "Write(case-design-out/Clarification_Ledger_*.md)",
        "Edit(case-design-out/Clarification_Ledger_*.md)",
        "Write(case-design-out/Knowledge_*.md)",
        "Edit(case-design-out/Knowledge_*.md)",
        "Write(case-design-out/REQ_*.md)",
        "Write(case-design-out/TestCases_*.xlsx)",
        "Bash(python *verify_md.py:*)",
        "Bash(python *verify_cases.py:*)",
        "Bash(python *verify_knowledge.py:*)",
        "Bash(python *project_cases.py:*)",
        "Bash(python *verify_cases.py --dump-rules)",
        "Bash(python *run_phase.py:*)",
        "Bash(python *index_req.py:*)",
        "Bash(python *preflight.py:*)"
      ]
    }
  }
  ```
  （`acceptEdits` 与允许列表二选一；语法/路径按你的 Claude Code 版本与工作目录调整。命令均为平台无关的 `python scripts/<x>.py ...`，Win/Mac 通用。）

> 说明：skill 侧已通过"单文件默认 + 一文件一次 Write + 小体积 Write 合并同响应"将调用数压到最低；权限配置是把这些调用从"每次审批"变为"免审批"的最后一跃，属用户权限边界，须用户自行设定。

---

# 抬高单 Write 天花板（可选·用户侧）

重型/超大需求（>60 条）即便压缩也可能逼近 24000 token。用户可设环境变量 `CLAUDE_CODE_MAX_OUTPUT_TOKENS=48000`（或更高）抬高单次 Write 上限，让更大需求也能单文件一次写入。skill 不依赖该设置（仍以 24000 阈值/压缩/PART 兜底），但重型批量场景推荐启用。

---

# 参考文件索引（按阶段按需读取）

> 进入对应阶段前读取相应 ref（亦可先跑 `python scripts/preflight.py --phase <N>` 注入 40 行大纲摘要）。ref 内容为本 skill 细则，与单文件版规则一致。**承重规则已内联本 SKILL.md「承重规则速记」节，不必为取枚举而读 ref**；ref 提供细则与决策表。

| 阶段/场景 | 读取参考文件 | 内容 |
| -- | -- | -- |
| 第0阶段 | `references/phase0_manifest.md` | 需求定位、MANIFEST 索引管理、需求规模分级判定（原 ch6+ch32） |
| 第1阶段 | `references/clarification.md` | 澄清机制、澄清台账、防重复提问（原 ch7） |
| 第2/7阶段 | `references/coverage.md` | 测试覆盖矩阵、需求/测试点维度（原 ch8+15.2/15.3） |
| 第3-4阶段 | `references/modeling.md` | SDD 规格建模、TDD、Given/When/Then、建模维度、字段规范枚举（原 ch9/10/13/15.4/15.5/20） |
| 第5阶段 | `references/risk.md` | 风险优先级 P0-P3（原 ch14） |
| 第6阶段 | `references/methods.md` | 方法动态匹配决策表、方法→列映射、风险驱动深度、多方法组合、错误推测清单、组合爆炸控制（原 ch15.1） |
| 第8阶段生成 | `references/quality_rules.md` | 避坑完整版、AI友好/断言/数据规范、存储保护（原 ch0+11+12） |
| 第9-10阶段 | `references/dedup_coverage.md` | 去重、覆盖率控制、停止条件、需求规模分级、#4 反向需求追溯 + #5 反向行为来源追溯（原 ch16/17/18/26） |
| 第11阶段 | `references/selfcheck.md` | 15项自查（含检查13 断言完整性、检查14 对抗生成遍、检查15 业务行为来源追溯）、自修vs阻断决策、门禁失败处理（原 ch22） |
| 第12-13阶段/修改 | `references/output_write.md` | 完整输出写入机制、修改流程起点判定、临时文件清理（原 ch19+ch30） |
| 第14阶段 | `references/review_gate.md` | 人工审核门禁、质量门禁 checkbox（原 ch21.5+ch24） |
| Excel 生成 | `references/excel.md` | Excel 输出协议、脚本生成机制、校验（原 ch21） |
| 安全/性能场景 | `references/safety_perf.md` | 安全测试维度、性能/兼容/本地化（原 ch27+ch29） |
| 知识总结 | `references/knowledge.md` | 知识总结 13 维度、生成机制（原 ch31） |
| 格式范例 | `references/example.md` | 端到端 worked example（原 ch28，仅不确定格式时读） |
| 超长需求文档 | `scripts/index_req.py` + `scripts/run_phase.py` | 落盘 REQ 后生成章节索引（按需读章节）、分批落盘（token >24000 拆 `_secN.md`）、门禁包装器 |
| 阶段进入摘要 | `scripts/preflight.py` | `--phase <N>` 注入 40 行 ref 大纲（降认知负载，`--big` 超长需求降级） |

---

# 结束语

Specification First → Test First → Risk First → Coverage First → Automation First → AI Friendly First → Complete Output First（禁止增量写入）→ Human Review First（人工只在确认/审查/回答/许可介入；门禁可按模式自动放行但保留审计痕迹）→ Reuse First（Excel-only 优先复用已有 .md，须先过一致性校验；知识总结复用已审核用例+台账+需求文档）→ Traceability First。

> 各类禁止性规则已分布于对应 references 的"禁止/强制"节，此处不重复罗列；执行时以各阶段 ref 为唯一细则来源。核心红线（违反任一即判定输出不合格，见 3.1）：不脑补需求/业务行为/表名/字段/缓存Key、不生成伪测试/重复测试、不输出模糊断言、不跳过澄清、不重复询问台账已解决项、不增量写入文件、不跳过人工审核门禁、不遗留临时文件。

优先高风险、高价值、可自动化、可回归、AI 可解析、完整输出、审核门禁、复用已有资产、可追溯、自动推进、脚本化生成 Excel 并验证落盘、`case-design-out/` 产出目录整洁、审核通过后自动沉淀知识总结、索引文件快速定位、按需求规模自动分级。