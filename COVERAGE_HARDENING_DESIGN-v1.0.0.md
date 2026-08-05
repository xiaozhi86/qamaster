# 覆盖率硬门与设计文档追溯加固设计 v1.0.0

> **状态**：已实施（Phase A·P0 四处 + Phase B·P1 五处落地）
> **日期**：2026-08-05
> **作者**：xiaozhi
> **范围**：`skills/case-design`（SKILL.md / config / references / scripts）+ `runtime/`（phases.py）
> **与既有设计的关系**：本文是 `PHASE_GATE_DESIGN.md`（v0.7.0·门禁前移与制品传递）的**补强**，不推翻 v0.7.0。v0.7.0 闭环了"引用悬空/编号跳号/台账传递/待确认泄漏"；本文闭环 v0.7.0 未覆盖的三个缺口：**测试点级覆盖无硬门、设计文档测试要点非正式追溯源、critique 不扫安全/脱敏盲区**。

---

## 0. 一句话目标

让 qamaster 的覆盖校验从"**需求条目级（#4）+ 风险级（RK）**"两道硬门，扩展为"**需求条目 + 测试点 + 风险 + 安全**"四道硬门，并把**设计文档**从"靠澄清台账间接捕获"升级为**正式追溯源**，从机制上预防本次事故（36 个测试点只覆盖 30 个用例、SpEL/Apollo/MDC/脱敏等设计文档明列测试要点漏测、接口 2/3 契约类测试点因未启用契约驱动分支而失守）。

---

## 1. 背景

### 1.1 事故复盘

对 `case-design-out/TestCases_电销通话AI总结.md`（30 条用例，Phase 13 全部 exit=0 通过）做覆盖性审查发现：

- **36→30 压缩静默通过**：Phase 7 建模 36 个测试点，Phase 8 生成 30 条用例，6 个测试点未被任何用例引用。`verify_cases.py` 的 `testpoint_coverage()` 函数（L1197-1219）**只返回软提示不入 `coverage_gate_failures`** → `exit=0` 放行。
- **设计文档测试要点大面积漏测**：设计文档 A §8（11 条测试要点）覆盖 82%，设计文档 B §6（24 条测试要点）只覆盖 54%。SpEL 多条件扩展、SpEL 解析失败容错、Apollo 热更新、MDC/租户上下文跨线程池、线程池拒绝策略、质检字段透传（`_id`→`id`）、字段命名转换（snake↔camel）、内层 map 结构透传、字段缺失三态兼容、请求 JSON root=Map、Dubbo 双集群注册、HTTP 端点映射等**设计文档自带的测试要点**未被纳入覆盖矩阵。
- **P0 安全漏测**：通话内容含客户敏感信息（手机号/身份证/财务），AI 输出 summary/labels/evidence 可能含原文 → 敏感信息脱敏（P0 级隐私泄露合规风险）**0 个测试点**覆盖。
- **接口 2/3 契约类失守**：本次需求被判定为 requirement 驱动（无 Swagger），契约驱动分支未启用 → `#6-H` 硬门完全不生效（`api_total=0` 跳过），接口 2/3 的契约类测试点（必填缺失/类型错传/出参契约/字段命名转换/内层 map/JSON root）零强制覆盖。

### 1.2 三层根因

| 层 | 根因 | 机制后果 |
|---|---|---|
| **机制层** | 框架事实来源通道里**只有 REQ 需求文档**，设计文档不是正式追溯源（§5 输入协议无【设计文档】字段；#4/#5 只追 REQ；Phase 4 SDD 事实来源只指 §5【技术实现摘要】） | 设计文档自带测试要点从 Phase 2 起就不在覆盖矩阵，一路失守到 Phase 11 |
| **校验层** | `coverage_gates` 硬门清单只有 `req_trace_min_ratio` / `interface_three_class` / `risk_p0p1` 三项 + `req_trace_presence`；**没有 `testpoint_coverage` 硬门** | 36→30 压缩静默通过；TP 漏测脚本只打 stdout 软提示，exit=0 |
| **盲区层** | `risk.md` §5 critique 高发漏标方向清单（资金/并发/状态机/权限/缓存·MQ/时间/历史缺陷）**不含"安全/脱敏"**；`selfcheck.md` 检查 14 对抗生成五类盲区亦不含安全 | P0 安全漏标无人发现 |

