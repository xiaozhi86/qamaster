# Changelog - case-design

本文件记录 case-design skill 的版本变更。

---

# 发布说明（面向使用者）

## v0.9.0（2026-08-08，多需求并行 + 通用 Workflow 引擎 + MANIFEST 收归 Runtime）

**本次发布解决单工程只能处理一个需求、且 MANIFEST 索引由模型维护两大架构缺口**。v0.6–v0.8 把质量门禁/覆盖硬门/阶段出口校验逐层代码化；v0.9.0 把"流程控制层"本身从单例改造为按需求分区，并把多需求共享索引的协调权从模型收回 Runtime——**强化"流程由 Runtime 严格控制、与模型无关"铁律到索引层**。

**根因**：旧 Runtime 状态固定为 `<workdir>/case-design-out/.runtime/state.json`（单例，只按 workdir 参数化），同工程下两个客户端处理不同需求会在 `state.json` 上互相 clobber（current_phase/req_id 被覆盖）、checkpoint 按阶段号互相覆盖、MANIFEST"整表 Write"丢行。Phase 0 既派生 req_id 又写 REQ.md，存在"先有鸡还是先有蛋"。

**核心修复一：状态按 (workflow, req_id) 分区（无锁隔离）**
- `state_store.default_state_path(workdir, workflow, req_id)` → `<workdir>/.qamaster/<workflow>/<req_id>/state.json`：每个在途需求独立 state.json + checkpoint 目录，**无需锁即可避免 clobber**；`save()` 的原子 `os.replace` 保留（仅防单写者中断/AV 锁）。
- 新增 `list_active_reqs`（供 `status --all` + bootstrap 碰撞检查）；新增 `migrate_legacy_state`（旧 `.runtime/state.json` 惰性迁移到分区路径，req_id 非空迁移、空则拒绝并保留原处待 `reset --legacy`，幂等崩溃安全）；`SCHEMA_VERSION` 2→3。

**核心修复二：req_id 派生协议（bootstrap → start，消除先有鸡还是先有蛋）**
- 新 `bootstrap` 子命令：从文件路径（经 `extract_doc.py`）/内联文本派生 req_id（清洗 CJK+alnum+`-`、碰撞加 `-YYYYMMDD`），**不创建状态**（幂等可重跑）；检测到在途状态输出 `RESUME`（start 走 resume 分支不重建，C8：created_at 不变）。
- `start --req-id` 改为**必需**；`commands/case-design.md` 内部链式 `bootstrap → start`，对用户单步透明。`set --req-id` **移除**（消除阶段内改 req_id 的危险目录迁移）。

**核心修复三：MANIFEST 收归 Runtime（铁律 4 强化）**
- 新 `manifest` 子命令（`add/update/complete/list/reconcile`），全程在跨平台 `FileLock`（`runtime/locking.py`，msvcrt/fcntl，stdlib）下 read-modify-write（原子 `os.replace`），多需求并发更新不损坏不丢行。
- **gate-PASS 确定性副作用**：Phase 0 PASS→`add`（需求名称从 `REQ_<id>.md` 首个 `#` 标题自动抽取）；Phase 1 confirm→`update` 台账列；Phase 13 PASS→`update` 用例文件列（glob `TestCases_<id>*.md`）；Phase 14 confirm→`complete`。模型**禁止 Write/Edit MANIFEST.md**；失步 `manifest reconcile` 从磁盘 `REQ_/TestCases_` 重建（C6 兜底）。
- C1：从 Phase 0/13 `gate_checks` 移除 `exists MANIFEST.md`（MANIFEST 是 Runtime 产物，不再是模型门禁责任）；C2：`_audit_degraded_artifacts` glob 限定当前 req_id，多需求下不误报对方用例。

**核心修复四：通用 Workflow 引擎（扩展点）**
- 新 `runtime/workflows/`（`registry.py` WorkflowSpec + register/get_workflow；`case_design.py` 适配 `phases.py`）。新 skill 注册自己的阶段机即继承隔离 + 强控；状态路径 `<workdir>/.qamaster/<workflow>/<req_id>/` 天然隔离不同 skill。`--workflow` 路由（默认 case-design 向后兼容）；显式 `register()`（无 import 副作用）。

**清理**：删除空的 `runtime/transaction/`（WAL 不再需要，`FileLock + os.replace` 足够）。

**变更文件**：`runtime/locking.py`、`runtime/manifest.py`、`runtime/workflows/{__init__,registry,case_design}.py`（新）；`runtime/{state_store,phases,qamaster_runtime}.py`（分区/迁移/bootstrap/manifest/gate 副作用/C1-C8）；`commands/case-design.md`、`skills/case-design/SKILL.md`、`references/{phase0_manifest,modeling,dedup_coverage,output_write}.md`、`scripts/{test_runtime,check_plugin}.py`、`.gitignore`、`AGENTS.md`、`README.md`、本 CHANGELOG。

