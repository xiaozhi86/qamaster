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
CASE_HEADER = "| " + "用例" + "ID | 步骤 | 预期 | c | d | e | f | g | h | i | j | k | l | m | n |"
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

    # --- v0.8.1: 根因 A/B/C/D 对抗场景 ---
    # 12) 会话未启动 + 写用例表到非约定路径 -> 必须拦（根因 B 兜底 + C 内容优先）
    tmp2 = tempfile.mkdtemp()
    try:
        rc, err = run_pre(tmp2, "Write", {"file_path": os.path.join(tmp2, "电销通话AI总结_测试用例.md"), "content": bad})
        results.append(("12 no-session wrong-path table block", rc == 2, err))
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)

    # 13) 会话未启动 + 普通文档写入 -> 放行（不误伤）
    tmp3 = tempfile.mkdtemp()
    try:
        rc, err = run_pre(tmp3, "Write", {"file_path": os.path.join(tmp3, "README.md"), "content": "# 项目说明\n这是一个普通项目\n"})
        results.append(("13 no-session plain doc allow", rc == 0, err))
    finally:
        shutil.rmtree(tmp3, ignore_errors=True)

    # 14) Bash heredoc 含用例表内容 -> 拦（根因 C 的 Bash 通道）
    rc, err = run_pre(tmp, "Bash", {"command": "cat > out.md <<'EOF'\n" + bad + "\nEOF"})
    results.append(("14 bash heredoc table block", rc == 2, err))

    # --- v0.8.2: 根因 E 对抗场景（模型换文件名/换表头绕过）---
    # 15) TC_ 前缀 + 自定义表头（序号|用例名称|步骤|预期）写到 case-design-out/ -> 必须拦
    custom_tc = "| 序号 | 用例名称 | 模块 | 优先级 | 步骤 | 预期结果 |\n|---|---|---|---|---|---|\n| 1 | 单通通话AI分析 | 单通 | P0 | MQ消费 | 返回labels |\n"
    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(out, "TC_电销通话AI总结.md"), "content": custom_tc})
    results.append(("15 TC_ prefix custom-header block", rc == 2, err))

    # 16) TC_ 前缀 + 自定义表头写到非约定路径 -> 必须拦
    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(tmp, "模型服务", "TC_x.md"), "content": custom_tc})
    results.append(("16 TC_ prefix wrong-path block", rc == 2, err))

    # 17) 约定 TestCases_ + 标准 15 列 + 0-7 完成 + gate8 过 -> 放行（回归）
    good_table = "| 用例ID | 关联需求ID | 关联规则 | 测试类型 | 测试维度 | 所属模块 | 用例名称 | Given | When | Then | 编辑模式 | 标签 | 责任人 | 用例等级 | 用例状态 |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n| ORD_CREATE_001 | REQ-1 | R1 | 功能 | 输入验证 | 订单 | 【订单】【创建】【成功】【返回200】 | 已登录 | 提交订单 | 返回200 SUCCESS | STEP | AI | AI | P0 | Completed |\n"
    # setup: phase 2-7 digests with correct markers per phase
    phase_content = {
        2: "# 测试需求分析\n维度：功能/边界/异常/状态\n覆盖范围：订单创建全链路\n",
        3: "# 规则建模\nR1: 订单金额计算规则\nR2: 库存扣减规则\n",
        4: "# 规格建模\n状态机：待支付→已支付→已发货\n异常：库存不足\n",
        5: "# 风险分析\nP0: 资金安全\nP1: 库存一致性\n",
        6: "# 策略匹配\n方法：等价类+边界值+决策表\n",
        7: "# 测试点建模\nTP1: 订单创建正向\nTP2: 金额边界\n",
    }
    for n in range(2, 8):
        open(os.path.join(out, ".phase_digest_%d.md" % n), "w", encoding="utf-8").write(phase_content[n])
    json.dump({"clarification_answered": True, "review_approved": False}, open(os.path.join(out, ".cd_tickets.json"), "w"))
    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(out, TC + "_ORD.md"), "content": good_table})
    results.append(("17 valid TestCases_ 15col allow", rc == 0, err))

    # 18) 普通技术文档（含「步骤」但非用例表格）-> 不误拦
    plain_doc = "# 操作手册\n## 步骤一\n先做A再做B\n"
    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(tmp, "manual.md"), "content": plain_doc})
    results.append(("18 plain manual no-false-positive", rc == 0, err))

    # --- v0.8.3: Phase 9-12 + 13 全阶段强制 ---
    # 19) Knowledge 未完成 Phase 9-12 -> 必须拦
    json.dump({"clarification_answered": True, "review_approved": True}, open(os.path.join(out, ".cd_tickets.json"), "w"))
    # persist TC
    open(os.path.join(out, TC + "_ORD.md"), "w", encoding="utf-8").write(good_table)
    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(out, "Knowledge_ORD.md"), "content": "# 知识总结\n"})
    results.append(("19 Knowledge-without-phase9-12 block", rc == 2, err))

    # 20) 补齐 Phase 9-12 digest + Knowledge -> 放行
    phase_9_12 = {
        9: "# 去重\n去除重复用例 2 条\n",
        10: "# 覆盖率校验\n覆盖率 95%，追溯全通过\n",
        11: "# 自查\n检查1 通过\n检查2 通过\n15项全通过\n",
        12: "# 展示\n用例投影 + 覆盖矩阵\n",
    }
    for n in range(9, 13):
        open(os.path.join(out, ".phase_digest_%d.md" % n), "w", encoding="utf-8").write(phase_9_12[n])
    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(out, "Knowledge_ORD.md"), "content": "# 知识总结\n业务沉淀\n"})
    results.append(("20 Knowledge-after-all-phases allow", rc == 0, err))

    # 21) 30 字节桩 digest（无标记词）-> 视为未完成
    open(os.path.join(out, ".phase_digest_9.md"), "w", encoding="utf-8").write("x" * 31)
    rc, err = run_pre(tmp, "Write", {"file_path": os.path.join(out, "Knowledge_ORD2.md"), "content": "# 知识总结2\n"})
    results.append(("21 stub-digest-no-marker block", rc == 2, err))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

allok = True
for name, ok, err in results:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        allok = False
        print("   stderr:", (err or "")[:200])
sys.exit(0 if allok else 1)
