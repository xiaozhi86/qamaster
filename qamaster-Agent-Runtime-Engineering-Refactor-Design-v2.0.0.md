# qamaster Agent Runtime Engineering 重构详细设计方案

版本：v2.3.0
日期：2026-08-19
作者：xiaozhi

> **一句话定位**：把 qamaster 从"依赖模型理解流程的 Skill"升级为"由 Runtime 严格控制、模型只负责思考、任何模型不可绕过"的企业级 Agent 系统，并支持**同工程多需求并行、互不干扰**、**跨需求自我进化知识系统**。
>
> 核心原则：**模型负责思考，Runtime 负责控制。流程通过 Runtime 严格控制，与模型无关。**

---

## 0. 版本演进说明（v1.0.0 → v2.3.0）

| 版本 | 内容 | 状态 |
|---|---|---|
| v1.0.0 | 早期愿景：`engine/gate/validator/memory` 分目录、yaml 流程定义、`state/runtime-state.json` | 已被更务实的实现取代，**保留为历史愿景** |
| v2.0.0 | 校正到**真实落地架构**（单控制器 + 注册表 + 分区状态），并新增三大改造：① 多需求并行；② 通用 workflow 引擎；③ MANIFEST 多需求索引协调权回归 Runtime（强化"与模型无关"） | 已被 v2.1.0 取代，**保留为历史设计** |
| **v2.1.0** | 在 v2.0.0 之上补齐两大落地：④ requirement-review 全状态机迁移完成（第二 workflow）；⑤ 自我进化知识系统（经验/业务/专家三库 + 双/三门注入）。同步铁律 5→6 条、CLI 增 `patch`/`kb`、断言 122→383 | 已被 v2.2.0 取代，保留为历史设计 |
| **v2.2.0** | requirement-review 完整多需求并行评审：门禁 req_id 隔离（`exists_any` 支持 `{req_id}` 占位）+ 独立 MANIFEST 聚合索引（`manifest.py` 泛化为按 workflow 的 schema 注册表）；case-design 零影响。断言 383→422 | 已被 v2.3.0 取代，保留为历史设计 |
| **v2.3.0** | 上下文/token 主动防护层：阈值门控 `##CONTEXT_BUDGET##`（契约卡末尾建议性提示）+ `context` 只读诊断命令 + 累计输入/输出 token 足迹（幂等重算）。默认零输出、零影响。断言 422→434 | **当前权威设计** |

**v1.0.0 为何被取代**：原愿景的分目录（engine/gate/validator/memory）与 yaml 流程定义在实践中偏重，最终按"一个 workflow 无关控制器 + 一个阶段注册表 + 分区状态存储"的务实结构落地。v2.0.0 的首要工作是**让设计文档与真实代码对齐**（v1.0.0 的目录结构从未实现，长期是文档与代码的悬空）；v2.1.0 继续这一对齐——补记 v2.0.0 之后落地的 requirement-review 第二 workflow 与自我进化知识系统；v2.2.0 再次对齐——补记 requirement-review 多需求并行评审（门禁 req_id 隔离 + 独立 MANIFEST 聚合索引）落地。v2.3.0 第三次对齐——补记上下文/token 主动防护层（阈值门控 `##CONTEXT_BUDGET##` + `context` 只读诊断 + 累计足迹）落地，闭合"全程会话转录持续累积、超限处理完全依赖 Claude Code 原生压缩、qamaster 自身无任何主动计量"的缺口。

**与三份细化设计的关系**（互补、不互斥，本文是总览）：

- [`skills/case-design/PHASE_GATE_DESIGN.md`](skills/case-design/PHASE_GATE_DESIGN.md) — 门禁前移（Phase 3/5/7/8/10 出口 gate 由 runtime 强制）+ 跨阶段制品传递（state.json `artifacts` 注册表 + 契约卡 `PRIOR_ARTIFACTS` 注入）。
- [`COVERAGE_HARDENING_DESIGN-v1.0.0.md`](COVERAGE_HARDENING_DESIGN-v1.0.0.md) — 覆盖率四道硬门（需求条目 + 测试点 + 风险 + 安全）+ 设计文档作为正式追溯源。
- [`skills/case-design/EXPERT_KB_AUTO_SEDIMENT_DESIGN-v1.0.0.md`](skills/case-design/EXPERT_KB_AUTO_SEDIMENT_DESIGN-v1.0.0.md) — 专家方法论沉淀侧自动化（自动识别可抽象反馈 + `kb extract-expert` 自动提炼 + occ≥3 自动生效 / 一键背书）。

本文（v2.3.0）描述**流程控制层**的整体架构、多需求并行机制、自我进化知识系统与上下文防护；上面三份描述**质量门禁层**与**自我进化沉淀侧**的细节。两层共同兑现"Runtime 控制流程、模型执行任务"。

---

## 1. 背景与目标

### 1.1 原始问题（v1.0.0 起点）

qamaster 早期是纯 SKILL.md 驱动：0-15 阶段流程依赖模型自身指令遵循能力。问题是模型拥有流程控制权——可以跳过阶段、忽略确认点、提前输出结果、自证"已通过"。这与"任何模型（Claude/GPT/GLM/Gemini/DeepSeek…）都必须按 0-15 阶段执行"的目标冲突。

### 1.2 本次新增问题（v2.0.0 起点）

原 Runtime 控制层是**单需求/单工作目录**模型：状态文件固定为 `<workdir>/case-design-out/.runtime/state.json`，checkpoint 按阶段号单例存放，MANIFEST 由模型"整表 Write"。同工程下两个客户端处理不同需求时：

- `state.json` 上互相覆盖（A 的 current_phase/req_id 被 B 写掉）；
- checkpoint 按阶段号互相覆盖；
- MANIFEST"整表 Write"丢行、竞态损坏。

产物层（`REQ_<id>.md` / `TestCases_<id>.md` 等）已按 `req_id` 文件名隔离、能多需求共存；但**控制层是单例固定路径、无锁**——多需求并发必然 clobber。

### 1.3 目标

1. **多需求并行**：同工程下 N 个需求并行推进、互不干扰。
2. **通用 workflow 引擎**：Runtime 与具体 skill 解耦，后续新增独立 skill（需求评审、接口自动化测试…）只需注册自己的阶段机，即继承隔离 + 强控。
3. **强化"与模型无关"**：把 MANIFEST 的多需求协调权从模型收回 Runtime——MANIFEST 变更成为 gate PASS 的**确定性副作用**，模型无法影响是否/何时更新多需求索引。

---

## 2. 核心架构

### 2.1 控制流（v1.0.0 愿景已落地为务实形态）

