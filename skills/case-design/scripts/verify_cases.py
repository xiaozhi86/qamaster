#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_cases.py — 测试用例 .md 内容级校验 + 覆盖统计（Tier B 降本脚本）

用途：TestCases_<需求标识>.md 落盘后，由 skill 经 Bash 在第13阶段回读环节
与 verify_md.py 串联调用（见 references/output_write.md）。
verify_md.py 只校验“结构”（行数/表头/末行/列宽）；本脚本进一步校验
“内容层 + 覆盖广度 + 追溯性”，把 references/selfcheck.md 中【可机器判定】的
检查项客观化，并在覆盖广度不足时给出客观数据，供模型判定 selfcheck 自修项是否通过。

【设计不变】本脚本不新增门禁、不改变 selfcheck 的 14 项检查、不改变自修/阻断
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
  关联需求ID追溯：笼统占位/全员相同→需求条目级追溯失效（软判定，对应 modeling.md 20.2）

覆盖统计（给 selfcheck 检查2/3/8 客观数据，不替代模型判定，只供证据）：
  - 标签维度：测试类型种类数、测试维度种类数、风险等级分布
  - 关键词维度（对测试类型标签错标鲁棒，扫描用例全文）：并发/幂等/安全/上下游/时间组合
  - 状态机流转：合法/非法/回滚/终态（非法流转为状态机核心，0 则提示）
  - 边界深度：边界用例是否覆盖 最小/最大/临界 三值
  - 异常子类：异常用例覆盖的子类数（输入/数据/状态/权限/服务/网络/缓存/MQ）
  - 规则追溯：解析“规则建模”section 的规则类别，校验每类是否被用例覆盖
  - 风险追溯：解析“风险清单”section，校验每 P0/P1 风险是否被用例覆盖
  - 风险来源：解析第5列“风险来源”，对技术隐含@开发/业务领域@业务/缺陷反哺来源的 P0/P1 提示需台账角色确认
  - 测试点追溯：解析“测试点清单”section，校验每测试点是否被用例覆盖
  - #4 反向需求追溯：解析需求文档条目（第2参数），列出未被用例引用的需求条目
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
BOUNDARY_KEYWORDS = list(_RULES["boundary_keywords"])
BOUNDARY_MIN_KW = list(_RULES["boundary_min_kw"])
BOUNDARY_MAX_KW = list(_RULES["boundary_max_kw"])
BOUNDARY_CRITICAL_KW = list(_RULES["boundary_critical_kw"])

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
    KEYWORD_DIMS = _DOMAIN_CFG["keyword_dims"]
if "exception_subtypes" in _DOMAIN_CFG:
    EXCEPTION_SUBTYPES = _DOMAIN_CFG["exception_subtypes"]
if "overdesign_exempt_types" in _DOMAIN_CFG:
    OVERDESIGN_EXEMPT_TYPES = set(_DOMAIN_CFG["overdesign_exempt_types"])


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


def parse_table(path):
    """解析 .md 中的用例表，返回 (header_cells, data_rows, full_lines)。"""
    if not os.path.exists(path):
        return None, "文件不存在: %s" % path
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        return None, "读取失败: %s" % e

    header_idx = None
    header_cells = None
    for i, ln in enumerate(lines):
        cells = split_row(ln)
        if cells and "用例ID" in cells[0]:
            header_idx = i
            header_cells = cells
            break
    if header_idx is None:
        return None, "未找到表头行（含‘用例ID’的表格行）"

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
    """标签维度覆盖统计（原有）+ 关键词维度 + 状态机 + 边界深度 + 异常子类。"""
    type_count = {}
    dim_count = {}
    level_count = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    flow_legal = flow_illegal = flow_rollback = flow_terminal = 0
    kw_dim_count = {k: 0 for k in KEYWORD_DIMS}
    bound_total = 0
    bound_min = bound_max = bound_critical = 0
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
        "exc_total": exc_total, "exc_subtypes_hit": exc_subtypes_hit,
    }


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


