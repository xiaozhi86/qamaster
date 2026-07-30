# Changelog - case-design

本文件记录 case-design skill 的版本变更。

---

# 发布说明（面向使用者）

> 本节为每个已发布版本的用户视角摘要；下方各版本技术条目面向维护者。两节互补，不重复。

## v0.7.5（2026-07-30）— 多厂商最低模型声明

**本次发布解决一个核心问题**：用户问"如何一劳永逸阻止弱模型"，发现 hook/脚本驱动对"不读 SKILL.md、不调用脚本"的弱模型都无效。唯一根治方案是**声明最低模型要求，让人类别用弱模型跑**。

**新特性：多厂商 min-models 声明**

在 `marketplace.json` / `plugin.json` / `SKILL.md` frontmatter / `README.md` 四处统一声明最低模型：

| 厂商 | 最低模型 | 不达标示例 |
|---|---|---|
| Anthropic | Sonnet 4.5 及以上 | — |
| 智谱（Zhipu） | GLM-5.2 及以上 | GLM-5（跳阶段/不读 SKILL.md/写到非约定位置） |
| OpenAI | GPT-4o 及以上 | — |
| Google | Gemini 2.0 Flash 及以上 | — |

**三层防护（叠加）**：
1. **事前·给人看**：min-models 多厂商声明，人类选模型时就知道别用弱模型
2. **事中·给机器挡**：PreToolUse hook 内容检测，弱模型违规 Write 也会被 exit 2 拦截
3. **事后·留痕**：run_phase.py gate8/summary 核对门禁是否齐全

**声明性质说明**：Claude Code 无 harness 强制执行的 min-model 字段，此声明为指引人类的文档；但与 hook 内容检测叠加后，弱模型即便忽略声明、不调用脚本，违规写入仍会被物理拦截。

## v0.7.4（2026-07-29）— 脚本驱动模式：彻底解决弱模型跳阶段问题

**本次发布彻底解决核心问题**：无论 hook 多强，弱模型总能绕过（不读 SKILL.md、跳过阶段、写到其他位置）。本版引入**脚本驱动模式**，从根本上改变执行方式。

**新特性：脚本驱动的测试用例设计流程**

| 对比项 | 原方案 | v0.7.4 |
|---|---|---|
| **执行主体** | 模型自觉执行 15 阶段 | **脚本强制执行** |
| **模型角色** | 读 SKILL.md → 理解流程 → 执行 | 只需按脚本指令执行当前阶段 |
| **流程合规** | 依赖模型自觉 | **由脚本硬编码保证** |
| **跳阶段** | 弱模型会跳 | **脚本拒绝执行** |

**使用方式**：

```bash
# 启动流程
python scripts/case_design_workflow.py start "需求文档路径"

# 查看当前状态
python scripts/case_design_workflow.py status

# 推进到下一阶段
python scripts/case_design_workflow.py next
```

**效果**：
- 模型不需要读懂 580 行 SKILL.md
- 模型不需要记忆 15 阶段流程
- 模型只需要按脚本指令执行当前阶段
- 脚本负责检查产出物、运行门禁、推进下一阶段
- **弱模型也无法跳阶段，因为脚本不允许**

**产出物不变**：MANIFEST.md, REQ_*.md, Clarification_Ledger_*.md, TestCases_*.md, Knowledge_*.md —— 全部复用现有规范。

## v0.7.2（2026-07-29）— 内容特征检测：拦截任意位置的测试用例 Write

**本次发布解决一个核心问题**：v0.7.1 只拦截 `case-design-out/` 目录，弱模型会把测试用例写到其他位置（如 `测试用例/`）来绕过门禁。

**新特性：内容特征检测**

hook 不仅检查路径，还检查 Write 的内容是否包含测试用例特征：
- 文件名含"测试用例"/"TestCases"
- 内容含"# 测试用例"/"测试用例ID"/"用例等级"等关键词

如果检测到测试用例内容，强制要求：
1. 写到 `case-design-out/TestCases_*.md`
2. 满足门禁（gate8 + Phase 0-7 签名）

