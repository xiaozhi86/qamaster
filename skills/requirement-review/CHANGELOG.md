# Changelog - requirement-review

本文件记录 requirement-review skill 的版本变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.5.0] - 2026-08-25

### 新增

- 自我进化知识系统解锁（lessons/expert 两库，v2.4.1）：`KB_lessons.md`（经验库）/`KB_expert.md`（专家方法论库）及其 `kb` 命令族、纠正自动捕获（`fail`/`patch` 沉淀 draft）、`##PRIOR_LESSONS##`/`##RELEVANT_LESSONS##`/`##PRIOR_EXPERT_KB##` 注入链、以及 Phase 4/7（用户确认门/最终输出门）的 `##METHODOLOGY_CAPTURE##` 沉淀提醒均对 requirement-review 生效。
- surface 词表兜底：`kb_store.get_surface_map` 主路（`verify_cases.py --dump-surface-map`）失败后降级读 `config/agents.json` 的 `agents[].required_signals`（键=扩展专家 id），使无 `verify_cases.py` 的 skill 也能派生 lesson 的 dim/trigger。
- 方法论捕捉阶段泛化：`WorkflowSpec.methodology_capture_phases` 字段（默认 `{14,15}`）取代硬编码，requirement-review 设 `{4,7}`，措辞适配「评审方法论」（case-design 仍「测试设计方法论」）。

### 变更

- `KB_business.md`（业务历史知识库）仍为 case-design 专属（requirement-review 无 `Knowledge_*.md` 业务总结产物、无 reconcile 聚合源）；`knowledge_gate` 仍为空。
- README §10、case-design README §8.5、设计文档 §8.5.6 同步 KB 覆盖范围说明。

## [0.4.1] - 2026-08-25

### 新增

- 需求 vs 设计一致性核对：Phase 0 多文档清单块追加核对指令——专家团逐条对照主需求文档的业务规则/数据口径/状态流转/异常边界，与各设计文档的技术/接口/数据结构细节，找出冲突（设计改口径/规则未同步）与遗漏（需求有定义、设计未落地），结论纳入评审问题清单并统一回填（`runtime/workflows/requirement_review.py` `_inputs_block` + SKILL.md 第0阶段）。

### 变更

- `_parse_input_docs`（`runtime/qamaster_runtime.py`）升级为「文件 + 内联混排」解析：①返回 `(entries, True)`，entry 形如 `("file", 路径)` 或 `("text", 片段)`；②改用 `shlex.split(posix=False)` 支持引号包裹的含空格路径（保留 Windows 反斜杠），引号未闭合回退 `ui.split()`；③外层引号仅在整串包裹且内部无同引号时剥离（避免剥坏逐文件引号）；④文件数 ≥2 才走多文档分支，非文件 token 保留为「补充说明 N」按出现位置排序。
- `_write_inputs_manifest`（`runtime/qamaster_runtime.py`）接受 `entries`，文件按「主需求文档 / 设计文档 N」、内联片段按「补充说明 N」落盘；首个 file 为主需求文档。
- `cmd_bootstrap` 多文档分支改为从 `entries` 取首个 file 派生 req_id。
- 单文档路径逐字节不变：无 `INPUTS_<id>.md` 时 Phase 0 契约卡不追加清单块；case-design 不受影响（多文档分支显式 `spec.name == "requirement-review"` 门禁）。
- SKILL.md 第0阶段、README §6.2/§9、版本头同步 v0.4.1。

## [0.4.0] - 2026-08-24

### 新增

- 多文档综合评审：`/requirement-review @主需求.md @设计A.md @设计B.md` 一次提供多份文件，第一个为主需求文档（决定 req_id、专家团信号词路由、MANIFEST 需求文档列），其余按序作为设计文档；Runtime 在 bootstrap 落盘 `INPUTS_<需求标识>.md` 清单，Phase 0 契约卡注入「多文档综合评审」清单块，模型逐份抽取后按序合并为一份 `REQ_<需求标识>.md` 评审语料（主需求在前 + 各设计文档 `## 输入文档：<文件名>` 分节），后续评审/重构统一综合多份文档、输出一份 `ReviewedReq_<需求标识>.md`。
- 新增 `_parse_input_docs` / `_write_inputs_manifest` / `_bootstrap_finish`（`runtime/qamaster_runtime.py`）；`_inputs_block`（`runtime/workflows/requirement_review.py` Phase 0 注入）。

### 变更

