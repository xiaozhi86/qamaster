# requirement-review 多文档综合评审 —— 设计方法与改动细节

> 版本：v1.0 · 日期：2026-08-24 · 适用 workflow：`requirement-review`
> 目标：让 `/requirement-review` 支持「1 份主需求文档 + N 份设计文档」一起评审，综合多份文档输出**一份**重构需求文档。

---

## 0. 背景与问题

requirement-review 当前是「单份需求文档 → 单次评审 → 单份重构文档」的设计，整条链路只认单个输入：

- `bootstrap` 的 `_derive_req_id`（`runtime/qamaster_runtime.py`）优先级为 `--req-id > 单文件路径 > 内联文本`，全程单数；
- `_derive_from_file` 只 `open(path)` **一个**文件取首个 `#` 标题；
- Phase 0 契约卡只落盘一份 `REQ_<id>.md`；
- `extract_text.py` 命令行是单文件签名 `python extract_text.py <文件路径>`。

实际评审场景里，用户常提供多份材料：**原始需求文档 + 多份开发设计文档**，需要综合评审后输出一份最终重构文档。现状下传多份文档会派生错误 `req_id`、丢文档，无法综合。

本设计在不影响任何现有功能（单文档路径、case-design、460 测试逐字节不变）的前提下，补齐这一能力。

---

## 1. 目标与红线

### 要做的

- 支持 `@主需求.md @设计A.md @设计B.md` 的多 `@file` 输入；
- 第一个文件为主需求（决定 `req_id`、专家团信号词路由、MANIFEST「需求文档」列）；
- 其余文件按序作为「设计文档」，与主需求合并为**一份**评审语料 `REQ_<id>.md`；
- Phase 1~7 照旧，评审/重构统一基于合并后的 `REQ_<id>.md` 全文，综合输出一份 `ReviewedReq_<id>.md`。

### 红线（不做 / 不破坏）

- **case-design 零触碰**：`phases.py`、`verify_cases.py`、case-design 的 `DESIGN_<id>.md`、MANIFEST case-design schema 一律不动。
- **单文档路径逐字节不变**：单个 `@file` / 一段内联文本的行为、契约卡文本、gate、460 测试全保持原样。
- **不改 MANIFEST schema、不改状态机阶段结构、不新增 gate 类型**。

---

## 2. 核心设计原则

1. **Runtime 解析、模型执行**：多文档的「识别 + 清单落盘」由 Runtime 确定性完成（`bootstrap`）；「OCR 抽取 + 合并正文」仍由模型按 Phase 0 契约卡跑 `extract_text.py`（与现状分工一致，不把合并逻辑塞进 Runtime）。
2. **additive 设计**：所有改动都是「新增函数 + 新增注入分支 + 文档」，单文档代码路径一行不改。
3. **首个文件 = 主需求**：`req_id`、专家团信号词路由、MANIFEST「需求文档」列都以**第一个文件**为准。
4. **评审语料合并**：合并只发生在 `REQ_<id>.md` 这一份落盘文件上；Phase 1 起所有阶段照旧基于 `REQ_<id>.md` 全文，天然综合多份文档，无需改动后续任何阶段。

---

## 3. 数据流（改动前后对比）

```
【现状 · 单文档】
/requirement-review @需求.md
  → bootstrap --user-input "@需求.md" → _derive_req_id(单输入) → req_id
  → start --req-id <id>
  → Phase 0 契约卡 → 模型 extract_text.py @需求.md → 落盘 REQ_<id>.md

【新增 · 多文档】
/requirement-review @需求.md @设计A.md @设计B.md
  → bootstrap --user-input "..." → _parse_input_docs → files=[需求,设计A,设计B], is_multi=True
       → req_id = _derive_from_file(需求.md)
       → Runtime 落盘 requirement-review-out/INPUTS_<id>.md（清单）
  → start --req-id <id>（不改）
  → Phase 0 契约卡 → extra_card_text 注入「输入清单块」→ 模型逐份 extract_text.py
       → 按序合并落盘 REQ_<id>.md（主需求在前，各设计文档分节）
  → Phase 1~7 照旧（路由/评审/重构都基于合并后的 REQ_<id>.md）
```

