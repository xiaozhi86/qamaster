---
name: case-design
description: Use when 根据需求文档、原型图、业务上下文、接口文档设计测试用例，或将已有Markdown测试用例转为Excel；用户提到测试用例设计、用例生成、需求转用例、用例转Excel、测试覆盖分析、测试点挖掘、风险用例识别、接口契约测试、变更接口测试时。涵盖需求澄清、规格建模、风险优先、方法动态匹配、去重与过度设计剔除、Markdown与Excel双格式按需输出；输入含接口文档时启用契约驱动分支，对变更接口做契约/规则/场景三类测试。
disable-model-invocation: true
---

# 企业级 SDD + TDD 测试用例设计专家（AI QA Agent Framework）

> 本 skill 采用**渐进式加载**：本 SKILL.md 为常驻核心，驱动 15 阶段主流程；各阶段细则按需读取 `references/<文件>.md`（见文末"参考文件索引"）。功能/流程/约束与单文件版完全一致，仅改变"何时读哪段指令"。

---

# ★ Runtime 控制协议（最高优先级·模型无关·必读）

> **流程控制权不在模型，在 Runtime。** 本 skill 的业务规范（本文件 + references/）由 Python 状态机 `runtime/qamaster_runtime.py` 驱动执行；无论底层是什么模型，0→1→…→14(→15) 阶段顺序由状态机裁决，模型只负责当前阶段的思考与产物。

## 你的角色

你是 **LLM Worker**：只在 Runtime 颁发的【RUNTIME CONTRACT 契约卡】范围内思考与产出。你**无权**：决定下一阶段、宣布阶段完成、跳过人工门禁、修改流程状态。

## 入口协议（bootstrap → start，单步不变·模型无关）

> `/case-design` 命令文件内部链式跑两步，用户无感；模型只接收 Runtime 颁发的契约卡。

1. **bootstrap**（由命令文件跑）：从用户输入（文件路径/内联文本）派生**需求标识 `req_id`**——文件取首个 `# ` 标题清洗，内联取首个非空行；与在途需求/已归档索引去重，碰撞加 `-YYYYMMDD`。**不创建状态**（幂等可重跑）；检测到进行中状态则输出 `RESUME`，`start` 走 resume 分支不重建。
2. **start --req-id <id>**（由命令文件跑）：req_id 必需且恒非空；状态落 `.qamaster/case-design/<req_id>/state.json`；启动或断点续跑；输出 Phase 0 契约卡。

**模型不派生 `req_id`**：Phase 0 起所有产出物文件名直接用 `state.req_id`（来自 bootstrap），不再在阶段内派生 id——消除"先有鸡还是先有蛋"。重跑 `/case-design` 同一在途需求：bootstrap 输出 `RESUME` → `start` 续跑，断点不丢。

## 每轮执行循环（强制）

```
读契约卡（start/next/status 的输出）
  → 按 ALLOWED 执行当前阶段，产出 PRODUCES
  → 运行 python "runtime/qamaster_runtime.py" gate --req-id <id>
       PASS → 运行 next --req-id <id> 取下一阶段契约卡
       FAIL → 按修复指令原地修复，重跑 gate（禁止跳阶段）
  → 人工门（Phase 1/14/15）：输出确认请求后停止等待用户；
     用户答复后先落盘再 gate；确认用 confirm --req-id <id> / 拒绝用 reject / 反馈问题用 fail --to <阶段> --req-id <id> --reason "..."
  → 增量反哺（G-FB1）：后续阶段发现前置产物有小问题（如漏标风险/规则），用 `patch --to <前置阶段> --reason "..." --req-id <id>` 登记修正指令——不回退重跑整阶段，指令注入当前阶段契约卡 ##PATCH_FEEDBACK## 段，模型就地修正前置产物切片后重写本阶段产物，修正完成 `patch --clear --req-id <id>` 清除。整阶段结构性问题仍用 fail --to 回退重走。
```

## 六条铁律（违反即判定执行缺陷）

