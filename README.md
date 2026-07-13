# QA Master

企业级 QA 工具集，包含两个 skill：

| Skill | 作用 |
|---|---|
| **case-design** | 需求文档/原型 → 测试用例（Markdown/Excel），含澄清、规格建模、风险分析、方法匹配、去重、覆盖率、自查、知识总结 |
| **requirement-review** | 需求文档多角色并行评审（BA/PM/QA/Arch/UX/Risk/Dev）+ 汇总仲裁 + 冲突检测 + 文档重构 + 自复查 |

两个 skill 的**正文内容统一存放在 `skills/` 下，为单一事实源，不随平台复制**。三个平台各自加一层薄引用包装，运行时读取对应 `SKILL.md` 执行。

---

## 平台一：Claude Code（原生 plugin）

本仓库根目录即一个 Claude Code plugin（含 `.claude-plugin/plugin.json` + `marketplace.json`）。`skills/` 下两个 skill 原生可发现，`commands/` 提供 `/case-design`、`/requirement-review` 显式触发。

### 安装

```
/plugin marketplace add <本仓库本地路径或 git url>
/plugin install qamaster@qamaster
```

### 使用

```
/case-design
/requirement-review
```

> 两个 skill 均设了 `disable-model-invocation: true`（不自动触发），故通过上述 `/` 命令显式调用；若你的版本下 `/` 命令未自动唤起 skill，直接说“使用 case-design skill”即可。

---

## 平台二：Codex（AGENTS.md + 自定义 prompt）

Codex 无 plugin 市场，“插件” = `AGENTS.md`（项目级指令，Codex 自动读取）+ 自定义 prompt（`~/.codex/prompts/`）。

### 安装

1. 把本仓库（或至少 `skills/` + `AGENTS.md`）放入你的项目根，Codex 在该项目运行时自动读 `AGENTS.md`。
2. 把 `codex/prompts/*.md` 拷贝到 `~/.codex/prompts/`，获得 `/case-design`、`/requirement-review` slash 命令。

### 使用

```
/case-design
/requirement-review
```

或直接说“用 case-design skill 设计测试用例”，Codex 会按 `AGENTS.md` 读取 `skills/case-design/SKILL.md` 执行。

> prompt 以薄引用方式指向 `skills/.../SKILL.md`，需 `skills/` 位于当前项目根。

---

## 平台三：Cursor（`.cursor/rules/*.mdc`）

Cursor 无 plugin 市场，“插件” = `.cursor/rules/` 下的 rule 文件。

### 安装

把本仓库（或至少 `skills/` + `.cursor/rules/`）作为项目根；Cursor 自动发现 `.cursor/rules/*.mdc`。

### 使用

两个 rule 均为 `alwaysApply: false`（按需触发，不污染上下文）。在对话中用 `@case-design` 或 `@requirement-review` 引用，或涉及测试用例设计 / 需求评审时让 Cursor 自动拉取。

> rule 以薄引用方式指向 `skills/.../SKILL.md`，需 `skills/` 位于项目根。

---

## 依赖

- Python 3.7+（case-design 的回读校验与 Excel 生成脚本在 `skills/case-design/scripts/`）。
- 生成 Excel 需 `openpyxl`（缺失时 skill 自动尝试安装并兜底报错）。
- case-design skill 正文中部分建议（`CLAUDE_CODE_MAX_OUTPUT_TOKENS`、`.claude/settings.json`、`acceptEdits`）为 Claude Code 专属；Codex/Cursor 用户忽略，用各自平台机制等价实现。

---

## 目录结构

```
.
├─ skills/                          # 单一事实源（不随平台复制）
│  ├─ case-design/
│  └─ requirement-review/
├─ .claude-plugin/                  # Claude Code
│  ├─ plugin.json
│  └─ marketplace.json
├─ commands/                        # Claude Code slash 命令
├─ AGENTS.md                        # Codex 项目指令
├─ codex/prompts/                   # Codex 自定义 prompt（拷到 ~/.codex/prompts/）
├─ .cursor/rules/                   # Cursor rule
└─ README.md
```

## 设计原则

- **单一事实源**：skill 正文只在 `skills/`，三平台不复制。
- **薄引用包装**：各平台适配文件只指引“读取并执行对应 SKILL.md”，零漂移。
- **skill 正文不改**：本层只在外围加适配，不碰 `skills/**` 内容。