---

## 4. 逐文件改动细节

### 改动 1 —— `runtime/qamaster_runtime.py`：输入解析（核心）

**新增函数 1**（放在 `_derive_from_text` 之后、`_derive_req_id` 附近）：

```python
def _parse_input_docs(ui):
    """把用户输入解析为多文档文件清单。
    仅当「整串按空白拆出的每个 token 都是已存在文件」且 ≥2 个时返回 (files, True)；
    否则返回 (None, False)——调用方走旧的 _derive_req_id 单输入路径（逐字节不变）。
    """
    ui = (ui or "").strip()
    if len(ui) >= 2 and ui[0] in "\"'" and ui[-1] == ui[0]:
        ui = ui[1:-1].strip()
    if not ui:
        return (None, False)
    toks = ui.split()
    if len(toks) < 2:
        return (None, False)
    files = []
    for t in toks:
        p = t[1:] if t.startswith("@") else t
        if not os.path.isfile(p):
            return (None, False)      # 任一 token 非文件 → 退回单输入
        files.append(p)
    return (files, True)
```

**新增函数 2**：

```python
def _write_inputs_manifest(workdir, spec, req_id, files):
    """多文档评审的输入清单（Runtime 落盘，模型只读）。
    幂等：已存在则覆盖刷新。失败静默（best-effort，不阻断 bootstrap）。
    """
    p = os.path.join(workdir, spec.output_dir, "INPUTS_%s.md" % req_id)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        lines = ["# 评审输入清单（qamaster Runtime 落盘·模型只读）", ""]
        for i, f in enumerate(files):
            role = "主需求文档" if i == 0 else "设计文档 %d" % i
            lines.append("- %s：%s" % (role, f))
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError:
        pass
```

**改 `cmd_bootstrap`**（约 `:1758`）：在 `req_id = _derive_req_id(...)` 前插入多文档分支，并把派生之后的碰撞检查/打印抽成尾部共用函数，避免复制：

```python
def cmd_bootstrap(a):
    spec = _spec(a)
    workdir = a.workdir
    state_store.migrate_legacy_state(workdir, spec.name)
    ui = (a.user_input or "").strip()
    files, is_multi = _parse_input_docs(ui)
    if is_multi and spec.name == "requirement-review":
        req_id = _derive_from_file(files[0]) or _clean_id(os.path.basename(files[0]))
        if not req_id:
            _die("bootstrap 无法从主需求文档派生需求标识。请显式传 --req-id <需求标识>。")
        _write_inputs_manifest(workdir, spec, req_id, files)
        _bootstrap_finish(a, spec, workdir, req_id)   # 复用下方碰撞检查+打印
        return
    req_id = _derive_req_id(a, spec, workdir)
    if not req_id:
        _die("bootstrap 无法从输入派生需求标识。请显式传 --req-id <需求标识>。")
    _bootstrap_finish(a, spec, workdir, req_id)
```

> `_bootstrap_finish` = 现 `cmd_bootstrap` 里 `req_id` 派生之后的全部碰撞检查 / `RESUME` / `MODIFY` / `BOOTSTRAP OK` 打印（原样搬入，单输入行为不变）。
> `is_multi and spec.name == "requirement-review"` 双保险，**case-design 走多文档分支时直接不生效**，天然隔离。

**不改**：`_derive_req_id`、`_derive_from_file`、`_derive_from_text`、`cmd_start`、`_card` 通用渲染、`state_store`、`manifest`。`start` 无需知道清单——清单文件由 bootstrap 落盘、由 Phase 0 契约卡读。

