# Changelog - case-design

本文件记录 case-design skill 的版本变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-07-13

### 新增

- 企业级 SDD + TDD 测试用例设计 skill 首个版本。
- 15 阶段主流程：需求定位 -> 澄清 -> 规格建模 -> 风险分析 -> 方法匹配 -> 测试点 -> 用例生成 -> 去重 -> 覆盖率 -> 自查 -> 写入 -> 人工审核 -> 知识总结 -> Excel。
- 渐进式加载：常驻核心 SKILL.md + `references/` 按需读取，显著降低每次请求 token。
- 脚本回读校验：`verify_md.py`（结构）+ `verify_cases.py`（内容/覆盖）+ `verify_knowledge.py`（知识综合）。
- Markdown / Excel 双格式按需输出，多需求索引 `MANIFEST.md`。
- 运行模式：完整 / 连跑 / 轻量；按需求规模自动分级。
- 校验规则单一事实源 `config/validation_rules.json`，支持领域扩展 `config/domain_config.json`。