**升级方式**：`git pull` 后跑 `python scripts/test_runtime.py`（122 项全过）与 `python scripts/check_plugin.py`。已有 `.runtime/state.json`（schema≤2 + req_id 非空）在首次 `start` 时自动迁移到分区路径；req_id 为空需 `reset --legacy` 清理。已有合规用例集不受影响。

---

## v0.8.0（2026-08-05，覆盖率硬门加固 + 设计文档追溯源 + 契约驱动触发放宽）

**本次发布解决覆盖率校验维度不足 + 设计文档非正式追溯源两大缺口**（设计依据 `COVERAGE_HARDENING_DESIGN-v1.0.0.md`）。v0.7.0 闭环了"引用悬空/编号跳号/台账传递/待确认泄漏"；v0.8.0 闭环 v0.7.0 未覆盖的三个缺口：**测试点级覆盖无硬门、设计文档测试要点非正式追溯源、critique 不扫安全/脱敏盲区**。

**根因复盘（电销通话AI总结产物第二轮评审）**：36 个测试点只覆盖 30 条用例静默通过、设计文档 A §8（11 条测试要点）覆盖 82%、设计文档 B §6（24 条测试要点）只覆盖 54%、P0 安全脱敏 0 覆盖、接口 2/3 契约类因未启用契约驱动分支而失守——全部"Phase 13 exit=0 通过"，因为 `coverage_gates` 硬门清单只有 req_trace/interface_three_class/risk_p0p1 三项，**没有测试点覆盖/设计文档测试要点/安全覆盖**三门。

**核心修复一：coverage_gates 三硬门扩展为六硬门**
- **#7-H 测试点追溯硬门**（`testpoint_coverage`）：TP 清单每条须被用例关联规则列引用，比例 < `tp_trace_min_ratio`（默认 1.0）→ exit=1。闭合 36→30 压缩（`verify_cases.py::coverage_gate_failures` 加 TP 分支；既有 `testpoint_coverage()` 函数从软提示升硬门）。
- **#8-H 设计文档测试要点追溯硬门**（`design_doc_testpoints_trace`）：DESIGN 文档"测试要点"章节每条须被用例"关联规则/用例名称"列覆盖 → exit=1。新增 `check_design_doc_testpoints`/`parse_design_testpoints`/`design_doc_testpoints_trace` 函数。
- **safety_coverage 安全覆盖硬门**：涉敏感数据（REQ/DESIGN 含手机号/身份证/银行卡/财务/脱敏/verifyAuth/token 等信号）时须有 ≥1 条测试类型=安全的用例 → exit=1。新增 `safety_coverage_gate`/`involves_sensitive_data` 函数 + `sensitive_signals` 词表。

**核心修复二：设计文档升级为正式追溯源**
- SKILL.md §5 新增【设计文档】可选输入通道；phase0_manifest.md 步骤零落盘 `DESIGN_<需求标识>.md`；索引文件增"设计文档"列。
- verify_cases.py 全入口（main/`--phase-gate`/`run_inmemory`/`collect_all_findings`）增 `--design`/`design_doc_lines` 参数链路。

**核心修复三：契约驱动分支触发条件放宽**
- phase0_manifest.md 步骤六：从"只认 Swagger/OpenAPI"放宽到"设计文档含接口描述（接口名/facade/方法签名/入参出参/错误码/@Service/@RestfulApi/Dubbo 方法）亦触发"。SKILL.md §159 同步。闭合 requirement 驱动下接口 2/3 契约类测试点失守。

**核心修复四：Phase 8 出口 gate 也判覆盖硬门**
- `verify_cases.py` run_phase_gate：覆盖硬门判定从 `Phase in (10,13)` 扩展到 `Phase in (8,10,13)`，写前 gate 即拦 TP/安全缺口。

**verify_summary_line 新增字段**：`tp_total`/`tp_uncovered`/`design_total`/`design_uncovered`/`safety_fail`。

**配置**：`config/validation_rules.json` `coverage_gates` 加 `tp_trace_min_ratio`/`design_doc_trace_min_ratio`/`testpoint_coverage`/`design_doc_testpoints_trace`/`safety_coverage`；`phase_gate_map` Phase 8/10/13 加对应检查子项；新增 `sensitive_signals` 词表。

**与既有约束的相容性**：既有合规用例集（无 DESIGN 文件）在新门禁下 `design_doc_testpoints_trace` SKIP、`safety_coverage` 不触发敏感信号时 SKIP、`testpoint_coverage` 在 TP 全覆盖时 PASS——不误伤。

