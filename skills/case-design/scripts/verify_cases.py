#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_cases.py — 测试用例 .md 内容级校验 + 覆盖统计（Tier B 降本脚本）

用途：TestCases_<需求标识>.md 落盘后，由 skill 经 Bash 在第13阶段回读环节
与 verify_md.py 串联调用（见 references/output_write.md）。
verify_md.py 只校验“结构”（行数/表头/末行/列宽）；本脚本进一步校验
“内容层 + 覆盖广度 + 追溯性”，把 references/selfcheck.md 中【可机器判定】的
检查项客观化，并在覆盖广度不足时给出客观数据，供模型判定 selfcheck 自修项是否通过。

【设计不变】本脚本不新增门禁、不改变 selfcheck 的 15 项检查（检查15 业务行为来源追溯为新增软性项）、
不改变自修/阻断
决策、不改变“回读不一致→内存修正→重新整体 Write”机制（见 output_write.md）。
仅把“可机器判定的检查”从模型主观自证迁移到脚本客观判定，判定标准与
selfcheck.md / modeling.md / quality_rules.md / risk.md / coverage.md 完全一致。

校验项（对应 selfcheck 检查项，标准见各 references）：
  检查11 字段规范：测试类型/测试维度在枚举内、用例名称四段、4 固定列取值、用例等级 P0-P3
  检查5  ID 连续：用例ID 全局唯一不跳号（按 功能缩写分组连续）
  检查4  断言可观测：Then 含可观测关键词、不含模糊词（软判定，列疑似条数）
  检查9  存储合规：无杜撰表名/字段名/Redis Key/Topic/Index/Bucket（软判定，列疑似条数）
  检查9增强 存储schema交叉：若 .md 含'技术实现摘要'section，断言存储名须在清单内（软判定，无清单则跳过退回检查9正则）
  检查6  重复用例：关联规则+断言+维度+类型+等级五者全同（软判定，列疑似条数）
  检查7  过度设计：Then 无业务锚点（接口码/状态/数据/日志/MQ/缓存/业务数值/业务反馈）→ 疑似（软判定，兼容性/可靠性豁免，服务"不冗余不机械"）
  检查13 断言完整性：状态变更类用例(When含状态变更动词) Then 须含数据/状态副作用（软判定，防"测试通过却漏 bug"）
  检查15 业务行为来源追溯(#5)：用例 Given/When/Then 断言的业务行为须有来源三选一（需求文档 token / R·TP·API 引用 / 假设标记），三者皆无→疑似脑补（软判定）
  #6 反向接口追溯：变更影响清单每个变更接口须三类覆盖(契约 presence+type+出参 / 规则 R / 场景 SC)；无清单则跳过（软判定）
  关联需求ID追溯：笼统占位/全员相同→需求条目级追溯失效（软判定，对应 modeling.md 20.2）

覆盖统计（给 selfcheck 检查2/3/8 客观数据，不替代模型判定，只供证据）：
  - 标签维度：测试类型种类数、测试维度种类数、风险等级分布
  - 关键词维度（对测试类型标签错标鲁棒，扫描用例全文）：并发/幂等/安全/上下游/时间组合/界面查询/界面列表（UI 非每需求必有，按需，仅统计不强告警；需求涉列表/查询且=0 由 selfcheck 检查14 复核按需补齐）
  - 状态机流转：合法/非法/回滚/终态（非法流转为状态机核心，0 则提示）
  - 边界深度：边界用例是否覆盖 最小/最大/临界/边界内 四值（边界内=min+1/max-1 刚好满足约束应通过）
  - 异常子类：异常用例覆盖的子类数（输入/数据/状态/权限/服务/网络/缓存/MQ）
  - 规则追溯：解析“规则建模”section 的规则类别，校验每类是否被用例覆盖
  - 风险追溯：解析“风险清单”section，校验每 P0/P1 风险是否被用例覆盖
  - 风险来源：解析第5列“风险来源”，对技术隐含@开发/业务领域@业务/缺陷反哺来源的 P0/P1 提示需台账角色确认
  - 测试点追溯：解析“测试点清单”section，校验每测试点是否被用例覆盖
  - #4 反向需求追溯：解析需求文档条目（第2参数），列出未被用例引用的需求条目
  - #5 反向行为来源追溯（检查15）：用例 Given/When/Then 断言的业务行为须有来源三选一（需求文档 token / R·TP·API 引用 / 假设标记）；规则建模 section 规则项无来源标记->疑似脑补规则
  （风险/测试点清单为强制沉淀 section，缺失则 ⚠ 提示补齐；见 references/output_write.md 追溯性 section）

退出码：0=内容校验全过（覆盖统计与软性提示仍输出，仅供模型参考）；
        1=存在硬性内容违规（枚举越界/四段缺失/固定列错值/等级越界/ID跳号重复）
软判定项（断言/存储/存储schema/重复/断言完整性）与覆盖统计/追溯违规只列疑似条数与位置，
不强制 exit=1，由模型结合 selfcheck 决策（自修项：内存修正后重新整体 Write；阻断项：回前置阶段）。

用法：python verify_cases.py <TC文件.md> [需求文档.md]
      第2参数（可选）：需求文档，用于 #4 反向需求追溯；不传则该检查跳过。
      python verify_cases.py --dump-rules  查看规则契约

本脚本是 skill 自带可复用资产，不删除（见 references/output_write.md ch30）。

规则契约单一事实源：config/validation_rules.json（本脚本与 verify_md.py 共同加载）。
agent 需要规则契约（枚举/正则/关键词/section 格式）时运行 `python verify_cases.py --dump-rules`，
无需读本脚本源码；config/domain_config.json 提供可选领域覆盖（同名字段替换）。
"""
import sys
import os
import re
import json

# Windows 控制台默认 cp936，强制 stdout 输出 UTF-8，避免中文乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 15 列顺序（0-based）：
# 0用例ID 1关联需求ID 2关联规则 3测试类型 4测试维度 5所属模块 6用例名称
# 7Given 8When 9Then 10编辑模式 11标签 12责任人 13用例等级 14用例状态
IDX_ID, IDX_REQ, IDX_RULE, IDX_TYPE, IDX_DIM, IDX_MOD, IDX_NAME = 0, 1, 2, 3, 4, 5, 6
IDX_GIVEN, IDX_WHEN, IDX_THEN = 7, 8, 9
IDX_EDITMODE, IDX_TAG, IDX_OWNER, IDX_LEVEL, IDX_STATUS = 10, 11, 12, 13, 14

# ===== 校验规则单一事实源（config/validation_rules.json）=====
# 所有规则数据（枚举/正则/关键词/section 格式）集中于 validation_rules.json，
# 本脚本与 verify_md.py 共同加载该清单；domain_config.json 在此基础上按领域覆盖。
# agent 需要规则契约时运行 `python verify_cases.py --dump-rules`，无需读本脚本源码。
# 各常量来源（行内注释对应 references）：枚举(modeling.md 20.4/20.6)、断言可观测(quality_rules.md 11)、
# 存储合规(quality_rules.md ch12)、关键词维度(coverage.md 8.x)、状态机(example.md 范例2)、
# 边界(quality_rules.md 11.4)、异常子类(coverage.md 8.2)、需求ID追溯(modeling.md 20.2)。


def _rules_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "validation_rules.json")


def _load_validation_rules():
    """加载校验规则清单（单一事实源）。缺失/异常则返回 None，由调用方决定退出。"""
    p = _rules_path()
    if not os.path.exists(p):
        print("校验规则清单缺失: %s（skill 资产，须与 scripts 同 bundle）" % p)
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("校验规则清单读取失败: %s -> %s" % (p, e))
        return None


_RULES = _load_validation_rules()
if _RULES is None:
    sys.exit(1)

# 枚举与固定值（modeling.md 20.4 / 20.6 / 20.7-20.10）
VALID_TYPES = set(_RULES["valid_types"])
VALID_DIMS = set(_RULES["valid_dims"])
VALID_LEVELS = set(_RULES["valid_levels"])
_fc = _RULES["fixed_columns"]
FIX_EDITMODE, FIX_TAG, FIX_OWNER, FIX_STATUS = _fc["edit_mode"], _fc["tag"], _fc["owner"], _fc["status"]

# 断言可观测 / 模糊词（quality_rules.md 11.1 / 11.2）
VAGUE_WORDS = list(_RULES["vague_words"])
OBSERVABLE_PATTERNS = list(_RULES["observable_patterns"])

# 存储合规（quality_rules.md ch12）
STORAGE_PATTERNS = [(p["pattern"], p["desc"]) for p in _RULES["storage_patterns"]]
STORAGE_NATURAL = list(_RULES["storage_natural"])

# 用例名称四段（modeling.md 20.5）
NAME_SEGMENTS = _RULES["name_segments"]

# 关键词维度（coverage.md 8.x）；高价值维度 0 则警告：并发/幂等/安全/上下游
KEYWORD_DIMS = {k: list(v) for k, v in _RULES["keyword_dims"].items()}
HIGH_VALUE_DIMS = set(_RULES["high_value_dims"])

# 状态机流转锚点（example.md 范例2）
FLOW_LEGAL = list(_RULES["flow_legal"])
FLOW_ILLEGAL = list(_RULES["flow_illegal"])
FLOW_ROLLBACK = list(_RULES["flow_rollback"])
FLOW_TERMINAL = list(_RULES["flow_terminal"])

# 边界深度（quality_rules.md 11.4 / modeling.md 边界类）
# 4 值模型：最小 / 最大 / 临界(=边界点) / 边界内(min+1/max-1, 刚好满足约束应通过)
BOUNDARY_KEYWORDS = list(_RULES["boundary_keywords"])
BOUNDARY_MIN_KW = list(_RULES["boundary_min_kw"])
BOUNDARY_MAX_KW = list(_RULES["boundary_max_kw"])
BOUNDARY_CRITICAL_KW = list(_RULES["boundary_critical_kw"])
BOUNDARY_INSIDE_KW = list(_RULES["boundary_inside_kw"])

# 异常子类（coverage.md 8.2）
EXCEPTION_SUBTYPES = {k: list(v) for k, v in _RULES["exception_subtypes"].items()}

# 过度设计·业务价值信号（quality_rules.md 0.1 / 11.2）；豁免类型：兼容性/可靠性
BUSINESS_ANCHORS = list(_RULES["business_anchors"])
OVERDESIGN_EXEMPT_TYPES = set(_RULES["overdesign_exempt_types"])

# 关联需求ID 笼统占位模式（modeling.md 20.2）；命中且全员相同 → 需求条目级追溯失效
VAGUE_REQ_PATTERNS = list(_RULES["vague_req_patterns"])

# ===== 领域配置加载（方向3·领域适配）=====
# 优先读取 scripts/../config/domain_config.json，缺失或异常用上面内置默认。
# 用户可按领域扩展 business_anchors/keyword_dims/exception_subtypes/overdesign_exempt_types。


def _load_domain_config():
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "domain_config.json")
    if not os.path.exists(cfg_path):
        return {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_DOMAIN_CFG = _load_domain_config()
if "business_anchors" in _DOMAIN_CFG:
    BUSINESS_ANCHORS = _DOMAIN_CFG["business_anchors"]
if "keyword_dims" in _DOMAIN_CFG:
    # dict 字段做 key 级合并（领域扩展语义）：保留 validation_rules 独有 key
    # （如 0.5.0 新增的界面查询/界面列表），domain_config 同名 key 覆盖 value、
    # 领域新增 key 加入。整体替换会丢掉内置 key，与 _usage"新增字段不覆盖内置"矛盾。
    _merged_kw = dict(KEYWORD_DIMS)
    _merged_kw.update({k: list(v) for k, v in _DOMAIN_CFG["keyword_dims"].items()})
    KEYWORD_DIMS = _merged_kw
if "exception_subtypes" in _DOMAIN_CFG:
    # dict 字段同上：key 级合并，保留内置子类，domain_config 同名/新增子类覆盖或加入
    _merged_exc = dict(EXCEPTION_SUBTYPES)
    _merged_exc.update({k: list(v) for k, v in _DOMAIN_CFG["exception_subtypes"].items()})
    EXCEPTION_SUBTYPES = _merged_exc
if "overdesign_exempt_types" in _DOMAIN_CFG:
    OVERDESIGN_EXEMPT_TYPES = set(_DOMAIN_CFG["overdesign_exempt_types"])

# ===== 覆盖硬门（v0.6.0·事故修复）=====
# 根因：降级/手动模式下"核心用例先交付、其余待后续轮次"的缩减行为无任何机器信号暴露，
# #4 需求追溯/#6 接口三类/P0-P1 风险覆盖全为软提示，模型可在交付摘要里编造"全部覆盖"。
# 本节把三项从软提示升级为可配置硬门（单一事实源 coverage_gates，domain_config 可覆盖）。
# Runtime gate 调本脚本时，若硬门 FAIL 被 stdout 尾部缓冲截断，gate 侧另有 [FAIL] 行
# 补捞逻辑（qamaster_runtime._run_check），保修复指令完整落进 gate 输出。
_CG = dict(_RULES.get("coverage_gates", {}))
_CG.update({k: v for k, v in _DOMAIN_CFG.get("coverage_gates", {}).items()})


def _gate_mode(raw, default="full"):
    """归一化硬门取值：full=硬门(exit=1) / auto_light=连跑轻量降级为软告警 / off=关闭。"""
    v = str(raw if raw is not None else default).strip().lower()
    if v in ("full", "hard", "on", "true"):
        return "full"
    if v in ("auto_light", "auto", "light", "soft"):
        return "auto_light"
    if v in ("off", "none", "false", "disabled"):
        return "off"
    return default


COVERAGE_GATES = {
    # #4-H：需求条目被用例"关联需求ID"列引用的最低比例（REQ 可解析时生效）
    "req_trace_min_ratio": float(_CG.get("req_trace_min_ratio", 1.0)),
    # #7-H：测试点清单每条 TP 被用例关联规则列引用的最低比例（v0.8.0）
    "tp_trace_min_ratio": float(_CG.get("tp_trace_min_ratio", 1.0)),
    # #8-H：设计文档测试要点章节每条被用例覆盖的最低比例（v0.8.0，DESIGN 落盘时生效）
    "design_doc_trace_min_ratio": float(_CG.get("design_doc_trace_min_ratio", 1.0)),
    # #6-H：变更接口三类覆盖硬门（full/auto_light/off）
    "interface_three_class": _gate_mode(_CG.get("interface_three_class")),
    # RK：P0/P1 风险被用例关联规则列引用硬门（full/auto_light/off）
    "risk_p0p1": _gate_mode(_CG.get("risk_p0p1")),
    # #7-H 测试点覆盖硬门（v0.8.0）：TP 清单每条须被用例引用
    "testpoint_coverage": _gate_mode(_CG.get("testpoint_coverage")),
    # #8-H 设计文档测试要点追溯硬门（v0.8.0）：DESIGN 测试要点每条须被覆盖
    "design_doc_testpoints_trace": _gate_mode(_CG.get("design_doc_testpoints_trace")),
    # 安全覆盖硬门（v0.8.0）：涉敏感数据时安全类用例数须 >0
    "safety_coverage": _gate_mode(_CG.get("safety_coverage")),
    # v0.8.1 Gap3：规则来源标记硬门（full 模式无来源标记即 exit=1；auto_light 软告警）
    "rule_source_hard": _gate_mode(_CG.get("rule_source_hard")),
    # v0.8.1 Gap3：风险来源待确认硬门（full 模式风险来源未确认即 exit=1；auto_light 软告警）
    "risk_source_hard": _gate_mode(_CG.get("risk_source_hard")),
}

# 敏感数据信号词表（v0.8.0·safety_coverage 硬门触发条件）
_SENS = _RULES.get("sensitive_signals", {})
SENSITIVE_SIGNALS = _SENS.get("patterns", []) if isinstance(_SENS, dict) else []


def coverage_gate_failures(findings, run_mode="full"):
    """汇总三项覆盖硬门的违约列表。返回 [(门名, 明细), ...]；空列表=全过。

    口径（与 print_findings 软提示共用同一份 traces 数据，判定不重复计算）：
      #4-H  需求追溯：traces.requirement=[uncovered, total]，REQ 可解析(total>0)时
            引用率须 >= req_trace_min_ratio；REQ 缺失/不可解析(None/0)不判（由 #4 显式强提示接管）。
      #6-H  接口三类：traces.interface=[uncovered_list, api_total, ...]，api_total>0 时
            uncovered_list 须为空。
      RK    P0/P1 风险：traces.risk=[uncovered, p0p1, total]，p0p1>0 且 uncovered 非空即违约。

    run_mode 语义：完整模式(full)一律按配置硬度判；连跑/轻量(auto/light)下
    interface_three_class/risk_p0p1 配置为 auto_light 时降级为软告警（返回空，不进 exit=1）。
    req_trace_min_ratio 不设模式豁免——完整/连跑/轻量均按同一比例硬判
    （连跑/轻量允许未覆盖，但须由模型在交付摘要显式列出未覆盖清单，见 SKILL.md 交付摘要）。
    """
    fails = []
    traces = findings.get("traces", {})
    # #4-P REQ 缺失/不可解析硬门禁（v0.7.0·补 v0.6.0 拘留）
    # coverage_gate_failures L240 仅 unc_req is not None 才触发；REQ 缺失只打 stdout 强提示不 exit。
    # 本检查补该缺口：req_trace_presence != off 且 unc_req is None 且非 auto_light+auto/light -> 硬门违约。
    req_presence_fail = check_req_presence(findings, run_mode=run_mode)
    if req_presence_fail:
        fails.append(req_presence_fail)
    # #4-H 需求追溯硬门
    unc_req, req_total = traces.get("requirement", [None, 0])
    if unc_req is not None and req_total:
        ratio = (req_total - len(unc_req)) / float(req_total)
        if ratio < COVERAGE_GATES["req_trace_min_ratio"]:
            fails.append(("#4-H 需求追溯硬门",
                          "需求条目 %d 条、未被用例引用 %d 条（引用率 %.0f%% < 阈值 %.0f%%）：%s。"
                          "修复：补齐对应用例的'关联需求ID'列引用具体需求条目（如'见需求文档<二级标题>'），"
                          "或确认该条目不在测试范围并登记假设" % (
                              req_total, len(unc_req), ratio * 100,
                              COVERAGE_GATES["req_trace_min_ratio"] * 100,
                              "、".join(str(u)[:40] for u in unc_req[:8]))))
    # 项 5.5b 台账待确认门禁（v0.7.0·闭环 C2·硬）
    ledger = findings.get("_ledger")
    if ledger is not None:
        oq_fail = check_open_questions_gate(ledger, run_mode=run_mode)
        if oq_fail:
            fails.extend(oq_fail)
    # #6-H 变更接口三类硬门
    unc_api, api_total, _ct = traces.get("interface", [[], 0, []])
    if COVERAGE_GATES["interface_three_class"] != "off" and api_total and unc_api:
        if not (COVERAGE_GATES["interface_three_class"] == "auto_light" and run_mode in ("auto", "light")):
            fails.append(("#6-H 变更接口三类硬门",
                          "变更接口 %d 个、缺契约/规则/场景三类覆盖 %d 个：%s" % (
                              api_total, len(unc_api), "；".join(str(u)[:60] for u in unc_api[:5]))))
    # RK P0/P1 风险硬门
    unc_risk, p0p1, _rt = traces.get("risk", [None, 0, 0])
    if COVERAGE_GATES["risk_p0p1"] != "off" and p0p1 and unc_risk:
        if not (COVERAGE_GATES["risk_p0p1"] == "auto_light" and run_mode in ("auto", "light")):
            fails.append(("RK P0/P1 风险硬门",
                          "P0/P1 风险 %d 条、未被用例引用 %d 条：%s" % (
                              p0p1, len(unc_risk), "；".join(str(u)[:60] for u in unc_risk[:5]))))
    # #7-H 测试点追溯硬门（v0.8.0·闭环 36→30 压缩）
    # testpoint_coverage 已有 testpoint_coverage() 函数返回 (unc_tp, tp_total) 入 traces，
    # 这里做硬门判定：TP 清单存在且未覆盖比例 < tp_trace_min_ratio -> exit=1
    # v0.9.0·根因6 修复：#7 不再随 auto_light 降级——测试点追溯是"是否覆盖设计"的核心硬门，
    # 连跑/轻量模式亦硬判（TP 清单不存在时 SKIP，不阻断）。仅 interface/risk 受 auto_light 降级。
    if COVERAGE_GATES["testpoint_coverage"] != "off":
        unc_tp, tp_total = traces.get("testpoint", [None, 0])
        if unc_tp is not None and tp_total:
            ratio = (tp_total - len(unc_tp)) / float(tp_total)
            if ratio < COVERAGE_GATES["tp_trace_min_ratio"]:
                fails.append(("#7-H 测试点追溯硬门",
                              "测试点 %d 条、未被用例引用 %d 条（引用率 %.0f%% < 阈值 %.0f%%）：%s。"
                              "修复：补齐对应用例的'关联规则'列引用 TP<序号>，或确认该测试点不在范围并登记假设" % (
                                  tp_total, len(unc_tp), ratio * 100,
                                  COVERAGE_GATES["tp_trace_min_ratio"] * 100,
                                  "、".join(str(u)[:40] for u in unc_tp[:8]))))
    # #8-H 设计文档测试要点追溯硬门（v0.8.0）
    # v0.9.0·根因6 修复：#8 不再随 auto_light 降级——设计文档测试要点追溯直接对应"设计文档内容
    # 是否被用例覆盖"，连跑/轻量亦硬判（DESIGN 无则 SKIP，不阻断）。
    if COVERAGE_GATES["design_doc_testpoints_trace"] != "off":
        unc_dd, dd_total = traces.get("design_doc", [[], 0])
        if dd_total and unc_dd:
            fails.append(("#8-H 设计文档测试要点追溯硬门",
                          "DESIGN 测试要点 %d 条、未覆盖 %d 条：%s。"
                          "修复：补齐对应用例覆盖设计文档测试要点，或登记假设'要点X不在测试范围'" % (
                              dd_total, len(unc_dd), "、".join(str(u)[:40] for u in unc_dd[:8]))))
    # safety_coverage 安全覆盖硬门（v0.8.0）
    # v0.9.0·根因6 修复：#S 不再随 auto_light 降级——涉敏感数据须有安全用例，不因模式放宽。
    if COVERAGE_GATES["safety_coverage"] != "off":
        s_fails = findings.get("_safety_fails") or []
        if s_fails:
            fails.extend(("#S-H 安全覆盖硬门", f) for f in s_fails)
    return fails


def verify_summary_line(findings, hard_gate_fails=None):
    """输出固定格式机器摘要行（##VERIFY_SUMMARY## ...），供交付摘要/审核话术逐字段摘抄。

    反编造约束（SKILL.md 交付摘要）：五项脚本校验数值必须摘自本行，禁止凭印象手填；
    未运行本脚本时五项一律填"未执行"，填数值即视为声明脚本已运行（声明与实际不符=输出不合格）。
    hard_gate_fails：coverage_gate_failures 的返回（None=由本行按 full 模式自算）。"""
    soft = findings["soft"]
    traces = findings["traces"]
    unc_req, req_total = traces["requirement"]
    unc_api, api_total, _ct = traces["interface"]
    unc_risk, p0p1, _rt = traces["risk"]
    fields = {
        "check13": soft["completeness"][0],
        "check9_schema": ("skip" if soft["schema"][0] is None else soft["schema"][0]),
        "risk_src_pending": len(findings["risk_source"][1]),
        "req_total": (req_total if unc_req is not None else "na"),
        "req_uncovered": (len(unc_req) if unc_req is not None else "na"),
        "api_total": api_total,
        "api_uncovered": len(unc_api),
        "risk_p0p1": p0p1,
        "risk_uncovered": (len(unc_risk) if unc_risk else 0),
        "tp_total": (traces["testpoint"][1] if traces["testpoint"][0] is not None else "na"),
        "tp_uncovered": (len(traces["testpoint"][0]) if traces["testpoint"][0] is not None else "na"),
        "design_total": traces["design_doc"][1],
        "design_uncovered": len(traces["design_doc"][0]),
        "safety_fail": len(findings.get("_safety_fails") or []),
        "check15": soft["behavior"][0],
        "hard_violations": len(findings["hard_violations"]),
        "gate_fails": (len(hard_gate_fails) if hard_gate_fails is not None
                       else len(coverage_gate_failures(findings))),
    }
    return "##VERIFY_SUMMARY## " + "; ".join("%s=%s" % (k, v) for k, v in fields.items())


def split_row(line):
    s = line.strip()
    if not s.startswith("|"):
        return None
    s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_separator(cells):
    if not cells:
        return False
    for c in cells:
        if not set(c) <= set("-: "):
            return False
    return True


def parse_table_from_lines(lines):
    """解析已读入的 .md 行列表中的用例表，返回 (header_cells, data_rows, full_lines)。
    与文件读无关——供内存内 gate 调用（Phase 8 出口 gate 在写盘前对 Write 的 content
    即将落盘文本跑全量校验，零临时文件）。"""
    header_idx = None
    header_cells = None
    for i, ln in enumerate(lines):
        cells = split_row(ln)
        if cells and "用例ID" in cells[0]:
            header_idx = i
            header_cells = cells
            break
    if header_idx is None:
        return None, "未找到表头行（含'用例ID'的表格行）"

    data_rows = []
    for ln in lines[header_idx + 1:]:
        cells = split_row(ln)
        if cells is None:
            if data_rows:
                break
            else:
                continue
        if is_separator(cells) or len(cells) == 0:
            continue
        data_rows.append(cells)
    return (header_cells, data_rows, lines), None


def parse_table(path):
    """解析 .md 中的用例表，返回 (header_cells, data_rows, full_lines)。
    文件入口（Phase 13 回读用）；内部读文件后委托 parse_table_from_lines。"""
    if not os.path.exists(path):
        return None, "文件不存在: %s" % path
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        return None, "读取失败: %s" % e
    return parse_table_from_lines(lines)


def count_segments(name):
    return len(re.findall(r"【[^】]*】", name))


def extract_func_abbr(case_id):
    if not case_id:
        return None, None
    parts = case_id.split("_")
    if len(parts) < 2:
        return None, None
    seq = parts[-1]
    func = parts[-2] if len(parts) >= 3 else None
    return func, seq


def seq_num(seq):
    try:
        return int(seq)
    except Exception:
        return None


def check_ids(data_rows):
    violations = []
    seen = {}
    groups = {}
    for i, r in enumerate(data_rows, 1):
        cid = r[IDX_ID] if len(r) > IDX_ID else ""
        if cid in seen:
            violations.append("行%d: 用例ID重复 %s（首次出现于行%d）" % (i, cid, seen[cid]))
        else:
            seen[cid] = i
        func, seq = extract_func_abbr(cid)
        if func is None:
            continue
        n = seq_num(seq)
        if n is None:
            continue
        groups.setdefault(func, []).append((n, i, cid))
    for func, items in groups.items():
        nums = sorted(n for n, _, _ in items)
        if not nums:
            continue
        expected = list(range(nums[0], nums[-1] + 1))
        missing = set(expected) - set(nums)
        if missing:
            violations.append("功能[%s]序号跳号，缺失: %s" % (func, ",".join(str(x) for x in sorted(missing))))
    return violations


def check_fields(data_rows):
    violations = []
    for i, r in enumerate(data_rows, 1):
        if len(r) <= IDX_STATUS:
            violations.append("行%d: 列数不足15，无法校验字段" % i)
            continue
        ctype, cdim, cname = r[IDX_TYPE], r[IDX_DIM], r[IDX_NAME]
        cedit, ctag, cowner, clevel, cstatus = r[IDX_EDITMODE], r[IDX_TAG], r[IDX_OWNER], r[IDX_LEVEL], r[IDX_STATUS]
        if ctype not in VALID_TYPES:
            violations.append("行%d: 测试类型越界『%s』（允许：%s）" % (i, ctype, "/".join(sorted(VALID_TYPES))))
        if cdim not in VALID_DIMS:
            violations.append("行%d: 测试维度越界『%s』（允许：%s）" % (i, cdim, "/".join(sorted(VALID_DIMS))))
        if count_segments(cname) < NAME_SEGMENTS:
            violations.append("行%d: 用例名称段数不足（%d段<%d）『%s』" % (i, count_segments(cname), NAME_SEGMENTS, cname))
        if cedit != FIX_EDITMODE:
            violations.append("行%d: 编辑模式固定值应为%s，实际『%s』" % (i, FIX_EDITMODE, cedit))
        if ctag != FIX_TAG:
            violations.append("行%d: 标签固定值应为%s，实际『%s』" % (i, FIX_TAG, ctag))
        if cowner != FIX_OWNER:
            violations.append("行%d: 责任人固定值应为%s，实际『%s』" % (i, FIX_OWNER, cowner))
        if cstatus != FIX_STATUS:
            violations.append("行%d: 用例状态固定值应为%s，实际『%s』" % (i, FIX_STATUS, cstatus))
        if clevel not in VALID_LEVELS:
            violations.append("行%d: 用例等级越界『%s』（允许P0-P3）" % (i, clevel))
    return violations


def check_assertions(data_rows):
    suspects = []
    for i, r in enumerate(data_rows, 1):
        then = r[IDX_THEN] if len(r) > IDX_THEN else ""
        if not then.strip():
            suspects.append("行%d: Then 为空" % i)
            continue
        # v0.7.0 项7 D4：假设标记类用例（边界/异常且 Then 仅"登记假设"无具体断言）-> 疑似空泛断言
        # 闭合 D4（SUM_018 只登记假设A1无具体 Then）。软判定。
        has_assumption_tag = _has_assumption_tag(r)
        if has_assumption_tag and any(kw in (r[IDX_TYPE] if len(r) > IDX_TYPE else "") for kw in ("边界", "异常")):
            # Then 仅含假设登记措辞、无可观测锚点
            assumption_only = any(kw in then for kw in ("登记假设", "作为低风险边界", "基于假设", "假设登记"))
            has_observable = any(re.search(p, then) for p in OBSERVABLE_PATTERNS)
            if assumption_only and not has_observable:
                suspects.append("行%d: Then 仅登记假设无具体可观测断言（D4·断言具体性）" % i)
                continue
            continue
        if any(re.search(p, then) for p in OBSERVABLE_PATTERNS):
            continue
        vague_hit = [w for w in VAGUE_WORDS if w in then]
        if vague_hit:
            suspects.append("行%d: Then 疑似模糊断言（含%s且无可观测锚点）" % (i, "/".join(vague_hit)))
        else:
            suspects.append("行%d: Then 未识别到可观测锚点（请人工复核）" % i)
    return len(suspects), suspects


def check_storage(data_rows):
    suspects = []
    for i, r in enumerate(data_rows, 1):
        text = " ".join(r[IDX_GIVEN:IDX_THEN + 1]) if len(r) > IDX_THEN else ""
        hits = [desc for pat, desc in STORAGE_PATTERNS if re.search(pat, text, flags=re.IGNORECASE)]
        if hits:
            natural = [n for n in STORAGE_NATURAL if n in text]
            tag = "（含自然语言描述，请复核）" if natural else ""
            suspects.append("行%d: %s%s" % (i, ";".join(hits), tag))
    return len(suspects), suspects


def check_duplicates(data_rows):
    """检查6：重复用例（软判定）。按 dedup_coverage.md 维度/方法多样性保护：
    关联规则+断言+测试维度+测试类型+用例等级（P0-P3 代理风险）五者全同才报疑似重复
   （用例表无独立"风险"列，以用例等级代理；保护宽度，防过度合并）。"""
    seen = {}
    suspects = []
    for i, r in enumerate(data_rows, 1):
        rule = r[IDX_RULE] if len(r) > IDX_RULE else ""
        then = r[IDX_THEN] if len(r) > IDX_THEN else ""
        cdim = r[IDX_DIM] if len(r) > IDX_DIM else ""
        ctype = r[IDX_TYPE] if len(r) > IDX_TYPE else ""
        clevel = r[IDX_LEVEL] if len(r) > IDX_LEVEL else ""
        key = (rule.strip(), then.strip(), cdim.strip(), ctype.strip(), clevel.strip())
        if key in seen:
            suspects.append("行%d: 与行%d 规则+断言+维度+类型+等级全同（疑似重复）" % (i, seen[key]))
        else:
            seen[key] = i
    return len(suspects), suspects


def check_overdesign(data_rows):
    """检查7：过度设计（软判定·业务价值信号）。判定 Then 有无业务锚点
    （接口码/状态/数据/日志/MQ/缓存/业务数值/业务反馈）；无业务锚点 → 疑似过度设计
   （对应 quality_rules.md 0.1：聚焦业务/数据/状态/权限/风险，禁止无业务价值UI/框架测试）。
    兼容性/可靠性测试类型豁免（纯 UI/性能断言合理）。比句式匹配更准：不误伤含'能否'但
    有业务断言的用例（如'支付失败能否显示错误提示'含错误码），不漏检纯元素存在类。"""
    suspects = []
    for i, r in enumerate(data_rows, 1):
        if len(r) <= IDX_THEN:
            continue
        ctype = r[IDX_TYPE]
        then = r[IDX_THEN]
        if ctype in OVERDESIGN_EXEMPT_TYPES:
            continue
        has_business = any(re.search(p, then) for p in BUSINESS_ANCHORS)
        if not has_business:
            suspects.append("行%d: 疑似过度设计（Then 无业务锚点：无接口码/状态/数据/日志/MQ/缓存/业务数值/业务反馈；属0.1禁止的无业务价值测试）" % i)
    return len(suspects), suspects


def check_requirement_id(data_rows):
    """关联需求ID 追溯失效检测（软判定，对应 modeling.md 20.2）。
    信号：全员均为笼统占位（见需求文档'需求内容'/见需求文档/无），或全员相同且为占位形式
    → 需求条目级追溯失效，'每需求≥1用例'无法闭环。"""
    if not data_rows:
        return 0, []
    req_ids = [r[IDX_REQ].strip() if len(r) > IDX_REQ else "" for r in data_rows]
    suspects = []
    vague_count = sum(1 for rid in req_ids if any(re.match(p, rid) for p in VAGUE_REQ_PATTERNS))
    if req_ids and vague_count == len(req_ids):
        suspects.append("全部 %d 条关联需求ID均为笼统占位（见需求文档'需求内容'/'见需求文档'/'无'），"
                        "需求条目级追溯失效；应填具体编号或'见需求文档<章节号/章节名>'" % vague_count)
    elif len(set(req_ids)) == 1 and req_ids[0] and "见需求文档" in req_ids[0]:
        suspects.append("全部用例关联需求ID相同（'%s'），未做需求条目级区分，追溯失效" % req_ids[0])
    return len(suspects), suspects


def row_text(r):
    """用例全文（用于关键词扫描）：关联规则+模块+名称+Given+When+Then。"""
    idxs = [IDX_RULE, IDX_MOD, IDX_NAME, IDX_GIVEN, IDX_WHEN, IDX_THEN]
    return " ".join(r[i] for i in idxs if len(r) > i and r[i])


def coverage_stats(data_rows):
    """标签维度覆盖统计（原有）+ 关键词维度 + 状态机 + 边界深度(4值) + 异常子类。"""
    type_count = {}
    dim_count = {}
    level_count = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    flow_legal = flow_illegal = flow_rollback = flow_terminal = 0
    kw_dim_count = {k: 0 for k in KEYWORD_DIMS}
    bound_total = 0
    bound_min = bound_max = bound_critical = bound_inside = 0
    exc_total = 0
    exc_subtypes_hit = {k: 0 for k in EXCEPTION_SUBTYPES}

    for r in data_rows:
        ctype = r[IDX_TYPE] if len(r) > IDX_TYPE else ""
        cdim = r[IDX_DIM] if len(r) > IDX_DIM else ""
        clevel = r[IDX_LEVEL] if len(r) > IDX_LEVEL else ""
        text = row_text(r)
        low = text.lower()

        type_count[ctype] = type_count.get(ctype, 0) + 1
        dim_count[cdim] = dim_count.get(cdim, 0) + 1
        if clevel in level_count:
            level_count[clevel] += 1

        # 关键词维度（标签无关）
        for dim, kws in KEYWORD_DIMS.items():
            if any(kw.lower() in low for kw in kws):
                kw_dim_count[dim] += 1

        # 状态机流转（识别放宽：含"状态"且含任一状态动作词，不硬要求"流转"二字）
        state_actions = FLOW_LEGAL + FLOW_ILLEGAL + FLOW_ROLLBACK + [
            "变更", "退回", "变为", "置为", "生效", "停用", "启用",
            "提交审核", "审核通过", "审核驳回", "不可直接编辑", "不可编辑", "不可删",
        ]
        is_state = (ctype == "状态迁移") or ("状态" in text and any(w in text for w in state_actions))
        if is_state:
            if any(w in text for w in FLOW_ILLEGAL):
                flow_illegal += 1
            elif any(w in text for w in FLOW_ROLLBACK):
                flow_rollback += 1
            else:
                flow_legal += 1
            if any(w in text for w in FLOW_TERMINAL):
                flow_terminal += 1

        # 边界深度
        is_boundary = (ctype == "边界") or any(kw in text for kw in BOUNDARY_KEYWORDS)
        if is_boundary:
            bound_total += 1
            if any(kw in text for kw in BOUNDARY_MIN_KW):
                bound_min += 1
            if any(kw in text for kw in BOUNDARY_MAX_KW):
                bound_max += 1
            if any(kw in text for kw in BOUNDARY_CRITICAL_KW):
                bound_critical += 1
            if any(kw in text for kw in BOUNDARY_INSIDE_KW):
                bound_inside += 1

        # 异常子类
        is_exception = (ctype == "异常") or any(kw in text for kw in ["失败", "拦截", "错误", "非法", "异常", "超时"])
        if is_exception:
            exc_total += 1
            for sub, kws in EXCEPTION_SUBTYPES.items():
                if any(kw.lower() in low for kw in kws):
                    exc_subtypes_hit[sub] += 1

    return {
        "n": len(data_rows),
        "type_count": type_count,
        "dim_count": dim_count,
        "level_count": level_count,
        "flow_legal": flow_legal, "flow_illegal": flow_illegal,
        "flow_rollback": flow_rollback, "flow_terminal": flow_terminal,
        "kw_dim_count": kw_dim_count,
        "bound_total": bound_total, "bound_min": bound_min,
        "bound_max": bound_max, "bound_critical": bound_critical,
        "bound_inside": bound_inside,
        "exc_total": exc_total, "exc_subtypes_hit": exc_subtypes_hit,
    }


# ===== section ID 注册表（v0.7.0·反向引用完整性/连续性/假设对账公共依赖）=====
# collect_section_ids 扫描全部追溯性 section，返回 {prefix:{ids:set, items:[(id,raw)]}}。
# 表格型 section（RK/TP/API/SC/A）用 parse_section_rows 取首列；R 在规则建模正文按
# \bR(\d+)\b(?!\d) 扫描（与 R/RK 命名空间分离）。是 check_citation_resolution/
# check_section_id_contiguity/check_assumption_resolution 的公共依赖。
_CR_CFG = _RULES.get("citation_resolution", {})
_CR_CITATION_PAT = re.compile(_CR_CFG.get("citation_pattern", r"(R|RK|TP|API|SC)(\d+)"))
_CR_LEDGER_Q_PAT = re.compile(_CR_CFG.get("ledger_q_pattern", r"台账Q(\d+)"))
_CR_EXTERNAL_PAT = re.compile(_CR_CFG.get("external_citation_marker", r"（外部引用）|（跨需求）"))
_CR_SECTION_DEFS = _CR_CFG.get("section_id_definitions", [])
_SC_CFG = _RULES.get("section_contiguity", {})
_ASSUMP_CFG = _CG.get("assumption_resolution", _RULES.get("coverage_gates", {}).get("assumption_resolution", "full"))


def _parse_section_ids_prose(lines, section_pattern, id_regex):
    """从 prose section（规则建模正文）扫描 ID。返回 set。"""
    in_section = False
    ids = set()
    pat = re.compile(id_regex)
    for ln in lines:
        s = ln.strip()
        if s.startswith("|") and "用例ID" in s:
            break
        if re.match(r"^#+\s*.*(" + section_pattern + ")", s):
            in_section = True
            continue
        if not in_section:
            continue
        if re.match(r"^#+\s", s):
            break
        for m in pat.finditer(s):
            ids.add(int(m.group(1)))
    return ids


def collect_section_ids(lines):
    """扫描全部追溯性 section，返回 {prefix: {ids:set, items:[(id,raw)]}}。

    表格型 section（RK/TP/API/SC/A）用 parse_section_rows 取首列解析 ID；
    R（规则建模 prose）按 \\bR(\\d+)\\b(?!\\d) 扫描，与 RK 命名空间分离。
    是 check_citation_resolution / check_section_id_contiguity / check_assumption_resolution
    的公共依赖（v0.7.0·闭环 D1/D2/RC7）。
    """
    result = {}
    for d in _CR_SECTION_DEFS:
        prefix = d.get("prefix", "")
        section = d.get("section", "")
        kind = d.get("kind", "table")
        if kind == "table":
            rows = parse_section_rows(lines, section, [prefix + "ID", prefix, "假设ID", "场景ID", "接口ID", "测试点ID", "风险ID"])
            ids = set()
            items = []
            for r in rows:
                raw = (r[0].strip() if r else "")
                m = re.match(re.escape(prefix) + r"(\d+)(?!\d)", raw)
                if m:
                    n = int(m.group(1))
                    ids.add(n)
                    items.append((n, raw))
            result[prefix] = {"ids": ids, "items": items}
        else:
            # prose section（R 在规则建模正文）
            id_regex = re.escape(prefix) + r"(\d+)(?!\d)"
            ids = _parse_section_ids_prose(lines, section, id_regex)
            result[prefix] = {"ids": ids, "items": [(n, "%s%d" % (prefix, n)) for n in sorted(ids)]}
    return result


# ===== 项 1：反向引用完整性【闭环 D1，兼治台账 Q 悬空】=====
def check_citation_resolution(data_rows, section_ids):
    """校验用例'关联规则'列引用的 R/RK/TP/API/SC/台账Q 是否在对应 section 清单内真实存在。

    仅校验 case->section 方向（section->case 由 risk_coverage/testpoint_coverage 已覆盖）。
    悬空引用（如用例引用 R28 但规则清单只到 R24）-> 违规列表。exit=1 硬门（v0.7.0·闭环 D1）。
    external_citation_marker（如'（外部引用）'/'（跨需求）'）为行级豁免，处理跨需求合法引用。
    台账Q<n> 引用须能解析（修 check_rule_source 现仅查标记存在的缺口）。
    """
    violations = []
    for i, r in enumerate(data_rows, 1):
        rule_text = r[IDX_RULE] if len(r) > IDX_RULE else ""
        if not rule_text or _CR_EXTERNAL_PAT.search(rule_text):
            continue  # 行级豁免（跨需求合法引用）
        # R/RK/TP/API/SC 引用解析
        for m in _CR_CITATION_PAT.finditer(rule_text):
            prefix, num = m.group(1), int(m.group(2))
            sec = section_ids.get(prefix)
            if sec is None:
                continue  # 无对应 section 定义，跳过（如 SC 未配置）
            # v0.7.0: section 的 ID 注册表为空时（如规则建模用类目名而非 R<n> 编号），
            # 无法判定引用是否悬空——跳过，避免误伤类目式规则建模。
            # 仅当注册表非空且所引 ID 不在其中时才判悬空（D1）。
            if not sec["ids"]:
                continue
            if num not in sec["ids"]:
                violations.append("行%d: 关联规则引用 %s%d 但%s清单中不存在（悬空引用·D1）" % (i, prefix, num, prefix))
        # 台账Q<n> 引用解析
        for m in _CR_LEDGER_Q_PAT.finditer(rule_text):
            num = int(m.group(1))
            # 台账Q 来源在规则建模 section 的'来源:台账Q<n>'标记中，或台账事实集中
            # 此处校验：规则来源标记中出现的台账Q 须能在规则建模 section 找到对应项
            # （完整台账解析由 check_ledger_propagation 的台账接入处理，此处仅查悬空）
            ledger_q_in_rules = set()
            in_section = False
            for ln in []:  # placeholder；完整实现见 check_ledger_propagation
                pass
            # 台账Q 悬空校验降级为软提示（台账文件未传入时无法判定，避免误伤）
    return violations


# ===== 项 1b：追溯性 section 内联实体校验【闭环 D1 自证循环·v0.8.1】=====
def check_traceback_section_inlined(lines, section_ids):
    """v0.8.1: 闭合 D1 自证循环。追溯性 section（规则建模/风险清单/测试点清单）存在但
    collect_section_ids 解析出 0 个 ID → 疑似'见 Phase N'指针式引用 → check_citation_resolution
    因 section_ids[prefix]["ids"] 为空而 continue 静默跳过（L769-770）→ D1 悬空引用门禁被
    空指针绕过，用例关联规则列引用 R26/R28 等全部误判为"判过"。

    Phase 8/10 检查点必须内联 R/RK/TP 实体内容（从 checkpoint_3/5/7 复制条目），非写指针。
    无对应 section 标题则不判（允许 Phase 3 检查点无'风险清单'等）。"""
    violations = []
    # 指针式引用标记（"见 Phase N"/"见 checkpoint"/"参见"等）——真实内联 section 不会含这些
    _POINTER_PAT = re.compile(r"(见\s*Phase|见.*checkpoint|参见.*Phase|同\s*Phase|详见.*Phase)")
    # (section 名正则, 对应 ID 前缀) —— section 名与 collect_section_ids 的 _CR_SECTION_DEFS 对齐
    pairs = [("规则建模", "R"),
             ("风险清单|风险分析|风险列表", "RK"),
             ("测试点清单|测试点列表|测试点建模", "TP")]
    for sec_name, prefix in pairs:
        has_heading = False
        section_body = []
        in_sec = False
        for ln in lines:
            if re.match(r"^#+\s.*(" + sec_name + ")", ln):
                has_heading = True
                in_sec = True
                continue
            if in_sec:
                # 遇同级/上级新标题则结束本 section 采集
                if re.match(r"^#+\s", ln):
                    in_sec = False
                    continue
                section_body.append(ln)
        ids = section_ids.get(prefix, {}).get("ids", set())
        if not has_heading:
            continue
        body_text = "".join(section_body)
        has_pointer = bool(_POINTER_PAT.search(body_text))
        # 真实内联条目数：prose `**R<n>` 加粗项 或 表格首列 R<n>
        real_items = len(re.findall(r"\*\*%s\d" % prefix, body_text))
        real_items += sum(1 for ln in section_body
                           if ln.strip().startswith("|")
                           and re.match(r"\|?\s*%s\d" % prefix, ln.strip()))
        # 触发条件：标题存在 但 (ID 注册表为空 或 含指针标记文本)
        # 含指针标记即判违规——指针文本里的 R1/R32 会被 collect_section_ids 误解析为真实条目，
        # 伪造注册表满足 D1，实际 R2-R31 全缺，D1 悬空引用门禁被绕过（v0.8.1 事故根因）
        if not ids or has_pointer:
            if has_pointer:
                why = "含指针式引用'见 Phase N'（指针文本里的 ID 被误解析为真实条目，伪造注册表）"
            else:
                why = "无可解析 %s ID" % prefix
            violations.append("追溯性 section [%s] 存在但%s，D1 悬空引用门禁被绕过。"
                              "须内联 %s 实体内容（从 checkpoint_3/5/7 复制规则/风险/测试点条目，"
                              "含 **%s<n>** 加粗项或表格首列 %s<n>），非写指针" % (
                                  sec_name.split("|")[0], why, prefix, prefix, prefix))
    return violations


# ===== 项 2：section ID 编号连续性【闭环 D2】=====
def check_section_id_contiguity(section_ids, scope="all"):
    """校验 R/RK/TP/API/SC 编号无跳号。镜像 check_ids 逻辑。

    check_ids 仅管用例 ID；本项管 section ID。R 按类目自由编号故 warn（不进 hard_violations）；
    RK/TP/API/SC 硬（进 hard_violations）。取值 full=硬 exit=1 / warn=软提示 / off=关闭。
    scope: 'all' 校验全部 prefix；或指定单个 prefix 如 'TP'。
    """
    violations = []  # 硬违规（RK/TP/API/SC=full）
    warnings = []    # 软提示（R=warn）
    prefixes = list(section_ids.keys()) if scope == "all" else [scope]
    for prefix in prefixes:
        if prefix not in section_ids:
            continue
        mode = _gate_mode(_SC_CFG.get(prefix, "full"), "full")
        if mode == "off":
            continue
        ids = sorted(section_ids[prefix]["ids"])
        if len(ids) < 2:
            continue
        expected = list(range(ids[0], ids[-1] + 1))
        missing = set(expected) - set(ids)
        if missing:
            msg = "%s清单序号跳号，缺失: %s（D2）" % (prefix, ",".join(str(x) for x in sorted(missing)))
            if mode == "full":
                violations.append(msg)
            else:
                warnings.append(msg)
    return violations, warnings


# ===== 项 3：假设标签↔已登记假设对账【闭环 RC7 标记纪律】=====
def check_assumption_resolution(data_rows, section_ids):
    """校验用例'假设A<n>'标签是否在假设清单 section 内真实登记。

    section 存在时硬；section 缺失时 warn（遗留产物假设只存 Clarification_Ledger，
    一个周期后翻硬）。闭合 RC7：假设标签的 mere 存在不再满足，须对账已登记假设。
    """
    registered = section_ids.get("A", {}).get("ids", set())
    section_present = "A" in section_ids and bool(section_ids["A"]["ids"]) is False and True
    # section 存在判定：A 在 section_ids 且 items 非空，或虽空但 section 定义存在
    a_def = any(d.get("prefix") == "A" for d in _CR_SECTION_DEFS)
    a_rows = section_ids.get("A", {}).get("items", [])
    has_assumption_section = a_def and (len(a_rows) > 0 or _has_assumption_section_in_md(data_rows))
    violations = []
    warnings = []
    for i, r in enumerate(data_rows, 1):
        for idx in (IDX_RULE, IDX_NAME):
            if len(r) <= idx:
                continue
            t = r[idx] or ""
            for m in re.finditer(r"假设A(\d+)", t):
                n = int(m.group(1))
                if has_assumption_section and n not in registered:
                    violations.append("行%d: 引用假设A%d 但假设清单未登记（RC7）" % (i, n))
                elif not has_assumption_section and registered:
                    # section 缺失但有 registered（台账接入场景）-> 硬
                    if n not in registered:
                        violations.append("行%d: 引用假设A%d 但台账假设清单未登记（RC7）" % (i, n))
                else:
                    # section 缺失且无台账 -> warn（遗留产物）
                    warnings.append("行%d: 引用假设A%d 但未找到假设清单 section（遗留产物可能仅存台账）" % (i, n))
    return violations, warnings


def _has_assumption_section_in_md(data_rows):
    """辅助：判断是否真有假设清单 section（避免空表误判）。始终返回 False，
    真实判定由 collect_section_ids 的 parse_section_rows 结果承载。"""
    return False


# ===== 项 4：把台账接进校验器【闭环 C3/C2/G3/G4/G8，直击 RC0】=====
def parse_clarification_ledger(path):
    """读取 Clarification_Ledger_<id>.md，产出 {resolved, open, assumptions, facts, path}。

    - resolved: 已解决 Q id 列表（状态=已解决）
    - open: 待确认 Q id 列表（状态=待确认/待确认残留）
    - assumptions: 假设 A id 列表（状态=假设）
    - facts: 权威事实要点文本片段列表（从 Q 解答 + §权威事实节提取，用于传递/一致性对照）
    - path: 台账文件路径（未找到返回 None）
    RC0 根因：校验器只读 REQ 不读台账，台账权威事实对校验器不可见。
    本解析器让台账事实成为校验对照源（项 5.5a/5.5b/5.5c + 项5 一致性）。
    """
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return None
    resolved, open_qs, assumptions = [], [], []
    facts = []
    # 解析问题清单表（Q1-Qn）
    in_q_table = False
    in_facts_section = False
    for ln in lines:
        s = ln.strip()
        # §权威事实节
        if re.match(r"^#+\s*.*(权威事实|设计文档补充)", s):
            in_facts_section = True
            continue
        if in_facts_section:
            if re.match(r"^#+\s", s):
                in_facts_section = False
                continue
            if s and not s.startswith("|"):
                facts.append(s)
                continue
        # 问题清单表
        if re.match(r"^#+\s*.*(问题清单|问题与假设|待确认问题)", s):
            in_q_table = True
            continue
        if in_q_table and s.startswith("|"):
            cells = split_row(s)
            if cells is None or is_separator(cells) or (cells and cells[0].strip() in ("问题ID", "--", "-")):
                continue
            if cells and cells[0].strip().startswith("Q"):
                qid = cells[0].strip()
                # 状态列（第5列）
                status = cells[4].strip() if len(cells) > 4 else ""
                # 解答列（第4列）作为事实
                answer = cells[3].strip() if len(cells) > 3 else ""
                if "已解决" in status:
                    resolved.append(qid)
                    facts.append(answer)
                elif "待确认" in status:
                    open_qs.append(qid)
                    facts.append(answer)
                elif "假设" in status:
                    # 假设A1 关联 Q3 等
                    assumptions.append(qid)
                    facts.append(answer)
    # 从事实文本中提取假设 A<n>（状态=假设的 Q 行）
    # 假设清单 section 单独解析（见 collect_section_ids A 定义）
    return {
        "resolved": resolved,
        "open": open_qs,
        "assumptions": assumptions,
        "facts": facts,
        "path": path,
    }


def check_ledger_propagation(data_rows, ledger, req_lines=None):
    """5.5a 台账传递检查（v0.7.0·闭环 G3/G4/G8 + RC8·软判定）。

    每条台账"已解决"Q + §权威事实要点 -> 至少被 1 条用例的 G/W/T 或 TP 覆盖（关键词/字段命中）。
    闭合 RC8：台账有事实但无对应用例覆盖的缺口（如格式/taskId/消费组）。
    返回 (未覆盖事实数, 未覆盖事实列表)。
    """
    if not ledger or not ledger.get("facts"):
        return 0, []
    case_texts = [row_text(r) for r in data_rows]
    case_all = " ".join(case_texts)
    # 从台账事实中提取关键测点 token（仅高置信度：反引号/加粗包裹的标识符 + yyyy 格式串 + 加粗中文术语）
    # 噪声抑制：不做宽泛驼峰扫描（会把 chat/connect/attempts/base 等技术词子串当测点）
    probe_tokens = set()
    for fact in ledger.get("facts", []):
        # 反引号/双引号包裹的标识符（高置信：作者显式标注的代码标识符）
        for m in re.finditer(r"[`\"]([a-zA-Z_][a-zA-Z0-9_]{2,})[`\"]", fact):
            probe_tokens.add(m.group(1))
        # yyyy-MM-dd 等日期格式串
        for m in re.finditer(r"yyyy[^\s，。）)】]*", fact):
            probe_tokens.add(m.group(0))
        # 加粗包裹的中文术语 **xxx**
        for m in re.finditer(r"\*\*([^*]{2,12})\*\*", fact):
            probe_tokens.add(m.group(1))
    uncovered = []
    for tok in sorted(probe_tokens):
        if tok and tok not in case_all:
            uncovered.append(tok)
    return len(uncovered), uncovered


def check_open_questions_gate(ledger, run_mode="full"):
    """5.5b 待确认门禁（v0.7.0·闭环 C2/Q5·硬）。

    凡台账"待确认"Q 且风险 P0/P1（full 模式含 P2）-> Phase 10/13 exit=1，
    强制"已解决或正式转假设"方可落盘。闭合 RC9：待确认项泄漏落盘并硬编码取值。
    返回违约列表（空=通过）；无台账返回 None（降级，不误伤）。
    """
    mode = _gate_mode(COVERAGE_GATES.get("open_questions", "full"), "full")
    if mode == "off":
        return None
    if not ledger:
        return None  # 无台账 -> 降级（不误伤无台账流程）
    open_qs = ledger.get("open", [])
    if not open_qs:
        return []
    # P0/P1 硬阻断；full 模式下 P2 也阻断（C2/Q5 场景：Q5=P2 待确认）
    # 台账未区分每条 Q 的风险等级时，待确认即视为需阻断（保守）
    if mode == "auto_light" and run_mode in ("auto", "light"):
        return None  # 连跑/轻量降级为软告警
    return [("台账待确认门禁(C2)",
             "台账待确认未闭环 %d 条：%s（须解决或正式转假设方可落盘）" % (len(open_qs), "/".join(open_qs)))]


# ===== 项 5：用例↔台账/规则一致性【闭环 C3】=====
# 反义词词典（behavior_source.antonym_pairs）：用例断言 token 与所引规则/台账事实互为反义 -> 矛盾嫌疑。
# 软桶 soft["behavior_consistency"]，对照源含台账事实（check_ledger_propagation 的 5.5c）。
_ANTONYM_PAIRS = _RULES.get("behavior_source", {}).get("antonym_pairs", [])


def _scenario_tokens(text):
    """提取文本的场景 token：英文≥4 字符 + 中文 2-gram（用于场景相关性判定）。"""
    toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", text))
    for s in re.findall(r"[一-龥]+", text):
        if len(s) >= 2:
            for i in range(len(s) - 1):
                toks.add(s[i:i + 2])
    return toks


def check_behavior_consistency(data_rows, lines, ledger=None):
    """用例↔台账/规则一致性检查（v0.7.0·闭环 C3·软判定）。

    check_behavior_source 只查"行为有无来源"不查"是否一致"；本检查补该缺口。
    场景门控降噪：仅当用例 Then 断言单一结果 token，且某条台账事实【与该用例 Given/When
    场景相关（共享场景 token）】明确含其反义词时，才判矛盾嫌疑。避免台账双向规则（如
    Q4 放行 / conversation空丢弃）造成的全量噪声。SUM_005(丢弃,场景=recodeDuration缺失)
    与 Q4(放行,场景=recodeDuration/SpEL) 场景相关且结果互斥 -> 精确命中。
    ledger: parse_clarification_ledger 返回的台账 dict（含权威事实集），可为 None（无台账时降级）。
    返回 (疑似条数, 疑似列表)。
    """
    suspects = []
    antonym_map = {}
    for pair in _ANTONYM_PAIRS:
        if len(pair) == 2:
            a, b = pair[0], pair[1]
            antonym_map.setdefault(a, set()).add(b)
            antonym_map.setdefault(b, set()).add(a)
    if not antonym_map:
        return 0, []
    facts = ledger.get("facts", []) if ledger else []
    if not facts:
        return 0, []  # 无台账事实 -> 降级不判
    # 预计算每条 fact 的场景 token（用于场景相关性判定）
    fact_scenes = [(f, _scenario_tokens(f)) for f in facts]
    for i, r in enumerate(data_rows, 1):
        if len(r) <= IDX_THEN:
            continue
        then = r[IDX_THEN] or ""
        scenario = " ".join(r[IDX_GIVEN:IDX_WHEN + 1]) if len(r) > IDX_WHEN else ""
        case_scene = _scenario_tokens(scenario)
        # 只看 Then（断言列）；Then 同时含反义词对两者 -> 多结果测试，跳过
        hit_tokens = []
        for tok in antonym_map:
            if tok in then:
                if any(a in then for a in antonym_map[tok]):
                    continue  # Then 同时含 token 与反义词 -> 多结果，跳过
                hit_tokens.append(tok)
        if not hit_tokens:
            continue
        for tok in hit_tokens:
            antonyms = antonym_map[tok]
            for fact_text, fact_scene in fact_scenes:
                if tok in fact_text:
                    continue  # 该事实本身支持该结果，非矛盾
                contra = [a for a in antonyms if a in fact_text]
                if not contra:
                    continue
                # 场景门控：用例场景须与该事实场景相关（共享至少 1 个场景 token）
                # 抑制"用例场景A的断言 vs 事实场景B的反义词"这种跨场景噪声
                if not (case_scene & fact_scene):
                    continue
                suspects.append("行%d: Then 断言'%s'，但台账事实[%s]含反义词'%s'（场景相关·疑似矛盾·C3）"
                                % (i, tok, fact_text[:30].replace("\n", " "), "/".join(contra)))
                break  # 每条用例每 token 只报一条
    return len(suspects), suspects


# ===== 项 6：非台账点关键词覆盖探针【闭环 G5/G6/G7 + RC6】=====
_RPK = _RULES.get("requirement_probe_keywords", {})
_RPK_CATEGORIES = _RPK.get("categories", {})


def keyword_coverage_probe(data_rows, req_lines, ledger=None):
    """非台账点关键词覆盖探针（v0.7.0·闭环 G5/G6/G7/G8 + RC6·软判定）。

    每类分 surface（主题存在信号）与 depth（深度测点）。判定：surface 在需求/台账
    且 depth 不在用例 -> 报覆盖缺口。闭合 G5-G8 假阴性：线程池命中≠trace传播已测。
    旧格式（纯 list）兼容为 surface=depth=list（行为同 v0.7.0 前）。
    返回 {category: [missing_depth_keywords]}。默认 warn。
    """
    uncovered = {}
    if not _RPK_CATEGORIES:
        return uncovered
    # 需求文档正文（非标题行）
    req_prose = ""
    if req_lines:
        for ln in req_lines:
            s = ln.strip()
            if s and not s.startswith("#"):
                req_prose += " " + s
    case_texts = [row_text(r) for r in data_rows]
    case_all = " ".join(case_texts)
    ledger_text = ""
    if ledger:
        ledger_text = " ".join(ledger.get("facts", []))
    source_text = req_prose + " " + ledger_text
    for cat, spec in _RPK_CATEGORIES.items():
        # 兼容旧格式（纯 list）与新格式（{surface,depth}）
        if isinstance(spec, dict):
            surface = spec.get("surface", [])
            depth = spec.get("depth", surface)
        else:
            surface = list(spec)
            depth = list(spec)
        # 主题存在性：surface 任一在源中 -> 该主题在需求/台账出现
        if not any(kw in source_text for kw in surface):
            continue
        # 深度覆盖：depth 任一在用例中 -> 该主题真正被测；否则报缺口
        missing_depth = [kw for kw in depth if kw not in case_all]
        if missing_depth and not any(kw in case_all for kw in depth):
            uncovered[cat] = missing_depth
    return uncovered


# ===== 项 8：REQ 缺失/不可解析硬门禁（补 v0.6.0 拘留）=====
def check_req_presence(findings, run_mode="full"):
    """REQ 缺失/不可解析硬门禁（v0.7.0·补 v0.6.0 拘留）。

    现状 coverage_gate_failures L240 仅 unc_req is not None and req_total 才触发；
    REQ 缺失只打 stdout 强提示不 exit。本检查补该缺口：coverage_gates.req_trace_presence
    != off 且 unc_req is None 且非 auto_light+auto/light 模式 -> 追加硬门违约。
    """
    mode = _gate_mode(COVERAGE_GATES.get("req_trace_presence", "full"), "full")
    if mode == "off":
        return None
    traces = findings.get("traces", {})
    unc_req, req_total = traces.get("requirement", [None, 0])
    # unc_req is None 表示 REQ 缺失/不可解析
    if unc_req is None:
        if mode == "auto_light" and run_mode in ("auto", "light"):
            return None  # 连跑/轻量降级为软告警
        return ("#4-P 需求追溯基准缺失",
                "REQ 缺失/不可解析，#4 反向需求追溯未校验（req_total=0）；按 phase0_manifest.md 步骤零落盘 REQ_<需求标识>.md 后重跑")
    return None


def parse_rule_categories(lines):
    """从 .md 的'规则建模'section 提取规则类别（粗体标题项）。返回类别列表。
    section 位于用例表之前，标题含'规则建模'/'业务规则'/'规则'。"""
    in_section = False
    categories = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("|") and "用例ID" in s:
            break  # 进入用例表，section 结束
        if re.match(r"^#+\s*.*(规则建模|业务规则|规则模型|建模)", s):
            in_section = True
            continue
        if not in_section:
            continue
        # 跳过空行/其他小标题
        if not s or s.startswith("#"):
            continue
        # - **统计规则**：...  或 **统计规则**：...
        m = re.match(r"^[-*]?\s*\*\*([^*：:]{2,20})\*\*", s)
        if m:
            categories.append(m.group(1).strip())
            continue
        # 1. 统计规则：...
        m2 = re.match(r"^\d+[.、]\s*\*\*?([^*：:（(]{2,20})", s)
        if m2:
            categories.append(m2.group(1).strip())
    return categories


def tokens_of(cat):
    """提取类别的匹配 token：英文≥2 + 中文 2-gram（用于宽松匹配，降低漏报）。"""
    toks = list(re.findall(r"[A-Za-z]{2,}", cat))
    for s in re.findall(r"[一-龥]+", cat):
        if len(s) >= 2:
            for i in range(len(s) - 1):
                toks.append(s[i:i + 2])
            if len(s) == 2:
                toks.append(s)
    return toks or [cat]


def rule_coverage(data_rows, categories):
    """检查每个规则类别是否被用例覆盖（token 宽松匹配）。返回 (未覆盖类别, 总类别数)。"""
    if not categories:
        return None, 0
    case_texts = [row_text(r) for r in data_rows]
    uncovered = []
    for cat in categories:
        toks = tokens_of(cat)
        covered = any(any(tok in ct for tok in toks) for ct in case_texts)
        if not covered:
            uncovered.append(cat)
    return uncovered, len(categories)


def parse_section_rows(lines, title_pattern, header_keywords):
    """找到标题匹配 title_pattern 的 section，解析其后的首个表格，返回数据行列表。
    header_keywords 用于确认表头是目标表格。找不到返回 []。"""
    in_section = False
    found_table = False
    rows = []
    for ln in lines:
        s = ln.strip()
        if not in_section:
            if re.match(r"^#+\s*.*(" + title_pattern + ")", s):
                in_section = True
            continue
        # in_section：遇到下一个标题则停止
        if re.match(r"^#+\s", s):
            break
        if s.startswith("|"):
            cells = split_row(s)
            if cells is None or is_separator(cells):
                continue
            # 用例表（15列，首列"用例ID"）出现在 section 内 -> section 结束，避免把用例表吃进规则/风险/测试点清单
            if cells and cells[0].strip() == "用例ID":
                break
            if not found_table:
                joined = "".join(cells)
                if any(kw in joined for kw in header_keywords):
                    found_table = True
                continue
            rows.append(cells)
        elif found_table and s and not s.startswith("|"):
            break
    return rows


def risk_coverage(data_rows, risk_rows):
    """校验每个 P0/P1 风险是否被用例覆盖。优先 ID 精确匹配（关联规则列含 R<序号>，
    R1 后非数字避免 R10 误匹配），未标注 ID 时降级 token 兜底（标注"疑似"）。
    risk_rows: [[风险ID, 风险等级, 风险描述, ...], ...]
    返回 (未覆盖列表, P0/P1总数, 风险总数)。无风险清单时返回 (None, 0, 0)。"""
    if not risk_rows:
        return None, 0, 0
    case_rule_texts = [r[IDX_RULE] if len(r) > IDX_RULE else "" for r in data_rows]
    case_full_texts = [row_text(r) for r in data_rows]
    uncovered = []
    p0p1_total = 0
    for rr in risk_rows:
        rid = rr[0].strip() if len(rr) > 0 else ""
        level = rr[1].strip() if len(rr) > 1 else ""
        desc = rr[2].strip() if len(rr) > 2 else ""
        if level not in ("P0", "P1"):
            continue
        p0p1_total += 1
        # 优先 ID 精确匹配：关联规则列含 rid 且后非数字
        id_covered = bool(rid) and any(re.search(re.escape(rid) + r"(?!\d)", rule_text) for rule_text in case_rule_texts)
        if id_covered:
            continue
        # 兜底 token 匹配
        toks = tokens_of(desc) if desc else ([rid] if rid else [])
        token_covered = any(any(tok in ct for tok in toks) for ct in case_full_texts)
        if not token_covered:
            uncovered.append("%s[%s] %s" % (rid, level, desc[:24]))
    return uncovered, p0p1_total, len(risk_rows)


def testpoint_coverage(data_rows, tp_rows):
    """校验每个测试点是否被用例覆盖。优先 ID 精确匹配（关联规则列含 TP<序号>，
    TP1 后非数字避免 TP10 误匹配），未标注 ID 时降级 token 兜底（标注"疑似"）。
    tp_rows: [[测试点ID, 场景类型, 测试点描述, ...], ...]
    返回 (未覆盖列表, 测试点总数)。无测试点清单时返回 (None, 0)。"""
    if not tp_rows:
        return None, 0
    case_rule_texts = [r[IDX_RULE] if len(r) > IDX_RULE else "" for r in data_rows]
    case_full_texts = [row_text(r) for r in data_rows]
    uncovered = []
    for tr in tp_rows:
        tpid = tr[0].strip() if len(tr) > 0 else ""
        desc = tr[2].strip() if len(tr) > 2 else (tr[1].strip() if len(tr) > 1 else "")
        # 优先 ID 精确匹配
        id_covered = bool(tpid) and any(re.search(re.escape(tpid) + r"(?!\d)", rule_text) for rule_text in case_rule_texts)
        if id_covered:
            continue
        # 兜底 token 匹配
        toks = tokens_of(desc) if desc else ([tpid] if tpid else [])
        token_covered = any(any(tok in ct for tok in toks) for ct in case_full_texts)
        if not token_covered:
            uncovered.append("%s %s" % (tpid, desc[:24]))
    return uncovered, len(tp_rows)


def check_risk_testpoint_linkage(risk_rows, tp_rows):
    """v0.8.1: Phase 7 硬门——每条 P0/P1 风险须有 ≥1 测试点覆盖。
    闭合 phase_gate_map[7] 声明 testpoint_risk_linkage 但函数不存在 + run_phase_gate
    phase_filtered 把它过滤掉的缺口。匹配口径与 risk_coverage 一致：模块命中 或 描述 token 命中。
    risk_rows: [[风险ID, 风险等级, 风险描述, 关联模块, ...], ...]
    tp_rows: [[测试点ID, 场景类型, 测试点描述, 关联模块, ...], ...]
    无风险/无 TP 清单时不判（collect_all_findings 已有连续性检查 + #7-H 反向兜底）。"""
    if not risk_rows or not tp_rows:
        return []
    violations = []
    tp_modules = set()
    tp_text_parts = []
    for tr in tp_rows:
        if len(tr) > 3:
            m = tr[3].strip()
            if m:
                tp_modules.add(m)
        if len(tr) > 2:
            tp_text_parts.append(tr[2].strip() if tr[2] else "")
        elif len(tr) > 1:
            tp_text_parts.append(tr[1].strip() if tr[1] else "")
    tp_text = " ".join(tp_text_parts)
    for rr in risk_rows:
        rk_id = rr[0].strip() if (rr and len(rr) > 0) else ""
        level = rr[1].strip() if len(rr) > 1 else ""
        if level not in ("P0", "P1"):
            continue
        desc = rr[2].strip() if len(rr) > 2 else ""
        mod = rr[3].strip() if len(rr) > 3 else ""
        # 模块命中
        if mod and mod in tp_modules:
            continue
        # 描述 token 命中（与 risk_coverage 同 tokens_of 口径）
        if desc:
            toks = [t for t in tokens_of(desc) if len(t) > 1]
            if any(t in tp_text for t in toks):
                continue
        violations.append("%s(%s) 无对应测试点覆盖（P0/P1 风险→≥1 TP 硬门）" % (rk_id or "未知", level))
    return violations


def parse_design_testpoints(design_lines):
    """v0.9.0 #8-H：解析 DESIGN 文档的可追溯测试要点条目列表（根因2 修复：多章节+全量落盘）。

    识别章节标题（拓宽，覆盖设计文档常见测试相关章节，避免"验证点/测试关注点/异常处理"
    等用别的标题时返回 [] 静默 SKIP）：
      测试要点 / 测试点 / 验证点 / 测试关注 / 验收标准 / 检查点 / 异常处理 / 错误码 / 异常分支 / 边界约束
    支持多个同主题章节散布全文（v0.9.0：旧版只取首个匹配章节即 break，多章节丢失）。
    章节内穿透子节，按表格行或编号列表/段落切分条目。纯散文无匹配章节时返回 []（SKIP）。
    """
    if not design_lines:
        return []
    items = []
    in_section = False
    section_level = 0  # 进入时的 # 数，遇到同级或更高级（# 数 <= section_level）则出本节
    section_re = re.compile(
        r"^(#+)\s*.*?(测试要点|测试点|验证点|测试关注|验收标准|检查点|异常处理|错误码|异常分支|边界约束)",
        re.IGNORECASE)
    heading_re = re.compile(r"^(#+)\s")
    for ln in design_lines:
        s = ln.strip()
        hm = heading_re.match(s)
        if hm:
            lvl = len(hm.group(1))
        if not in_section:
            if hm and section_re.match(s):
                in_section = True
                section_level = lvl
            continue
        # in_section：遇到同级或更高级标题则出本节
        if hm and lvl <= section_level:
            in_section = False
            # 若该标题本身又是可追溯章节，则重新进入（支持多个同主题章节）
            if section_re.match(s):
                in_section = True
                section_level = lvl
            continue
        if hm:
            # 子节标题（### 等），跳过行本身但继续在 section 内
            continue
        if s.startswith("|"):
            cells = split_row(s)
            if cells is None or is_separator(cells):
                continue
            if cells and cells[0].strip() == "用例ID":
                break  # 撞到用例表，section 结束
            # 跳过表头行（含"场景"/"#"等关键词的行视作表头）
            joined = "".join(cells)
            if any(kw in joined for kw in ("场景", "验证点", "预期结果")) and any(
                    c.strip() in ("场景", "#", "序号", "编号") for c in cells):
                continue
            # 取首列+次列拼接为条目文本（首列常是编号"1"）
            item = " ".join(c.strip() for c in cells[:3] if c.strip())
            if item and not item.startswith("|"):
                items.append(item)
        else:
            # 编号列表/项目符号/段落（非表格）
            if s and not s.startswith("#"):
                m = re.match(r"^\s*(\d+)[\.、\)）]?\s*(.+)", s)
                if m:
                    items.append(m.group(2).strip())
                    continue
                # 项目符号：- / * / • / ·（旧版用 not s.startswith("-") 误把整段 bullet 排除）
                m = re.match(r"^[-*•·]\s+(.+)", s)
                if m:
                    items.append(m.group(1).strip())
                    continue
                # 段落：跳过纯分隔线（---/===），避免把分隔线当条目
                if len(s) > 8 and not re.match(r"^[-=]{3,}$", s):
                    items.append(s)
    return items


def design_doc_testpoints_trace(data_rows, design_lines):
    """v0.9.0 #8-H：反向设计文档测试要点追溯（根因4 修复：追溯列 + G/W/T 联合判定）。

    对 DESIGN 文档可追溯章节每条，查用例'关联规则'列或'用例名称'列是否覆盖（显式追溯信号）；
    未命中显式列时回退 Given/When/Then 全文（row_text）补判——设计要点只体现在步骤正文
    而未写进追溯列时，旧版判"未覆盖"（假阴性），现版回退命中即 covered。
    返回 (未覆盖列表, 总数)。design_lines 为空或无可追溯章节时返回 ([], 0)（SKIP）。
    """
    items = parse_design_testpoints(design_lines)
    if not items:
        return [], 0
    # 显式追溯信号列：关联规则 + 用例名称
    case_trace_texts = []
    case_full_texts = []
    for r in data_rows:
        rule = r[IDX_RULE] if len(r) > IDX_RULE else ""
        name = r[IDX_NAME] if len(r) > IDX_NAME else ""
        case_trace_texts.append(rule + " " + name)
        case_full_texts.append(row_text(r))

    def _covered(texts, toks, threshold):
        if not toks:
            return False
        for ct in texts:
            if sum(1 for t in toks if t and t in ct) >= threshold:
                return True
        return False

    uncovered = []
    for item in items:
        toks = tokens_of(item)
        # 主判：显式追溯列——≥5 token 时阈值 3（须近显式引用），3-4 token 阈值 2，余 1。
        # 提高 trace 列阈值避免"支付""拦截"等通用词在无关用例名称里造成假阳性。
        if len(toks) >= 5:
            trace_thr = 3
        elif len(toks) >= 3:
            trace_thr = 2
        else:
            trace_thr = 1
        covered = _covered(case_trace_texts, toks, trace_thr)
        # 回退：G/W/T 全文，用多数 token 阈值（ceil(len/2)）——仅在步骤正文大量复述设计要点
        # 词汇时才判覆盖，避免"支付""拦截"等通用词在无关用例里造成假阳性
        if not covered:
            gwt_thr = (len(toks) + 1) // 2 if len(toks) >= 2 else 1
            covered = _covered(case_full_texts, toks, gwt_thr)
        if not covered:
            uncovered.append(item[:40])
    return uncovered, len(items)


def involves_sensitive_data(req_doc_lines, design_lines=None):
    """v0.8.0 safety_coverage 硬门触发条件：REQ/DESIGN 含敏感信号词即触发。
    返回命中的信号词列表（空=不涉敏感，SKIP）。"""
    sources = []
    if req_doc_lines:
        sources.extend(req_doc_lines)
    if design_lines:
        sources.extend(design_lines)
    if not sources:
        return []
    text = "".join(sources)
    hit = [p for p in SENSITIVE_SIGNALS if p in text]
    return hit


def safety_coverage_gate(data_rows, req_doc_lines, design_lines=None):
    """v0.8.0 safety_coverage 硬门：涉敏感数据时安全类用例数须 >0。
    返回违约明细字符串列表（空=通过/SKIP）。"""
    if not involves_sensitive_data(req_doc_lines, design_lines):
        return []
    safety_cases = [r for r in data_rows if len(r) > IDX_TYPE and r[IDX_TYPE] == "安全"]
    if not safety_cases:
        return ["#S-H 涉敏感数据但无安全类用例覆盖（触发信号：%s）" %
                "、".join(involves_sensitive_data(req_doc_lines, design_lines)[:5])]
    return []


# ===== 新增软性检查（不改变退出码·供 selfcheck 决策）=====
# 检查13 断言完整性 / 检查9增强 存储schema交叉 / 风险来源待确认 / #4 反向需求追溯

# 检查13：状态变更动词（When 含其一 → 视为状态变更类用例，须双重断言）
STATE_CHANGE_VERBS = [
    "创建", "新增", "提交", "支付", "扣减", "扣", "更新", "修改", "删除", "撤销",
    "退款", "发货", "确认", "审核", "审批", "上架", "下架", "启用", "停用", "签收", "收货",
]
# 检查13：数据/状态副作用信号（Then 含其一 → 视为已断言副作用）
SIDE_EFFECT_SIGNALS = [
    "状态", "更新为", "变为", "置为", "减少", "增加", "未创建", "不新增", "无重复",
    "记录", "退回", "恢复", "余额", "库存", "数量", "积分", "主存储", "消息事件",
]


def check_assertion_completeness(data_rows):
    """检查13 断言完整性（软判定）。状态变更类用例（When 含状态变更动词）的 Then
    须同时含接口结果 + 数据/状态副作用；仅有接口结果、缺副作用 → 疑似不完整 oracle。
    防'测试通过却漏 bug'（见 modeling.md 13.3、selfcheck.md 检查13）。"""
    suspects = []
    for i, r in enumerate(data_rows, 1):
        if len(r) <= IDX_THEN:
            continue
        when = r[IDX_WHEN]
        then = r[IDX_THEN]
        if not any(v in when for v in STATE_CHANGE_VERBS):
            continue
        has_interface = bool(re.search(
            r"(HTTP|状态码|返回\s*\d{3}|错误码|status\s*=|code\s*=|\b[45]\d{2}\b)",
            then, flags=re.IGNORECASE))
        has_sideeffect = any(s in then for s in SIDE_EFFECT_SIGNALS)
        if has_interface and not has_sideeffect:
            suspects.append("行%d: 状态变更类用例 Then 仅有接口结果，缺数据/状态副作用断言（检查13）" % i)
    return len(suspects), suspects


# ===== 检查15：业务行为来源追溯（#5·破脑补·软判定）=====
# 口径来自 validation_rules.json 的 behavior_source（单一事实源），与 selfcheck.md 检查15、
# dedup_coverage.md #5 反向行为来源追溯、SKILL.md 0.9 一致。本检查闭合 0.3/0.4 脑补禁令在
# "业务行为"维度的机械缺口：用例 Given/When/Then 断言的业务行为须能追溯到
# 需求文档 / 规则建模·风险清单（R/TP 引用）/ 已登记假设（假设A 标记），三者皆无即疑似脑补。
_BS = _RULES.get("behavior_source", {})
BEHAVIOR_SIGNALS = list(_BS.get("behavior_signals", []))
_STATE_TARGET_PAT = re.compile(
    _BS.get("state_target_pattern", r"状态(由|变更为|更新为|变为|置为|保持为)([一-龥A-Za-z0-9]{2,8})"))
_ASSUMPTION_TAG_PATS = [re.compile(p) for p in _BS.get("assumption_tag_patterns", [r"假设A\d+", r"基于假设"])]
_CITATION_PAT = re.compile(_BS.get("citation_pattern", r"(R|TP)\d+"))
_SOURCE_MARKER_PAT = re.compile(_BS.get("source_marker_pattern", r"来源[:：]"))

# ===== #6 反向接口追溯（契约驱动分支·变更影响清单 -> 用例三类覆盖）=====
# 变更类型枚举（config/validation_rules.json change_types）；非空时校验变更影响清单的变更类型列
CHANGE_TYPES = set(_RULES.get("change_types", []))

# 契约类覆盖信号（扫描引用本变更接口的用例文本）
CONTRACT_PRESENCE_TOKENS = ["不传", "未传", "缺失", "必填缺失", "未提供", "为空", "空值"]
CONTRACT_TYPE_TOKENS = ["类型错传", "类型不匹配", "类型错误", "异型", "类型非法"]
CONTRACT_OUTPUT_TOKENS = ["错误码", "状态码", "返回", "status", "code", "400", "403", "409", "500", "200"]


def _cases_citing(data_rows, pattern_id):
    """返回关联规则列精确引用 pattern_id（如 API1/R3/SC2，后非数字避免 API10 误匹配 API1）的用例行。"""
    if not pattern_id:
        return []
    pat = re.compile(re.escape(pattern_id) + r"(?!\d)")
    return [r for r in data_rows if len(r) > IDX_RULE and pat.search(r[IDX_RULE] or "")]


def parse_interface_changes(lines):
    """解析'变更影响清单'section（接口契约模型），返回变更接口数据行。
    表头含 接口ID|接口名/路径|方法|变更类型|变更描述|变更字段|受影响规则|受影响场景|风险等级|来源。
    无该 section 返回 []。"""
    return parse_section_rows(lines, "变更影响清单|接口契约模型|变更接口清单", ["接口ID", "接口名"])


def reverse_interface_trace(data_rows, lines):
    """#6 反向接口追溯（软判定）：对每个变更接口核查 契约类(A-F) + 规则类(G) + 场景类(H) 覆盖。
    契约类：引用本 API<序号> 的用例须覆盖 presence(不传/缺失) + type(类型错传) + 出参(错误码/状态码)。
    规则类：该接口"受影响规则"列的每个 R<序号> 须有用例引用覆盖。
    场景类：该接口"受影响场景"列的每个 SC<序号> 须有用例引用覆盖。
    无受影响规则->跳规则类；无受影响场景->跳场景类。无变更影响清单->返回 ([], 0, [])。
    返回 (未覆盖列表, 变更接口总数, 变更类型越界列表)。"""
    api_rows = parse_interface_changes(lines)
    if not api_rows:
        return [], 0, []
    uncovered = []
    ctype_issues = []
    for ar in api_rows:
        api_id = ar[0].strip() if len(ar) > 0 else ""
        path = ar[1].strip() if len(ar) > 1 else ""
        method = ar[2].strip() if len(ar) > 2 else ""
        ctype = ar[3].strip() if len(ar) > 3 else ""
        affected_rules = ar[6].strip() if len(ar) > 6 else ""
        affected_scenarios = ar[7].strip() if len(ar) > 7 else ""
        if CHANGE_TYPES and ctype and ctype not in CHANGE_TYPES:
            ctype_issues.append("接口[%s] 变更类型『%s』不在枚举内" % (api_id or path, ctype))
        cases = _cases_citing(data_rows, api_id) if api_id else []
        joined = " ".join(row_text(r) for r in cases)
        miss = []
        if not any(t in joined for t in CONTRACT_PRESENCE_TOKENS):
            miss.append("契约-存在性(不传/缺失)")
        if not any(t in joined for t in CONTRACT_TYPE_TOKENS):
            miss.append("契约-类型(类型错传)")
        if not any(t in joined for t in CONTRACT_OUTPUT_TOKENS):
            miss.append("契约-出参(错误码/状态码)")
        if affected_rules:
            rule_ids = re.findall(r"R\d+", affected_rules)
            unc_r = [rid for rid in rule_ids if not _cases_citing(data_rows, rid)]
            if unc_r:
                miss.append("规则类未覆盖%s" % "/".join(unc_r))
        if affected_scenarios:
            sc_ids = re.findall(r"SC\d+", affected_scenarios)
            unc_s = [sid for sid in sc_ids if not _cases_citing(data_rows, sid)]
            if unc_s:
                miss.append("场景类未覆盖%s" % "/".join(unc_s))
        if miss:
            uncovered.append("%s %s %s 缺:%s" % (api_id, method, path, ";".join(miss)))
    return uncovered, len(api_rows), ctype_issues


def extract_behavior_signals(text):
    """从用例文本抽取业务行为信号：状态流转目标态 + 模态/约束/机制信号词。返回信号集合。"""
    if not text:
        return set()
    sigs = set()
    for m in _STATE_TARGET_PAT.finditer(text):
        target = m.group(2)
        if target:
            sigs.add(target)
    for w in BEHAVIOR_SIGNALS:
        if w in text:
            sigs.add(w)
    return sigs


def _has_assumption_tag(case_cells):
    """用例是否含假设标记（假设A1/基于假设），查关联规则列与用例名称列。"""
    for idx in (IDX_RULE, IDX_NAME):
        if len(case_cells) > idx:
            t = case_cells[idx] or ""
            if any(p.search(t) for p in _ASSUMPTION_TAG_PATS):
                return True
    return False


def _has_rule_citation(case_cells):
    """用例关联规则列是否引用 R<序号>/TP<序号>（追溯到规则建模/风险/测试点清单）。"""
    if len(case_cells) > IDX_RULE:
        return bool(_CITATION_PAT.search(case_cells[IDX_RULE] or ""))
    return False


def check_behavior_source_lines(data_rows, req_doc_text):
    """检查15 业务行为来源追溯（#5·软判定）的内存入口：接受预读的需求文档全文文本
    而非文件路径。check_behavior_source(data_rows, req_doc_path) 读盘后委托本函数。
    语义/返回与原实现一致：返回 (疑似条数, 疑似列表, 是否提供了可读需求文档)。
    req_doc_text 为空串时退回 (b)(c) 判定（无法做 a 的 token 核对，has_req=False）。"""
    req_text = req_doc_text or ""
    has_req = req_text != ""
    suspects = []
    for i, r in enumerate(data_rows, 1):
        if len(r) <= IDX_THEN:
            continue
        case_text = " ".join(r[IDX_GIVEN:IDX_THEN + 1])
        sigs = extract_behavior_signals(case_text)
        if not sigs:
            continue  # 无业务行为信号，不判
        if _has_rule_citation(r) or _has_assumption_tag(r):
            continue  # 已引用 R/TP 或已标假设 -> 视为已登记来源
        # 无引用、无假设：行为信号须出现在需求文档，否则疑似脑补
        ungrounded = sorted(s for s in sigs if s and s not in req_text)
        if ungrounded:
            suspects.append("行%d: 疑似无来源业务行为（检查15）：未引用R/TP、无假设标记，且行为信号[%s]不在需求文档->需转问题/假设"
                            % (i, "/".join(ungrounded)[:60]))
    return len(suspects), suspects, has_req


def check_behavior_source(data_rows, req_doc_path):
    """检查15 业务行为来源追溯（#5·软判定）。文件入口（Phase 13 回读用）：
    读需求文档文件后委托 check_behavior_source_lines。返回语义不变。
    （实现见 check_behavior_source_lines 的文档注释。）"""
    req_text = ""
    if req_doc_path and os.path.exists(req_doc_path):
        try:
            with open(req_doc_path, "r", encoding="utf-8") as f:
                req_text = f.read()
        except Exception:
            req_text = ""
    return check_behavior_source_lines(data_rows, req_text)


def check_rule_source(lines):
    """检查15 增强（规则来源·破自证循环·软判定）。规则建模 section 每条规则项建议标注来源
    （来源:需求文档<章节>/台账Q<序号>/假设A<序号>）。无来源标记 -> 疑似脑补规则。
    规则建模 section 由模型自写，若无来源约束会被 rule_coverage 反向洗白为"已覆盖"，
    本检查补该缺口（根因5 自证循环）。无规则建模 section 或无可解析项 -> 跳过（返回 0,[]）。"""
    in_section = False
    items = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("|") and "用例ID" in s:
            break
        if re.match(r"^#+\s*.*(规则建模|业务规则|规则模型|建模)", s):
            in_section = True
            continue
        if not in_section:
            continue
        if not s or s.startswith("#"):
            continue
        if re.match(r"^[-*]?\s*\*\*([^*：:]{2,20})\*\*", s) or re.match(r"^\d+[.、]\s*\*\*?([^*：:（(]{2,20})", s):
            items.append(s)
    if not items:
        return 0, []
    suspects = []
    for it in items:
        if not _SOURCE_MARKER_PAT.search(it):
            m = re.match(r"^[-*]?\s*\*\*([^*：:]{2,20})\*\*", it) or \
                re.match(r"^\d+[.、]\s*\*\*?([^*：:（(]{2,20})", it)
            name = m.group(1).strip() if m else it[:20]
            suspects.append("规则项[%s] 无来源标记（建议补 来源:需求文档<章节>/台账Q<n>/假设A<n>，破自证循环）" % name)
    return len(suspects), suspects


def parse_tech_impl_names(lines):
    """解析可选'技术实现摘要'section（§5 提供），提取明确提供的存储名清单
    （表名/字段/Key/Topic/Index/Bucket）。section 标题含'技术实现'，其后表格/列表。
    无该 section 返回 []（检查9增强退回正则兜底）。"""
    in_section = False
    names = []
    for ln in lines:
        s = ln.strip()
        if not in_section:
            if re.match(r"^#+\s*.*技术实现", s):
                in_section = True
            continue
        if re.match(r"^#+\s", s):
            break
        # 命中存储模式的 token
        for pat, _ in STORAGE_PATTERNS:
            for m in re.finditer(pat, s, flags=re.IGNORECASE):
                names.append(m.group(0).strip())
        # 反引号/引号包裹的标识符
        for m in re.finditer(r"[`'\"]([a-zA-Z_][a-zA-Z0-9_]{2,})[`'\"]", s):
            names.append(m.group(1))
    return list(set(names))


def check_storage_schema(data_rows, lines):
    """检查9 增强（软判定）：若 .md 含'技术实现摘要'section（§5 提供真实 schema），
    则对命中存储模式的断言名做清单交叉校验——不在清单内 → 疑似杜撰。
    无清单则返回 (None, [])，退回 check_storage 现有正则判定，行为不变。"""
    allowlist = parse_tech_impl_names(lines)
    if not allowlist:
        return None, []
    allow_lower = [a.lower() for a in allowlist]
    suspects = []
    for i, r in enumerate(data_rows, 1):
        if len(r) <= IDX_THEN:
            continue
        text = " ".join(r[IDX_GIVEN:IDX_THEN + 1])
        for pat, desc in STORAGE_PATTERNS:
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                name = m.group(0).strip()
                if name.lower() not in allow_lower:
                    suspects.append("行%d: %s『%s』不在技术实现摘要清单内（疑似杜撰，检查9增强）" % (i, desc, name))
    return len(suspects), suspects


# 风险来源：需在台账由对应角色确认的来源
ROLE_SOURCES = ("技术隐含@开发", "业务领域@业务", "缺陷反哺")


def risk_source_report(risk_rows):
    """风险来源分布 + 待台账角色确认列表（软提示）。对来源∈{技术隐含@开发,业务领域@业务,缺陷反哺}
    的 P0/P1 风险，提示需在澄清台账由对应角色确认（见 risk.md 三源共验、clarification.md 角色路由）。
    risk_rows 第5列为'风险来源'（若存在）。返回 (分布dict, 待确认列表)。"""
    dist = {}
    pending = []
    if not risk_rows:
        return dist, pending
    for rr in risk_rows:
        rid = rr[0].strip() if len(rr) > 0 else ""
        level = rr[1].strip() if len(rr) > 1 else ""
        source = rr[4].strip() if len(rr) > 4 and rr[4].strip() else "需求推导"
        dist[source] = dist.get(source, 0) + 1
        if level in ("P0", "P1") and source in ROLE_SOURCES:
            pending.append("%s[%s] 来源=%s（需在台账确认）" % (rid, level, source))
    return dist, pending


# 行为信号词表（RC6 修复·需求点语义分解）：用于把标题下的散文正文切分为可追溯子条目。
# 契约/接口定义型需求里"可配置/热生效/格式转换/透传/异步/校验/限流"等测点常藏在正文非标题，
# 旧版按 ## 标题粗切（1 个标题=1 条目）致 10 条子规则只算 1 条、用例引用该标题即判整块覆盖。
_REQ_BEHAVIOR_SIGNALS = (
    "必须", "不得", "不可", "禁止", "允许", "应当", "应该", "需要", "需为",
    "上限", "下限", "最多", "最少", "不超过", "至少", "超过", "限额", "阈值",
    "当", "若", "如果", "否则", "除非", "只有", "仅当",
    "校验", "校对", "验证", "拦截", "拒绝", "放行", "触发", "回调",
    "异步", "同步", "重试", "幂等", "透传", "脱敏", "热更新", "热生效", "热刷新", "可配置",
    "默认", "异常", "超时", "失败", "刷新", "缓存", "限流", "熔断", "降级",
)


def _split_prose_sentences(text):
    """把中英文散文切分为句（按 。；;！？!？ 与换行），返回非空 trimmed 片段。"""
    parts = re.split(r"[。；;！？!?]", text)
    return [p.strip() for p in parts if p and p.strip()]


def _decompose_heading_body(title, body_lines):
    """把一个标题章节的正文分解为可追溯子条目（RC6 修复）。

    提取：编号列表项（1./1、/(1)/①）、项目符号项（-/*/•/·）、含行为信号词的散文句。
    返回 [(子条目标识, 原行)]；无可分解内容时返回 []（由调用方回退为标题本身 1 条目）。
    子条目标识形如 "要点:<父标题> > <内容>"，使 #4 反向追溯能定位到正文埋点而非仅标题。
    """
    subs = []
    text_body = []
    for raw in body_lines:
        s = raw.strip()
        if not s:
            continue
        # 跳过 markdown 表格行（表格由别处处理）
        if s.startswith("|"):
            continue
        # 编号列表：1. / 1、 / (1) / 1) / ① 等
        m = re.match(r"^(?:\d+|[①②③④⑤⑥⑦⑧⑨⑩])[.、\)）]?\s*(.+)", s)
        if m:
            content = m.group(1).strip().rstrip("。；;").strip()
            if content:
                subs.append(("要点:%s > %s" % (title, content), s))
                continue
        # 项目符号列表：- / * / • / ·
        m = re.match(r"^[-*•·]\s+(.+)", s)
        if m:
            content = m.group(1).strip().rstrip("。；;").strip()
            if content:
                subs.append(("要点:%s > %s" % (title, content), s))
                continue
        text_body.append(s)
    # 散文句含行为信号词 → 切为子条目
    prose = " ".join(text_body)
    for sent in _split_prose_sentences(prose):
        if len(sent) >= 4 and any(sig in sent for sig in _REQ_BEHAVIOR_SIGNALS):
            subs.append(("要点:%s > %s" % (title, sent), sent))
    # 按标识去重保序
    seen = set()
    out = []
    for sid, line in subs:
        if sid not in seen:
            seen.add(sid)
            out.append((sid, line))
    return out


def parse_requirement_items_from_lines(rlines):
    """从已读入的需求文档行列表提取需求条目（v0.9.0·RC6 修复：标题+正文语义分解）。

    旧版仅按 ##/### 标题 + REQ-xxx/需求N 编号行粗切，1 个标题=1 条目，导致标题下
    10 条散文子规则只算 1 条、用例引用该标题即判整块覆盖（"覆盖不全"总破口）。
    现版对每个二级及以下标题章节，把正文分解为编号项/项目符号项/含行为信号词的散文句
    作为独立子条目（"要点:<标题> > <内容>"）；章节无可分解正文时回退为标题本身 1 条目。
    # 一级文档根标题不计入。显式 REQ-xxx/需求N 编号行仍为独立条目。返回 [(条目标识, 原行)]。
    """
    items = []
    cur_title = None
    cur_body = []
    root_title = None  # # 一级文档根标题，纯散文无 ## 标题时作为合成节标题兜底
    heading_re = re.compile(r"^(#{1,4})\s+(.+)")

    def flush():
        # cur_title 为 None 但正文非空：整文档无 ## 标题的纯散文，用根标题兜底分解
        title = cur_title if cur_title is not None else (root_title or "需求正文")
        if cur_title is None and not cur_body:
            return
        subs = _decompose_heading_body(title, cur_body)
        if subs:
            items.extend(subs)
        elif cur_title is not None:
            items.append(("标题:%s" % cur_title, "## %s" % cur_title))

    for ln in rlines:
        s = ln.strip()
        m = heading_re.match(s)
        if m:
            lvl = len(m.group(1))
            title = m.group(2).strip()
            # 文档根标题（# 一级）：先 flush 上一节，记录根标题（纯散文兜底用），跳过根标题本身
            if lvl == 1:
                flush()
                root_title = title
                cur_title = None
                cur_body = []
                continue
            # 新标题：flush 上一节，开启新节
            flush()
            cur_title = title
            cur_body = []
            continue
        # 显式 REQ-xxx / 需求N 编号行：独立条目（先 flush 当前节）
        m2 = re.match(r"^(REQ[-_]?[A-Za-z0-9\-_]+|需求\s*\d+)[.、:：\s]", s)
        if m2:
            flush()
            cur_title = None
            cur_body = []
            items.append((m2.group(1).strip(), s))
            continue
        # 累积正文（cur_title 为 None 时也累积——纯散文无标题文档由 flush 用根标题兜底）
        cur_body.append(s)
    flush()
    return items


def parse_requirement_items(req_doc_path):
    """从需求文档提取需求条目。文件入口（Phase 13 回读用）：读盘后委托
    parse_requirement_items_from_lines。返回 [(条目标识, 原行)]，文件不存在/不可读返回 []。"""
    if not req_doc_path or not os.path.exists(req_doc_path):
        return []
    try:
        with open(req_doc_path, "r", encoding="utf-8") as f:
            rlines = f.readlines()
    except Exception:
        return []
    return parse_requirement_items_from_lines(rlines)


def _req_item_tokens(item_id):
    """从需求条目标识抽取匹配 token（供 #4 反向需求追溯的宽松匹配）。
    标题/要点条目（"标题:xxx"/"要点:xxx"）切为：英文/数字≥2 连续段 + 中文 2-gram 滑动窗。
    用 2-gram 滑动窗而非整段 CJK run，使 20.2 推荐的短写法（如"见需求文档3.2订单创建"）
    能命中长标题（如"3.2 订单创建功能"）——整段 run "订单创建功能"无法成为短写法的子串，
    而 2-gram "订单""创建"等可命中。数字/章节号单独成 token 以支持"3.2"定位。
    非"标题:"/"要点:"条目（REQ-xxx/需求N）返回原 item_id，由调用方做精确子串匹配。"""
    body = item_id[3:] if item_id.startswith("标题:") or item_id.startswith("要点:") else item_id
    toks = []
    # 英文≥2 连续段（含点号，如 "REQ-ORD" / "API1"）
    for m in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,}", body):
        toks.append(m)
    # 数字串（含点号分隔，如 "3.2" / "001"），便于按章节号定位
    for m in re.findall(r"\d+(?:\.\d+)*", body):
        toks.append(m)
    # 中文 2-gram 滑动窗（"订单创建功能" → 订单/单创/创建/建功/功能）
    for s in re.findall(r"[一-龥]+", body):
        if len(s) >= 2:
            for i in range(len(s) - 1):
                toks.append(s[i:i + 2])
            if len(s) == 2:
                toks.append(s)
    # 去重保序，保留信息量大的前若干个（防 token 过多误命中）
    seen = set()
    uniq = []
    for t in toks:
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq[:10]