```
User
 ↓
Claude Code Plugin（commands/case-design.md）
 ↓
qamaster Runtime Controller（runtime/qamaster_runtime.py，workflow 无关）
 ↓
WorkflowSpec（runtime/workflows/registry.py + case_design.py，阶段机）
 ↓
Quality Gate（runtime/phases.py 的 gate_checks + 客观校验脚本）
 ↓
LLM Worker（模型，只思考、产出，不控制流程）
```

### 2.2 三层职责

| 层 | 职责 | 承载 |
|---|---|---|
| 业务规范 | 阶段细则、避坑红线、输入协议、运行模式、质量标准 | `skills/case-design/SKILL.md` + `references/*.md`；`skills/requirement-review/SKILL.md` |
| 流程控制 | 状态机、契约卡、门禁裁决、状态分区、MANIFEST 协调、自我进化知识库、上下文防护（建议性估算） | `runtime/{state_store,phases,requirement_review_phases,qamaster_runtime,manifest,locking,kb_store}.py` + `runtime/workflows/` |
| 客观校验 | 机器可判定的检查（结构/内容/覆盖/门禁前移） | `skills/case-design/scripts/{verify_md,verify_cases,gen_excel,verify_knowledge}.py` + `config/validation_rules.json`；`skills/requirement-review/scripts/extract_text.py` |

原则不变：**模型负责思考，Runtime 负责控制。** 业务规则以 SKILL.md + references 为唯一细则来源（铁律 3），Runtime 只做流程控制。

---

## 3. 目录设计（真实落地，v2.0.0 校正）

```
qamaster/
├─ .claude-plugin/plugin.json          # 插件清单
├─ commands/case-design.md             # /case-design 入口（内部链式 bootstrap → start）
├─ skills/case-design/                 # 业务规范层（case-design workflow）
│  ├─ SKILL.md                         # 全局规范 + 六条铁律 + Runtime 控制协议
│  ├─ references/*.md                  # 各阶段细则（0~15 + 知识沉淀 + expert_kb）
│  ├─ scripts/                         # 客观校验脚本（verify_md/verify_cases/gen_excel/...）
│  └─ config/validation_rules.json     # 校验单一事实源
├─ skills/requirement-review/          # 业务规范层（requirement-review workflow）
│  ├─ SKILL.md                         # 多 Agent 并行评审规范（7 Agent·9 阶段散文）
│  └─ scripts/extract_text.py          # 非 Markdown 需求文档预处理（含 OCR）
├─ runtime/                            # 流程控制层（workflow 无关引擎）
│  ├─ qamaster_runtime.py              # 控制器：bootstrap/start/status/next/gate/confirm/patch/kb/...
│  ├─ state_store.py                   # 状态分区存储 + 迁移（SCHEMA_VERSION=3）
│  ├─ phases.py                        # case-design 阶段机（0-15，单一事实源）
│  ├─ requirement_review_phases.py     # requirement-review 阶段机（0-7，单一事实源）
│  ├─ manifest.py                      # MANIFEST.md 的 read-modify-write（Runtime 独占）
│  ├─ kb_store.py                      # KB_lessons/business/expert 的 read-modify-write（Runtime 独占）
│  ├─ locking.py                       # 跨平台 FileLock（msvcrt/fcntl，stdlib）
│  └─ workflows/
│     ├─ registry.py                   # WorkflowSpec 数据结构 + 注册表
│     ├─ case_design.py                # phases.py → WorkflowSpec 适配层（显式 register）
│     └─ requirement_review.py         # requirement_review_phases.py → WorkflowSpec 适配层
├─ case-design-out/                    # case-design 产物层（用户工程运行时生成）
│  ├─ REQ_<id>.md / TestCases_<id>*.md / Clarification_Ledger_<id>.md
│  ├─ Knowledge_<id>.md / DESIGN_<id>.md / TestCases_<id>.xlsx
│  ├─ MANIFEST.md                      # 多需求共享索引（Runtime 锁控·模型禁写）
│  ├─ KB_lessons.md                    # 自我进化经验库（Runtime 锁控·模型禁写）
│  ├─ KB_business.md                   # 业务历史知识库（Runtime 锁控·模型禁写）
│  └─ KB_expert.md                     # 专家方法论库（Runtime 锁控·模型禁写）
├─ requirement-review-out/             # requirement-review 产物层（REQ/ReviewIssues/ReviewedReq/MANIFEST）
└─ .qamaster/                          # Runtime 控制层根（gitignore，按 workflow/req_id 分区）
   ├─ case-design/<req_id>/
   │  ├─ state.json
   │  └─ checkpoint_<N>.md
   └─ requirement-review/<req_id>/
      ├─ state.json
      └─ checkpoint_<N>.md
```

> 与 v1.0.0 的差异：v1.0.0 写的 `runtime/engine|gate|validator|memory/`、`workflow/case-design-flow.yaml`、`state/runtime-state.json` **均未实现**；真实结构是上图的"控制器 + 注册表 + 分区状态"。v2.0.0 以此为准；v2.1.0 新增 `requirement_review_phases.py`（第二 workflow 阶段机）与 `kb_store.py`（三 KB 的独占维护），产物层新增三 KB 文件与 `requirement-review-out/`；v2.2.0 新增 requirement-review 独立 MANIFEST 索引（`manifest.py` 按 workflow schema 泛化）。

---

## 4. 多需求并行与状态分区（v2.0.0 核心·新增）

### 4.1 分区布局

```
<workdir>/
├─ case-design-out/          # 产物层（保持不变，向后兼容）
│  ├─ REQ_<id>.md  …  （按 req_id 文件名天然隔离）
│  └─ MANIFEST.md            # 唯一共享可变资源（FileLock 串行化）
└─ .qamaster/                # Runtime 控制层根（新增）
   └─ case-design/<req_id>/  # 按 (workflow, req_id) 分区
      ├─ state.json
      └─ checkpoint_<N>.md
```

### 4.2 隔离原理（无需锁即可避免 clobber）

状态按 `(workflow, req_id)` 目录分区（`state_store.default_state_path(workdir, workflow, req_id)` → `<workdir>/.qamaster/<workflow>/<req_id>/state.json`）：

- 每个 in-flight 需求有独立的 `state.json` 与 `checkpoint_<N>.md`，**单写者、无并发**——根本不存在 A/B 争抢同一文件的问题。
- 同一 req_id 不同 workflow（未来 skill）也隔离（路径含 workflow 段），天然不冲突。
- `state_store.save` 保留原子写（tmp + `os.replace`，4 次重试防 AV 锁），仅防单写者中断/杀毒锁，不再承担并发职责。

**唯一例外**：各 workflow 的 `MANIFEST.md`（`case-design-out/MANIFEST.md` 与 `requirement-review-out/MANIFEST.md`，v0.11.12 起）是多需求共享可变资源，需锁——见 §8。

### 4.3 多需求可见性