**Phase B（P1·方法论补强·已落地）**：
- `references/dedup_coverage.md`：§17 新增 #7 反向测试点追溯 + #8 反向设计文档测试要点追溯；#5 行为来源三选一升级四选一（加设计文档）；§18 停止条件机器前提加 #7-H/#8-H/safety_coverage。
- `references/coverage.md`：§8 新增 8.11 设计文档测试要点覆盖；§8.9 安全场景补 safety_coverage 硬门说明；§15.2/15.3 维度列表加"设计文档测试要点"。
- `references/risk.md`：P0 列表补"敏感信息脱敏"；§5 critique 高发漏标方向新增"安全/脱敏"+"设计文档测试要点"两个专项。
- `references/selfcheck.md`：检查3 升级 TP 级 + 加契约/安全维度；检查8 P0 加"安全漏洞/敏感信息脱敏"；检查14 对抗生成五类盲区新增"安全风险遗漏"；新增检查17"设计文档测试要点覆盖率"；自查决策表加检查17。
- `references/modeling.md`：规则建模来源三选一升级四选一（加设计文档）；SDD 事实来源加设计文档；接口契约模型触发放宽（设计文档含接口描述也触发）。

---

## v0.7.0（2026-08-04，阶段门禁前移 + 制品传递 + 反向引用/台账接入）

**本次发布解决两个流程控制缺口**（设计依据 `skills/case-design/PHASE_GATE_DESIGN.md`）：
1. **跨阶段制品靠模型记忆传递**——runtime 现携带制品注册表，契约卡注入 PRIOR_ARTIFACTS，上下文裁剪不丢；
2. **中间阶段橡皮章 + 机器兜底集中在写盘后**——检查从 Phase 13 写盘后才跑，前移到 Phase 3/5/7/8/10 各阶段出口由 runtime 强制（`verify_cases.py --phase-gate <N>`）。

**根因复盘（电销通话AI总结产物评审）**：D1 悬空引用(R26/R28)、D2 编号跳号(TP7)、C3 用例违背台账(Q4 放行 vs 丢弃)、C2 待确认项泄漏(Q5)、G3/G4/G8 台账事实未传成用例——全部"Phase 13 exit=0 通过"，因为 `verify_cases.py` 只查 section→case 不查 case→section、不读台账、不查编号连续性。

**核心修复一：verify_cases.py 检查项加固**（exit=1 硬门 + 软探针）
- **项1 反向引用完整性** `check_citation_resolution`：用例关联规则列引用的 R/RK/TP/API/SC 须在清单内真实存在（闭环 D1）。
- **项2 section ID 连续性** `check_section_id_contiguity`：RK/TP/API/SC 编号无跳号（闭环 D2）。
- **项3 假设标签对账** `check_assumption_resolution`：`假设A<n>` 须在假设清单内登记（闭环 RC7）。
- **项4 台账接入** `parse_clarification_ledger` + `check_ledger_propagation`(5.5a 台账事实→用例覆盖) + `check_open_questions_gate`(5.5b 待确认门禁) + 一致性事实源(5.5c)：直击 RC0（校验器不读台账）。
- **项5 行为一致性** `check_behavior_consistency`：用例断言与台账事实反义词矛盾嫌疑（闭环 C3·软）。
- **项6 关键词覆盖探针** `keyword_coverage_probe`：非台账点(异步/脏payload/端点)覆盖（闭环 G5/G6/G7 + RC6）。
- **项8 REQ 缺失门禁** `check_req_presence`：REQ 缺失/不可解析 exit=1（补 v0.6.0 拘留）。

**核心修复二：门禁前移 + 制品传递（runtime）**
- `state_store.py`：schema 1→2，增 `artifacts` 制品注册表 + `gate_rounds` 有界返修计数（schema=1 向后兼容）。
- `phases.py`：各阶段增 `consumes` 依赖图；Phase 3/5/7/8/10 填 `gate_checks`（`phase_gate` kind，调 `verify_cases.py --phase-gate N`）；Phase 13 增 `--ledger` 参数。
- `qamaster_runtime.py`：契约卡 `_card` 增 PRIOR_ARTIFACTS 段（按 consumes 注入上游制品指针）；`_run_check` 增 `phase_gate` kind + gate PASS 回填 artifacts；`cmd_gate` auto FAIL 计 `gate_rounds`，≥3 次强制人工提示（堵 silent infinite-retry）。
- `verify_cases.py`：增 `--phase-gate <N> <checkpoint>` CLI 模式 + `run_phase_gate`，复用 `collect_all_findings` 保证写前/写后口径一致。

