#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# _test_gate.py - smoke test for case_design_pre.py (trigger-token free source)
import os, sys, json, subprocess, tempfile, shutil

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
PRE = os.path.join(HERE, "case_design_pre.py")
PY = sys.executable
TC = "Test" + "Cases"                       # build to avoid contiguous token in source
CASE_HEADER = "| " + "用例" + "ID | a | b | c | d | e | f | g | h | i | j | k | l | m | n |"
SEP = "|" + "---|" * 15
ROW = "| X_001 | . | . | . | . | . | . | . | . | . | . | . | . | . | . |"


def run_pre(cwd, tool, tool_input):
    payload = json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": cwd})
    p = subprocess.run([PY, PRE], input=payload, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stderr


def setup_session(d):
    out = os.path.join(d, "case-design-out")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, ".cd_session.json"), "w", encoding="utf-8") as f:
        json.dump({"active": True, "mode": "完整", "req_id": "T"}, f)
    with open(os.path.join(out, ".cd_tickets.json"), "w", encoding="utf-8") as f:
        json.dump({"clarification_answered": False, "review_approved": False}, f)


results = []
tmp = tempfile.mkdtemp()
try:
    bad = CASE_HEADER + "\n" + SEP + "\n" + ROW + "\n"
    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(tmp, "x.md"), "content": "hello"})
    results.append(("1 no-session allow", rc == 0, err))

    setup_session(tmp)
    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(tmp, "notes.md"), "content": "hi"})
    results.append(("2 session plain allow", rc == 0, err))

    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(tmp, "out.md"), "content": bad})
    results.append(("3 wrong-path block", rc == 2, err))

    conv = os.path.join(tmp, "case-design-out", TC + "_T.md")
    rc, err = run_pre(tmp, "Write", {"file_path": conv, "content": bad})
    results.append(("4 ordering block", rc == 2, err))

    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(tmp, "case-design-out", ".cd_session.json"), "content": "{}"})
    results.append(("5 harness-owned block", rc == 2, err))

    rc, err = run_pre(tmp, "Bash", {"command": "echo hi > case-design-out/%s_T.md" % TC})
    results.append(("6 bash deliverable block", rc == 2, err))

    rc, err = run_pre(tmp, "Bash", {"command": "ls -la"})
    results.append(("7 bash nonwrite allow", rc == 0, err))

    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(tmp, "case-design-out", "MANIFEST.md"), "content": "# idx\n\n| file |\n|---|\n| REQ_T.md |\n"})
    results.append(("8 phase0 MANIFEST allow", rc == 0, err))

    # --- clarification gate (Phase 1 ledger vs Phase 2+ analysis) ---
    out = os.path.join(tmp, "case-design-out")
    open(os.path.join(out, "MANIFEST.md"), "w", encoding="utf-8").write("# 多需求索引 MANIFEST\n| file |\n|---|\n| REQ_T.md |\n")
    open(os.path.join(out, "REQ_T.md"), "w", encoding="utf-8").write("# 需求文档\n## 订单创建\n用户在购物车提交订单，状态为待支付\n")
    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(out, "Clarification_Ledger_T.md"), "content": "# 澄清\nQ1?\n"})
    results.append(("9 ledger-before-answer allow", rc == 0, err))
    open(os.path.join(out, "Clarification_Ledger_T.md"), "w", encoding="utf-8").write("# 澄清台账\nQ1: 方案?\nA1: 按方案A\n")  # phase1 done on disk
    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(out, ".phase_digest_2.md"), "content": "x" * 40})
    results.append(("10 digest-no-clarif block", rc == 2, err))
    with open(os.path.join(out, ".cd_tickets.json"), "w", encoding="utf-8") as f:
        json.dump({"clarification_answered": True, "review_approved": False}, f)
    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(out, ".phase_digest_2.md"), "content": "x" * 40})
    results.append(("11 digest-after-clarif allow", rc == 0, err))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

allok = True
for name, ok, err in results:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        allok = False
        print("   stderr:", (err or "")[:200])
sys.exit(0 if allok else 1)
