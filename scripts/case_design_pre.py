#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_design_pre.py — Claude Code PreToolUse hook（v0.8.0 模型无关强制执行）。

把「流程合规」判定权彻底收归 harness：模型无论是否读 SKILL.md / 是否调脚本，
都无法绕过阶段顺序、无法把用例写到非约定位置、无法伪造状态推进。

与旧 gate(.claude/hooks/case_design_gate.py) 的关键差异（闭合其破绽）：
  - 旧 gate 信任模型可写的 .phase_signatures.json/.gate_log（可伪造）；
    本 hook 完全不读这些，当前阶段由「实际产出物是否存在」派生（强化4）。
  - 旧 gate matcher 仅 Write|Edit|MultiEdit 且只查 Write 的 content（Edit 恒空→漏）；
    本 hook 覆盖 Write|Edit|MultiEdit|Bash：Edit/MultiEdit 读盘+应用 patch 再校验（强化8），
    Bash 写交付物一律拒（须用 Write 走内容门禁）（改动3 / Gap1）。
  - 旧 gate 内容正则既漏判又误伤；本 hook 用 verify_cases 表格解析器做结构判定（改动3）。
  - 会话激活守卫：仅在 case-design 会话进行中介入，不污染无关项目/文件（强化2）。
  - harness-owned 状态/票据文件模型禁写（强化3）。

