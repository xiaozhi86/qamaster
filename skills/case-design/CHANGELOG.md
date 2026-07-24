# Changelog - case-design

本文件记录 case-design skill 的版本变更。

---

# 发布说明（面向使用者）

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
