# Changelog - requirement-review

本文件记录 requirement-review skill 的版本变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-07-13

### 新增

- 需求文档多角色评审 skill 首个版本。
- 7 个专家 Agent 并行评审：BA（业务分析）/ PM（产品设计）/ QA（测试设计）/ Arch（技术架构）/ UX（用户体验）/ Risk（风险控制）/ Dev（开发实现）。
- 九阶段流程：并行评审 -> 结果汇总去重 -> 冲突检测 -> 优化方案总览 -> 用户确认 -> 需求文档重构 -> 自动复查 -> 二次修复 -> 最终输出。
- 输出优化后的高质量需求文档 + 评审问题详情列表（含已解决/未解决）。
- 输出落盘到项目根的 `requirement-review/` 目录。
