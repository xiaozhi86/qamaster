# qamaster Agent Runtime Engineering 重构详细设计方案

版本：v2.0.0
日期：2026-08-08
作者：xiaozhi

> **一句话定位**：把 qamaster 从"依赖模型理解流程的 Skill"升级为"由 Runtime 严格控制、模型只负责思考、任何模型不可绕过"的企业级 Agent 系统，并支持**同工程多需求并行、互不干扰**。
>
> 核心原则：**模型负责思考，Runtime 负责控制。流程通过 Runtime 严格控制，与模型无关。**

---

## 0. 版本演进说明（v1.0.0 → v2.0.0）

| 版本 | 内容 | 状态 |
|---|---|---|
| v1.0.0 | 早期愿景：`engine/gate/validator/memory` 分目录、yaml 流程定义、`state/runtime-state.json` | 已被更务实的实现取代，**保留为历史愿景** |
| **v2.0.0** | 校正到**真实落地架构**（单控制器 + 注册表 + 分区状态），并新增三大改造：① 多需求并行；② 通用 workflow 引擎；③ MANIFEST 多需求索引协调权回归 Runtime（强化"与模型无关"） | **当前权威设计** |

**v1.0.0 为何被取代**：原愿景的分目录（engine/gate/validator/memory）与 yaml 流程定义在实践中偏重，最终按"一个 workflow 无关控制器 + 一个阶段注册表 + 分区状态存储"的务实结构落地。v2.0.0 的首要工作是**让设计文档与真实代码对齐**（v1.0.0 的目录结构从未实现，长期是文档与代码的悬空）。

**与两份细化设计的关系**（互补、不互斥，本文是总览）：

- [`skills/case-design/PHASE_GATE_DESIGN.md`](skills/case-design/PHASE_GATE_DESIGN.md) — 门禁前移（Phase 3/5/7/8/10 出口 gate 由 runtime 强制）+ 跨阶段制品传递（state.json `artifacts` 注册表 + 契约卡 `PRIOR_ARTIFACTS` 注入）。
- [`COVERAGE_HARDENING_DESIGN-v1.0.0.md`](COVERAGE_HARDENING_DESIGN-v1.0.0.md) — 覆盖率四道硬门（需求条目 + 测试点 + 风险 + 安全）+ 设计文档作为正式追溯源。

本文（v2.0.0）描述**流程控制层**的整体架构与多需求并行机制；上面两份描述**质量门禁层**的细节。两层共同兑现"Runtime 控制流程、模型执行任务"。

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
| 业务规范 | 阶段细则、避坑红线、输入协议、运行模式、质量标准 | `skills/case-design/SKILL.md` + `references/*.md` |
| 流程控制 | 状态机、契约卡、门禁裁决、状态分区、MANIFEST 协调 | `runtime/{state_store,phases,qamaster_runtime,manifest,locking}.py` + `runtime/workflows/` |
| 客观校验 | 机器可判定的检查（结构/内容/覆盖/门禁前移） | `skills/case-design/scripts/{verify_md,verify_cases,gen_excel,verify_knowledge}.py` + `config/validation_rules.json` |

原则不变：**模型负责思考，Runtime 负责控制。** 业务规则以 SKILL.md + references 为唯一细则来源（铁律 3），Runtime 只做流程控制。

---

## 3. 目录设计（真实落地，v2.0.0 校正）

