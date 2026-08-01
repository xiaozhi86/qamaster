#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_design_submit.py — Claude Code UserPromptSubmit hook（v0.8.0 模型无关强制执行）。

harness 层「真正用户输入」唯一入口。三职责：
  1) 开局引导：识别 case-design 调用 -> 建会话标记(.cd_session.json, harness-owned)
     -> 注入 Phase 0 行动清单（模型无需读 SKILL.md 即可起步）。
  2) 运行模式记录：解析 完整/连跑/轻量 -> 写入会话标记（模型不可改）。
  3) 暂停门禁票据：解析用户澄清回答 / 「审核通过」-> 写 .cd_tickets.json，
     作为澄清(Phase1)/审核(Phase14)门禁「已满足」的唯一可信来源。

模型无法伪造：本 hook 由 harness 在用户提交时调用，看到的是用户原始 prompt；
且 PreToolUse(case_design_pre.py) 禁止模型 Write 这些 harness-owned 文件。

触发：hooks/hooks.json UserPromptSubmit（无 matcher，每次用户提交都跑）。
退出码恒 0（不阻断用户输入；用 stdout 注入上下文）。
"""
import sys
import os
import json
import re

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 产出文件名前缀（构造而成，避免源码出现连续触发词被旧 hook 内容正则误伤）
TC_PREFIX = "Test" + "Cases"  # 盘上连续拼写 TestCases


def _root(payload):
    return payload.get("cwd") or os.getcwd()


def _out(root):
    return os.path.join(root, "case-design-out")


def _session_file(root):
    return os.path.join(_out(root), ".cd_session.json")


def _ticket_file(root):
    return os.path.join(_out(root), ".cd_tickets.json")


def _load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _detect_mode(prompt):
    if re.search(r"连跑|自动跑|批量", prompt):
        return "连跑"
    if re.search(r"轻量|小改|低风险", prompt):
        return "轻量"
    return "完整"


def _is_start(prompt):
    # v0.8.1：覆盖裸命令 + 命名空间命令 + 中文意图 + 结构化标记。
    # 关键修复：`/qamaster:case-design` 不含子串 `/case-design`（`qamaster:` 前无斜杠），
    # 故须显式匹配 `qamaster:case-design` / 去斜杠容错。
    if re.search(r"/(?:qamaster:)?case-design|qamaster:case-design|case-design", prompt):
        return True
    if re.search(r"<<<需求文档开始>>>|【业务需求描述】|【需求标识】", prompt):
        return True
    if re.search(r"设计测试用例|测试用例设计|需求转用例|用例设计", prompt):
        return True
    return False


def _req_id(prompt):
    m = re.search(r"【需求标识】\s*([^\n\r]+)", prompt)
    if m:
        return re.sub(r'[\\/*?:"<>|\s]+', "_", m.group(1).strip())[:60]
    return "需求"


def _is_review_ok(prompt):
    return bool(re.search(r"审核通过|无问题|通过\b|approved|确认通过", prompt))


def _is_clarif(prompt):
    return bool(re.search(r"Q\d|按方案|方案[ABC]|选[ABC]|假设A|按\s*\d", prompt))


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    prompt = payload.get("prompt", "") or ""
    root = _root(payload)
    out = _out(root)
    msgs = []
    try:
        if _is_start(prompt):
            sess = _load(_session_file(root), None)
            if not (isinstance(sess, dict) and sess.get("active")):
                mode = _detect_mode(prompt)
                rid = _req_id(prompt)
                os.makedirs(out, exist_ok=True)
                _save(_session_file(root), {"active": True, "mode": mode, "req_id": rid})
                _save(_ticket_file(root), {"clarification_answered": False, "review_approved": False})
                msgs.append("【case-design 会话已启动·harness 驱动】")
                msgs.append("运行模式：%s（P0/P1 硬阻断；P2/P3 按模式放行）" % mode)
                msgs.append("需求标识：%s" % rid)
                msgs.append("")
                msgs.append("【Phase 0 · 需求定位】请按序完成（无需读 SKILL.md，按本清单做即可）：")
                msgs.append("  1. 创建目录 case-design-out/")
                msgs.append("  2. 写 case-design-out/MANIFEST.md（多需求索引）")
                msgs.append("  3. 把需求文档落盘为 case-design-out/REQ_%s.md（须含 ## 二级标题分节）" % rid)
                msgs.append("  4. 后续每阶段产出物须落盘到 case-design-out/；harness 自动校验并给下一阶段指令")
                msgs.append("")
                msgs.append("说明：流程合规由 harness（hook）判定，与所用模型无关。跳阶段/写到非约定位置/伪造状态都会被拦。")
        else:
            sess = _load(_session_file(root), None)
            if isinstance(sess, dict) and sess.get("active"):
                mode = _detect_mode(prompt)
                if mode != "完整":
                    sess["mode"] = mode
                    _save(_session_file(root), sess)
                tick = _load(_ticket_file(root), {"clarification_answered": False, "review_approved": False})
                changed = False
                if _is_clarif(prompt) and not tick.get("clarification_answered"):
                    tick["clarification_answered"] = True
                    changed = True
                    msgs.append("【澄清门禁】已记录用户澄清回答（Phase 1 门禁满足）。")
                if _is_review_ok(prompt) and not tick.get("review_approved"):
                    tick["review_approved"] = True
                    changed = True
                    msgs.append("【审核门禁】已记录用户「审核通过」（Phase 14 门禁满足，可生成 Excel/Knowledge）。")
                if changed:
                    _save(_ticket_file(root), tick)
    except Exception as e:
        sys.stderr.write("[case_design_submit] %s\n" % e)

    if msgs:
        sys.stdout.write("\n".join(msgs) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