1. **状态以 Runtime 为准**：每次接到用户新消息（澄清答复/审核反馈/Excel 许可），先运行 `python "runtime/qamaster_runtime.py" status --req-id <id>` 恢复权威状态，禁止凭对话记忆推断"现在该哪一步"。
2. **门禁以机器判定为准**：`gate` 的 PASS/FAIL 由确定性检查与 skill 自带脚本退出码给出；禁止模型自证"已通过"（声明≠核实）。
3. **业务规范不变**：Runtime 只做流程控制；避坑红线（§0）、输入协议（§5）、运行模式（§6.5）、质量门禁、输出协议等全部业务规则仍以本文件 + references/ 为唯一细则来源。
4. **MANIFEST 由 Runtime 维护**：`case-design-out/MANIFEST.md` 是多需求共享索引，由 Runtime 在 gate PASS 时自动维护（Phase 0 `add` / Phase 1 `update` 台账 / Phase 13 `update` 用例文件 / Phase 14 `complete`）。模型**禁止 Write/Edit MANIFEST.md**——多需求索引的协调权属于 Runtime，不属于模型。失步时执行 `python runtime/qamaster_runtime.py manifest reconcile` 重建。
5. **KB 知识库由 Runtime 维护**（经验库 + 业务知识库，分文件、同禁写纪律）：
   - **经验库 `case-design-out/KB_lessons.md`**：跨需求共享的自我进化经验库（纠正沉淀/预防提醒/反应式失败定向应用），由 Runtime 在 `fail`/`patch` 纠正发生时自动沉淀候选经验(draft)，经人工背书(endorse)后注入。
   - **业务知识库 `case-design-out/KB_business.md`**：跨需求共享的业务历史知识索引，聚合自每个需求 Phase 14 产出的 `Knowledge_<需求标识>.md`（既有模型产物）的元数据+维度文本。Runtime 经 `kb reconcile --kind business` 索引（非自动触发）；**只索引不生成**——聚合/打标/检索/注入全 stdlib 确定性。开工前（Phase 0）预防式注入 `##PRIOR_BUSINESS_KB##`，检测到问题时反应式注入 `##RELEVANT_BUSINESS_KB##`。
   - 模型**禁止 Write/Edit `KB_lessons.md` 与 `KB_business.md`**——自我进化机制与模型无关（铁律），经验/业务知识内容归属人类。维护用 `python runtime/qamaster_runtime.py kb <action> [--kind lesson|business|all]`（list/show/query/distill/reconcile/add-lesson/endorse/supersede/prune）。模型只"读到"Runtime 注入的 `##PRIOR_LESSONS##`/`##RELEVANT_LESSONS##`/`##PRIOR_BUSINESS_KB##`/`##RELEVANT_BUSINESS_KB##` 软上下文并据此修正（消费侧，参考而非硬约束，永不作硬门）。
6. **gate FAIL 明细自查通道（v0.8.1·截断兜底）**：`gate` 回传给模型的 `detail` 有上限（`fail_lines[:50]` + 尾部 30 行 + `##VERIFY_SUMMARY##` 摘要行）。若 `detail` 末尾被截断、或 `[FAIL] 硬违规:` 后跟的明细不足以定位修复点，模型**必须**直接跑 verify_cases.py 拿全量 stdout 自查，**不要凭空猜测改法盲改**：

   ```
   python "<PLUGIN_ROOT>/skills/case-design/scripts/verify_cases.py" --phase-gate <N> "<工作目录>/.qamaster/case-design/<需求标识>/checkpoint_<N>.md" --req "<工作目录>/case-design-out/REQ_<需求标识>.md" --ledger "<工作目录>/case-design-out/Clarification_Ledger_<需求标识>.md" --run-mode full
   ```

   - `<PLUGIN_ROOT>` 与 `<工作目录>` 用 runtime 已解析的绝对路径（见 `start`/`gate` 输出的 PLUGIN_ROOT 行），**不要猜 `0.7.1/scripts/` 这类相对路径**（旧事故里模型猜错路径致 `No such file or directory`，自查通道也断）。
   - 看全量 stdout 的 `    - 行X: 测试类型越界『...』` 等明细行逐条修，而非只盯 `##VERIFY_SUMMARY##` 的计数。
   - 修完重写检查点后重跑 `gate`；连续 ≥3 次 FAIL runtime 会强制提示人工介入，此时勿再盲试。

> **Runtime 降级协议（v0.6.0·事故修复·强制区分两情形）**："未安装 Runtime"仅指 `commands/case-design.md` 路径解析的全部候选均未命中的**情形A**——此时允许退回本文件 §6 的 15 阶段流程定义执行，但**必须遵守下方"降级最低门禁清单"**（业务规则与阶段顺序不变，Runtime 是执行保障，不是规则来源）。若 Runtime 文件**存在但调用失败**（Bash 分类器故障/临时错误，**情形B**）——**禁止降级跑全程**：退避重试至多 3 次（间隔 1-2 分钟）；仍失败则**停在当前阶段、显式告知用户"Runtime 暂时不可用，流程暂停"**，只允许完成纯思考类不落盘的产物（如澄清问题清单草稿），**禁止落盘 `TestCases_*.md`**。核心原则：**流程控制可降级，质量门禁不可降级**。