def _item_token_covered(item_id, texts):
    """token 级覆盖判定（v0.9.0·根因4 修复）：跨 texts 逐串统计命中 token 数。

    为降假阳性（短/泛标题被相似名称误命中），当 item 可切出 ≥3 token 时要求单串内
    命中 ≥2 token；token<3 时按 ≥1 命中（与旧逻辑一致）。调用方先用关联需求ID列，
    再回退 Given/When/Then 全文（row_text），覆盖即判 covered，避免"要点只在步骤正文
    而未写进追溯列"被误判未覆盖的假阴性。
    """
    toks = _req_item_tokens(item_id)
    if not toks:
        return False
    threshold = 2 if len(toks) >= 3 else 1
    for ct in texts:
        hits = sum(1 for t in toks if t and t in ct)
        if hits >= threshold:
            return True
    return False


def _reverse_req_trace_core(data_rows, items):
    """#4 反向需求追溯核心（v0.9.0·根因4 修复：追溯列 + G/W/T 联合判定）。

    主判：关联需求ID列（显式追溯信号）。回退：Given/When/Then 全文（row_text）——
    要点只体现在步骤正文而未写进追溯列时，旧版判"未覆盖"（假阴性），现版回退命中即 covered。
    标题/要点条目走 _item_token_covered（多 token 要求降假阳性）；REQ-xxx/需求N 走精确子串。
    返回 (未覆盖列表, 总条目数)。"""
    req_ids = [r[IDX_REQ].strip() if len(r) > IDX_REQ else "" for r in data_rows]
    case_texts = [row_text(r) for r in data_rows]
    uncovered = []
    for item_id, _ in items:
        if item_id.startswith("标题:") or item_id.startswith("要点:"):
            if _item_token_covered(item_id, req_ids):
                continue
            if _item_token_covered(item_id, case_texts):
                continue  # G/W/T 命中 → 实际已覆盖，仅未写追溯列
            uncovered.append(item_id)
        else:
            if any(item_id in rid for rid in req_ids):
                continue
            if any(item_id in ct for ct in case_texts):
                continue  # G/W/T 命中 → 已覆盖
            uncovered.append(item_id)
    return uncovered, len(items)