**效果**：模型无论如何输出测试用例（写到任意位置），都会被门禁拦截，stderr 给出可执行修复指令。

**升级原因**：用户反馈 glm-5 在 v0.7.1 下仍绕过流程——直接把测试用例写到 `测试用例/` 目录，而非 skill 约定的 `case-design-out/`。

## v0.7.1（2026-07-29）— 全目录拦截：每一步都卡门禁

**本次发布解决一个核心问题**：v0.7.0 的 hook 只拦截 TestCases 写入，弱模型可以跳过 Phase 0-7 在内存中生成用例内容然后展示，不触发 Write。本版升级为**全目录拦截**，每一步产出物都被门禁卡住。

**新特性：分文件类型门禁**

| 文件类型 | 门禁要求 |
|---|---|
| MANIFEST.md / REQ_*.md | 允许写入，提示运行 gate-phase 0 |
| Clarification_Ledger_*.md | 需要 Phase 0 已签名 |
| TestCases_*.md|xlsx | 需要 gate8 exit=0 + Phase 0-7 全签 |
| Knowledge_*.md | 需要 Phase 0-7 全签 |
| 其他 case-design-out/ 文件 | 需要 Phase 0 签名 |

**效果**：模型必须按顺序 MANIFEST → gate-phase 0 → Clarification_Ledger → gate-phase 1-7 + gate8 → TestCases。跳过任何步骤都会被门禁拦住，stderr 给出可执行修复指令。

**升级原因**：用户反馈 glm-5 在 v0.7.0 下仍跳过阶段 0 直接在对话中生成用例内容——因为没有 Write，hook 无法拦截。全目录拦截后，模型要输出任何产出物都必须先过门禁。

## v0.7.0（2026-07-29）— harness 强制合规：硬门禁 + PreToolUse hook

**本次发布解决一个核心问题**：不同模型（尤其 glm-5 等弱模型）调用本 skill 时不严格按 Phase 0-15 顺序执行，跳过澄清/规格建模/风险分析直接生成用例。v0.6.0 的机器门禁仍依赖模型"自觉调用脚本"，弱模型不调用即绕过。本次把约束从"模型层"下沉到"harness 层"。

**新特性一：PreToolUse hook 硬拦截 Write（keystone）**

新增 `.claude/hooks/case_design_gate.py` + `.claude/settings.json` 的 `hooks.PreToolUse`。仅命中 `case-design-out/TestCases_*.md|.xlsx` 的 `Write/Edit/MultiEdit` 触发；未过 gate8（exit=0）且 Phase 0-7 签名不全即 `exit 2` 阻止工具调用。模型被物理阻断，无法跳步直接落盘——**与模型是否自觉无关**。其余文件（MANIFEST/REQ/Clarification_Ledger/Knowledge/项目任意文件）一律放行。

**新特性二：run_phase.py 三处硬化**

- **Phase 2-7 硬拒绝**：`check_phase_dependencies` 从"可选警告"提为"硬拒绝"，gate8 要求 Phase 0-7 签名齐全才放行（缺签记 `PHASE_DEPS_MISSING`）。闭合弱模型跳过规则建模(3)/风险分析(5)/策略匹配(6)/测试点建模(7) 的漏洞。
- **阶段顺序校验**：`cmd_gate_phase` 签 Phase N 前须先签 Phase N-1，禁止跨阶段跳签（`PHASE_ORDER_VIOLATION`）。
- **preflight 自动注入**：`gate-phase N` 内嵌 `_inject_preflight`，随门禁 stdout 注入本阶段 ref 40 行大纲摘要，不再依赖模型自觉读 ref。

**双层校验**：hook（harness 层，Write 前）与 `check_phase_dependencies`（脚本层，gate8 内）双重把关 Phase 0-7，一处可被绕过另一处仍兜底。不放宽任何质量底线（断言/覆盖/存储合规等仍由 verify_cases 把关），只挡"跳步直接 Write"。

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