- 单文档路径逐字节不变：无 `INPUTS_<id>.md` 时 Phase 0 契约卡不追加清单块；case-design 不受影响（多文档分支显式 `spec.name == "requirement-review"` 门禁）。
- SKILL.md 第0阶段补「多文档综合评审」步骤；README §6.2/§9、CHANGELOG 同步。

## [0.3.1] - 2026-08-24

### 变更

- 专家团路由从「纯字面信号词命中」升级为「三级裁决 + 存疑即启用」：①信号词命中必启用 → ②co_trigger 连带启用（`config/agents.json` 新增 `co_trigger`：Arch/Risk 命中即连带 BA）→ ③语义兜底（未命中但视角仍有价值则启用并记理由，仅明确无关才裁掉）。
- 修复 0.3.0 的路由漏选：资金/接口类需求原文无 BA 字面词（"上下游/对账/业务规则"）时 BA 被误裁，但其「数据口径/枚举/业务规则」视角价值高——现经 co_trigger + 语义兜底兜回。
- `config/agents.json` 新增 `_routing_policy`（默认偏向「宁多勿漏」）、`_co_trigger_semantics` 字段；BA `required_signals` 增补「枚举/校验/约束/触发/状态流转/兜底/默认值」等场景语义词。
- SKILL.md 第0阶段步骤6、README §2 同步三级裁决说明；`requirement_review_phases.py` Phase 0 objective/allowed/forbidden 措辞同步（forbidden 增「仅按字面信号词硬裁专家」）。

## [0.3.0] - 2026-08-21

### 新增

- 专家团动态路由：不是任何需求都全量 7 专家，Phase 0 按需求文本信号词从 `config/agents.json` 选出「核心团 + 命中扩展团」作为本次评审专家团（落盘 `Agents_<需求标识>.md`）。
- 专家池目录 `config/agents.json`（可扩展池）：核心团 `core_agents`（PM/QA/Dev 恒参与）+ 各专家 `required_signals` 信号词（BA/Arch/UX/Risk 按需）；新增专家只需加一条 + SKILL.md 补评审标准，不改 Runtime。
- Runtime 新增 `contains` 门禁类型：确定性校验产物文件含全部 `must_contain` 子串，Phase 0 gate 机器判定专家团名单含核心团 PM/QA/Dev（防模型漏选核心团）。
- Phase 1 契约卡经 `extra_card_text` 钩子注入本次评审专家团（只启用名单内专家）；Phase 2 冲突检测改按实际参与专家两两组合。

### 变更

- SKILL.md / README.md：措辞「7-Agent」→「专家团」，新增「专家团动态路由」说明；§2 专家表加「参与方式」列；§7 阶段表、§9 产出物（+ `Agents_<req_id>.md`）、§11 目录结构（+ `config/agents.json`）同步。

## [0.2.0] - 2026-07-17

### 新增

- 输入预处理能力：图片/扫描件/含图文档统一抽取为纯文本，避免文本-only 模型 400 硬崩（`config/input_rules.json` + `scripts/extract_text.py`）。
- 多格式抽取：PDF（pdfplumber 文本+表格+图片坐标）/ Word（python-docx 遍历 body 子元素）/ PPT（python-pptx）/ Excel（openpyxl）/ 图片（RapidOCR 中文）。
- 就地回填：图片 OCR 文本就地回填到文档原位置（占位符 `【图片@位置k(置信度)：文本】`），保留图文上下文语义，不汇总到文末或丢失；PDF 复杂版式降级为正文留位置标记+文末汇总。
- 扫描件 PDF 兜底：整页字符<阈值 → pdf2image 逐页转图 → 整页 OCR（天然就位）。
- 降级链路：依赖缺失自动 pip install 兜底；OCR 低置信度回退提示用户补文字说明；扫描件 poppler 缺失回退提示用户转文字版。
- SKILL.md 新增第0阶段（输入预处理与降级）+ 输入协议补文本-only 约束。

## [0.1.0] - 2026-07-13

### 新增

- 需求文档多角色评审 skill 首个版本。
- 7 个专家 Agent 并行评审：BA（业务分析）/ PM（产品设计）/ QA（测试设计）/ Arch（技术架构）/ UX（用户体验）/ Risk（风险控制）/ Dev（开发实现）。
- 九阶段流程：并行评审 -> 结果汇总去重 -> 冲突检测 -> 优化方案总览 -> 用户确认 -> 需求文档重构 -> 自动复查 -> 二次修复 -> 最终输出。
- 输出优化后的高质量需求文档 + 评审问题详情列表（含已解决/未解决）。
- 输出落盘到项目根的 `requirement-review-out/` 目录。