### 1.3 与 v0.7.0 的边界

`PHASE_GATE_DESIGN.md`（v0.7.0）已落地的修复（`citation_resolution` / `section_contiguity` / `phase_gate_map` / `requirement_probe_keywords` / `ledger_propagation` / `open_questions` / `assumption_resolution`）主要闭环**引用悬空 / 编号跳号 / 台账传递 / 待确认泄漏**，已在 `validation_rules.json` + `phases.py` + `qamaster_runtime.py` 落地。v0.7.0 的 `requirement_probe_keywords` 是 `warn` 软门，且关键词分类（可配置/重试退避/格式转换/透传字段/异步上下文/异常输入/端点可达/消费组/枚举完整性/幂等）**不含"脱敏"深度项**，也不强制设计文档测试要点追溯。本文补强 v0.7.0 未覆盖的三个缺口，不冲突。

---

## 2. 设计原则

1. **补硬门不破坏回归**：新增硬门在既有合规用例集上须 PASS（不误伤）；仅"TP 未覆盖/安全未覆盖/设计文档测试要点未追溯"的产出物被拦下。
2. **设计文档是正式追溯源**：把 DESIGN 文档从"靠台账间接捕获"升级为落盘产物 + 追溯基准，与 REQ 并列。
3. **口径集中于 config**：所有新检查的枚举/正则/阈值集中于 `config/validation_rules.json`，`verify_cases.py --phase-gate N` 与 Phase 13 全量校验共用 `collect_all_findings`，保证口径一致（沿用 v0.6.0 keystone 回归安全原则）。
4. **契约驱动分支触发条件放宽**：从"只认 Swagger/OpenAPI"放宽到"设计文档含接口描述也触发"，避免 requirement 驱动下接口契约类测试点完全失守。
5. **critique 补安全盲区**：risk critique + selfcheck 检查 14 双处补"安全/脱敏"专项。

---

## 3. 缺陷 → 修复映射（总览）

| 缺陷 | 闭环项 | 机制 | 阶段 | 优先级 |
|---|---|---|---|---|
| 36→30 压缩（6 TP 未覆盖静默通过） | §5.1 `#7-H` TP 追溯硬门 | `coverage_gates.testpoint_coverage=full` + `verify_cases.py::coverage_gate_failures` 加 TP 分支 | Phase 7/8/10/13 | P0 |
| 设计文档测试要点漏测（SpEL/Apollo/MDC/字段透传等） | §5.2【设计文档】输入通道 + DESIGN 落盘 + §5.3 `#8-H` 设计文档测试要点追溯 | SKILL.md §5 + phase0_manifest.md 步骤零/六 + coverage.md 8.11 | Phase 0/2/7/10 | P0 |
| 接口 2/3 契约类失守（无 Swagger → #6-H 不生效） | §5.4 契约驱动分支触发条件放宽 | phase0_manifest.md 步骤六 + SKILL.md §159 | Phase 0 | P0 |
| P0 安全/脱敏漏标 | §5.5 critique 补安全盲区 + §5.6 `safety_coverage` 硬门 | risk.md §5 + selfcheck.md 检查 14 + validation_rules.json | Phase 5/11/13 | P0 |
| #5 来源不含设计文档（行为来源仅三选一） | §5.7 #5 升级四选一 | dedup_coverage.md §17 #5 + validation_rules.json | Phase 10/13 | P1 |
| selfcheck 检查 3 是维度级非 TP 级 | §5.8 检查 3 升 TP 级 + 新增设计文档测试要点覆盖率检查 | selfcheck.md | Phase 11 | P1 |

---

## 4. 总体架构