```
qamaster/
├─ .claude-plugin/plugin.json          # 插件清单
├─ commands/case-design.md             # /case-design 入口（内部链式 bootstrap → start）
├─ skills/case-design/                 # 业务规范层
│  ├─ SKILL.md                         # 全局规范 + 五条铁律 + Runtime 控制协议
│  ├─ references/*.md                  # 各阶段细则（0~15 + 知识沉淀）
│  ├─ scripts/                         # 客观校验脚本（verify_md/verify_cases/gen_excel/...）
│  └─ config/validation_rules.json     # 校验单一事实源
├─ runtime/                            # 流程控制层（workflow 无关引擎）
│  ├─ qamaster_runtime.py              # 控制器：bootstrap/start/status/next/gate/confirm/...
│  ├─ state_store.py                   # 状态分区存储 + 迁移（SCHEMA_VERSION=3）
│  ├─ phases.py                        # case-design 阶段机（0-15，单一事实源）
│  ├─ manifest.py                      # MANIFEST.md 的 read-modify-write（Runtime 独占）
│  ├─ locking.py                       # 跨平台 FileLock（msvcrt/fcntl，stdlib）
│  └─ workflows/
│     ├─ registry.py                   # WorkflowSpec 数据结构 + 注册表
│     └─ case_design.py                # phases.py → WorkflowSpec 适配层（显式 register）
├─ case-design-out/                    # 产物层（用户工程运行时生成，向后兼容）
│  ├─ REQ_<id>.md / TestCases_<id>*.md / Clarification_Ledger_<id>.md
│  ├─ Knowledge_<id>.md / DESIGN_<id>.md / TestCases_<id>.xlsx
│  └─ MANIFEST.md                      # 多需求共享索引（Runtime 锁控·模型禁写）
└─ .qamaster/                          # Runtime 控制层根（gitignore，按 workflow/req_id 分区）
   └─ case-design/<req_id>/
      ├─ state.json
      └─ checkpoint_<N>.md
```

> 与 v1.0.0 的差异：v1.0.0 写的 `runtime/engine|gate|validator|memory/`、`workflow/case-design-flow.yaml`、`state/runtime-state.json` **均未实现**；真实结构是上图的"控制器 + 注册表 + 分区状态"。v2.0.0 以此为准。

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

**唯一例外**：`case-design-out/MANIFEST.md` 是多需求共享可变资源，需锁——见 §8。

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

### 5.3 新增 skill 扩展点（Day-2）

新增独立 skill 只需：在 `runtime/workflows/` 加 `<name>.py` 构造一份 `WorkflowSpec` 并 `register()`，在控制器 `main()` 调用它。控制器按 `--workflow` 路由取 `get_workflow(name)`，状态路径、产物目录、契约卡、门禁全部由 spec 驱动，**无需改控制器**。`phases.py` 保持 case-design 专属（不强行 dataclass 化，最小改动）。

> Day-1 不为 requirement-review 建状态机，仅留注册占位；requirement-review 全状态机迁移与 interface-test 新 skill 列入后续（§15）。

---

## 6. Runtime Core：状态机与门禁

### 6.1 state.json 字段（`state_store.new_state`，SCHEMA_VERSION=3）

```
schema=3, workflow, req_id, workdir,
current_phase, completed[], status,
run_mode(full|auto|light), depth(heavy|medium|light), input_kind(requirement|contract),
skipped_phases[], failed_gates{}, confirm_rounds, gate_rounds{}, artifacts{},
history[], created_at, updated_at, (excel, knowledge 后置)
```

**status 枚举**：`RUNNING`（未过出口门）/ `GATE_PASSED`（已过，可 next）/ `WAIT_USER_CONFIRM`（人工门待答复）/ `WAIT_LICENSE`（Excel 许可待答复）/ `REVIEW_PENDING`（连跑/轻量人工门已标注待审、自动放行）/ `DONE`。

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

`next` 强校验：`RUNNING`/`WAIT_*` 状态直接 `RUNTIME_ERROR`，**跳阶段不可能**。auto 门 FAIL 时 `gate_rounds[phase]+=1`，≥3 次强制人工介入提示（有界返修，堵 silent infinite-retry），并回显"禁止以任何理由绕过本门禁交付"。

---

## 7. 模型无关协议与五条铁律（强化）

### 7.1 五条铁律（SKILL.md，违反即判定执行缺陷）