- `state_store.list_active_reqs(workdir, workflow)`：枚举该 workdir+workflow 下所有存在 `state.json` 的 req_id（含已完成，供复用检测与全量展示）。
- `status --all`：JSON 列出全部在途需求及其阶段/状态/模式（`cmd_status`）。
- `bootstrap` 碰撞检查：派生 req_id 时查 in-flight 状态（→ `RESUME`）与 MANIFEST 已归档行（→ 追加 `-YYYYMMDD`），杜绝同名覆盖。

### 4.4 降级对账不误报（C2 修正）

`_audit_degraded_artifacts` 在 `start` resume 时扫描"产物存在但状态缺失/不符"。多需求下若 glob 所有 `TestCases_*.md` 会误报**别的需求**的用例。修正为按当前 `req_id` 限定 glob：`TestCases_<req_id>*.md`，只对本需求的产物对账。

---

## 5. 通用 Workflow 引擎（v2.0.0·新增）

### 5.1 WorkflowSpec 注册表

`runtime/workflows/registry.py` 定义 `WorkflowSpec`（阶段机 + 元数据）：

| 字段 | 含义 |
|---|---|
| `name` | "case-design" 等；用于状态分区路径与 `--workflow` 取值 |
| `output_dir` | 产物目录相对 workdir，如 `case-design-out` |
| `skill_dir` | skill 根相对 workdir，如 `skills/case-design` |
| `phases` | 阶段列表（dict 形状，与 `phases.py` 兼容） |
| `depth_skips` | 流程深度裁剪表 `{"heavy":[],"medium":[4],"light":[3,4]}` |
| `knowledge_gate` | Phase 14 confirm 后置动作（知识沉淀）的门禁 |
| `last_phase` | 末阶段号（由 phases 末尾推导） |
| `skill_md` | SKILL.md 路径 |
| `extra_card_text` | 钩子 `(phase, st) -> str`，给契约卡追加 workflow 专属片段 |

helper：`get_phase / effective_phases / next_phase_id / find_phase_by_name`（与 `phases.py` 同名函数行为一致）。

### 5.2 显式注册（无 import 副作用）

`case_design.py` 把 `phases.py`（case-design 阶段机的单一事实源）包成 `WorkflowSpec` 并暴露 `register()`，由控制器 `main()` 在 `_register_workflows()` 显式调用——**不靠 import 副作用**（规避隐式注册风险 R7）。

```python
# runtime/workflows/case_design.py
def register():
    spec = WorkflowSpec(name="case-design", output_dir="case-design-out",
                        skill_dir="skills/case-design",
                        phases=phases.PHASES, depth_skips=phases.DEPTH_SKIPS,
                        knowledge_gate=phases.KNOWLEDGE_GATE, extra_card_text=_extra_card_text)
    spec.last_phase = phases.LAST_PHASE
    _registry_register(spec)
```

### 5.3 第二 workflow 落地：requirement-review（v2.1.0 已完成）

新增独立 skill 只需：在 `runtime/workflows/` 加 `<name>.py` 构造一份 `WorkflowSpec` 并 `register()`，在控制器 `main()` 调用它。控制器按 `--workflow` 路由取 `get_workflow(name)`，状态路径、产物目录、契约卡、门禁全部由 spec 驱动，**无需改控制器**。`phases.py` 保持 case-design 专属（不强行 dataclass 化，最小改动）。

这条扩展点已在 **requirement-review** 上兑现（v0.11.10）：

- `runtime/requirement_review_phases.py` — 8 阶段（0-7）轻量状态机，把 SKILL.md 的「并行评审 + 汇总仲裁」9 阶段压缩为受控阶段：
  0 输入预处理与需求定位(auto) → 1 并行评审(auto) → 2 结果汇总去重+冲突检测(auto·无门禁) → 3 优化方案总览(auto·无门禁) → **4 用户确认(confirm)** → 5 需求文档重构(auto) → 6 自动复查+二次修复(auto·无门禁) → 7 最终输出(auto·last)。`DEPTH_SKIPS` 全空（单次评审，无深度裁剪）。
- `runtime/workflows/requirement_review.py` — 把阶段机包成 `WorkflowSpec` 并显式 `register()`；`_EXTRA_PHASE4` 给 Phase 4 契约卡追加 requirement-review 专属确认话术。
- 与 case-design 的差异：无知识总结后置动作、无 Excel 许可门（末阶段=auto）；门禁为确定性文件存在性检查（`exists_any`：`REQ_{req_id}.md` / `ReviewIssues_{req_id}.md` / `ReviewedReq_{req_id}.md`，v0.11.12 起 req_id 绑定，此前为 `*` glob）；人工确认门（Phase 4）复用控制器 `confirm` 机制，模型不可绕过。
- 控制器侧 `_manifest_side_effect` 由「`if spec.name != "case-design": return` 护栏」（v0.11.10 缺陷4）演进为按 workflow 分派（v0.11.12）：case-design 走 `_case_design_manifest_side_effect`（原逻辑原样搬入），requirement-review 走 `_rr_manifest_side_effect`（Phase 0/1/5/7 写 `requirement-review-out/MANIFEST.md`，列集独立）。

> requirement-review 的 8 阶段明细见 §6.4；完整阶段定义见 `runtime/requirement_review_phases.py`（单一事实源）。

### 5.4 自我进化知识系统（v2.1.0 新增，详见 §8.5）

runtime 新增 `kb_store.py`（三 KB 的 read-modify-write）与控制器 `cmd_kb`，把"跨需求共享知识"从模型手中收回 Runtime——经验/业务/专家三库同禁写纪律，通过契约卡注入软上下文（消费侧参考，非硬门）。这是 v2.0.0 "MANIFEST 协调权回归 Runtime" 在知识维度的延续。

---

## 6. Runtime Core：状态机与门禁

### 6.1 state.json 字段（`state_store.new_state`，SCHEMA_VERSION=3）

```
schema=3, workflow, req_id, workdir,
current_phase, completed[], status,
run_mode(full|auto|light), depth(heavy|medium|light), input_kind(requirement|contract),
skipped_phases[], failed_gates{}, confirm_rounds, gate_rounds{}, artifacts{},
patch_directives[], history[], created_at, updated_at,
(excel, knowledge 后置；modify_of 修改既有需求标记；review_kind 审核放行类型审计)
```

**status 枚举**：`RUNNING`（未过出口门）/ `GATE_PASSED`（已过，可 next）/ `WAIT_USER_CONFIRM`（人工门待答复）/ `WAIT_LICENSE`（Excel 许可待答复）/ `REVIEW_PENDING`（连跑/轻量人工门已标注待审、自动放行）/ `DONE` / `ESCALATION_REQUIRED`（有界返修：某 auto 门 `gate_rounds≥3` 触发，阻断推进，须人工 `--force` 解除）。

