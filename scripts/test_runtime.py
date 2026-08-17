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
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RT = os.path.join(ROOT, "runtime", "qamaster_runtime.py")
SKILL_SCRIPTS = os.path.join(ROOT, "skills", "case-design", "scripts")
sys.path.insert(0, os.path.join(ROOT, "runtime"))
sys.path.insert(0, SKILL_SCRIPTS)  # 供直接 import verify_cases 做探针单测（P3-1/P1-1）
import phases as _RT_PHASES  # noqa: E402
import manifest as _MANIFEST  # noqa: E402
import state_store as _STATE  # noqa: E402

REQ_ID = "自证需求-20260802"
WORKFLOW = "case-design"
QAMASTER_PART = os.path.join(".qamaster", WORKFLOW)  # 分区根（相对 workdir）

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

- **R1 订单创建主流程** [来源:需求文档订单创建]
- **R2 库存扣减时机** [来源:需求文档库存扣减]

## 风险清单

| 风险ID | 风险等级 | 风险描述 | 关联模块 | 风险来源 |
| -- | -- | -- | -- | -- |
| RK1 | P0 | 库存超卖（并发扣减） | 订单 | 需求推导 |

## 测试点清单

| 测试点ID | 场景类型 | 测试点描述 | 关联模块 |
| -- | -- | -- | -- |
| TP1 | 正常 | 创建订单扣库存 | 订单 |

{header}
{sep}
| {req}_CREATE_001 | 见需求文档订单创建 | R1:订单创建、TP1:创建订单 | 功能 | 接口验证 | 订单 | 【订单模块】【创建订单】【库存充足】【创建成功】 | 用户已登录；购物车有商品A001数量2；库存充足 | 1.进入购物车点击提交订单；2.确认金额 | 接口返回200且status=SUCCESS；订单主存储中订单状态为待支付；库存数量减少2；发送订单创建消息事件 | STEP | AI | AI | P0 | Completed |
| {req}_CREATE_002 | 见需求文档订单创建 | R1:数量边界、TP1:数量边界 | 边界 | 边界验证 | 订单 | 【订单模块】【创建订单】【数量边界1与99】【创建成功】 | 用户已登录；购物车有商品A001 | 1.数量设为1提交；2.数量设为99提交 | 接口返回200且status=SUCCESS；订单创建成功；库存数量减少对应值 | STEP | AI | AI | P1 | Completed |
| {req}_CREATE_003 | 见需求文档订单创建 | R1:数量非法、TP1:数量非法 | 异常 | 输入验证 | 订单 | 【订单模块】【创建订单】【数量0与100非法】【返回参数非法错误】 | 用户已登录 | 1.数量设为0提交；2.数量设为100提交 | 接口返回400且错误码=PARAM_INVALID；订单未创建；库存未扣减 | STEP | AI | AI | P2 | Completed |
| {req}_CREATE_004 | 见需求文档订单创建 | R1:重复提交幂等 | 幂等 | 幂等验证 | 订单 | 【订单模块】【创建订单】【并发重复提交】【仅创建一个订单】 | 用户已登录；购物车有商品A001 | 1.同一请求连续提交两次 | 仅创建1个订单；库存仅扣减一次；无重复消息事件 | STEP | AI | AI | P1 | Completed |
| {req}_STOCK_001 | 见需求文档库存扣减 | R2:扣减时机 | 功能 | 数据验证 | 库存 | 【库存模块】【库存扣减】【下单即扣】【扣减成功】 | 用户已登录；商品A001库存充足 | 提交订单 | 接口返回200且status=SUCCESS；库存数量减少对应值；记录库存变更日志 | STEP | AI | AI | P1 | Completed |
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


def _inject_args(args, req_id):
    """run/run_debug 公共：自动注入 --workflow case-design；命令非 bootstrap 且未显式带 --req-id 时注入 req_id。

    bootstrap 派生 id，不能强塞 --req-id；start/status/manifest 等显式带 --req-id 的调用方不重复注入。
    """
    args = list(args)
    if "--workflow" not in args:
        args += ["--workflow", WORKFLOW]
    cmd = args[0] if args else ""
    if cmd != "bootstrap" and req_id and "--req-id" not in args:
        args += ["--req-id", req_id]
    return args