1. **状态以 Runtime 为准**：每次接到用户新消息先 `status --req-id <id>` 恢复权威状态，禁止凭对话记忆推断"现在该哪一步"。
2. **门禁以机器判定为准**：`gate` 的 PASS/FAIL 由确定性检查与脚本退出码给出；禁止模型自证"已通过"（声明≠核实）。
3. **业务规范不变**：Runtime 只做流程控制；避坑红线/输入协议/运行模式/质量门禁/输出协议全部以 SKILL.md + references 为唯一细则来源。
4. **MANIFEST 由 Runtime 维护**（v2.0.0 强化）：多需求共享索引由 Runtime 在 gate PASS 时自动维护，模型**禁止 Write/Edit MANIFEST.md**——多需求索引的协调权属于 Runtime。失步时 `manifest reconcile` 重建。
5. **gate FAIL 明细自查通道**：`detail` 有上限，截断时模型必须直接跑 verify_cases.py 拿全量 stdout 自查，不得盲改。

### 7.2 MANIFEST 作为 gate-PASS 确定性副作用（铁律 4 的落地）

模型被剥夺对 MANIFEST 的写权限后，MANIFEST 的所有变更都成为**gate PASS 的确定性副作用**，在每条 PASS 路径上由 Runtime 在 `FileLock` 下执行（`_manifest_side_effect`）：

| 触发点（gate PASS） | Runtime 副作用 |
|---|---|
| Phase 0（需求落盘） | `manifest add`（从 `REQ_<id>.md` 首个 `#` 标题抽需求名称） |
| Phase 1（澄清完成） | `manifest update`（台账文件列） |
| Phase 13（写盘回读通过） | `manifest update`（glob `TestCases_<id>*.md` 实际落盘文件列） |
| Phase 14（审核通过 confirm） | `manifest complete`（置已完成） |

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

- **资源**：`<workdir>/case-design-out/MANIFEST.md`；锁文件 `.manifest.lock`（同目录）。
- **所有权**：`runtime/manifest.py` 是唯一 read-modify-write 路径；`cmd_manifest` 全程持 `FileLock(timeout=30)`，写用 tmp + `os.replace` 原子替换。
- **列**：需求标识 | 需求名称 | 需求文档 | 设计文档 | 台账文件 | 测试用例文件 | 知识总结 | 状态 | 更新时间。
- **子命令**：`add`（插新行，重复报错）/ `update`（改指定列，幂等）/ `complete`（置已完成）/ `list`（只读 JSON）/ `reconcile`（从磁盘重建兜底）。
- **模型权限**：明确禁止 `Write/Edit(MANIFEST.md)`（铁律 4）；`check_plugin.py` 加回归护栏 `re.search(r"(Write|Edit)\([^)]*MANIFEST\.md", skill_text)` 命中即报错。
- **为何强化"与模型无关"**：MANIFEST 变更成为 gate PASS 的确定性副作用，模型无法影响多需求索引的协调——"Runtime 负责控制"从状态层延伸到索引层。

---

## 9. 跨平台文件锁 `locking.py`

跨平台 advisory FileLock，仅 Python 标准库（与 `state_store.py` 仓库策略一致）：

- POSIX：`fcntl.flock(LOCK_EX|LOCK_NB)` + 退避重试；Windows：`msvcrt.locking(LK_NBLCK, 1)` + 重试。
- 锁文件 = `<被保护资源路径> + ".lock"`；`with` 块进出，**fd 关闭即释放（进程崩溃也释放，崩溃安全）**。
- 超时抛 `LockTimeout`。
- 当前仅 MANIFEST 多需求协调使用；状态分区后无并发写者，**state.json 不需要锁**。

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
| `next` | 推进下一阶段（须当前阶段已过 gate） | `--req-id` |
| `gate` | 执行当前阶段出口门禁 | `--req-id` |
| `confirm` | 人工门：用户已确认/答复/许可 | `--req-id` |
| `reject` | 人工门：拒绝/退回 | `--req-id` |
| `fail` | 回退到更早阶段 | `--to` `--reason` |
| `set` | 登记判定/意图（**无 `--req-id`**） | `--depth` `--input-kind` `--mode` `--knowledge` `--excel` |
| `manifest` | MANIFEST 维护（Runtime 独占） | `add`/`update`/`complete`/`list`/`reconcile` |
| `plan` | 打印执行计划 | `--req-id`(可选) |
| `verify` | 离线自证校验 | `--req-id` |
| `reset` | 删分区状态（不影响产物） | `--req-id` \| `--legacy` |