**patch_directives**（G-FB1 增量反哺）：`[{target_phase, target_name, from_phase, reason}]`，由 `patch --to` 登记，注入当前阶段契约卡 `##PATCH_FEEDBACK##` 段，模型就地修正前置产物切片后 `patch --clear` 清除——不回退不重跑。

### 6.2 阶段机（0-15，`phases.py`）

| # | 阶段 | gate | 出口检查 |
|---|---|---|---|
| 0 | 需求定位与输入分析 | auto | `exists_any REQ_*.md`（+ 可选 DESIGN） |
| 1 | 需求分析与澄清 | confirm | 人工门（台账落盘 + 缺口分级） |
| 2 | 测试需求分析 | auto | 内存产物 |
| 3 | 规则建模 | auto | `phase_gate 3`（规则来源 + R 连续） |
| 4 | 规格建模 SDD | auto | 内存（medium/light 裁剪） |
| 5 | 风险分析 | auto | `phase_gate 5`（风险来源 + RK 连续） |
| 6 | 测试策略匹配 | auto | 内存 |
| 7 | 测试点建模 | auto | `phase_gate 7`（TP 连续 + 风险→TP） |
| 8 | 用例生成 | auto | `phase_gate 8`（全量 + 引用/消费/一致性/连续） |
| 9 | 去重 | auto | 内存 |
| 10 | 覆盖率校验与反向追溯 | auto | `phase_gate 10`（覆盖硬门 + 台账门禁） |
| 11 | 输出前自查 | auto | 内存（≤3 轮自修） |
| 12 | 对话展示投影 | auto | 内存（只展示不写盘） |
| 13 | 写盘与脚本回读 | auto | `script` verify_md + verify_cases |
| 14 | 人工审核门禁 | confirm | 人工门（+ 后置知识沉淀） |
| 15 | Excel 生成 | license | `script` gen_excel |

> Phase 3/5/7/8/10 的 `phase_gate` 出口门禁、`artifacts` 制品注册表与 `PRIOR_ARTIFACTS` 注入，详见 [PHASE_GATE_DESIGN.md](skills/case-design/PHASE_GATE_DESIGN.md)。Phase 10/13 的覆盖硬门与设计文档追溯，详见 [COVERAGE_HARDENING_DESIGN-v1.0.0.md](COVERAGE_HARDENING_DESIGN-v1.0.0.md)。

### 6.3 门禁三种 kind（与模型无关的强制点）

- **auto（自动门）**：`gate_checks` 经 `_run_check` 跑确定性检查（`exists`/`exists_any`/`script`/`phase_gate`），**PASS 当且仅当所有非 optional 检查通过（`ok_all`）**——模型无法自证 PASS（铁律 2）。
- **confirm（人工门，Phase 1/14）**：由 `_human_gate_decision` 判定，**只看运行模式 + 用户意图标记，不信模型自证**。完整模式默认 WAIT 等用户；连跑/轻量按缺口分级或"待审自动放行"（留 `REVIEW_PENDING` 审计痕迹）。
- **license（许可门，Phase 15）**：默认需用户许可生成 Excel；连跑/轻量且用户已声明要 Excel（`excel=asked_yes`）时自动放行。

`next` 强校验：`RUNNING`/`WAIT_*` 状态直接 `RUNTIME_ERROR`，**跳阶段不可能**。auto 门 FAIL 时 `gate_rounds[phase]+=1`，≥3 次置 `ESCALATION_REQUIRED` 强制人工介入（有界返修，堵 silent infinite-retry），并回显"禁止以任何理由绕过本门禁交付"。

### 6.4 requirement-review 阶段机（0-7，`requirement_review_phases.py`）

| # | 阶段 | gate | 出口检查 |
|---|---|---|---|
| 0 | 输入预处理与需求定位 | auto | `exists_any REQ_{req_id}.md` |
| 1 | 并行评审（7 Agent） | auto | `exists_any ReviewIssues_{req_id}.md` |
| 2 | 结果汇总去重 + 冲突检测 | auto | 内存（无门禁） |
| 3 | 优化方案总览 | auto | 内存（无门禁） |
| 4 | 用户确认 | confirm | 人工确认门（复用控制器 confirm） |
| 5 | 需求文档重构 | auto | `exists_any ReviewedReq_{req_id}.md` |
| 6 | 自动复查 + 二次修复 | auto | 内存（无门禁） |
| 7 | 最终输出 | auto | `exists_any ReviewedReq_{req_id}.md` + `exists_any ReviewIssues_{req_id}.md`（last） |

有独立 MANIFEST 聚合索引（`requirement-review-out/MANIFEST.md`，v0.11.12 起）、无知识后置、无许可门；`DEPTH_SKIPS` 全空；门禁均为 req_id 绑定的文件存在性 glob（`{req_id}` 占位，v0.11.12 起）。

---

## 7. 模型无关协议与六条铁律（强化）

### 7.1 六条铁律（SKILL.md，违反即判定执行缺陷）

1. **状态以 Runtime 为准**：每次接到用户新消息先 `status --req-id <id>` 恢复权威状态，禁止凭对话记忆推断"现在该哪一步"。
2. **门禁以机器判定为准**：`gate` 的 PASS/FAIL 由确定性检查与脚本退出码给出；禁止模型自证"已通过"（声明≠核实）。
3. **业务规范不变**：Runtime 只做流程控制；避坑红线/输入协议/运行模式/质量门禁/输出协议全部以 SKILL.md + references 为唯一细则来源。
4. **MANIFEST 由 Runtime 维护**（v2.0.0 强化）：多需求共享索引由 Runtime 在 gate PASS 时自动维护，模型**禁止 Write/Edit MANIFEST.md**——多需求索引的协调权属于 Runtime。失步时 `manifest reconcile` 重建。
5. **KB 知识库由 Runtime 维护**（v2.1.0 新增，经验库 + 业务知识库 + 专家知识库，分文件、同禁写纪律）：
   - **经验库 `KB_lessons.md`**：跨需求共享的自我进化经验库（纠正原话 verbatim 沉淀/预防提醒/反应式失败定向应用），Runtime 在 `fail`/`patch` 纠正发生时自动沉淀 draft，人工 `endorse` 后注入。
   - **业务知识库 `KB_business.md`**：跨需求共享的业务历史知识索引，聚合自每需求 Phase 14 产出的 `Knowledge_<id>.md` 元数据+维度文本，Runtime 经 `kb reconcile --kind business` 索引（非自动触发），只索引不生成。
   - **专家知识库 `KB_expert.md`**：跨需求共享的**通用测试设计方法论库**（从用户纠正提炼、脱业务复用），经 `kb add-expert` 沉淀 draft、人工 `kb endorse` 后注入；只存通用方法、不记具体业务；信任门仅 endorsed（无 occ≥3 逃生口）。
   - 模型**禁止 Write/Edit `KB_lessons.md`/`KB_business.md`/`KB_expert.md`**——自我进化机制与模型无关，经验/业务/方法论内容归属人类；维护经 `kb <action> [--kind ...]`。模型只"读到"Runtime 注入的 `##PRIOR_LESSONS##`/`##RELEVANT_LESSONS##`/`##PRIOR_BUSINESS_KB##`/`##RELEVANT_BUSINESS_KB##`/`##PRIOR_EXPERT_KB##` 软上下文并据此修正（消费侧参考，非硬门）。
