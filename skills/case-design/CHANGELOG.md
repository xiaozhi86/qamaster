# Changelog - case-design

本文件记录 case-design skill 的版本变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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
