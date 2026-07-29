#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_design_gate.py — Claude Code PreToolUse hook：硬拦截跳过门禁直接写产出物。

v0.7.1 设计动机：
  原 v0.7.0 只拦截 TestCases_*.md|xlsx，弱模型可以跳过 Phase 0-7
  在内存中生成用例内容然后展示，不触发 Write。

  本版升级为"全目录拦截"：
  - 任何 case-design-out/ 目录下的 Write 都触发门禁检查
  - 不同文件类型有不同的门禁要求
  - 迫使模型必须按阶段顺序产出，无法跳过
  - MANIFEST.md / REQ_*.md：
      允许无签名写入（Phase 0 产物），但写入后 stderr 提示运行 gate-phase 0
  - Clarification_Ledger_*.md：
      需要 Phase 0 已签名（否则 exit 2 阻止）
  - TestCases_*.md|xlsx：
      需要 gate8 exit=0 + Phase 0-7 全签（否则 exit 2 阻止）
  - Knowledge_*.md：
      需要 Phase 0-7 全签（知识总结在审核后生成）
  - 其他 case-design-out/ 文件：
      需要 Phase 0 签名

效果：
  - 模型必须先 Write MANIFEST/REQ（Phase 0 产物，允许）
  - 然后必须 gate-phase 0 签名
  - 才能 Write Clarification_Ledger（Phase 1）
  - 然后必须 gate-phase 1-7 签名 + gate8
  - 才能 Write TestCases

  每一步都被门禁卡住，无法跳过。

Claude Code PreToolUse hook 协议：
  stdin JSON → exit 0=放行，2=阻止（stderr 反馈模型）

跨平台：纯 Python 标准库。
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

# 命中 case-design-out/ 下的文件（跨平台）
_OUT_DIR_RE = re.compile(r"(?:^|[\\/])case-design-out[\\/]", re.I)

# 特定文件类型正则
_MANIFEST_RE = re.compile(r"(?:^|[\\/])case-design-out[\\/]MANIFEST\.md$", re.I)
_REQ_RE = re.compile(r"(?:^|[\\/])case-design-out[\\/]REQ_[^\\/]+\.md$", re.I)
_CLARIFICATION_RE = re.compile(r"(?:^|[\\/])case-design-out[\\/]Clarification_Ledger_[^\\/]+\.md$", re.I)
_TESTCASES_RE = re.compile(r"(?:^|[\\/])case-design-out[\\/]TestCases_[^\\/]+\.(md|xlsx)$", re.I)
_KNOWLEDGE_RE = re.compile(r"(?:^|[\\/])case-design-out[\\/]Knowledge_[^\\/]+\.md$", re.I)


def _match(path, regex):
    return bool(regex.search(path.replace("\\", "/")))


def _is_out_dir_file(path):
    return bool(_OUT_DIR_RE.search(path.replace("\\", "/")))


def _phase0_signed():
    """检查 Phase 0 是否已签名。"""
    if not os.path.exists(SIG_FILE):
        return False
    try:
        with open(SIG_FILE, "r", encoding="utf-8") as f:
            sigs = json.load(f)
        if not isinstance(sigs, dict):
            return False
        return sigs.get("phases", {}).get("0", {}).get("completed", False)
    except Exception:
        return False


def _all_phases_signed():
    """检查 Phase 0-7 是否全部签名。"""
    if not os.path.exists(SIG_FILE):
        return False, list(range(0, 8))
    try:
        with open(SIG_FILE, "r", encoding="utf-8") as f:
            sigs = json.load(f)
    except Exception:
        return False, list(range(0, 8))
    if not isinstance(sigs, dict):
        return False, list(range(0, 8))
    phases = sigs.get("phases", {}) if isinstance(sigs.get("phases"), dict) else {}
    missing = [p for p in range(0, 8) if not phases.get(str(p), {}).get("completed")]
    return len(missing) == 0, missing