6. **gate FAIL 明细自查通道**：`detail` 有上限，截断时模型必须直接跑 verify_cases.py 拿全量 stdout 自查，不得盲改。

### 7.2 MANIFEST 作为 gate-PASS 确定性副作用（铁律 4 的落地）

模型被剥夺对 MANIFEST 的写权限后，MANIFEST 的所有变更都成为**gate PASS 的确定性副作用**，在每条 PASS 路径上由 Runtime 在 `FileLock` 下执行（`_manifest_side_effect`）：

| workflow | 触发点（gate PASS） | Runtime 副作用 |
|---|---|---|
| case-design | Phase 0（需求落盘） | `manifest add`（从 `REQ_<id>.md` 首个 `#` 标题抽需求名称） |
| case-design | Phase 1（澄清完成） | `manifest update`（台账文件列） |
| case-design | Phase 13（写盘回读通过） | `manifest update`（glob `TestCases_<id>*.md` 实际落盘文件列） |
| case-design | Phase 14（审核通过 confirm） | `manifest complete`（置已完成） |
| requirement-review | Phase 0（需求落盘） | `manifest add`（`REQ_<id>.md`） |
| requirement-review | Phase 1（并行评审） | `manifest update`（评审问题清单列） |
| requirement-review | Phase 5（文档重构） | `manifest update`（最终需求文档列） |
| requirement-review | Phase 7（最终输出） | `manifest complete`（置已完成） |

副作用是 best-effort（锁超时失败不阻断 gate；MANIFEST 是索引不是事实源），失步用 `manifest reconcile` 从磁盘 `REQ_*.md`/`TestCases_*.md` 重建兜底（C6）。auto 门 PASS（`cmd_gate`）、人工门 PASS、`confirm` 三条路径都调用同一副作用，模型无从影响是否/何时更新。

### 7.3 req_id 派生协议（解决"先有鸡还是先有蛋"）

旧 Phase 0 既派生 req_id 又写 REQ.md，导致 `start` 时 id 未知、状态路径无法定位。新协议拆为两步（对用户透明，由 `commands/case-design.md` 链式执行）：

1. **`bootstrap`**：派生 req_id（`--req-id` > 文件路径经 `extract_doc.py` > 内联文本清洗），**不创建状态**；in-flight 则输出 `RESUME`，已归档同名则追加 `-YYYYMMDD`。幂等可重跑。
2. **`start --req-id <id>`**：req_id 必需；存在状态则 `resume`（断点续跑，不重建），否则 `new_state` 落 `.qamaster/case-design/<id>/`。
3. Phase 0 不再派生 id，只读 `state.req_id` → 写 `REQ_<id>.md`（文件名与状态一致）。

### 7.4 C1 时序修正（关键）

`exists MANIFEST.md` 曾是 Phase 0/13 的 gate-check，但 MANIFEST 现由 Runtime 在 gate **PASS 副作用**时创建——gate-check 在 PASS 之前跑，若校验 exists 会死锁（MANIFEST 不存在→FAIL→到不了 PASS→永不创建）。修正：从 Phase 0/13 的 `gate_checks` 移除 `exists MANIFEST.md`。MANIFEST 不再是模型的门禁责任，反而**强化**了"与模型无关"。

---

## 8. MANIFEST 并发协议（v2.0.0·新增）

- **资源**：`<workdir>/{case-design-out,requirement-review-out}/MANIFEST.md`（按 workflow 各一份，列集独立，v0.11.12 起）；锁文件 `.manifest.lock`（同目录）。
- **所有权**：`runtime/manifest.py` 是唯一 read-modify-write 路径；`cmd_manifest` 全程持 `FileLock(timeout=30)`，写用 tmp + `os.replace` 原子替换。
- **列**：按 workflow schema 决定——case-design：需求标识 | 需求名称 | 需求文档 | 设计文档 | 台账文件 | 测试用例文件 | 知识总结 | 状态 | 更新时间；requirement-review：需求标识 | 需求名称 | 需求文档 | 评审问题清单 | 最终需求文档 | 状态 | 更新时间。
- **子命令**：`add`（插新行，重复报错）/ `update`（改指定列，幂等）/ `complete`（置已完成）/ `list`（只读 JSON）/ `reconcile`（从磁盘重建兜底）。
- **模型权限**：明确禁止 `Write/Edit(MANIFEST.md)`（铁律 4）；`check_plugin.py` 加回归护栏 `re.search(r"(Write|Edit)\([^)]*MANIFEST\.md", skill_text)` 命中即报错。
- **为何强化"与模型无关"**：MANIFEST 变更成为 gate PASS 的确定性副作用，模型无法影响多需求索引的协调——"Runtime 负责控制"从状态层延伸到索引层。

---

## 8.5 自我进化知识系统（v2.1.0·新增）

把"跨需求共享知识"从模型手中收回 Runtime，延续 MANIFEST 的"协调权回归 Runtime"哲学到知识维度。三个 KB 分文件、同禁写纪律，均由 Runtime 在 `FileLock` 下独占 read-modify-write（`runtime/kb_store.py`），模型禁止 Write/Edit（铁律 5）。

### 8.5.1 三库职责

| KB 文件 | 内容 | 沉淀入口 | 信任门 | 相关性门 |
|---|---|---|---|---|
| `KB_lessons.md`（经验库） | 纠正原话 verbatim + 预防提醒 + 反应式失败定向 | Runtime 在 `fail`/`patch` 纠正时自动捕获 draft（`_maybe_capture_lesson`） | endorsed 或 occ≥3 | surface≥2 或模块标题命中 |
| `KB_business.md`（业务知识库） | 业务历史知识索引，聚合自 `Knowledge_*.md` 元数据+维度文本 | `kb reconcile --kind business`（非自动，只索引不生成） | endorsed（Knowledge 已过 verify+confirm） | surface≥2 或标题命中 |
| `KB_expert.md`（专家方法论库） | 通用测试设计方法论（脱业务复用），含 category/applicable_phases/principle | `kb add-expert` 沉淀 draft → 人工 `kb endorse` | **仅 endorsed**（无 occ≥3 逃生口） | surface≥2 或标题命中 + phase∈applicable_phases |