### 改动 2 —— `runtime/workflows/requirement_review.py`：Phase 0 注入清单块

`_extra_card_text` 现有 Phase 1（roster）+ Phase 4（确认话术）两分支。**新增 Phase 0 分支**，读 `INPUTS_<req_id>.md`：

```python
def _inputs_block(st):
    """Phase 0 契约卡注入：多文档评审的输入清单 + 合并指令。
    无 INPUTS_<req_id>.md（单文档）→ 返回 ""（Phase 0 卡片与现状逐字节一致）。
    """
    workdir = st.get("workdir") or ""
    req_id = (st.get("req_id") or "").strip()
    if not workdir or not req_id:
        return ""
    p = os.path.join(workdir, OUTPUT_DIR, "INPUTS_%s.md" % req_id)
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            body = f.read().strip()
    except OSError:
        return ""
    if not body:
        return ""
    return ("\n📥 本次为「多文档综合评审」：原始需求 + 设计文档须合并为一份评审语料。\n" +
            body + "\n" +
            "  处理要求：对清单中每份文件分别运行 `python skills/requirement-review/scripts/extract_text.py <文件> --json` 抽取纯文本，\n" +
            "  再按清单顺序合并落盘 requirement-review-out/REQ_<需求标识>.md——主需求文档在前，各设计文档按序追加，\n" +
            "  每份前加「## 输入文档：<文件名>」二级标题分节，保留各份内容原样、不删减。\n" +
            "  req_id、专家团信号词路由以【主需求文档】为准；后续评审/重构统一基于合并后的 REQ_<需求标识>.md 全文。")

def _extra_card_text(phase, st):
    if phase == 0:
        return _inputs_block(st)
    if phase == 1:
        return _roster_block(st)
    if phase == 4:
        return _EXTRA_PHASE4
    return ""
```

关键：**单文档不落盘 `INPUTS_<id>.md` → `_inputs_block` 返回 "" → Phase 0 卡片逐字节不变**（护现有测试）。

### 改动 3 —— `skills/requirement-review/SKILL.md`：输入协议补一段

在「第0阶段」输入探测步骤里补一条多文档说明（不影响单文档）：

> **多文档综合评审**：当契约卡出现「多文档综合评审」清单块时，按清单逐份 `extract_text.py` 抽取，按序合并落盘 `REQ_<id>.md`（主需求在前，各设计文档加 `## 输入文档：<文件名>` 分节）。单文档时无此清单，按原单文档流程执行。评审/重构统一基于合并后的 `REQ_<id>.md` 全文；`req_id` 与专家团路由以主需求文档为准。

### 改动 4 —— 文档同步（README / CHANGELOG 版本 bump）

- `README.md`：§6.2「提供需求文档」补「可多 `@file`：第一个为主需求，其余为设计文档，综合评审」；§9 产出物表补 `INPUTS_<id>.md`（仅多文档时出现）；版本头 bump。
- `CHANGELOG.md`：新增 `## [0.4.0] - 2026-08-24` 条目（多文档综合评审）。
- `runtime/requirement_review_phases.py`：**不改**（Phase 0 的 objective/gate 保持现状，多文档规则完全走 `extra_card_text` 注入，不碰 phase 注册表文本）。

### 改动 5 —— `scripts/test_runtime.py`：新增回归测试

1. `test_parse_input_docs()`：单文件 → `(None,False)`；单内联 → `(None,False)`；两文件 → `(files,True)` 且顺序正确；含非文件 token → `(None,False)`；带引号包裹；`@` 前缀剥离。
2. `test_rr_inputs_block_noop()`：无 `INPUTS_<id>.md` → `_extra_card_text(0, st)==""`（逐字节 no-op，护单文档卡片）。
3. `test_rr_inputs_block_inject()`：落盘 `INPUTS_<id>.md` → Phase 0 卡片含「多文档综合评审」+ 清单。
4. 现有 460 测试全跑，确认无回归。