def parse_requirement_items(req_doc_path):
    """从需求文档提取需求条目（标题行 # + 显式编号 REQ-xxx / 需求N）。
    返回 [(条目标识, 原行)]。文件不存在/不可读返回 []。"""
    if not req_doc_path or not os.path.exists(req_doc_path):
        return []
    try:
        with open(req_doc_path, "r", encoding="utf-8") as f:
            rlines = f.readlines()
    except Exception:
        return []
    items = []
    heading_level = 99
    for ln in rlines:
        s = ln.strip()
        m = re.match(r"^(#{1,4})\s+(.+)", s)
        if m:
            lvl = len(m.group(1))
            title = m.group(2).strip()
            # 跳过文档根标题（# 一级），只取二级及以下章节为需求条目
            if lvl == 1:
                continue
            if lvl < heading_level:
                heading_level = lvl
            items.append(("标题:%s" % title, s))
            continue
        m = re.match(r"^(REQ[-_]?[A-Za-z0-9\-_]+|需求\s*\d+)[.、:：\s]", s)
        if m:
            items.append((m.group(1).strip(), s))
    return items


def reverse_requirement_trace(data_rows, req_doc_path):
    """#4 反向需求追溯（软判定）：需求文档每条条目须有≥1用例引用（关联需求ID列）。
    未被引用的条目列为'未覆盖需求'。无需求文档（未传第2参数）则跳过，返回 (None, 0)。"""
    items = parse_requirement_items(req_doc_path)
    if not items:
        return None, 0
    req_ids = [r[IDX_REQ].strip() if len(r) > IDX_REQ else "" for r in data_rows]
    uncovered = []
    for item_id, _ in items:
        if item_id.startswith("标题:"):
            toks = re.findall(r"[一-龥]{2,}|[A-Za-z]{2,}", item_id[3:])
            toks = toks[:3]
            if toks and not any(any(tok in rid for tok in toks) for rid in req_ids):
                uncovered.append(item_id)
        else:
            if not any(item_id in rid for rid in req_ids):
                uncovered.append(item_id)
    return uncovered, len(items)


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
    print("【边界深度】(最小/最大/临界 三者任一=0 且有边界用例时⚠)")
    print("  最小: " + "/".join(r["boundary_min_kw"]))
    print("  最大: " + "/".join(r["boundary_max_kw"]))
    print("  临界: " + "/".join(r["boundary_critical_kw"]))
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
    print("  规则建模: 粗体项 **类别名** 或 '1. **类别名**'，每类须被用例覆盖(token宽松匹配)")
    print("  风险清单: 表格 风险ID|风险等级|风险描述|关联模块|风险来源；用例'关联规则'列含 R<序号> 精确覆盖每个 P0/P1")
    print("    风险来源取值: 需求推导 / 技术隐含@开发 / 业务领域@业务 / 缺陷反哺（risk.md 三源共验）")
    print("  测试点清单: 表格 测试点ID|场景类型|测试点描述|关联模块；用例'关联规则'列含 TP<序号> 精确覆盖每个测试点")
    print()
    print("【软性检查（新增·不改变退出码）】")
    print("  检查13 断言完整性: 状态变更类用例(When含%s) Then 须含数据/状态副作用" % "/".join(["创建","支付","扣减","更新","删除","撤销","退款","发货"]))
    print("  检查9增强 存储schema: 若 .md 含'技术实现摘要'section，断言存储名须在清单内")
    print("  风险来源待确认: 来源∈{技术隐含@开发,业务领域@业务,缺陷反哺} 的 P0/P1 须在台账角色确认")
    print("  #4 反向需求追溯: 需求文档每条目须被用例引用（传第2参数需求文档启用）")
    print()
    print("【domain_config.json】可选领域覆盖(同名字段替换)：business_anchors / keyword_dims / exception_subtypes / overdesign_exempt_types")
    print("=" * 64)


