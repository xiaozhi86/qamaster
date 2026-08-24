# requirement-review — 需求文档多角色评审 Skill（Claude Code）

> 版本：v0.3.0 · 更新：2026-08-21 · 版本变更明细见 `CHANGELOG.md`
> Runtime 受控流程已随插件 v0.11.12 支持多需求并行评审（8 阶段状态机，见 §7）；v0.11.13 起契约卡末尾按需追加 `##CONTEXT_BUDGET##` 上下文建议（Phase 5/6 重输出点提示 `/compact`），并新增 `context` 只读命令查工作集估算与累计 token 足迹；v0.11.14 起 Phase 0 专家团动态路由（`config/agents.json` + `contains` 门禁）

一套跑在 **Claude Code** 上的需求文档评审 Skill：输入需求文档（支持含图 / 扫描件 / Word / PDF / PPT / Excel），按需求内容动态路由出**评审专家团**（核心团 PM/QA/Dev 恒参与 + BA/Arch/UX/Risk 按信号词命中），并行评审，Review Master 汇总去重 + 冲突仲裁，经用户确认后自动重构出一份**高质量、可开发、可测试**的需求文档，并附评审问题详情清单。

核心模式：**「并行评审 + 汇总仲裁」**——专家团各专家独立思考、互不影响的并行输出，再由 Review Master 统一汇总、去重、检测冲突并给出权衡推荐。

---

## 目录

