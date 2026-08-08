# case-design 阶段门禁前移与制品传递设计 v1.0.0

> **状态**：待评审（未实施）
> **日期**：2026-08-04
> **作者**：xiaozhi
> **范围**：`skills/case-design`（scripts / config / references / SKILL.md）+ `runtime/`（state_store / phases / qamaster_runtime）
> **与既有设计的关系**：本文是 `qamaster-Agent-Runtime-Engineering-Refactor-Design-v2.0.0.md`（Runtime 总体重构）在"中间阶段门禁 + 跨阶段制品传递"维度的细化与落地，不改写那份总览；二者互补，本文不推翻既有 Runtime 哲学，而是**让 Runtime 兑现自己承诺却未做到的两件事**。

---

## 0. 一句话目标

让 qamaster 的 0-14 阶段流程在**模型无关**的前提下做到两件事：
1. **上游制品不靠记忆传递**——runtime 携带制品注册表，契约卡注入，上下文裁剪不丢。
2. **质量门禁在生成时就地强制**——检查从"Phase 13 写盘后才发现"前移到"Phase 3/5/7/8/10 各阶段出口由 runtime 跑"，FAIL 不放行。

从而系统性消除：台账事实没传到用例（RC0/RC8）、引用悬空（RC1/D1）、编号跳号（RC2/D2）、用例违背台账/规则（RC4/C3）、待确认项泄漏落盘（RC9/C2）、覆盖缺口（RC6/G3-G8）。

---

## 1. 背景

### 1.1 现状基线（精确到代码行）

`runtime/phases.py` 定义 0-15 共 16 阶段，但真正有 `gate_checks` 的只有 3 个：

| 阶段 | gate_checks | 实际行为 |
|---|---|---|
| 0 需求定位 | `exists_any`/`exists` | 文件存在即放行 |
| 13 写盘 | `verify_md.py` + `verify_cases.py` | 脚本 exit=0 才放行 |
| 15 Excel | `gen_excel.py` | 脚本 exit=0 才放行 |
| **2/3/4/5/6/7/8/9/10/11/12/14** | **`[]`（空）** | `cmd_gate` L380-381 打印"本阶段无机器检查项…Runtime 记录通过"**直接放行** |

`runtime/qamaster_runtime.py::_card`（L164-222）渲染的契约卡只含 CURRENT PHASE / ALLOWED / FORBIDDEN / PRODUCES / EXIT CONDITION，**无 PRIOR_ARTIFACTS**——上游沉淀（规则/风险/测试点/台账事实）从不被注入。

`runtime/state_store.py::new_state`（L50-68）的 state.json 字段无 `artifacts`、无 `consumes`——沉淀只活在模型上下文里，上下文被压缩即失真。

`verify_cases.py::run_inmemory`（L1238）虽是 Phase 8 出口 gate 的 keystone，但它是**模型经 Bash 自跑的建议循环**，runtime 既不调用也不感知（Phase 8 的 `gate_checks=[]`）。runtime 真正强制的脚本门只有 Phase 13/15。

### 1.2 真实事故复盘（本轮评审发现）

对 `case-design-out/TestCases_电销通话AI总结.md`（33 条用例，Phase 13 全部 exit=0 通过）评审发现：

- **D1 悬空引用**：SUM_008/013/015 引用 R26/R28，但规则清单只到 R24。`verify_cases.py` 只查"清单每项被用例引用"（section→case），不查"用例引用的 ID 是否存在"（case→section）→ 全程漏网。
- **D2 编号跳号**：测试点清单 TP1-6、TP8-42，TP7 缺失。`check_ids`（L377-402）只查**用例 ID** 连续性，不查 R/TP/RK/API 编号连续性。
- **C3 用例违背台账**：台账 Q4 已明确"SpEL 异常→放行"，SUM_005 却断言"丢弃"。`check_behavior_source` 只查"行为有无来源"，不查"行为与来源是否一致"。
- **C2 待确认泄漏**：台账 Q5 标"待确认"（重试 3 次还是 5 次未定），仍流进用例并硬编码取值，Phase 13 不拦。
- **G3/G4/G8 台账事实未传递**：台账 Q2/§权威事实有"connection_time 格式 yyyy-MM-dd HH:mm:ss""taskId/taskName 透传""重试消费组 dirp-rmp-app-record-summary-retry"，但无对应用例覆盖——台账事实是内存沉淀，Phase 8 本该消费却没消费。

### 1.3 根因（RC0-RC9）