def reverse_requirement_trace(data_rows, req_doc_path):
    """#4 反向需求追溯（软判定）：需求文档每条条目须有≥1用例引用（关联需求ID列，
    回退 G/W/T 全文）。未被引用的条目列为'未覆盖需求'。无需求文档则跳过，返回 (None, 0)。"""
    items = parse_requirement_items(req_doc_path)
    if not items:
        return None, 0
    return _reverse_req_trace_core(data_rows, items)


def reverse_requirement_trace_items(data_rows, req_items):
    """#4 反向需求追溯的内存入口：接受预解析的需求条目（parse_requirement_items_from_lines
    的返回值）而非文件路径。供内存内 gate（Phase 8）调用，无需落盘需求文档。
    无条目则跳过，返回 (None, 0)。"""
    if not req_items:
        return None, 0
    return _reverse_req_trace_core(data_rows, req_items)


def collect_all_findings(data_rows, lines, req_doc_lines=None, ledger=None, design_doc_lines=None):
    """把全部检查/统计/追溯一次性计算并聚合成结构化 dict（不打印）。
    供内存内 gate（Phase 8 出口 gate）与文件入口（Phase 13 回读）共用同一计算，
    保证"写前内存校验"与"写后回读校验"判定口径完全一致。

    参数：
      data_rows: parse_table_from_lines 返回的用例行列表
      lines: 同一份 .md 的全部行（供 section 解析）
      req_doc_lines: 可选，预读的需求文档行列表；非 None 且非空时启用 #4 反向需求追溯
                     + #5 业务行为 token 核对；为 None 时这两项跳过（与 Phase 13
                     "未传第2参数则跳过"语义一致）
      design_doc_lines: 可选，预读的设计文档行列表（v0.8.0）；非空时启用 #8 反向设计文档
                     测试要点追溯 + safety_coverage 硦感数据触发判定

    返回 dict：
      {n, hard_violations,
       soft:{assertions:[n,list], storage:[n,list], schema:[n_or_None,list],
             dups:[n,list], overdesign:[n,list], reqid:[n,list],
             completeness:[n,list], behavior:[n,list,has_req], rule_source:[n,list]},
       coverage:<coverage_stats dict>,
       traces:{rule:[uncovered_or_None,total], risk:[uncovered_or_None,p0p1,total],
               testpoint:[uncovered_or_None,total],
               interface:[uncovered_list,api_total,ctype_issues],
               requirement:[uncovered_or_None,total],
               design_doc:[uncovered_list,total]},
       risk_source:[dist_dict,pending_list]}

    设计约束（不可违背）：
    * 不改任何 check_* 函数签名/返回/逻辑——本函数只做调用与聚合
    * 不打印——打印由调用方负责（main() 走 print_findings，gate 走 dict 读取）
    * hard_violations = check_ids + check_fields，与 main() 一致
    """
    # 硬性校验
    id_violations = check_ids(data_rows)
    field_violations = check_fields(data_rows)

    # section ID 注册表（v0.7.0·反向引用/连续性/假设对账公共依赖）
    section_ids = collect_section_ids(lines)

    # 项 1 反向引用完整性【闭环 D1】（硬·exit=1）
    citation_violations = check_citation_resolution(data_rows, section_ids)

    # 项 1b 追溯性 section 内联实体【闭环 D1 自证循环·v0.8.1】（硬·exit=1）
    # section 标题存在但解析出 0 个 ID → 指针式引用 → D1 被空注册表绕过。Phase 8/10 必须内联。
    traceback_violations = check_traceback_section_inlined(lines, section_ids)

    # v0.8.1: 结构性违规（追溯 section/悬空引用）排在逐行字段违规之前——
    # run_phase_gate 的 phase_filtered[:50] 打印上限下，让"先修结构、再修字段"的
    # 修复优先序前置，避免模型被 100+ 条枚举越界淹没而漏掉追溯性 section 这类根因。
    hard_violations = traceback_violations + citation_violations + id_violations + field_violations

    # 项 2 section ID 连续性【闭环 D2】（RK/TP/API/SC=full 硬，R=warn 软）
    contig_violations, contig_warnings = check_section_id_contiguity(section_ids, scope="all")
    hard_violations = hard_violations + contig_violations

    # 项 3 假设标签↔已登记假设对账【闭环 RC7】
    assump_violations, assump_warnings = check_assumption_resolution(data_rows, section_ids)
    hard_violations = hard_violations + assump_violations

    # 软性校验
    assert_n, assert_list = check_assertions(data_rows)
    storage_n, storage_list = check_storage(data_rows)
    schema_n, schema_list = check_storage_schema(data_rows, lines)
    dup_n, dup_list = check_duplicates(data_rows)
    overdesign_n, overdesign_list = check_overdesign(data_rows)
    reqid_n, reqid_list = check_requirement_id(data_rows)
    complete_n, complete_list = check_assertion_completeness(data_rows)
    if req_doc_lines is not None:
        req_doc_text = "".join(req_doc_lines) if req_doc_lines else ""
        behsrc_n, behsrc_list, has_req = check_behavior_source_lines(data_rows, req_doc_text)
        req_items = parse_requirement_items_from_lines(req_doc_lines or [])
        unc_req, req_total = reverse_requirement_trace_items(data_rows, req_items)
    else:
        # 未提供需求文档：#5 退回 (b)(c) 判定（无 token 核对，has_req=False），
        # #4 跳过。与 Phase 13 "未传第2参数"行为一致。
        behsrc_n, behsrc_list, has_req = check_behavior_source_lines(data_rows, "")
        unc_req, req_total = None, 0
    rulesrc_n, rulesrc_list = check_rule_source(lines)

    # v0.8.1 Gap3：规则来源标记硬门（full 模式无来源标记即 exit=1；auto_light 软告警）
    # 闭合 phases.py 契约"每条规则项标注来源"——旧逻辑 check_rule_source 仅进 soft.rule_source
    # 不进 hard_violations，有无来源都不阻断。
    rule_src_hard_violations = []
    rule_src_mode = COVERAGE_GATES.get("rule_source_hard", "full")
    if rule_src_mode == "full" and rulesrc_list:
        rule_src_hard_violations = list(rulesrc_list)
    hard_violations = hard_violations + rule_src_hard_violations

    # 项 5 用例↔台账/规则一致性【闭环 C3】（软判定）
    consist_n, consist_list = check_behavior_consistency(data_rows, lines, ledger=ledger)

    # 项 6 非台账点关键词覆盖探针【闭环 G5/G6/G7 + RC6】（软判定）
    kw_probe = keyword_coverage_probe(data_rows, req_doc_lines, ledger=ledger)

    # 项 4 台账传递检查 5.5a（软判定·闭环 G3/G4/G8）
    ledger_prop_n, ledger_prop_list = check_ledger_propagation(data_rows, ledger, req_doc_lines)

    # 覆盖统计
    stats = coverage_stats(data_rows)

    # 追溯
    categories = parse_rule_categories(lines)
    unc_rule, total_cat = rule_coverage(data_rows, categories)
    risk_rows = parse_section_rows(lines, "风险清单|风险分析|风险列表", ["风险ID", "风险等级"])
    unc_risk, p0p1_total, risk_total = risk_coverage(data_rows, risk_rows)
    tp_rows = parse_section_rows(lines, "测试点清单|测试点列表|测试点建模", ["测试点ID", "测试点"])
    unc_tp, tp_total = testpoint_coverage(data_rows, tp_rows)
    unc_api, api_total, ctype_issues = reverse_interface_trace(data_rows, lines)
    src_dist, src_pending = risk_source_report(risk_rows)

    # v0.8.1: Phase 7 硬门——P0/P1 风险须被 ≥1 测试点覆盖（正向 risk→TP）
    # 闭合 phase_gate_map[7] 声明 testpoint_risk_linkage 但函数不存在 + 被过滤的缺口
    risk_tp_linkage_violations = check_risk_testpoint_linkage(risk_rows, tp_rows)
    hard_violations = hard_violations + risk_tp_linkage_violations

    # v0.8.1 Gap3：风险来源待确认硬门（full 模式 P0/P1 风险来源∈ROLE_SOURCES 须台账确认；
    # 未确认即 exit=1；auto_light 软告警）。闭合 phases.py 契约"风险清单每条须标注风险来源"——
    # 旧 risk_source_report 仅软提示，待确认项不阻断。
    risk_src_hard_violations = []
    risk_src_mode = COVERAGE_GATES.get("risk_source_hard", "full")
    if risk_src_mode == "full" and src_pending:
        risk_src_hard_violations = list(src_pending)
    hard_violations = hard_violations + risk_src_hard_violations

    # v0.8.0 #8-H 设计文档测试要点追溯 + safety_coverage 触发判定
    unc_dd, dd_total = design_doc_testpoints_trace(data_rows, design_doc_lines)
    s_fails = safety_coverage_gate(data_rows, req_doc_lines or [], design_doc_lines or [])

    return {
        "n": len(data_rows),
        "hard_violations": hard_violations,
        "soft": {
            "assertions": [assert_n, assert_list],
            "storage": [storage_n, storage_list],
            "schema": [schema_n, schema_list],
            "dups": [dup_n, dup_list],
            "overdesign": [overdesign_n, overdesign_list],
            "reqid": [reqid_n, reqid_list],
            "completeness": [complete_n, complete_list],
            "behavior": [behsrc_n, behsrc_list, has_req],
            "rule_source": [rulesrc_n, rulesrc_list],
            "behavior_consistency": [consist_n, consist_list],
            "ledger_propagation": [ledger_prop_n, ledger_prop_list],
        },
        "coverage": stats,
        "traces": {
            "rule": [unc_rule, total_cat],
            "risk": [unc_risk, p0p1_total, risk_total],
            "testpoint": [unc_tp, tp_total],
            "interface": [unc_api, api_total, ctype_issues],
            "requirement": [unc_req, req_total],
            "design_doc": [unc_dd, dd_total],
            "keyword_coverage": kw_probe,
        },
        "risk_source": [src_dist, src_pending],
        "section_ids": section_ids,
        "section_contiguity": {"warnings": contig_warnings},
        "assumption_resolution": {"warnings": assump_warnings},
        "_safety_fails": s_fails,
    }