```
Phase0 ─gate─> Phase1(确认) ─gate─> Phase2 ─gate─> Phase3 ─gate─> Phase4 ─gate─>
   落盘 REQ + DESIGN（新）          覆盖矩阵含 8.11 设计文档测试要点（新）
   契约驱动分支触发放宽（新）        Phase 0 探测设计文档含接口描述也启用（新）
... Phase5 ─gate─> Phase7 ─gate─> Phase8 ─gate─> Phase10 ─gate─> Phase13 ─gate─>
   critique 补安全（新）  #7-H TP追溯（新）  #7-H+#8-H+#6-H+安全硬门（新）
```

新增四道覆盖硬门（`coverage_gates`）：

| 硬门 | 校验对象 | 阈值 | 阶段 |
|---|---|---|---|
| `#4-H` 需求追溯（既有） | REQ 条目被用例引用比例 | ≥1.0 | Phase 10/13 |
| `#7-H` 测试点追溯（**新**） | TP 清单每条被用例引用比例 | ≥1.0 | Phase 7/8/10/13 |
| `#8-H` 设计文档测试要点追溯（**新**） | DESIGN §测试要点每条被用例覆盖 | ≥1.0 | Phase 10/13 |
| `#6-H` 变更接口三类（既有，触发放宽） | 变更接口契约/规则/场景齐全 | full | Phase 10/13 |
| RK P0/P1 风险（既有） | P0/P1 风险被用例引用 | full | Phase 10/13 |
| `safety_coverage`（**新**） | 涉敏感数据时安全类用例数 >0 | full | Phase 11/13 |

---

## 5. 详细设计

### 5.1 项 1 — `#7-H` 反向测试点追溯硬门（闭环 36→30 压缩）

> **根因**：`verify_cases.py` 已有 `testpoint_coverage()` 函数（L1197-1219）解析"测试点清单"section，但只返回 `(uncovered_list, total)` 软提示，不入 `coverage_gate_failures`（L221-276），不触发 exit=1。Phase 8 出口 gate 也不判覆盖硬门（L2228 只在 Phase 10/13 判）。

#### 5.1.1 `config/validation_rules.json`

`coverage_gates` 新增：

```json
"coverage_gates": {
  "req_trace_min_ratio": 1.0,
  "tp_trace_min_ratio": 1.0,                    // 新增：#7-H 测试点追溯比例
  "design_doc_trace_min_ratio": 1.0,            // 新增：#8-H 设计文档测试要点追溯比例（§5.3）
  "interface_three_class": "full",
  "risk_p0p1": "full",
  "req_trace_presence": "full",
  "testpoint_coverage": "full",                 // 新增：TP 覆盖硬门（full=exit=1）
  "design_doc_testpoints_trace": "full",        // 新增：设计文档测试要点追溯硬门
  "safety_coverage": "full",                    // 新增：安全覆盖硬门（§5.6）
  "ledger_propagation": "warn",
  "open_questions": "full",
  "keyword_coverage": "warn",
  "assumption_resolution": "full"
}
```

#### 5.1.2 `scripts/verify_cases.py`

- `COVERAGE_GATES` dict（L211-218）新增：
  ```python
  "testpoint_coverage": _gate_mode(_CG.get("testpoint_coverage")),
  "design_doc_testpoints_trace": _gate_mode(_CG.get("design_doc_testpoints_trace")),
  "safety_coverage": _gate_mode(_CG.get("safety_coverage")),
  ```
- `coverage_gate_failures()`（L221-276）新增 TP 覆盖分支：
  ```python
  # #7-H 测试点追溯硬门
  if gate_mode("testpoint_coverage") != "off":
      tp_uncovered, tp_total = testpoint_coverage(data_rows, section_ids)  # 复用既有函数
      if tp_total > 0 and tp_uncovered:
          ratio = 1 - len(tp_uncovered) / tp_total
          if ratio < _CG.get("tp_trace_min_ratio", 1.0):
              fails.append(("#7-H 测试点未全覆盖", f"TP {tp_total} 条、未被用例引用 {len(tp_uncovered)} 条：{tp_uncovered}"))
  ```
- Phase 8 gate（L2228 `if a.phase in (10, 13)`）扩展为 `if a.phase in (8, 10, 13)`，让写前 gate 也拦 TP 覆盖（与 v0.7.0 phase_gate_map Phase 8 一致）。