**沉淀检查点机制**：Phase 3/5/7/8/10 结束写 `.qamaster/case-design/<req_id>/checkpoint_<N>.md`（runtime 受控临时件，按 `(workflow, req_id)` 分区隔离，Phase 13 后清理），让沉淀机器可见，不违反"禁止增量写 TestCases.md"红线。

**回归安全**：文件入口 `verify_cases.py <file> [req] [--ledger ..]` stdout/退出码字节级不变（新检查追加在 hard_violations/soft 桶，[FAIL] 行格式一致）；既有合规用例集在新门禁下仍 PASS（仅"覆盖不足/引用悬空/编号跳号/违背台账/待确认泄漏"被拦下）。`test_runtime.py` 由 17 组扩为 19 组（90+ 项全过），新增 [18] phase-gate 7 抓 TP7、[19] phase-gate 8 抓 R28 + 台账门禁抓 Q5。

**变更文件**（8 个）：`verify_cases.py`（+collect_section_ids/检查项/phase-gate 模式）、`config/validation_rules.json`（+citation_resolution/section_contiguity/phase_gate_map/requirement_probe_keywords/source_scope/coverage_gates 扩/behavior_source.antonym_pairs）、`runtime/{state_store,phases,qamaster_runtime}.py`、`scripts/test_runtime.py`（+write_checkpoints/advance_to_phase13 辅助 + 检查点占位）、`SKILL.md`（阶段标注）、本 CHANGELOG、`PHASE_GATE_DESIGN.md`（设计文档）。

**升级方式**：`git pull` 后跑 `python scripts/test_runtime.py`（应全过）与 `python skills/case-design/scripts/verify_cases.py --dump-rules`（确认 citation_resolution/section_contiguity 段）。已有 state.json（schema=1）自动兼容升级；已有合规用例集不受影响。

---

## v0.6.0（2026-08-03，覆盖塌方事故修复）

**本次发布解决一个真实事故**：在一次 case-design 执行中，Runtime 因 Bash 分类器临时不可用而启动失败，模型退回"手动降级"并最终只交付 8 条用例（需求覆盖矩阵 16 条只覆盖 5 条、3 个接口只覆盖 1 个、4 个 P0 风险只覆盖 2 个），却在交付摘要里填写"脚本校验摘要：全部覆盖"。根因是**降级路径无门禁 + 覆盖底线全为软提示 + token 预算条款存在"缩减用例集"歧义**三者叠加。

**核心修复：把覆盖底线从"软提示"升级为"机器硬门"**

`verify_cases.py` 在原有软性提示之外新增三项覆盖硬门（违约即 `exit=1`），口径集中于 `config/validation_rules.json` 的 `coverage_gates`（单一事实源，`domain_config.json` 可覆盖）：

| 硬门 | 口径 | 本次事故中本会拦下 |
| -- | -- | -- |
| #4-H 需求追溯 | REQ 可解析时，需求条目被用例"关联需求ID"列引用比例 ≥ `req_trace_min_ratio`（默认 1.0） | 16 条需求只覆盖 5 条 → FAIL |
| #6-H 接口三类 | 变更影响清单每个接口的契约/规则/场景三类覆盖齐全 | API2/API3 零用例 → FAIL |
| RK P0/P1 风险 | 风险清单全部 P0/P1 须被用例"关联规则"列引用 | 4 个 P0 只覆盖 2 个 → FAIL |

`full`=硬门；`auto_light`=完整模式仍硬、连跑/轻量降为软告警（交付摘要须显式列缺口）；`off`=关闭。

**反编造**：脚本输出末尾固定打印 `##VERIFY_SUMMARY## k=v;...` 机器摘要块，交付摘要与审核话术的"脚本校验摘要"五项**必须逐字段摘自该块**；脚本未运行时一律填"未执行"，填数值即视为声明脚本已运行，声明与实际不符 = 3.1 红线。

**降级协议分两情形（闭合"Runtime 一次故障放大成全程失控"）**：
- 情形A（Runtime 未安装，路径候选全未命中）→ 允许薄客户端降级，但须守"降级最低门禁清单"（降级声明 / verify_md+verify_cases 仍强制经 Bash 跑且 exit=0 / 阶段顺序自证 / 事后对账）；
- 情形B（Runtime 存在但调用失败，如分类器故障）→ **禁止降级**，退避重试至多 3 次，仍失败则暂停流程、**禁止落盘 TestCases**。原则：流程控制可降级，质量门禁不可降级。