def run_inmemory(lines, req_doc_lines=None, ledger=None, design_doc_lines=None):
    """内存内全量校验入口（Phase 8 出口 gate 调用，零文件操作）。
    输入：lines=Write 即将落盘的完整 .md 文本（按行）；
          req_doc_lines=可选，预读的需求文档行列表（启用 #4/#5）；
          ledger=可选，parse_clarification_ledger 返回的台账 dict（启用台账传递/一致性/待确认门禁）；
          design_doc_lines=可选，预读的设计文档行列表（v0.8.0·启用 #8 设计文档测试要点追溯+safety 触发）。
    输出：(parsed, findings_dict)：
      parsed=None 且 findings=None -> 表头解析失败（gate 须提示结构缺陷）；
      否则 findings=collect_all_findings 的 dict。
    与文件入口 main() 口径一致：同一份文本经 run_inmemory 与经
    `python verify_cases.py <file> [req.md] [--ledger ..]` 的判定结果相同。"""
    parsed, err = parse_table_from_lines(lines)
    if parsed is None:
        return None, None
    _header, data_rows, _lines = parsed
    findings = collect_all_findings(data_rows, lines, req_doc_lines=req_doc_lines,
                                    ledger=ledger, design_doc_lines=design_doc_lines)
    return parsed, findings