#### 5.1.3 `references/dedup_coverage.md` §17

- #4 反向需求追溯后新增 **#7 反向测试点追溯**：
  > 测试点清单每条 `TP<序号>` 须被用例"关联规则"列引用。未引用比例 < `coverage_gates.tp_trace_min_ratio`（默认 1.0）→ exit=1。与运行模式正交语义同 #4-H。
- §18 停止条件"机器可判前提"增 `#7-H`。

#### 5.1.4 `config/validation_rules.json` phase_gate_map

```json
"7":  ["testpoint_risk_linkage", "check_section_id_contiguity:TP"],
"8":  ["collect_all_findings", "check_citation_resolution", "check_assumption_resolution", "check_ledger_propagation", "check_behavior_consistency", "check_section_id_contiguity:all", "testpoint_coverage"],
"10": ["coverage_gate_failures", "check_open_questions_gate", "check_ledger_propagation", "testpoint_coverage", "design_doc_testpoints_trace"],
"13": ["verify_md", "collect_all_findings", "coverage_gate_failures", "check_open_questions_gate", "testpoint_coverage", "design_doc_testpoints_trace", "safety_coverage"]
```

---

### 5.2 项 2 —【设计文档】输入通道 + DESIGN 落盘（闭环设计文档测试要点漏测根因）

#### 5.2.1 `SKILL.md` §5 输入协议

新增【设计文档】可选通道（位于【接口契约文档】之后）：

```
【设计文档】（可选·设计文档测试要点强制覆盖）
<<<设计文档开始>>>
开发/架构设计文档（Markdown）。含技术方案、调用链路、字段映射、错误处理、测试要点章节。
提供时：
- 第0阶段把"测试要点"章节提取落盘为 case-design-out/DESIGN_<需求标识>.md（#8 反向设计文档测试要点追溯基准）
- 第2阶段覆盖矩阵新增"8.11 设计文档测试要点覆盖"维度
- 第7阶段测试点建模须引用设计文档测试要点
未提供时退回当前行为，不阻断。
<<<设计文档结束>>>
```

#### 5.2.2 `references/phase0_manifest.md`

- **步骤零**（需求文档落盘）扩展：探测到【设计文档】时，提取其"测试要点/测试点"章节落盘为 `case-design-out/DESIGN_<需求标识>.md`（保留原始 `##`/`###` 分节，使可解析）。
- **索引文件格式**表头新增"设计文档"列：`| 需求标识 | 需求名称 | 需求文档 | 设计文档 | 台账文件 | ... |`
- **文件命名规范**表新增：`设计文档 | DESIGN_<需求标识>.md`
- **里程碑更新表**新增：第0阶段落盘 DESIGN 文件时更新索引"设计文档"列。

#### 5.2.3 `runtime/phases.py` Phase 0

```python
"gate_checks": [
    {"kind": "exists_any", "patterns": ["case-design-out/REQ_*.md"], "label": "需求文档已落盘"},
    {"kind": "exists", "path": "case-design-out/MANIFEST.md", "label": "索引文件存在"},
    # 新增：设计文档存在时才校验（向后兼容）
    {"kind": "exists_any", "patterns": ["case-design-out/DESIGN_*.md"], "label": "设计文档已落盘（如有）", "optional": True},
],
"produces": ["case-design-out/REQ_<需求标识>.md", "case-design-out/DESIGN_<需求标识>.md（如有）", "case-design-out/MANIFEST.md"],
```

> `optional` 字段为新增 gate kind 修饰符：探测到【设计文档】输入但未落盘时 FAIL；无【设计文档】输入时 SKIP。

---

### 5.3 项 3 — `#8-H` 反向设计文档测试要点追溯（闭环 SpEL/Apollo/MDC 漏测）

#### 5.3.1 `scripts/verify_cases.py` 新增 `check_design_doc_testpoints`

