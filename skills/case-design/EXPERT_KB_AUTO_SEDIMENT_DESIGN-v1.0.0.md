# 专家方法论自动识别·提炼·沉淀设计 v1.0.0

> **状态**：待评审（未实施）
> **日期**：2026-08-18
> **作者**：xiaozhi
> **范围**：`runtime/qamaster_runtime.py` + `runtime/kb_store.py` + `skills/case-design/{SKILL.md, references/expert_kb.md, CHANGELOG.md}` + `scripts/test_runtime.py`
> **与既有设计的关系**：本文是 `KB_expert.md`（v0.11.3 专家方法论库）在**沉淀侧**的进化补强，不推翻 v0.11.3 的三门注入/指纹去重/FileLock 独占维护。v0.11.3 闭环了"专家库能存能注入"；本文闭环 v0.11.3 留下的"沉淀侧仍靠人肉"缺口——**自动识别可抽象反馈 + 自动提炼落 draft + occ≥3 自动生效 + 一键背书**，让"用户操作简单"从愿景落到机制。

---

## 0. 一句话目标

让专家方法论的沉淀从「模型靠 `_abstraction_hint`/`_methodology_capture_hint` **软提醒**、人肉跑 `kb add-expert` + `kb endorse`」升级为「**Runtime 确定性分类 → 命中即强制提炼 → 指纹去重累积 occ → occ≥3 自动生效 / occ<3 一键背书**」。用户**只在两条路上花一次动作**：反馈问题（本来就做）+ 回一个「通过」（只对全新方法论）；多数方法论被 ≥3 个独立需求验证后**自动转正，零人工**。

---

## 1. 背景

### 1.1 现状基线（精确到代码行）

| 机制 | 位置 | 现状 |
|---|---|---|
| 经验自动捕获 `_maybe_capture_lesson` | `runtime/qamaster_runtime.py` L581-611 | **硬编码只写 `KB_lessons.md`**（L604-605）；expert 零自动捕获 |
| 抽象信号嗅探 `_abstraction_hint` | L428-435（词表 `_ABSTRACTION_SIGNALS` L421-425） | 纯 stdlib 子串匹配；**仅非约束 stdout 提示**，cmd_fail L1948-1953 / cmd_patch L2006-2011 |
| 审核环节提醒 `_methodology_capture_hint` | L534-578 | **仅 Phase 14/15**；非约束软上下文；列出待 endorse draft（`_pending_endorse_drafts` L932-948） |
| 专家信任门（预防式 `_prior_expert_kb_block`） | L842 | `if r.get("status") != "endorsed": continue` —— **endorsed-only，无 occ≥3 逃生口** |
| 专家信任门（反应式 `_relevant_expert_on_fail`） | L899 | 同上 |
| `kb add-expert` | L2374-2415 | 人工沉淀 draft；自动并入 REQ 域词（L2393-2395，RC-d）；不自动触发 |
| `kb endorse` | L2416-2425 | **单条**，须 `--id`；无批量/一键入口 |
| occ 累积 `kb_store.upsert_lesson` | `runtime/kb_store.py` L288-330 | 指纹命中且 `new_req` 不在 `source_reqs` 才 occ++（L306-308）——**只对独立新需求累积** |
| 专家指纹 `kb_store.fingerprint` | L272-274 | `category|principle[:40]` sha1 |

### 1.2 三个根因（为什么"用户操作简单"至今没达成）

| 根因 | 机制后果 |
|---|---|
| **RC-a 沉淀全人肉** | expert 只能 `kb add-expert` 手敲；`_abstraction_hint`/`_methodology_capture_hint` 是非约束软提醒，模型可忘、可跳 → "自动识别提炼"根本不存在 |
| **RC-b endorse-only 死锁** | v0.11.3 经用户确认的"endorsed-only 无 occ≥3"使 draft 永不自动转正；draft 需人肉跑 CLI endorse，现实中无人跑 → 沉淀了也永不注入（v0.11.5 `_pending_endorse_drafts` 只解决了"看得见"，没解决"要人肉跑命令"） |
| **RC-c 审核摩擦** | `kb endorse` 单条 + 必须记 id，与"用户回一个字"的期望相距甚远；无批量背书入口 |

> 注：RC-a/RC-b/RC-c 是本文新命名的沉淀侧根因，与既有 RC 编号（RC-a 曾指 v0.11.5 死锁）不冲突——本文在 §9 相容性核对中声明沿革。

---

## 2. 设计原则