def main():
    if len(sys.argv) >= 2 and sys.argv[1] in ("--dump-rules", "--rules"):
        dump_rules()
        return 0
    if len(sys.argv) < 2:
        print("用法: python verify_cases.py <TC文件.md> [需求文档.md]  |  --dump-rules 查看规则契约")
        print("  第2参数（可选）：需求文档，用于 #4 反向需求追溯")
        return 1

    path = sys.argv[1]
    req_doc_path = sys.argv[2] if len(sys.argv) >= 3 else None
    parsed, err = parse_table(path)
    if parsed is None:
        print(err)
        return 1
    header_cells, data_rows, lines = parsed
    n = len(data_rows)

    print("===== 用例内容校验 + 覆盖统计 =====")
    print("文件: %s" % os.path.basename(path))
    print("用例条数: %d" % n)
    print("-" * 48)

    # 硬性校验
    id_violations = check_ids(data_rows)
    field_violations = check_fields(data_rows)
    hard_violations = id_violations + field_violations
    print("【硬性校验·不通过即 exit=1】")
    print("检查5 ID唯一连续: %s" % ("通过" if not id_violations else "不通过"))
    for v in id_violations:
        print("  - %s" % v)
    print("检查11 字段规范(枚举/四段/固定列/等级): %s" % ("通过" if not field_violations else "不通过"))
    for v in field_violations:
        print("  - %s" % v)

    # 软性校验
    assert_n, assert_list = check_assertions(data_rows)
    storage_n, storage_list = check_storage(data_rows)
    schema_n, schema_list = check_storage_schema(data_rows, lines)
    dup_n, dup_list = check_duplicates(data_rows)
    overdesign_n, overdesign_list = check_overdesign(data_rows)
    reqid_n, reqid_list = check_requirement_id(data_rows)
    complete_n, complete_list = check_assertion_completeness(data_rows)
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

    # 覆盖统计
    stats = coverage_stats(data_rows)
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
    print("-- 边界深度（references/quality_rules.md 11.4）--")
    if stats["bound_total"] > 0:
        depth_warn = ""
        if stats["bound_min"] == 0 or stats["bound_max"] == 0 or stats["bound_critical"] == 0:
            miss = []
            if stats["bound_min"] == 0:
                miss.append("最小")
            if stats["bound_max"] == 0:
                miss.append("最大")
            if stats["bound_critical"] == 0:
                miss.append("临界")
            depth_warn = "（⚠ 疑似边界深度不足，缺%s）" % "/".join(miss)
        print("  边界用例 %d 条，覆盖 最小=%d / 最大=%d / 临界=%d%s" % (
            stats["bound_total"], stats["bound_min"], stats["bound_max"], stats["bound_critical"], depth_warn))
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
    categories = parse_rule_categories(lines)
    uncovered, total_cat = rule_coverage(data_rows, categories)
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
    risk_rows = parse_section_rows(lines, "风险清单|风险分析|风险列表", ["风险ID", "风险等级"])
    unc_risk, p0p1_total, risk_total = risk_coverage(data_rows, risk_rows)
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
    tp_rows = parse_section_rows(lines, "测试点清单|测试点列表|测试点建模", ["测试点ID", "测试点"])
    unc_tp, tp_total = testpoint_coverage(data_rows, tp_rows)
    print("-- 测试点追溯（解析'测试点清单'section，校验每测试点被用例覆盖）--")
    if tp_total == 0:
        print("  ⚠ 未找到'测试点清单'section（强制沉淀，请补齐以启用闭环与跨会话记忆）")
    else:
        print("  测试点 %d 条，未覆盖 %d 条" % (tp_total, len(unc_tp) if unc_tp else 0))
        if unc_tp:
            print("  ⚠ 疑似未覆盖测试点（供复核）：%s" % "；".join(unc_tp))
        else:
            print("  全部测试点均有用例覆盖")

    # 风险来源分布 + 待台账角色确认（risk.md 三源共验）
    src_dist, src_pending = risk_source_report(risk_rows)
    print("-- 风险来源（risk.md 三源共验，第5列为'风险来源'）--")
    if not risk_rows:
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
    unc_req, req_total = reverse_requirement_trace(data_rows, req_doc_path)
    print("-- 反向需求追溯 #4（需求条目 → 用例引用）--")
    if unc_req is None:
        print("  跳过（未传需求文档第2参数，或文档无可解析章节；传 'python verify_cases.py <TC.md> <REQ.md>' 启用）")
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
    print("=" * 48)

    return 1 if hard_violations else 0


if __name__ == "__main__":
    sys.exit(main())