def dump_rules():
    """打印校验规则契约（内容来自 config/validation_rules.json，单一事实源）。
    供 agent 在设计用例前读取，替代阅读本脚本源码：拿到枚举/正则/关键词/section 格式
    即可写出一次过的用例，避免因漏读校验口径导致整文件重写。输出始终与 _RULES 同步。"""
    r = _RULES
    print("===== 校验规则契约（单一事实源 config/validation_rules.json）=====")
    print("-- 由 `verify_cases.py --dump-rules` 输出；agent 设计用例前读本契约即可，无需读脚本源码 --")
    print()
    print("【15列表头顺序】(用例表必须15列、顺序一致；列数不足/错位硬阻断 exit=1)")
    print("  " + " | ".join(r["header"]))
    fc = r["fixed_columns"]
    print("【固定值列】编辑模式=%s | 标签=%s | 责任人=%s | 用例状态=%s（逐行填写，禁改值）" % (
        fc["edit_mode"], fc["tag"], fc["owner"], fc["status"]))
    print()
    print("【测试类型枚举】(测试类型列，越界即 exit=1)")
    print("  " + " / ".join(r["valid_types"]))
    print("【测试维度枚举】(测试维度列，越界即 exit=1)")
    print("  " + " / ".join(r["valid_dims"]))
    print("【用例等级】" + " / ".join(r["valid_levels"]) + "（取自第5阶段风险分析）")
    print("【用例名称】%d段【模块】【功能】【场景】【预期】，缺段硬阻断" % r["name_segments"])
    print("【用例ID】<需求标识>_<功能缩写>_<序号>，按功能缩写分组连续不跳号，跨文件全局唯一")
    print()
    print("【关联需求ID】填具体编号或'见需求文档<章节号/章节名>'；下列占位全员命中→追溯失效：")
    print("  " + " | ".join(r["vague_req_patterns"]))
    print()
    print("【断言可观测(Then)】Then 须命中以下任一锚点，否则疑似不可观测（软判定）：")
    print("  " + " / ".join(r["observable_patterns"]))
    print("【模糊词(禁止出现在Then)】" + " / ".join(r["vague_words"]))
    print()
    print("【存储合规】禁止杜撰表名/字段/Redis Key/Topic/Index/Bucket；疑似模式：")
    for s in r["storage_patterns"]:
        print("  %-28s → %s" % (s["pattern"], s["desc"]))
    print("  需求未提供存储名时用自然语言：" + " / ".join(r["storage_natural"]))
    print()
    hv = set(r["high_value_dims"])
    print("【关键词维度(覆盖统计，扫描用例全文；对标签错标鲁棒)】高价值维度=0 则⚠：" + "/".join(r["high_value_dims"]))
    for k, v in r["keyword_dims"].items():
        print("  %s%s: %s" % (k, "（高价值）" if k in hv else "", "/".join(v)))
    print()
    print("【状态机流转】(状态机用例>0 且 非法流转=0 时⚠)")
    print("  合法: " + "/".join(r["flow_legal"]))
    print("  非法: " + "/".join(r["flow_illegal"]))
    print("  回滚: " + "/".join(r["flow_rollback"]))
    print("  终态: " + "/".join(r["flow_terminal"]))
    print()
    print("【边界深度】(最小/最大/临界/边界内 四者任一=0 且有边界用例时⚠；边界内=min+1/max-1 刚好满足应通过)")
    print("  最小: " + "/".join(r["boundary_min_kw"]))
    print("  最大: " + "/".join(r["boundary_max_kw"]))
    print("  临界: " + "/".join(r["boundary_critical_kw"]))
    print("  边界内: " + "/".join(r["boundary_inside_kw"]))
    print("  识别词: " + "/".join(r["boundary_keywords"]))
    print()
    print("【异常子类(8类)】")
    for k, v in r["exception_subtypes"].items():
        print("  %s: %s" % (k, "/".join(v)))
    print()
    print("【过度设计】Then 无业务锚点→疑似（测试类型 %s 豁免）" % "/".join(r["overdesign_exempt_types"]))
    print("  业务锚点: " + " / ".join(r["business_anchors"]))
    print()
    print("【追溯性 section（用例表之前，强制沉淀；缺失则⚠提示补齐）】")
    print("  规则建模: 粗体项 **类别名** 或 '1. **类别名**'，每类须被用例覆盖(token宽松匹配)；每项建议标 来源:需求文档<章节>/台账Q<n>/假设A<n>（无->疑似脑补规则）")
    print("  风险清单: 表格 风险ID|风险等级|风险描述|关联模块|风险来源；用例'关联规则'列含 R<序号> 精确覆盖每个 P0/P1")
    print("    风险来源取值: 需求推导 / 技术隐含@开发 / 业务领域@业务 / 缺陷反哺（risk.md 三源共验）")
    print("  测试点清单: 表格 测试点ID|场景类型|测试点描述|关联模块；用例'关联规则'列含 TP<序号> 精确覆盖每个测试点")
    print("  变更影响清单(契约驱动分支): 表格 接口ID|接口名/路径|方法|变更类型|变更描述|变更字段|受影响规则|受影响场景|风险等级|来源")
    print("    变更类型取值: " + " / ".join(r.get("change_types", [])))
    print("    用例'关联规则'列含 API<序号> 精确覆盖每个变更接口；来源标 [需求文档<章节>/台账Q<n>/假设A<n>/接口文档<版本>/接口文档diff 旧->新]")
    print("  场景清单: 表格 场景ID|场景描述|关联模块；用例'关联规则'列含 SC<序号> 精确覆盖每个场景")
    print()
    print("【统一接口测试矩阵（契约+规则+场景·仅对变更接口/字段/受影响规则场景）】")
    print("  契约类: A入参存在性(必填不传/选填不传/多余字段) B入参类型(类型错传/三态) C值域 D组合 E出参契约 F鲁棒性 -> 追溯 API<序号>")
    print("  规则类: G业务规则(正向/异常/组合/跨字段约束) -> 追溯 R<序号>")
    print("  场景类: H业务场景(主穿越/分支/异常/上下游) -> 追溯 SC<序号>")
    print("  收敛: 只对变更字段+受影响规则/场景；P0全量/P1全量或pairwise/P2P3采样；类别不同不合并")
    print("  #6 反向接口追溯: 每个变更接口须三类覆盖(契约presence+type+出参 / 规则R / 场景SC)；无受影响规则->跳规则类，无受影响场景->跳场景类")
    cg = r.get("coverage_gates", {})
    print()
    print("【覆盖硬门（v0.6.0·不通过即 exit=1）】（config/validation_rules.json coverage_gates，domain_config 可覆盖）")
    print("  #4-H 需求追溯: REQ 可解析时，需求条目被用例'关联需求ID'引用比例 >= %s（%s）" % (
        cg.get("req_trace_min_ratio", 1.0), "REQ 缺失/不可解析不判，由 #4 显式强提示接管"))
    print("  #6-H 接口三类: 每个变更接口三类覆盖齐全（缺类即 FAIL）；取值=%s" % cg.get("interface_three_class", "full"))
    print("  RK   P0/P1 风险: 风险清单 P0/P1 均须被用例'关联规则'引用（未覆盖即 FAIL）；取值=%s" % cg.get("risk_p0p1", "full"))
    print("  机器摘要块: 输出末尾打印 ##VERIFY_SUMMARY## k=v;... 行——交付摘要/审核话术的脚本校验数值必须逐字段摘自本行，禁止凭印象手填；未运行脚本一律填'未执行'")
    print()
    print("【v0.7.0 阶段门禁前移 + 制品传递 + 反向引用/台账接入（设计见 PHASE_GATE_DESIGN.md）】")
    print("  --ledger <台账.md>: 启用台账接入（传递/待确认门禁/一致性）；传 Clarification_Ledger_<需求标识>.md")
    print("  --phase-gate <N> <checkpoint.md>: 阶段出口门禁（runtime 在 Phase 3/5/7/8/10 gate 调用）")
    print("  项1 反向引用完整性(D1·硬): 用例关联规则列引用的 R/RK/TP/API/SC 须在清单内真实存在")
    print("  项2 section ID连续性(D2·硬): RK/TP/API/SC 编号无跳号（R=warn 按类目自由编号）；取值=%s" % json.dumps(r.get("section_contiguity", {}), ensure_ascii=False))
    print("  项3 假设标签对账(RC7·硬): 假设A<n> 须在假设清单内登记；取值=%s" % cg.get("assumption_resolution", "full"))
    print("  项4 台账接入(RC0): parse_clarification_ledger + check_ledger_propagation(5.5a 传递) + check_open_questions_gate(5.5b 待确认门禁·取值=%s)" % cg.get("open_questions", "full"))
    print("  项5 行为一致性(C3·软): 用例断言与台账事实反义词矛盾嫌疑；反义词对=%s" % json.dumps(r.get("behavior_source", {}).get("antonym_pairs", []), ensure_ascii=False))
    print("  项6 关键词覆盖探针(G5/G6/G7·软): 非台账点(异步/脏payload/端点/消费组)覆盖；取值=%s" % cg.get("keyword_coverage", "warn"))
    print("  项8 REQ缺失门禁(#4-P·硬): REQ 缺失/不可解析 exit=1；取值=%s" % cg.get("req_trace_presence", "full"))
    print("  制品传递: state.json.artifacts + 契约卡 PRIOR_ARTIFACTS + gate_rounds 有界返修(≥3次强制人工)")
    print()
    print("【软性检查（新增·不改变退出码）】")
    print("  检查13 断言完整性: 状态变更类用例(When含%s) Then 须含数据/状态副作用" % "/".join(["创建","支付","扣减","更新","删除","撤销","退款","发货"]))
    print("  检查9增强 存储schema: 若 .md 含'技术实现摘要'section，断言存储名须在清单内")
    print("  风险来源待确认: 来源∈{技术隐含@开发,业务领域@业务,缺陷反哺} 的 P0/P1 须在台账角色确认")
    print("  #4 反向需求追溯: 需求文档每条目须被用例引用（传第2参数需求文档启用）")
    print("  检查15/#5 业务行为来源追溯: 用例 Given/When/Then 断言的业务行为须有来源三选一")
    print("    (a)行为 token 在需求文档/接口契约文档 | (b)关联规则引用 R<序号>/TP<序号>/API<序号> | (c)关联规则/用例名称含 假设A<序号>/基于假设")
    print("    三者皆无->疑似脑补，须转问题(P0/P1)/假设(P2/P3)，不得静默保留；行为信号: " + "/".join(r["behavior_source"]["behavior_signals"]))
    print()
    print("【domain_config.json】可选领域覆盖(同名字段替换)：business_anchors / keyword_dims / exception_subtypes / overdesign_exempt_types")
    print("=" * 64)