**Runtime 侧加固**：`start` 新增"降级产物对账"——检测到 TestCases 存在但 state 缺失/阶段<13 时打印补验警告；`gate` FAIL 文案补"禁止以任何理由绕过本门禁交付（含'脚本暂未运行/先交付后补验/核心用例先行'）"；FAIL 行补捞逻辑保证覆盖硬门 `[FAIL]` 修复指令不被 stdout 尾部缓冲截断。

**规范层闭环**：
- `commands/case-design.md` 路径解析改为候选列表存在性探测（修 `$0` 推导在 marketplace 缓存安装下打错路径）。
- `SKILL.md` token 预算条款补"预算只决定怎么写、永不决定写哪些"反缩减硬条款；交付摘要脚本校验五项加"未执行"合法取值；3.1 红线加"不允许缩减用例集凑 token / 不允许未运行脚本就填数值"。
- `references/output_write.md` 错误做法表加"缩减用例凑预算"行；`dedup_coverage.md` 第18章停止条件加"机器可判前提（覆盖矩阵闭合 + 三硬门通过）"；`selfcheck.md` 检查2/8/16 关联到新硬门；`review_gate.md` 审核话术同步反编造口径；`clarification.md` 补降级模式 P2 未闭环须逐条列清单。

**回归安全**：`test_runtime.py` 由 15 组扩为 17 组（76 项全过），新增 [16] 降级产物对账（3 情形）、[17] 覆盖硬门违约→Phase13 gate FAIL + 补齐后 PASS（证明不误伤全覆盖用例集）。文件入口 stdout 与退出码语义保持（仅在末尾追加覆盖硬门段 + VERIFY_SUMMARY 行；exit 码新增覆盖硬门违约条件）。

**变更文件**（11 个）：`verify_cases.py`（coverage_gates 加载 + coverage_gate_failures + verify_summary_line + dump-rules 投影 + print_findings 末尾段）、`config/validation_rules.json`（+`coverage_gates`）、`runtime/qamaster_runtime.py`（降级对账 + FAIL 文案 + [FAIL] 补捞 + tail 放大）、`scripts/test_runtime.py`（+TC_MD 库存行 + [16][17]）、`commands/case-design.md`（路径候选）、`SKILL.md`、`references/{output_write,dedup_coverage,selfcheck,review_gate,clarification}.md`、本 CHANGELOG。

**升级方式**：本地 `git pull` 后跑 `python scripts/test_runtime.py`（应 76/0 过）与 `python skills/case-design/scripts/verify_cases.py --dump-rules`（确认覆盖硬门段）。已有合规用例集不受影响（三硬门在全覆盖时 PASS）；仅"覆盖不足却自称全覆盖"的产出物会被新硬门拦下。

---

# 发布说明（面向使用者·历史）

> 本节为每个已发布版本的用户视角摘要；下方各版本技术条目面向维护者。两节互补，不重复。

## v0.4.0（2026-07-24，含 v0.3.0 合并发布）

**本次发布解决两个核心问题**：

1. **边界值设计长期漏"边界内"场景**（off-by-one 高发区）：原 3 值模型（最小/最大/临界）中"临界"被重定义为"恰好等于边界点"，与 min/max 重复，`min+1/max-1` 这一档从边界值方法与等价类方法之间漏掉。
2. **"多轮自审纠错"只集中在第11阶段一处、且机器检查要到写后第13阶段才第一次跑**：导致第9去重/第10覆盖率/第11自查/第12展示全在可能有机器可判缺陷的用例集上做白工，写后才发现回头重写。

**新特性一：边界值 4 值模型（v0.3.0）**

边界值由 3 值升级为 4 值，每档独立用例、不得合并：

| 档 | 取值 | 语义 | 预期 |
|---|---|---|---|
| 最小 | min | 边界点 | 应通过 |
| 最大 | max | 边界点 | 应通过 |
| 临界 | 恰好=边界点 | 与 min/max 重叠 | 同上 |
| **边界内** | **min+1 / max-1** | **内邻接，刚好满足约束** | **应通过** |

明确"不得用临界覆盖边界内""不得由等价类兜底"；`verify_cases.py` 边界深度统计扩为 4 档，缺边界内即告警。

**新特性二：阶段出口校验 + agent-loop 式有界纠错（v0.4.0 keystone）**

借鉴 agent loop 的「act → check → repair → re-check」循环结构（有界轮次 + 失败升级），不引入多 subagent critique 形态——机器信号复用已有 `verify_cases.py`。