1. **提炼归模型，机制归 Runtime**（铁律不变）：唯一需要 LLM 的环节是"从纠正原话提炼 category/principle"；候选判定、忽略判定、落盘、指纹去重、occ 累积、信任门、背书全部 Runtime 确定性，模型不可绕过。
2. **自动生效靠"现实验证"而非"模型自信"**：occ 累积要求 ≥3 个**独立需求**（`source_req` 不同）命中**同一指纹**（`category|principle[:40]` 逐字一致）才自动转正——三个互不相干的需求独立复现同一方法论，可信度高于人肉扫一眼。
3. **不破坏回归**：无 expert 候选命中时，fail/patch 行为与今日**逐字节一致**（护既有 150/0 substring 断言）；endorse 单条路径不变。
4. **可撤销**：自动生效的 expert 记录仍走 `kb supersede` 一键归档，误生效成本可控。

---

## 3. 总体架构

```
用户反馈（fail/patch --reason，或 审核环节对话）
        │
        ▼
┌─ 项1·自动识别（Runtime 确定性，零模型）─────────────────────────┐
│  reason 命中 _ABSTRACTION_SIGNALS？                              │
│  ├─ 否 → 自动忽略（expert 路由不触发，仅 lessons 原话，即现状）  │
│  └─ 是 → 置 st["pending_expert_extraction"]=reason，强制提炼      │
└──────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─ 项2·自动提炼（模型提炼 + Runtime 校验落盘）─────────────────────┐
│  模型执行 kb extract-expert --reason ... --category --principle   │
│  Runtime 校验：category∈词表 / principle 非空 / 自动并入 REQ 域词 │
│  → 落 draft（不注入）；指纹去重 → occ++（仅独立需求）            │
└──────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─ 项3·自动生效 / 一键背书（信任门重开 occ≥3）────────────────────┐
│  draft occ≥3 → 自动 endorsed → 注入 ##PRIOR_EXPERT_KB##          │
│  draft occ<3 → _pending_endorse_drafts 列出 → kb endorse --all-drafts│
│  用户回「通过」→ 模型跑一条命令全背                              │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. 详细设计

### 4.1 项 1 — 自动识别（`_maybe_capture_lesson` 扩展 + 卡片强制）

**根因**：`_abstraction_hint` 已能做候选判定（纯 stdlib），但只打印非约束提示；`_maybe_capture_lesson` 只写 lessons。

**改动**：

- 新增 `_flag_expert_candidate(st, reason)`（`qamaster_runtime.py`，置于 `_maybe_capture_lesson` 旁）：`_abstraction_hint(reason)` 非空 → `st["pending_expert_extraction"] = reason.strip()`；否则不写。返回是否命中。
- `cmd_fail`（L1940 后）与 `cmd_patch`（L1997 后）在 `_maybe_capture_lesson` 旁调用 `_flag_expert_candidate`；命中时**替换**现有非约束 `_abstraction_hint` 提示段（L1948-1953 / L2006-2011）为一条**约束指令**：
  > 本阶段纠正命中可抽象方法信号（`<命中词>`）。完成本阶段前**必须**执行 `kb extract-expert --reason "<原话>" --req-id <id> --category <类> --principle "<脱业务原则>" --applicable-phases <阶段>` 提炼落 draft；不执行视为漏沉淀。

- **诚实边界（挂"取舍与风险"）**：fail/patch 通道 reason 是 CLI 参数、Runtime 可嗅探 → **全自动**。审核/许可环节（Phase 14/15）反馈是对话式、无 reason 字符串，Runtime 无法确定性嗅探 → 该通道维持 `_methodology_capture_hint` 软提醒 + `_pending_endorse_drafts` 列出，由模型主动识别（v0.11.4 已有此路径），本文**不强行把对话式反馈做成假自动**。

### 4.2 项 2 — 自动提炼（新命令 `kb extract-expert`）

**根因**：`kb add-expert` 是纯人肉入口；没有"带原话 + 确定性忽略判定 + 强制校验"的提取入口。

**改动**（`cmd_kb` 内，`qamaster_runtime.py`）：

- 新增 action `extract-expert`，参数 `--reason`（必填·纠正原话 verbatim）+ `--category` + `--principle` + `--applicable-phases` + `--trigger`（可选）+ `--req-id`/`--source-req`。逻辑：
  1. **忽略门（确定性）**：`_abstraction_hint(a.reason)` 为空 → `_die("此纠正不含可抽象方法信号，已自动忽略（不进专家库）")`——这就是"不适合写入专家知识库则自动忽略"的机器实现。
  2. **校验**：`category` ∈ 词表（复用 `expert_kb.md` §三 10 类，硬编码枚举常量 `_EXPERT_CATEGORIES`）；`principle` 非空；`applicable_phases` 数字过滤（复用 `_split_tokens`）。
  3. **自动并入 REQ 域词**：复用 `add-expert` 的 `_req_signal_hits(_req_corpus_text(...))`（L2393-2395 同款，护 RC-d）。
  4. 落 draft（`kind=expert`，`occurrences=1`，`status=draft`），指纹去重由 `upsert_lesson` 完成（同 category|principle 自动 occ++）。
- `add-expert` 保留（人肉精调入口），`extract-expert` 与其共享落盘逻辑（抽公共 `_upsert_expert_rec(...)`，避免双写漂移）。

### 4.3 项 3 — 信任门重开 occ≥3 + 一键背书

**根因**：RC-b（endorsed-only 死锁）+ RC-c（单条 endorse 摩擦）。

**改动**：

- **信任门两行重开**（这是对 v0.11.3 经用户确认的 endorsed-only 的**显式反转**，§8 诚实披露）：
  - `_prior_expert_kb_block` L842：`if r.get("status") != "endorsed":` → `if r.get("status") != "endorsed" and (r.get("occurrences", 1) or 1) < 3:`
  - `_relevant_expert_on_fail` L899：同款。
  - 同步改两函数 docstring（L820-821、L878-879）与 `_prior_expert_kb_block` 头注释，删除"无 occ≥3 逃生口"表述。
- **一键背书**（`kb_store.py` + `cmd_kb`）：
  - `kb_store.endorse_all(path)`：把所有非 `superseded_by`、`status==draft` 的记录置 `endorsed`，返回条数。
  - `cmd_kb` 新增 `endorse --all`（或 `--kind expert --status draft` 批量）：`kb endorse --kind expert --all-drafts` → 全背。用户回「通过」→ 模型跑这一条即可。
- `_pending_endorse_drafts`（L932-948）不变——它已正确列出 occ<3 待背 draft；一键背书消费它。

---

## 5. 改动文件清单（按优先级）

### Phase A（P0·核心闭环·3 处）

| 文件 | 改动 |
|---|---|
| `runtime/qamaster_runtime.py` | ①信任门 L842/L899 重开 `or occ≥3`（+docstring）；②`_flag_expert_candidate` + `cmd_fail`/`cmd_patch` 挂接；③`cmd_kb` 增 `extract-expert` + `endorse --all-drafts`；④`_EXPERT_CATEGORIES` 词表常量 |
| `runtime/kb_store.py` | `endorse_all(path)` 批量背书 |
| `scripts/test_runtime.py` | 改 `test_expert_draft_blocked_trust_gate`（occ=3 现注入）；新增 occ≥3 自动生效 / occ=1 仍阻断 / extract-expert 忽略门 / endorse --all-drafts 四组 |

### Phase B（P1·文档同步·4 处）

| 文件 | 改动 |
|---|---|
| `skills/case-design/references/expert_kb.md` | §五 信任门表：expert 由"仅 endorsed"改"endorsed 或 occ≥3"；§一/§二 捕获时机补"extract-expert 自动提炼 + 忽略门" |
| `skills/case-design/SKILL.md` | 铁律 #5（L52）信任门表述同步；修改流程路由补 extract-expert |
| `skills/case-design/CHANGELOG.md` | 新增 v0.11.11 发布说明 |
| `.claude-plugin/plugin.json` + `marketplace.json` | 0.11.10 → 0.11.11 |

---

## 6. 迁移路线

1. `kb_store.endorse_all` + `cmd_kb endorse --all-drafts`（最小、独立、先落地）
2. 信任门 L842/L899 重开 occ≥3 + docstring + 测试翻转
3. `_flag_expert_candidate` + `cmd_fail`/`cmd_patch` 挂接（护 no-op：无命中 → 逐字节不变）
4. `cmd_kb extract-expert` + `_EXPERT_CATEGORIES`（含忽略门）
5. 文档同步（expert_kb.md / SKILL.md / CHANGELOG / plugin.json）
6. 端到端验证（§7）

---

## 7. 验证方法（端到端）

1. **回归基线**：无 expert 候选命中时，fail/patch stdout 与改动前逐字节一致（护 150/0）；`test_expert_noop_preserves_baseline` 仍绿。
2. **occ≥3 自动生效**：同 `category|principle` 三个不同 `source_req` → draft occ=3 → `_prior_expert_kb_block` 注入（无需 endorse）；occ=1 draft 仍不注入。
3. **extract-expert 忽略门**：`kb extract-expert --reason "RK16 没引"` → 拒绝（无抽象信号）；`--reason "边界只测 min/max 漏 min+1"` → 落 draft + 并入 REQ 域词。
4. **一键背书**：3 条 expert draft → `kb endorse --kind expert --all-drafts` → 全 endorsed → 注入。
5. **endorse-only 反转的可撤销**：自动生效的 occ=3 记录 → `kb supersede` → 不再注入。
6. **脚本自测**：`scripts/test_runtime.py` 扩组：occ≥3 自动生效、occ=1 阻断、extract-expert 忽略门/落盘/域词并入、endorse --all-drafts。

---

## 8. 取舍与风险（诚实披露）

1. **反转 v0.11.3 的 endorsed-only**：这是本文唯一一处"推翻既往明确决策"的地方。理由：①occ 累积要求 ≥3 个独立需求 + 指纹逐字一致，是强现实信号而非模型自信；②自动生效记录可 `supersede` 撤销；③不重开则 RC-b 死锁无法根治（draft 永不自动转正）。**风险**：模型若在 3 个需求里稳定复现同一"过度泛化"方法论（措辞几乎一致），会误自动生效——但 fingerprint 要求 `principle[:40]` 逐字一致，措辞漂移即不累积，实际误生效概率低；且可 supersede。
2. **对话式反馈（Phase 14/15）无法 Runtime 自动嗅探**：无 reason 字符串，本文不强行假自动，仍靠 `_methodology_capture_hint` + 模型主动识别。诚实声明：这一通道的"自动识别"是"模型记得做"，非"Runtime 保证做"。
3. **强制提炼是"软强制"非硬门**：`pending_expert_extraction` 置位后卡片约束模型必须跑 extract-expert，但未把它做成 gate 硬阻断——方法论提炼失败不应阻塞测试用例交付（沉淀是副产品，交付是主线）。代价：极端情况下模型仍可能跳过提炼，但比纯 `_abstraction_hint` 软提示强一档（有状态位 + 强措辞 + 交付摘要可回显）。
4. **`endorse --all-drafts` 一次背多条**：背书从"逐条精审"降为"批量放行"，牺牲单条审阅粒度换操作简单——正是用户目标。不放心者仍可单条 `kb endorse --id`。

---

## 9. 与既有约束的相容性核对

| 既有约束 | 是否破坏 | 说明 |
|---|---|---|
| 铁律 #5「机制与模型无关，内容归人类」 | 否 | 候选判定/忽略/落盘/occ/信任门/背书全 Runtime 确定性；唯一模型环节是提炼 category/principle（内容，仍归人背书或 occ≥3 验证） |
| 模型禁写 KB_*.md | 否 | 仍走 `kb` 命令 FileLock 落盘 |
| 三门注入（适用/信任/相关） | 否 | 只松信任门（endorsed→endorsed∨occ≥3），适用门/相关性门不变 |
| No-op 基线 150/0 | 否 | 无候选命中时 fail/patch 逐字节不变 |
| 指纹去重/occ 语义 | 否 | occ 累积逻辑（独立 source_req）不变，仅信任门消费它 |
| v0.11.3 专家库机制 | 否 | 沉淀侧进化，注入侧（`_render_expert_block`）不变 |
| 回归安全 | 部分 | `test_expert_draft_blocked_trust_gate` 断言需翻转（occ=3 由"不注入"改"注入"），属预期行为变更 |

---

## 10. CHANGELOG v0.11.11 摘要（待写）

> **本次发布把专家方法论沉淀从"人肉"升级为"半自动"**。新增 `kb extract-expert`（带确定性别忽略门 + 自动并入 REQ 域词）与 `kb endorse --all-drafts` 一键背书；fail/patch 纠正命中可抽象信号时 Runtime 置位强制提炼；专家信任门重开 `endorsed 或 occ≥3`——同方法论被 ≥3 个独立需求命中即自动生效（可 supersede 撤销），闭合 draft 永不自动转正的死锁。

---

## 11. 结束语

本设计不改写 v0.11.3 的三门注入与指纹去重，而是**补齐沉淀侧的自动化**——把"自动识别/提炼/生效"落到 Runtime 确定性的候选判定 + 强制提炼 + occ 累积信任门上，让"用户操作简单"从愿景变成机制。核心原则不变：**提炼归模型，机制归 Runtime，任何模型不可绕过**；唯一松动的"endorsed-only"由"≥3 独立需求现实验证 + 可 supersede 撤销"双重兜底。