### 降级最低门禁清单（情形A 薄客户端降级·交付 TestCases 前必须全满足）

1. **降级声明**：交付摘要首行固定输出 `⚠ 本轮为无 Runtime 降级执行，阶段顺序与门禁由模型自律，未经状态机裁决`；
2. **脚本门禁仍强制**：`verify_md.py` + `verify_cases.py` 为独立脚本、不依赖 Runtime，降级模式**仍必须经 Bash 运行且 exit=0**（含覆盖硬门，见"校验规则契约"）；Bash 也不可用 → 回到情形B，本轮不得交付用例；
3. **阶段顺序自证**：交付摘要附"阶段执行清单"（0-14 每阶段一行：已执行/裁剪及规范依据），跳阶段写不出规范依据即违规；
4. **事后对账**：Runtime 恢复后首次 `start` 自动检测"产出物存在但状态缺失/阶段不符"并打印补验警告——补跑 verify_md/verify_cases 通过前，不得信任该产出物的覆盖结论、不得进 Excel 流程。

---

# 输出位置约定（全局·强制·必读）

> **所有需求产出物统一写入当前项目根目录下的 `case-design-out/` 子目录**（即 `<项目根目录>/case-design-out/`），不散落到项目根目录。

* **产出物范围**：索引 `MANIFEST.md`、需求文档 `REQ_<需求标识>.md`、澄清台账 `Clarification_Ledger_<需求标识>.md`、测试用例 `TestCases_<需求标识>.md` / `TestCases_<需求标识>.xlsx`、知识总结 `Knowledge_<需求标识>.md`——全部落盘到 `case-design-out/` 下
* **Runtime 维护的共享索引（非模型产出物）**：`MANIFEST.md`（多需求索引）、`KB_lessons.md`（自我进化经验库）、`KB_business.md`（业务历史知识库）三者均由 Runtime 在 FileLock 下独占维护，**模型禁止 Write/Edit**（详见 §4/§5）。三者存在与否不影响模型当需求的产出职责——无文件即 no-op（输出与无 KB 时逐字节一致）。
* **需求文档强制落盘**：`REQ_<需求标识>.md` 在第0阶段步骤零强制落盘（用户内联提供或给路径的需求文档均落盘；纯散文/无标题者落盘前补 `## 二级标题` 分节），为 #4/#5 反向需求追溯提供唯一可靠基准——不落盘则"完整覆盖无遗漏"承诺失效（详见 `references/phase0_manifest.md` 步骤零）
* **非 Markdown 文档经 `extract_doc.py` 落盘**（v0.9.0·根因5）：用户提供 .docx/.pdf/.pptx/.xlsx/.png 等非 .md 文件路径时，禁止用 Read 工具直读原文（丢页眉/文本框/OCR 顺序），必须运行 `python skills/case-design/scripts/extract_doc.py <文件> --kind req|design --req-id <需求标识> --out-dir case-design-out` 全文抽取落盘；解析降级（`[FAIL]`）即硬阻断请用户补 Markdown/纯文本，不得静默继续（详见 `references/phase0_manifest.md` 步骤零"非 Markdown 文档解析落盘"）
* **读写统一前缀**：凡读写上述产出物，路径均为 `case-design-out/<文件名>`；索引表路径列填写相对 `case-design-out/` 的文件名（不含目录前缀）
* **目录自动创建**：`case-design-out/` 不存在时按需创建（首次写入产出物前）
* **临时文件**：Excel 生成/校验的 ad-hoc 脚本与中间产物（CSV/JSON/txt）同样置于 `case-design-out/` 下，用完即删（见 §临时文件清理 / `references/output_write.md` ch30）
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

不允许脑补需求/业务行为/表名/字段名/缓存Key；不允许生成伪测试/重复测试；不允许输出模糊断言；不允许跳过澄清环节；不允许重复询问澄清台账中已解决的问题；不允许增量写入文件；不允许跳过人工审核门禁；不允许遗留临时本地文件；不允许缩减用例集合凑 token 预算（一轮必须交付覆盖矩阵闭合后的完整用例集）；不允许在未运行 verify_cases.py 的情况下于交付摘要/审核话术填写脚本校验数值（未运行填"未执行"）。

违反任一即判定输出不合格。

## 3.2 优化方向（非风险标度，勿与 P0-P3 混用）

用例聚合 / 自动化友好 / Markdown结构稳定 / 追溯性完整 / 可复用性 / `case-design-out/` 产出目录整洁。