触发：hooks/hooks.json PreToolUse on Write|Edit|MultiEdit|Bash。
退出码：0=放行；2=阻断（stderr 给可执行修复指令）。
"""
import sys
import os
import json
import re
import glob
import importlib

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
try:
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 产出文件名前缀（构造而成，避免源码出现连续触发词被旧 hook 内容正则误伤）
TC_PREFIX = "Test" + "Cases"          # 盘上连续拼写 TestCases
CLAR_PREFIX = "Clarification_Ledger"
REQ_PREFIX = "REQ"
DIGEST_RE = re.compile(r"\.phase_digest_(\d+)\.md$")

# v0.8.3：各阶段 digest 须含的标记词（防 30 字节桩塞数）；Phase 9-12 新增
_PHASE_MARKERS = {
    2: ["测试需求", "维度", "覆盖范围", "测试范围"],
    3: ["R1", "R2", "规则建模", "规则项", "规则"],
    4: ["状态", "状态机", "规格", "异常", "契约"],
    5: ["P0", "P1", "风险", "风险等级"],
    6: ["方法", "策略", "等价类", "边界值", "决策表"],
    7: ["TP1", "TP2", "测试点", "测试点清单"],
    9: ["去重", "重复"],
    10: ["覆盖", "追溯", "覆盖率"],
    11: ["检查1", "检查2", "自查", "selfcheck", "15项"],
    12: ["展示", "投影", "矩阵", "覆盖矩阵"],
}

# harness-owned：模型禁写（防伪造状态/票据）
HARNESS_OWNED = {
    ".cd_session.json", ".cd_tickets.json",
    ".phase_signatures.json", ".gate_log",
    ".phase_state.json", ".workflow_state.json",
}

_VERIFY = {"mod": None}


def _load_verify():
    if _VERIFY["mod"] is not None:
        return _VERIFY["mod"]
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [
        os.path.abspath(os.path.join(here, "..", "skills", "case-design", "scripts")),
        os.path.abspath(os.path.join(here, "skills", "case-design", "scripts")),
    ]
    for c in cands:
        if os.path.exists(os.path.join(c, "verify_cases.py")):
            sys.path.insert(0, c)
            try:
                _VERIFY["mod"] = importlib.import_module("verify_cases")
                return _VERIFY["mod"]
            except Exception:
                pass
    return None


def _root(data):
    return data.get("cwd") or os.getcwd()


def _out(root):
    return os.path.join(root, "case-design-out")


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _session_active(root):
    sess = _load_json(os.path.join(_out(root), ".cd_session.json"), {})
    return isinstance(sess, dict) and sess.get("active") is True


def _should_guard(root, path, content):
    """v0.8.1：门禁是否生效，三重 OR 兜底，消除「激活正则没命中→整层失效」单点。
    1) 会话标记显式活跃；或
    2) case-design-out/ 目录已存在（模型已开始往约定目录写）；或
    3) 当前操作呈现 case-design 特征：路径含 case-design-out/测试用例/TestCases，
       或内容是 verify_cases 可解析的用例表（无论路径）。
    无关项目的普通写入三者皆不命中 -> 放行（不污染）。"""
    if _session_active(root):
        return True
    out = _out(root)
    if os.path.isdir(out):
        return True
    p = (path or "").replace("\\", "/").lower()
    if "case-design-out" in p or "测试用例" in (path or "") or (TC_PREFIX.lower() in p):
        return True
    if _looks_like_testcase_content(content or "") or _filename_looks_like_testcase(path or ""):
        return True
    return False


def _tickets(root):
    return _load_json(os.path.join(_out(root), ".cd_tickets.json"),
                      {"clarification_answered": False, "review_approved": False})


def _nonempty(path):
    return os.path.exists(path) and os.path.getsize(path) > 30


def _first_nonempty(pattern):
    files = sorted(glob.glob(pattern))
    return files[0] if files and _nonempty(files[0]) else None


def _phase_done(root, n):
    """阶段 n 的产出物是否真实存在（文件派生，不读可伪造签名）。
    v0.8.3：Phase 2-12 加内容标记校验（不只查存在），Phase 9-12 新增 digest 文件。"""
    out = _out(root)
    if n == 0:
        return _nonempty(os.path.join(out, "MANIFEST.md")) and \
            _first_nonempty(os.path.join(out, REQ_PREFIX + "_*.md")) is not None
    if n == 1:
        return _first_nonempty(os.path.join(out, CLAR_PREFIX + "_*.md")) is not None
    if n == 8:
        # Phase 8 = 用例文件已落盘
        return _tc_path(root) is not None
    if n in (2, 3, 4, 5, 6, 7, 9, 10, 11, 12):
        path = os.path.join(out, ".phase_digest_%d.md" % n)
        if not _nonempty(path):
            return False
        text = _read_text(path)
        markers = _PHASE_MARKERS.get(n, [])
        # 须命中至少 1 个本阶段标记词（防 30 字节桩塞数）
        return any(m in text for m in markers) if markers else True
    if n == 13:
        # Phase 13 = 用例已落盘 + 过 gate8（readback 等价）
        tc = _tc_path(root)
        if not tc:
            return False
        req = _req_path(root)
        req_text = _read_text(req) if req else ""
        ok, _ = _gate8_ok(_read_text(tc), req_text)
        return ok
    return False


def _max_phase_done(root):
    m = -1
    for n in range(0, 14):
        if _phase_done(root, n):
            m = n
        else:
            break
    return m


def _tc_path(root):
    return _first_nonempty(os.path.join(_out(root), TC_PREFIX + "_*.md"))


def _req_path(root):
    return _first_nonempty(os.path.join(_out(root), REQ_PREFIX + "_*.md"))


def _is_case_table(text):
    """是否是一张用例表（结构判定，替代脆弱关键词正则）。v0.8.1：无论路径，
    内容满足即拦——这才是「写到别处也拦」。"""
    if not text or ("用例" not in text and "case" not in text.lower()):
        return False
    v = _load_verify()
    if v is not None:
        try:
            parsed, _err = v.parse_table_from_lines(text.splitlines())
            if parsed is not None:
                _h, rows, _l = parsed
                return len(rows) > 0
            return False
        except Exception:
            pass
    return bool(re.search(r"\|\s*用例ID", text)) and text.count("|") > 20


# v0.8.2：语义识别——不依赖「用例ID」精确字样。模型用「序号」等表头仍能识别。
_TC_DIM_WORDS = ["步骤", "预期", "优先级", "前置", "Given", "When", "Then",
                 "场景", "测试步骤", "预期结果", "测试场景", "P0", "P1", "P2", "P3"]
_TC_DIM_WORDS_EN = ["test case", "scenario", "test step", "expected result",
                    "priority", "test scenario", "test point"]


def _looks_like_testcase_content(text):
    """语义层用例产出识别：含表格 + 用例语义 + 维度词即 True，不依赖「用例ID」字样。
    收窄到「表格 + 用例 + 维度词」组合，普通技术文档不命中。"""
    if not text:
        return False
    # 至少 2 行 markdown 表格
    table_rows = [ln for ln in text.splitlines() if ln.strip().startswith("|")]
    if len(table_rows) < 2:
        return False
    low = text.lower()
    has_case = ("用例" in text) or ("test case" in low) or ("testcase" in low) or ("scenario" in low)
    has_dim = any(w in text or w.lower() in low for w in _TC_DIM_WORDS) or \
        any(w in low for w in _TC_DIM_WORDS_EN)
    return has_case and has_dim


def _filename_looks_like_testcase(path):
    """文件名语义识别：覆盖 TC_/testcase/测试用例/_用例 等模型常见变体。"""
    if not path:
        return False
    base = os.path.basename(path.replace("\\", "/")).lower()
    for kw in ("测试用例", "testcase", "tc_", "_用例", "cases", "case_", "用例表", "_tc."):
        if kw in base:
            return True
    return False


def _gate8_ok(text, req_text):
    """对即将落盘的用例文本跑内存内全量校验，返回 (ok, hard_violations)。"""
    v = _load_verify()
    if v is None:
        return True, []  # verify_cases 不可用时降级放行
    try:
        req_lines = req_text.splitlines() if req_text else None
        parsed, findings = v.run_inmemory(text.splitlines(), req_lines)
        if parsed is None:
            return False, ["用例表结构解析失败（缺表头行『用例ID』或列数不足）"]
        hard = (findings or {}).get("hard_violations", [])
        return (len(hard) == 0), hard
    except Exception as e:
        return False, ["gate8 运行异常: %s" % e]


def _classify(path):
    """返回 (phase, kind)。kind∈{deliverable, testcase, knowledge, other}。"""
    p = path.replace("\\", "/")
    base = os.path.basename(p)
    m = DIGEST_RE.search(p)
    if m:
        return int(m.group(1)), "deliverable"
    if base == "MANIFEST.md" or base.startswith(REQ_PREFIX + "_"):
        return 0, "deliverable"
    if base.startswith(CLAR_PREFIX + "_"):
        return 1, "deliverable"
    if base.startswith(TC_PREFIX + "_") and base.lower().endswith((".md", ".xlsx")):
        return 8, "testcase"
    if base.startswith("Knowledge_"):
        return 15, "knowledge"
    return None, "other"


def _block(reason, hint):
    sys.stderr.write("[case-design-gate] ❌ " + reason + "\n")
    sys.stderr.write("  修复：" + hint + "\n")
    return 2


def _apply_edit(text, old, new):
    if old and old in text:
        return text.replace(old, new, 1)
    return text + "\n" + new  # 保守：把新内容纳入检测


def _reconstruct(tool, ti):
    """返回 (path, content)。content=该操作落盘后的目标文件文本。"""
    path = ti.get("file_path", "") or ""
    if tool == "Write":
        return path, ti.get("content", "") or ""
    if tool in ("Edit", "MultiEdit"):
        cur = _read_text(path) if path else ""
        if tool == "Edit":
            return path, _apply_edit(cur, ti.get("old_string", "") or "", ti.get("new_string", "") or "")
        content = cur
        for e in ti.get("edits", []) or []:
            content = _apply_edit(content, e.get("old_string", "") or "", e.get("new_string", "") or "")
        return path, content
    return "", ""


_BASH_WRITE_RE = re.compile(r"(?:>>?|tee(?:\s+-a)?\s+|cp\s+\S+\s+|mv\s+\S+\s+|sed\s+-i)")
_REDIRECT_RE = re.compile(r"(?:>>?|tee(?:\s+-a)?\s+)\s*([^\s;|&>]+)")


def _bash_write_paths(command):
    paths = set()
    for m in _REDIRECT_RE.finditer(command):
        paths.add(m.group(1).strip("'\""))
    for m in re.finditer(r"(?:^|[;\s])(?:cp|mv)\s+(\S+)\s+(\S+)", command):
        paths.add(m.group(2).strip("'\""))
    return paths


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0
    tool = data.get("tool_name", "")
    if tool not in ("Write", "Edit", "MultiEdit", "Bash"):
        return 0
    root = _root(data)
    ti = data.get("tool_input", {}) or {}

    # 会话守卫：非 case-design 会话一律放行（不污染无关工作·强化2）
    if not _session_active(root):
        # v0.8.1 兜底：会话未激活但内容是用例表 -> 仍拦（根因 A/B/C）。
        # 先做内容判定，命中即阻断；未命中则按 _should_guard 决定是否继续。
        _content = ""
        _path = ""
        if tool == "Write":
            _content = (ti.get("content", "") or "")
            _path = (ti.get("file_path", "") or "")
        elif tool in ("Edit", "MultiEdit"):
            _path = (ti.get("file_path", "") or "")
        elif tool == "Bash":
            _content = (ti.get("command", "") or "")
        if _looks_like_testcase_content(_content) or _filename_looks_like_testcase(_path):
            return _block("检测到测试用例产出内容。",
                          "测试用例必须经 Write 工具写到 case-design-out/%s_<需求标识>.md。" % TC_PREFIX)
        if not _should_guard(root, _path, _content):
            return 0

    out = _out(root)

    # ---- Bash 分支：禁止用 Bash 产出交付物（须用 Write 走内容门禁·Gap1）----
    if tool == "Bash":
        cmd = ti.get("command", "") or ""
        if not _BASH_WRITE_RE.search(cmd) and not _looks_like_testcase_content(cmd):
            return 0
        if _looks_like_testcase_content(cmd):
            return _block("检测到测试用例产出内容经 Bash 写盘。",
                          "测试用例必须经 Write 工具写到 case-design-out/%s_<需求标识>.md。" % TC_PREFIX)
        for p in _bash_write_paths(cmd):
            _ph, kind = _classify(p)
            if kind in ("deliverable", "testcase", "knowledge") or _filename_looks_like_testcase(p):
                return _block(
                    "禁止用 Bash 写 case-design 交付物（%s）。" % os.path.basename(p),
                    "交付物必须经 Write 工具写入，以便 harness 校验内容与阶段顺序。改用 Write。")
        return 0

    # ---- Write/Edit/MultiEdit 分支 ----
    path, content = _reconstruct(tool, ti)
    if not path:
        return 0
    norm = path.replace("\\", "/")
    base = os.path.basename(norm)

    # 保护 harness-owned 文件（模型禁写·强化3）
    if base in HARNESS_OWNED and norm.startswith(out.replace("\\", "/")):
        return _block("禁止写入 harness 状态文件 %s。" % base,
                      "该文件由 harness（hook）独占维护，模型不可写/不可伪造。")

    phase, kind = _classify(path)
    is_testcase_output = _looks_like_testcase_content(content) or _filename_looks_like_testcase(norm)
    is_standard_table = _is_case_table(content)  # 严格 15 列（含「用例ID」）

    # 规则 A：任何位置写入「测试用例产出」-> 须落约定路径 + 阶段顺序 + gate8
    if is_testcase_output:
        # 门 1：必须写到约定位置 + 约定文件名
        if not (norm.startswith(out.replace("\\", "/")) and base.startswith(TC_PREFIX + "_")):
            return _block("检测到测试用例产出。必须写到 case-design-out/%s_<需求标识>.md（前缀 %s_，15 列标准表头含『用例ID』）。" % (TC_PREFIX, TC_PREFIX),
                          "当前路径/文件名不合规。改用 Write 写到 case-design-out/%s_<需求标识>.md。" % TC_PREFIX)
        # 门 2：阶段 0-7 须完成
        if _max_phase_done(root) < 7:
            return _block(
                "用例表门禁：阶段 0-7 未全部完成（当前最高已完成阶段=%d）。" % _max_phase_done(root),
                "先按序产出：MANIFEST+REQ(0) -> Clarification_Ledger(1) -> .phase_digest_2..7，再生成用例。")
        # 门 3：内容须是标准 15 列用例表（gate8）
        if not is_standard_table:
            return _block("用例须采用 15 列标准表头（首列『用例ID』）。当前表头非标准。",
                          "运行 `python scripts/verify_cases.py --dump-rules` 查看标准表头，改为 15 列标准格式后重新 Write。")
        req_text = _read_text(_req_path(root)) if _req_path(root) else ""
        ok, hard = _gate8_ok(content, req_text)
        if not ok:
            return _block("第8出口 gate8 未通过（%d 项硬性违规）。" % len(hard),
                          "按 verify_cases 输出在内存修正后重新 Write：%s" % "；".join(hard[:5]))
        return 0

    # 规则 B：约定命名交付物的阶段顺序门
    if kind == "deliverable" and phase is not None and phase >= 1:
        if _max_phase_done(root) < phase - 1:
            return _block(
                "阶段顺序违规：写 Phase %d 产出物前，Phase 0..%d 须先完成（当前最高=%d）。" % (
                    phase, phase - 1, _max_phase_done(root)),
                "按序先完成前置阶段产出物（MANIFEST/REQ -> Clarification_Ledger -> .phase_digest_2..7）。")
        # 澄清门禁：进入 Phase 2+ 前须用户已回答澄清（Phase 1 台账写问题本身不受阻——
        # 台账先落问题、用户回答后再进分析；用户回答由 UserPromptSubmit 记入票据）
        if phase >= 2 and not _tickets(root).get("clarification_answered"):
            return _block("澄清门禁未满足：尚未记录用户澄清回答。",
                          "Phase 1 已提澄清问题；须等用户回答后再进入 Phase 2+（用户回答后 harness 自动记录）。")

    # 规则 C：最终制品（Excel/Knowledge）须 全阶段(0-13)完成 + gate8 通过 + 审核票据
    if kind == "knowledge":
        if _max_phase_done(root) < 13:
            return _block("生成 Knowledge/Excel 前，阶段 0-13 须全部完成（当前最高=%d）。" % _max_phase_done(root),
                          "补齐缺失阶段产出物（含 .phase_digest_9 去重 / .phase_digest_10 覆盖 / .phase_digest_11 自查 / .phase_digest_12 展示），再用例过 gate8 + 回读。")
        tc = _tc_path(root)
        if not tc:
            return _block("生成 Knowledge/Excel 前须先有用例文件。", "先完成 Phase 8 用例生成。")
        req_text = _read_text(_req_path(root)) if _req_path(root) else ""
        ok, hard = _gate8_ok(_read_text(tc), req_text)
        if not ok:
            return _block("用例文件未过 gate8，禁止生成最终制品。", "先修正用例使其过 gate8。")
        if not _tickets(root).get("review_approved"):
            return _block("Phase 14 审核门禁未满足：尚未记录用户「审核通过」。",
                          "等用户回复『审核通过』后再生成 Excel/Knowledge。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