def _gate8_passed():
    """检查 gate8 是否 exit=0。"""
    if not os.path.exists(GATE_LOG):
        return False, "无 .gate_log"
    best_rc = None
    try:
        with open(GATE_LOG, "r", encoding="utf-8") as f:
            for ln in f:
                parts = ln.rstrip("\n").split("|")
                if len(parts) >= 3 and parts[1] == "gate8":
                    try:
                        best_rc = int(parts[2])
                    except ValueError:
                        continue
    except Exception:
        return False, ".gate_log 读异常"
    if best_rc is None:
        return False, "无 gate8 条目"
    if best_rc != 0:
        return False, "gate8 exit=%s" % best_rc
    return True, ""


def _block(path, reason, hint):
    sys.stderr.write(
        "[case-design-gate] ❌ 禁止写入 %s\n" % os.path.basename(path)
        + "  原因：%s\n" % reason
        + "  修复：%s\n" % hint
    )
    return 2


def _hint(path, msg):
    """允许写入，但打印提示。"""
    sys.stderr.write("[case-design-gate] ⚠️  %s\n" % msg)
    return 0


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    tool = data.get("tool_name", "")
    if tool not in ("Write", "Edit", "MultiEdit"):
        return 0

    ti = data.get("tool_input", {}) or {}
    path = ti.get("file_path", "") or ""

    # 只拦截 case-design-out/ 目录下的文件
    if not path or not _is_out_dir_file(path):
        return 0

    # ===== 分文件类型门禁 =====

    # MANIFEST.md / REQ_*.md：允许写入，提示运行 gate-phase 0
    if _match(path, _MANIFEST_RE) or _match(path, _REQ_RE):
        # 检查 Phase 0 是否已签
        if _phase0_signed():
            return _hint(path, "%s 已写入，但 Phase 0 已签名，无需重复提示" % os.path.basename(path))
        return _hint(
            path,
            "%s 已写入。下一步：运行 `python scripts/run_phase.py gate-phase 0 \"MANIFEST.md,REQ_*.md\"` 签名 Phase 0" % os.path.basename(path)
        )

    # Clarification_Ledger_*.md：需要 Phase 0 签名
    if _match(path, _CLARIFICATION_RE):
        if not _phase0_signed():
            return _block(
                path,
                "Phase 0 未签名",
                "先运行 `python scripts/run_phase.py gate-phase 0 \"MANIFEST.md,REQ_*.md\"`"
            )
        return _hint(
            path,
            "%s 已写入。下一步：运行 `python scripts/run_phase.py gate-phase 1 \"Clarification_Ledger_*.md\"` 签名 Phase 1" % os.path.basename(path)
        )

    # TestCases_*.md|xlsx：需要 gate8 + Phase 0-7 全签
    if _match(path, _TESTCASES_RE):
        ok, why = _gate8_passed()
        if not ok:
            return _block(
                path,
                why,
                "先执行 Phase 0-7 + gate8："
                "`python scripts/run_phase.py gate-phase <N> \"<产出物>\"` "
                "然后 `python scripts/run_phase.py gate8 <TC.md> <REQ.md>`"
            )
        all_ok, missing = _all_phases_signed()
        if not all_ok:
            return _block(
                path,
                "缺阶段签名：%s" % ",".join(str(m) for m in missing),
                "逐阶段补签 `python scripts/run_phase.py gate-phase <N> \"<产出物>\"`"
            )
        sys.stderr.write("[case-design-gate] ✅ 门禁已过，放行 %s\n" % os.path.basename(path))
        return 0

    # Knowledge_*.md：需要 Phase 0-7 全签
    if _match(path, _KNOWLEDGE_RE):
        all_ok, missing = _all_phases_signed()
        if not all_ok:
            return _block(
                path,
                "知识总结需要 Phase 0-7 全签，缺：%s" % ",".join(str(m) for m in missing),
                "先完成测试用例设计并通过审核"
            )
        return 0

    # 其他 case-design-out/ 文件：需要 Phase 0 签名
    if not _phase0_signed():
        return _block(
            path,
            "写入 case-design-out/ 需要先完成 Phase 0",
            "先写入 MANIFEST.md 和 REQ_*.md，然后运行 gate-phase 0"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())