| 根源 | 机制 | 导致 |
|---|---|---|
| **RC0 校验器不读台账** | `verify_cases.py` 只读 REQ，不读 Clarification_Ledger；`check_rule_source` 只看 `来源:` 标记存在，不校验所引 `台账Q<n>` 是否存在、不读台账权威事实 | RC4/RC8/RC9 失去机器兜底 |
| **RC1 引用校验单向** | 只查 section→case，不查 case→section；`check_behavior_source` 对任何 `(R\|TP\|API)\d+` 即判有来源 | D1 |
| **RC2 无编号连续性校验** | `check_ids` 只管用例 ID；R/TP/RK/API/SC 自由编号无查跳号 | D2 |
| **RC3 跨阶段消费无强制** | state.json 无 artifacts；契约卡无 PRIOR_ARTIFACTS；`consumes` 字段不存在 | RC0/RC8 结构性成因 |
| **RC4 行为来源只查有无不查一致** | #5 校验"有来源"，不校验"与来源一致" | C3 |
| **RC5 ID 生成无注册表** | R/TP/RK 在 Phase 3/5/7 自由编号、Phase 8 重新誊写，两处无双向对账 | 加剧 D1/D2 |
| **RC6 需求覆盖粒度过粗** | #4 按 `##` 标题切分；契约/接口定义型需求里"可配置/热生效/格式转换/透传/异步"等测点藏在正文，非标题，不被分解为可追溯项 | G3-G8 |
| **RC8 台账→用例传递缺口** | 台账权威事实无"→≥1 TP/用例"追溯 | G3/G4/G8 |
| **RC9 待确认项泄漏** | 台账"待确认"Q 未"已解决/正式假设"即流进用例并硬编码取值，Phase 13 不拦 | C2 |

> **RC3（无设计文档输入）经核查作废**：Phase 1 澄清台账（`Clarification_Ledger_*.md`）已把设计文档当输入做了需求↔设计对账（Q1 单位、Q5 重试次数、§重要契约差异 排序均为证）。C1/C4/D3/G9/G10 在台账层已权威解决或显式裁剪，**不是缺陷**。本轮真缺陷收窄为 D1/D2/C3/C2/G3-G8 + G5/G6（非台账点）。

---

## 2. 设计原则（模型无关，贴合本工程哲学）

1. **模型只思考，runtime 管制品 + 管门禁**——沉淀不再只活在模型上下文里；每个沉淀阶段产出一个 runtime 可解析的"检查点"，runtime 解析后写入 state.json 制品注册表。上下文裁剪也不丢。
2. **门禁前移、就地强制**——检查在生成阶段（3/5/7/8/10）就由 runtime 跑，FAIL 不放行；不再等 Phase 13 写完盘才发现。
3. **不破坏既有约束**——TestCases.md 仍 Phase 13 一次写盘（单文件一次 Write，禁 Edit 增量）；深度裁剪（heavy/medium/light）与降级协议（情形A/B）不变；state.json 仍由 `state_store` 单写。
4. **检查项单一事实源**——所有检查口径集中于 `config/validation_rules.json`；`verify_cases.py --phase-gate <N>` 与 Phase 13 全量校验共用同一套 `collect_all_findings`，保证"写前内存校验"与"写后回读校验"判定口径完全一致（沿用 v0.4.0 keystone 的回归安全原则）。
5. **补检查不破坏回归**——新增检查在全覆盖合规用例集上须 PASS（不误伤）；仅"覆盖不足/引用悬空/编号跳号/违背台账"的产出物被拦下。

---

## 3. 总体架构

### 3.1 现状（橡皮章中间阶段）

```
Phase0 ─gate─> Phase1(确认) ─gate─> Phase2 ─[空gate]─> Phase3 ─[空gate]─> ...
   制品靠模型上下文记忆传递                     runtime 橡皮章自动放行
... Phase8 ─[空gate·模型自律run_inmemory]─> Phase9 ─[空]─> Phase10 ─[空]─>
   唯一runtime强制兜底在Phase13写盘后           Phase11/12/13...
```

### 3.2 目标（runtime 携带制品 + 中间阶段强制门禁）

```
Phase0 ─gate─> Phase1(确认) ─gate─> Phase2 ─gate─> Phase3 ─gate─> Phase4 ─gate─>
   制品注册表(state.json)          各阶段gate由runtime跑verify_cases --phase-gate N
   契约卡注入PRIOR_ARTIFACTS        FAIL不放行·有界返修
... Phase7 ─gate─> Phase8 ─gate─> Phase10 ─gate─> Phase13 ─gate─> Phase14(确认)
   全量+消费+一致性     覆盖硬门+台账门禁     写盘+artifacts防漂移
```

### 3.3 三层职责（不变，仅补强）

| 层 | 职责 | 文件 |
|---|---|---|
| 业务规范 | 阶段细则、避坑红线、字段规范 | `SKILL.md` + `references/*.md` |
| 流程控制 | 状态机、契约卡、门禁裁决、制品注册表 | `runtime/{state_store,phases,qamaster_runtime}.py` |
| 客观校验 | 机器可判定的检查项（阶段子集 + 全量） | `skills/case-design/scripts/verify_cases.py` + `config/validation_rules.json` |

---

## 4. 制品注册表与跨阶段传递（修复 RC3/RC5/RC8）

### 4.1 state.json 新增 `artifacts` 字段（schema 1 → 2，向后兼容）

`state_store.py::new_state` 增字段：

```json
"artifacts": {
  "req":      {"items": ["单通通话AI分析接口", "客户特征ai分析建议接口", "挂机节点ai分析建议接口"]},
  "ledger":   {"resolved": ["Q1","Q2","Q4","Q6","Q7"],
               "open":     ["Q5"],
               "assumptions": ["A1","A2"],
               "facts":    ["yyyy-MM-dd HH:mm:ss", "taskId", "taskName", "dirp-rmp-app-record-summary-retry", ...],
               "path":     "Clarification_Ledger_电销通话AI总结.md"},
  "3":  {"rule_ids": ["R1",...,"R24"], "categories": [...], "source_marked": true},
  "5":  {"risk_ids": ["RK1",...,"RK17"], "levels": {"RK1":"P0","RK2":"P1",...}, "source_marked": true},
  "7":  {"tp_ids": ["TP1",...,"TP42"]},
  "8":  {"case_ids": ["..._SUM_001",...],
         "rule_refs": {"..._SUM_008": ["R5","RK10","R28"], ...},
         "level_map":  {"..._SUM_011":"P0", ...}}
}
```