> **输出 token 预算（硬约束，非软方向）**：单次响应输出受 `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 上限（默认 32000）约束，Write 的 `content` 即模型输出，超限被截断报错。落盘前必须预估单次 Write `content` 输出 token，**默认单文件**；> 24000 先压缩（追溯性 section 全需求一份 + Given/When/Then 精简），压缩后仍超才拆最小 PART（`TestCases_<需求标识>_PARTn.md`，按风险排序、不按模块拆），或将展示(第12阶段)与写入(第13阶段)分属不同响应（细则见 `references/output_write.md` 写前规模评估）。
>
> **预算只决定"怎么写"，永不决定"写哪些"（v0.6.0·反缩减硬条款）**：用例集合在第11阶段自查通过时即冻结。token 预算的合法出口**仅三个**：压缩 → 拆 PART → 展示与写入分响应；**禁止以 token/上下文/时间限制为由缩减用例集合**（如只交付"核心用例/代表性采样"、宣称"其余留待后续轮次"）——一轮 = 一个需求的**全部**用例，缩减用例集即执行缺陷，与增量写入同级。

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
未提供时退回当前"自然语言兜底+澄清提问"行为，不阻断——但若【设计文档】含接口描述（接口名/facade/方法签名/入参出参/错误码/@Service/@RestfulApi/Dubbo 方法），第0阶段亦强制启用契约驱动分支（v0.8.0·设计文档驱动），避免 requirement 驱动下接口契约类测试点完全失守。
<<<接口契约结束>>>

【设计文档】（可选·设计文档测试要点强制覆盖·v0.8.0）
<<<设计文档开始>>>
开发/架构设计文档（Markdown）。含技术方案、调用链路、字段映射、错误处理、测试要点章节。
提供时：
- 第0阶段把**设计文档整文**落盘为 case-design-out/DESIGN_<需求标识>.md（v0.9.0·根因2：全量落盘，不再只提取"测试要点"章节；#8-H 反向设计文档测试要点追溯基准，见 references/phase0_manifest.md 步骤零）。**非 .md 文件路径须经 `scripts/extract_doc.py --kind design` 落盘**（v0.9.0·根因5，降级即硬阻断）
- 设计文档无任何可追溯章节（测试要点/验证点/验收标准/异常处理/错误码/边界约束 等）时（根因3）须从正文/字段映射/异常处理补建 `## 测试要点` 章节，不得 SKIP 了事
- 第2阶段覆盖矩阵新增"8.11 设计文档测试要点覆盖"维度（见 references/coverage.md）
- 第7阶段测试点建模须引用设计文档测试要点
- 第8/10/13阶段 #8-H 硬门：DESIGN 可追溯章节每条须被用例"关联规则"列或"用例名称"列覆盖，未命中显式列时回退 Given/When/Then 全文补判（scripts/verify_cases.py design_doc_testpoints_trace；v0.9.0 runtime/Phase13 均传 `--design`）
- safety_coverage 硬门触发条件：DESIGN 含敏感信号词（手机号/身份证/银行卡/财务/脱敏/verifyAuth/token 等）时须有 ≥1 条测试类型=安全的用例
未提供时退回当前行为，不阻断（#8-H/SKIP）。
<<<设计文档结束>>>

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

需求标识由 `bootstrap` 派生写入 `state.req_id`（见"入口协议"），模型从 state 读取，不在阶段内派生。

> **可选通道的流向**：技术实现摘要 → 第4阶段 SDD（State/Exception/契约事实校对）+ 第8阶段测试数据 + 检查9（存储可断言，见 references/selfcheck.md）；业务规则与历史缺陷 → 第3阶段规则建模 + 第5阶段业务领域风险；历史缺陷摘要 → 第5阶段缺陷种子测试点（强制覆盖）。三者均可选，未提供时 skill 退回当前"自然语言兜底+澄清提问"行为，不阻断。 接口契约文档 -> 第4阶段接口契约模型+变更影响清单 + 统一接口测试矩阵（契约/规则/场景三类）+ 检查16/#6 反向接口追溯；启用契约驱动分支（见 references/modeling.md 接口契约模型、references/dedup_coverage.md 契约驱动分支）。 设计文档 -> 第0阶段全量落盘 DESIGN_<需求标识>.md（v0.9.0 整文落盘）+ 第2阶段覆盖矩阵 8.11 + 第7阶段测试点引用 + 第8/10/13阶段 #8-H 反向设计文档测试要点追溯（runtime/Phase13 均传 `--design`）+ safety_coverage 触发（v0.8.0，见 references/phase0_manifest.md 步骤零、references/coverage.md 8.11、references/dedup_coverage.md #8）。

---

# 6、执行工作流（强制）

## 第0阶段：需求定位（必读，必须首先执行）

解决多需求快速定位。**必须首先读取** `references/phase0_manifest.md` 获得完整规则后执行：