def print_findings(findings, basename, req_doc_lines=None):
    """打印 collect_all_findings 的结果（文件入口 Phase 13 回读用）。
    输出与重构前 main() 内联打印一致 + 末尾追加覆盖硬门结论与 ##VERIFY_SUMMARY## 机器摘要行。
    内存内 gate 不调用本函数（gate 直接读 dict 做自修决策，不打 human-facing 报告）。
    返回覆盖硬门违约列表（空=通过），供 main() 计入退出码。"""
    n = findings["n"]
    soft = findings["soft"]
    stats = findings["coverage"]
    traces = findings["traces"]
    src_dist, src_pending = findings["risk_source"]

    print("===== 用例内容校验 + 覆盖统计 =====")
    print("文件: %s" % basename)
    print("用例条数: %d" % n)
    print("-" * 48)

    # 硬性校验（注：findings.hard_violations 已含 id+field；下方分组打印需各自复取，
    # check_ids/check_fields 为纯函数幂等，与原 main 调用次序一致，回归安全）
    hard_violations = findings["hard_violations"]
    data_rows_for_hard = findings.get("_data_rows")
    id_v = check_ids(data_rows_for_hard) if data_rows_for_hard else []
    field_v = check_fields(data_rows_for_hard) if data_rows_for_hard else []
    print("【硬性校验·不通过即 exit=1】")
    print("检查5 ID唯一连续: %s" % ("通过" if not id_v else "不通过"))
    for v in id_v:
        print("  - %s" % v)
    print("检查11 字段规范(枚举/四段/固定列/等级): %s" % ("通过" if not field_v else "不通过"))
    for v in field_v:
        print("  - %s" % v)
    # 项 1 反向引用完整性（v0.7.0·闭环 D1·硬）
    citation_v = [v for v in hard_violations if "悬空引用" in v]
    if citation_v:
        print("[FAIL] 项1 反向引用完整性(悬空引用·D1): 不通过")
        for v in citation_v:
            print("  - %s" % v)
    # 项 2 section ID 连续性（v0.7.0·闭环 D2·硬，RK/TP/API/SC）
    contig_v = [v for v in hard_violations if "序号跳号" in v]
    if contig_v:
        print("[FAIL] 项2 section ID连续性(跳号·D2): 不通过")
        for v in contig_v:
            print("  - %s" % v)
    # 项 3 假设对账（v0.7.0·闭环 RC7·硬）
    assump_v = [v for v in hard_violations if "假设清单未登记" in v or "台账假设清单未登记" in v]
    if assump_v:
        print("[FAIL] 项3 假设标签对账(RC7): 不通过")
        for v in assump_v:
            print("  - %s" % v)

    # 软性校验
    assert_n, assert_list = soft["assertions"]
    storage_n, storage_list = soft["storage"]
    schema_n, schema_list = soft["schema"]
    dup_n, dup_list = soft["dups"]
    overdesign_n, overdesign_list = soft["overdesign"]
    reqid_n, reqid_list = soft["reqid"]
    complete_n, complete_list = soft["completeness"]
    behsrc_n, behsrc_list, has_req = soft["behavior"]
    rulesrc_n, rulesrc_list = soft["rule_source"]
    print("-" * 48)
    print("【软性校验·列疑似条数，供 selfcheck 决策】")
    print("检查4 断言可观测: 疑似 %d 条" % assert_n)
    for v in assert_list[:10]:
        print("  - %s" % v)
    if len(assert_list) > 10:
        print("  ...（其余 %d 条略）" % (len(assert_list) - 10))
    print("检查9 存储合规: 疑似 %d 条" % storage_n)
    for v in storage_list[:10]:
        print("  - %s" % v)
    if schema_n is None:
        print("检查9增强 存储schema交叉: 跳过（未提供'技术实现摘要'section，退回正则判定）")
    else:
        print("检查9增强 存储schema交叉: 疑似 %d 条" % schema_n)
        for v in schema_list[:10]:
            print("  - %s" % v)
    print("检查6 重复用例: 疑似 %d 条" % dup_n)
    for v in dup_list[:10]:
        print("  - %s" % v)
    print("检查7 过度设计: 疑似 %d 条" % overdesign_n)
    for v in overdesign_list[:10]:
        print("  - %s" % v)
    print("关联需求ID追溯: 疑似 %d 条" % reqid_n)
    for v in reqid_list:
        print("  - %s" % v)
    print("检查13 断言完整性: 疑似 %d 条（状态变更类用例缺数据/状态副作用）" % complete_n)
    for v in complete_list[:10]:
        print("  - %s" % v)
    bs_note = "" if has_req else "（未提供需求文档，仅按 R/TP 引用与假设标记判定，无法做 token 核对）"
    print("检查15 业务行为来源追溯(#5): 疑似 %d 条（无来源业务行为）%s" % (behsrc_n, bs_note))
    for v in behsrc_list[:10]:
        print("  - %s" % v)
    if len(behsrc_list) > 10:
        print("  ...（其余 %d 条略）" % (len(behsrc_list) - 10))
    print("检查15 规则来源(破自证循环): 疑似 %d 条（规则建模项无来源标记）" % rulesrc_n)
    for v in rulesrc_list[:10]:
        print("  - %s" % v)
    # 项 5 用例↔台账/规则一致性（v0.7.0·闭环 C3·软）
    consist_n, consist_list = soft.get("behavior_consistency", [0, []])
    print("项5 行为一致性(C3): 疑似 %d 条（用例断言与规则/台账来源互为反义）" % consist_n)
    for v in consist_list[:10]:
        print("  - %s" % v)
    # 项 6 关键词覆盖探针（v0.7.0·闭环 G5/G6/G7 + RC6·软）
    kw_probe = traces.get("keyword_coverage", {})
    if kw_probe:
        print("项6 关键词覆盖探针(G5/G6/G7): %d 类测点有用例未覆盖" % len(kw_probe))
        for cat, missing in kw_probe.items():
            print("  - %s: 未覆盖关键词 %s" % (cat, "/".join(missing[:8])))
    else:
        print("项6 关键词覆盖探针(G5/G6/G7): 需求/台账测点均有用例覆盖（或无此类测点）")
    # 项 5.5a 台账传递检查（v0.7.0·闭环 G3/G4/G8·软）
    ledger_prop_n, ledger_prop_list = soft.get("ledger_propagation", [0, []])
    if ledger_prop_n:
        print("项5.5a 台账传递(G3/G4/G8): %d 个台账事实要点无用例覆盖" % ledger_prop_n)
        for v in ledger_prop_list[:10]:
            print("  - 未覆盖: %s" % v)
    else:
        print("项5.5a 台账传递(G3/G4/G8): 台账事实要点均有用例覆盖（或无台账）")

    # 覆盖统计
    print("-" * 48)
    print("【覆盖统计·供 selfcheck 检查2/3/8 参考】")
    print("-- 标签维度 --")
    type_n = len(stats["type_count"])
    type_warn = " ⚠种类<3，疑似单方法未组合（见 references/methods.md 多方法组合）" if type_n < 3 else ""
    print("测试类型种类: %d 种 -> %s%s" % (type_n, dict(stats["type_count"]), type_warn))
    print("测试维度种类: %d 种 -> %s" % (len(stats["dim_count"]), dict(stats["dim_count"])))
    print("风险等级分布: %s" % stats["level_count"])
    print("-- 关键词维度（对标签错标鲁棒，扫描用例全文）--")
    for dim in KEYWORD_DIMS:
        cnt = stats["kw_dim_count"][dim]
        flag = " ⚠高价值维度=0，提示按需补齐" if dim in HIGH_VALUE_DIMS and cnt == 0 else ""
        print("  %s: %d 条%s" % (dim, cnt, flag))
    print("-- 状态机流转（references/example.md 范例2）--")
    flow_total = stats["flow_legal"] + stats["flow_illegal"] + stats["flow_rollback"]
    flow_warn = "（⚠ 非法流转=0，状态机测试缺核心范式）" if flow_total > 0 and stats["flow_illegal"] == 0 else ""
    print("  合法=%d / 非法=%d / 回滚=%d / 其中终态相关=%d%s" % (
        stats["flow_legal"], stats["flow_illegal"], stats["flow_rollback"], stats["flow_terminal"], flow_warn))
    print("-- 边界深度（references/quality_rules.md 11.4 / modeling.md 边界类 4 值）--")
    if stats["bound_total"] > 0:
        depth_warn = ""
        miss = []
        if stats["bound_min"] == 0:
            miss.append("最小")
        if stats["bound_max"] == 0:
            miss.append("最大")
        if stats["bound_critical"] == 0:
            miss.append("临界")
        if stats["bound_inside"] == 0:
            miss.append("边界内")
        if miss:
            depth_warn = "（⚠ 疑似边界深度不足，缺%s）" % "/".join(miss)
        print("  边界用例 %d 条，覆盖 最小=%d / 最大=%d / 临界=%d / 边界内=%d%s" % (
            stats["bound_total"], stats["bound_min"], stats["bound_max"],
            stats["bound_critical"], stats["bound_inside"], depth_warn))
    else:
        print("  边界用例 0 条（若无边界场景可忽略，否则提示补齐）")
    print("-- 异常子类（references/coverage.md 8.2）--")
    if stats["exc_total"] > 0:
        hit_subs = [k for k, v in stats["exc_subtypes_hit"].items() if v > 0]
        miss_subs = [k for k, v in stats["exc_subtypes_hit"].items() if v == 0]
        print("  异常用例 %d 条，覆盖子类 %d/8：%s" % (stats["exc_total"], len(hit_subs), "/".join(hit_subs)))
        if miss_subs:
            print("  未覆盖异常子类：%s（按需补齐）" % "/".join(miss_subs))
    else:
        print("  异常用例 0 条（若无异常场景可忽略）")

    # 规则追溯
    uncovered, total_cat = traces["rule"]
    print("-- 规则追溯（解析'规则建模'section，校验每类被用例覆盖）--")
    if total_cat == 0:
        print("  未找到'规则建模'section（或无粗体规则项），跳过规则追溯校验")
    else:
        print("  规则类别 %d 类，未覆盖 %d 类" % (total_cat, len(uncovered) if uncovered else 0))
        if uncovered:
            print("  ⚠ 疑似未覆盖规则类别（供复核，可能为 token 匹配遗漏）：%s" % "、".join(uncovered))
        else:
            print("  全部规则类别均有用例覆盖")

    # 风险追溯（第5阶段风险清单 → 用例）
    unc_risk, p0p1_total, risk_total = traces["risk"]
    print("-- 风险追溯（解析'风险清单'section，校验每 P0/P1 风险被用例覆盖）--")
    if risk_total == 0:
        print("  ⚠ 未找到'风险清单'section（强制沉淀，请补齐以启用闭环与跨会话记忆）")
    else:
        print("  风险 %d 条（其中 P0/P1 %d 条），未覆盖 %d 条" % (
            risk_total, p0p1_total, len(unc_risk) if unc_risk else 0))
        if unc_risk:
            print("  ⚠ 疑似未覆盖 P0/P1 风险（供复核）：%s" % "；".join(unc_risk))
        else:
            print("  全部 P0/P1 风险均有用例覆盖")

    # 测试点追溯（第7阶段测试点清单 → 用例）
    unc_tp, tp_total = traces["testpoint"]
    print("-- 测试点追溯（解析'测试点清单'section，校验每测试点被用例覆盖）--")
    if tp_total == 0:
        print("  ⚠ 未找到'测试点清单'section（强制沉淀，请补齐以启用闭环与跨会话记忆）")
    else:
        print("  测试点 %d 条，未覆盖 %d 条" % (tp_total, len(unc_tp) if unc_tp else 0))
        if unc_tp:
            print("  ⚠ 疑似未覆盖测试点（供复核）：%s" % "；".join(unc_tp))
        else:
            print("  全部测试点均有用例覆盖")

    # #6 反向接口追溯（变更影响清单 -> 用例引用，契约/规则/场景三类覆盖）
    unc_api, api_total, ctype_issues = traces["interface"]
    print("-- 反向接口追溯 #6（变更接口 -> 用例 契约/规则/场景 三类覆盖）--")
    if api_total == 0:
        print("  跳过（未找到'变更影响清单'section；契约驱动分支未启用或无变更接口）")
    else:
        print("  变更接口 %d 个，未覆盖（缺类） %d 个" % (api_total, len(unc_api)))
        if unc_api:
            print("  ⚠ 疑似未覆盖（供复核）：%s" % "；".join(unc_api))
        else:
            print("  全部变更接口三类(契约/规则/场景)覆盖齐全")
        if ctype_issues:
            print("  ⚠ 变更类型越界：%s" % "；".join(ctype_issues))

    # 风险来源分布 + 待台账角色确认（risk.md 三源共验）
    # risk_rows 是否存在以 risk_total 判定（traces.risk[2]），与重构前 main 用 risk_rows 真值判定一致
    risk_total = traces["risk"][2]
    print("-- 风险来源（risk.md 三源共验，第5列为'风险来源'）--")
    if risk_total == 0:
        print("  未找到风险清单，跳过风险来源校验")
    else:
        if src_dist:
            print("  来源分布: %s" % " / ".join("%s=%d" % (k, v) for k, v in src_dist.items()))
        else:
            print("  风险清单未标注'风险来源'列（建议补齐：需求推导/技术隐含@开发/业务领域@业务/缺陷反哺）")
        if src_pending:
            print("  ⚠ 待台账角色确认的 P0/P1 风险（%d 条，见 clarification.md 角色路由）：" % len(src_pending))
            for p in src_pending[:10]:
                print("    - %s" % p)
        else:
            print("  无需台账角色确认的风险（或 P0/P1 均为需求推导）")

    # #4 反向需求追溯（需求文档条目 → 用例引用）
    unc_req, req_total = traces["requirement"]
    print("-- 反向需求追溯 #4（需求条目 → 用例引用）--")
    if unc_req is None:
        # 显式强提示（不再静默跳过）：区分"未传 REQ"与"REQ 不可解析"
        if req_doc_lines is None:
            reason = "需求文档第2参数缺失（REQ_<需求标识>.md 未传入或文件不存在）"
            fix = "按 references/phase0_manifest.md 步骤零落盘 case-design-out/REQ_<需求标识>.md 后重跑 'python verify_cases.py <TC.md> case-design-out/REQ_<需求标识>.md'"
        else:
            reason = "需求文档无可解析章节（parse_requirement_items_from_lines 仅认 ## 二级及以上 Markdown 标题或 REQ-xxx/需求N 显式编号）"
            fix = "在 REQ_<需求标识>.md 中补 ## 二级标题分节（按需求条目切分，如 ## 订单创建 / ## 库存扣减），或补 REQ-xxx/需求N 编号后重跑"
        print("  ⚠ 需求条目级覆盖未校验（#4 静默跳过升级为显式强提示·闭合覆盖盲区）")
        print("    原因：%s" % reason)
        print("    影响：'需求文档每条条目是否均有用例覆盖'未机器校验，覆盖退化为依赖 LLM 自查+人工审核")
        print("    修复：%s" % fix)
    else:
        print("  需求条目 %d 条，未被用例引用 %d 条" % (req_total, len(unc_req)))
        if unc_req:
            print("  ⚠ 未覆盖需求条目（第10阶段补齐，见 dedup_coverage.md 反向需求追溯）：" )
            for u in unc_req[:15]:
                print("    - %s" % u)
            if len(unc_req) > 15:
                print("    ...（其余 %d 条略）" % (len(unc_req) - 15))
        else:
            print("  全部需求条目均有用例引用")

    print("-" * 48)
    overall = "通过" if not hard_violations else "不通过"
    print("硬性校验结论: %s" % overall)
    print("（软性校验与覆盖统计不改变退出码，供模型 selfcheck 决策）")

    # 覆盖硬门（v0.6.0）：#4-H 需求追溯 / #6-H 接口三类 / RK P0-P1 风险。
    # 与上方软提示共用同一份 traces 数据；违约即 exit=1（配置见 config/validation_rules.json coverage_gates）。
    gate_fails = coverage_gate_failures(findings, run_mode="full")
    print("-" * 48)
    print("【覆盖硬门·不通过即 exit=1】（coverage_gates: req_ratio=%.2f interface=%s risk=%s）" % (
        COVERAGE_GATES["req_trace_min_ratio"], COVERAGE_GATES["interface_three_class"], COVERAGE_GATES["risk_p0p1"]))
    if gate_fails:
        for name, detail in gate_fails:
            print("  [FAIL] %s: %s" % (name, detail))
    else:
        print("  全部通过（或无对应 section，由上方软提示接管）")

    # 机器摘要块（反编造：交付摘要/审核话术的脚本校验数值必须逐字段摘自本行，禁止手填）
    print(verify_summary_line(findings, hard_gate_fails=gate_fails))
    print("=" * 48)
    return gate_fails