**写入时机**：runtime 在各阶段 gate PASS 时，解析该阶段检查点 → 回填对应 `artifacts["<phase>"]`。模型不碰 state.json，保单写原则。

**兼容读取**：`state_store.load` 遇 schema=1 的旧 state.json，自动补 `artifacts={}`、`gate_rounds={}`，不报错（向后兼容既有进行中流程）。

### 4.2 phases.py 新增 `consumes` 字段（显式依赖图）

```python
# 节选
{"id":4,  ...,"consumes":["3"]},                              # SDD 消费规则
{"id":6,  ...,"consumes":["5"]},                              # 策略消费风险
{"id":7,  ...,"consumes":["5","2"]},                          # 测试点消费风险+测试需求
{"id":8,  ...,"consumes":["3","4","5","7","ledger","req"]},   # 用例消费全部上游
{"id":10, ...,"consumes":["8","req","ledger"]},              # 覆盖率消费用例+需求+台账
{"id":13,...,"consumes":["3","5","7","8"]},                  # 写盘组装
```

### 4.3 契约卡注入 PRIOR_ARTIFACTS

`qamaster_runtime.py::_card` 增一段，按当前阶段 `consumes` 从 `state.json["artifacts"]` 渲染（只注入 ID 范围 + 待确认项 + 关键事实摘要，控制卡片长度）：

```
PRIOR_ARTIFACTS（本阶段必须消费的上游制品·由 Runtime 注入，勿凭记忆）:
  规则 R1–R24 | 风险 RK1–RK17(P0:1·P1:14) | 测试点 TP1–TP42
  台账 已解决 Q1,Q2,Q4,Q6,Q7 / 待确认 Q5 / 假设 A1,A2
  台账关键事实: connection_time=yyyy-MM-dd HH:mm:ss; 透传 taskId/taskName; 重试消费组 dirp-rmp-app-record-summary-retry
  消费约束: 用例等级须映射 RK 等级; 关联规则列 R/RK/TP 须在上游清单内; 台账"已解决"事实须落成断言; 假设A<n> 须在台账假设清单内
```

→ 直接消除"台账有 Q4 放行、用例却写丢弃"：Q4 事实被注入到 Phase 8 卡片，且由消费门禁（§6.3）再校验一次。

### 4.4 检查点机制（让沉淀机器可见，绕开"禁止增量写 TestCases.md"）

每个沉淀阶段（3/5/7/8/10）结束时，模型把**本阶段产物**写到 runtime 检查点 `.qamaster/case-design/<req_id>/checkpoint_<阶段>.md`（每阶段一次性 Write，非 Edit；runtime 受控临时件，按 `(workflow, req_id)` 分区隔离不同需求，Phase 13 后清理）。

runtime 的 gate 解析它 → 跑阶段专属检查（§6）→ 回填 `artifacts["<phase>"]`。

> **不违反"禁止增量写入"红线**——该红线针对最终 `TestCases_*.md`（防 Edit/append 损坏）；`.qamaster/case-design/<req_id>/checkpoint_*.md` 是 runtime 受控临时件，与 state.json 同级（按 `(workflow, req_id)` 分区隔离），Phase 13 后由 runtime 清理（纳入"临时文件清理"节）。

---

## 5. verify_cases.py 检查项加固（修复 RC0/RC1/RC2/RC4/RC6/RC9）

> 与既有 v0.6.0 `coverage_gates` 一脉相承：新增检查的口径同样集中于 `config/validation_rules.json`，便于 `domain_config.json` 按领域覆盖。所有新检查复用既有工具（`parse_section_rows`、`_cases_citing` 的 `re.escape(id)+r"(?!\d)"` ID 匹配、`coverage_gate_failures` 聚合器、`_ASSUMPTION_TAG_PATS`），不造平行机制。

### 5.1 共享前置：`collect_section_ids(lines)` 解析器

插入 `parse_section_rows` 之后（约 L690）。扫描全部追溯性 section，返回 `{prefix:{ids:set, items:[(id,raw)]}}`。表格型 section（RK/TP/API/SC/A）用 `parse_section_rows` 取首列；R 在规则建模正文按 `\bR(\d+)\b(?!\d)` 扫描（与 R/RK 命名空间分离）。是项 5.2/5.3/5.4 的公共依赖。配置镜像 `section_id_definitions`。

### 5.2 项 1 — 反向引用完整性【闭环 D1，兼治台账 Q 悬空】

- **函数** `check_citation_resolution(data_rows, section_ids) → List[str]`。置于 `check_behavior_source` 附近（L921 后）。
- **逻辑**：从每行 `IDX_RULE` 抽 `(R|RK|TP|API|SC)(\d+)` token，凡 `num` 不在 `section_ids[prefix]` 即报；R/RK 命名空间分离；按行聚合。**同时校验 `台账Q(\d+)` 引用能在台账/规则来源中解析**（修 `check_rule_source` 现仅查标记存在的缺口）。
- **退出策略**：**硬（exit=1）**，并入 `hard_violations`。
- **配置** `citation_resolution`（含 `external_citation_marker` 行级豁免 `（外部引用）|（跨需求）`，处理跨需求合法引用）。
- **验证**：现产物 → exit=1 列出 R28(SUM_008)、R26(SUM_013)、R28(SUM_015)；合成 `台账Q99` → exit=1。