def run(workdir, *args, expect_rc=None, req_id=REQ_ID):
    full = _inject_args(args, req_id)
    proc = subprocess.run([sys.executable, RT] + full + ["--workdir", workdir],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if expect_rc is not None:
        assert proc.returncode == expect_rc, "rc=%d expected %d\ncmd=%s\nstdout=%s\nstderr=%s" % (
            proc.returncode, expect_rc, args, proc.stdout, proc.stderr)
    return proc


def run_debug(workdir, *args, req_id=REQ_ID):
    full = _inject_args(args, req_id)
    proc = subprocess.run([sys.executable, RT] + full + ["--workdir", workdir],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("    cmd=%s rc=%d | %s" % (" ".join(args), proc.returncode,
                                   (proc.stdout or proc.stderr).strip().splitlines()[0][:100] if (proc.stdout or proc.stderr).strip() else ""))
    return proc


def state_of(workdir, req_id=REQ_ID):
    """读分区状态：<workdir>/.qamaster/case-design/<req_id>/state.json"""
    p = os.path.join(workdir, QAMASTER_PART, req_id, "state.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def manifest_path(workdir):
    return os.path.join(workdir, "case-design-out", "MANIFEST.md")


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


def cp_dir(workdir, req_id=REQ_ID):
    """检查点分区目录：<workdir>/.qamaster/case-design/<req_id>/"""
    d = os.path.join(workdir, QAMASTER_PART, req_id)
    os.makedirs(d, exist_ok=True)
    return d


def write_checkpoints(workdir, req_id=REQ_ID):
    """v0.7.0: Phase 3/5/7/8/10 现有 phase_gate 检查，需检查点占位文件。
    Phase 8/10 用 TC_MD 内容（含用例表，使引用解析/覆盖校验有内容）。
    分区路径：<workdir>/.qamaster/case-design/<req_id>/checkpoint_<N>.md"""
    d = cp_dir(workdir, req_id)
    secs = {
        3: "## 规则建模\n\n- **R1 订单创建主流程** [来源:需求文档]\n- **R2 库存扣减时机** [来源:需求文档]\n",
        5: "## 风险清单\n\n| 风险ID | 风险等级 | 风险描述 | 关联模块 | 风险来源 |\n| -- | -- | -- | -- | -- |\n| RK1 | P0 | x | m | 需求推导 |\n",
        7: "## 测试点清单\n\n| 测试点ID | 场景类型 | 测试点描述 | 关联模块 |\n| -- | -- | -- | -- |\n| TP1 | 正常 | x | m |\n",
        8: TC_MD.format(req=req_id, header=HEADER, sep=SEP),
        10: TC_MD.format(req=req_id, header=HEADER, sep=SEP),
    }
    for pid, content in secs.items():
        with open(os.path.join(d, "checkpoint_%d.md" % pid), "w", encoding="utf-8") as f:
            f.write(content)


def advance_to_phase13(workdir, req_id=REQ_ID):
    """从 Phase 2（已 confirm 进入）推进到 Phase 13（写盘前）。
    v0.7.0: Phase 3/5/7/8/10 有 phase_gate，需先写检查点。"""
    run(workdir, "gate", expect_rc=0, req_id=req_id)  # Phase 2
    write_checkpoints(workdir, req_id)
    for pid in [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]:
        run(workdir, "next", expect_rc=0, req_id=req_id)
        run(workdir, "gate", expect_rc=0, req_id=req_id)
    run(workdir, "next", expect_rc=0, req_id=req_id)  # → Phase 13


def test_probe_p3_p1():
    """P3-1（规则来源假标注核对）+ P1-1（澄清完整性探针）+ P2-1（组合/判定表覆盖探针）软探针单测。

    直接调用 verify_cases 的探针函数，正/反/降级三路覆盖，确认：
      - 软探针不新增硬违规（不改硬门行为）；
      - 假标注/漏问/组合漏测命中，真实标注/已澄清/已覆盖不误报；
      - 无 REQ / 无台账 / 无用例等边界降级跳过（不误伤）。
    """
    print("\n[new] P3-1 规则来源假标注 + P1-1 澄清完整性 + P2-1 组合覆盖（软探针·直接函数单测）")
    import verify_cases as vc

    # ---- P3-1：check_rule_source ----
    REQ_2CH = ["# 需求", "## 订单创建", "用户下单，库存扣减。",
               "## 订单退款", "用户申请退款，资金原路返回。"]
    # 正例：声称章节不存在 → 假标注命中（软）
    n, sus, fake = vc.check_rule_source(
        ["## 规则建模", "- **订单规则** [来源:需求文档<瞎编章节>]", "| 用例ID | x |"],
        req_doc_lines=REQ_2CH)
    check("P3-1 假标注命中", len(fake) == 1 and len(sus) == 0, "fake=%d sus=%d" % (len(fake), len(sus)))
    check("P3-1 假标注文案含失实提示", fake and "来源标注疑似失实" in fake[0])
    # 反例：声称章节真实存在 → 不误报
    n, sus, fake = vc.check_rule_source(
        ["## 规则建模", "- **订单规则** [来源:需求文档<订单创建>]", "| 用例ID | x |"],
        req_doc_lines=REQ_2CH)
    check("P3-1 真实章节不误报", len(fake) == 0 and len(sus) == 0, "fake=%d" % len(fake))
    # 降级：无 REQ → 假标注核对跳过
    n, sus, fake = vc.check_rule_source(
        ["## 规则建模", "- **订单规则** [来源:需求文档<瞎编章节>]", "| 用例ID | x |"],
        req_doc_lines=None)
    check("P3-1 无REQ降级跳过", len(fake) == 0, "fake=%d" % len(fake))
    # 行为不变：无来源标记 → 仍进 suspects（rule_source_hard 硬门路径），假标注空
    n, sus, fake = vc.check_rule_source(
        ["## 规则建模", "- **订单规则** 无来源描述", "| 用例ID | x |"],
        req_doc_lines=REQ_2CH)
    check("P3-1 无来源标记仍进硬门 suspects", len(sus) == 1 and len(fake) == 0,
          "sus=%d fake=%d" % (len(sus), len(fake)))

    # ---- P1-1：check_clarification_completeness ----
    REQ_SM = ["# 需求", "## 订单", "订单状态流转涉及多步迁移，状态变更为终态。"]
    LED_NO_SM = {"facts": ["金额字段必填"], "question_text": ["金额格式是什么"],
                 "open": [], "resolved": ["Q1"], "assumptions": []}
    LED_SM = {"facts": ["订单流转为已支付"], "question_text": [],
              "open": [], "resolved": ["Q1"], "assumptions": []}
    # 正例：REQ 含状态机信号但台账无 → 漏问命中
    gn, gl = vc.check_clarification_completeness(REQ_SM, LED_NO_SM)
    check("P1-1 漏问命中", gn == 1, "gaps=%d %s" % (gn, gl))
    check("P1-1 漏问文案含状态机类", gl and "状态机流转" in gl[0])
    # 反例：台账已含状态机 token → 不误报
    gn, gl = vc.check_clarification_completeness(REQ_SM, LED_SM)
    check("P1-1 台账已澄清不误报", gn == 0, "gaps=%d" % gn)
    # 降级：无台账 → 跳过
    gn, gl = vc.check_clarification_completeness(REQ_SM, None)
    check("P1-1 无台账降级跳过", gn == 0, "gaps=%d" % gn)
    # 降级：无 REQ → 跳过
    gn, gl = vc.check_clarification_completeness([], LED_NO_SM)
    check("P1-1 无REQ降级跳过", gn == 0, "gaps=%d" % gn)
    # R2 评审 MED 修复验证：裸权限概念词（权限/鉴权/授权）须能命中"权限与敏感数据"类
    REQ_PERM = ["# 需求", "## 功能", "本功能涉及权限校验与鉴权逻辑，需登录态。"]
    gn, gl = vc.check_clarification_completeness(REQ_PERM, LED_NO_SM)
    check("P1-1 裸权限词命中权限类(R2 MED修复)", gn >= 1 and any("权限" in g for g in gl),
          "gaps=%d %s" % (gn, gl))
    gn, gl = vc.check_clarification_completeness(REQ_PERM, {"facts": ["权限校验仅管理员可操作"],
                                                             "question_text": [], "open": [],
                                                             "resolved": [], "assumptions": []})
    check("P1-1 台账已澄清权限不误报", gn == 0, "gaps=%d" % gn)

    # parse_clarification_ledger 收集 question_text（与 facts 分离，不污染 check_ledger_propagation）
    ledger_md = ("# 澄清台账 Clarification_Ledger - X\n\n## 问题清单\n\n"
                 "| 问题ID | 类型 | 原问题 | 用户答复 | 状态 | 建议回答角色 | 登记轮次 |\n"
                 "| -- | -- | -- | -- | -- | -- | -- |\n"
                 "| Q1 | 状态规则 | 订单状态流转规则？ | 待支付流转为已支付 | 已解决 | @开发 | 创建 |\n\n"
                 "## 权威事实\n- 金额字段必填\n")
    fd, lpath = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    try:
        with open(lpath, "w", encoding="utf-8") as f:
            f.write(ledger_md)
        led = vc.parse_clarification_ledger(lpath)
        check("台账解析收集 question_text", led.get("question_text") == ["订单状态流转规则？"],
              "question_text=%s" % led.get("question_text"))
        # facts 含解答 + 权威事实，但不含问题原文（避免污染 token 提取）
        check("台账 facts 不含问题原文", all("状态流转规则" not in x for x in led.get("facts", [])),
              "facts=%s" % led.get("facts"))
    finally:
        os.remove(lpath)

    # VERIFY_SUMMARY 契约含两个新软字段
    sm = vc.verify_summary_line({"soft": {"completeness": [0], "schema": [None], "behavior": [0]},
                                 "traces": {"requirement": [[], 0], "interface": [[], 0, 0],
                                            "risk": [[], 0, 0], "testpoint": [[], 0],
                                            "design_doc": [[], 0]},
                                 "risk_source": [{}, []], "hard_violations": []})
    check("VERIFY_SUMMARY 含 rule_source_fake 字段", "rule_source_fake=0" in sm, sm)
    check("VERIFY_SUMMARY 含 clarification_gaps 字段", "clarification_gaps=0" in sm, sm)
    check("VERIFY_SUMMARY 含 combination_gaps 字段", "combination_gaps=0" in sm, sm)

    # ---- P2-1：check_combination_coverage（组合/判定表覆盖探针）----
    def _row(ctype="功能", cdim="正常", name="用例", given="G", when="W"):
        return ["ID1", "REQ", "R1", ctype, cdim, "模块", name, given, when, "T",
                "STEP", "AI", "AI", "P1", "Completed"]
    REQ_COMBO = ["# 需求", "## 优惠", "满100减20，叠加优惠券，优惠互斥时取最大。"]
    REQ_PLAIN = ["# 需求", "## 订单", "创建订单扣库存"]
    # 正例：REQ 含组合信号但无用例覆盖组合维度 → 命中
    cn, cl = vc.check_combination_coverage(REQ_COMBO, ["# 测试用例"], [_row()])
    check("P2-1 组合漏测命中", cn == 1, "combo=%d %s" % (cn, cl))
    check("P2-1 命中文案含 bug 高发区", cl and "组合" in cl[0] and "bug 高发区" in cl[0])
    # 反例：有用例 测试类型=判定表 → 不误报
    cn, cl = vc.check_combination_coverage(REQ_COMBO, ["# 测试用例"], [_row(ctype="判定表", cdim="组合")])
    check("P2-1 判定表用例已覆盖不误报", cn == 0, "combo=%d" % cn)
    # 反例：用例文本含 正交 → 不误报
    cn, cl = vc.check_combination_coverage(REQ_COMBO, ["# 测试用例"], [_row(name="正交实验覆盖组合分支")])
    check("P2-1 用例文本含正交不误报", cn == 0, "combo=%d" % cn)
    # 无信号：REQ 不含组合词 → 跳过
    cn, cl = vc.check_combination_coverage(REQ_PLAIN, ["# 测试用例"], [_row()])
    check("P2-1 无组合信号跳过", cn == 0, "combo=%d" % cn)
    # 降级：无用例 → 跳过
    cn, cl = vc.check_combination_coverage(REQ_COMBO, ["# 测试用例"], [])
    check("P2-1 无用例降级跳过", cn == 0, "combo=%d" % cn)
    # lines 侧规则 section 含组合（即使无 REQ）→ 命中
    lines_rule = ["# TC", "## 规则建模", "- **优惠规则** 多条件组合判定", "| 用例ID | x |"]
    cn, cl = vc.check_combination_coverage(None, lines_rule, [_row()])
    check("P2-1 规则section组合信号命中", cn == 1, "combo=%d" % cn)

    # ---- P9-1：check_duplicates 边界点/场景变体保护 ----
    def _drow(given="G", when="W"):
        # 规则/断言/维度/类型/等级 固定全同，仅 Given/When 可变
        return ["ID", "REQ", "R1", "边界", "金额校验", "模块", "名", given, when,
                "断言模板", "STEP", "AI", "AI", "P1", "Done"]
    # 危险近重复：五者全同但 Given 不同（金额=0 vs 金额=最大值）→ 升级告警
    dn, dl = vc.check_duplicates([_drow(given="金额=0"), _drow(given="金额=最大值")])
    check("P9-1 边界点近重复命中", dn == 1 and "边界点" in dl[0], "dups=%d %s" % (dn, dl))
    # When 不同同样触发
    dn, dl = vc.check_duplicates([_drow(when="点单"), _drow(when="改单")])
    check("P9-1 When不同近重复命中", dn == 1 and "边界点" in dl[0], "dups=%d %s" % (dn, dl))
    # 真重复：Given/When 完全相同 → 普通疑似重复告警（不含边界点字样）
    dn, dl = vc.check_duplicates([_drow(given="X", when="Y"), _drow(given="X", when="Y")])
    check("P9-1 真重复普通告警", dn == 1 and "边界点" not in dl[0] and "疑似重复" in dl[0],
          "dups=%d %s" % (dn, dl))
    # 不同规则/断言 → 不报重复（key 不同）
    dn, dl = vc.check_duplicates([_drow(), ["ID", "REQ", "R2", "边界", "金额校验",
                                            "模块", "名", "G", "W", "断言模板", "STEP",
                                            "AI", "AI", "P1", "Done"]])
    check("P9-1 不同规则不误报", dn == 0, "dups=%d" % dn)


def main():
    print("== qamaster Runtime 自证测试 ==")
    workdir = tempfile.mkdtemp(prefix="qamaster-rt-test-")
    try:
        _run_suite(workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    # 并行/迁移/索引自证（各自独立 workdir）
    test_concurrent_reqs()
    test_manifest_concurrent_update()
    test_phase0_manifest_created_on_pass()
    test_legacy_migration()
    test_bootstrap_idempotent()
    test_manifest_reconcile()
    test_probe_p3_p1()

    # KB 经验库自证（自我进化·机制与模型无关·13 项）
    test_kb_noop_preserves_baseline()
    test_kb_autocapture_silent_draft_not_injected()
    test_kb_surface_map_via_subprocess()
    test_kb_dim_trigger_union()
    test_kb_fingerprint_coarse_recurrence()
    test_kb_preventive_dual_gate()
    test_kb_reactive_failure_targeted()
    test_kb_reactive_respects_trust_gate()
    test_kb_endorse_and_supersede()
    test_kb_threshold_recurrence_injected()
    test_kb_concurrent_add()
    test_kb_distill_replays_history()
    test_kb_capture_never_blocks_correction()

    # KB 业务历史知识库（MVP2b·机制与模型无关·7 项）
    test_kb_business_noop()
    test_kb_business_reconcile_indexes()
    test_kb_business_preventive_injects_at_phase0()
    test_kb_business_reactive_injects_on_fail()
    test_kb_business_relevance_gate_filters()
    test_kb_business_verify_id_patterns()
    test_kb_business_separate_from_lessons()
    test_kb_query_top_preview()

    # KB 专家方法论库（v0.11.7·机制与模型无关·10 项·护 150/0 endorsed-only）
    test_expert_noop_preserves_baseline()
    test_expert_draft_blocked_trust_gate()
    test_expert_endorsed_injected()
    test_methodology_capture_lists_pending_draft()
    test_add_expert_trigger_tokenization()
    test_verify_kb_softwarn_pipe_trigger()
    test_kb_pending_endorse_summary()
    # v0.11.6（RC-d 终极修复）回归：读取时分词自愈 + add-expert 自动补 REQ 域词
    test_expert_legacy_malformed_trigger_selfheal()
    test_add_expert_auto_req_signals()
    # v0.11.7（RC-e）回归：子串遮蔽去重（数字阈值不误注入）
    test_expert_substring_shadow_no_overmatch()
    # v0.11.8（RC-f）回归：台账引入 AND 门（REQ 散文无信号）→ 编号条件归一注入
    test_expert_ledger_numbered_cond_injection()
    # v0.11.9（RC-g）回归：补齐专家库反应式失败定向（失败文本命中→RELEVANT_EXPERT_KB）
    test_expert_reactive_on_fail()

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
    # MANIFEST 不预写：Runtime 在 Phase 0 gate PASS 时经 manifest add 自动创建（见 [new] test_phase0_manifest_created_on_pass）
    r = run(workdir, "gate", expect_rc=0)
    check("补齐产物后 gate PASS", "GATE RESULT: PASS" in r.stdout)
    check("Phase 0 gate PASS 后 Runtime 自动创建 MANIFEST", os.path.isfile(manifest_path(workdir)))
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
    # v0.7.0: Phase 3/5/7/8/10 现在有 phase_gate 检查（需检查点文件）；
    # test_runtime 验证状态机迁移而非真实内容校验，故用 run_debug（不 assert rc）跑 gate
    # 并在需要的阶段补检查点占位文件，使 phase_gate PASS。
    checkpoints = {3: "## 规则建模\n\n- **R1 订单创建主流程** [来源:需求文档]\n- **R2 库存扣减时机** [来源:需求文档]\n",
                   5: "## 风险清单\n\n| 风险ID | 风险等级 | 风险描述 | 关联模块 | 风险来源 |\n| -- | -- | -- | -- | -- |\n| RK1 | P0 | x | m | 需求推导 |\n",
                   7: "## 测试点清单\n\n| 测试点ID | 场景类型 | 测试点描述 | 关联模块 |\n| -- | -- | -- | -- |\n| TP1 | 正常 | x | m |\n",
                   8: TC_MD.format(req=REQ_ID, header=HEADER, sep=SEP),
                   10: TC_MD.format(req=REQ_ID, header=HEADER, sep=SEP)}  # Phase 10 用含用例表的检查点（带 REQ 引用），使覆盖硬门 PASS
    expect_seq = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    for pid in expect_seq:
        r = run(workdir, "next", expect_rc=0)
        st = state_of(workdir)
        check("推进到 Phase %d" % pid, st["current_phase"] == pid)
        # v0.7.0: 有 phase_gate 的阶段补检查点占位，使 gate PASS
        if pid in checkpoints:
            d = cp_dir(workdir)
            with open(os.path.join(d, "checkpoint_%d.md" % pid), "w", encoding="utf-8") as f:
                f.write(checkpoints[pid])
        r = run(workdir, "gate", expect_rc=0)
        check("Phase %d gate PASS" % pid, "GATE RESULT: PASS" in r.stdout, r.stdout[-400:])
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
    # v0.7.0: 重走时 Phase 8/10 需补检查点占位（已在 [5] 写过 3/5/7；8 用 TestCases 内容、10 用覆盖率占位）
    # [5] 已写 checkpoint_3/5/7/10；重走 8/10 时仍存在，phase_gate 应 PASS
    # 但 [5] 的 checkpoint_8 未写（8 阶段当时靠空 gate_checks）。重走需补 8 检查点。
    d = cp_dir(workdir)
    with open(os.path.join(d, "checkpoint_8.md"), "w", encoding="utf-8") as f:
        f.write(TC_MD.format(req=REQ_ID, header=HEADER, sep=SEP))
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
        # MANIFEST 不预写：Runtime 自动创建（铁律 4）
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
        # MANIFEST 不预写：Runtime 自动创建
        run(workdir3, "gate", expect_rc=0)
        run(workdir3, "next", expect_rc=0)
        run(workdir3, "confirm", expect_rc=0)   # 澄清门确认 → Phase 1 GATE_PASSED
        run(workdir3, "next", expect_rc=0)      # 进入 Phase 2
        run(workdir3, "gate", expect_rc=0)      # Phase 2 自动门 PASS（无机器检查）
        # v0.7.0: Phase 3/5/7/8/10 需补检查点占位（与 [5] 同）
        cp3 = {3: "## 规则建模\n\n- **R1 订单创建主流程** [来源:需求文档]\n- **R2 库存扣减时机** [来源:需求文档]\n",
               5: "## 风险清单\n\n| 风险ID | 风险等级 | 风险描述 | 关联模块 | 风险来源 |\n| -- | -- | -- | -- | -- |\n| RK1 | P0 | x | m | 需求推导 |\n",
               7: "## 测试点清单\n\n| 测试点ID | 场景类型 | 测试点描述 | 关联模块 |\n| -- | -- | -- | -- |\n| TP1 | 正常 | x | m |\n",
               8: TC_MD.format(req=REQ_ID, header=HEADER, sep=SEP),
               10: TC_MD.format(req=REQ_ID, header=HEADER, sep=SEP)}
        cp_dir3 = cp_dir(workdir3)
        for pid, content in cp3.items():
            with open(os.path.join(cp_dir3, "checkpoint_%d.md" % pid), "w", encoding="utf-8") as f:
                f.write(content)
        # Phase 2 已过 gate；3-12 next+gate（与 [5] 同：先 next 后 gate）
        for pid in [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]:
            run(workdir3, "next", expect_rc=0)
            run(workdir3, "gate", expect_rc=0)
        run(workdir3, "next", expect_rc=0)  # → Phase 13
        st = state_of(workdir3)
        assert st["current_phase"] == 13, "expect phase 13, got %s" % st["current_phase"]
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

    print("\n[14] 深度裁剪（light 裁 3/4）")
    workdir4 = tempfile.mkdtemp(prefix="qamaster-rt-test4-")
    try:
        run(workdir4, "start", "--req-id", REQ_ID, "--mode", "light", expect_rc=0)
        run(workdir4, "set", "--depth", "light", expect_rc=0)
        r = run(workdir4, "plan", expect_rc=0)
        check("plan 不含 Phase 3/4", "Phase 3 " not in r.stdout and "Phase 4 " not in r.stdout,
              r.stdout)
        st = state_of(workdir4)
        check("skipped_phases=[3,4]", st["skipped_phases"] == [3, 4],
              "actual=%s" % st.get("skipped_phases"))
        # light 模式澄清门语义（仅 P0 阻断）：人工门默认 WAIT，confirm 后放行
        w(workdir4, os.path.join(out, "REQ_%s.md" % REQ_ID), REQ_DOC)
        # MANIFEST 不预写：Runtime 自动创建
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
        # MANIFEST 不预写：Runtime 自动创建
        run(workdir5, "set", "--excel", "asked_yes", expect_rc=0)   # 用户已声明要 Excel
        run(workdir5, "gate", expect_rc=0)
        run(workdir5, "next", expect_rc=0)
        run(workdir5, "confirm", expect_rc=0)
        run(workdir5, "next", expect_rc=0)
        run(workdir5, "gate", expect_rc=0)          # Phase 2
        # v0.7.0: Phase 3/5/7/8/10 需补检查点占位
        cp5 = {3: "## 规则建模\n\n- **R1 订单创建主流程** [来源:需求文档]\n- **R2 库存扣减时机** [来源:需求文档]\n",
               5: "## 风险清单\n\n| 风险ID | 风险等级 | 风险描述 | 关联模块 | 风险来源 |\n| -- | -- | -- | -- | -- |\n| RK1 | P0 | x | m | 需求推导 |\n",
               7: "## 测试点清单\n\n| 测试点ID | 场景类型 | 测试点描述 | 关联模块 |\n| -- | -- | -- | -- |\n| TP1 | 正常 | x | m |\n"}
        cp_dir5 = cp_dir(workdir5)
        for pid, content in cp5.items():
            with open(os.path.join(cp_dir5, "checkpoint_%d.md" % pid), "w", encoding="utf-8") as f:
                f.write(content)
        for pid in [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]:
            if pid == 8 or pid == 10:
                with open(os.path.join(cp_dir5, "checkpoint_%d.md" % pid), "w", encoding="utf-8") as f:
                    f.write(TC_MD.format(req=REQ_ID, header=HEADER, sep=SEP))
            run(workdir5, "next", expect_rc=0)
            run(workdir5, "gate", expect_rc=0)
        run(workdir5, "next", expect_rc=0)          # → Phase 13
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
        # MANIFEST 不预写：Runtime 自动创建
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
        run(workdir6, "gate", expect_rc=0)  # Phase 2
        # v0.7.0: Phase 3/5/7/8/10 需补检查点占位
        cp6 = {3: "## 规则建模\n\n- **R1 订单创建主流程** [来源:需求文档]\n- **R2 库存扣减时机** [来源:需求文档]\n",
               5: "## 风险清单\n\n| 风险ID | 风险等级 | 风险描述 | 关联模块 | 风险来源 |\n| -- | -- | -- | -- | -- |\n| RK1 | P0 | x | m | 需求推导 |\n",
               7: "## 测试点清单\n\n| 测试点ID | 场景类型 | 测试点描述 | 关联模块 |\n| -- | -- | -- | -- |\n| TP1 | 正常 | x | m |\n"}
        cp_dir6 = cp_dir(workdir6)
        for pid, content in cp6.items():
            with open(os.path.join(cp_dir6, "checkpoint_%d.md" % pid), "w", encoding="utf-8") as f:
                f.write(content)
        for pid in [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]:
            if pid == 8 or pid == 10:
                with open(os.path.join(cp_dir6, "checkpoint_%d.md" % pid), "w", encoding="utf-8") as f:
                    f.write(TC_MD.format(req=REQ_ID, header=HEADER, sep=SEP))
            run(workdir6, "next", expect_rc=0)
            run(workdir6, "gate", expect_rc=0)
        run(workdir6, "next", expect_rc=0)  # → Phase 13
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
        # MANIFEST 不预写：Runtime 自动创建
        run(workdir7, "gate", expect_rc=0)
        run(workdir7, "next", expect_rc=0)
        w(workdir7, os.path.join(out, "Clarification_Ledger_%s.md" % REQ_ID), LEDGER_MD.format(req=REQ_ID))
        run(workdir7, "confirm", expect_rc=0)
        run(workdir7, "next", expect_rc=0)
        advance_to_phase13(workdir7)
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


# ============================================================
# 并行/迁移/索引自证（各自独立 workdir，证明多需求隔离与铁律）
# ============================================================

def test_concurrent_reqs():
    """并发核心：同 workdir 两 req 独立推进，state/检查点互不覆盖，降级对账不误报对方用例（C2）。"""
    print("\n[new] 并发核心：同 workdir 两 req 独立推进，状态互不覆盖，降级对账不误报（C2）")
    out = "case-design-out"
    workdir_cc = tempfile.mkdtemp(prefix="qamaster-rt-test-conc-")
    try:
        rA = "并发需求甲-20260808"
        rB = "并行需求乙-20260808"

        def advance_to_phase2(wd, rid):
            run(wd, "start", "--req-id", rid, req_id=rid, expect_rc=0)
            w(wd, os.path.join(out, "REQ_%s.md" % rid),
              "# %s\n\n## 订单创建\n\n内容%s\n\n## 库存扣减\n\n内容\n" % (rid, rid))
            run(wd, "gate", req_id=rid, expect_rc=0)       # Phase 0 PASS → manifest add
            run(wd, "next", req_id=rid, expect_rc=0)        # → Phase 1（人工确认门）
            w(wd, os.path.join(out, "Clarification_Ledger_%s.md" % rid), LEDGER_MD.format(req=rid))
            run(wd, "confirm", req_id=rid, expect_rc=0)     # Phase 1 confirm → GATE_PASSED
            run(wd, "next", req_id=rid, expect_rc=0)        # → Phase 2

        advance_to_phase2(workdir_cc, rA)
        st_a = state_of(workdir_cc, rA)
        check("req A 到达 Phase 2", st_a["current_phase"] == 2, "phase=%s" % st_a.get("current_phase"))
        check("req A state.req_id 独立", st_a["req_id"] == rA)
        a_created = st_a["created_at"]

        advance_to_phase2(workdir_cc, rB)
        st_b = state_of(workdir_cc, rB)
        check("req B 到达 Phase 2", st_b["current_phase"] == 2, "phase=%s" % st_b.get("current_phase"))
        check("req B state.req_id 独立", st_b["req_id"] == rB)

        # 关键断言：B 推进后 A 的状态未被覆盖（分区隔离证明）
        st_a2 = state_of(workdir_cc, rA)
        check("B 推进后 A 仍在 Phase 2（未被覆盖）", st_a2["current_phase"] == 2,
              "phase=%s" % st_a2.get("current_phase"))
        check("B 推进后 A 的 req_id 仍为 A", st_a2["req_id"] == rA)
        check("B 推进后 A 的 created_at 不变（不重建状态·C8）", st_a2["created_at"] == a_created,
              "before=%s after=%s" % (a_created, st_a2["created_at"]))

        # 检查点分区目录各自独立
        dir_a = os.path.join(workdir_cc, QAMASTER_PART, rA)
        dir_b = os.path.join(workdir_cc, QAMASTER_PART, rB)
        check("A/B 分区目录各自独立", os.path.isdir(dir_a) and os.path.isdir(dir_b))

        # C2：A、B 均有用例（均<13，降级产物）；audit B 只报 B 的、不误报 A 的
        w(workdir_cc, os.path.join(out, "TestCases_%s.md" % rA),
          TC_MD.format(req=rA, header=HEADER, sep=SEP))
        w(workdir_cc, os.path.join(out, "TestCases_%s.md" % rB),
          TC_MD.format(req=rB, header=HEADER, sep=SEP))
        rb = run(workdir_cc, "start", "--req-id", rB, req_id=rB, expect_rc=0)  # B 续跑 → 触发降级对账
        check("audit B 触发自身降级警告", "降级产物对账警告" in rb.stdout, rb.stdout[:500])
        check("audit B 不误报 A 的 TestCases（C2）",
              ("TestCases_%s" % rA) not in rb.stdout, rb.stdout[:800])
        check("audit B 仅报自身 TestCases", ("TestCases_%s" % rB) in rb.stdout, rb.stdout[:800])

        # MANIFEST 两行共存（共享索引未丢行）
        rows = _MANIFEST.load_rows(manifest_path(workdir_cc))
        ids = [row.get("req_id") for row in rows]
        check("MANIFEST 两 req 行共存", rA in ids and rB in ids, "ids=%s" % ids)

        # status --all 列出两 req
        rall = run(workdir_cc, "status", "--all", req_id=None, expect_rc=0)
        check("status --all 列出两 req", rA in rall.stdout and rB in rall.stdout, rall.stdout[:400])
    finally:
        shutil.rmtree(workdir_cc, ignore_errors=True)


def test_manifest_concurrent_update():
    """并发 manifest update：FileLock 串行化，无损坏无丢行。"""
    print("\n[new] 并发 manifest update：FileLock 串行化，无损坏无丢行")
    workdir_mc = tempfile.mkdtemp(prefix="qamaster-rt-test-mc-")
    try:
        rA = "清单甲-20260808"
        rB = "清单乙-20260808"
        run(workdir_mc, "manifest", "add", "--req-id", rA, req_id=None, expect_rc=0)
        run(workdir_mc, "manifest", "add", "--req-id", rB, req_id=None, expect_rc=0)

        errors = []

        def worker(rid, idx):
            try:
                run(workdir_mc, "manifest", "update", "--req-id", rid,
                    "--knowledge-file", "Kf_%s_%d.md" % (rid, idx),
                    "--ledger-file", "Lg_%s_%d.md" % (rid, idx),
                    req_id=None, expect_rc=0)
            except Exception as e:  # noqa
                errors.append("%s/%d: %s" % (rid, idx, e))

        threads = []
        for i in range(6):
            threads.append(threading.Thread(target=worker, args=(rA, i)))
            threads.append(threading.Thread(target=worker, args=(rB, i)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        check("并发更新无异常", not errors, str(errors[:3]))
        rows = _MANIFEST.load_rows(manifest_path(workdir_mc))
        ids = [row.get("req_id") for row in rows]
        check("并发后两行均存在", rA in ids and rB in ids, "ids=%s" % ids)
        check("并发后无重复行", len(ids) == len(set(ids)) == 2, "ids=%s" % ids)
        for row in rows:
            check("%s 行字段已写（非空）" % row.get("req_id"),
                  bool(row.get("knowledge_file")) and bool(row.get("ledger_file")), str(row))
    finally:
        shutil.rmtree(workdir_mc, ignore_errors=True)


def test_phase0_manifest_created_on_pass():
    """C1：空 MANIFEST 下 Phase 0 gate PASS 由 Runtime 自动创建 MANIFEST（gate-check 不卡 exists MANIFEST）。"""
    print("\n[new] Phase 0 gate PASS 自动创建 MANIFEST（C1）")
    out = "case-design-out"
    workdir_p0 = tempfile.mkdtemp(prefix="qamaster-rt-test-p0-")
    try:
        rid = "清单创建-20260808"
        run(workdir_p0, "start", "--req-id", rid, req_id=rid, expect_rc=0)
        check("初始无 MANIFEST", not os.path.isfile(manifest_path(workdir_p0)))
        w(workdir_p0, os.path.join(out, "REQ_%s.md" % rid), "# %s\n\n## 订单创建\n\n内容\n" % rid)
        r = run(workdir_p0, "gate", req_id=rid, expect_rc=0)
        check("Phase 0 gate PASS", "GATE RESULT: PASS" in r.stdout, r.stdout[-400:])
        check("gate PASS 后 MANIFEST 自动创建", os.path.isfile(manifest_path(workdir_p0)))
        rows = _MANIFEST.load_rows(manifest_path(workdir_p0))
        ids = [row.get("req_id") for row in rows]
        check("MANIFEST 含本 req 行", rid in ids, "ids=%s" % ids)
        row = next((row for row in rows if row.get("req_id") == rid), None)
        check("行 status=进行中", row is not None and row.get("status") == "进行中", str(row))
    finally:
        shutil.rmtree(workdir_p0, ignore_errors=True)


def test_legacy_migration():
    """legacy v2 状态迁移到分区路径；空 req_id 拒绝迁移（归属不明）。"""
    print("\n[new] legacy v2 状态迁移到分区路径；空 req_id 拒绝迁移")
    out = "case-design-out"

    def _legacy_state(workdir, rid, phase):
        return {
            "schema": 2, "workflow": WORKFLOW, "req_id": rid, "workdir": workdir,
            "current_phase": phase, "completed": list(range(0, phase)), "status": "RUNNING",
            "run_mode": "full", "depth": "heavy", "input_kind": "requirement",
            "skipped_phases": [], "failed_gates": {}, "confirm_rounds": 0, "history": [],
            "created_at": "2026-07-01 10:00:00", "updated_at": "2026-07-01 11:00:00",
        }

    workdir_lm = tempfile.mkdtemp(prefix="qamaster-rt-test-legacy-")
    try:
        LEG = "迁移需求-20260808"
        legacy_dir = os.path.join(workdir_lm, out, ".runtime")
        os.makedirs(legacy_dir, exist_ok=True)
        with open(os.path.join(legacy_dir, "state.json"), "w", encoding="utf-8") as f:
            json.dump(_legacy_state(workdir_lm, LEG, 5), f, ensure_ascii=False)

        ok, rid, reason = _STATE.migrate_legacy_state(workdir_lm, WORKFLOW)
        check("非空 req_id 迁移返回 migrated", ok is True and rid == LEG,
              "ret=(%s,%s,%s)" % (ok, rid, reason))
        new_path = os.path.join(workdir_lm, QAMASTER_PART, LEG, "state.json")
        check("迁移到分区路径", os.path.isfile(new_path))
        with open(new_path, "r", encoding="utf-8") as f:
            st = json.load(f)
        check("迁移保留 current_phase=5", st["current_phase"] == 5, "phase=%s" % st.get("current_phase"))
        check("迁移保留 req_id", st["req_id"] == LEG)
        check("迁移升 schema=3", st["schema"] == 3, "schema=%s" % st.get("schema"))
        # 幂等：再迁一次不重建
        ok2, _rid2, reason2 = _STATE.migrate_legacy_state(workdir_lm, WORKFLOW)
        check("二次迁移幂等", ok2 is False, "ret2=(%s,%s)" % (ok2, reason2))
        # start 命中已迁移的分区状态 → 断点续跑（不重置）
        r = run(workdir_lm, "start", "--req-id", LEG, req_id=LEG, expect_rc=0)
        check("start 检测到迁移后状态续跑", "断点续跑" in r.stdout, r.stdout[:300])
    finally:
        shutil.rmtree(workdir_lm, ignore_errors=True)

    # 空 req_id 旧状态 → 拒绝迁移
    workdir_lm2 = tempfile.mkdtemp(prefix="qamaster-rt-test-legacy-empty-")
    try:
        legacy_dir2 = os.path.join(workdir_lm2, out, ".runtime")
        os.makedirs(legacy_dir2, exist_ok=True)
        with open(os.path.join(legacy_dir2, "state.json"), "w", encoding="utf-8") as f:
            json.dump(_legacy_state(workdir_lm2, "", 3), f, ensure_ascii=False)
        ok, rid, reason = _STATE.migrate_legacy_state(workdir_lm2, WORKFLOW)
        check("空 req_id 拒绝迁移", ok is False and "empty req_id" in reason, "reason=%s" % reason)
        check("空 req_id 未生成分区状态", not os.path.isdir(os.path.join(workdir_lm2, QAMASTER_PART)))
        check("空 req_id 旧状态保留原处", os.path.isfile(os.path.join(legacy_dir2, "state.json")))
    finally:
        shutil.rmtree(workdir_lm2, ignore_errors=True)


def test_bootstrap_idempotent():
    """bootstrap 幂等：在途需求重跑输出 RESUME 且不重建状态（C8）。"""
    print("\n[new] bootstrap 幂等：在途需求重跑输出 RESUME 且不重建状态（C8）")
    workdir_bi = tempfile.mkdtemp(prefix="qamaster-rt-test-bs-")
    try:
        r1 = run(workdir_bi, "bootstrap", "--user-input", "# 幂等需求", req_id=None, expect_rc=0)
        check("首次 bootstrap 输出 BOOTSTRAP OK", "BOOTSTRAP OK" in r1.stdout, r1.stdout[:200])
        import re as _re
        m = _re.search(r"req_id=(\S+)", r1.stdout)
        check("首次 bootstrap 派生 req_id", m is not None, r1.stdout[:200])
        rid = m.group(1)
        st_path = os.path.join(workdir_bi, QAMASTER_PART, rid, "state.json")
        check("bootstrap 未创建状态文件", not os.path.isfile(st_path))

        run(workdir_bi, "start", "--req-id", rid, req_id=rid, expect_rc=0)
        st = state_of(workdir_bi, rid)
        created0 = st["created_at"]
        check("start 后状态 created_at 已记录", bool(created0))

        r2 = run(workdir_bi, "bootstrap", "--user-input", "# 幂等需求", req_id=None, expect_rc=0)
        check("二次 bootstrap 输出 RESUME", "BOOTSTRAP RESUME" in r2.stdout, r2.stdout[:200])
        check("RESUME 含 phase/status", "phase=" in r2.stdout and "status=" in r2.stdout, r2.stdout[:200])
        st2 = state_of(workdir_bi, rid)
        check("RESUME 后 created_at 不变（C8 不重建状态）", st2["created_at"] == created0,
              "before=%s after=%s" % (created0, st2["created_at"]))
    finally:
        shutil.rmtree(workdir_bi, ignore_errors=True)


def test_manifest_reconcile():
    """C6 兜底：删 MANIFEST 后 manifest reconcile 从磁盘 REQ_/TestCases_ 重建索引。"""
    print("\n[new] manifest reconcile：从磁盘重建索引（C6 兜底）")
    out = "case-design-out"
    workdir_rc = tempfile.mkdtemp(prefix="qamaster-rt-test-recon-")
    try:
        rid = "重建清单-20260808"
        w(workdir_rc, os.path.join(out, "REQ_%s.md" % rid), "# %s\n\n## 订单创建\n\n内容\n" % rid)
        w(workdir_rc, os.path.join(out, "TestCases_%s.md" % rid),
          TC_MD.format(req=rid, header=HEADER, sep=SEP))
        check("初始无 MANIFEST", not os.path.isfile(manifest_path(workdir_rc)))
        r = run(workdir_rc, "manifest", "reconcile", req_id=None, expect_rc=0)
        check("reconcile 输出 OK", "MANIFEST RECONCILE: OK" in r.stdout, r.stdout[:300])
        rows = _MANIFEST.load_rows(manifest_path(workdir_rc))
        ids = [row.get("req_id") for row in rows]
        check("reconcile 重建出本 req 行", rid in ids, "ids=%s" % ids)
        row = next((row for row in rows if row.get("req_id") == rid), None)
        check("reconcile 回填 testcase_files", row is not None and "TestCases" in (row.get("testcase_files") or ""),
              str(row))
        check("reconcile 回填 req_file", row is not None and "REQ_" in (row.get("req_file") or ""), str(row))
    finally:
        shutil.rmtree(workdir_rc, ignore_errors=True)


# ===== KB 经验库自证（自我进化·机制与模型无关·13 项）=====
# 铁律守护：无 KB 文件 → 完全 no-op → 与基线逐字节一致；KB 影响一律软上下文，非硬门。
# 信任门：endorsed 或 occ≥3；相关性门：surface≥2 或标题命中（预防）/ 失败文本命中≥1 或 REQ 命中≥2（反应）。

def _kb_path_of(workdir):
    return os.path.join(workdir, "case-design-out", "KB_lessons.md")


def _kb_business_path_of(workdir):
    return os.path.join(workdir, "case-design-out", "KB_business.md")


def _kb_seed(workdir, records):
    """直接落盘 KB_lessons.md（绕过 upsert 指纹，精确控制 id/status/phase/occ）。"""
    import kb_store
    kb_store._save_records(_kb_path_of(workdir), records)


def _kb_seed_business(workdir, records):
    """直接落盘 KB_business.md（business 文件，横幅随 records kind 推断）。"""
    import kb_store
    kb_store._save_records(_kb_business_path_of(workdir), records)


def _kb_rec(rid, phase, dim, status, occ, trigger, raw_text,
            source_req="kb-seed", module="", superseded_by=None):
    """构造一条完整 KB 记录 dict（字段与 kb_store._DEFAULT_REC 对齐）。"""
    return {
        "kind": "lesson", "id": rid, "phase": str(phase), "dimension": dim,
        "error_type": "人工纠正", "module": module, "source_req": source_req,
        "source_reqs": [source_req], "captured": "2026-08-09",
        "supersedes": [], "superseded_by": list(superseded_by or []),
        "occurrences": occ, "status": status, "trigger": list(trigger),
        "raw_text": raw_text, "variants": [],
    }


def _kb_biz_rec(rid, dim, status, occ, trigger, raw_text,
                source_req="kb-biz", module="订单", superseded_by=None):
    """构造一条 business KB 记录 dict（kind=business，phase=14，error_type=业务知识）。
    结构键=(module,dimension)；指纹前缀 KB-business-。"""
    return {
        "kind": "business", "id": rid, "phase": "14", "dimension": dim,
        "error_type": "业务知识", "module": module, "source_req": source_req,
        "source_reqs": [source_req], "captured": "2026-08-09",
        "supersedes": [], "superseded_by": list(superseded_by or []),
        "occurrences": occ, "status": status, "trigger": list(trigger),
        "raw_text": raw_text, "variants": [],
    }


def _kb_expert_path_of(workdir):
    return os.path.join(workdir, "case-design-out", "KB_expert.md")


def _kb_seed_expert(workdir, records):
    """直接落盘 KB_expert.md（绕过 upsert 指纹，精确控制 id/status/category/principle/applicable_phases）。"""
    import kb_store
    kb_store._save_records(_kb_expert_path_of(workdir), records)


def _kb_expert_rec(rid, category, principle, applicable_phases, status, occ,
                   trigger, raw_text, source_req="kb-expert", module="", superseded_by=None):
    """构造一条 expert KB 记录 dict（kind=expert，通用方法论）。
    结构键=(category, principle[:40])；指纹前缀 KB-expert-。raw_text 由调用方给（测试断言用，
    真实 add-expert 落 raw_text=principle；此处分离以便断言文本独立于 principle）。"""
    return {
        "kind": "expert", "id": rid, "phase": "", "dimension": "通用",
        "error_type": "方法提炼", "module": module, "source_req": source_req,
        "source_reqs": [source_req], "captured": "2026-08-09",
        "supersedes": [], "superseded_by": list(superseded_by or []),
        "occurrences": occ, "status": status, "trigger": list(trigger),
        "raw_text": raw_text, "variants": [],
        "category": category, "applicable_phases": list(applicable_phases),
        "principle": principle,
    }


def _kb_state(workdir, rid, name=None):
    """构造最小 state 供 KB 检索 helper（workdir + req_id）。"""
    return {"workdir": workdir, "req_id": rid, "name": name or rid}


def _seed_state(workdir, rid, current_phase, completed):
    """直接落分区 state.json（跳过昂贵推进），供 KB fail/patch 测试构造前置态。

    KB 测试聚焦经验库机制，不需真实跑完 Phase 0-7；直接落一个合法 schema=3
    状态使 `fail --to <N>` / `patch --to <N>` 的目标<当前阶段合法。
    """
    sp = _STATE.default_state_path(workdir, WORKFLOW, rid)
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    st = _STATE.new_state(WORKFLOW, rid, workdir)
    st["current_phase"] = current_phase
    st["completed"] = list(completed)
    st["depth"] = "heavy"
    st["run_mode"] = "full"
    st["input_kind"] = "requirement"
    _STATE.save(sp, st)
    return sp


def _kb_req_file(workdir, rid, text):
    """落 case-design-out/REQ_<id>.md，供 surface 命中（镜像 runtime _read_req_text）。"""
    w(workdir, os.path.join("case-design-out", "REQ_%s.md" % rid), text)


# 并发幂等类的 REQ 正文（含真实 surface 词，使 _prior_kb_block 相关性门可达 surface≥2）
_KB_REQ_CONCURRENCY = """# %s

## 订单创建

用户提交订单，系统并发扣减库存，重复提交需幂等。状态置为待支付。
"""


def test_kb_noop_preserves_baseline():
    """无 KB_lessons.md → 预防式/反应式均返 ''（no-op，护基线 150/0 逐字节一致）。"""
    print("\n[kb] 无 KB 文件 → 双链路 no-op（护基线 150/0）")
    import qamaster_runtime as rt
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kb-noop-")
    try:
        phase = spec.get_phase(5)
        st = _kb_state(workdir, "noop-req")
        check("无 KB 文件 → 预防式返回空串",
              rt._prior_kb_block(st, phase, spec) == "", "应 no-op")
        check("无 KB 文件 → 反应式返回空串",
              rt._relevant_lessons_on_fail(st, phase, "并发超卖", spec) == "", "应 no-op")
        # 反应式对空 fail_context 也应 no-op
        check("无 KB 文件 → 反应式空 context 返回空串",
              rt._relevant_lessons_on_fail(st, phase, "", spec) == "", "应 no-op")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_autocapture_silent_draft_not_injected():
    """fail --reason：KB 出现 draft(occ=1)，stdout 无捕获噪声，预防式/反应式都不注入。"""
    print("\n[kb] 自动捕获静默 draft(occ=1) 不注入（护既有 substring 断言）")
    workdir = tempfile.mkdtemp(prefix="qamaster-kb-capture-")
    try:
        import qamaster_runtime as rt
        from case_design import spec as _cd_spec
        spec = _cd_spec()
        rid = "并发需求-20260809"
        _seed_state(workdir, rid, 7, [0, 1, 2, 3, 4, 5, 6])
        _kb_req_file(workdir, rid, _KB_REQ_CONCURRENCY % rid)
        # fail --to 5 --reason 含并发 surface 词（确保捕获后 dim=并发幂等）
        reason = "漏标并发超卖 P0，因为下单重复提交必须覆盖幂等"
        r = run(workdir, "fail", "--to", "5", "--reason", reason, req_id=rid, expect_rc=0)
        kb_p = _kb_path_of(workdir)
        check("fail 后 KB_lessons.md 被创建", os.path.isfile(kb_p), "KB 文件应自动沉淀")
        import kb_store
        recs = kb_store.load_records(kb_p)
        check("KB 沉淀一条 draft 记录", len(recs) == 1 and recs[0]["status"] == "draft",
              "recs=%s" % [(x.get("status"), x.get("occurrences")) for x in recs])
        check("draft 记录 occ=1", recs[0].get("occurrences") == 1, "occ=%s" % recs[0].get("occurrences"))
        check("捕获静默（stdout 无经验沉淀 WARN/噪声）",
              "经验沉淀" not in r.stdout and "KB ADD" not in r.stdout,
              "stdout 含捕获噪声: %s" % r.stdout[:300])
        check("捕获 reason verbatim 落 raw_text",
              recs[0].get("raw_text") == reason, "raw=%s" % recs[0].get("raw_text"))
        # 落 draft/occ=1 → 双链路都不注入（信任门）
        st = _kb_state(workdir, rid)
        phase5 = spec.get_phase(5)
        check("draft/occ=1 → 预防式不注入",
              rt._prior_kb_block(st, phase5, spec) == "", "应不过信任门")
        check("draft/occ=1 → 反应式不注入",
              rt._relevant_lessons_on_fail(st, phase5, reason, spec) == "", "应不过信任门")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_surface_map_via_subprocess():
    """verify_cases.py --dump-surface-map 合法 JSON、5 类齐全；get_surface_map memoize。"""
    print("\n[kb] surface map 经子进程取（单一真源零漂移 + memoize）")
    import kb_store
    script = os.path.join(SKILL_SCRIPTS, "verify_cases.py")
    proc = subprocess.run([sys.executable, script, "--dump-surface-map"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=30)
    check("--dump-surface-map 退出码 0", proc.returncode == 0, "rc=%d" % proc.returncode)
    m = json.loads(proc.stdout)
    expected = {"状态机流转", "权限与敏感数据", "异常处理", "上下游依赖", "并发幂等"}
    check("surface map 含 5 类齐全", set(m.keys()) == expected,
          "keys=%s" % set(m.keys()))
    check("并发幂等类非空", len(m.get("并发幂等", [])) > 0, "并发幂等=%s" % m.get("并发幂等"))
    # get_surface_map 走子进程并 memoize（同 skill_dir 第二次命中缓存）
    import qamaster_runtime as rt
    skill_dir = os.path.join(rt.PLUGIN_ROOT, "skills", "case-design")
    m1 = kb_store.get_surface_map(skill_dir)
    check("get_surface_map 返回 5 类", set(m1.keys()) == expected, "keys=%s" % set(m1.keys()))
    # 清缓存后再调一次，确认稳定
    kb_store._surf_cache.pop(skill_dir, None)
    m2 = kb_store.get_surface_map(skill_dir)
    check("get_surface_map 重复调用一致", m1 == m2, "两次结果不一致")


def test_kb_dim_trigger_union():
    """REQ+reason 含并发 surface 词：dim=并发幂等，trigger=各类命中并集。"""
    print("\n[kb] 维度/触发词派生（dim=命中最多类，trigger=全类并集）")
    import qamaster_runtime as rt
    import kb_store
    skill_dir = os.path.join(rt.PLUGIN_ROOT, "skills", "case-design")
    surfmap = kb_store.get_surface_map(skill_dir)
    req_text = "用户提交订单，系统并发扣减库存，重复提交需幂等。"
    reason = "漏标并发超卖 P0，因为重复提交必须覆盖幂等"
    dim, trigger = rt._derive_dim_trigger(req_text, reason, surfmap)
    check("dim=并发幂等", dim == "并发幂等", "dim=%s" % dim)
    # 并发/幂等/重复提交 至少在 trigger 并集
    check("trigger 并集含并发", "并发" in trigger, "trigger=%s" % trigger)
    check("trigger 并集含幂等", "幂等" in trigger, "trigger=%s" % trigger)
    check("trigger 并集含重复提交", "重复提交" in trigger, "trigger=%s" % trigger)
    # 无任何命中 → 通用 + 空 trigger
    dim2, trig2 = rt._derive_dim_trigger("完全无关的普通文案", "", surfmap)
    check("无命中 → dim=通用", dim2 == "通用", "dim=%s" % dim2)
    check("无命中 → trigger=空", trig2 == [], "trig=%s" % trig2)


def test_kb_fingerprint_coarse_recurrence():
    """同(phase,dim)不同 source_req 两次：一条 occ=2、variants 两条、trigger 并集。"""
    print("\n[kb] 指纹去重（同(phase,dim)跨需求 occ 累积 + trigger 并集）")
    import kb_store
    workdir = tempfile.mkdtemp(prefix="qamaster-kb-fp-")
    try:
        kb_p = _kb_path_of(workdir)
        base = {"kind": "lesson", "phase": "5", "dimension": "并发幂等",
                "error_type": "人工纠正", "module": "", "captured": "2026-08-09",
                "status": "draft", "occurrences": 1, "raw_text": ""}
        r1 = dict(base, source_req="订单A-20260809", raw_text="漏标并发超卖",
                  trigger=["并发", "重复提交", "幂等"])
        r2 = dict(base, source_req="秒杀B-20260809", raw_text="秒杀场景漏幂等",
                  trigger=["并发", "重复扣减", "幂等"])
        kb_store.upsert_lesson(kb_p, r1)
        kb_store.upsert_lesson(kb_p, r2)
        recs = kb_store.load_records(kb_p)
        check("去重后仅一条记录", len(recs) == 1, "len=%d" % len(recs))
        rec = recs[0]
        # 预期指纹 = KB-lesson- + sha1("5|并发幂等")[:12]
        expect_id = kb_store.fingerprint({"phase": "5", "dimension": "并发幂等"})
        check("id=指纹(phase,dim)", rec["id"] == expect_id, "id=%s expect=%s" % (rec["id"], expect_id))
        check("occ=2（跨需求累积）", rec["occurrences"] == 2, "occ=%s" % rec["occurrences"])
        check("source_reqs 含两需求",
              set(rec["source_reqs"]) == {"订单A-20260809", "秒杀B-20260809"},
              "reqs=%s" % rec["source_reqs"])
        check("trigger=并集", set(rec["trigger"]) == {"并发", "重复提交", "幂等", "重复扣减"},
              "trigger=%s" % rec["trigger"])
        check("variants 累积两条", len(rec["variants"]) == 2, "variants=%s" % rec["variants"])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_preventive_dual_gate():
    """4 条种子：endorsed+surface≥2 / draft occ=1+surface≥2[不注入] / 错阶段 / 被废止。仅 endorsed 注入。"""
    print("\n[kb] 预防式双门（相关+信任）：仅 endorsed 那条注入")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kb-prev-")
    try:
        rid = "并发需求-20260809"
        _kb_req_file(workdir, rid, _KB_REQ_CONCURRENCY % rid)
        fp_endorsed = kb_store.fingerprint({"phase": "5", "dimension": "并发幂等"})
        fp_draft = kb_store.fingerprint({"phase": "5", "dimension": "异常处理"})
        fp_wrongphase = kb_store.fingerprint({"phase": "7", "dimension": "并发幂等"})
        fp_superseded = kb_store.fingerprint({"phase": "5", "dimension": "上下游依赖"})
        fp_new = kb_store.fingerprint({"phase": "5", "dimension": "权限与敏感数据"})
        recs = [
            _kb_rec(fp_endorsed, 5, "并发幂等", "endorsed", 1,
                    ["并发", "幂等", "重复提交"], "endorsed 并发经验", source_req="A"),
            _kb_rec(fp_draft, 5, "异常处理", "draft", 1,
                    ["并发", "幂等", "重复提交", "参数非法"], "draft 异常类 occ=1", source_req="A"),
            _kb_rec(fp_wrongphase, 7, "并发幂等", "endorsed", 1,
                    ["并发", "幂等"], "endorsed 但错阶段", source_req="A"),
            _kb_rec(fp_superseded, 5, "上下游依赖", "endorsed", 1,
                    ["上游", "失败", "重试"], "endorsed 但被废止", source_req="A",
                    superseded_by=[fp_new]),
        ]
        _kb_seed(workdir, recs)
        st = _kb_state(workdir, rid)
        phase5 = spec.get_phase(5)
        block = rt._prior_kb_block(st, phase5, spec)
        check("预防式注入非空", bool(block), "应注入 endorsed 那条")
        check("注入含 endorsed 并发经验原文", "endorsed 并发经验" in block, block)
        check("注入标签 PRIOR_LESSONS", "##PRIOR_LESSONS##" in block, block)
        check("draft/occ=1 不注入（异常类）", "draft 异常类 occ=1" not in block, "信任门失效")
        check("错阶段不注入", "endorsed 但错阶段" not in block, "阶段门失效")
        check("被废止不注入", "endorsed 但被废止" not in block, "废止门失效")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_reactive_failure_targeted():
    """endorsed Phase-5 并发经验：fail_detail 含触发词 → 注入；不含 → ''。"""
    print("\n[kb] 反应式失败定向（失败文本命中=强信号）")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kb-react-")
    try:
        rid = "并发需求-20260809"
        _kb_req_file(workdir, rid, _KB_REQ_CONCURRENCY % rid)
        fp = kb_store.fingerprint({"phase": "5", "dimension": "并发幂等"})
        _kb_seed(workdir, [_kb_rec(fp, 5, "并发幂等", "endorsed", 1,
                                   ["并发", "幂等", "重复提交", "重复扣减"],
                                   "并发超卖必须覆盖幂等", source_req="A")])
        st = _kb_state(workdir, rid)
        phase5 = spec.get_phase(5)
        # 失败文本含触发词 → 注入
        hit = rt._relevant_lessons_on_fail(st, phase5, "并发扣减导致重复提交超卖", spec)
        check("失败文本命中 → 反应式注入", bool(hit), "应注入")
        check("反应式标签 RELEVANT_LESSONS", "##RELEVANT_LESSONS##" in hit, hit)
        check("反应式含经验原文", "并发超卖必须覆盖幂等" in hit, hit)
        check("反应式含修正页脚", "请据此修正" in hit, hit)
        # 失败文本不含触发词、且 REQ 也不含触发词 → ''（hit_fail=0 且 hit_req<2）
        rid2 = "界面需求-20260809"
        _kb_req_file(workdir, rid2, "# %s\n\n## 界面布局\n\n按钮对齐与配色规范\n" % rid2)
        st2 = _kb_state(workdir, rid2)
        miss = rt._relevant_lessons_on_fail(st2, phase5, "界面按钮样式不对齐", spec)
        check("失败文本无命中 → 不注入", miss == "", "应 no-op: %s" % miss)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_reactive_respects_trust_gate():
    """draft/occ=1：反应式不注入（信任门）。"""
    print("\n[kb] 反应式尊重信任门（draft/occ=1 不注入）")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kb-trust-")
    try:
        rid = "并发需求-20260809"
        _kb_req_file(workdir, rid, _KB_REQ_CONCURRENCY % rid)
        fp = kb_store.fingerprint({"phase": "5", "dimension": "并发幂等"})
        _kb_seed(workdir, [_kb_rec(fp, 5, "并发幂等", "draft", 1,
                                   ["并发", "幂等", "重复提交"],
                                   "draft 并发经验 occ=1", source_req="A")])
        st = _kb_state(workdir, rid)
        phase5 = spec.get_phase(5)
        block = rt._relevant_lessons_on_fail(st, phase5, "并发重复提交超卖", spec)
        check("draft/occ=1 反应式不注入", block == "", "信任门失效: %s" % block)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_endorse_and_supersede():
    """draft→endorsed：预防/反应均注入；supersede 后均消失。"""
    print("\n[kb] endorse 注入 + supersede 失效")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kb-endorse-")
    try:
        rid = "并发需求-20260809"
        _kb_req_file(workdir, rid, _KB_REQ_CONCURRENCY % rid)
        fp_old = kb_store.fingerprint({"phase": "5", "dimension": "并发幂等"})
        fp_new = kb_store.fingerprint({"phase": "5", "dimension": "异常处理"})
        _kb_seed(workdir, [_kb_rec(fp_old, 5, "并发幂等", "draft", 1,
                                   ["并发", "幂等", "重复提交"],
                                   "draft 待背书并发经验", source_req="A")])
        # endorse（走 kb 命令，验证整链路）
        run(workdir, "kb", "endorse", "--id", fp_old, req_id=rid, expect_rc=0)
        st = _kb_state(workdir, rid)
        phase5 = spec.get_phase(5)
        prior = rt._prior_kb_block(st, phase5, spec)
        check("endorse 后预防式注入", "draft 待背书并发经验" in prior, prior)
        react = rt._relevant_lessons_on_fail(st, phase5, "并发重复提交", spec)
        check("endorse 后反应式注入", "draft 待背书并发经验" in react, react)
        # supersede：老被新取代 → 两链路都不再注入老经验
        _kb_seed(workdir, [_kb_rec(fp_old, 5, "并发幂等", "endorsed", 1,
                                   ["并发", "幂等", "重复提交"],
                                   "draft 待背书并发经验", source_req="A",
                                   superseded_by=[fp_new]),
                            _kb_rec(fp_new, 5, "异常处理", "endorsed", 1,
                                    ["参数非法", "并发"], "新异常类经验", source_req="A")])
        prior2 = rt._prior_kb_block(st, phase5, spec)
        check("supersede 后老经验预防式不注入",
              "draft 待背书并发经验" not in prior2, "废止失效: %s" % prior2)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_threshold_recurrence_injected():
    """draft occ≥3 后预防/反应均注入（无需背书，跨需求置信门）。"""
    print("\n[kb] occ≥3 阈值门（无需背书即可注入）")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kb-thresh-")
    try:
        rid = "并发需求-20260809"
        _kb_req_file(workdir, rid, _KB_REQ_CONCURRENCY % rid)
        fp = kb_store.fingerprint({"phase": "5", "dimension": "并发幂等"})
        # occ=3 但仍 draft（三个不同 source_req 累积）
        rec = _kb_rec(fp, 5, "并发幂等", "draft", 3,
                      ["并发", "幂等", "重复提交"],
                      "draft occ=3 跨需求并发经验", source_req="A")
        rec["source_reqs"] = ["A", "B", "C"]
        _kb_seed(workdir, [rec])
        st = _kb_state(workdir, rid)
        phase5 = spec.get_phase(5)
        prior = rt._prior_kb_block(st, phase5, spec)
        check("occ≥3 draft 预防式注入（无需背书）",
              "draft occ=3 跨需求并发经验" in prior, prior)
        react = rt._relevant_lessons_on_fail(st, phase5, "并发重复提交超卖", spec)
        check("occ≥3 draft 反应式注入（无需背书）",
              "draft occ=3 跨需求并发经验" in react, react)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_concurrent_add():
    """12 线程并发捕获：FileLock 串行、无损坏、去重正确。镜像 test_manifest_concurrent_update。"""
    print("\n[kb] 并发捕获（FileLock 串行化，无损坏无丢条）")
    import kb_store
    workdir = tempfile.mkdtemp(prefix="qamaster-kb-conc-")
    try:
        kb_p = _kb_path_of(workdir)
        os.makedirs(os.path.dirname(kb_p), exist_ok=True)
        errors = []
        base_rec = {"kind": "lesson", "phase": "5", "dimension": "并发幂等",
                    "error_type": "人工纠正", "module": "", "captured": "2026-08-09",
                    "status": "draft", "occurrences": 1, "raw_text": "",
                    "trigger": ["并发", "幂等", "重复提交"]}
        # 6 个不同 source_req × 2 = 12 次并发 upsert，全部同指纹 → 应合并成 1 条 occ=6
        reqs = ["并发A-%d" % i for i in range(6)] + ["秒杀B-%d" % i for i in range(6)]

        def worker(rid):
            try:
                rec = dict(base_rec, source_req=rid, raw_text="并发超卖 from %s" % rid)
                with locking.FileLock(kb_p, timeout=30):
                    kb_store.upsert_lesson(kb_p, rec)
            except Exception as e:  # noqa
                errors.append("%s: %s" % (rid, e))

        import locking
        threads = [threading.Thread(target=worker, args=(rid,)) for rid in reqs]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        check("并发捕获无异常", not errors, str(errors[:3]))
        recs = kb_store.load_records(kb_p)
        check("并发后仅一条记录（指纹去重）", len(recs) == 1, "len=%d" % len(recs))
        rec = recs[0]
        check("occ=12（12 个不同 source_req 累积）",
              rec["occurrences"] == 12, "occ=%s" % rec["occurrences"])
        check("source_reqs 含全部 12 需求",
              len(rec["source_reqs"]) == 12, "reqs=%d" % len(rec["source_reqs"]))
        check("variants 累积 12 条", len(rec["variants"]) == 12,
              "variants=%d" % len(rec["variants"]))
        check("trigger 并集稳定",
              set(rec["trigger"]) == {"并发", "幂等", "重复提交"}, "trigger=%s" % rec["trigger"])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_distill_replays_history():
    """经 fail/patch/gate_fail 后 kb distill：stdout 含全部 reason（含 gate_fail，零模型）。"""
    print("\n[kb] distill 回放纠正历史（含 gate_fail，零模型）")
    workdir = tempfile.mkdtemp(prefix="qamaster-kb-distill-")
    try:
        rid = "回放需求-20260809"
        _seed_state(workdir, rid, 7, [0, 1, 2, 3, 4, 5, 6])
        _kb_req_file(workdir, rid, _KB_REQ_CONCURRENCY % rid)
        # fail（落 rollback）
        run(workdir, "fail", "--to", "5", "--reason", "fail原因:并发超卖",
            req_id=rid, expect_rc=0)
        # 推进 current_phase 到 7（fail 已设到 5，需 next 回到 7 供 patch）
        # 直接重置 state：patch --to 5 需 current_phase>5
        sp = _STATE.default_state_path(workdir, WORKFLOW, rid)
        st = _STATE.load(sp)
        st["current_phase"] = 7
        st["completed"] = [0, 1, 2, 3, 4, 5, 6]
        _STATE.save(sp, st)
        # patch（落 patch 指令）
        run(workdir, "patch", "--to", "5", "--reason", "patch原因:幂等漏标",
            req_id=rid, expect_rc=0)
        # 手工注入一条 gate_fail 历史（runtime gate_fail 写 history.detail=fail_detail）
        st = _STATE.load(sp)
        _STATE.log_event(st, "gate_fail", phase=7, detail="gate_fail原因:覆盖不全")
        _STATE.save(sp, st)
        # distill 回放
        r = run(workdir, "kb", "distill", "--req-id", rid, req_id=rid, expect_rc=0)
        check("distill 含 fail 原因", "fail原因:并发超卖" in r.stdout, r.stdout[-600:])
        check("distill 含 patch 原因", "patch原因:幂等漏标" in r.stdout, r.stdout[-600:])
        check("distill 含 gate_fail 原因", "gate_fail原因:覆盖不全" in r.stdout, r.stdout[-600:])
        check("distill 标注零模型", "零模型" in r.stdout, r.stdout[-600:])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_capture_never_blocks_correction():
    """KB 文件锁占用时 fail 仍成功（best-effort，仅 WARN 不阻断）。"""
    print("\n[kb] 捕获不阻断纠正（锁占用 → WARN，fail 仍成功）")
    import locking
    workdir = tempfile.mkdtemp(prefix="qamaster-kb-block-")
    try:
        rid = "不阻断需求-20260809"
        _seed_state(workdir, rid, 7, [0, 1, 2, 3, 4, 5, 6])
        _kb_req_file(workdir, rid, _KB_REQ_CONCURRENCY % rid)
        kb_p = _kb_path_of(workdir)
        os.makedirs(os.path.dirname(kb_p), exist_ok=True)
        # 预创建 KB 文件并长期持锁（30s 内不释放）
        with open(kb_p, "w", encoding="utf-8") as f:
            f.write("# 占位")
        held = {"ok": False}

        def hold():
            try:
                with locking.FileLock(kb_p, timeout=30):
                    held["ok"] = True
                    time.sleep(8)  # 占住锁
            except Exception:
                pass

        import time
        t = threading.Thread(target=hold)
        t.start()
        # 等待持锁
        for _ in range(50):
            if held["ok"]:
                break
            time.sleep(0.05)
        # fail 在锁占用下仍应 rc=0（best-effort 捕获，不阻断纠正）
        r = run(workdir, "fail", "--to", "5", "--reason", "并发重复提交超卖",
                req_id=rid, expect_rc=0)
        check("锁占用下 fail 仍成功（rc=0）", r.returncode == 0, "rc=%d" % r.returncode)
        check("fail 仍输出 ROLLBACK", "ROLLBACK" in r.stdout, r.stdout[:300])
        t.join(timeout=15)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def P_gate_of(st):
    return _RT_PHASES.get_phase(st["current_phase"])["gate"]


def test_kb_query_top_preview():
    """kb query --top K 真正按 K 取条数（flag 不再撒谎）；真实注入路径仍默认 top-3。

    种 4 条同阶段 endorsed、REQ 相关（surface≥2）的经验 → 全过双门，候选 4 条。
    --top 2 取 2；默认 --top 3 取 3；--top 5 取 4（封顶于种子数）。真实注入（直接调 helper）
    仍默认 top=3，与 query 的 top 解耦——验证注入路径不受预览 flag 影响。
    """
    print("\n[kb] kb query --top 预览标志真正生效（默认注入仍 top-3 硬上限）")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kb-top-")
    try:
        rid = "并发需求-20260809"
        _kb_req_file(workdir, rid, _KB_REQ_CONCURRENCY % rid)
        # 4 条 phase=5 endorsed，trigger 各含 ≥2 个 REQ 子串（并发/幂等/重复提交），全过双门
        dims = [("并发幂等", ["并发", "幂等", "重复提交"]),
                ("异常处理", ["并发", "幂等"]),
                ("上下游依赖", ["并发", "重复提交"]),
                ("权限与敏感数据", ["幂等", "重复提交"])]
        recs = []
        for i, (dim, trig) in enumerate(dims):
            fp = kb_store.fingerprint({"phase": "5", "dimension": dim})
            recs.append(_kb_rec(fp, 5, dim, "endorsed", 1, trig,
                                "top-preview 经验 %d" % i, source_req="A"))
        _kb_seed(workdir, recs)

        def _count(out):
            return out.count("- [Phase 5")

        # --top 2 → 2 条
        r2 = run(workdir, "kb", "query", "--phase", "5", "--against", rid, "--top", "2", req_id=rid)
        n2 = _count(r2.stdout)
        check("kb query --top 2 返回 2 条（flag 生效）", n2 == 2, "n2=%d\n%s" % (n2, r2.stdout[-400:]))
        check("--top 2 文案印 top=2", "top=2" in r2.stdout, r2.stdout[-200:])
        # 默认 --top 3 → 3 条
        r3 = run(workdir, "kb", "query", "--phase", "5", "--against", rid, req_id=rid)
        n3 = _count(r3.stdout)
        check("kb query 默认 top=3 返回 3 条", n3 == 3, "n3=%d" % n3)
        # --top 5 → 4 条（封顶种子数）
        r5 = run(workdir, "kb", "query", "--phase", "5", "--against", rid, "--top", "5", req_id=rid)
        n5 = _count(r5.stdout)
        check("kb query --top 5（仅 4 条种子）返回 4 条", n5 == 4, "n5=%d" % n5)
        # 真实注入路径：直接调 helper（不经 query），默认 top=3 → 4 候选截 3
        st = _kb_state(workdir, rid)
        phase5 = spec.get_phase(5)
        block = rt._prior_kb_block(st, phase5, spec)  # 默认 top=3
        check("真实注入路径默认 top-3（4 候选截 3，不受 query flag 影响）",
              block.count("- [Phase 5") == 3, "应 3 条: %d" % block.count("- [Phase 5"))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# =============================================================================
# MVP2b 业务历史知识库（business KB）· 7 项自证
# 约束：No-op 基线（无 Knowledge/无 KB_business.md → 注入返 ''，护 206/0）/ 纯软上下文
# （永不硬门）/ 单一真源零漂移（trigger 复用 surface map）/ 复用不 fork（kind=business
# 共享 kb_store parse/serialize/upsert/fingerprint/retrieve）/ 模型禁写 / 零 schema/门变更。
# =============================================================================

def test_kb_business_noop():
    """无 Knowledge 文件/无 KB_business.md → 预防式(Phase 0)/反应式均返 ''（no-op，护 206/0）。"""
    print("\n[kb-biz] 无 Knowledge/无 KB_business → 双链路 no-op（护 206/0 逐字节一致）")
    import qamaster_runtime as rt
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbbiz-noop-")
    try:
        phase0 = spec.get_phase(0)
        phase5 = spec.get_phase(5)
        st = _kb_state(workdir, "biz-noop-req")
        check("无 KB_business → 预防式(Phase 0)返回空串",
              rt._prior_business_kb_block(st, phase0, spec) == "", "应 no-op")
        check("无 KB_business → 反应式返回空串",
              rt._relevant_business_kb_on_fail(st, phase5, "并发超卖", spec) == "", "应 no-op")
        check("无 KB_business → 反应式空 context 返回空串",
              rt._relevant_business_kb_on_fail(st, phase5, "", spec) == "", "应 no-op")
        # 无 Knowledge 文件 → reconcile 为 no-op（返回 ok=False，count=0，不落 KB_business.md）
        r = run(workdir, "kb", "reconcile", "--kind", "business", req_id="biz-noop-req")
        check("无 Knowledge 文件 → reconcile no-op（count=0）",
              "business 记录 0 条" in r.stdout, r.stdout[:300])
        check("reconcile no-op 不创建 KB_business.md",
              not os.path.isfile(_kb_business_path_of(workdir)), "不应落盘")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_business_reconcile_indexes():
    """种 Knowledge_<rid>.md → kb reconcile --kind business → KB_business.md 落盘；
    记录 kind=business/status=endorsed/module=元数据"更新模块"/dimension=Knowledge 维度标题/
    id 形如 KB-business-<12hex>。"""
    print("\n[kb-biz] reconcile 聚合 Knowledge_*.md → KB_business.md（只索引不生成）")
    import kb_store
    workdir = tempfile.mkdtemp(prefix="qamaster-kbbiz-reconcile-")
    try:
        rid = "自证需求"
        # 落盘 KNOWLEDGE_MD fixture（元数据"更新模块：订单"，含并发扣减库存维度文本）
        w(workdir, os.path.join("case-design-out", "Knowledge_%s.md" % rid), KNOWLEDGE_MD)
        r = run(workdir, "kb", "reconcile", "--kind", "business", req_id="biz-rec", expect_rc=0)
        check("reconcile rc=0", r.returncode == 0, "rc=%d" % r.returncode)
        check("reconcile 输出 OK + 计数",
              "KB RECONCILE: OK" in r.stdout and "business 记录" in r.stdout, r.stdout[:300])
        bp = _kb_business_path_of(workdir)
        check("KB_business.md 被创建", os.path.isfile(bp), "应落盘")
        recs = kb_store.load_records(bp)
        check("reconcile 产出多条 business 记录", len(recs) >= 5, "recs=%d" % len(recs))
        # 跳过"本需求不涉及"的维度（权限模型/配置项 fixture 标注）-> 业务流程/异常处理等应入
        dims = {x.get("dimension") for x in recs}
        check("含业务流程维度", "业务流程" in dims, "dims=%s" % dims)
        check("含异常处理维度", "异常处理" in dims, "dims=%s" % dims)
        check("跳过'本需求不涉及'维度（权限模型）", "权限模型" not in dims, "应跳过")
        # 全量结构断言
        for x in recs:
            check("记录 kind=business", x.get("kind") == "business", "kind=%s" % x.get("kind"))
            check("记录 status=endorsed", x.get("status") == "endorsed", "status=%s" % x.get("status"))
            check("记录 module=元数据'更新模块'(订单)", x.get("module") == "订单", "module=%s" % x.get("module"))
            check("id 形如 KB-business-<12hex>", x.get("id", "").startswith("KB-business-")
                  and len(x.get("id", "")) == len("KB-business-") + 12, "id=%s" % x.get("id"))
        # verify_kb 结构校验通过
        vkb = os.path.join(SKILL_SCRIPTS, "verify_kb.py")
        proc = subprocess.run([sys.executable, vkb, bp], capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
        check("verify_kb 对 KB_business.md 退出码 0", proc.returncode == 0,
              "rc=%d\n%s" % (proc.returncode, proc.stdout[-400:]))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_business_preventive_injects_at_phase0():
    """endorsed business 记录(trigger 含并发/库存扣减) + REQ 含同词 → Phase 0 预防式注入
    ##PRIOR_BUSINESS_KB##；helper phase 无关(任何阶段返同一块)；trigger 零重叠的 REQ → ''。
    _card 仅在 Phase 0 注入 PRIOR_BUSINESS_KB（开工前一次性业务背景）。"""
    print("\n[kb-biz] 预防式业务知识注入（Phase 0；相关性门；_card 仅 Phase 0）")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbbiz-prev-")
    try:
        rid = "并发需求-20260809"
        _kb_req_file(workdir, rid, _KB_REQ_CONCURRENCY % rid)
        fp = kb_store.fingerprint({"kind": "business", "module": "订单", "dimension": "异常处理"})
        _kb_seed_business(workdir, [_kb_biz_rec(
            fp, "异常处理", "endorsed", 1, ["并发", "幂等", "重复提交", "库存扣减"],
            "下单扣库存须覆盖并发重复提交幂等", source_req="A", module="订单")])
        st = _kb_state(workdir, rid)
        phase0 = spec.get_phase(0)
        phase5 = spec.get_phase(5)
        block0 = rt._prior_business_kb_block(st, phase0, spec)
        check("Phase 0 预防式注入非空", bool(block0), "应注入 endorsed 那条")
        check("注入标签 PRIOR_BUSINESS_KB", "##PRIOR_BUSINESS_KB##" in block0, block0)
        check("注入含业务知识原文", "下单扣库存须覆盖并发重复提交幂等" in block0, block0)
        check("注入含'参考而非硬约束'（纯软上下文）", "参考而非硬约束" in block0, block0)
        # helper phase 无关：Phase 5 同样返回该块（gating 在 _card，非 helper）
        block5 = rt._prior_business_kb_block(st, phase5, spec)
        check("business helper phase 无关（Phase 5 同样命中）",
              "##PRIOR_BUSINESS_KB##" in block5, "应不受 phase 过滤")
        # _card 仅 Phase 0 注入 PRIOR_BUSINESS_KB
        st_card = {"workdir": workdir, "req_id": rid, "depth": "heavy", "run_mode": "full"}
        card0 = rt._card(st_card, phase0, spec)
        check("_card Phase 0 含 PRIOR_BUSINESS_KB", "PRIOR_BUSINESS_KB" in card0, "Phase 0 应注入")
        card5 = rt._card(st_card, phase5, spec)
        check("_card 非 Phase 0 不含 PRIOR_BUSINESS_KB",
              "PRIOR_BUSINESS_KB" not in card5, "仅 Phase 0 注入: %s" % card5[-300:])
        # 相关性门：trigger 零重叠的 REQ → ''
        rid2 = "界面需求-20260809"
        _kb_req_file(workdir, rid2, "# %s\n\n## 界面布局\n\n按钮对齐与配色规范\n" % rid2)
        st2 = _kb_state(workdir, rid2)
        miss = rt._prior_business_kb_block(st2, phase0, spec)
        check("trigger 零重叠 → 预防式不注入", miss == "", "相关性门失效: %s" % miss)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_business_reactive_injects_on_fail():
    """endorsed business 记录 + gate_fail fail_detail 含触发词 → 反应式注入 ##RELEVANT_BUSINESS_KB##；
    fail_detail 无命中且 REQ 无命中 → ''。"""
    print("\n[kb-biz] 反应式业务知识定向（失败文本命中=强信号）")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbbiz-react-")
    try:
        rid = "并发需求-20260809"
        _kb_req_file(workdir, rid, _KB_REQ_CONCURRENCY % rid)
        fp = kb_store.fingerprint({"kind": "business", "module": "订单", "dimension": "异常处理"})
        _kb_seed_business(workdir, [_kb_biz_rec(
            fp, "异常处理", "endorsed", 1, ["并发", "幂等", "重复提交", "库存扣减", "超卖"],
            "并发超卖须覆盖幂等扣减", source_req="A", module="订单")])
        st = _kb_state(workdir, rid)
        phase5 = spec.get_phase(5)
        # 失败文本含触发词 → 注入
        hit = rt._relevant_business_kb_on_fail(st, phase5, "并发扣减导致重复提交超卖", spec)
        check("失败文本命中 → 反应式注入", bool(hit), "应注入")
        check("反应式标签 RELEVANT_BUSINESS_KB", "##RELEVANT_BUSINESS_KB##" in hit, hit)
        check("反应式含业务知识原文", "并发超卖须覆盖幂等扣减" in hit, hit)
        check("反应式含参考页脚", "参考而非硬约束" in hit, hit)
        # 失败文本不含触发词、REQ 也不含触发词 → ''
        rid2 = "界面需求-20260809"
        _kb_req_file(workdir, rid2, "# %s\n\n## 界面布局\n\n按钮对齐与配色规范\n" % rid2)
        st2 = _kb_state(workdir, rid2)
        miss = rt._relevant_business_kb_on_fail(st2, phase5, "界面按钮样式不对齐", spec)
        check("失败文本无命中 → 反应式不注入", miss == "", "应 no-op: %s" % miss)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_business_relevance_gate_filters():
    """business 记录 endorsed（信任门恒过）但 trigger 与 REQ 零重叠 → 预防+反应均不注入。
    证明：信任过 ≠ 注入；相关性门是真正过滤器（business 信任模型下尤其关键）。"""
    print("\n[kb-biz] 相关性门过滤（endorsed 信任恒过但 trigger 零重叠 → 不注入）")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbbiz-relgate-")
    try:
        rid = "界面需求-20260809"
        _kb_req_file(workdir, rid, "# %s\n\n## 界面布局\n\n按钮对齐与配色规范\n" % rid)
        fp = kb_store.fingerprint({"kind": "business", "module": "订单", "dimension": "异常处理"})
        _kb_seed_business(workdir, [_kb_biz_rec(
            fp, "异常处理", "endorsed", 5, ["并发", "幂等", "库存扣减", "超卖"],  # 信任门过(occ=5)
            "并发超卖业务知识（trigger 与本需求零重叠）", source_req="A", module="订单")])
        st = _kb_state(workdir, rid)
        phase0 = spec.get_phase(0)
        phase5 = spec.get_phase(5)
        check("endorsed+occ=5 但零重叠 → 预防式不注入",
              rt._prior_business_kb_block(st, phase0, spec) == "", "相关性门失效（预防）")
        check("endorsed+occ=5 但零重叠 → 反应式不注入",
              rt._relevant_business_kb_on_fail(st, phase5, "按钮配色不对齐", spec) == "",
              "相关性门失效（反应）")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_business_verify_id_patterns():
    """verify_kb.py 对 KB-business-<12hex> id 通过；business 文件中 KB-lesson-<12hex> 报错
    （kind 派发 pattern）；malformed business id 报错。"""
    print("\n[kb-biz] verify_kb id 模式 kind 派发（business 文件拒 lesson id）")
    import kb_store
    workdir = tempfile.mkdtemp(prefix="qamaster-kbbiz-idpat-")
    try:
        vkb = os.path.join(SKILL_SCRIPTS, "verify_kb.py")
        # (1) 合法 business id → 退出码 0
        fp_ok = kb_store.fingerprint({"kind": "business", "module": "订单", "dimension": "异常处理"})
        _kb_seed_business(workdir, [_kb_biz_rec(
            fp_ok, "异常处理", "endorsed", 1, ["并发"], "合法 business 记录",
            source_req="A", module="订单")])
        bp = _kb_business_path_of(workdir)
        proc = subprocess.run([sys.executable, vkb, bp], capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
        check("合法 business id → verify_kb 退出码 0", proc.returncode == 0,
              "rc=%d\n%s" % (proc.returncode, proc.stdout[-300:]))
        # (2) business 文件中混入 lesson id（kind=business 但 id=KB-lesson-…）→ 报错
        bad = _kb_biz_rec("KB-lesson-deadbeefdead", "异常处理", "endorsed", 1, ["并发"],
                          "kind=business 但 id 用了 lesson 前缀", source_req="A", module="订单")
        _kb_seed_business(workdir, [bad])
        proc2 = subprocess.run([sys.executable, vkb, bp], capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
        check("business 记录用 lesson id → verify_kb 报错", proc2.returncode == 1,
              "rc=%d（应非0）" % proc2.returncode)
        check("报错指向 id 不符 KB-business-",
              "不符 KB-business" in proc2.stdout, proc2.stdout[-300:])
        # (3) malformed business id → 报错
        malformed = _kb_biz_rec("KB-business-NOHEX", "异常处理", "endorsed", 1, ["并发"],
                                "malformed business id", source_req="A", module="订单")
        _kb_seed_business(workdir, [malformed])
        proc3 = subprocess.run([sys.executable, vkb, bp], capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
        check("malformed business id → verify_kb 报错", proc3.returncode == 1,
              "rc=%d（应非0）" % proc3.returncode)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_business_separate_from_lessons():
    """KB_lessons.md + KB_business.md 共存：lessons helper 不读 business 记录、
    business helper 不读 lessons 记录（kind 隔离，分文件）。"""
    print("\n[kb-biz] 与 lessons 库分离（kind 隔离，分文件互不污染）")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbbiz-sep-")
    try:
        rid = "并发需求-20260809"
        _kb_req_file(workdir, rid, _KB_REQ_CONCURRENCY % rid)
        # lessons 库：endorsed Phase-5 并发经验
        fp_lesson = kb_store.fingerprint({"kind": "lesson", "phase": "5", "dimension": "并发幂等"})
        _kb_seed(workdir, [_kb_rec(fp_lesson, 5, "并发幂等", "endorsed", 1,
                                   ["并发", "幂等", "重复提交"],
                                   "LESSONS-ONLY 经验原文", source_req="A")])
        # business 库：endorsed 业务知识（同 REQ 相关）
        fp_biz = kb_store.fingerprint({"kind": "business", "module": "订单", "dimension": "异常处理"})
        _kb_seed_business(workdir, [_kb_biz_rec(
            fp_biz, "异常处理", "endorsed", 1, ["并发", "幂等", "库存扣减"],
            "BUSINESS-ONLY 业务知识原文", source_req="A", module="订单")])
        st = _kb_state(workdir, rid)
        phase0 = spec.get_phase(0)
        phase5 = spec.get_phase(5)
        # lessons helper 只读 KB_lessons.md
        prior_lesson = rt._prior_kb_block(st, phase5, spec, kind="lesson")
        check("lessons 预防式含 LESSONS 原文", "LESSONS-ONLY" in prior_lesson, prior_lesson)
        check("lessons 预防式不含 BUSINESS 原文", "BUSINESS-ONLY" not in prior_lesson,
              "lessons helper 误读 business: %s" % prior_lesson)
        react_lesson = rt._relevant_lessons_on_fail(st, phase5, "并发重复提交超卖", spec)
        check("lessons 反应式不含 BUSINESS 原文", "BUSINESS-ONLY" not in react_lesson,
              "lessons 反应式误读 business")
        # business helper 只读 KB_business.md
        prior_biz = rt._prior_business_kb_block(st, phase0, spec)
        check("business 预防式含 BUSINESS 原文", "BUSINESS-ONLY" in prior_biz, prior_biz)
        check("business 预防式不含 LESSONS 原文", "LESSONS-ONLY" not in prior_biz,
              "business helper 误读 lessons: %s" % prior_biz)
        react_biz = rt._relevant_business_kb_on_fail(st, phase5, "并发重复提交超卖", spec)
        check("business 反应式不含 LESSONS 原文", "LESSONS-ONLY" not in react_biz,
              "business 反应式误读 lessons")
        # 文件确实分离
        check("KB_lessons.md 与 KB_business.md 分文件",
              os.path.isfile(_kb_path_of(workdir)) and os.path.isfile(_kb_business_path_of(workdir))
              and _kb_path_of(workdir) != _kb_business_path_of(workdir), "文件未分离")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# =============================================================================
# KB 专家方法论库（expert KB）· 7 项自证（v0.11.5：闭合 draft→endorse→注入 闭环）
# 约束：No-op 基线（无 KB_expert.md → PRIOR_EXPERT_KB='' + METHODOLOGY_CAPTURE 逐字节等于静态基串，
#   护 150/0）/ 信任门 endorsed-only（无 occ≥3 逃生口——错方法论污染所有未来设计）/ 适用性门
#   （phase∈applicable_phases）/ 相关性门（surface≥2 或 module 标题命中）/ 模型禁写 /
#   _pending_endorse_drafts 故意不套适用性门（endorse 是跨阶段人工动作，服务可见性而非注入）。
# =============================================================================

# v0.11.6（终极修复 RC-d）：夹具改为真实业务散文措辞（回归锚点）。
# 旧夹具预埋方法论词（"判定表穷举2^n组合/多条件组合"）→ 相关性门在测试里恒 surface≥2，
# 测试全绿却从未覆盖真实场景（业务散文 REQ 方法论词命中 0 次）——"假绿"掩盖词域错配根因。
# 现夹具镜像真实催收 REQ：全词均在 REQ 域（全部条件/条件1/2/3/既不是/也不是/大于等于），
# 方法论词（判定表/AND门/枚举）一个都不出现——正是生产环境打破注入门的措辞形态。
_KB_REQ_EXPERT = """# %s

## 调用条件

接口调用必须满足以下全部条件：
条件1：逾期天数(overdueDays)大于等于10天
条件2：产品代码(productCode)是：yyyy
条件3：资金方（payment）既不是AAA也不是BBB
"""


def test_expert_noop_preserves_baseline():
    """无 KB_expert.md → PRIOR_EXPERT_KB 返 ''；Phase14 mcap 逐字节等于静态基串（护 150/0）。"""
    print("\n[kb-expert] 无 KB_expert → PRIOR_EXPERT_KB='' + mcap=静态基串（护 150/0）")
    import qamaster_runtime as rt
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbexp-noop-")
    try:
        rid = "expert-noop-req"
        _kb_req_file(workdir, rid, _KB_REQ_EXPERT % rid)
        st = _kb_state(workdir, rid)
        phase6 = spec.get_phase(6)
        phase14 = spec.get_phase(14)
        # 注入路径 no-op
        check("无 KB_expert → PRIOR_EXPERT_KB 返空串",
              rt._prior_expert_kb_block(st, phase6, spec) == "", "应 no-op")
        # mcap 路径：Phase14 无 draft → 逐字节等于静态基串（_methodology_capture_hint 内联的 base）
        mcap = rt._methodology_capture_hint(st, phase14, spec)
        base = (
            "##METHODOLOGY_CAPTURE##（审核/许可环节方法论沉淀提醒·软上下文·非约束）\n"
            "  若用户在本轮审核/许可反馈中给出【可跨需求复用的测试设计方法论】（脱去具体业务实体后仍成立，\n"
            "  如“多条件判定须用判定表穷举 2^n 组合”“状态机须覆盖终态后非法流转拦截”），须分类路由：\n"
            "  - 可提炼为通用方法论 → kb add-expert --category <方法类目> --principle \"<脱业务原则>\" \\\n"
            "      --applicable-phases <阶段> --trigger <词>  (draft 不注入；人工 endorse 后进 ##PRIOR_EXPERT_KB##)\n"
            "  - 仅本次业务特例（离开本需求即无意义）→ kb add-lesson --phase <N> --summary \"<人类原话>\"\n"
            "  - 需求层变更（新规则/新字段/新业务约束）→ 汇入 Knowledge_<需求标识>.md，不进专家库\n"
            "  禁止以写入 Claude 个人记忆/项目记忆（~/.claude/.../memory）替代——个人记忆不注入 qamaster\n"
            "  任何阶段、对后续需求设计不可见；方法论须经 Runtime `kb` 命令落盘方可经 endorse 注入。\n"
            "  分类决策树与可提炼判定见 references/expert_kb.md。"
        )
        check("无 draft → mcap 逐字节等于静态基串（护 150/0）",
              mcap == base, "mcap 漂移:\n%s" % mcap)
        # Phase 非 14/15 → mcap 返空串
        check("Phase 6 → mcap 返空串", rt._methodology_capture_hint(st, phase6, spec) == "",
              "非 14/15 不应提示")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_expert_draft_blocked_trust_gate():
    """draft + 过适用性门 + 过相关性门 → 仍返 ''（endorsed-only 信任门阻断，无 occ≥3 逃生口）。"""
    print("\n[kb-expert] draft 过双门仍不注入（endorsed-only 信任门，无 occ≥3 逃生口）")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbexp-draft-")
    try:
        rid = "expert-draft-req"
        _kb_req_file(workdir, rid, _KB_REQ_EXPERT % rid)
        fp = kb_store.fingerprint({"kind": "expert", "category": "判定表",
                                    "principle": "N个AND门前置条件须判定表穷举2^n全行"})
        # v0.11.6: trigger 含 REQ 域实词（夹具已改业务散文）→ 相关性门过，纯测信任门
        _kb_seed_expert(workdir, [_kb_expert_rec(
            fp, "判定表", "N个AND门前置条件须判定表穷举2^n全行", [6, 8, 11],
            "draft", 1, ["全部条件", "条件1", "条件2", "判定表"],
            "判定表穷举方法论 draft", source_req="A")])
        st = _kb_state(workdir, rid)
        phase6 = spec.get_phase(6)
        block = rt._prior_expert_kb_block(st, phase6, spec)
        check("draft 过适用+相关 → PRIOR_EXPERT_KB 仍空（信任门阻断）",
              block == "", "draft 不应注入: %s" % block)
        # 即便 occ=3（draft 累积）仍不注入——expert 无 occ≥3 逃生口
        rec3 = _kb_expert_rec(
            fp, "判定表", "N个AND门前置条件须判定表穷举2^n全行", [6, 8, 11],
            "draft", 3, ["全部条件", "条件1", "条件2", "判定表"],
            "判定表穷举方法论 draft occ=3", source_req="A")
        _kb_seed_expert(workdir, [rec3])
        block3 = rt._prior_expert_kb_block(st, phase6, spec)
        check("draft occ=3 仍不注入（expert 无 occ≥3 逃生口）",
              block3 == "", "occ≥3 不应放行 expert: %s" % block3)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_expert_endorsed_injected():
    """endorsed + 过适用 + 过相关 → 注入 ##PRIOR_EXPERT_KB##；错阶段/错 REQ 不注入。"""
    print("\n[kb-expert] endorsed 过三门 → 注入 PRIOR_EXPERT_KB；错阶段/零相关不注入")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbexp-endorsed-")
    try:
        rid = "expert-endorsed-req"
        _kb_req_file(workdir, rid, _KB_REQ_EXPERT % rid)
        fp = kb_store.fingerprint({"kind": "expert", "category": "判定表",
                                    "principle": "N个AND门前置条件须判定表穷举2^n全行"})
        # v0.11.6: trigger 含 REQ 域实词（夹具已改业务散文）→ 相关性门过，纯测注入路径
        _kb_seed_expert(workdir, [_kb_expert_rec(
            fp, "判定表", "N个AND门前置条件须判定表穷举2^n全行", [6, 8, 11],
            "endorsed", 1, ["全部条件", "条件1", "条件2", "判定表"],
            "判定表穷举方法论 endorsed", source_req="A")])
        st = _kb_state(workdir, rid)
        phase6 = spec.get_phase(6)
        block = rt._prior_expert_kb_block(st, phase6, spec)
        check("endorsed 过三门 → 注入非空", bool(block), "应注入: %s" % block)
        check("注入标签 PRIOR_EXPERT_KB", "##PRIOR_EXPERT_KB##" in block, block)
        check("注入含 category=判定表", "判定表" in block, block)
        check("注入含 principle", "AND门前置条件" in block, block)
        check("注入含 适用阶段 6/8/11", "6/8/11" in block, block)
        # 错阶段（applicable_phases 不含 14）→ 不注入
        phase14 = spec.get_phase(14)
        block14 = rt._prior_expert_kb_block(st, phase14, spec)
        check("applicable_phases 不含 14 → Phase14 不注入", block14 == "",
              "适用性门失效: %s" % block14)
        # 零相关 REQ → 不注入
        rid2 = "界面需求-20260809"
        _kb_req_file(workdir, rid2, "# %s\n\n## 界面布局\n\n按钮对齐与配色规范\n" % rid2)
        st2 = _kb_state(workdir, rid2)
        miss = rt._prior_expert_kb_block(st2, phase6, spec)
        check("零相关 REQ → 不注入", miss == "", "相关性门失效: %s" % miss)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_methodology_capture_lists_pending_draft():
    """Phase14 + draft（纯方法论词 trigger + 业务散文 REQ）→ mcap 含"待 endorse draft" + id。

    v0.11.6（RC-d 死锁回归锚点）：draft 的暴露不再做 REQ 相关性预筛——
    方法论词 trigger 对业务散文 REQ surface=0，draft 仍必须出现在 mcap（给人 endorse）。
    无 draft → 逐字节等于静态基串（护 150/0）。
    """
    print("\n[kb-expert] mcap 列出待 endorse draft（死锁回归：不预筛相关性）；无 draft 逐字节 no-op")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbexp-mcap-")
    try:
        rid = "expert-mcap-req"
        _kb_req_file(workdir, rid, _KB_REQ_EXPERT % rid)
        # 先断 no-op 基串（无 draft）
        st = _kb_state(workdir, rid)
        phase14 = spec.get_phase(14)
        base = rt._methodology_capture_hint(st, phase14, spec)
        check("无 KB_expert → mcap 为静态基串", base.startswith("##METHODOLOGY_CAPTURE##"),
              "应含 mcap 头: %s" % base[:80])
        check("无 draft → mcap 不含待 endorse 子节",
              "待 endorse draft" not in base, "误列 draft: %s" % base)
        # 种一条纯方法论词 trigger draft（REQ 是业务散文，surface=0——RC-d 死锁原景）
        fp = kb_store.fingerprint({"kind": "expert", "category": "判定表",
                                    "principle": "N个AND门前置条件须判定表穷举2^n全行"})
        _kb_seed_expert(workdir, [_kb_expert_rec(
            fp, "判定表", "N个AND门前置条件须判定表穷举2^n全行", [6, 8, 11],
            "draft", 1, ["判定表", "组合", "前置条件", "AND门"],
            "判定表穷举方法论 draft", source_req="A")])
        mcap = rt._methodology_capture_hint(st, phase14, spec)
        check("死锁回归：纯方法论 trigger + 业务散文 REQ → draft 仍列入 mcap",
              "待 endorse draft" in mcap and fp in mcap, "应列 draft: %s" % mcap)
        check("mcap 含 endorse 提示", "kb endorse --kind expert --id" in mcap, mcap)
        # endorsed 记录不被列（已注入，不重复提示）
        _kb_seed_expert(workdir, [_kb_expert_rec(
            fp, "判定表", "N个AND门前置条件须判定表穷举2^n全行", [6, 8, 11],
            "endorsed", 1, ["判定表", "组合", "前置条件", "AND门"],
            "判定表穷举方法论 endorsed", source_req="A")])
        mcap2 = rt._methodology_capture_hint(st, phase14, spec)
        check("endorsed 记录不进待 endorse 子节",
              "待 endorse draft" not in mcap2, "不应列 endorsed: %s" % mcap2)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_add_expert_trigger_tokenization():
    """`kb add-expert --trigger "A|B，C、D/E"` → 落盘 trigger==["A","B","C","D","E"]（5 元素）。"""
    print("\n[kb-expert] add-expert trigger 分词鲁棒性（半角 / | , 与全角 、 ，）")
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbexp-tok-")
    try:
        rid = "expert-tok-req"
        r = run(workdir, "kb", "add-expert",
                "--category", "判定表",
                "--principle", "多条件AND门须判定表穷举2^n组合全行",
                "--applicable-phases", "6/8/11",
                "--trigger", "A|B，C、D/E",
                req_id=rid, expect_rc=0)
        check("add-expert rc=0", r.returncode == 0, "rc=%d\n%s" % (r.returncode, r.stdout[:300]))
        check("add-expert 输出 OK", "KB ADD-EXPERT: OK" in r.stdout, r.stdout[:300])
        ep = _kb_expert_path_of(workdir)
        check("KB_expert.md 被创建", os.path.isfile(ep), "应落盘")
        recs = kb_store.load_records(ep)
        check("落盘一条 expert 记录", len(recs) == 1, "recs=%d" % len(recs))
        trig = recs[0].get("trigger", [])
        check("trigger 分词为 5 元素（A|B，C、D/E）",
              trig == ["A", "B", "C", "D", "E"], "trigger=%s" % trig)
        check("applicable_phases 分词 [6,8,11]",
              recs[0].get("applicable_phases") == [6, 8, 11],
              "ap=%s" % recs[0].get("applicable_phases"))
        check("记录 kind=expert", recs[0].get("kind") == "expert", "kind=%s" % recs[0].get("kind"))
        check("id 形如 KB-expert-<12hex>",
              recs[0].get("id", "").startswith("KB-expert-") and
              len(recs[0].get("id", "")) == len("KB-expert-") + 12,
              "id=%s" % recs[0].get("id"))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_verify_kb_softwarn_pipe_trigger():
    """verify_kb.py 对 trigger 单元素含分隔符 print WARN 但 return 0（不升门禁·护 docstring 设计意图）。"""
    print("\n[kb-expert] verify_kb 软告警（trigger 畸形单元素 WARN·return 0 不升门禁）")
    workdir = tempfile.mkdtemp(prefix="qamaster-kbexp-warn-")
    try:
        vkb = os.path.join(SKILL_SCRIPTS, "verify_kb.py")
        # 构造一条 trigger 为畸形单元素含 | 的 expert 记录（直接落盘，绕过 add-expert 分词）
        bad_rec = _kb_expert_rec(
            "KB-expert-deadbeefdead", "判定表",
            "多条件AND门须判定表穷举2^n组合全行", [6, 8, 11],
            "draft", 1, ["条件组合|判定表|多条件|前置条件|AND门|OR门"],
            "trigger 畸形单元素含 |", source_req="A")
        _kb_seed_expert(workdir, [bad_rec])
        ep = _kb_expert_path_of(workdir)
        proc = subprocess.run([sys.executable, vkb, ep], capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
        check("trigger 畸形单元素 → verify_kb return 0（不升门禁）",
              proc.returncode == 0, "rc=%d（应 0，软 WARN 不升门禁）" % proc.returncode)
        check("stdout 含 WARN 提示", "[WARN]" in proc.stdout, "应软告警:\n%s" % proc.stdout)
        check("WARN 指向未分词", "未分词" in proc.stdout, "应提示未分词:\n%s" % proc.stdout)
        # 对照：正常分词 trigger 无 WARN
        good_rec = _kb_expert_rec(
            "KB-expert-cafebabecafe", "判定表",
            "多条件AND门须判定表穷举2^n组合全行", [6, 8, 11],
            "draft", 1, ["条件组合", "判定表", "多条件", "前置条件", "AND门"],
            "trigger 正常分词", source_req="A")
        _kb_seed_expert(workdir, [good_rec])
        proc2 = subprocess.run([sys.executable, vkb, ep], capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
        check("正常分词 trigger → verify_kb return 0 且无 WARN",
              proc2.returncode == 0 and "[WARN]" not in proc2.stdout,
              "正常 trigger 不应告警:\n%s" % proc2.stdout)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_kb_pending_endorse_summary():
    """expert draft N → 摘要含"N"；全 endorsed/无文件 → 返 ''（命令侧·通道B）。"""
    print("\n[kb-expert] _kb_pending_endorse_summary（通道B·expert draft 计数）")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbexp-sum-")
    try:
        # 无任何 KB 文件 → ''
        check("无 KB 文件 → 摘要返空串",
              rt._kb_pending_endorse_summary(workdir, spec) == "", "应 no-op")
        # 2 条 expert draft → 摘要含 "expert 2"
        fp1 = kb_store.fingerprint({"kind": "expert", "category": "判定表",
                                     "principle": "AND门须判定表穷举2^n全行"})
        fp2 = kb_store.fingerprint({"kind": "expert", "category": "边界值",
                                     "principle": "边界内邻接值min+1/max-1须独立用例"})
        _kb_seed_expert(workdir, [
            _kb_expert_rec(fp1, "判定表", "AND门须判定表穷举2^n全行", [6, 8, 11],
                           "draft", 1, ["判定表", "组合", "前置条件"],
                           "draft 判定表方法论", source_req="A"),
            _kb_expert_rec(fp2, "边界值", "边界内邻接值min+1/max-1须独立用例", [6, 8, 11],
                           "draft", 1, ["边界", "阈值", "min", "max"],
                           "draft 边界值方法论", source_req="A"),
        ])
        summary = rt._kb_pending_endorse_summary(workdir, spec)
        check("2 条 expert draft → 摘要非空", bool(summary), "应非空: %s" % summary)
        check("摘要含 'expert 2'", "expert 2" in summary, "应含 expert 2: %s" % summary)
        check("摘要含 endorse 提示命令", "kb endorse" in summary, summary)
        # superseded draft 不计数（三记录同落一盘，第三条被第一条废止）
        fp3 = kb_store.fingerprint({"kind": "expert", "category": "状态迁移",
                                     "principle": "状态机须覆盖终态后非法流转拦截"})
        _kb_seed_expert(workdir, [
            _kb_expert_rec(fp1, "判定表", "AND门须判定表穷举2^n全行", [6, 8, 11],
                           "draft", 1, ["判定表", "组合", "前置条件"],
                           "draft 判定表方法论", source_req="A"),
            _kb_expert_rec(fp2, "边界值", "边界内邻接值min+1/max-1须独立用例", [6, 8, 11],
                           "draft", 1, ["边界", "阈值", "min", "max"],
                           "draft 边界值方法论", source_req="A"),
            _kb_expert_rec(fp3, "状态迁移", "状态机须覆盖终态后非法流转拦截", [5, 6, 8, 11],
                           "draft", 1, ["状态机", "终态", "流转"],
                           "draft 状态迁移方法论(被废止)", source_req="A",
                           superseded_by=[fp1]),
        ])
        summary2 = rt._kb_pending_endorse_summary(workdir, spec)
        check("superseded draft 不计数 → 仍 expert 2（不含被废止的）",
              "expert 2" in summary2 and "expert 3" not in summary2,
              "应仍 expert 2（跳过 superseded）: %s" % summary2)
        # 全 endorsed → 摘要不含 expert（draft=0 → 该 kind 不进 counts）
        fp1_end = kb_store.fingerprint({"kind": "expert", "category": "判定表",
                                         "principle": "AND门须判定表穷举2^n全行-end"})
        _kb_seed_expert(workdir, [
            _kb_expert_rec(fp1_end, "判定表", "AND门须判定表穷举2^n全行-end", [6, 8, 11],
                           "endorsed", 1, ["判定表", "组合"],
                           "endorsed 判定表方法论", source_req="A"),
        ])
        summary3 = rt._kb_pending_endorse_summary(workdir, spec)
        check("全 endorsed（无 draft）→ 摘要返空串",
              summary3 == "", "应 no-op: %s" % summary3)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_expert_legacy_malformed_trigger_selfheal():
    """存量畸形单元素 trigger（["条件组合|判定表|全部条件|条件1"]）endorsed → 读取时 _split_tokens 自愈注入。

    v0.11.6（F3/RC-d）：D:/AGI/AAAA 存量数据即此形态——RC-b 只修了写入侧分词，
    旧记录落盘时已是单元素串；读取时分词后 surface≥2 可达，无需重建数据。
    """
    print("\n[kb-expert] 读取时分词自愈：legacy 畸形单元素 trigger → 注入门可命中")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbexp-selfheal-")
    try:
        rid = "expert-selfheal-req"
        _kb_req_file(workdir, rid, _KB_REQ_EXPERT % rid)
        fp = kb_store.fingerprint({"kind": "expert", "category": "组合覆盖",
                                    "principle": "多条件AND门须判定表穷举2^n全行"})
        _kb_seed_expert(workdir, [_kb_expert_rec(
            fp, "组合覆盖", "多条件AND门须判定表穷举2^n全行", [6, 8, 11],
            "endorsed", 1, ["条件组合|判定表|全部条件|条件1"],  # legacy 畸形单元素
            "2^n 组合覆盖方法论", source_req="A")])
        st = _kb_state(workdir, rid)
        block = rt._prior_expert_kb_block(st, spec.get_phase(6), spec)
        check("legacy 畸形 trigger 读取时自愈 → 注入非空", bool(block),
              "应注入（分词后 全部条件+条件1 命中 surface≥2）: %s" % block)
        check("自愈注入含 PRIOR_EXPERT_KB 标签", "##PRIOR_EXPERT_KB##" in block, block)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_expert_substring_shadow_no_overmatch():
    """子串遮蔽去重（RC-e）：无关数字阈值 REQ（仅 大于等于 一处）不再误注入；真 AND 门 REQ 仍注入。

    镜像 D:/AGI/AAAA 真实数据形态：trigger 含 大于+大于等于 子串对。修复前
    "大于等于50条" 一处双计 → surface=2 → 分页规则误注入两条组合覆盖方法论（已实锤）。
    修复后短词 大于 被 大于等于 遮蔽不计数 → surface=1 → 不注入；
    "大于50"（无 等于）仍计 大于；非子串命中词集（全部条件/条件1）不受影响。
    """
    print("\n[kb-expert] 子串遮蔽去重：数字阈值 REQ 不误注入，AND 门 REQ 仍注入")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbexp-shadow-")
    try:
        rid = "expert-shadow-req"
        _kb_req_file(workdir, rid, _KB_REQ_EXPERT % rid)
        # trigger 镜像真实存量（F2 自动补词后的形态：含 大于+大于等于 子串对）
        fp = kb_store.fingerprint({"kind": "expert", "category": "组合覆盖",
                                    "principle": "多条件AND门须判定表穷举2^n全行"})
        _kb_seed_expert(workdir, [_kb_expert_rec(
            fp, "组合覆盖", "多条件AND门须判定表穷举2^n全行", [6, 8, 11],
            "endorsed", 1, ["全部条件", "条件1", "大于", "大于等于"],
            "2^n 组合覆盖方法论", source_req="A")])
        st = _kb_state(workdir, rid)
        phase6 = spec.get_phase(6)
        block = rt._prior_expert_kb_block(st, phase6, spec)
        check("AND 门 REQ（全部条件+条件1，非子串对）→ 仍注入", bool(block),
              "应注入: %s" % block)
        # 无关分页 REQ：仅 大于等于 一处（大于 被遮蔽）→ surface=1 → 不注入
        rid2 = "分页需求-20260815"
        _kb_req_file(workdir, rid2,
                     "# %s\n\n## 分页规则\n\n查询接口返回条数大于等于50条时分页，"
                     "页大小不超过100条。\n" % rid2)
        st2 = _kb_state(workdir, rid2)
        miss = rt._prior_expert_kb_block(st2, phase6, spec)
        check("数字阈值 REQ（大于被大于等于遮蔽，surface=1）→ 不注入", miss == "",
              "误注入: %s" % miss)
        # 裸 大于（无 等于）：不被遮蔽，正常计数——但单独一处仍 surface=1 不注入
        rid3 = "限额需求-20260815"
        _kb_req_file(workdir, rid3, "# %s\n\n## 限额规则\n\n单笔金额大于100万元须复核。\n" % rid3)
        st3 = _kb_state(workdir, rid3)
        miss3 = rt._prior_expert_kb_block(st3, phase6, spec)
        check("裸大于 REQ（无第二信号）→ 仍不注入", miss3 == "", "误注入: %s" % miss3)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_add_expert_auto_req_signals():
    """add-expert --req-id 指向业务散文 REQ → 落盘 trigger 自动并入 REQ 域实词（F2/RC-d）。

    人工 trigger 只给方法论词（判定表|AND门），来源 REQ 命中的 全部条件/条件1/既不是/也不是
    自动并集——写入侧根治"词域错配"，endorsed 后注入门对业务散文可命中。
    """
    print("\n[kb-expert] add-expert 自动补 REQ 域 trigger 词（写入侧根治词域错配）")
    import kb_store
    workdir = tempfile.mkdtemp(prefix="qamaster-kbexp-sig-")
    try:
        rid = "expert-sig-req"
        _kb_req_file(workdir, rid, _KB_REQ_EXPERT % rid)
        r = run(workdir, "kb", "add-expert",
                "--category", "组合覆盖",
                "--principle", "多条件AND门须判定表穷举2^n全行",
                "--applicable-phases", "6/8/11",
                "--trigger", "判定表|AND门",
                req_id=rid, expect_rc=0)
        check("add-expert rc=0", r.returncode == 0, "rc=%d\n%s" % (r.returncode, r.stdout[:300]))
        ep = _kb_expert_path_of(workdir)
        check("KB_expert.md 被创建", os.path.isfile(ep), "应落盘")
        recs = kb_store.load_records(ep)
        check("落盘一条 expert 记录", len(recs) == 1, "recs=%d" % len(recs))
        trig = recs[0]["trigger"] if recs else []
        check("trigger 保留人工方法论词", "判定表" in trig and "AND门" in trig,
              "方法论词应保留: %s" % trig)
        check("trigger 自动并入 全部条件", "全部条件" in trig, "缺 REQ 域词: %s" % trig)
        check("trigger 自动并入 条件1", "条件1" in trig, "缺 REQ 域词: %s" % trig)
        check("trigger 自动并入 既不是/也不是", "既不是" in trig and "也不是" in trig,
              "缺 REQ 域词: %s" % trig)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_expert_ledger_numbered_cond_injection():
    """台账引入 AND 门（REQ 散文无信号）→ endorsed 判定表方法论仍注入（RC-f）。

    D:/AGI/AAAA 真实原景：REQ 正文是纯 ASR 流程散文（无 条件N/全部条件 信号词）；
    AND 门三前置条件经台账 Q32 二轮需求变更引入（措辞「需同时满足全部三条件：
    1.… 2.… 3.…，任一不满足则不调用」）。修复前相关性门只扫 REQ 正文 surface=0 →
    endorsed 方法论永不注入，最终靠 verify_cases.py gate 失败事后逼出 2³=8。
    修复后：①扫描语料扩到 REQ+台账；②「1./2./3.」编号条件归一为「条件1/2/3」
    与存量 trigger 对齐（无需重建数据）→ surface≥2 → 注入。
    """
    print("\n[kb-expert] 台账引入 AND 门（REQ 散文无信号）→ endorsed 方法论注入（RC-f）")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbexp-ledger-")
    try:
        rid = "催收-通话ASR实时转义挂机AI总结催记-md"
        # REQ 正文：纯 ASR 流程散文，无任何结构信号词
        _kb_req_file(workdir, rid,
                     "# %s\n\n坐席手工外呼拨打客户，客户接通，判断当前坐席号是否在开启ASR坐席的"
                     "字典中存在；缓存中实时记录坐席及客户的ASR内容，分角色记录；通话结束，将ASR"
                     "缓存内容请催记模型接口总结分析；两次处理完成后异步回调催收系统。\n" % rid)
        # 台账：Q32 引入 AND 门（1./2./3. 编号条件 + 全部三条件 + 任一不满足）
        w(workdir, os.path.join("case-design-out", "Clarification_Ledger_%s.md" % rid),
          "| Q32 | 业务规则 | 调用催记模型的准入条件？ | 需同时满足全部三条件："
          "1.坐席所属appcode在apollo配置了可调催记接口；"
          "2.当前坐席在开启双向ASR的appcode字典中配置了该坐席；"
          "3.当前通话坐席和客户ASR文本不能均为空。任一不满足则不调用催记模型 | 已解决 |\n")
        fp = kb_store.fingerprint({"kind": "expert", "category": "组合覆盖",
                                    "principle": "补充需求中出现多条件AND/OR门时须判定表2^n全面组合覆盖"})
        # 存量 endorsed 记录：trigger 存的是「条件1/条件2/条件3」，非台账的「1./2./3.」
        _kb_seed_expert(workdir, [_kb_expert_rec(
            fp, "组合覆盖", "补充需求中出现多条件AND/OR门时须判定表2^n全面组合覆盖", [],
            "endorsed", 2, ["AND门", "也不是", "全部条件", "判定表", "大于", "大于等于",
                            "既不是", "条件1", "条件2", "条件3",
                            "条件组合|判定表|多条件|前置条件|AND门|OR门"],
            "多条件AND/OR门须判定表2^n全面组合覆盖", source_req="manual")])
        st = _kb_state(workdir, rid)
        block = rt._prior_expert_kb_block(st, spec.get_phase(6), spec)
        check("台账 AND 门（REQ 散文）→ endorsed 判定表方法论注入", bool(block),
              "应注入（台账 全部三条件+1./2./3.→条件1/2/3 surface≥2）: %s" % block)
        check("注入含 PRIOR_EXPERT_KB 标签", "##PRIOR_EXPERT_KB##" in block, block)
        # 反例：无台账（仅 REQ 散文）→ 仍不注入（护 150/0 与既有相关性门语义）
        st2 = _kb_state(workdir, "仅REQ散文无台账-md")
        _kb_req_file(workdir, "仅REQ散文无台账-md",
                     "# 仅REQ散文无台账-md\n\n坐席外呼客户接通后启动ASR识别并写缓存，通话结束推送催记模型。\n")
        miss = rt._prior_expert_kb_block(st2, spec.get_phase(6), spec)
        check("无台账仅 REQ 散文 → 仍不注入", miss == "", "误注入: %s" % miss)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_expert_reactive_on_fail():
    """反应式专家方法论定向（RC-g）：失败文本命中→注入 ##RELEVANT_EXPERT_KB##；
    错阶段 / draft / 失败文本无命中且 REQ 无命中 → ''。

    镜像 test_kb_business_reactive_injects_on_fail 与 test_kb_reactive_failure_targeted，
    但保留 expert 特有过滤：applicable_phases 适用门 + endorsed-only 信任门（无 occ≥3 逃生口）。
    """
    print("\n[kb-expert] 反应式失败定向（RC-g）：失败文本命中→注入；错阶段/draft/无命中→''")
    import qamaster_runtime as rt
    import kb_store
    from case_design import spec as _cd_spec
    spec = _cd_spec()
    workdir = tempfile.mkdtemp(prefix="qamaster-kbexp-react-")
    try:
        rid = "expert-react-req"
        _kb_req_file(workdir, rid, _KB_REQ_EXPERT % rid)
        st = _kb_state(workdir, rid)
        phase6 = spec.get_phase(6)
        phase3 = spec.get_phase(3)
        # ① endorsed 判定表记录：trigger 与 REQ 域词重叠（全部条件/条件1/条件2）
        fp = kb_store.fingerprint({"kind": "expert", "category": "判定表",
                                    "principle": "N个AND门前置条件须判定表穷举2^n全行"})
        _kb_seed_expert(workdir, [_kb_expert_rec(
            fp, "判定表", "N个AND门前置条件须判定表穷举2^n全行", [6, 8, 11],
            "endorsed", 1, ["全部条件", "条件1", "条件2", "判定表", "AND门"],
            "判定表穷举方法论 endorsed", source_req="A")])
        # 失败文本含触发词（判定表/AND门）→ 注入
        hit = rt._relevant_expert_on_fail(st, phase6, "AND门组合未用判定表穷举2^n全行", spec)
        check("失败文本命中 → 反应式注入非空", bool(hit), "应注入: %s" % hit)
        check("反应式标签 RELEVANT_EXPERT_KB", "##RELEVANT_EXPERT_KB##" in hit, hit)
        check("反应式含方法论原则原文", "N个AND门前置条件须判定表穷举2^n全行" in hit, hit)
        check("反应式含参考页脚", "参考而非硬约束" in hit, hit)
        # ② 错阶段（phase 3 不在 applicable_phases [6,8,11]）→ 适用门阻断 → ''
        wrong_phase = rt._relevant_expert_on_fail(st, phase3, "AND门组合未用判定表穷举", spec)
        check("错阶段 → 适用门阻断返空", wrong_phase == "", "适用门失效: %s" % wrong_phase)
        # ③ draft（endorsed-only 信任门，无 occ≥3 逃生口）→ ''（失败文本命中但信任门阻断）
        fp2 = kb_store.fingerprint({"kind": "expert", "category": "状态机",
                                     "principle": "状态机须覆盖终态后非法流转拦截"})
        _kb_seed_expert(workdir, [_kb_expert_rec(
            fp2, "状态机", "状态机须覆盖终态后非法流转拦截", [6, 8, 11],
            "draft", 3, ["状态机", "非法流转", "终态"],
            "状态机方法论 draft occ=3", source_req="A")])
        draft_block = rt._relevant_expert_on_fail(st, phase6, "状态机终态非法流转未拦截", spec)
        check("draft occ=3 反应式仍不注入（endorsed-only）", draft_block == "",
              "信任门失效: %s" % draft_block)
        # ④ endorsed 但 trigger 与 REQ/失败文本零重叠 → 相关性门阻断 → ''
        #    用独立 req_id（REQ 无 全部条件/条件N 等词）避免 hit_req≥2 误放行
        rid2 = "界面需求-20260817"
        _kb_req_file(workdir, rid2, "# %s\n\n## 界面布局\n\n按钮对齐与配色规范\n" % rid2)
        st2 = _kb_state(workdir, rid2)
        fp3 = kb_store.fingerprint({"kind": "expert", "category": "状态机",
                                     "principle": "状态机须覆盖终态后非法流转拦截"})
        _kb_seed_expert(workdir, [_kb_expert_rec(
            fp3, "状态机", "状态机须覆盖终态后非法流转拦截", [6, 8, 11],
            "endorsed", 1, ["状态机", "非法流转", "终态"],
            "状态机方法论 endorsed", source_req="A")])
        miss = rt._relevant_expert_on_fail(st2, phase6, "界面按钮样式不对齐", spec)
        check("失败文本无命中且 REQ 无命中 → 不注入", miss == "", "应 no-op: %s" % miss)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