```python
def check_design_doc_testpoints(data_rows, design_lines, section_ids) -> list:
    """#8-H 反向设计文档测试要点追溯。
    解析 DESIGN 文档'测试要点'章节每条，查用例 G/W/T 或关联规则是否覆盖。
    design_lines 为空（无 DESIGN 文件）时返回空列表（SKIP，不报错）。
    """
    if not design_lines:
        return []
    # 解析"## 测试要点" / "### 测试要点" / "## 6. 测试要点" 章节
    items = parse_design_testpoints(design_lines)  # 新解析器，按编号/标题切分
    uncovered = []
    for item in items:
        if not _cases_cover(data_rows, item):  # 用例 G/W/T 或关联规则命中
            uncovered.append(item)
    return uncovered
```

并入 `coverage_gate_failures`：

```python
# #8-H 设计文档测试要点追溯硬门
if gate_mode("design_doc_testpoints_trace") != "off" and design_lines:
    dd_uncovered = check_design_doc_testpoints(data_rows, design_lines, section_ids)
    if dd_uncovered:
        fails.append(("#8-H 设计文档测试要点未全覆盖", f"DESIGN 测试要点 {len(items)} 条、未覆盖 {len(dd_uncovered)} 条：{dd_uncovered}"))
```

#### 5.3.2 `references/coverage.md`

- §8 新增 **8.11 设计文档测试要点覆盖**：
  > 当第0阶段落盘了 `DESIGN_<需求标识>.md` 时，其"测试要点"章节每条须被用例覆盖（用例 G/W/T 或关联规则命中）。未覆盖比例 < `coverage_gates.design_doc_trace_min_ratio`（默认 1.0）→ exit=1。
- §15.2 测试需求分析维度新增"设计文档测试要点"维度。
- §15.3 测试点提取维度新增"设计文档测试要点"维度。

#### 5.3.3 `references/dedup_coverage.md` §17

- #7 反向测试点追溯后新增 **#8 反向设计文档测试要点追溯**（条款镜像 #4/#7）。

---

### 5.4 项 4 — 契约驱动分支触发条件放宽（闭环接口 2/3 契约类失守）

#### 5.4.1 `references/phase0_manifest.md` 步骤六

现状（L93-106）只认"Swagger/OpenAPI JSON-YAML、`/api/` 路径、HTTP 方法表"为契约驱动信号。改为：

| 输入形态 | 判定 | 处理 |
| -- | -- | -- |
| 需求文档 + 接口文档（Swagger/OpenAPI） | 启用契约驱动分支 | 既有 |
| 需求文档 + 设计文档含接口描述（**新**） | 启用契约驱动分支（设计文档驱动） | 第4阶段从设计文档提取接口契约模型+变更影响清单；变更接口按 methods.md 统一接口测试矩阵设计契约/规则/场景三类用例 |
| 需求文档（无接口无设计文档接口描述） | 不启用 | 退回纯需求驱动 |

**判定信号**（设计文档含接口描述）：设计文档中出现接口名/facade 名/方法签名/入参出参 JSON/错误码表/`@Service`/`@RestfulApi`/Dubbo 方法等任一信号。

#### 5.4.2 `SKILL.md` §159

"接口契约文档"可选通道流向说明改为：
> 提供时启用契约驱动分支；**设计文档含接口描述时也强制启用**（Phase 0 探测）；未提供且设计文档无接口描述时退回自然语言兜底，不阻断。

#### 5.4.3 `references/modeling.md` 接口契约模型触发条件

同步放宽：触发信号增"设计文档含接口描述"。

---

### 5.5 项 5 — critique 补安全/脱敏盲区（闭环 P0 安全漏标）

#### 5.5.1 `references/risk.md` §5 critique 高发漏标方向

现状清单：资金/数值、并发/幂等、状态机、权限、缓存·MQ 一致性、时间边界、历史缺陷。新增：

- **安全/脱敏（新）**：敏感字段脱敏（手机号/身份证/银行卡/财务）、AI 输出含原文敏感信息、SpEL 注入、配置热更新致参数泄露、日志/MDC/链路上下文丢失、密钥轮转、越权数据可见性、未授权调用（verifyAuth=false 暴露）