### 5.3 项 2 — section ID 连续性【闭环 D2】

- **函数** `check_section_id_contiguity(section_ids) → List[str]`。与 5.2 同位。
- **逻辑**：镜像 `check_ids`（L394-401）；每 prefix 下 ≥2 个 id 时 `missing = set(range(min,max+1)) - set(nums)`。
- **退出策略**：**RK/TP/API/SC = 硬(full)；R = warn**（R 按类目自由编号）。
- **配置** `section_contiguity = {"R":"warn","RK":"full","TP":"full","API":"full","SC":"full"}`，每 prefix 可 `off`。
- **验证**：现产物 → `测试点清单序号跳号，缺失: 7`(exit=1)。

### 5.4 项 3 — 假设标签↔已登记假设对账【闭环 RC7 标记纪律】

- **函数** `check_assumption_resolution(data_rows, section_ids) → List[str]`。
- **逻辑**：`registered = section_ids["A"]["ids"]`；用现有 `_ASSUMPTION_TAG_PATS`（L516-521）抽 `假设A(\d+)`，凡 `n not in registered` 报错；假设清单 section 缺失但有标签亦报。
- **退出策略**：**section 存在时硬；首版 section 缺失时 warn**（遗留产物假设只存 Clarification_Ledger），一个周期后翻硬。
- **配置**：扩 `behavior_source.assumption_section_patterns`、`coverage_gates.assumption_resolution`。

### 5.5 项 4 — 把台账接进校验器【闭环 C3/C2/G3/G4/G8，直击 RC0】

新增 `parse_clarification_ledger(path)` 读取 `Clarification_Ledger_<id>.md`，产出 `{Q项:{状态,风险,事实摘要}, 权威事实集, 假设集}`。`verify_cases.py` 命令行增第 3 参（或自动按 REQ 同目录发现）。派生三检查：

- **5.5a 传递检查 `check_ledger_propagation`**：每条台账"已解决"Q + §权威事实要点 → 至少被 1 条用例的 G/W/T 或 TP 覆盖（关键词/字段命中）。→ 闭环 G3(格式)/G4(taskId/taskName)/G8(消费组)。
- **5.5b 待确认门禁 `check_open_questions_gate`**：凡台账"待确认"且风险 P0/P1（full 模式含 P2）→ Phase 10/13 exit=1，强制"已解决或正式转假设"方可落盘。→ 闭环 C2/Q5。
- **5.5c 一致性事实源**：把台账权威事实喂给项 5.6 的一致性检查作为对照源之一。→ 闭环 C3。
- **退出策略**：5.5a 默认 warn（首版，词表稳后升 full）；5.5b 硬（full 模式）；配置 `coverage_gates.{ledger_propagation, open_questions}`。

### 5.6 项 5 — 用例↔台账/规则一致性【闭环 C3】

- 扩 `check_behavior_source_lines`（L914 现对任何 R/TP 引用即 `continue`）：加反义词词典 `behavior_source.antonym_pairs = [[放行,丢弃],[禁止,允许],[不重试,重试],[成功,失败],[升序,降序],[启用,停用]]`；用例断言 token 与所引规则/台账事实互为反义 → 矛盾嫌疑。新软桶 `soft["behavior_consistency"]`，对照源含台账事实（5.5c）。`selfcheck.md` 检查15 增"一致性"判据。
- **验证**：SUM_005(丢弃) vs 台账 Q4(放行) → 报矛盾嫌疑。

### 5.7 项 6 — 非台账点关键词覆盖探针【闭环 G5/G6 + RC6】

- 扩 `parse_requirement_items_from_lines`：对非标题行按 `requirement_probe_keywords.categories`（10 类：可配置/重试退避/格式转换/透传字段/异步上下文/异常输入/端点可达/消费组/枚举完整性/幂等）扫描，吐 `prose:` 测点。`reverse_requirement_trace` 对 prose 项做全行扫描。新增 `keyword_coverage_probe` 追踪 + `traces["keyword_coverage"]`。默认 `coverage_gates.keyword_coverage = warn`（词表稳定后升 full）。`coverage.md` 15.2/15.3、`dedup_coverage.md` #4 同步记录 prose 分解。
- **闭环**：G5(异步上下文)/G6(脏 payload)/G7(端点可达) 等非台账点；同时收窄 RC6（契约型需求正文测点被分解为可追溯项）。

### 5.8 项 7 — 断言具体性(D4) + REQ 缺失门禁

- **D4**：扩 `check_assertions`——`IDX_THEN` 含假设标签且行为边界/异常时，要求一个**非"登记假设"**的可观测锚点。配置 `assumption_only_then_pattern`。
- **REQ 缺失**：`coverage_gates.req_trace_presence = full` 时 REQ 不可解析 → exit=1（补 v0.6.0 拘留：现 `coverage_gate_failures` L240 仅 `unc_req is not None and req_total` 才触发，REQ 缺失只打 stdout 强提示不 exit）。

