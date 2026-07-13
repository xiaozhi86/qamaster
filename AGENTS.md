# QA Master — Codex 项目指令

本仓库提供两个 QA 能力，skill 正文统一存放在 `skills/` 下（单一事实源），采用**薄引用**方式调用：运行时读取对应 `SKILL.md` 并以其所在目录为 skill 根（`references/`、`scripts/`、`config/` 均相对它解析），不复制正文。

## 能力入口

- **case-design（测试用例设计）**：用户提到测试用例设计 / 用例生成 / 需求转用例 / 用例转 Excel / 覆盖分析时 → 读取并执行 `skills/case-design/SKILL.md`。
- **requirement-review（需求评审）**：用户提到需求评审 / 需求分析 / 多角色评审时 → 读取并执行 `skills/requirement-review/SKILL.md`。

也可通过自定义 prompt 触发：把 `codex/prompts/*.md` 拷贝到 `~/.codex/prompts/`，即可用 `/case-design`、`/requirement-review`。

## 产出位置

- case-design → 项目根的 `case-design-out/`（自动创建）。
- requirement-review → 项目根的 `requirement-review/`。

## 依赖

- Python 3.7+：case-design 的回读校验脚本在 `skills/case-design/scripts/`；生成 Excel 需 `openpyxl`（缺失时 skill 会自动尝试安装并兜底报错）。
- skill 正文中 Claude Code 专属建议（`CLAUDE_CODE_MAX_OUTPUT_TOKENS`、`.claude/settings.json`、`acceptEdits`）在 Codex 无对应物，忽略即可；等价行为用 Codex 自身配置实现。