1. [系统目标](#1-系统目标)
2. [专家池（7 个专家 Agent · 动态路由）](#2-专家池7-个专家-agent--动态路由)
3. [环境要求与依赖](#3-环境要求与依赖)
4. [安装步骤](#4-安装步骤)
5. [验证 Skill 已生效](#5-验证-skill-已生效)
6. [使用步骤](#6-使用步骤)
7. [评审流程（Runtime 状态机）](#7-评审流程runtime-状态机)
8. [输入预处理与降级](#8-输入预处理与降级)
9. [产出物说明](#9-产出物说明)
10. [Runtime 控制协议](#10-runtime-控制协议)
11. [Skill 目录结构](#11-skill-目录结构)
12. [注意事项](#12-注意事项)
13. [常见问题 FAQ](#13-常见问题-faq)

---

## 1. 系统目标

对【需求文档】执行六步闭环：

```
多角色并行评审 → 自动发现问题 → 输出优化建议 → 用户确认 → 自动生成高质量需求文档 → 自动复查 + 二次修复
```

- **多角色并行评审**：核心团（PM/QA/Dev）恒参与，BA / Arch / UX / Risk 按需求内容信号词命中启用，各从其视角逐条审查需求。
- **自动发现问题**：每个 Agent 输出 ✅ 已满足 / ❌ 不满足 / ⚠ 风险项，并附问题建议与依据。
- **汇总仲裁**：Review Master 去重合并，检测 Agent 间冲突（业务 vs 技术、体验 vs 风控），给出权衡推荐。
- **用户确认**：评审问题须经用户明确答复（接受 / 忽略 / 修改 / 补充）才推进重构。
- **产出高质量需求文档**：10 节齐全（背景/目标/角色/流程/功能/规则/边界/异常/接口/权限），可开发 + 可测试。

---

## 2. 专家池（7 个专家 Agent · 动态路由）

每个 Agent 都按各自「Expert Level」评审标准独立、并行输出，输出格式统一为：

- ✅ 已满足项
- ❌ 不满足项
- ⚠ 风险项（潜在问题）
- 问题建议
- 建议依据

> **专家团动态路由**：不是任何需求都全量 7 专家。Phase 0 按需求文本信号词路由，从 `config/agents.json` 选出「核心团 + 命中扩展团」作为本次评审专家团，落盘 `Agents_<需求标识>.md`。**核心团 PM/QA/Dev 恒参与**；BA/Arch/UX/Risk 按信号词命中才启用（如涉资金/支付/合规 → Risk；涉接口/性能/并发 → Arch；涉页面/交互 → UX；涉跨部门流程/复杂业务 → BA）。信号词定义见 `config/agents.json`。

| Agent | 参与方式 | 角色 | 核心视角 | 评审要点 |
|---|---|---|---|---|
| **BA** | 按需 | 业务分析 | 业务完整性 + 正确性 + 闭环性 | 业务目标/范围边界/流程完整性/业务规则/角色职责/数据语义一致性/异常与边界 |
| **PM** | 核心团·恒参与 | 产品设计 | 功能设计质量 + 一致性 + 完整性 | 功能必要性/功能完整性/状态模型/交互逻辑/一致性/边界处理/可扩展性 |
| **QA** | 核心团·恒参与 | 测试设计 | 需求可用例化能力（可测试性） | 测试点可拆解/输入-处理-输出结构/边界值/异常输入/状态测试/预期可验证/测试方法可应用/缺陷发现潜力 |
| **Arch** | 按需 | 技术架构 | 可实现性 + 稳定性 + 可维护性 | 技术可行性/架构一致性/接口设计/数据设计/性能扩展/容错恢复 |
| **UX** | 按需 | 用户体验 | 易用性 + 认知效率 + 体验一致性 | 任务效率/可理解性/反馈机制/容错性/一致性/可访问性 |
| **Risk** | 按需 | 风险控制 | 安全性 + 合规性 + 风险可控 | 业务风险/安全性/合规性/攻击防护/极端故障场景/风控策略 |
| **Dev** | 核心团·恒参与 | 开发实现 | 需求可实现性明确、边界清楚、风险低 | 实现可行性/数据设计可实现性/业务逻辑可实现性/技术约束兼容/性能扩展/可维护性/异常处理/安全合规/可测试性/风险红旗 |

> QA Agent 除常规评审外，须额外输出三类：❌ 不可设计测试用例的需求点 / ⚠ 测试设计困难点 / ✅ 可直接转测试用例的优质需求点，并给出「影响的测试设计方法 + 补充建议」。

> **可扩展池**：新增专家（如 Data/法务/性能/国际化）只需在 `config/agents.json` 的 `agents` 加一条 + 本文件/SKILL.md 补一段评审标准，无需改 Runtime。

---

## 3. 环境要求与依赖

| 组件 | 要求 | 说明 |
|---|---|---|
| **Claude Code** | 较新版本（支持 Skills） | 桌面端 / CLI / VS Code 扩展均可 |
| **Python** | 3.7+ | 跑 `scripts/extract_text.py` 输入预处理脚本 |

**文本输入（.txt / .md / 粘贴）零依赖**，直接读取无需任何第三方库。

非文本输入的第三方依赖按需安装（缺失时脚本会提示 `pip install`，不静默放弃）：

| 输入格式 | 依赖库 | 安装命令 |
|---|---|---|
| PDF | pdfplumber | `pip install pdfplumber` |
| Word（.docx） | python-docx | `pip install python-docx` |
| PPT（.pptx） | python-pptx | `pip install python-pptx` |
| Excel（.xlsx） | openpyxl | `pip install openpyxl` |
| 图片 / 扫描件 OCR | rapidocr-onnxruntime（首选）+ onnxruntime + Pillow | `pip install rapidocr-onnxruntime onnxruntime Pillow` |
| 图片 OCR 兜底 | pytesseract + tesseract 系统二进制 | `pip install pytesseract`（tesseract 需另装系统二进制 + chi_sim 语言包） |
| 扫描件 PDF 转图 | pdf2image + poppler | Windows 需装 poppler 并加 PATH |

> OCR 引擎按序尝试：`rapidocr_onnxruntime`（首选，中文准）→ `pytesseract`（绕开 Python 版本限制）。rapidocr 2.x 要求 Python<3.13，3.14 环境装不上时自动降级 pytesseract。所有引擎均不可用时，脚本显式降级提示用户补文字说明，不静默中断。

---

## 4. 安装步骤

与 `case-design` 相同，任选其一：

**方式 A：项目级（推荐）** — 放进项目根目录 `.claude/skills/requirement-review/`

```
<你的项目根目录>/
└── .claude/
    └── skills/
        └── requirement-review/     ← 整个目录放这里
            ├── SKILL.md
            ├── config/
            └── scripts/
```

**方式 B：用户级（全局）** — 放进 `~/.claude/skills/requirement-review/`

安装后**重启 Claude Code 会话**（或新开一个）即生效。

---

## 5. 验证 Skill 已生效

- 显式触发：输入 `/requirement-review`，若 Skill 被加载，Claude 按本 Skill 的「并行评审 + 汇总仲裁」流程响应。
- 自然语言：输入"列出当前可用的 skills"，确认 `requirement-review` 在列。
- 任务触发：描述一个需求评审任务，看 Claude 是否进入专家团并行评审流程（先输入预处理、再专家团路由、再并行评审、再汇总仲裁）。

> 本 skill 设了 `disable-model-invocation: true`——模型不会自动加载，须显式 `/requirement-review` 触发（见 §12.1）。

---

## 6. 使用步骤

### 6.1 触发

```
/requirement-review
```

或在消息中说明：

```
使用 requirement-review skill，帮我评审下面的需求文档。
```

### 6.2 提供需求文档

直接把需求文档粘贴到对话中，或提供文件路径。支持：

- **纯文本**：直接粘贴，或 `.txt` / `.md` 文件路径。
- **含图文档 / 扫描件**：`.pdf` / `.docx` / `.pptx` / `.xlsx` / `.png` / `.jpg` 等——Skill 会自动经 `extract_text.py` 抽取为纯文本后再评审（见 §8）。

最简形式：

```
/requirement-review
【需求文档】
<<<需求文档开始>>>
用户在购物车点击"提交订单"，系统创建订单，状态为"待支付"……
<<<需求文档结束>>>
```

### 6.3 交互流程

提交后，Skill 依次执行：

1. **输入预处理**（第0阶段）：探测输入类型；非文本输入经 `extract_text.py` 抽取为纯文本并就地回填图片 OCR 结果；随后按需求文本信号词路由专家团，落盘 `Agents_<需求标识>.md`。
2. **并行评审**（第1阶段）：专家团（核心团 PM/QA/Dev + 命中扩展团）各独立输出问题清单，落盘 `ReviewIssues_<需求标识>.md`。
3. **汇总去重 + 冲突检测**（第2阶段）：Review Master 汇总去重、标准化、分类，检测实际参与专家间冲突并给权衡推荐。
4. **优化方案总览**（第3阶段）：按 P0/P1/P2 优先级汇总方案，标注影响范围（开发/测试/业务）。
5. **用户确认**（第4阶段·人工门）：输出【问题详情列表】+【请确认】三项，**停止等待用户明确答复**。
   - 答复方式：是否接受全部优化 / 是否忽略或修改 / 是否补充业务。
   - 用户未明确确认前，Runtime 禁止进入下一阶段。
6. **需求文档重构**（第5阶段）：基于确认结果生成 10 节齐全的最终需求文档，落盘 `ReviewedReq_<需求标识>.md`。
7. **自动复查 + 二次修复**（第6阶段）：Self-Review Agent 复查遗漏/未定义状态/不可测点/歧义/缺异常/缺边界，发现问题就地修复并标注修改点。
8. **最终输出**（第7阶段）：输出最终需求文档 + 评审问题详情列表（含已解决/未解决）。

> 阶段顺序由 Runtime 状态机裁决，模型无法跳阶段或自证完成（见 §7、§10）。

---

## 7. 评审流程（Runtime 状态机）

SKILL.md 的「并行评审 + 汇总仲裁」9 阶段（0-9）已压缩为 **8 个受控阶段（0-7）**，由 `runtime/requirement_review_phases.py` 驱动（v0.11.11 起，与 case-design 同走通用 workflow 引擎）：

| # | 阶段 | gate | 出口检查 |
|---|---|---|---|
| 0 | 输入预处理与需求定位 | auto | `REQ_{req_id}.md` + `Agents_{req_id}.md` 已落盘，且专家团名单含核心团 PM/QA/Dev（contains 门禁） |
| 1 | 并行评审（专家团） | auto | `ReviewIssues_{req_id}.md` 已落盘 |
| 2 | 结果汇总去重 + 冲突检测 | auto | 内存（无门禁） |
| 3 | 优化方案总览 | auto | 内存（无门禁） |
| 4 | 用户确认 | **confirm** | 人工确认门（复用控制器 confirm 机制） |
| 5 | 需求文档重构 | auto | `ReviewedReq_{req_id}.md` 已落盘 |
| 6 | 自动复查 + 二次修复 | auto | 内存（无门禁） |
| 7 | 最终输出 | auto | `ReviewedReq_{req_id}.md` + `ReviewIssues_{req_id}.md` 均存在（last） |

**与 SKILL.md 9 阶段散文的映射**：阶段 2「结果汇总」+ 阶段 3「冲突检测」→ Phase 2；阶段 7「自动复查」+ 阶段 8「二次修复」→ Phase 6；其余一一对应。

**与 case-design 的差异**：requirement-review 是「单次评审产出」，**有独立 MANIFEST 聚合索引（`requirement-review-out/MANIFEST.md`，列集与 case-design 不同）**，但**无知识总结后置动作、无 Excel 许可门**（末阶段=auto，gate PASS 即 DONE）；阶段门禁为确定性的文件存在性检查（req_id 绑定的 glob，`{req_id}` 占位经 `_fmt_cmd` 替换，多需求并发互不串扰），人工确认门（Phase 4）复用控制器 confirm 机制，模型不可绕过。无深度裁剪（`DEPTH_SKIPS` 全空，单次评审全阶段执行）。

---

## 8. 输入预处理与降级

> 当前部署模型为文本-only（报错 `Model only support text input` 即本约束触发）。需求文档常含原型截图/流程图/扫描件/含图 PDF，非文本直接喂模型会 400 硬崩。第0阶段把任何非文本输入统一转为纯文本再评审。

**规则契约单一事实源**：`config/input_rules.json`（缺失时脚本用内置默认，行为一致）。

### 8.1 支持的格式与处理方式

| 格式 | 扩展名 | 处理方式 |
|---|---|---|
| 纯文本 | .txt / .md / .markdown / 粘贴 | 直读（UTF-8/GBK 自动探测），跳过解析与 OCR |
| PDF | .pdf | pdfplumber 抽文本+表格+图片坐标，文本块+图片按 y 交错就地回填；单页字符<20 → 扫描件 → pdf2image 逐页转图 → 整页 OCR |
| Word | .docx（.doc 提示另存为 .docx） | python-docx 遍历 body 子元素抽正文+表格，内嵌图片就地 OCR 回填 |
| PPT | .pptx | python-pptx shapes 按坐标排序抽文本框+表格，Picture 就地 OCR 回填 |
| Excel | .xlsx / .xls | openpyxl 抽单元格文本 |
| 图片 | .png / .jpg / .jpeg / .gif / .bmp / .webp | RapidOCR（中文）直接 OCR |

### 8.2 就地回填（保留图文上下文语义）

图片 OCR 文本**就地回填**到图片在文档中的原始位置（占位符 `【图片@位置k(置信度)：文本】`），不汇总到文末、不丢失：

- Word：遍历 body 子元素（保留文档流顺序，含图）
- PDF：文本块 + 图片按 y 坐标交错就地回填；扫描件页整页 OCR 天然就位
- PPT：shapes 按坐标排序，Picture 就地 OCR 占位

> PDF 多栏/复杂版式坐标不可靠时降级：正文留位置标记 `→见图k@页n-yn`，OCR 文本汇总到文末 `【图k@页n：<OCR>】`。

### 8.3 降级链路（不静默中断）

- 依赖缺失 → 尝试 `pip install` 兜底 → 失败显式报错 + 用户指引。
- OCR 置信度 < 0.6（疑似流程图/原型图）→ 提示用户补该图的文字说明。
- 扫描件 PDF 但 pdf2image/poppler 不可用 → 提示用户转文字版或提供文字说明。
- 所有 OCR 引擎不可用 → 提示用户提供原型图/流程图的文字说明（不阻断纯文本主路解析）。

### 8.4 命令行用法

```
python scripts/extract_text.py <文件路径>            # 摘要模式（来源/字符数/预处理方式/置信度/图片数/降级标记 + 前 N 字预览）
python scripts/extract_text.py <文件路径> --json     # 结构化 JSON（供第0阶段程序化解析）
python scripts/extract_text.py <文件路径> --full     # 全文（降本模式下不建议）
```

### 8.5 超长文档分块

抽取后文本 > 24000 token → 按章节/模块分块，分批喂评审 Agent（不可超 32000 单响应上限）。

---

## 9. 产出物说明

运行后**项目根目录下的 `requirement-review-out/` 子目录**会出现以下文件（正式产出物，请勿手动删除）：

| 文件 | 内容 |
|---|---|
| `requirement-review-out/REQ_<需求标识>.md` | 预处理后的需求文档纯文本（第0阶段落盘，评审的唯一文本输入基准） |
| `requirement-review-out/Agents_<需求标识>.md` | 评审专家团名单（第0阶段落盘：核心团 PM/QA/Dev + 命中扩展团，逐行 id+命中依据） |
| `requirement-review-out/ReviewIssues_<需求标识>.md` | 专家团并行评审问题清单（第1阶段落盘） |
| `requirement-review-out/ReviewedReq_<需求标识>.md` | 重构后的最终需求文档（10 节齐全，第5阶段落盘） |
| `requirement-review-out/MANIFEST.md` | 多需求聚合索引（Runtime 在 gate PASS 时自动维护，模型禁写） |

> 需求标识由 Runtime `bootstrap` 预先派生（文件取首个 `#` 标题清洗，内联取首个非空行），所有产出物文件名直接用该标识，模型不派生 id。

---

## 10. Runtime 控制协议

requirement-review 走与 case-design 相同的 Runtime 受控流程（`runtime/qamaster_runtime.py` + `runtime/workflows/requirement_review.py`），核心原则不变：**模型负责思考，Runtime 负责控制，任何模型不可绕过**。

关键约束：

- **流程控制权不在模型**：8 阶段顺序由状态机裁决，模型只负责当前阶段的思考与产物，无权决定下一阶段、宣布阶段完成、跳过人工门禁。
- **人工确认门（Phase 4）不可绕过**：用户未明确确认前，Runtime 拒绝推进到 Phase 5。确认经 `confirm`，拒绝/反馈经 `reject`/`fail` 回退重走。
- **门禁以机器判定为准**：auto 门的 PASS/FAIL 由文件存在性检查给出，模型禁止自证"已通过"。
- **状态以 Runtime 为准**：每次接到用户新消息先 `status --req-id <id>` 恢复权威状态。
- **有 MANIFEST 聚合索引**：requirement-review 有独立多需求共享索引 `requirement-review-out/MANIFEST.md`（列集：需求标识/需求名称/需求文档/评审问题清单/最终需求文档/状态/更新时间），由 Runtime 在 Phase 0/1/5/7 gate PASS 时自动维护（模型禁止 Write/Edit）；支持 `manifest list`/`manifest reconcile`，多需求并发评审互不覆盖。

> 完整铁律见 `skills/case-design/SKILL.md` §「六条铁律」——requirement-review 与 case-design 共用同一套铁律（状态/门禁/业务规范/MANIFEST/KB 五条 + gate FAIL 自查通道）。

> **自我进化知识系统（KB）不覆盖 requirement-review**：`KB_lessons.md`/`KB_business.md`/`KB_expert.md` 三库及其 `kb` 命令族、经验自动捕获、`##PRIOR_*##`/`##RELEVANT_*##` 注入链**当前只在 case-design 生效**（详见 `skills/case-design/README.md` §8）。requirement-review 是单次评审产出，无知识总结后置动作、无经验捕获挂载点。评审产出的最终需求文档 `ReviewedReq_<需求标识>.md` 可直接作为 case-design 输入，再经 case-design 沉淀经验 / 业务知识。

---

## 11. Skill 目录结构

```
requirement-review/
├── SKILL.md                    # 常驻核心：专家池评审标准 + 9 阶段散文 + 输入协议 + 专家团路由
├── README.md                   # 本说明
├── CHANGELOG.md                # 版本变更（0.1.0 → 0.2.0 → 0.3.0）
├── config/
│   ├── input_rules.json        # 输入预处理规则单一事实源（格式/OCR/降级/分块/就地回填）
│   └── agents.json             # 专家池目录单一事实源（core_agents 核心团 + 各专家 required_signals 信号词）
└── scripts/
    └── extract_text.py         # 非文本输入统一抽取（OCR + 文档解析 + 就地回填）
```

> `config/` 与 `scripts/` 是 Skill 资产，**不要删除**。`extract_text.py` 只用 Python 标准库 + 按需第三方库（见 §3），缺失时脚本显式降级而非崩溃。

---

## 12. 注意事项

### 12.1 关于 `disable-model-invocation`

当前 `SKILL.md` 设了 `disable-model-invocation: true`——模型不会自动加载本 Skill，须用 `/requirement-review` 显式触发。想让"用户一提需求评审就自动激活"，删除 frontmatter 里这一行并重启会话。

### 12.2 文本-only 约束

当前模型仅支持文本输入。**禁止将图片/扫描件/含图二进制文档直接喂给模型**（会触发 400）。须经 `extract_text.py` 抽取为纯文本后再评审，抽取失败须显式降级提示。原型图/流程图优先要「文字说明」（用户提供文字版 > OCR > 多模态理解）。

### 12.3 产出目录会被写入文件

产出物统一写入项目根目录 `requirement-review-out/`，Runtime 控制层状态写 `.qamaster/requirement-review/<需求标识>/`（已 `.gitignore`）。建议在专用项目文件夹运行。

### 12.4 强制约束（评审质量底线）

- 必须专业、具体、无歧义，不允许泛化描述。
- 必须可开发 + 可测试，必须考虑异常/边界/状态流转。
- 任何问题未经用户确定，不可擅自确定。

---

## 13. 常见问题 FAQ

**Q1：Skill 没被识别 / `/requirement-review` 无效？**
检查：① `SKILL.md` 是否在 `.claude/skills/requirement-review/` 下；② 是否重启了 Claude Code 会话；③ frontmatter 的 `name` 和 `description` 是否完整。

**Q2：报 `Model only support text input` 怎么办？**
说明输入含图片/扫描件/含图文档，而当前模型文本-only。任选其一：① 提供纯文本需求描述；② 提供已提取的文字版；③ 对原型图/流程图补文字说明。或让 Skill 经 `extract_text.py` 抽取为纯文本后再评审。

**Q3：OCR / 文档解析依赖缺失？**
按 §3 的安装命令补齐对应依赖。OCR 引擎不可用时，脚本会显式提示（不会静默跳过），可按提示装 tesseract 系统二进制，或改用纯文本。

**Q4：需求文档很长，会超限吗？**
不会硬崩。抽取后文本 > 24000 token 按章节/模块分块，分批喂评审 Agent（不可超 32000 单响应上限）。

**Q5：评审到一半停了，能续跑吗？**
能。Runtime 状态按 `(workflow, req_id)` 分区落 `.qamaster/requirement-review/<需求标识>/state.json`，同一需求重新触发会断点续跑（bootstrap 输出 RESUME），已完成的阶段不重做。

**Q6：和 case-design 是什么关系？**
两者是同一插件（qamaster）下两个独立 skill，走同一套 Runtime 通用 workflow 引擎：`requirement-review` 负责「需求评审 → 产出高质量需求文档」，`case-design` 负责「需求文档 → 测试用例」。评审后的最终需求文档可直接作为 case-design 的输入。

**Q7：能同时评审多个需求吗？**
能。同一工程可对多个需求分别 `start --req-id <id>` 并发评审，状态按 `(requirement-review, req_id)` 分区落盘互不覆盖，门禁 req_id 绑定互不串扰，产出物与 MANIFEST 聚合索引按需求标识隔离。