### 5.9 项 8 — REQ 缺失/不可解析硬门禁（补 v0.6.0 拘留）

- 现状：`coverage_gate_failures` L240 仅 `unc_req is not None and req_total` 才触发；REQ 缺失只打 stdout 强提示（L1551-1561），不 exit。
- 改动：L262 `return fails` 前追加——`coverage_gates.req_trace_presence != "off"` 且 `unc_req is None` 且非 auto_light+auto/light 模式 → 追加 `("#4-P 需求追溯基准缺失", ...)`；同步加 `verify_summary_line` 字段。
- 退出策略：**full 模式硬**。配置 `coverage_gates.req_trace_presence = "full"`。

---

## 6. 阶段门禁前移（修复 RC3 中间阶段橡皮章）

### 6.1 `verify_cases.py --phase-gate <N>` 模式

新增 CLI 模式（保留现有 file/inmemory 模式不变）：

```
python verify_cases.py --phase-gate <N> <checkpoint_N.md> [--req REQ.md] [--ledger Ledger.md] [--artifacts state.json]
```

按阶段跑检查子集 + 消费校验 + 台账对照；`config/validation_rules.json` 增 `phase_gate_map` 声明"哪些检查归哪个阶段"，避免与 Phase 13 全量重复或遗漏。沿用 `collect_all_findings` 聚合，保证口径一致。

### 6.2 phases.py 填充 gate_checks

| 阶段 | 现状 gate_checks | 改后（runtime 强制） |
|---|---|---|
| 3 规则 | 空（模型自律） | `--phase-gate 3`：`check_rule_source`（来源标注）+ R 编号连续性 |
| 5 风险 | 空（模型自律） | `--phase-gate 5`：`risk_source_report` + P0/P1 风险均有来源 + RK 编号连续性 |
| 7 测试点 | 空 | **新增** `--phase-gate 7`：每个 P0/P1 风险→≥1 TP + TP 编号连续性（**当场抓 TP7**） |
| 8 用例 | 空（模型自律） | `--phase-gate 8`：`run_inmemory` 全量 + **引用解析/等级映射/台账传递/假设解析**（§5.2/5.3/5.4/5.5a/5.6）+ 用例 ID 连续 |
| 10 覆盖 | 空 | **新增** `--phase-gate 10`：#4-H/#5/#6 覆盖硬门 + **台账待确认门禁**（Q5 未闭环→exit=1，**当场抓 C2**）+ 台账传递（5.5a） |
| 13 写盘 | verify_md+verify_cases（已强制） | 不变；额外对照 artifacts 防落盘漂移 |
| 2/4/6/9/11/12 | 空 | 维持空（纯内存/展示），但其产物在 8/10/13 被间接校验 |

**关键转变**：用例质量与覆盖的机器兜底从"Phase 13 写盘后"前移到"Phase 8 生成时 + Phase 10 覆盖时"——生成即强制，而非先写后验。

### 6.3 消费门禁（consumption gate，Phase 8 gate 子集）

Phase 8 的 gate 增检查（由 `--phase-gate 8` 跑，对照 `state.json["artifacts"]`）：
- **引用解析**：每条用例 `关联规则` 列的 `R/RK/TP/API` 必须在 artifacts 对应清单内 → **当场抓 R26/R28**。
- **等级映射**：`用例等级` 必须能在 `artifacts["5"].levels` 找到对应风险或属合规降级。
- **台账传递**：`artifacts["ledger"].facts` 的关键事实须被至少一条用例 G/W/T 命中 → **当场抓 G3/G4/G8**。
- **假设解析**：`假设A<n>` 须在 `artifacts["ledger"].assumptions` 内。

### 6.4 有界返修（堵 silent infinite-retry）

`state.json` 增 `gate_rounds:{<phase>:n}`。`cmd_gate` auto 分支 FAIL 时 `gate_rounds[phase]+=1`；≥3 次 runtime 强制输出"Phase N 门禁连续失败 3 次，疑似系统性问题：请人工介入或 `fail --to <更早阶段>` 回退"，并在 `history` 留审计。把"模型反复原地改不过"从静默变成可见停顿。

> `confirm_rounds`（现仅 `fail` 回退时 +1，L514）与 `gate_rounds` 分工：前者记人工门审核反馈往返，后者记自动门原地返修。

### 6.5 阶段门禁总览（修复后）

```
0  exists(REQ/MANIFEST)          ─ 强制(已有)
1  confirm(澄清)                   ─ 人工(已有)
2  ─(内存)                         ─ 间接由 7/10 校验
3  phase-gate 3 (规则来源+连续)     ─ 强制(新)
4  ─(SDD 内存)                     ─ 间接由 8 校验
5  phase-gate 5 (风险来源+连续)     ─ 强制(新,原仅建议)
6  ─(策略内存)                     ─ 间接由 8 校验
7  phase-gate 7 (TP←风险+连续)     ─ 强制(新)
8  phase-gate 8 (全量+消费+一致性)  ─ 强制(新,原仅建议)
9  ─(去重内存)                     ─ 间接由 10/13 校验
10 phase-gate 10 (覆盖硬门+台账)    ─ 强制(新)
11 ─(自查内存,≤3轮)                ─ 间接由 13 校验
12 ─(展示)
13 verify_md+verify_cases          ─ 强制(已有)+artifacts防漂移
14 confirm(审核)                   ─ 人工(已有)
15 gen_excel                       ─ 强制(已有)
```

