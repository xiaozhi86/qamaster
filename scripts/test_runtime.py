#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_runtime.py — qamaster Runtime 自证测试（无 LLM，纯状态机验证）

验证 Runtime Engineering 的核心承诺：
  1. 流程严格 0→1→…→15 顺序，非法跳转被拒绝
  2. 人工门（Phase 1/14/15）未确认前禁止推进
  3. 自动门机器判定（Phase 0 产物缺失 → FAIL；补齐 → PASS）
  4. Phase 13 真实调用 verify_md.py + verify_cases.py 回读（含失败路径）
  5. 审核反馈 → fail 回退到指定阶段重走
  6. 审核通过 → 知识沉淀 → Excel 许可 → gen_excel.py 真实生成（openpyxl 缺失时跳过）
  7. 连跑模式 Phase 14 自动放行（REVIEW_PENDING 审计痕迹）
  8. 状态一致性 verify 命令
  9. 断点续跑（二次 start 恢复状态而非重置）

运行：python scripts/test_runtime.py
退出码：0=全过；1=有失败
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RT = os.path.join(ROOT, "runtime", "qamaster_runtime.py")
SKILL_SCRIPTS = os.path.join(ROOT, "skills", "case-design", "scripts")
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import phases as _RT_PHASES  # noqa: E402

REQ_ID = "自证需求-20260802"

HEADER = ("| 用例ID | 关联需求ID | 关联规则 | 测试类型 | 测试维度 | 所属模块 | 用例名称 | "
          "Given | When | Then | 编辑模式 | 标签 | 责任人 | 用例等级 | 用例状态 |")
SEP = "| -- | -- | -- | -- | -- | -- | -- | ----- | ---- | ---- | ---- | ---- | ---- | ---- | ---- |"

REQ_DOC = """# 自证需求

## 订单创建

用户在购物车提交订单，系统创建订单，状态为待支付，扣减库存。数量需为 1-99 整数。

## 库存扣减

下单即扣库存；库存不足时拒绝下单并返回库存不足错误。
"""

TC_MD = """# 测试用例 - {req}

## 规则建模

- **订单创建主流程** [来源:需求文档订单创建]
- **库存扣减时机** [来源:需求文档库存扣减]

## 风险清单

| 风险ID | 风险等级 | 风险描述 | 关联模块 | 风险来源 |
| -- | -- | -- | -- | -- |
| R1 | P0 | 库存超卖（并发扣减） | 订单 | 需求推导 |

## 测试点清单

| 测试点ID | 场景类型 | 测试点描述 | 关联模块 |
| -- | -- | -- | -- |
| TP1 | 正常 | 创建订单扣库存 | 订单 |

{header}
{sep}
| {req}_CREATE_001 | 见需求文档订单创建 | R1:库存扣减、TP1:创建订单 | 功能 | 接口验证 | 订单 | 【订单模块】【创建订单】【库存充足】【创建成功】 | 用户已登录；购物车有商品A001数量2；库存充足 | 1.进入购物车点击提交订单；2.确认金额 | 接口返回200且status=SUCCESS；订单主存储中订单状态为待支付；库存数量减少2；发送订单创建消息事件 | STEP | AI | AI | P0 | Completed |
| {req}_CREATE_002 | 见需求文档订单创建 | TP1:数量边界 | 边界 | 边界验证 | 订单 | 【订单模块】【创建订单】【数量边界1与99】【创建成功】 | 用户已登录；购物车有商品A001 | 1.数量设为1提交；2.数量设为99提交 | 接口返回200且status=SUCCESS；订单创建成功；库存数量减少对应值 | STEP | AI | AI | P1 | Completed |
| {req}_CREATE_003 | 见需求文档订单创建 | TP1:数量非法 | 异常 | 输入验证 | 订单 | 【订单模块】【创建订单】【数量0与100非法】【返回参数非法错误】 | 用户已登录 | 1.数量设为0提交；2.数量设为100提交 | 接口返回400且错误码=PARAM_INVALID；订单未创建；库存未扣减 | STEP | AI | AI | P2 | Completed |
| {req}_CREATE_004 | 见需求文档订单创建 | R1:重复提交幂等 | 幂等 | 幂等验证 | 订单 | 【订单模块】【创建订单】【并发重复提交】【仅创建一个订单】 | 用户已登录；购物车有商品A001 | 1.同一请求连续提交两次 | 仅创建1个订单；库存仅扣减一次；无重复消息事件 | STEP | AI | AI | P1 | Completed |
| {req}_STOCK_001 | 见需求文档库存扣减 | R1:扣减时机 | 功能 | 数据验证 | 库存 | 【库存模块】【库存扣减】【下单即扣】【扣减成功】 | 用户已登录；商品A001库存充足 | 提交订单 | 接口返回200且status=SUCCESS；库存数量减少对应值；记录库存变更日志 | STEP | AI | AI | P1 | Completed |
"""

