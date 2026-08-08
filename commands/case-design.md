---
description: 测试用例设计（case-design）：需求文档/原型 → 测试用例 Markdown/Excel（Runtime 受控流程，0-14 阶段状态机）
argument-hint: "[可选：需求标识 / 需求文档 / 指令]"
---

启动 **qamaster Runtime 受控流程**（模型负责思考，Runtime 负责控制——流程状态由 Python 状态机裁决，任何模型不可绕过）。

## 路径解析（先做·一次）

本命令文件位于 plugin 根目录的 `commands/` 下，Runtime 位于同级 `../runtime/`。**候选列表存在性探测**（v0.6.0 修复：单一 `$0` 推导在 marketplace 缓存安装下会打错路径）：

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
- **全部候选未命中 → 判定"Runtime 未安装"**：允许进入薄客户端降级（SKILL.md Runtime 控制协议·情形A，带降级最低门禁）。
- **候选命中但执行报错**（如 Bash 分类器暂不可用）→ 判定"Runtime 存在但调用失败"：**禁止降级**，按 SKILL.md 降级协议情形B 退避重试，仍失败则暂停流程、不得落盘 TestCases。

## 第一步：启动 Runtime（bootstrap → start，必须先做·单步不变对用户透明）

```bash
cd "<用户当前项目根>"
# 1) bootstrap 派生 req_id（不创建状态·幂等可重跑）；检测到在途状态输出 RESUME
REQ_ID=$(python "$PLUGIN_ROOT/runtime/qamaster_runtime.py" bootstrap \
    --workflow case-design --user-input "$ARGUMENTS" --workdir "$(pwd)" \
    | sed -n 's/.*req_id=\([^ ]*\).*/\1/p' | head -1)
# bootstrap 输出 BOOTSTRAP RESUME req_id=<id> 时 REQ_ID 同样取到该 id（复用，不重建状态）
# 2) start 按 (workflow, req_id) 创建/续跑状态（状态落 .qamaster/case-design/<req_id>/）
python "$PLUGIN_ROOT/runtime/qamaster_runtime.py" start \
    --workflow case-design --req-id "$REQ_ID" --workdir "$(pwd)"
```

- cwd 必须是**用户项目根**（产出物写 `./case-design-out/`，状态写 `./.qamaster/case-design/<req_id>/`）。
- `req_id` 由 bootstrap 派生（文件取首个 `# ` 标题清洗 / 内联取首个非空行；去重，碰撞加 `-YYYYMMDD`），模型不在阶段内派生 id——消除"先有鸡还是先有蛋"。bootstrap 若失败（空 id 等），停下报错指引，不得跳过。
- 输出含【RUNTIME CONTRACT 契约卡】：先按其提示一次性阅读全局业务规范 `skills/case-design/SKILL.md`（避坑红线/输入协议/运行模式），随后回到契约卡执行当前 Phase。
- 已存在进行中的同一 req 时，bootstrap 输出 `RESUME` → `start` 走 resume 分支断点续跑（恢复契约卡，不重置）——分区路径即 resume 判据，不同需求各自续跑互不干扰。

## 第二步：按契约卡执行当前 Phase

每阶段只做契约卡 `ALLOWED` 中的事，产物达标后：

```bash
python "$PLUGIN_ROOT/runtime/qamaster_runtime.py" gate --workflow case-design --req-id "$REQ_ID"     # 出口门禁（机器判定，禁止自证）
```

- `PASS` → `next` 获取下一阶段契约卡；`FAIL` → 按修复指令原地修复后重跑 `gate`（**禁止自行跳阶段**）。
- 人工确认门（Phase 1 澄清 / Phase 14 审核）：输出确认请求后**停止等待**；收到用户答复先落盘（台账），再 `gate` 看放行判定。
- 用户确认（审核通过/答复完毕）→ `confirm --workflow case-design --req-id "$REQ_ID"`；Excel 许可门用户拒绝 → `reject`；审核反馈有问题 → `fail --to <受影响最深阶段号> --workflow case-design --req-id "$REQ_ID" --reason "..."` 回退重走。
- **gate PASS 时 Runtime 自动维护 MANIFEST 索引**（Phase 0 `add` / Phase 1 `update` 台账 / Phase 13 `update` 用例文件 / Phase 14 `complete`），模型无需、也禁止 Write/Edit MANIFEST.md（铁律 4）。

## 第三步：每次接到用户新消息时

**先 `status --workflow case-design --req-id "$REQ_ID"` 恢复权威状态**（当前阶段/待办/门禁类型），再继续——禁止凭对话记忆推断流程位置。查所有在途需求用 `status --workflow case-design --all`。

## 阶段判定登记（Phase 0 执行中完成）

```bash
python "$PLUGIN_ROOT/runtime/qamaster_runtime.py" set --workflow case-design --req-id "$REQ_ID" --depth heavy|medium|light --input-kind requirement|contract
# 用户声明 连跑/自动跑/批量 → set --mode auto；声明 轻量/小改/低风险 → set --mode light
```

> `req_id` 已由 bootstrap 派生写入 `state.req_id`，此处不再 `set --req-id`（已移除该参数——状态分区目录在 start 时已按 req_id 确定，阶段内改 req_id 会做无意义且危险的目录迁移）。仅 `set --depth/--input-kind/--mode`。

## 铁律

1. 0→1→…→14(→15) 严格顺序，跳阶段/合并阶段/提前产出后续阶段产物 = 执行缺陷。
2. `gate` 未 PASS 不进下一阶段；人工门未收到用户确认不得 `next`。
3. 修改场景从 `fail --to` 起点依次顺序重走到 Phase 14，不得跳阶段。
4. **MANIFEST 由 Runtime 维护**：`case-design-out/MANIFEST.md` 是多需求共享索引，由 Runtime 在 gate PASS 时自动维护（Phase 0 `add` / Phase 1 `update` 台账 / Phase 13 `update` 用例文件 / Phase 14 `complete`）。模型**禁止 Write/Edit MANIFEST.md**——多需求索引的协调权属于 Runtime。失步时 `python runtime/qamaster_runtime.py manifest reconcile` 重建。
5. 业务规范以 `skills/case-design/SKILL.md` + `skills/case-design/references/*.md` 为唯一细则来源；Runtime 只做流程控制，不改变任何质量规则。**流程由 Runtime 严格控制、与模型无关。**

用户输入（作为本流程入参）：

$ARGUMENTS