#### 5.5.2 `references/selfcheck.md` 检查 14 对抗生成五类盲区

现状五类：边界组合遗漏 / 异常子类未覆盖 / 状态机非法流转 / 并发竞态 / 界面结构遗漏。新增第六类：

- **安全风险遗漏（新）**：敏感信息脱敏、越权、注入、未授权调用、密钥泄露

#### 5.5.3 `references/risk.md` P0 列表

P0 列表"安全漏洞"后显式补"敏感信息脱敏"。

---

### 5.6 项 6 — `safety_coverage` 安全覆盖硬门（闭环安全类用例缺失）

#### 5.6.1 `scripts/verify_cases.py` 新增 `safety_coverage_gate`

```python
def safety_coverage_gate(data_rows, req_lines, design_lines) -> list:
    """涉敏感数据时安全类用例数 >0 硬门。
    触发条件：REQ/DESIGN 含敏感信号（手机号/身份证/银行卡/财务/脱敏/敏感信息/verifyAuth=false）。
    满足触发条件且安全类用例数==0 → exit=1。
    """
    if not _involves_sensitive_data(req_lines, design_lines):
        return []  # 不涉敏感数据，SKIP
    safety_cases = [r for r in data_rows if r[IDX_TYPE] == "安全"]
    if not safety_cases:
        return ["#S-H 涉敏感数据但无安全类用例覆盖"]
    return []
```

并入 `coverage_gate_failures`，Phase 11/13 判定。

#### 5.6.2 `config/validation_rules.json`

```json
"safety_coverage": "full",
"sensitive_signals": ["手机号", "身份证", "银行卡", "财务", "脱敏", "敏感信息", "verifyAuth", "token", "密码", "手机号", "custNo"]
```

---

### 5.7 项 7 — `#5` 行为来源三选一升级四选一（闭环设计文档行为无来源）

#### 5.7.1 `references/dedup_coverage.md` §17 #5

来源三选一 → 四选一，新增 (d)：

> (d) 行为 token 出现在设计文档（`DESIGN_<需求标识>.md`，含测试要点/字段映射/错误处理章节）

#### 5.7.2 `config/validation_rules.json` behavior_source

`citation_pattern` 增设计文档 token 核对；`check_behavior_source_lines` 增设计文档作为对照源。

---

### 5.8 项 8 — selfcheck 检查升级（补强项）

#### 5.8.1 `references/selfcheck.md` 检查 3

"测试点覆盖"口径从维度级（主流程/分支/异常/状态流转/权限/数据一致性）升级为 **TP 级**（每个 TP 须 ≥1 用例引用），并新增"契约类/安全类"测试点维度。

#### 5.8.2 `references/selfcheck.md` 新增检查项

新增"设计文档测试要点覆盖率"检查：DESIGN §测试要点每条须被覆盖（与 #8-H 呼应，selfcheck 是 LLM 自查层，#8-H 是机器兜底层）。

#### 5.8.3 `references/selfcheck.md` 检查 8

P0 列表"支付/资金/权限/状态流转/数据一致性"后补"安全漏洞/敏感信息脱敏"。

---

## 6. 改动文件清单（按优先级）

### Phase A（P0·根因修复·4 处）

| 文件 | 改动 | 闭环 |
|---|---|---|
| `skills/case-design/config/validation_rules.json` | `coverage_gates` 加 `testpoint_coverage`/`design_doc_testpoints_trace`/`safety_coverage`/`tp_trace_min_ratio`/`design_doc_trace_min_ratio`；`phase_gate_map` Phase 8/10/13 加 `testpoint_coverage`/`design_doc_testpoints_trace`/`safety_coverage` | 36→30、安全、设计文档要点 |
| `skills/case-design/scripts/verify_cases.py` | `coverage_gate_failures` 加 TP/设计文档/安全三分支；`COVERAGE_GATES` dict 加三项；Phase 8 gate 加覆盖硬门判定；新增 `check_design_doc_testpoints`/`safety_coverage_gate` 函数 | 36→30、安全、设计文档要点 |
| `skills/case-design/SKILL.md` | §5 新增【设计文档】输入通道；§159 契约驱动触发放宽 | 设计文档要点、接口契约类 |
| `skills/case-design/references/phase0_manifest.md` | 步骤零落盘 DESIGN + 索引增列；步骤六契约驱动触发条件放宽 | 设计文档要点、接口契约类 |