KNOWLEDGE_MD = """# 知识总结 - 自证需求

---
**元数据**
需求名称：自证需求
当前版本：v1.0
首次生成：2026-08-02
最近更新：2026-08-02
更新模块：订单
本轮变更：新增
来源统计：需求文档 2 条 / 澄清台账 1 条 / 测试用例 4 条
---

## 一、业务流程

1. 用户进入购物车点击提交订单；2. 系统创建订单，状态为待支付；3. 扣减库存；4. 发送订单创建消息。

## 二、状态机

| 状态 | 含义 | 是否终态 |
| -- | -- | -- |
| 待支付 | 订单已创建未支付 | 否 |

## 三、业务逻辑

| 计算项 | 规则 | 结果 |
| -- | -- | -- |
| 订单金额 | 单价×数量 | 金额正确 |

## 四、业务规则

- 数量规则：1-99 整数。

## 五、数据规则

| 字段名 | 校验规则 | 示例值 |
| -- | -- | -- |
| 数量 | 1-99 整数 | 2 |

## 六、权限模型

本需求不涉及。

## 七、异常处理

- 库存不足：拒绝下单并返回库存不足错误。

## 八、配置项

本需求不涉及。

## 九、存储信息

订单主存储（自然语言描述，未提供具体表名）。

## 十、接口信息

订单创建接口（入参：商品、数量；出参：订单状态）。

## 十一、上下游依赖

- 下游：订单创建消息事件。

## 十二、变更历史

| 更新时间 | 更新模块 | 更新类型 |
| -- | -- | -- |
| 2026-08-02 | 订单 | 新增 |

## 十三、待澄清项

本需求已全部澄清。
"""

MANIFEST_MD = """# 需求文件索引 MANIFEST

## 索引表

| 需求标识 | 需求名称 | 需求文档 | 台账文件 | 测试用例文件 | 知识总结 | 状态 | 更新时间 |
| -- | -- | -- | -- | -- | -- | -- | -- |
| `{req}` | 自证需求 | REQ_{req}.md | Clarification_Ledger_{req}.md | TestCases_{req}.md | Knowledge_{req}.md | 进行中 | 2026-08-02 |
"""

LEDGER_MD = """# 澄清台账 Clarification_Ledger - {req}

| 问题ID | 类型 | 原问题 | 用户答复 | 状态 | 建议回答角色 | 登记轮次 |
| -- | -- | -- | -- | -- | -- | -- |
| Q1 | 数据规则 | 库存扣减时机？ | 下单即扣 | 已解决 | @开发 | {req} |
"""

passed = []
failed = []


def check(name, cond, detail=""):
    if cond:
        passed.append(name)
        print("  [OK] %s" % name)
    else:
        failed.append((name, detail))
        print("  [FAIL] %s  %s" % (name, detail))