- **keystone：verify_cases.py 内存化**——把全量机器检查从第13阶段（写后回读）前移到第8阶段出口（写前、内存内）。纯函数、零临时文件、零权限弹窗，契合"落盘前零文件操作"铁律。文件入口 stdout 与退出码字节级不变（回归安全）。
- **阶段×校验矩阵**：第3阶段（规则来源机器 gate）、第5阶段（风险来源机器 gate + P0漏标 critique）、第8阶段（全量机器 gate + 检查14对抗遍 critique）、第11阶段（LLM 主观自查 ≤3 轮）、第13阶段（写后回归）。机器 gate 查"已有的机器可判缺陷"，critique 查"该有却没有的漏标/漏测"——检查项不相交、计数独立。
- **5 个有界循环各自独立不嵌套**：第5机器 gate / 第5 critique / 第8机器 gate / 第8 critique / 第11自查，单向衔接（critique 补出新用例须回跑第8 gate），无无限循环。

**逻辑正确性保证**：回归字节级一致（仅 0.3.0 边界值新增"边界内"行差异，属预期）；运行模式正交（gate 全规模必跑，不放宽质量底线只放宽等人工时点）；端到端验证缺陷用例集 → gate 报 → 内存修 → 重跑清零通过。

**升级影响**：对最终用户无感（质量内建于阶段出口，用户仍只需回答澄清问题 + 审核）；对已有产出物无破坏（15 列字段/固定值/Excel 格式全不变）；token 增量可控（机器 gate 确定性自修增量小，critique 真增量但只 2 轮且只重型需求跑满）。

**变更文件**（15 个）：脚本/配置（`verify_cases.py` 内存化 + 边界4档、`validation_rules.json` +`boundary_inside_kw`）；spec（`modeling.md` §15.7 + 第3 gate、`risk.md` 第5 gate + critique、`methods.md` 边界4值、`selfcheck.md` 检查14 critique + 分工、`output_write.md`/`quality_rules.md`/`example.md`/`review_gate.md`）；流程与文档（`SKILL.md`/`README.md`/`一分钟上手.md`/根 `README.md`/本 CHANGELOG）。

**升级方式**：Claude Code 用户 `/plugin marketplace update qamaster` 后新开会话生效；本地开发 `git pull` 后跑 `python skills/case-design/scripts/verify_cases.py --dump-rules` 确认边界 4 档。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.5.0] - 2026-07-24

### 新增

- **UI 类测试子维度补全（闭合"界面结构覆盖整块缺失 + 0.1 反向劝退"根因）**：闭合覆盖矩阵全是"业务/数据/接口"导向、缺"界面交互结构"导向，且 `SKILL.md 0.1 严禁过度设计`把"页面能否显示/按钮能否点击"列入禁令反向把业务 UI 测试压进豁免区的根因。UI 测试锚定"界面结构是否正确承载业务规则/数据/权限/状态"，而非"元素存在/框架渲染"。
- **0.1 禁令精确剥离（最关键·否则后续白加）**：`SKILL.md` 0.1 把"页面能否显示/按钮能否点击"从禁令剥离，保留"禁测框架自身能力/纯元素存在性/像素级布局"，放开"业务界面承载测试"；判定线 = UI 用例是否过度看 Then 断言"业务可观测变化"还是"元素存在性"。`references/quality_rules.md` 11.1 同步。
- **UI 类 8 子维展开**：`references/modeling.md` 15.5 "UI类"从"控件状态、页面交互"8 字展开为 8 子维（查询/筛选条件区、列表/表格展示区、表单录入区、操作按钮与交互、页面状态与反馈、导航与流程跳转、权限驱动 UI、数据展示格式与极端值），含边界表（UI 只测界面承载、不重复测底层值/数据/契约）+ 适度性校准（不测框架/测业务承载/按风险分级 P0-P1全量-P2采样-P3最小）。
- `references/coverage.md` 新增 **8.10 界面结构覆盖**维度（查询条件项/列表展示/表单/按钮交互/权限UI）+ 15.3 测试点维度追加查询条件/列表展示/表单交互/权限UI四类测试点 + 场景类型列追加"界面结构"枚举值。
- `config/validation_rules.json` `valid_dims` 新增 `界面验证`（UI 用例类型填"功能"、维度填"界面验证"，避免 valid_type 膨胀）；`keyword_dims` 新增 `界面查询`/`界面列表` 两桶（默认查询/单条件/组合查询/重置/级联 + 列表展示/字段映射/分页/排序/四态/脱敏/回显）。
- `scripts/verify_cases.py` 覆盖统计新增 UI 两桶关键词计数（`界面查询`/`界面列表`，对标签错标鲁棒）；dump-rules 投影同步；**修复 domain_config 字段级覆盖 bug**——原 `if "keyword_dims" in _DOMAIN_CFG: KEYWORD_DIMS = _DOMAIN_CFG["keyword_dims"]` 整体替换会丢掉 validation_rules 独有 key（如 0.5.0 新增的 UI 桶），改为 key 级合并（保留内置、domain 同名覆盖/新增加入），与 _usage"新增字段不覆盖内置"一致；exception_subtypes 同样修复。
- `references/example.md` 新增**范例4：列表/查询 UI 覆盖**（ORD_LIST_001-008，8 条 UI 用例覆盖默认查询态/组合查询/重置/列表四态/分页越界/脱敏/终态按钮），展示 UI 用例结构与断言口径（断言业务可观测，非元素存在）。