### Phase B（P1·机制补强·5 处）

| 文件 | 改动 |
|---|---|
| `skills/case-design/references/dedup_coverage.md` | §17 新增 #7（TP 追溯）+ #8（设计文档测试要点追溯）；#5 升级四选一；§18 停止条件机器前提加 #7-H |
| `skills/case-design/references/coverage.md` | §8 新增 8.11 设计文档测试要点覆盖；§15.2/15.3 维度列表加"设计文档测试要点" |
| `skills/case-design/references/risk.md` | §5 critique 高发漏标方向加"安全/脱敏"；P0 列表补"敏感信息脱敏" |
| `skills/case-design/references/selfcheck.md` | 检查 3 升 TP 级 + 加契约/安全维度；检查 8 P0 加安全；检查 14 盲区加"安全风险遗漏"；新增"设计文档测试要点覆盖率"检查项 |
| `skills/case-design/references/modeling.md` | 接口契约模型触发条件放宽（设计文档含接口描述也触发） |

### Phase C（runtime 同步·2 处）

| 文件 | 改动 |
|---|---|
| `runtime/phases.py` | Phase 0 gate_checks 加 DESIGN 存在性校验（optional）；phase_gate_map 已在 config 声明，phases.py 无需重复 |
| `skills/case-design/CHANGELOG.md` | 新增 v0.8.0 发布说明 |

---

## 7. 迁移路线

### Phase A（P0，一个迭代，全 exit=1）

1. `validation_rules.json` `coverage_gates` 加三项硬门 + 两项比例阈值
2. `verify_cases.py` `coverage_gate_failures` 加 TP/设计文档/安全三分支 + 新增 `check_design_doc_testpoints`/`safety_coverage_gate`
3. `SKILL.md` §5 加【设计文档】通道 + §159 契约驱动触发放宽
4. `phase0_manifest.md` 步骤零/六同步
5. 端到端验证（§8）

### Phase B（P1，可与 A 部分并行）

1. `dedup_coverage.md` 加 #7/#8 + #5 升四选一
2. `coverage.md` 加 8.11
3. `risk.md` critique 补安全
4. `selfcheck.md` 检查 3/8/14 升级
5. `modeling.md` 契约触发放宽

### Phase C（runtime 同步）

- `phases.py` Phase 0 加 DESIGN gate（optional kind）
- `CHANGELOG.md` v0.8.0 摘要

---

## 8. 验证方法（端到端）

1. **回归基线（改动前）**：对现产物跑 `verify_cases.py --phase-gate 7 checkpoint_7.md`，确认 `testpoint_coverage` 报 6 个 TP 未引用（TP9/TP31-35 等）→ 证实新门禁抓得到缺口。
2. **设计文档追溯**：落盘 `DESIGN_电销通话AI总结.md`（含设计 A §8 / 设计 B §6 测试要点章节）→ 跑 `#8-H` → 报"设计 B §6 测试点 2/9/10/11/12/19/20/21 未覆盖"。
3. **安全 critique**：Phase 5 跑 critique → 应发现"敏感信息脱敏"漏标并补入 RK 清单。
4. **契约驱动触发放宽**：Phase 0 探测设计文档含接口描述（facade/方法签名）→ 启用契约驱动分支 → `#6-H` 生效 → 报接口 2/3 契约类测试点缺失。
5. **Phase 13 联动**：`/case-design` 重型完整重放，确认 Phase 7/8/10 gate 真正 PASS/FAIL 判定，FAIL 阻断 next。
6. **不误伤**：既有合规用例集（无 DESIGN 文件）在新门禁下仍 PASS（`design_doc_testpoints_trace` SKIP，`testpoint_coverage` 在 TP 全覆盖时 PASS）。
7. **脚本自测**：`scripts/test_runtime.py` 扩组：[22] phase-gate 7 抓 TP 未覆盖、[23] #8-H 抓设计文档测试要点未覆盖、[24] safety_coverage 抓安全类缺失、[25] 契约驱动触发放宽后 #6-H 生效。