---

## 7. 状态机改动（runtime 侧）

### 7.1 `state_store.py`

- `SCHEMA_VERSION` 1 → 2。
- `new_state` 增 `artifacts:{}`、`gate_rounds:{}`。
- `load` 兼容 schema=1：自动补 `artifacts={}`、`gate_rounds={}`，不报错。
- `log_event` 不变（`history` 已有界 500 条）。

### 7.2 `phases.py`

- 各阶段增 `consumes`（§4.2）。
- Phase 3/5/7/8/10 填 `gate_checks`（§6.2）：

```python
# 节选 Phase 8
{"id":8, ...,
 "gate_checks":[
   {"kind":"phase_gate","phase":8,"label":"用例生成出口gate(引用/消费/一致性/全量)"},
 ],
 "consumes":["3","4","5","7","ledger","req"]},
```

- `_run_check`（`qamaster_runtime.py` L124）增 `phase_gate` kind：调用 `verify_cases.py --phase-gate N checkpoint_N.md --req ... --ledger ... --artifacts state.json`，按退出码判定。

### 7.3 `qamaster_runtime.py`

- `_card` 增 PRIOR_ARTIFACTS 渲染（读 `artifacts` + `consumes`，§4.3）。
- `cmd_gate` auto 分支：解析检查点 → 回填 `artifacts`、计 `gate_rounds`、≥3 次强制人工提示（§6.4）。
- `_run_check` 增 `phase_gate` kind。
- 检查点清理：Phase 13 gate PASS 后清理 `.qamaster/case-design/<req_id>/checkpoint_*.md`（纳入"临时文件清理"节）。

---

## 8. references / SKILL.md 方法论修订

| 文件 | 改动 |
|---|---|
| `references/phase0_manifest.md` | 步骤零补"沉淀阶段结束写 checkpoint_<N>.md 再 gate"机制说明；MANIFEST 不变 |
| `references/clarification.md` | 强化"待确认 Q 未闭环禁止落盘"门禁；台账权威事实→artifacts["ledger"].facts 的提取口径 |
| `references/modeling.md` | §15.7 Phase 8 出口 gate 从"模型自律 run_inmemory"升级为"runtime 强制 --phase-gate 8"；补 checkpoint_8.md 写法 |
| `references/risk.md` | Phase 5 出口 gate 升级为 runtime 强制；补 checkpoint_5.md 写法 |
| `references/coverage.md` | 15.2/15.3 补 prose 测点分解（§5.7）；§8 覆盖矩阵补"台账事实传递"维度 |
| `references/dedup_coverage.md` | #4/#5/#6 追溯补"台账传递/一致性/待确认门禁"；Phase 10 出口 gate runtime 强制 |
| `references/selfcheck.md` | 检查15 增"一致性"判据；检查4 增"不得仅登记假设无具体断言"；与 phase-gate 分工声明 |
| `references/output_write.md` | 临时文件清理节补"`.qamaster/case-design/<req_id>/checkpoint_*.md` 由 runtime 在 Phase 13 后清理"；写盘约束补"对照 artifacts 防漂移" |
| `references/review_gate.md` | 审核话术补"phase-gate 已在 3/5/7/8/10 就地强制"说明 |
| `SKILL.md` | §6 阶段列表 3/5/7/8/10 标注"runtime 强制 phase-gate"；§19 输出顺序补"沉淀阶段写 checkpoint"；交付摘要补"phase-gate 摘要"字段 |
| `CHANGELOG.md` | 新增 v0.7.0 发布说明（见 §11） |

---

## 9. config 改动（单一事实源）

`config/validation_rules.json` 新增/扩展：

```json
{
  "citation_resolution": {
    "citation_pattern": "(R|RK|TP|API|SC)(\\d+)",
    "ledger_q_pattern": "台账Q(\\d+)",
    "section_id_definitions": [...],
    "external_citation_marker": "（外部引用）|（跨需求）"
  },
  "section_contiguity": {"R":"warn","RK":"full","TP":"full","API":"full","SC":"full"},
  "phase_gate_map": {
    "3":  ["check_rule_source","check_section_id_contiguity:R"],
    "5":  ["risk_source_report","check_section_id_contiguity:RK"],
    "7":  ["testpoint_risk_linkage","check_section_id_contiguity:TP"],
    "8":  ["collect_all_findings","check_citation_resolution","check_assumption_resolution","check_ledger_propagation","check_behavior_consistency","check_section_id_contiguity:all"],
    "10": ["coverage_gate_failures","check_open_questions_gate","check_ledger_propagation"],
    "13": ["verify_md","collect_all_findings","coverage_gate_failures","check_open_questions_gate"]
  },
  "requirement_probe_keywords": {
    "categories": {"可配置":[...],"重试退避":[...],"格式转换":[...],"透传字段":[...],"异步上下文":[...],"异常输入":[...],"端点可达":[...],"消费组":[...],"枚举完整性":[...],"幂等":[...]}
  },
  "source_scope": {"field_pattern":"\\b[a-z_]{4,}\\b","whitelist":["code","status","data",...]},
  "coverage_gates": {
    "req_trace_min_ratio": 1.0,
    "interface_three_class": "full",
    "risk_p0p1": "full",
    "req_trace_presence": "full",
    "ledger_propagation": "warn",
    "open_questions": "full",
    "keyword_coverage": "warn",
    "assumption_resolution": "full"
  },
  "behavior_source": {
    "...": "现有不变",
    "antonym_pairs": [["放行","丢弃"],["禁止","允许"],["不重试","重试"],["成功","失败"],["升序","降序"],["启用","停用"]],
    "assumption_section_patterns": [...]
  },
  "assumption_only_then_pattern": "..."
}
```