### 变更

- `references/selfcheck.md` 检查14 对抗生成遍补"界面结构遗漏"盲区（需求涉列表/查询但界面查询/界面列表=0 时按需补齐）。
- `README.md`/根 `README.md` 特性列表补 UI 类 8 子维度说明。

### 设计依据

- 根因分析：skill 覆盖矩阵无界面结构维度、UI类仅8字无子维度、valid_types/dims 无 UI 枚举位、verify_cases 无 UI 统计/缺口告警、0.1 禁令反向劝退——五层互锁致 UI 覆盖整块缺失。
- 不过度原则：UI 维度边界表钉死只测"界面承载"，不重复测输入类/数据类/接口类；适度性校准按风险分级防爆炸；0.1 精确剥离后框架类 UI 用例仍由检查7（Then 无业务锚点→疑似过度设计）拦下，机制自洽。
- 不新增 valid_type 避免 12 类枚举膨胀；UI 用例类型填"功能"与现有兼容，verify_cases 检查11 字段规范不破坏。

## [0.4.0] - 2026-07-24

### 新增

- **阶段出口机器 gate（把 verify_cases 机器检查从写后前移到写前·防"白工+回流滞后"）**：闭合"多轮自审纠错只集中在第11阶段一处、机器检查要到写后第13才第一次跑"的根因。把 `verify_cases.py` 全量检查从第13阶段（写后回读）前移到**第8阶段出口（写前、内存内）**，使 9/10/11/12 作用在已通过机器校验的用例集上，第13阶段降级为"Write 是否损坏内容"的回归检查。另在第3/5阶段出口加窄域机器 gate（规则来源/风险来源），把"脑补规则""风险漏标"这类前置阶段就能机器判定、却拖到写前/写后才反向捕获的缺陷就地拦住。
- **verify_cases.py 内存化 keystone**：新增 `run_inmemory(lines, req_doc_lines=None)` / `collect_all_findings()` / `parse_table_from_lines()` / `check_behavior_source_lines()` / `parse_requirement_items_from_lines()` / `reverse_requirement_trace_items()`，使全量校验可在内存 list-of-lines 上跑（零临时文件、零 Bash、零权限弹窗，契合"落盘前零文件操作"铁律）；`main()` 重构为经 `collect_all_findings` 后走 `print_findings`，文件入口 stdout 与退出码**字节级不变**（回归安全）。
- `references/modeling.md` 新增 §15.7 第8阶段出口机器 gate（含与第11阶段/第13阶段分工表、≤2轮机器自修、硬阻断转问题/假设、运行模式正交、设计约束、被检查14回跑衔接）；新增第3阶段出口机器 gate（规则来源 check_rule_source）。
- `references/risk.md` 新增第5阶段出口机器 gate（风险来源 risk_source_report）+ **第5阶段 critique 循环**（P0 漏标对抗式第二视角，≤2轮 critique 自修，与机器 gate 分工独立计数）。
- `references/output_write.md` 第5步标注"第8 gate 已先跑"、第6步标注"第13回读降为回归检查、不回触第8 gate 循环"。
- `references/selfcheck.md` 顶部加与第8 gate 的分工声明（机器可判项第8已修、主观项第11管、计数独立不嵌套）；检查14对抗遍升级为**独立≤2轮 critique 子循环**（含与第8 gate 衔接：补出新用例须回跑第8 gate）。

### 变更

- `SKILL.md` 阶段列表第3/5/8阶段标注出口机器 gate（第5阶段另标注 critique 循环）；输出顺序第5步与要点速记补第8 gate 与第11自查分工独立计数声明、检查14 critique 子循环计数说明。

### 设计依据

- 两个探查代理确认：Phase 8 现有自检（modeling §15.6）单遍无循环不调脚本，Phase 11 纯 LLM 主观从不调 verify_cases.py，Phase 13 是 verify_cases.py 唯一调用点——故 Phase 8 gate 为 net-new。verify_cases.py 大部分已是 line-based（parse_table/check_behavior_source/reverse_requirement_trace 仅3处文件耦合），keystone 重构面小且回归可逐字节校验。
- Tier B（第5阶段 critique / 第8阶段检查14 critique）是真正花 token 的对抗式第二视角，聚焦机器查不出的"P0 漏标"与"漏测用例"；各有界≤2轮+升级机制，与机器 gate / selfcheck 主循环计数独立不嵌套。

