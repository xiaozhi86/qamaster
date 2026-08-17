# Changelog - requirement-review

本文件记录 requirement-review skill 的版本变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.2.0] - 2026-07-17

### 新增

- 输入预处理能力：图片/扫描件/含图文档统一抽取为纯文本，避免文本-only 模型 400 硬崩（`config/input_rules.json` + `scripts/extract_text.py`）。
- 多格式抽取：PDF（pdfplumber 文本+表格+图片坐标）/ Word（python-docx 遍历 body 子元素）/ PPT（python-pptx）/ Excel（openpyxl）/ 图片（RapidOCR 中文）。
- 就地回填：图片 OCR 文本就地回填到文档原位置（占位符 `【图片@位置k(置信度)：文本】`），保留图文上下文语义，不汇总到文末或丢失；PDF 复杂版式降级为正文留位置标记+文末汇总。
- 扫描件 PDF 兜底：整页字符<阈值 → pdf2image 逐页转图 → 整页 OCR（天然就位）。
- 降级链路：依赖缺失自动 pip install 兜底；OCR 低置信度回退提示用户补文字说明；扫描件 poppler 缺失回退提示用户转文字版。
- SKILL.md 新增第0阶段（输入预处理与降级）+ 输入协议补文本-only 约束。

## [0.1.0] - 2026-07-13

### 新增

- 需求文档多角色评审 skill 首个版本。
- 7 个专家 Agent 并行评审：BA（业务分析）/ PM（产品设计）/ QA（测试设计）/ Arch（技术架构）/ UX（用户体验）/ Risk（风险控制）/ Dev（开发实现）。
- 九阶段流程：并行评审 -> 结果汇总去重 -> 冲突检测 -> 优化方案总览 -> 用户确认 -> 需求文档重构 -> 自动复查 -> 二次修复 -> 最终输出。
- 输出优化后的高质量需求文档 + 评审问题详情列表（含已解决/未解决）。
- 输出落盘到项目根的 `requirement-review-out/` 目录。