---

## 10. 缺陷 → 修复映射

| 缺陷 | 闭环项 | 机制 | 阶段 |
|---|---|---|---|
| D1 R26/R28 悬空 + 台账Q悬空 | §5.2 | exit=1 | Phase 8（生成时） |
| D2 TP7 跳号 | §5.3 | exit=1(TP=full) | Phase 7（测试点建模时） |
| C3 SUM_005 vs Q4 | §5.5c + §5.6 | 台账事实源 + 反义词一致性 | Phase 8 |
| C2 Q5 待确认泄漏 | §5.5b | 待确认门禁 exit=1 | Phase 10（覆盖校验时） |
| G3 格式 / G4 taskId / G8 消费组 | §5.5a | 台账传递检查 | Phase 8/10 |
| G5 异步 / G6 脏payload / G7 端点可达 | §5.7 | 关键词探针 | Phase 10 |
| D4 空泛断言 | §5.8 | 软→selfcheck 阻断 | Phase 11 |
| RC3 跨阶段消费无强制 | §4 全节 | 制品注册表 + 契约卡注入 + 消费门禁 | 全阶段 |
| RC5 ID 无注册表 | §4.1 + §5.2 | artifacts + 反向对账 | Phase 3/5/7/8 |
| RC6 需求覆盖粒度过粗 | §5.7 | prose 测点分解 | Phase 10 |
| ~~C1/C4/D3/G9/G10~~ | — | 台账已解决/裁剪，撤回 | — |

---

## 11. 迁移路线

### Phase A（Tier 1 硬门禁，一个迭代，全 exit=1）
1. `collect_section_ids` 解析器
2. 项 1（§5.2 反向引用）+ 项 2（§5.3 连续性）+ 项 3（§5.4 假设对账）—— 均依赖 1
3. 项 8（§5.9 REQ 缺失门禁）—— 独立
4. runtime 侧 `phase_gate` kind + `gate_checks` 填充 + `gate_rounds`
5. `state_store` schema 2 + artifacts/gate_rounds + 兼容读取
6. `--phase-gate <N>` 模式 + `phase_gate_map`
7. SKILL/references 方法论同步

### Phase B（Tier 2，可与 A 部分并行）
1. 项 4（§5.5 台账接入：解析器 + 5.5a/5.5b/5.5c）—— 最高优先，直击 RC0
2. 项 5（§5.6 一致性软探针）
3. 项 6（§5.7 关键词覆盖探针）
4. 项 7（§5.8 D4 断言具体性）

### Phase C（可选·降级）
- DESIGN_*.md 正式化（phase0 落盘 + MANIFEST 增列）—— 台账已做设计文档对账，此项非必需。

### CHANGELOG v0.7.0 摘要（待写）
> **本次发布解决中间阶段橡皮章 + 跨阶段制品靠记忆两大流程控制缺口**。把 Phase 3/5/7/8/10 的出口 gate 从"模型自律 run_inmemory"升级为"runtime 强制 `verify_cases.py --phase-gate N`"；state.json 增 `artifacts` 制品注册表，契约卡注入 PRIOR_ARTIFACTS；verify_cases 增反向引用完整性/编号连续性/假设对账/台账接入（传递+待确认门禁+一致性）/关键词覆盖探针。闭合 D1/D2/C3/C2/G3-G8 的流程控制根因。schema 1→2 向后兼容。

---

## 12. 验证方法（端到端）

1. **回归基线（改动前）**：对现产物跑 `verify_cases.py <TC.md> <REQ.md>`，记 `hard_violations=0; gate_fails=0; exit 0`（证实 RC1/RC2/RC0 复现）。`runtime plan` 显示 Phase 2-12 gate_checks 空。
2. **项 1/2（Phase 7/8 gate）**：改动后构造 Phase 7 checkpoint（TP1-6,8-42）→ `--phase-gate 7` exit=1 报 TP7；Phase 8 checkpoint 含 SUM_008→R28 → `--phase-gate 8` exit=1 报 R28（不再漏到落盘）。
3. **项 4（台账接入）**：增参 `<Ledger.md>` → 5.5a 报"格式/taskId/消费组 无覆盖用例"、5.5b 报"Q5 待确认泄漏"(exit=1)、5.5c+项5 报"SUM_005 与 Q4 放行矛盾"。
4. **Phase 13 联动**：`/case-design` 重型完整重放，确认 runtime 在 Phase 3/5/7/8/10 真正 PASS/FAIL 判定（不再橡皮章），FAIL 阻断 next；`gate_rounds` ≥3 次强制人工提示。
5. **artifacts 注入**：Phase 8 契约卡含 PRIOR_ARTIFACTS（Q4 放行、taskId/taskName、消费组均注入）。
6. **兼容**：light 模式跳 3/10 仍能由 Phase 8+13 兜底通过；旧 state.json（schema 1）能兼容加载；既有合规用例集在新门禁下仍 PASS（不误伤）。
7. **脚本自测**：`scripts/test_runtime.py` 扩组：[18] phase-gate 7 抓 TP7、[19] phase-gate 8 抓 R28、[20] 台账待确认门禁抓 Q5、[21] 全覆盖合规用例集新门禁全 PASS。

