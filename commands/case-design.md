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

## 第一步：启动 Runtime（必须先做）

```bash
cd "<用户当前项目根>" && python "$PLUGIN_ROOT/runtime/qamaster_runtime.py" start --user-input "$ARGUMENTS"
```

- cwd 必须是**用户项目根**（产出物与状态写入 `./case-design-out/`）。
- 输出含【RUNTIME CONTRACT 契约卡】：先按其提示一次性阅读全局业务规范 `skills/case-design/SKILL.md`（避坑红线/输入协议/运行模式），随后回到契约卡执行当前 Phase。
- 已存在进行中的流程时，`start` 自动断点续跑（恢复契约卡，不重置）。

## 第二步：按契约卡执行当前 Phase

每阶段只做契约卡 `ALLOWED` 中的事，产物达标后：

```bash
python "$PLUGIN_ROOT/runtime/qamaster_runtime.py" gate     # 出口门禁（机器判定，禁止自证）
```

- `PASS` → `next` 获取下一阶段契约卡；`FAIL` → 按修复指令原地修复后重跑 `gate`（**禁止自行跳阶段**）。
- 人工确认门（Phase 1 澄清 / Phase 14 审核）：输出确认请求后**停止等待**；收到用户答复先落盘（台账），再 `gate` 看放行判定。
- 用户确认（审核通过/答复完毕）→ `confirm`；Excel 许可门用户拒绝 → `reject`；审核反馈有问题 → `fail --to <受影响最深阶段号> --reason "..."` 回退重走。

## 第三步：每次接到用户新消息时

**先 `status` 恢复权威状态**（当前阶段/待办/门禁类型），再继续——禁止凭对话记忆推断流程位置。

## 阶段判定登记（Phase 0 执行中完成）

```bash
python "$PLUGIN_ROOT/runtime/qamaster_runtime.py" set --req-id "<需求标识>" --depth heavy|medium|light --input-kind requirement|contract
# 用户声明 连跑/自动跑/批量 → set --mode auto；声明 轻量/小改/低风险 → set --mode light
```

## 铁律

1. 0→1→…→14(→15) 严格顺序，跳阶段/合并阶段/提前产出后续阶段产物 = 执行缺陷。
2. `gate` 未 PASS 不进下一阶段；人工门未收到用户确认不得 `next`。
3. 修改场景从 `fail --to` 起点依次顺序重走到 Phase 14，不得跳阶段。
4. 业务规范以 `skills/case-design/SKILL.md` + `skills/case-design/references/*.md` 为唯一细则来源；Runtime 只做流程控制，不改变任何质量规则。

用户输入（作为本流程入参）：

$ARGUMENTS