### 8.5.2 三条注入链（预防 / 反应 / 方法论）

契约卡 `_card` 注入的软上下文块（消费侧参考，永不作硬门）：

- **预防式（开工前）**：`##PRIOR_LESSONS##`（Phase 0 起）、`##PRIOR_BUSINESS_KB##`（Phase 0 起）、`##PRIOR_EXPERT_KB##`（**每阶段每轮 0-14 含自检轮**，按阶段适用性 + 信任门 + 相关性门过滤）。
- **反应式（失败定向）**：`gate`/`fail` 触发时按失败文本打分注入 `##RELEVANT_LESSONS##` / `##RELEVANT_BUSINESS_KB##` / `##RELEVANT_EXPERT_KB##`（RC-g 补齐专家库反应式路径）。
- **方法论捕捉提醒**：审核门(14)/许可门(15) 契约卡常驻 `##METHODOLOGY_CAPTURE##`，提醒模型把用户可通用的方法论反馈主动 `kb add-expert`（个人记忆不注入任何阶段，v0.11.4 根因修复）。

### 8.5.3 词域匹配与去重（RC-d/e/f 系列修复）

注入门的相关性判定依赖"触发词 surface 命中"，早期存在**词域错配**（方法论术语给人读，但 REQ 正文是业务实词，endorsed 后仍恒 surface<2 不注入）。三轮修复：

- **RC-d（v0.11.6）**：`kb add-expert` 自动并入来源 REQ 的域信号词——`_REQ_SIGNALS` 词表 + `_req_signal_hits` 从 `_req_corpus_text`（REQ+台账语料）命中实词并入 `trigger`，与人工 trigger 并集去重。
- **RC-e（v0.11.7）**：`_dedup_substring_shadow` 子串遮蔽去重——`_REQ_SIGNALS` 含子串对（"大于"⊂"大于等于"），命中时只留最长词，避免子串重复触发。
- **RC-f（v0.11.8）**：`_NUMBERED_COND_RE` + `_COND_CLAUSE_SIGNALS` 编号条件归一——结构性规则常经澄清引入（台账 Q32 引入 AND 门），`1./2./3.` 编号条件被归一为一个条件词触发，写入侧不再漏注入。

### 8.5.4 kb 子命令族（Runtime 独占，全程 FileLock）

`kb <action> [--kind lesson|business|expert|all]`：
`list`/`show`（只读 JSON）、`query`（针对某 req+phase 预览"会注入什么"，`--top`）、`distill`（回放 rollback/patch/gate_fail 纠正事件，零模型）、`reconcile`（仅 business：聚合 Knowledge_*.md）、`add-lesson`/`add-expert`（沉淀 draft）、`endorse`（draft→endorsed）、`supersede`（老经验被新经验取代）、`prune`（清噪）。

记录结构：`<!-- @kb:record start id=KB-<kind>-<fingerprint12> -->` 围栏 + `key: value` 行（标量原样、列表/字典 JSON 字面量），stdlib 可解析、git-diff 友好；指纹按 kind 派发（lesson=phase|dimension，business=module|dimension，expert=category|principle[:40]），同类跨需求 `occurrences++` 累积不拆类。

### 8.5.5 与 MANIFEST 的对称性

MANIFEST 与三 KB 同为"Runtime 独占的可变共享资源"：模型被剥夺写权后，所有变更都是 Runtime 的确定性副作用（MANIFEST=gate PASS 副作用；KB_lessons=fail/patch 自动捕获；KB_business=reconcile 聚合；KB_expert=人工 add-expert+endorse）。`check_plugin.py` 对 MANIFEST 禁写的回归护栏同样适用于 KB（SKILL 文本不得含 `Write/Edit KB_*.md` 权限示例）。

---

## 8.6 上下文/token 主动防护层（v2.3.0·新增）

把「上下文溢出防护」补进 Runtime，但**性质与 MANIFEST/KB 的"独占强控"相反——它是纯建议性（advisory）**，永不参与门禁/状态机/状态 schema，默认零输出。

### 8.6.1 为什么是"建议性"而非"实时拦截"

上一轮分析发现：qamaster 的**单阶段工作集有界**（渐进加载 + 契约卡 + 制品落盘 + `PRIOR_ARTIFACTS` 只注入 ID 范围），但**全程会话转录持续累积、可能逼近/超过模型上下文窗口**；超限处理**完全依赖 Claude Code 原生压缩**，qamaster 自身无任何 token 计量——`SKILL.md` 的 24000/32000 单次 Write 预算只是写给模型的散文，`runtime/` 下无任何计量逻辑。

**核心约束**：Runtime 是 Bash 子进程，**读不到 Claude Code 会话的真实 token 计数**（无环境变量/API 暴露；`/context`/`/cost` 是 REPL 内置非 shell 可执行；解析 `session.jsonl` 属反向工程内部结构、脆弱，**不做**）。因此防护只能是三种**确定性、只读/只追加文本**的手段，而非"实时拦截"：

1. **磁盘指纹估算**——REQ 大小 / checkpoint 用例行数 / KB 注入条数 → 估算工作集 token，越过阈值才提示；
2. **阶段边界建议**——进入已知重输出阶段时给一条「可 `/compact`」提示；
3. **按需诊断命令**——新增 `context` 只读子命令，随时打印估算。

三者均**纯 stdlib、确定性、只读或只追加文本**，**不新增门禁、不改状态机、不改状态 schema（不新增必填字段）、不改任何既有测试断言**。

### 8.6.2 三条机制

| 机制 | 触发 | 行为 | 零影响依据 |
|---|---|---|---|
| **阈值门控 `##CONTEXT_BUDGET##`** | `_context_budget_block` 估算越线 | 契约卡末尾追加「压缩 → 拆最小 PART → 展示与写入分响应」+ 靠后阶段附「可先 `/compact`（状态已落盘，压缩后 `status` 可恢复）」 | 未越线返回 `""`，卡片与现状**逐字节一致**（复用既有「无 KB → no-op」惯例） |
| **阶段边界建议** | case-design Phase 8/13、requirement-review Phase 5/6 | 恒追加一行 `/compact` 提示（已知重输出点） | 纯追加 advisory，不改 ALLOWED/FORBIDDEN/GATE/流程 |
| **`context` 只读命令** | 模型/用户按需调用 | 结构化打印当前工作集估算 + 累计输入/输出 token | 新增子命令、无状态写入 |

估算口径（`_est_tokens`）：CJK 字符≈1 token、其余≈4 字符/token，**估高不估低**（宁早提示）。阈值常量：`CTX_INPUT_TOKENS_WARN=60000`（输入工作集 REQ+refs+KB）、`CTX_OUTPUT_ROWS_WARN=60`（用例行数，对应 24000 输出预算）、`CTX_OUTPUT_TOKENS_WARN=24000`。

