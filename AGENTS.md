# QA Master — Codex 项目指令

本仓库提供两个 QA 能力，skill 正文统一存放在 `skills/` 下（单一事实源），采用**薄引用**方式调用：运行时读取对应 `SKILL.md` 并以其所在目录为 skill 根（`references/`、`scripts/`、`config/` 均相对它解析），不复制正文。

## 能力入口

- **case-design（测试用例设计）**：用户提到测试用例设计 / 用例生成 / 需求转用例 / 用例转 Excel / 覆盖分析时 → 读取并执行 `skills/case-design/SKILL.md`。
- **requirement-review（需求评审）**：用户提到需求评审 / 需求分析 / 多角色评审时 → 读取并执行 `skills/requirement-review/SKILL.md`。

也可通过自定义 prompt 触发：把 `codex/prompts/*.md` 拷贝到 `~/.codex/prompts/`，即可用 `/case-design`、`/requirement-review`。

## Runtime（可选增强，Claude Code 默认启用）

`runtime/qamaster_runtime.py` 是 case-design 的流程状态机（0-14 阶段严格顺序 + 质量门禁 + 人工确认点，模型无关）。Codex 下若能执行 Python，可先用 `bootstrap`（派生需求标识）再 `start --req-id <需求标识>` 启动受控流程；不用 Runtime 时退回 `skills/case-design/SKILL.md` 的 15 阶段定义执行，业务规则完全一致。**同一工程可并行处理多个需求**：状态按 `(workflow, req_id)` 分区互不干扰。

## 产出位置

- case-design → 项目根的 `case-design-out/`（自动创建）；**Runtime 控制层状态在 `.qamaster/case-design/<需求标识>/state.json`**（按需求标识分区隔离，多需求互不覆盖）。`case-design-out/MANIFEST.md` 为多需求共享索引，由 Runtime 在 gate PASS 时自动维护。
- requirement-review → 项目根的 `requirement-review/`。

## 依赖

- Python 3.7+：case-design 的回读校验脚本在 `skills/case-design/scripts/`；Runtime 在 `runtime/`；生成 Excel 需 `openpyxl`（缺失时 skill 会自动尝试安装并兜底报错）。
- skill 正文中 Claude Code 专属建议（`CLAUDE_CODE_MAX_OUTPUT_TOKENS`、`.claude/settings.json`、`acceptEdits`）在 Codex 无对应物，忽略即可；等价行为用 Codex 自身配置实现。