---

## 9. 取舍与风险（诚实披露）

1. **DESIGN 文件格式依赖可解析**：设计文档测试要点章节须有 `##`/`###` 标题或编号才可被 `parse_design_testpoints` 解析。纯散文设计文档会退化为 `#8` SKIP（与 #4 显式强提示机制一致，打 stdout 提示不阻断）。
2. **`#8-H` 是关键词命中非语义保证**：用例 G/W/T 或关联规则命中设计文档测试要点靠关键词/字段匹配，异形表述漏配即漏检。需按域维护 `domain_config.json` 关键词。
3. **`safety_coverage` 触发条件是关键词探测**：`sensitive_signals` 词表漏配即漏触发。建议词表稳定后升 `full`，首版可 `warn`。
4. **契约驱动分支触发放宽可能过度启用**：设计文档含任何接口描述即启用，可能导致简单接口也走全量契约三类。缓解：methods.md 三类收敛规则（变更接口少时走轻型契约分支）。
5. **critique 补安全仍靠 LLM 主观**：机器 gate（`safety_coverage`）只能查"安全类用例数 >0"，查不出"安全断言是否充分"。终判归 LLM/人。
6. **DESIGN 落盘增加 Phase 0 工作量**：但换来设计文档测试要点的强制追溯，值得。

---

## 10. 与既有约束的相容性核对

| 既有约束 | 本设计是否破坏 | 说明 |
|---|---|---|
| TestCases.md 单文件一次 Write（禁 Edit 增量） | 否 | 本设计不动 TestCases.md 写盘机制 |
| state.json 由 state_store 单写 | 否 | 本设计不动 state.json schema（v0.7.0 已加 artifacts） |
| 深度裁剪 heavy/medium/light | 否 | light 跳 3/10，由 Phase 8+13 兜底（与现行一致）；新硬门在 Phase 8/13 仍判 |
| v0.6.0 三覆盖硬门 | 否 | 本设计扩展为六硬门，既有三门不变 |
| v0.7.0 phase_gate_map | 否 | 本设计在 phase_gate_map 加检查子项，复用 collect_all_findings |
| 回归安全（字节级） | 部分 | `verify_cases.py <file>` stdout/退出码在既有合规集上不变；新增硬门仅在"TP 未覆盖/安全缺失/设计文档要点未追溯"时 exit=1 |

---

## 11. CHANGELOG v0.8.0 摘要（待写）

> **本次发布解决覆盖率校验维度不足 + 设计文档非正式追溯源两大缺口**。`coverage_gates` 从三硬门扩展为六硬门（新增 `#7-H` 测试点追溯、`#8-H` 设计文档测试要点追溯、`safety_coverage` 安全覆盖）；新增【设计文档】输入通道 + DESIGN 文件落盘，使设计文档测试要点成为正式追溯源；契约驱动分支触发条件从"只认 Swagger"放宽到"设计文档含接口描述也触发"，闭合 requirement 驱动下接口契约类测试点失守；risk critique + selfcheck 检查 14 双处补"安全/脱敏"盲区。闭合本次事故的 36→30 压缩、SpEL/Apollo/MDC/脱敏漏测、接口 2/3 契约类失守三大缺口。

---

## 12. 结束语

本设计不改写 v0.7.0 的门禁前移与制品传递哲学，而是**补强覆盖校验的维度**——从"需求条目 + 风险"两道硬门扩展为"需求条目 + 测试点 + 设计文档测试要点 + 安全"四道硬门，并把设计文档从"靠台账间接捕获"升级为正式追溯源。核心原则不变：**Runtime 控制流程，模型执行任务，任何模型不可绕过**。本设计把"不可绕过"的覆盖校验从"需求/风险"两层扩展到"需求/测试点/设计文档/安全"四层。