1. 读取索引文件 `case-design-out/MANIFEST.md`（存在则读入全部索引表；`case-design-out/` 或索引文件不存在视为首次，按需创建目录与空索引）。**MANIFEST 由 Runtime 在 gate PASS 时自动维护**，模型可读但禁止 Write/Edit。
2. 匹配需求标识（精确匹配/关键词匹配/无匹配=新需求）；`req_id` 已由 `bootstrap` 派生写入 `state.req_id`，本阶段直接读取使用，不在阶段内派生。
3. 匹配成功则定位已有文件（均位于 `case-design-out/` 下）：`case-design-out/Clarification_Ledger_<需求标识>.md` / `case-design-out/TestCases_<需求标识>.md` / `case-design-out/Knowledge_<需求标识>.md`
4. 判断处理模式（新需求完整设计 / 已有需求增量 / 修改 / 复用）

**强制**：必须先读索引文件，禁止逐一扫描所有文件；索引由 Runtime 在各 gate PASS 时按里程碑自动维护——Phase 0 PASS → `add`（status=进行中，需求名称从 `REQ_<id>.md` 首个 `# ` 标题自动抽取），Phase 1 confirm → `update` 台账文件列，Phase 13 PASS → `update` 用例文件列，Phase 14 confirm → `complete`（status=已完成）。**模型禁止 Write/Edit MANIFEST.md**（铁律 4）；失步时执行 `python runtime/qamaster_runtime.py manifest reconcile` 从磁盘重建。索引文件位于 `case-design-out/MANIFEST.md`。

## 主执行流程（第1-15阶段）

必须严格顺序执行（单轮视角）：