所有命令默认 `--workflow case-design`、`--workdir` 默认当前目录。`/case-design` 入口内部链式跑 `bootstrap → start`，用户无感。

---

## 13. 验证体系

`scripts/test_runtime.py` 全套断言（v2.0.0 达 122 项），含本次新增的并发/迁移/索引测试：

- `test_concurrent_reqs`：同 workdir 两 req 各推进到 Phase 2，断言 state/checkpoint 互不覆盖，audit 不误报对方用例，MANIFEST 两行共存，`status --all` 列出两 req（**并发的核心证明**）。
- `test_manifest_concurrent_update`：12 线程并发 `manifest update`，无损坏无丢行。
- `test_phase0_manifest_created_on_pass`：空 MANIFEST 下 Phase 0 gate PASS 后 MANIFEST 被创建（验证 C1 时序）。
- `test_legacy_migration`：v2+req_id 旧 state 迁移到新分区；req_id 为空拒绝迁移并告警。
- `test_bootstrap_idempotent`：重复 bootstrap 输出 RESUME 且不创状态、created_at 不变。
- `test_manifest_reconcile`：删 MANIFEST 后从磁盘文件重建索引。

回归护栏 `scripts/check_plugin.py`：校验 `locking.py`/`manifest.py`/`workflows/{__init__,registry,case_design}.py` 存在、`bootstrap`/`manifest` 子命令存在、SKILL 文本不含 `Write/Edit(MANIFEST.md)` 权限示例。

最终状态：`py_compile runtime/*.py runtime/workflows/*.py` 通过；`check_plugin.py` rc=0；`test_runtime.py` 122 通过 / 0 失败。

---

## 14. 迁移实施路线

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1 | Runtime Core：状态机 + 门禁 + 契约卡（v1.0.0 落地） | ✅ 已完成 |
| Phase 2 | 门禁前移（3/5/7/8/10）+ 制品传递（PHASE_GATE_DESIGN） | ✅ 已完成 |
| Phase 2.5 | 覆盖率四道硬门 + 设计文档追溯（COVERAGE_HARDENING_DESIGN） | ✅ 已完成 |
| **Phase 3** | **多需求并行 + 通用 workflow 引擎 + MANIFEST Runtime 接管（本文 v2.0.0）** | **✅ 已完成** |
| Phase 4 | requirement-review 全状态机迁移；interface-test 新 skill；Phase dict→dataclass；跨 workflow 共享索引 | 后续 |

---

## 15. 后续方向

- **requirement-review 全状态机迁移**：从注册占位升级为独立 WorkflowSpec，复用本引擎的分区/锁/门禁。
- **interface-test 新 skill**：注册新 WorkflowSpec，接口自动化测试继承隔离 + 强控。
- **Phase dict → dataclass 化**：`phases.py` 阶段定义结构化，提升类型安全（当前保留 dict 形状，最小改动）。
- **跨 workflow 共享索引**：MANIFEST 当前按产物目录隔离，后续可演进为跨 workflow 统一索引。
- **Multi-Agent Runtime / Observability**：BA/PM/QA/Architect/Risk Agent 由 Runtime 调度；执行日志/阶段耗时/模型调用记录/质量指标（v1.0.0 愿景，待条件成熟）。

---

## 最终目标

qamaster 从"依赖模型理解流程的 Skill"升级为"由 Runtime 控制流程、模型执行任务、任何模型不可绕过"的企业级 Agent 系统，并支持同工程多需求并行。

核心原则不变：**Runtime 控制流程，模型执行任务，任何模型不可绕过。** v2.0.0 把"不可绕过"从状态层（state.json 单写、门禁机器判定）延伸到索引层（MANIFEST 由 Runtime 在 gate PASS 副作用维护），并通过状态分区让"多需求并行、互不干扰"成为引擎内建能力。