### 8.6.3 累计足迹（新增需求的形态边界）

「实时展示累计输入/输出 token」落地为**「qamaster 足迹」**方案：

| 诉求 | 可行性 | 依据 |
|---|---|---|
| 展示模型**真实会话**累计 token | ❌ 不可行（Runtime 侧） | token 计数归 Claude Code 进程所有，不向子进程暴露 |
| 展示 **qamaster 足迹**累计 token | ✅ 可行（确定性·幂等） | Runtime 是经手每个文件的唯一控制方：输入（SKILL.md/refs/REQ/KB/checkpoint 注入）与输出（checkpoint/台账/TestCases/最终文档落盘）均可从磁盘 + `st["completed"]` 重算，路径 `set` 去重、无 double-count |
| 「实时」语义 | ⚠ 按需即时重算（非 live 面板） | 每次 `context`/`status` 即时重算 = 最新累计；不做后台自动刷新 |
| 精度 | ⚠ 系统性低于真实会话 | 不含模型推理/聊天正文/工具调用开销；卡片标注「非模型真实会话 token，真实会话请用 `/context`」 |

`_cumulative_footprint(st, spec)` 幂等重算、**不写 state.json 任何新字段**；累计量只在新增的 `context` 命令暴露，`status` 既有 JSON 键保持不变（不破坏任何 status 形状断言）。

### 8.6.4 与既有"预算纪律"的一致性

`##CONTEXT_BUDGET##` **永不含**缩减用例集 / 跳阶段 / 放宽门禁的指令——对齐既有「预算只决定怎么写、永不决定写哪些」的反缩减硬条款。估错只影响提示早晚、不影响正确性（advisory 不参与门禁）。

---

## 9. 跨平台文件锁 `locking.py`

跨平台 advisory FileLock，仅 Python 标准库（与 `state_store.py` 仓库策略一致）：

- POSIX：`fcntl.flock(LOCK_EX|LOCK_NB)` + 退避重试；Windows：`msvcrt.locking(LK_NBLCK, 1)` + 重试。
- 锁文件 = `<被保护资源路径> + ".lock"`；`with` 块进出，**fd 关闭即释放（进程崩溃也释放，崩溃安全）**。
- 超时抛 `LockTimeout`。
- 当前 MANIFEST 与三 KB 文件使用（多需求共享可变资源）；状态分区后无并发写者，**state.json 不需要锁**。
- RC33：锁文件在释放时 `os.unlink` 清理，避免残留 `.lock` 堆积。

---

## 10. 向后兼容与迁移

### 10.1 schema 演进

`SCHEMA_VERSION`：1 → 2（v0.7.0 加 `artifacts`/`gate_rounds`，兼容补字段）→ **3**（v0.9.0 无字段变更，仅版本标记，让降级可检测）。

### 10.2 惰性迁移 `migrate_legacy_state`

旧 `case-design-out/.runtime/state.json` → `.qamaster/case-design/<req_id>/`（在 `bootstrap`/`start`/`_load_or_die` 触发，幂等、崩溃安全）：

- req_id 非空 → 连同 checkpoint 一起迁移，升版本到 3；
- req_id 为空 → **拒绝自动迁移**（归属不明）并告警，需人工 `reset --legacy` 清理；
- 仅 case-design workflow 有 legacy 路径，其它 workflow no-op；
- 旧 `.runtime/` 迁移后**保留**（不自动删用户数据），由 `reset --legacy` 显式清理。

### 10.3 会破坏的（随本次一起修）

旧 `commands/case-design.md`（需配合同发更新）；`set --req-id`（移除——消除危险的状态目录迁移操作，req_id 由 bootstrap 派生、start 确定、不可后改）；旧 checkpoint 字面路径引用（机械改为分区路径）；`test_runtime.py` 路径假设。

---

## 11. 复查校正 C1-C8（落地要点）

二次核对源码确认架构方向无误，落地时修正的 8 处实现细节（均已实现并有测试覆盖）：

| # | 问题 | 修正 |
|---|---|---|
| C1 | MANIFEST gate-check 时序死锁 | Phase 0/13 移除 `exists MANIFEST.md`（§7.4） |
| C2 | `_audit_degraded_artifacts` 跨需求误报 | glob 限定当前 `req_id`（§4.4） |
| C3 | `P.` 模块级引用 → 通用引擎下须随 workflow 变 | 各 cmd 顶部 `spec=get_workflow()`，`P.X` 改 `spec.X`，`_run_check` 加 `spec` 参 |
| C4 | `_card` 的 req_id fallback 文案死分支 | req_id 恒非空（来自 bootstrap），空即报错 |
| C5 | `status` 裸调用歧义 | `--req-id` 与 `--all` 二选一，裸调用报错指引 |
| C6 | legacy 迁移调用点 + workflow 限定 + 兜底 | 非 case-design no-op；加 `manifest reconcile` 兜底 gate PASS 成功但 add 锁超时失步 |
| C7 | Phase 0 重复 `produces` 键 | 合并为单一 `produces` |
| C8 | `start` resume 须按 req_id 精确恢复 | 分区路径即 resume 判据；RESUME 后 created_at 不变 |

---

## 12. CLI 命令总览（`qamaster_runtime.py main()`）

| 命令 | 作用 | 关键参数 |
|---|---|---|
| `bootstrap` | 派生 req_id（不创状态，幂等） | `--user-input` / `--req-id` |
| `start` | 启动/恢复流程（req_id 必需） | `--req-id`(必需) `--mode` `--fresh` |
| `status` | 查看状态 | `--req-id` 单需求 \| `--all` 全量 |
| `context` | 打印当前需求工作集 token 估算 + 累计足迹（只读，无状态写入） | `--req-id`(必需) |
| `next` | 推进下一阶段（须当前阶段已过 gate） | `--req-id` |
| `gate` | 执行当前阶段出口门禁 | `--req-id` |
| `confirm` | 人工门：用户已确认/答复/许可 | `--req-id` |
| `reject` | 人工门：拒绝/退回 | `--req-id` |
| `fail` | 回退到更早阶段 | `--to` `--reason` |
| `patch` | 增量反哺（G-FB1：不回退，登记前置产物修正指令） | `--to` `--reason` `--clear` |
| `set` | 登记判定/意图（**无 `--req-id`**） | `--depth` `--input-kind` `--mode` `--knowledge` `--excel` |
| `manifest` | MANIFEST 维护（Runtime 独占） | `add`/`update`/`complete`/`list`/`reconcile` |
| `kb` | 自我进化知识库维护（Runtime 独占） | `list`/`show`/`query`/`distill`/`reconcile`/`add-lesson`/`add-expert`/`endorse`/`supersede`/`prune` + `--kind` |
| `plan` | 打印执行计划 | `--req-id`(可选) |
| `verify` | 离线自证校验 | `--req-id` |
| `reset` | 删分区状态（不影响产物） | `--req-id` \| `--legacy` |