1. Requirement Analysis + Clarification（需求分析与澄清，落盘台账，问题按角色路由 @开发/@产品/@业务，详见 `references/clarification.md`）
2. Test Requirement Analysis（测试需求分析，维度见 `references/coverage.md`）
3. Rule Modeling（规则建模，详见 `references/modeling.md`；含**第3阶段出口机器 gate**——规则来源 check_rule_source + R 编号连续性，runtime 强制 `verify_cases.py --phase-gate 3`，检查点 `.qamaster/case-design/<需求标识>/checkpoint_3.md`）
4. Specification Modeling（规格建模 SDD，State/Exception/契约标注事实来源由 @开发 校对，详见 `references/modeling.md`）
5. Risk Analysis（风险分析，三源共验产出 P0-P3：需求推导+技术隐含@开发+业务领域@业务+缺陷反哺，详见 `references/risk.md`；含**第5阶段出口机器 gate**——风险来源 risk_source_report + RK 编号连续性，runtime 强制 `verify_cases.py --phase-gate 5`；含**第5阶段 critique 循环**——P0 漏标对抗式第二视角，≤2轮 critique 自修）
6. Test Strategy Matching（测试策略匹配，决策表见 `references/methods.md`）
7. Test Point Modeling（测试点建模，维度见 `references/coverage.md`；含**第7阶段出口机器 gate**——TP 编号连续性 + P0/P1 风险→≥1 TP，runtime 强制 `verify_cases.py --phase-gate 7`，检查点 `.qamaster/case-design/<需求标识>/checkpoint_7.md`）
8. Test Case Generation（用例生成，Given/When/Then + AI友好 + 字段规范 + 断言完整性，详见 `references/modeling.md` 与 `references/quality_rules.md`；含**第8阶段出口机器 gate**——`verify_cases.py --phase-gate 8` 全量校验 + **反向引用完整性(D1) + 台账传递 + 行为一致性(C3) + 消费门禁**，runtime 强制；检查点 `.qamaster/case-design/<需求标识>/checkpoint_8.md`；详见 `references/modeling.md` 15.7）
9. Duplicate Removal（去重，详见 `references/dedup_coverage.md`）
10. Coverage Validation（覆盖率校验 + 反向需求追溯 #4 + 反向行为来源追溯 #5 + **台账待确认门禁(C2) + 台账传递**，详见 `references/dedup_coverage.md`；含**第10阶段出口机器 gate**——runtime 强制 `verify_cases.py --phase-gate 10`，检查点 `.qamaster/case-design/<需求标识>/checkpoint_10.md`）
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
脚本校验摘要（取自 verify_cases.py 输出末尾 `##VERIFY_SUMMARY##` 机器摘要块，逐字段摘抄，禁止凭印象手填；**脚本未实际运行时五项一律填"未执行"，填数值即声明脚本已运行，声明与实际不符 = 3.1 红线"判定输出不合格"**）：
  检查13 断言完整性：疑似 <n> 条 / 未执行（状态变更类缺副作用）
  检查9增强 存储schema交叉：跳过/疑似 <n> 条 / 未执行（断言存储名不在技术实现摘要清单）
  风险来源待确认：<n> 条 P0/P1 / 未执行（技术隐含@开发/业务领域@业务/缺陷反哺 未在台账确认）
  #4 反向需求追溯：未校验(REQ缺失/不可解析,待消除)/需求条目 <m> 条、未引用 <k> 条/全部覆盖 / 未执行
  检查15 业务行为来源追溯(#5)：疑似 <n> 条 / 未执行（无来源业务行为/无来源标记规则项）
覆盖硬门（v0.6.0）：#4-H 需求引用率 / #6-H 接口三类 / RK P0-P1 风险 —— 通过 / FAIL<明细> / 未执行
假设登记：共 k 条假设（连跑/轻量模式），已回显进【待确认问题与假设清单】（状态=假设）
审核状态：已人工审核通过 / 待人工审核
输出文件：case-design-out/TestCases_<需求标识>.md [+ case-design-out/TestCases_<需求标识>.xlsx]（拆 PART 时为 case-design-out/TestCases_<需求标识>_PARTn.md 多文件）
知识总结：未生成 / 已生成(case-design-out/Knowledge_<需求标识>.md) / 已更新 / 审核未通过暂不生成
Excel 状态：未生成 / 已生成(经21.7脚本产出+结构验证+数据完整性校验全过) / 生成失败
Excel 数据校验：未执行 / 七项全过 / 不通过(问题项及条数)
临时文件清理：已清理(清单) / 无临时文件产生 / 清理失败(残留清单)
待确认问题：Q列表中未关闭 m 条（P0/P1 阻断项）
下一步建议：<提示人工动作：审核/回答问题/许可生成Excel/安装openpyxl>
```

要求：连跑跳过等待仍须输出摘要；P0/P1 阻断项须显式列出；Excel/知识总结/清理须如实填写，未通过不得声明已生成。**脚本校验摘要**五项数值须从 `verify_cases.py` 输出末尾的 `##VERIFY_SUMMARY##` 机器摘要块逐字段摘抄（检查13 断言完整性 / 检查9增强 存储schema交叉 / 风险来源 / 反向需求追溯 #4 / 检查15 业务行为来源追溯 #5），禁止凭印象手填；**脚本未运行时填"未执行"，禁止编造数值**（编造即违反 3.1，判定输出不合格）。**#4 反向需求追溯行**：REQ 已落盘且可解析时填"需求条目 N 条、未引用 K 条/全部覆盖"；REQ 缺失或不可解析时填"未校验(REQ缺失/不可解析,待消除)"——此为显式强提示（`references/dedup_coverage.md` #4 显式强提示节），完整模式须消除（补落盘 REQ/补 ## 标题后重跑）才进第14阶段，**禁止填"跳过"隐瞒**；其余跳过项（如检查9增强未提供技术实现摘要）填"跳过"并注明原因。**拆 PART 自动续跑时**：中间 PART 落盘后交付摘要"下一步建议"填"自动续跑下一 PART"，仅末 PART 填"统一审核全部文件"；审核状态以全部 PART 聚合填写。

---

# 临时文件清理（全局·强制·概要）

执行中产生的临时脚本/中间产物（CSV/JSON/txt/片段/日志）须在不再使用时立即删除（置于 `case-design-out/` 下）。**例外**：`scripts/` 下的 `verify_md.py`、`verify_cases.py`、`verify_knowledge.py`、`project_cases.py` 为 skill 自带可复用资产，**不删除**；仅 ad-hoc 一次性脚本（如 Excel 生成脚本）用完即删。正式产出物（`case-design-out/` 下的 `TestCases_*.md/.xlsx`、台账、knowledge、原始需求）禁止删除。完整规则见 `references/output_write.md` 临时文件清理节。

---

# 校验规则契约（单一事实源·降本）

`config/validation_rules.json` 为校验规则的**单一事实源**：15 列表头、测试类型/维度/等级枚举、固定值列、断言可观测正则、模糊词、存储合规模式、关键词维度、状态机流转锚点、边界深度词、异常子类、过度设计业务锚点、追溯性 section 格式——全部集中于此。`scripts/verify_cases.py` 与 `scripts/verify_md.py` 启动时共同加载该清单，`config/domain_config.json` 在此基础上按领域覆盖（同名字段替换）。该文件为 skill 永久资产，不删除。

**覆盖硬门（v0.6.0·事故修复）**：`verify_cases.py` 在软性提示之外新增三项机器硬门（违约即 exit=1），口径集中于 `config/validation_rules.json` 的 `coverage_gates`：

| 硬门 | 口径 | 配置 |
| -- | -- | -- |
| #4-H 需求追溯 | REQ 可解析时，需求条目被用例"关联需求ID"列引用比例 ≥ `req_trace_min_ratio`（默认 1.0）；REQ 缺失/不可解析不判（由 #4 显式强提示接管） | 比例值 |
| #6-H 接口三类 | 变更影响清单每个接口三类覆盖(契约presence+type+出参/规则/场景)齐全 | full/auto_light/off |
| RK P0/P1 风险 | 风险清单 P0/P1 均须被用例"关联规则"列引用 | full/auto_light/off |

`full`=硬门；`auto_light`=完整模式仍硬、连跑/轻量降为软告警（交付摘要须显式列缺口）；`off`=关闭。`domain_config.json` 的 `coverage_gates` 可按领域覆盖。输出末尾固定打印 `##VERIFY_SUMMARY## k=v;...` 机器摘要块——交付摘要与审核话术的脚本校验数值**必须逐字段摘自该块**（见交付摘要模板）。

**agent 需要规则契约时**：运行 `python scripts/verify_cases.py --dump-rules`（经 Bash），即可拿到上述全部校验口径的紧凑投影（约 60 行），**无需读 `verify_cases.py` 源码**。设计用例前读这一份契约即可一次过校验，避免因漏读校验口径（枚举越界 / 断言无可观测锚点 / 存储杜撰 / section 格式不符 / 覆盖硬门违约）导致整文件重写。`references/*.md` 的散文规则与本清单冲突时，以本清单（机器判定）为准。

---

# 阶段门禁前移与制品传递（v0.7.0·模型无关·设计见 PHASE_GATE_DESIGN.md）

> 闭合"中间阶段橡皮章 + 跨阶段制品靠模型记忆"两大流程控制缺口。Runtime 兑现"门禁以机器判定为准"的承诺，从首尾(0/13/15)扩展到中间 3/5/7/8/10。

## 检查点机制（沉淀阶段）

Phase 3/5/7/8/10 结束时，模型把**本阶段产物**写到 `.qamaster/case-design/<需求标识>/checkpoint_<阶段>.md`（路径由 Runtime 解析，状态按 `(workflow, req_id)` 分区隔离不同需求；每阶段一次性 Write，非 Edit；runtime 受控临时件，Phase 13 后清理）。runtime 的 gate 解析它 → 跑阶段专属检查 → 回填 `state.json` 制品注册表。**不违反"禁止增量写 TestCases.md"红线**——该红线针对最终 `TestCases_*.md`，检查点是 runtime 临时件。

### 检查点格式契约（v0.7.1·强制）

检查点必须含 runtime 可解析的产物，**不可只写摘要文档**，否则 phase-gate 报"检查点格式不符·无用例表"FAIL（须重写检查点，非改用例格式）：

| 阶段 | 检查点必须含 | 可选共存 |
|---|---|---|
| Phase 3 规则建模 | `## 规则建模` section（粗体规则项，每项带 `[来源:...]`）| 摘要正文 |
| Phase 5 风险分析 | `## 风险清单` section（表格：风险ID\|风险等级\|风险描述\|关联模块\|风险来源）| 摘要正文 |
| Phase 7 测试点 | `## 测试点清单` section（表格：测试点ID\|场景类型\|测试点描述\|关联模块）| 摘要正文 |
| **Phase 8 用例生成** | **完整 15 列用例表**（首列"用例ID"，与最终 TestCases.md 同结构；含追溯性 section 规则建模/风险清单/测试点清单）| 覆盖预检摘要 |
| **Phase 10 覆盖率** | **复制 checkpoint_8.md 的完整 15 列用例表 + 追加覆盖分析**（不可只写"## 覆盖率 OK"摘要；#4-H 需求追溯校验用例表的"关联需求ID"列）| 覆盖缺口清单 |

> **格式违反示例**（必 FAIL）：Phase 10 检查点只写 `## 覆盖率\n\nOK\n` → `parse_table_from_lines` 返回 None → `data_rows=[]` → #4-H 误报"全部未引用"。正确做法：检查点含用例表，让 #4-H 校验真实的"关联需求ID"列引用。

## 契约卡注入 PRIOR_ARTIFACTS

Runtime 按**当前阶段 `consumes`** 从 `state.json.artifacts` 注入上游制品指针（不靠模型记忆）：
- Phase 8 卡片注入：规则 R1-R24 / 风险 RK1-RKn(P0/P1 计数) / 测试点 TP1-TPn / 台账(已解决/待确认/假设) + 消费约束（关联规则列 R/RK/TP 须在清单内·悬空引用 exit=1；用例等级须映射 RK 等级；台账"已解决"事实须落成断言；假设A<n> 须在台账假设清单内；台账"待确认"须闭环或转假设）。
- 上下文裁剪也不丢：制品注册表持久化在 state.json，契约卡每次按需渲染。

## verify_cases.py 检查项加固（exit=1 硬门 + 软探针）

- **项1 反向引用完整性**（D1）：用例关联规则列引用的 R/RK/TP/API/SC 须在清单内真实存在。
- **项2 section ID 连续性**（D2）：RK/TP/API/SC 编号无跳号（R 为 warn，按类目自由编号）。
- **项3 假设标签对账**（RC7）：`假设A<n>` 须在假设清单内登记。
- **项4 台账接入**（C3/C2/G3-G8·直击 RC0）：`--ledger` 参数启用 `parse_clarification_ledger`，台账权威事实成为校验对照源（传递/待确认门禁/一致性）。
- **项5 行为一致性**（C3·软）：用例断言与台账事实反义词矛盾嫌疑。
- **项6 关键词覆盖探针**（G5/G6/G7 + RC6·软）：非台账点(异步/脏payload/端点/消费组)覆盖。
- **项8 REQ 缺失门禁**：REQ 缺失/不可解析 exit=1（补 v0.6.0 拘留）。

## 有界返修（堵 silent infinite-retry）

`state.json.gate_rounds` 记自动门原地返修轮次；Phase N 门禁连续失败 ≥3 次 → runtime 强制输出"疑似系统性问题，请人工介入或 `fail --to <更早阶段>` 回退"，把"模型反复改不过"从静默变成可见停顿。

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
        "Write(case-design-out/Clarification_Ledger_*.md)",
        "Edit(case-design-out/Clarification_Ledger_*.md)",
        "Write(case-design-out/Knowledge_*.md)",
        "Edit(case-design-out/Knowledge_*.md)",
        "Write(case-design-out/REQ_*.md)",
        "Write(case-design-out/TestCases_*.xlsx)",
        "Bash(python *qamaster_runtime.py manifest:*)",
        "Bash(python *verify_md.py:*)",
        "Bash(python *verify_cases.py:*)",
        "Bash(python *verify_knowledge.py:*)",
        "Bash(python *project_cases.py:*)",
        "Bash(python *verify_cases.py --dump-rules)"
      ]
    }
  }
  ```
  （`acceptEdits` 与允许列表二选一；语法/路径按你的 Claude Code 版本与工作目录调整。）

> 说明：skill 侧已通过"单文件默认 + 一文件一次 Write + 小体积 Write 合并同响应"将调用数压到最低；权限配置是把这些调用从"每次审批"变为"免审批"的最后一跃，属用户权限边界，须用户自行设定。

---

# 抬高单 Write 天花板（可选·用户侧）

重型/超大需求（>60 条）即便压缩也可能逼近 24000 token。用户可设环境变量 `CLAUDE_CODE_MAX_OUTPUT_TOKENS=48000`（或更高）抬高单次 Write 上限，让更大需求也能单文件一次写入。skill 不依赖该设置（仍以 24000 阈值/压缩/PART 兜底），但重型批量场景推荐启用。

---

# 参考文件索引（按阶段按需读取）

> 进入对应阶段前读取相应 ref。ref 内容为本 skill 细则，与单文件版规则一致。

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

---

# 结束语

Specification First → Test First → Risk First → Coverage First → Automation First → AI Friendly First → Complete Output First（禁止增量写入）→ Human Review First（人工只在确认/审查/回答/许可介入；门禁可按模式自动放行但保留审计痕迹）→ Reuse First（Excel-only 优先复用已有 .md，须先过一致性校验；知识总结复用已审核用例+台账+需求文档）→ Traceability First。

> 各类禁止性规则已分布于对应 references 的"禁止/强制"节，此处不重复罗列；执行时以各阶段 ref 为唯一细则来源。核心红线（违反任一即判定输出不合格，见 3.1）：不脑补需求/业务行为/表名/字段/缓存Key、不生成伪测试/重复测试、不输出模糊断言、不跳过澄清、不重复询问台账已解决项、不增量写入文件、不跳过人工审核门禁、不遗留临时文件。

优先高风险、高价值、可自动化、可回归、AI 可解析、完整输出、审核门禁、复用已有资产、可追溯、自动推进、脚本化生成 Excel 并验证落盘、`case-design-out/` 产出目录整洁、审核通过后自动沉淀知识总结、索引文件快速定位、按需求规模自动分级。