---

## 13. 取舍与风险（诚实披露）

1. **检查点增加少量 Write**：沉淀阶段多 5 次小文件写（`.qamaster/case-design/<req_id>/checkpoint_*.md`）。代价是换"生成时强制"——值得，且是 runtime 临时件、Phase 13 后清理。
2. **`--phase-gate` 检查子集要维护**：`phase_gate_map` 需与 Phase 13 全量校验对齐，避免重复或遗漏。用 config 一处声明。
3. **一致性/传递仍是"高概率非保证"**：反义词词典、台账事实关键词命中属启发式；门禁强制的是"必须过"，过不了就回退/浮现，但语义终判仍归 LLM/人。
4. **契约卡变长**：PRIOR_ARTIFACTS 增加卡片体积，但换来"不靠记忆"——只注入 ID 范围 + 待确认项 + 关键事实摘要控制长度。
5. **C2 待确认门禁能阻漏落盘，但不替人决策**："该填 3 还是 5"仍需人工确认——门禁强制浮现，不替人决策。
6. **G5/G6/G7 关键词探针仅匹配已配置关键词**：异形表述（"支持热刷新"）漏配即漏检，需按域维护 domain_config。
7. **C3 语义矛盾**：反义词词典抓结构对（放行↔丢弃），漏同义（丢弃↔不予处理）；台账事实源提升命中面，但终判归 LLM。

---

## 14. 与既有约束的相容性核对

| 既有约束 | 本设计是否破坏 | 说明 |
|---|---|---|
| TestCases.md 单文件一次 Write（禁 Edit 增量） | 否 | 检查点是 `.qamaster/case-design/<req_id>/checkpoint_*.md`，非 TestCases.md |
| state.json 由 state_store 单写 | 否 | 仍由 runtime 在 gate 时写，模型不碰 |
| 深度裁剪 heavy/medium/light | 否 | light 跳 3/10，由 Phase 8+13 兜底（与现行一致） |
| 降级协议情形A/B | 否 | 情形A 退回模型自律时 phase-gate 脚本仍可由模型经 Bash 自跑；情形B 仍禁止落盘 |
| v0.6.0 三覆盖硬门 | 否 | 本设计在 Phase 10 就地强制，Phase 13 仍最终全量回读 |
| v0.4.0 run_inmemory keystone | 否 | `--phase-gate 8` 复用 `collect_all_findings`，口径一致 |
| 回归安全（字节级） | 部分 | 文件入口 `verify_cases.py <file>` stdout/退出码不变；新增 `--phase-gate` 模式为独立入口 |

---

## 15. 附录：关键函数签名（供实施参考）

```python
# verify_cases.py 新增
def collect_section_ids(lines) -> dict: ...
def check_citation_resolution(data_rows, section_ids) -> list: ...
def check_section_id_contiguity(section_ids) -> list: ...
def check_assumption_resolution(data_rows, section_ids) -> list: ...
def parse_clarification_ledger(path) -> dict: ...
def check_ledger_propagation(data_rows, ledger, req_lines) -> list: ...   # 5.5a
def check_open_questions_gate(ledger, run_mode) -> list: ...             # 5.5b
def check_behavior_consistency(data_rows, lines, ledger) -> list: ...    # 5.6
def keyword_coverage_probe(data_rows, req_lines, ledger) -> dict: ...    # 5.7

# verify_cases.py 新 CLI
# python verify_cases.py --phase-gate <N> <checkpoint.md> [--req ..] [--ledger ..] [--artifacts state.json]

# state_store.py
SCHEMA_VERSION = 2
def new_state(...) -> dict:  # 增 artifacts={}, gate_rounds={}
def load(path):  # schema=1 兼容补字段

# phases.py
# 各阶段增 "consumes":[...]
# Phase 3/5/7/8/10 墫 gate_checks: [{"kind":"phase_gate","phase":N,...}]

# qamaster_runtime.py
def _card(st, phase, extra=""):  # 增 PRIOR_ARTIFACTS 渲染
def _run_check(chk, st):         # 增 phase_gate kind
# cmd_gate auto 分支：回填 artifacts、计 gate_rounds、≥3 次强制人工提示
```

---

## 16. 结束语

本设计不改写 Runtime 总体重构哲学，而是**让 runtime 兑现自己承诺却没做到的两件事**——携带上游制品（§4）、gate 中间阶段（§6）。配合 verify_cases 检查项加固（§5），形成"检查齐全 + 流程强制 + 制品可传"的完整闭环，从流程控制侧根除"台账不传导、引用悬空、编号跳号、矛盾漏网、覆盖缺口、待确认泄漏"六类问题的复发。

核心原则不变：**Runtime 控制流程，模型执行任务，任何模型不可绕过。** 本设计只是把"不可绕过"从首尾（0/13/15）扩展到中间 3/5/7/8/10。