所有命令默认 `--workflow case-design`、`--workdir` 默认当前目录。`/case-design` 入口内部链式跑 `bootstrap → start`，用户无感。`--workflow requirement-review` 时同一命令族路由到第二 workflow 的状态机/产物目录/门禁。

---

## 13. 验证体系

`scripts/test_runtime.py` 全套断言（v0.11.13 达 **434 项**），含并发/迁移/索引/自我进化知识库/上下文防护测试：

- `test_concurrent_reqs`：同 workdir 两 req 各推进到 Phase 2，断言 state/checkpoint 互不覆盖，audit 不误报对方用例，MANIFEST 两行共存，`status --all` 列出两 req（**并发的核心证明**）。
- `test_requirement_review_concurrent_reqs`：同 workdir 两需求并发评审，断言门禁 req_id 隔离（A 的 REQ/问题清单不误放行 B 的门）、状态分区独立、`requirement-review-out/MANIFEST.md` 两行共存、`status --all` 列出两 req（requirement-review 多需求并发的核心证明）。
- `test_manifest_concurrent_update`：12 线程并发 `manifest update`，无损坏无丢行。
- `test_phase0_manifest_created_on_pass`：空 MANIFEST 下 Phase 0 gate PASS 后 MANIFEST 被创建（验证 C1 时序）。
- `test_legacy_migration`：v2+req_id 旧 state 迁移到新分区；req_id 为空拒绝迁移并告警。
- `test_bootstrap_idempotent`：重复 bootstrap 输出 RESUME 且不创状态、created_at 不变。
- `test_manifest_reconcile`：删 MANIFEST 后从磁盘文件重建索引。
- `test_context_budget_guard`：默认零输出（小需求卡片不含 `##CONTEXT_BUDGET##`）、大 REQ 越线才提示（含压缩/PART）、Phase 8/13 与 requirement-review Phase 5/6 出 `/compact` 提示、轻阶段不出、`context` 命令字段齐全、累计幂等（重跑相等）且单调（落盘后输出增）、`status` 输出不含 `cumulative` 键（既有形状不变）。

回归护栏 `scripts/check_plugin.py`：校验 `locking.py`/`manifest.py`/`kb_store.py`/`requirement_review_phases.py`/`workflows/{__init__,registry,case_design,requirement_review}.py` 存在、`bootstrap`/`manifest`/`kb` 子命令存在、SKILL 文本不含 `Write/Edit(MANIFEST.md)` 权限示例；另校验 requirement-review 阶段机连续 0-7、Phase 4=confirm、Phase 7=auto、无 license 门；README 断言计数一致性护栏。

最终状态：`py_compile runtime/*.py runtime/workflows/*.py` 通过；`check_plugin.py` rc=0；`test_runtime.py` 434 通过 / 0 失败。

---

## 14. 迁移实施路线

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1 | Runtime Core：状态机 + 门禁 + 契约卡（v1.0.0 落地） | ✅ 已完成 |
| Phase 2 | 门禁前移（3/5/7/8/10）+ 制品传递（PHASE_GATE_DESIGN） | ✅ 已完成 |
| Phase 2.5 | 覆盖率四道硬门 + 设计文档追溯（COVERAGE_HARDENING_DESIGN） | ✅ 已完成 |
| Phase 3 | 多需求并行 + 通用 workflow 引擎 + MANIFEST Runtime 接管（v2.0.0） | ✅ 已完成 |
| **Phase 4** | **requirement-review 全状态机迁移（第二 workflow）+ 自我进化知识系统（经验/业务/专家三库）（本文 v2.1.0）** | **✅ 已完成** |
| **Phase 4.5** | **requirement-review 完整多需求并行评审（门禁 req_id 隔离 + 独立 MANIFEST 聚合索引）（本文 v2.2.0）** | **✅ 已完成** |
| Phase 5 | interface-test 新 skill；Phase dict→dataclass；跨 workflow 共享索引 | 后续 |

---

## 15. 后续方向

- **interface-test 新 skill**：注册新 WorkflowSpec，接口自动化测试继承隔离 + 强控（复用 requirement-review 已证实的扩展点）。
- **Phase dict → dataclass 化**：`phases.py` 阶段定义结构化，提升类型安全（当前保留 dict 形状，最小改动）。
- **跨 workflow 共享索引**：MANIFEST 当前按产物目录隔离，后续可演进为跨 workflow 统一索引。
- **知识系统延伸**：KB 相关性门的 surface 词表可扩展到 interface-test 等新 workflow；`kb query` 已支持预览，后续可加"注入命中统计"可观测性。
- **上下文可观测性深化**：`context` 命令当前输出 qamaster 足迹估算；若 Claude Code 后续向子进程暴露真实会话 token 计数（或提供官方 API），可把「足迹估算」升级为「真实会话计量」——`_budget_snapshot`/`_cumulative_footprint` 的接口已为此预留（估算函数与渲染层解耦）。
- **Multi-Agent Runtime / Observability**：BA/PM/QA/Architect/Risk Agent 由 Runtime 调度；执行日志/阶段耗时/模型调用记录/质量指标（v1.0.0 愿景，待条件成熟）。

---

## 最终目标

qamaster 从"依赖模型理解流程的 Skill"升级为"由 Runtime 控制流程、模型执行任务、任何模型不可绕过"的企业级 Agent 系统，并支持同工程多需求并行、跨需求自我进化。

核心原则不变：**Runtime 控制流程，模型执行任务，任何模型不可绕过。** v2.1.0 在 v2.0.0 基础上把"不可绕过"进一步延伸：从状态层（state.json 单写、门禁机器判定）到索引层（MANIFEST 由 Runtime 在 gate PASS 副作用维护）再到知识层（三 KB 由 Runtime 独占维护、模型禁写），通过状态分区让"多需求并行、互不干扰"成为引擎内建能力，通过通用 workflow 引擎让第二个 skill（requirement-review）继承同一套隔离 + 强控。v2.2.0 补齐 requirement-review 的多需求并行：门禁 req_id 绑定（`{req_id}` 占位）+ 独立 MANIFEST 聚合索引（`manifest.py` 按 workflow schema 泛化），使第二 workflow 也具备"同工程多需求并行、互不串扰"的完整能力，且对 case-design 零影响。v2.3.0 把防护边界扩展到上下文维度：补一层**建议性、可度量、默认零输出**的上下文/token 防护（阈值门控 `##CONTEXT_BUDGET##` + `context` 只读诊断 + 累计足迹），在「模型负责思考」的前提下由 Runtime 提供越线提示与可观测性，且对 case-design / requirement-review 既有功能零影响。
