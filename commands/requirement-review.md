---
description: 需求文档多角色评审（requirement-review）：需求文档 → 7-Agent 并行评审 → 重构高质量需求文档（Runtime 受控流程，0-7 阶段状态机）
argument-hint: "[可选：需求文档 / 指令]"
---

启动 **qamaster Runtime 受控流程**（模型负责思考，Runtime 负责控制——流程状态由 Python 状态机裁决，任何模型不可绕过）。

## 路径解析（先做·一次）

本命令文件位于 plugin 根目录的 `commands/` 下，Runtime 位于同级 `../runtime/`。**候选列表存在性探测**（同 case-design，适配 marketplace 缓存安装）：

```bash
# 有序候选：逐一 [ -f ] 探测，取第一个命中
PLUGIN_ROOT=""
for c in \
  "$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)" \
  "$HOME/.claude/plugins/qamaster" \
  $(ls -d "$HOME"/.claude/plugins/cache/qamaster/qamaster/*/ 2>/dev/null | sort -V | tail -1) \
  "D:/qamaster" \
; do
  [ -n "$c" ] && [ -f "${c%/}/runtime/qamaster_runtime.py" ] && PLUGIN_ROOT="${c%/}" && break
done
echo "PLUGIN_ROOT=$PLUGIN_ROOT"
```

- 候选 4 为本地开发仓库路径，按实际克隆位置调整；候选 3 为 marketplace 缓存安装（glob 取版本号最大者）。
- **全部候选未命中 → 判定"Runtime 未安装"**：允许进入薄客户端降级（SKILL.md 7-Agent 流程定义执行，阶段顺序与门禁由模型自律）。
- **候选命中但执行报错** → 判定"Runtime 存在但调用失败"：**禁止降级**，退避重试至多 3 次；仍失败则暂停流程、不得落盘 `ReviewedReq_*.md`。

## 第一步：启动 Runtime（bootstrap → start，必须先做·单步不变对用户透明）

```bash
cd "<用户当前项目根>"
# 1) bootstrap 派生 req_id（不创建状态·幂等可重跑）；检测到在途状态输出 RESUME
REQ_ID=$(python "$PLUGIN_ROOT/runtime/qamaster_runtime.py" bootstrap \
    --workflow requirement-review --user-input "$ARGUMENTS" --workdir "$(pwd)" \
    | sed -n 's/.*req_id=\([^ ]*\).*/\1/p' | head -1)
# 2) start 按 (workflow, req_id) 创建/续跑状态（状态落 .qamaster/requirement-review/<req_id>/）
python "$PLUGIN_ROOT/runtime/qamaster_runtime.py" start \
    --workflow requirement-review --req-id "$REQ_ID" --workdir "$(pwd)"
```

- cwd 必须是**用户项目根**（产出物写 `./requirement-review-out/`，状态写 `./.qamaster/requirement-review/<req_id>/`）。
- `req_id` 由 bootstrap 派生（文件取首个 `# ` 标题清洗 / 内联取首个非空行；去重，碰撞加 `-YYYYMMDD`），模型不在阶段内派生 id。bootstrap 若失败（空 id 等），停下报错指引，不得跳过。
- 输出含【RUNTIME CONTRACT 契约卡】：先按其提示一次性阅读业务规范 `skills/requirement-review/SKILL.md`（7-Agent 评审细则/输入协议），随后回到契约卡执行当前 Phase。
- 已存在进行中的同一 req 时，bootstrap 输出 `RESUME` → `start` 走 resume 分支断点续跑（恢复契约卡，不重置）。

## 第二步：按契约卡执行当前 Phase

每阶段只做契约卡 `ALLOWED` 中的事，产物达标后：

```bash
python "$PLUGIN_ROOT/runtime/qamaster_runtime.py" gate --workflow requirement-review --req-id "$REQ_ID"     # 出口门禁（机器判定，禁止自证）
```

- `PASS` → `next` 获取下一阶段契约卡；`FAIL` → 按修复指令原地修复后重跑 `gate`（**禁止自行跳阶段**）。
- 人工确认门（Phase 4 用户确认）：输出【问题详情列表】+【请确认】三项后**停止等待**；收到用户答复先落盘，再 `gate` 看放行判定，确认后 `confirm --workflow requirement-review --req-id "$REQ_ID"`。
- 审核反馈有问题 → `fail --to <受影响最深阶段号> --workflow requirement-review --req-id "$REQ_ID" --reason "..."` 回退重走。
- **gate PASS 时 Runtime 自动维护 MANIFEST 索引**（Phase 0 `add` / Phase 1 `update` 评审问题清单 / Phase 5 `update` 最终需求文档 / Phase 7 `complete`），模型无需、也禁止 Write/Edit MANIFEST.md。

## 第三步：每次接到用户新消息时

**先 `status --workflow requirement-review --req-id "$REQ_ID"` 恢复权威状态**（当前阶段/待办/门禁类型），再继续——禁止凭对话记忆推断流程位置。查所有在途需求用 `status --workflow requirement-review --all`。

## 运行模式登记（可选）

```bash
python "$PLUGIN_ROOT/runtime/qamaster_runtime.py" set --workflow requirement-review --req-id "$REQ_ID" --mode auto|light
```

> requirement-review 无流程深度裁剪（8 阶段全执行），仅 `--mode` 影响 Phase 4 人工确认门的放行口径（完整模式等用户；auto/light 连跑标注待审自动放行）。

## 铁律

1. 0→1→…→7 严格顺序，跳阶段/合并阶段/提前产出后续阶段产物 = 执行缺陷。
2. `gate` 未 PASS 不进下一阶段；Phase 4 人工门未收到用户确认不得 `next`。
3. 修改场景从 `fail --to` 起点依次顺序重走到 Phase 7，不得跳阶段。
4. **MANIFEST 由 Runtime 维护**：`requirement-review-out/MANIFEST.md` 是多需求共享索引，由 Runtime 在 gate PASS 时自动维护。模型**禁止 Write/Edit MANIFEST.md**。失步时 `python runtime/qamaster_runtime.py manifest reconcile` 重建。
5. 业务规范以 `skills/requirement-review/SKILL.md` 为唯一细则来源；Runtime 只做流程控制，不改变任何评审规则。**流程由 Runtime 严格控制、与模型无关。**

用户输入（作为本流程入参）：

$ARGUMENTS