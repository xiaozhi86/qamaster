#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_design_stop.py — Claude Code Stop hook（v0.8.2 威慑层）。

模型被 PreToolUse 拦住后，可能改在对话里直出用例表（hook 拦不住已发出的文本）。
本 hook 在 turn 结束时检测：case-design 会话进行中、且对话里有用例产出内容、
但 case-design-out/ 无对应合规 Write → 阻断并要求改用 Write 落盘。

这是「威慑非预防」：文本可能已露出，无法撤回；但能阻止模型跳过文件交付直接收尾，
强制其必须经 Write 走内容门禁才能产出合规交付文件。

死循环防护：必须读 stop_hook_active 字段，为 true 时 exit 0 放行（避免触发 8 次阻断上限）。

触发：hooks/hooks.json Stop（无 matcher，turn 结束时跑）。
退出码：0=放行；2=阻断（stderr 给可执行修复指令）。
"""
import sys
import os
import json
import glob

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import case_design_pre as pre
except Exception:
    pre = None


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    # 死循环防护：harness 已在阻断循环中则放行，避免触发 8 次上限
    if data.get("stop_hook_active"):
        return 0

    if pre is None:
        return 0
    root = data.get("cwd") or os.getcwd()

    # 仅 case-design 会话进行中介入（不污染无关项目）
    if not pre._session_active(root):
        return 0

    # 评估本轮是否产出了合规用例文件（case-design-out/TestCases_*.md 过 gate8）
    out = pre._out(root)
    tc = pre._tc_path(root)
    has_valid_tc = False
    if tc:
        req = pre._req_path(root)
        req_text = pre._read_text(req) if req else ""
        ok, _ = pre._gate8_ok(pre._read_text(tc), req_text)
        has_valid_tc = ok

    # 已有合规用例文件 -> 放行（流程骨架已完成）
    if has_valid_tc:
        return 0

    # 无合规用例文件但会话进行中 -> 阻断，要求经 Write 走门禁
    sys.stderr.write(
        "[case-design-gate] ⚠️ 会话进行中但未产出合规用例文件（case-design-out/%s_*.md 且过 gate8）。\n"
        "  若已在对话中展示用例，须改用 Write 工具写到 case-design-out/%s_<需求标识>.md（15 列标准表头含『用例ID』），\n"
        "  经 harness 内容校验后才算合规交付。对话直出文本无法作为交付文件。\n"
        "  当前阶段最高完成=%d；先完成前置阶段产出物再生成用例。\n" % (
            pre.TC_PREFIX, pre.TC_PREFIX, pre._max_phase_done(root))
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
