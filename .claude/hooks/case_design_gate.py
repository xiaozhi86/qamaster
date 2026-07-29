#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_design_gate.py — Claude Code PreToolUse hook：硬拦截跳过门禁。

v0.7.2 设计动机：
  v0.7.1 只拦截 case-design-out/ 目录的 Write。
  弱模型（glm-5）会完全绕过 skill 约定，把测试用例写到其他位置。

  本版升级为"内容特征检测"：
  - 不仅检查路径，还检查 Write 的内容是否是测试用例
  - 如果内容包含测试用例特征，强制要求：
    1. 写到 case-design-out/TestCases_*.md
    2. 满足门禁（gate8 + Phase 0-7 签名）

门禁规则：
  A. case-design-out/ 目录下的 Write：
     按文件类型分档门禁（MANIFEST/REQ 允许，其他需签名）

  B. 非 case-design-out/ 目录的 Write：
     检查内容是否包含测试用例特征：
     - 文件名含"测试用例"/"TestCases"
     - 内容含"# 测试用例"/"## 一、.*测试用例"/"测试用例ID"等
     如果包含，强制要求写到 case-design-out/ 并检查门禁

效果：模型无论如何输出测试用例，都会被门禁卡住。
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

# === 路径正则 ===
_OUT_DIR_RE = re.compile(r"(?:^|[\\/])case-design-out[\\/]", re.I)
_MANIFEST_RE = re.compile(r"(?:^|[\\/])case-design-out[\\/]MANIFEST\.md$", re.I)
_REQ_RE = re.compile(r"(?:^|[\\/])case-design-out[\\/]REQ_[^\\/]+\.md$", re.I)
_CLARIFICATION_RE = re.compile(r"(?:^|[\\/])case-design-out[\\/]Clarification_Ledger_[^\\/]+\.md$", re.I)
_TESTCASES_PATH_RE = re.compile(r"(?:^|[\\/])case-design-out[\\/]TestCases_[^\\/]+\.(md|xlsx)$", re.I)
_KNOWLEDGE_RE = re.compile(r"(?:^|[\\/])case-design-out[\\/]Knowledge_[^\\/]+\.md$", re.I)

# === 内容特征正则（检测是否是测试用例内容）===
_TESTCASES_NAME_RE = re.compile(r"(测试用例|TestCases?)[_\\/]", re.I)
_TESTCASES_CONTENT_RE = re.compile(
    r"(#\s*测试用例|##\s*一、.*测试用例|测试用例ID|测试用例名称|用例等级|测试用例设计|用例总数)",
    re.I
)


def _match(path, regex):
    return bool(regex.search(path.replace("\\", "/")))


def _is_out_dir_file(path):
    return bool(_OUT_DIR_RE.search(path.replace("\\", "/")))


def _is_testcases_content(path, content):
    """检测是否是测试用例内容（基于文件名和内容特征）。"""
    # 文件名含"测试用例"/"TestCases"
    if _TESTCASES_NAME_RE.search(path):
        return True
    # 内容含测试用例特征
    if content and _TESTCASES_CONTENT_RE.search(content):
        return True
    return False


def _phase0_signed():
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
    content = ti.get("content", "") or ""

    if not path:
        return 0

    # ===== A. case-design-out/ 目录下的 Write =====
    if _is_out_dir_file(path):
        # MANIFEST.md / REQ_*.md：允许写入，提示运行 gate-phase 0
        if _match(path, _MANIFEST_RE) or _match(path, _REQ_RE):
            if _phase0_signed():
                return _hint(path, "%s 已写入，Phase 0 已签名" % os.path.basename(path))
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
        if _match(path, _TESTCASES_PATH_RE):
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

    # ===== B. 非 case-design-out/ 目录的 Write：内容特征检测 =====
    if _is_testcases_content(path, content):
        sys.stderr.write(
            "[case-design-gate] ❌ 检测到测试用例内容，禁止写到非约定位置\n"
            + "  文件：%s\n" % path
            + "  原因：测试用例必须写到 case-design-out/TestCases_*.md 并满足门禁\n"
            + "  修复：\n"
            + "    1. 按 skill 流程执行 Phase 0-7\n"
            + "    2. 逐阶段签名：python scripts/run_phase.py gate-phase <N> \"<产出物>\"\n"
            + "    3. 第8阶段出口：python scripts/run_phase.py gate8 <TC.md> <REQ.md>\n"
            + "    4. 通过后写到 case-design-out/TestCases_<需求标识>.md\n"
        )
        return 2

    # 其他文件放行
    return 0


if __name__ == "__main__":
    sys.exit(main())