## [0.3.0] - 2026-07-24

### 新增

- **边界值 4 值模型（补边界内邻接·防 off-by-one 漏测）**：闭合边界值设计长期缺"边界内"场景的根因。边界值由原 3 值（min/max/临界）升级为 **4 值**：最小 / 最大 / 临界(=边界点) / **边界内(min+1/max-1，刚好满足约束应通过)**。边界内是 off-by-one 历史最高 bug 产出点，原模型中"临界"被重定义为"恰好等于边界点"（与 min/max 重复），边界内被甩给等价类兜底但等价类只取代表值，从两方法间漏掉。
- `config/validation_rules.json` 新增 `boundary_inside_kw`（边界内关键词桶，单一事实源）。
- `references/methods.md` 新增"边界值 4 值模型"专节：四档语义对照、不得用临界覆盖边界内、不得由等价类兜底；P0 全量/P2 采样深度、各方法适用说明、统一接口测试矩阵 C 行均补边界内。
- `references/selfcheck.md` 检查14 对抗生成遍补"边界内邻接遗漏"盲区。

### 变更

- `scripts/verify_cases.py` 边界深度统计由 3 档扩为 4 档（增 `bound_inside` 计数器 + `BOUNDARY_INSIDE_KW` 常量 + `--dump-rules` 投影 + 缺档告警）；docstring/`coverage_stats` 文案同步。
- `references/modeling.md` 边界类、`references/quality_rules.md` 数值类型补边界内邻接（min+1/max-1）。
- `references/example.md` 范例1 数量边界补 `ORD_CREATE_002B`（数量 2/98 边界内邻接）用例与说明。
- `references/review_gate.md` 覆盖摘要边界深度文案补"边界内"。

## [0.2.0] - 2026-07-14

### 新增

- **检查15 业务行为来源追溯（#5 反向行为来源追溯）**：闭合 0.3 脑补禁令在"业务行为"维度的机械缺口。用例 Given/When/Then 断言的业务行为须有来源三选一（需求文档 token / `R·TP` 引用 / `假设A` 标记），三者皆无即疑似脑补，须转问题(P0/P1)/假设(P2/P3)，不得静默保留。`verify_cases.py` 新增 `check_behavior_source` + `check_rule_source` 软性检查（含 `--dump-rules` 投影），`config/validation_rules.json` 新增 `behavior_source` 口径（单一事实源）。
- **规则建模 section 来源标注（破自证循环）**：每条规则项须标 `[来源:需求文档<章节>/台账Q<序号>/假设A<序号>]`，无来源标记->疑似脑补规则，破 `rule_coverage` 自证洗白。
- **假设可见化**：待确认问题与假设统一为【待确认问题与假设清单】（加「状态」列：待确认(阻断)/假设(非阻断)），假设不再仅沉于交付报告，须回显清单并在人工审核话术中显式列出。
- **0.9 业务行为必须有来源** 避坑条目；3.1 合规红线补"不脑补业务行为"。
- 交付摘要脚本校验摘要由四项扩为五项（增 检查15/#5）；自查由 14 项扩为 15 项。

### 变更

- `references/example.md` 状态机范例修正：原"假设澄清已完成/本例假设允许"的静默虚构改为登记假设 A1（回显清单、用例关联规则标 `假设A1`、规则建模 section 标来源）。
- `references/clarification.md` 假设登记机制收紧：行业惯例仅作已登记假设的依据，禁止静默推断。

## [0.1.0] - 2026-07-13

### 新增

- 企业级 SDD + TDD 测试用例设计 skill 首个版本。
- 15 阶段主流程：需求定位 -> 澄清 -> 规格建模 -> 风险分析 -> 方法匹配 -> 测试点 -> 用例生成 -> 去重 -> 覆盖率 -> 自查 -> 写入 -> 人工审核 -> 知识总结 -> Excel。
- 渐进式加载：常驻核心 SKILL.md + `references/` 按需读取，显著降低每次请求 token。
- 脚本回读校验：`verify_md.py`（结构）+ `verify_cases.py`（内容/覆盖）+ `verify_knowledge.py`（知识综合）。
- Markdown / Excel 双格式按需输出，多需求索引 `MANIFEST.md`。
- 运行模式：完整 / 连跑 / 轻量；按需求规模自动分级。
- 校验规则单一事实源 `config/validation_rules.json`，支持领域扩展 `config/domain_config.json`。
