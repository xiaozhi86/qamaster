#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_design_gate.py — Claude Code PreToolUse hook：硬拦截跳过门禁直接写测试用例。

设计动机：case-design skill 的流程合规原本完全依赖模型自觉调用
run_phase.py / preflight.py / 各阶段 ref。强模型（glm-5.2）自觉合规，
弱模型（glm-5）会跳过 Phase 0-7 直接 Write(TestCases_*.md)，而 prompt
拦不住 Write。本 hook 把约束从"模型层"下沉到"harness 层"：在 Write/Edit
落到磁盘前由 harness 调用本脚本，未过门禁即 exit 2 阻止，与模型是否自觉无关。

触发范围（最小侵入）：
  仅当目标路径命中 <cwd>/case-design-out/TestCases_*.(md|xlsx) 时启用门禁。
  其余文件（MANIFEST / REQ / Clarification_Ledger / Knowledge / 项目内任意文件）
  一律 exit 0 放行，不影响正常开发与 Phase 0-1 的落盘。

门禁条件（TestCases 写入须同时满足）：
  1. case-design-out/.gate_log 含 gate8 条目且最近一次 exit=0（第8阶段出口已过）
  2. case-design-out/.phase_signatures.json 含 Phase 0-7 全部 completed=true
满足 → exit 0 放行；否则 → exit 2 阻止，stderr 给出可执行修复指引。

Claude Code PreToolUse hook 协议：
  - stdin 收到 JSON：{"tool_name":"Write","tool_input":{"file_path":...}, ...}
  - stdout JSON 可控制行为（此处用退出码足够）；exit 0=放行，2=阻止（stderr 反馈模型）
  - 非 0/2 的退出码视为错误（非阻断），故本脚本只在明确需阻止时返回 2

跨平台：纯 Python 标准库；路径用 os.path；cwd 由 Claude Code 设为项目根。
本脚本是 skill 配套 harness 资产，不删除。
"""
import sys
import os
import json
import re

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
try:
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT_DIR = os.path.join(os.getcwd(), "case-design-out")
GATE_LOG = os.path.join(OUT_DIR, ".gate_log")
SIG_FILE = os.path.join(OUT_DIR, ".phase_signatures.json")

# 命中 case-design-out/TestCases_<任意>.(md|xlsx)，跨平台斜杠
# (?:^|[\\/]) 兼容相对路径开头（无前导分隔符）与绝对路径
_TARGET_RE = re.compile(r"(?:^|[\\/])case-design-out[\\/]TestCases_[^\\/]+\.(md|xlsx)$", re.I)


def _is_target(path):
    # 归一化斜杠后用正则匹配相对路径头部
    return bool(_TARGET_RE.search(path.replace("\\", "/")))


def _gate8_status():
    """返回 (passed:bool, why:str)。passed=True 表示 .gate_log 中存在 exit=0 的 gate8。"""
    if not os.path.exists(GATE_LOG):
        return False, "无 .gate_log（从未跑过门禁脚本，Phase 0-8 均未留痕）"
    best_rc = None
    try:
        with open(GATE_LOG, "r", encoding="utf-8") as f:
            for ln in f:
                parts = ln.rstrip("\n").split("|")
                # 字段：script | phase | exit | digest_hash | note | state_version
                if len(parts) >= 3 and parts[1] == "gate8":
                    try:
                        rc = int(parts[2])
                        best_rc = rc  # 取最后一条 gate8 的 exit
                    except ValueError:
                        continue
    except Exception as e:
        return False, ".gate_log 读取异常：%s" % e
    if best_rc is None:
        return False, ".gate_log 中无 gate8 条目（未跑第8阶段出口门禁）"
    if best_rc != 0:
        return False, "gate8 最近 exit=%s（未通过，须先修至 exit=0 再 Write）" % best_rc
    return True, ""


def _missing_phases():
    """返回未签名的 Phase 列表（0-7）。"""
    if not os.path.exists(SIG_FILE):
        return list(range(0, 8))
    try:
        with open(SIG_FILE, "r", encoding="utf-8") as f:
            sigs = json.load(f)
    except Exception:
        return list(range(0, 8))
    if not isinstance(sigs, dict):
        return list(range(0, 8))
    phases = sigs.get("phases", {}) if isinstance(sigs.get("phases"), dict) else {}
    return [p for p in range(0, 8)
            if not phases.get(str(p), {}).get("completed")]


def _block(path, reason, hint):
    sys.stderr.write(
        "[case-design-gate] ❌ 禁止跳过门禁直接写 %s\n" % os.path.basename(path)
        + "  原因：%s\n" % reason
        + "  修复：%s\n" % hint
    )
    return 2


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        # stdin 非 JSON（非标准调用）→ 放行，避免误伤其他工具链
        return 0
    tool = data.get("tool_name", "")
    if tool not in ("Write", "Edit", "MultiEdit"):
        return 0
    ti = data.get("tool_input", {}) or {}
    path = ti.get("file_path", "") or ""
    if not path or not _is_target(path):
        return 0

    # ===== 命中 TestCases 写入：启用硬门禁 =====
    ok, why = _gate8_status()
    if not ok:
        return _block(
            path, why,
            "先按流程执行 Phase 0-7，逐阶段签名 "
            "`python scripts/run_phase.py gate-phase <N> \"<产出物>\"`，"
            "再跑第8出口 `python scripts/run_phase.py gate8 <TC.md> <REQ.md>`（须 exit=0）。"
        )

    miss = _missing_phases()
    if miss:
        return _block(
            path,
            "阶段签名不全，缺 Phase：%s" % ",".join(str(m) for m in miss),
            "逐阶段补签 `python scripts/run_phase.py gate-phase <N> \"<产出物>\"`"
            "（Phase 2-7 内存阶段可传空串 \"\"）。"
        )

    # 放行（仅打印到 stderr，不污染 stdout）
    sys.stderr.write("[case-design-gate] ✅ 门禁已过，放行 %s\n" % os.path.basename(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