def run(workdir, *args, expect_rc=None):
    proc = subprocess.run([sys.executable, RT] + list(args) + ["--workdir", workdir],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if expect_rc is not None:
        assert proc.returncode == expect_rc, "rc=%d expected %d\ncmd=%s\nstdout=%s\nstderr=%s" % (
            proc.returncode, expect_rc, args, proc.stdout, proc.stderr)
    return proc


def run_debug(workdir, *args):
    proc = subprocess.run([sys.executable, RT] + list(args) + ["--workdir", workdir],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("    cmd=%s rc=%d | %s" % (" ".join(args), proc.returncode,
                                   (proc.stdout or proc.stderr).strip().splitlines()[0][:100] if (proc.stdout or proc.stderr).strip() else ""))
    return proc


def state_of(workdir):
    p = os.path.join(workdir, "case-design-out", ".runtime", "state.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def w(workdir, rel, content):
    p = os.path.join(workdir, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


def openpyxl_available():
    try:
        import openpyxl  # noqa: F401
        return True
    except ImportError:
        return False


def main():
    print("== qamaster Runtime 自证测试 ==")
    workdir = tempfile.mkdtemp(prefix="qamaster-rt-test-")
    try:
        _run_suite(workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print("\n结果：%d 通过 / %d 失败" % (len(passed), len(failed)))
    if failed:
        for name, detail in failed:
            print("  FAILED: %s — %s" % (name, detail))
        return 1
    return 0


def _run_suite(workdir):
    out = "case-design-out"

    print("\n[1] start 启动 + 契约卡")
    r = run(workdir, "start", "--req-id", REQ_ID, expect_rc=0)
    check("start 输出契约卡", "RUNTIME CONTRACT" in r.stdout and "Phase 0" in r.stdout)
    st = state_of(workdir)
    check("初始状态 phase=0 RUNNING", st["current_phase"] == 0 and st["status"] == "RUNNING")

    print("\n[2] 非法跳转防护")
    r = run(workdir, "next", expect_rc=2)
    check("未过 gate 禁止 next", "RUNTIME_ERROR" in r.stdout)

    print("\n[3] Phase 0 自动门：产物缺失 FAIL → 补齐 PASS")
    r = run(workdir, "gate", expect_rc=0)
    check("gate 输出 FAIL（REQ 未落盘）", "GATE RESULT: FAIL" in r.stdout)
    st = state_of(workdir)
    check("FAIL 后停留 Phase 0", st["current_phase"] == 0 and st["status"] == "RUNNING")
    w(workdir, os.path.join(out, "REQ_%s.md" % REQ_ID), REQ_DOC)
    w(workdir, os.path.join(out, "MANIFEST.md"), MANIFEST_MD.format(req=REQ_ID))
    r = run(workdir, "gate", expect_rc=0)
    check("补齐产物后 gate PASS", "GATE RESULT: PASS" in r.stdout)
    r = run(workdir, "next", expect_rc=0)
    check("next 进入 Phase 1 契约卡", "Phase 1" in r.stdout and "澄清" in r.stdout)

    print("\n[4] Phase 1 人工确认门：未确认禁止推进")
    r = run(workdir, "gate", expect_rc=0)
    check("人工门判定 WAIT", "GATE RESULT: WAIT" in r.stdout)
    r = run(workdir, "next", expect_rc=2)
    check("WAIT_USER_CONFIRM 状态禁止 next", "RUNTIME_ERROR" in r.stdout)
    st = state_of(workdir)
    check("状态=WAIT_USER_CONFIRM", st["status"] == "WAIT_USER_CONFIRM")
    w(workdir, os.path.join(out, "Clarification_Ledger_%s.md" % REQ_ID), LEDGER_MD.format(req=REQ_ID))
    r = run(workdir, "confirm", expect_rc=0)
    check("用户答复后 confirm 放行", "CONFIRM ACCEPTED" in r.stdout)

    print("\n[5] Phase 2-12 自动门依序推进（验证严格顺序）")
    run(workdir, "set", "--depth", "heavy", expect_rc=0)
    expect_seq = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    for pid in expect_seq:
        r = run(workdir, "next", expect_rc=0)
        st = state_of(workdir)
        check("推进到 Phase %d" % pid, st["current_phase"] == pid)
        r = run(workdir, "gate", expect_rc=0)
        check("Phase %d gate PASS" % pid, "GATE RESULT: PASS" in r.stdout)
    st = state_of(workdir)
    check("completed 连续 0-11", st["completed"] == list(range(0, 12)))

    print("\n[6] Phase 13 写盘门：真实 verify_md + verify_cases")
    run(workdir, "next", expect_rc=0)
    r = run(workdir, "gate", expect_rc=0)
    check("用例未写盘时 gate FAIL", "GATE RESULT: FAIL" in r.stdout)
    w(workdir, os.path.join(out, "TestCases_%s.md" % REQ_ID),
      TC_MD.format(req=REQ_ID, header=HEADER, sep=SEP))
    r = run(workdir, "gate", expect_rc=0)
    check("用例写盘后 gate PASS（真实脚本校验）", "GATE RESULT: PASS" in r.stdout,
          r.stdout[-800:])

    print("\n[7] Phase 14 人工审核门：完整模式必须 confirm")
    run(workdir, "next", expect_rc=0)
    r = run(workdir, "gate", expect_rc=0)
    check("审核门 WAIT（完整模式）", "GATE RESULT: WAIT" in r.stdout)
    r = run(workdir, "next", expect_rc=2)
    check("未审核禁止 next", "RUNTIME_ERROR" in r.stdout)

    print("\n[8] 审核反馈 → fail 回退重走")
    r = run(workdir, "fail", "--to", "8", "--reason", "断言模糊需修改", expect_rc=0)
    st = state_of(workdir)
    check("回退到 Phase 8 且清除后续 completed", st["current_phase"] == 8 and st["completed"] == list(range(0, 8)))
    check("回退输出起点判定提示", "依次顺序执行至 Phase 14" in r.stdout)
    for pid in [9, 10, 11, 12, 13, 14]:
        run_debug(workdir, "gate")
        run_debug(workdir, "next")
    st = state_of(workdir)
    check("重走回到 Phase 14", st["current_phase"] == 14)

    print("\n[9] 审核通过 → 知识沉淀后置动作 → Excel 许可门")
    r = run(workdir, "confirm", expect_rc=0)
    check("confirm 输出知识沉淀指引", "Knowledge_" in r.stdout and "MANIFEST" in r.stdout)
    # 负路径1：未登记知识沉淀直接 next → 拒绝
    r = run(workdir, "next", expect_rc=2)
    check("未登记知识沉淀禁止进 Excel 门", "知识沉淀未完成" in r.stdout)
    # 负路径2：知识总结结构不合格（缺维度）→ set --knowledge done 拒绝
    bad_k = os.path.join(workdir, out, "Knowledge_%s.md" % REQ_ID)
    w(workdir, os.path.join(out, "Knowledge_%s.md" % REQ_ID),
      "# 知识总结\n\n---\n需求名称：x\n当前版本：v1.0\n首次生成：2026-08-02\n最近更新：2026-08-02\n来源统计：需求文档 1 条 / 澄清台账 1 条 / 测试用例 1 条\n---\n\n## 一、业务流程\n\nx\n")
    r = run(workdir, "set", "--knowledge", "done", expect_rc=2)
    check("知识总结缺维度时拒绝登记", "知识总结门禁未过" in r.stdout)
    # 正路径：写合格知识总结 → 登记 → next
    w(workdir, os.path.join(out, "Knowledge_%s.md" % REQ_ID), KNOWLEDGE_MD)
    run(workdir, "set", "--knowledge", "done", expect_rc=0)
    r = run(workdir, "next", expect_rc=0)
    st = state_of(workdir)
    check("进入 Phase 15 许可门", st["current_phase"] == 15)
    check("completed 含 0-14", st["completed"] == list(range(0, 15)))
    r = run(workdir, "gate", expect_rc=0)
    check("许可门 WAIT（询问用户）", "GATE RESULT: WAIT" in r.stdout)

    print("\n[10] Excel 生成（gen_excel.py 真实调用）")
    if openpyxl_available():
        r = run(workdir, "confirm", expect_rc=0)
        check("Excel 生成+校验通过，流程 DONE", "流程 DONE" in r.stdout, r.stdout[-600:])
        xlsx = os.path.join(workdir, out, "TestCases_%s.xlsx" % REQ_ID)
        check("xlsx 文件真实存在", os.path.isfile(xlsx))
        st = state_of(workdir)
        check("状态 DONE 且 15 已 completed", st["status"] == "DONE" and 15 in st["completed"])
    else:
        print("  [SKIP] openpyxl 不可用，改测 reject 路径")
        r = run(workdir, "reject", expect_rc=0)
        st = state_of(workdir)
        check("用户拒绝 Excel → DONE", st["status"] == "DONE" and st.get("excel") == "declined")

    print("\n[11] verify 状态一致性")
    r = run(workdir, "verify", expect_rc=0)
    check("verify OK", "STATE VERIFY OK" in r.stdout)

    print("\n[12] 断点续跑（二次 start 不重置）")
    workdir2 = tempfile.mkdtemp(prefix="qamaster-rt-test2-")
    try:
        run(workdir2, "start", "--req-id", REQ_ID, expect_rc=0)
        w(workdir2, os.path.join(out, "REQ_%s.md" % REQ_ID), REQ_DOC)
        w(workdir2, os.path.join(out, "MANIFEST.md"), MANIFEST_MD.format(req=REQ_ID))
        run(workdir2, "gate", expect_rc=0)
        run(workdir2, "next", expect_rc=0)
        r = run(workdir2, "start", expect_rc=0)
        check("二次 start 检测到进行中流程并续跑", "断点续跑" in r.stdout)
        st = state_of(workdir2)
        check("续跑保持 Phase 1", st["current_phase"] == 1)
    finally:
        shutil.rmtree(workdir2, ignore_errors=True)

    print("\n[13] 连跑模式 Phase 14 自动放行（审计痕迹）")
    workdir3 = tempfile.mkdtemp(prefix="qamaster-rt-test3-")
    try:
        run(workdir3, "start", "--req-id", REQ_ID, "--mode", "auto", expect_rc=0)
        w(workdir3, os.path.join(out, "REQ_%s.md" % REQ_ID), REQ_DOC)
        w(workdir3, os.path.join(out, "MANIFEST.md"), MANIFEST_MD.format(req=REQ_ID))
        run(workdir3, "gate", expect_rc=0)
        run(workdir3, "next", expect_rc=0)
        run(workdir3, "confirm", expect_rc=0)   # 澄清门确认 → Phase 1 GATE_PASSED
        run(workdir3, "next", expect_rc=0)      # 进入 Phase 2
        for pid in [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]:
            run(workdir3, "gate", expect_rc=0)
            run(workdir3, "next", expect_rc=0)
        st = state_of(workdir3)
        assert st["current_phase"] == 13, "expect phase 13, got %s" % st["current_phase"]
        # Phase 13 写盘门：先写盘再过门
        w(workdir3, os.path.join(out, "TestCases_%s.md" % REQ_ID),
          TC_MD.format(req=REQ_ID, header=HEADER, sep=SEP))
        g13 = run(workdir3, "gate", expect_rc=0)
        assert "GATE RESULT: PASS" in g13.stdout, "P13 gate not passed:\n" + g13.stdout
        run(workdir3, "next", expect_rc=0)      # 进入 Phase 14
        st = state_of(workdir3)
        check("已进入 Phase 14", st["current_phase"] == 14,
              "phase=%s completed=%s" % (st["current_phase"], st["completed"]))
        r = run(workdir3, "gate", expect_rc=0)
        check("连跑模式审核门自动放行", "GATE RESULT: PASS" in r.stdout and "待人工审核" in r.stdout,
              r.stdout[-300:])
        st = state_of(workdir3)
        check("放行后可推进（审计痕迹见 history auto_release）", st["status"] == "GATE_PASSED",
              "status=%s phase=%s" % (st["status"], st["current_phase"]))
        # 知识沉淀后置动作（连跑模式同样强制）
        w(workdir3, os.path.join(out, "Knowledge_%s.md" % REQ_ID), KNOWLEDGE_MD)
        run(workdir3, "set", "--knowledge", "done", expect_rc=0)
        run(workdir3, "next", expect_rc=0)
        st = state_of(workdir3)
        check("自动放行后进入 Phase 15", st["current_phase"] == 15,
              "phase=%s completed=%s" % (st["current_phase"], st["completed"]))
    finally:
        shutil.rmtree(workdir3, ignore_errors=True)

    print("\n[14] 深度裁剪（light 裁 3/4/10）")
    workdir4 = tempfile.mkdtemp(prefix="qamaster-rt-test4-")
    try:
        run(workdir4, "start", "--req-id", REQ_ID, "--mode", "light", expect_rc=0)
        run(workdir4, "set", "--depth", "light", expect_rc=0)
        r = run(workdir4, "plan", expect_rc=0)
        check("plan 不含 Phase 3/4/10", "Phase 3 " not in r.stdout and "Phase 10 " not in r.stdout
              and "Phase 4 " not in r.stdout, r.stdout)
        st = state_of(workdir4)
        check("skipped_phases=[3,4,10]", st["skipped_phases"] == [3, 4, 10])
        # light 模式澄清门语义（仅 P0 阻断）：人工门默认 WAIT，confirm 后放行
        w(workdir4, os.path.join(out, "REQ_%s.md" % REQ_ID), REQ_DOC)
        w(workdir4, os.path.join(out, "MANIFEST.md"), MANIFEST_MD.format(req=REQ_ID))
        run(workdir4, "gate", expect_rc=0)
        run(workdir4, "next", expect_rc=0)          # Phase 1（light 裁不掉澄清）
        st = state_of(workdir4)
        check("light 模式 Phase 1 仍为人工确认门", P_gate_of(st) == "confirm")
        r = run(workdir4, "gate", expect_rc=0)
        check("light 澄清门未答复时 WAIT", "GATE RESULT: WAIT" in r.stdout)
        run(workdir4, "confirm", expect_rc=0)       # 无 P0 缺口，用户确认
        st = state_of(workdir4)
        check("light 澄清门 confirm 后放行", st["status"] == "GATE_PASSED")
    finally:
        shutil.rmtree(workdir4, ignore_errors=True)

    print("\n[15] Excel 许可门：连跑模式用户已声明要 Excel → 自动放行")
    workdir5 = tempfile.mkdtemp(prefix="qamaster-rt-test5-")
    try:
        run(workdir5, "start", "--req-id", REQ_ID, "--mode", "auto", expect_rc=0)
        w(workdir5, os.path.join(out, "REQ_%s.md" % REQ_ID), REQ_DOC)
        w(workdir5, os.path.join(out, "MANIFEST.md"), MANIFEST_MD.format(req=REQ_ID))
        run(workdir5, "set", "--excel", "asked_yes", expect_rc=0)   # 用户已声明要 Excel
        run(workdir5, "gate", expect_rc=0)
        run(workdir5, "next", expect_rc=0)
        run(workdir5, "confirm", expect_rc=0)
        run(workdir5, "next", expect_rc=0)
        for pid in [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]:
            run(workdir5, "gate", expect_rc=0)
            run(workdir5, "next", expect_rc=0)
        w(workdir5, os.path.join(out, "TestCases_%s.md" % REQ_ID),
          TC_MD.format(req=REQ_ID, header=HEADER, sep=SEP))
        run(workdir5, "gate", expect_rc=0)
        run(workdir5, "next", expect_rc=0)          # Phase 14
        run(workdir5, "gate", expect_rc=0)          # 连跑自动放行审核门
        w(workdir5, os.path.join(out, "Knowledge_%s.md" % REQ_ID), KNOWLEDGE_MD)
        run(workdir5, "set", "--knowledge", "done", expect_rc=0)
        run(workdir5, "next", expect_rc=0)          # Phase 15
        st = state_of(workdir5)
        check("进入 Phase 15", st["current_phase"] == 15)
        if openpyxl_available():
            r = run(workdir5, "gate", expect_rc=0)  # 已声明要 Excel → 自动放行并生成
            check("已声明 Excel 时许可门自动放行（直接生成）", "GATE RESULT: PASS" in r.stdout)
            st = state_of(workdir5)
            check("自动放行后流程 DONE", st["status"] == "DONE",
                  "status=%s" % st["status"])
        else:
            print("  [SKIP] openpyxl 不可用，跳过自动放行生成路径")
    finally:
        shutil.rmtree(workdir5, ignore_errors=True)

    print("\n[16] 降级产物对账（v0.6.0）：TestCases 先于 Phase 13 落盘 → start 打印补验警告")
    workdir6 = tempfile.mkdtemp(prefix="qamaster-rt-test6-")
    try:
        # 情形 a：state 不存在但 TestCases 已落盘 → 首次 start 即应告警
        w(workdir6, os.path.join(out, "TestCases_%s.md" % REQ_ID),
          TC_MD.format(req=REQ_ID, header=HEADER, sep=SEP))
        r = run(workdir6, "start", "--req-id", REQ_ID, expect_rc=0)
        check("无 state + 有 TestCases → 降级对账警告", "降级产物对账警告" in r.stdout,
              r.stdout[:400])
        check("警告含补验指令", "verify_cases.py" in r.stdout and "REQ_" in r.stdout)
        # 情形 b：state 在 Phase 1，TestCases 已落盘 → 续跑 start 应告警
        w(workdir6, os.path.join(out, "REQ_%s.md" % REQ_ID), REQ_DOC)
        w(workdir6, os.path.join(out, "MANIFEST.md"), MANIFEST_MD.format(req=REQ_ID))
        run(workdir6, "gate", expect_rc=0)
        run(workdir6, "next", expect_rc=0)   # Phase 1
        r = run(workdir6, "start", expect_rc=0)
        check("Phase<13 + 有 TestCases → 续跑告警", "降级产物对账警告" in r.stdout)
        # 情形 c：Phase>=13（用例正当落盘后）→ 不再告警
        # （Phase 13 gate 会真实跑 verify_md/verify_cases 校验已落盘的合规 TC_MD；
        #   落盘发生在 gate 之前，故 gate 重跑后应 PASS 并推进到 Phase 14）
        w(workdir6, os.path.join(out, "Clarification_Ledger_%s.md" % REQ_ID), LEDGER_MD.format(req=REQ_ID))
        run(workdir6, "confirm", expect_rc=0)
        run(workdir6, "next", expect_rc=0)
        for pid in [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]:
            run(workdir6, "gate", expect_rc=0)
            run(workdir6, "next", expect_rc=0)
        st = state_of(workdir6)
        assert st["current_phase"] == 13, "expect phase 13, got %s" % st["current_phase"]
        # Phase 13 写盘门：对已落盘的合规 TC_MD 跑 verify_md/verify_cases → 应 PASS（硬门不误伤）
        r = run(workdir6, "gate", expect_rc=0)
        assert "GATE RESULT: PASS" in r.stdout, "P13 gate not passed:\n" + r.stdout[-1500:]
        run(workdir6, "next", expect_rc=0)   # Phase 14
        st = state_of(workdir6)
        assert st["current_phase"] == 14, "expect phase 14, got %s" % st["current_phase"]
        r = run(workdir6, "start", expect_rc=0)
        check("Phase>=13 正当落盘 → 无降级告警", "降级产物对账警告" not in r.stdout)
    finally:
        shutil.rmtree(workdir6, ignore_errors=True)

    print("\n[17] 覆盖硬门（v0.6.0）：#4-H / #6-H / RK 违约 → verify_cases exit=1 → Phase 13 gate FAIL")
    workdir7 = tempfile.mkdtemp(prefix="qamaster-rt-test7-")
    try:
        run(workdir7, "start", "--req-id", REQ_ID, expect_rc=0)
        # REQ 有 2 个二级标题条目；构造只引用其中 1 条、P0 风险 R1 无引用的用例集
        w(workdir7, os.path.join(out, "REQ_%s.md" % REQ_ID), REQ_DOC)
        w(workdir7, os.path.join(out, "MANIFEST.md"), MANIFEST_MD.format(req=REQ_ID))
        run(workdir7, "gate", expect_rc=0)
        run(workdir7, "next", expect_rc=0)
        w(workdir7, os.path.join(out, "Clarification_Ledger_%s.md" % REQ_ID), LEDGER_MD.format(req=REQ_ID))
        run(workdir7, "confirm", expect_rc=0)
        run(workdir7, "next", expect_rc=0)
        for pid in [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]:
            run(workdir7, "gate", expect_rc=0)
            run(workdir7, "next", expect_rc=0)
        st = state_of(workdir7)
        assert st["current_phase"] == 13, "expect phase 13, got %s" % st["current_phase"]
        # 坏用例集：关联需求ID 填"见需求文档"（笼统占位 → 2 条 REQ 均未覆盖 → #4-H FAIL）；
        # 关联规则不含 R1，且风险描述 token（资金/反向/操作/漏洞）刻意不与用例文本重叠
        # （避免 risk_coverage 的 token 兜底误判为"已覆盖"），使 RK P0/P1 硬门真正触发。
        BAD_TC = """# 测试用例 - {req}

## 规则建模

- **订单创建主流程** [来源:需求文档订单创建]

## 风险清单

| 风险ID | 风险等级 | 风险描述 | 关联模块 | 风险来源 |
| -- | -- | -- | -- | -- |
| R1 | P0 | 资金反向操作漏洞（负数金额绕过校验） | 支付 | 需求推导 |

## 测试点清单

| 测试点ID | 场景类型 | 测试点描述 | 关联模块 |
| -- | -- | -- | -- |
| TP1 | 正常 | 创建订单扣库存 | 订单 |

{header}
{sep}
| {req}_CREATE_001 | 见需求文档 | TP1:创建订单 | 功能 | 接口验证 | 订单 | 【订单模块】【创建订单】【库存充足】【创建成功】 | 用户已登录；购物车有商品 | 提交订单 | 接口返回200且status=SUCCESS；订单状态为待支付；库存数量减少 | STEP | AI | AI | P1 | Completed |
"""
        w(workdir7, os.path.join(out, "TestCases_%s.md" % REQ_ID),
          BAD_TC.format(req=REQ_ID, header=HEADER, sep=SEP))
        r = run(workdir7, "gate", expect_rc=0)
        check("覆盖硬门违约 → Phase 13 gate FAIL", "GATE RESULT: FAIL" in r.stdout,
              r.stdout[-1500:])
        check("FAIL 含 #4-H 需求追溯硬门", "#4-H" in r.stdout, r.stdout[-1500:])
        check("FAIL 含 RK P0/P1 风险硬门", "RK" in r.stdout and "风险硬门" in r.stdout)
        check("FAIL 文案含防逃逸声明", "禁止以任何理由绕过本门禁交付" in r.stdout)
        st = state_of(workdir7)
        check("硬门 FAIL 后停留 Phase 13", st["current_phase"] == 13 and st["status"] == "RUNNING")
        # 修复为合规用例集 → gate PASS（证明硬门不误伤全覆盖用例集）
        w(workdir7, os.path.join(out, "TestCases_%s.md" % REQ_ID),
          TC_MD.format(req=REQ_ID, header=HEADER, sep=SEP))
        r = run(workdir7, "gate", expect_rc=0)
        check("补齐后 gate PASS（硬门不误伤）", "GATE RESULT: PASS" in r.stdout, r.stdout[-1200:])
        check("回读输出含 ##VERIFY_SUMMARY## 机器摘要块", "##VERIFY_SUMMARY##" in r.stdout)
    finally:
        shutil.rmtree(workdir7, ignore_errors=True)


def P_gate_of(st):
    return _RT_PHASES.get_phase(st["current_phase"])["gate"]


if __name__ == "__main__":
    sys.exit(main())