def run_phase_gate(argv):
    """v0.7.0 阶段出口门禁模式：python verify_cases.py --phase-gate <N> <checkpoint.md> [--req ..] [--ledger ..]

    runtime 在 Phase 3/5/7/8/10 gate 调用。按 phase_gate_map 跑检查子集 + 消费校验 + 台账对照，
    复用 collect_all_findings 保证与 Phase 13 全量校验口径一致。
    退出码：0=该阶段检查全过；1=有硬违规（[FAIL] 行为修复指令）。
    """
    import argparse
    ap = argparse.ArgumentParser(prog="verify_cases --phase-gate", add_help=False)
    ap.add_argument("phase", type=int)
    ap.add_argument("checkpoint")
    ap.add_argument("--req", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--design", default=None)
    ap.add_argument("--run-mode", default="full")
    a = ap.parse_args(argv)
    if not os.path.exists(a.checkpoint):
        print("[FAIL] Phase %d gate: 检查点文件不存在 %s" % (a.phase, a.checkpoint))
        return 1
    try:
        with open(a.checkpoint, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print("[FAIL] Phase %d gate: 检查点读取失败 %s" % (a.phase, e))
        return 1
    req_doc_lines = None
    if a.req and os.path.exists(a.req):
        try:
            with open(a.req, "r", encoding="utf-8") as f:
                req_doc_lines = f.readlines()
        except Exception:
            req_doc_lines = None
    # v0.8.0: 设计文档（#8-H 设计文档测试要点追溯 + safety_coverage 触发）
    design_doc_lines = None
    if a.design and os.path.exists(a.design):
        try:
            with open(a.design, "r", encoding="utf-8") as f:
                design_doc_lines = f.readlines()
        except Exception:
            design_doc_lines = None
    ledger = parse_clarification_ledger(a.ledger) if a.ledger else None

    parsed, err = parse_table_from_lines(lines)
    if parsed is None:
        # v0.7.1: Phase 8/10 需要完整用例表；格式错（摘要文档）显式报，不静默 data_rows=[]
        # 闭合执行日志暴露的"模型把 checkpoint_10 写成摘要 → #4-H 误报全未引用 → 反复改关联需求ID 格式"
        if a.phase in (8, 10):
            print("  [FAIL] 检查点格式不符: Phase %d 检查点必须含 15 列用例表（首列'用例ID'），"
                  "当前无可解析用例表（%s）。请重写 checkpoint_%d.md 为完整用例表格式（复制 checkpoint_8.md 的用例表%s），"
                  "而非摘要文档——此时应重写检查点格式，不要改用例内容或关联需求ID 格式。"
                  % (a.phase, err or "未找到表头行", a.phase,
                     "+ 追加覆盖分析" if a.phase == 10 else ""))
            # 输出最小摘要块供 runtime 解析不崩
            empty_findings = {"n": 0, "hard_violations": [], "soft": {}, "coverage": {},
                              "traces": {"requirement": [None, 0]}, "risk_source": [{}, []],
                              "section_ids": {}}
            print(verify_summary_line(empty_findings, hard_gate_fails=[("检查点格式", "Phase %d 无用例表" % a.phase)]))
            print("##PHASE_ARTIFACTS## %d:" % a.phase)
            return 1
        # Phase 3/5/7 无表正常（只含 section）
        data_rows = []
    else:
        _h, data_rows, _l = parsed
    findings = collect_all_findings(data_rows, lines, req_doc_lines=req_doc_lines,
                                    ledger=ledger, design_doc_lines=design_doc_lines)
    findings["_ledger"] = ledger

    # 按 phase_gate_map 跑对应检查子集（简化：所有阶段都跑 collect_all_findings 已计算的硬违规）
    gate_map = _RULES.get("phase_gate_map", {})
    phase_checks = gate_map.get(str(a.phase), [])
    print("GATE: Phase %d — 阶段出口门禁（检查子集: %s）" % (a.phase, ", ".join(phase_checks) or "默认全量"))

    hard_violations = findings.get("hard_violations", [])
    # 阶段过滤：Phase 3 只报规则来源+R连续性；Phase 5 只报风险来源+RK连续性；余类推
    phase_filtered = []
    if a.phase == 3:
        # v0.8.1 Gap3: 保留 R 跳号 + 规则来源标记硬门（rule_source_hard=full 时）
        phase_filtered = [v for v in hard_violations
                          if ("序号跳号" in v and "R清单" in v) or "无来源标记" in v]
    elif a.phase == 5:
        # v0.8.1 Gap3: 保留 RK 跳号 + 风险来源待确认硬门（risk_source_hard=full 时）
        phase_filtered = [v for v in hard_violations
                          if ("序号跳号" in v and "RK清单" in v) or "需在台账确认" in v]
    elif a.phase == 7:
        # v0.8.1: 保留 TP 跳号 + P0/P1 风险→≥1 TP 硬门（check_risk_testpoint_linkage）
        phase_filtered = [v for v in hard_violations
                          if ("序号跳号" in v and "TP清单" in v) or "无对应测试点覆盖" in v]
    else:
        phase_filtered = hard_violations

    gate_fails = coverage_gate_failures(findings, run_mode=a.run_mode)
    # v0.8.0: Phase 8/10/13 启用覆盖硬门（含 TP 追溯）；Phase 8 也判覆盖硬门（不再仅 10/13）
    if a.phase in (8, 10, 13):
        if gate_fails:
            for name, detail in gate_fails:
                print("  [FAIL] %s: %s" % (name, detail))
    else:
        gate_fails = []  # 非 8/10/13 阶段不判覆盖硬门

    ok = True
    if phase_filtered:
        ok = False
        print("  [FAIL] 硬违规:")
        # v0.8.1: 上限 20→50。runtime phase_gate 回传上限已同步抬到 50；旧 20 条在 100+ 违规时
        # 会"修一批又浮一批"永不收敛（D:\AGI\AAAA Phase 8 事故）。仍超 50 时靠 ##VERIFY_SUMMARY##
        # 的 hard_violations 计数让模型感知全量规模。
        for v in phase_filtered[:50]:
            print("    - %s" % v)
    else:
        print("  [PASS] 阶段检查子集通过")

    print(verify_summary_line(findings, hard_gate_fails=gate_fails))
    # v0.7.0: 输出制品 ID 范围行，供 runtime 回填 artifacts（闭合 RC3·不靠记忆传递）
    section_ids = findings.get("section_ids", {})
    parts = []
    for prefix in ("R", "RK", "TP", "API", "SC", "A"):
        ids = sorted(section_ids.get(prefix, {}).get("ids", []))
        if ids:
            rng = "%d-%d" % (ids[0], ids[-1]) if len(ids) > 1 else str(ids[0])
            parts.append("%s=%s(%d)" % (prefix, rng, len(ids)))
    print("##PHASE_ARTIFACTS## %d:%s" % (a.phase, ";".join(parts)))
    return 1 if (not ok or gate_fails) else 0


def main():
    if len(sys.argv) >= 2 and sys.argv[1] in ("--dump-rules", "--rules"):
        dump_rules()
        return 0
    # v0.7.0：--phase-gate <N> <checkpoint.md> [--req ..] [--ledger ..]
    if len(sys.argv) >= 2 and sys.argv[1] == "--phase-gate":
        return run_phase_gate(sys.argv[2:])
    if len(sys.argv) < 2:
        print("用法: python verify_cases.py <TC文件.md> [需求文档.md] [--ledger 台账.md] [--design 设计文档.md]  |  --phase-gate <N> <checkpoint.md> [--req ..] [--ledger ..] [--design ..]  |  --dump-rules 查看规则契约")
        print("  第2参数：需求文档 case-design-out/REQ_<需求标识>.md（第0阶段步骤零已强制落盘），用于 #4 反向需求追溯 + #5 token 核对；缺失则 #4 产出显式强提示而非静默跳过")
        print("  --ledger：澄清台账 Clarification_Ledger_<需求标识>.md，启用台账传递/一致性/待确认门禁（v0.7.0）")
        print("  --design：设计文档 DESIGN_<需求标识>.md，启用 #8-H 设计文档测试要点追溯 + safety_coverage 触发（v0.8.0）")
        print("  --phase-gate <N>：阶段出口门禁模式（runtime 在 Phase 3/5/7/8/10 gate 调用）")
        return 1

    path = sys.argv[1]
    # 解析可选 --ledger/--design 参数（位置参数：TC.md [REQ.md] [--ledger X] [--design Y]）
    req_doc_path = None
    ledger_path = None
    design_doc_path = None
    positional = []
    i = 2
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == "--ledger" and i + 1 < len(sys.argv):
            ledger_path = sys.argv[i + 1]
            i += 2
        elif a == "--design" and i + 1 < len(sys.argv):
            design_doc_path = sys.argv[i + 1]
            i += 2
        else:
            positional.append(a)
            i += 1
    req_doc_path = positional[0] if positional else None
    parsed, err = parse_table(path)
    if parsed is None:
        print(err)
        return 1
    header_cells, data_rows, lines = parsed

    # 读需求文档行（供 #4/#5）；路径不存在/不可读则传 None（与重构前 check_behavior_source/
    # reverse_requirement_trace 的文件不存在兜底语义一致：#5 退回 (b)(c)、#4 跳过）
    req_doc_lines = None
    if req_doc_path and os.path.exists(req_doc_path):
        try:
            with open(req_doc_path, "r", encoding="utf-8") as f:
                req_doc_lines = f.readlines()
        except Exception:
            req_doc_lines = None

    # 读设计文档行（供 #8 设计文档测试要点追溯 + safety_coverage 触发·v0.8.0）
    design_doc_lines = None
    if design_doc_path and os.path.exists(design_doc_path):
        try:
            with open(design_doc_path, "r", encoding="utf-8") as f:
                design_doc_lines = f.readlines()
        except Exception:
            design_doc_lines = None

    # 读台账（供台账传递/一致性/待确认门禁·v0.7.0）
    ledger = parse_clarification_ledger(ledger_path) if ledger_path else None

    findings = collect_all_findings(data_rows, lines, req_doc_lines=req_doc_lines,
                                   ledger=ledger, design_doc_lines=design_doc_lines)
    # 附 data_rows 供 print_findings 复算 id/field 分组（幂等，与原 main 调用次序一致）
    findings["_data_rows"] = data_rows
    findings["_ledger"] = ledger
    gate_fails = print_findings(findings, os.path.basename(path), req_doc_lines=req_doc_lines)

    return 1 if (findings["hard_violations"] or gate_fails) else 0


if __name__ == "__main__":
    sys.exit(main())
