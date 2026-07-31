#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_design_post.py — Claude Code PostToolUse hook（v0.8.0 模型无关强制执行）。

每次交付物落盘后，由 harness 注入「下一阶段行动指令」（复用 case_design_workflow
的 PHASE_INSTRUCTIONS + ref）。模型无需读 SKILL.md 即知下一步——这是「与模型是否
读 SKILL.md 无关」的彻底实现。

阶段推进由「实际产出物」派生（复用 case_design_pre._max_phase_done，不读可伪造状态）：
写 MANIFEST/REQ/digest -> 推进到下一未完成阶段；写用例文件 -> Phase 9。

触发：hooks/hooks.json PostToolUse on Write|Edit|MultiEdit。
退出码恒 0（PostToolUse 不阻断；用 stdout 注入上下文）。
"""
import sys
import os
import json
import importlib

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_pre():
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    try:
        return importlib.import_module("case_design_pre")
    except Exception:
        return None


def _load_workflow():
    c = os.path.abspath(os.path.join(HERE, "..", "skills", "case-design", "scripts"))
    if os.path.exists(os.path.join(c, "case_design_workflow.py")):
        if c not in sys.path:
            sys.path.insert(0, c)
        try:
            return importlib.import_module("case_design_workflow")
        except Exception:
            return None
    return None


def _is_deliverable(base, tc_prefix):
    if base == "MANIFEST.md" or base.startswith("REQ_"):
        return True
    if base.startswith("Clarification_Ledger_"):
        return True
    if base.startswith(".phase_digest_"):
        return True
    if base.startswith(tc_prefix + "_") and base.lower().endswith(".md"):
        return True
    return False


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    tool = data.get("tool_name", "")
    if tool not in ("Write", "Edit", "MultiEdit"):
        return 0
    root = data.get("cwd") or os.getcwd()
    ti = data.get("tool_input", {}) or {}
    path = (ti.get("file_path", "") or "").replace("\\", "/")
    base = os.path.basename(path)

    pre = _load_pre()
    if pre is None:
        return 0
    if not pre._session_active(root):
        return 0
    tc_prefix = pre.TC_PREFIX
    if not _is_deliverable(base, tc_prefix):
        return 0

    wf = _load_workflow()
    PH = wf.PHASE_INSTRUCTIONS if wf else {}

    # 用例文件落盘 -> Phase 8 完成；否则按产出物派生的最高阶段
    if base.startswith(tc_prefix + "_") and base.lower().endswith(".md"):
        completed = 8
    else:
        completed = pre._max_phase_done(root)

    nxt = completed + 1
    if nxt > 15:
        sys.stdout.write("【harness】全部阶段产出物已就绪。可进行人工审核；审核通过后生成 Excel/Knowledge。\n")
        return 0
    info = PH.get(nxt)
    if info:
        sys.stdout.write("【harness · 下一阶段 Phase %d · %s】\n" % (nxt, info.get("name", "")))
        sys.stdout.write((info.get("model_action") or "") + "\n")
        if info.get("ref"):
            sys.stdout.write("参考文档：%s\n" % info["ref"])
    else:
        sys.stdout.write("【harness】Phase %d 无需文件产出（内存处理），继续后续阶段。\n" % nxt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