---

## 5. 边界情况与降级

| 场景 | 行为 |
|---|---|
| 单个 `@file` | 走旧 `_derive_req_id`，逐字节不变 |
| 纯内联文本 | 走旧路径，不变 |
| 多 `@file` 里混有非文件 token（如内联补充说明） | 文件数 ≥2 → `(entries,True)`，非文件 token 保留为「补充说明 N」按出现位置排序（v0.4.1）；文件数 <2 → 退回旧单输入路径 |
| 路径含空格 | 用引号包裹 `@"设计 文档A.md"` → `shlex.split(posix=False)` 正确拆分（v0.4.1）；未包裹则按空白拆成多段，整段非文件 → 退回单输入 |
| 文件不存在 | 同上，退回单输入（旧路径派生的 id 行为不变） |
| 断点续跑 | `INPUTS_<id>.md` 是 Runtime 落盘的稳定文件，resume 后 Phase 0 契约卡仍可读到清单 |
| 修改已完成需求（`@ReviewedReq_<id>.md`） | 命中产物前缀剥离 → 走旧单输入路径，不受多文档影响 |
| case-design | `_parse_input_docs` 分支显式 `spec.name == "requirement-review"` 门禁，绝不触碰 |

---

## 6. 风险与回退

- **风险最低点**：所有改动是新增（新函数 + 新 extra_card_text 分支 + 文档 + 测试），单文档 / case-design 代码路径零改动；唯一「共享函数」改动是把 `cmd_bootstrap` 尾部抽成 `_bootstrap_finish`（纯搬移，行为等价）。
- **回退**：删除 `_inputs_block` + `_parse_input_docs` / `_write_inputs_manifest` 两个新增函数 + bootstrap 里的 `is_multi` 分支，即可完全回到现状。

---

## 7. 后续增强（v0.4.1 已落地，2026-08-25）

> 本节原列 3 项「后续增强」，已全部在 v0.4.1 实现（见 `skills/requirement-review/CHANGELOG.md`）。

1. **需求 vs 设计一致性核对**（✅ 已落地）：`_inputs_block` 追加核对指令——专家团逐条对照主需求文档的业务规则/数据口径/状态流转/异常边界，与各设计文档的技术/接口/数据结构细节，找出冲突与遗漏，结论纳入评审问题清单并统一回填。
2. **混排输入**（✅ 已落地）：`_parse_input_docs` 返回 `(entries, True)`，非文件 token 保留为 `("text", 片段)` 按出现位置排序，`_write_inputs_manifest` 落盘为「补充说明 N」；文件数 ≥2 才走多文档分支。
3. **路径含空格**（✅ 已落地）：`_parse_input_docs` 改用 `shlex.split(posix=False)`（保留 Windows 反斜杠）+ 逐 token 剥引号；外层引号仅在整串包裹且内部无同引号时剥离；引号未闭合回退 `ui.split()`。

---

## 8. 改动清单汇总

| # | 文件 | 改动性质 | 内容 |
|---|---|---|---|
| 1 | `runtime/qamaster_runtime.py` | 新增函数 + 改 bootstrap | `_parse_input_docs`、`_write_inputs_manifest`、`_bootstrap_finish` 抽取 + `is_multi` 分支 |
| 2 | `runtime/workflows/requirement_review.py` | 新增注入分支 | `_inputs_block` + `_extra_card_text` Phase 0 分支 |
| 3 | `skills/requirement-review/SKILL.md` | 补文档 | 第0阶段多文档说明 |
| 4 | `skills/requirement-review/README.md` / `CHANGELOG.md` | 文档 | §6.2/§9 补多文档 + 版本 bump |
| 5 | `scripts/test_runtime.py` | 新增测试 | `test_parse_input_docs` / `test_rr_inputs_block_noop` / `test_rr_inputs_block_inject` |
