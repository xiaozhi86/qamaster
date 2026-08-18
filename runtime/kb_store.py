#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kb_store.py — KB_lessons.md 自我进化经验库的 read-modify-write（Runtime 独占）

设计原则：KB_lessons 是跨需求共享可变资源，**所有变更必须经本模块**，
且调用方须在 `locking.FileLock` 内调用。模型被明确禁止 Write/Edit
KB_lessons.md（强化"进化机制与模型无关"铁律；经验内容归属人类）。

格式：注释围栏 + `key: value` 行（标量原样、列表/字典用 JSON 字面量）。
stdlib 可解析、git-diff 友好。文件头置模型禁写横幅。

本模块仅做解析/序列化/记录级操作，不持锁、不写 state。
仅用 Python 标准库——机制层与模型无关（铁律，不可妥协）。
"""
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

# 围栏正则：<!-- @kb:record start id=KB-lesson-a1b2 -->
RECORD_START = re.compile(r"<!--\s*@kb:record\s+start\s+id=([^\s>]*)\s*-->")
RECORD_END = "<!-- @kb:record end -->"

_HEADER_LINES_LESSON = [
    "# 自我进化经验库 KB_lessons",
    "",
    "> 本文件为跨需求共享的经验知识库（错误纠正沉淀 / 自我进化）。",
    "> 由 qamaster Runtime 在纠正发生时自动沉淀候选经验(draft)，经人工背书(endorse)后注入。",
    "> **模型禁止 Write/Edit 本文件**（进化机制与模型无关铁律；经验内容归属人类）。",
    "> 经验原文为人类纠正原话(verbatim)；Runtime 仅做确定性捕获/去重/检索/注入。",
    "",
    "---",
    "",
]
_HEADER_LINES_BUSINESS = [
    "# 业务历史知识库 KB_business",
    "",
    "> 本文件为跨需求共享的业务知识索引（聚合自 Knowledge_*.md 元数据+维度文本）。",
    "> 由 qamaster Runtime 经 `kb reconcile --kind business` 聚合（非自动触发）。",
    "> **模型禁止 Write/Edit 本文件**（进化机制与模型无关铁律；业务知识内容归属人类）。",
    "> Knowledge_*.md 内容是既有模型产物(Phase 14)；本机制只索引不生成——聚合/检索/注入全 stdlib。",
    "",
    "---",
    "",
]
_HEADER_LINES_EXPERT = [
    "# 专家知识库 KB_expert",
    "",
    "> 本文件为跨需求共享的通用测试设计方法论库（从用户纠正中提炼、跨需求复用）。",
    "> 由 qamaster Runtime 经 `kb add-expert` 沉淀 draft、人工 `kb endorse` 后注入 ##PRIOR_EXPERT_KB##。",
    "> **只存通用方法知识，不记录具体业务知识**（业务知识归 Knowledge_*.md/KB_business）。",
    "> **模型禁止 Write/Edit 本文件**（进化机制与模型无关铁律；方法论内容归属人类）。",
    "> 仅 endorsed 或 occ≥3 记录才注入（v0.11.11 重开 occ≥3 逃生口）——错方法论污染所有未来设计，质量优先于速度；occ≥3 是强现实信号而非模型自信。",
    "",
    "---",
    "",
]


def _header(kind="lesson"):
    """按 kind 选文件头横幅（lesson/business/expert 分离，同结构同禁写纪律）。"""
    if kind == "business":
        return list(_HEADER_LINES_BUSINESS)
    if kind == "expert":
        return list(_HEADER_LINES_EXPERT)
    return list(_HEADER_LINES_LESSON)

# 记录字段默认值（单一事实源；序列化与解析共用）
_DEFAULT_REC = {
    "kind": "lesson", "id": "", "phase": "", "dimension": "通用",
    "error_type": "人工纠正", "module": "", "source_req": "",
    "source_reqs": [], "captured": "", "supersedes": [], "superseded_by": [],
    "occurrences": 1, "status": "draft", "trigger": [], "raw_text": "",
    "variants": [],
    # expert 专用（kind=expert）：通用测试设计方法论的结构化字段。
    # lesson/business 记录携带空默认值，既有行为不变（共享 schema）。
    "category": "", "applicable_phases": [], "principle": "",
}

# 需 JSON 解析的列表/字典字段（标量字段按原样字符串）
_JSON_FIELDS = {"source_reqs", "supersedes", "superseded_by", "trigger", "variants", "applicable_phases"}

# surface map 子进程 memoize 缓存（进程内，键=skill_dir）
_surf_cache = {}


def _today():
    return time.strftime("%Y-%m-%d")


def _is_json_field(key):
    return key in _JSON_FIELDS


def parse_records(text):
    """解析 KB_lessons.md 文本 -> records: list[dict]。

    仅在 `<!-- @kb:record start id=... -->` ... `<!-- @kb:record end -->`
    围栏内提取记录；其余文本（含文件头横幅）忽略。无记录 -> []。
    容错：未知字段忽略；非法 JSON 值退空列表；occurrences 非法退 1。
    """
    records = []
    if not text:
        return records
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i].strip()
        m = RECORD_START.match(ln)
        if not m:
            i += 1
            continue
        rec = dict(_DEFAULT_REC)
        rec["id"] = m.group(1).strip()
        i += 1
        # 读到 RECORD_END 为止
        while i < n and lines[i].strip() != RECORD_END:
            field_ln = lines[i].strip()
            if field_ln and ":" in field_ln:
                key, _, val = field_ln.partition(":")
                key = key.strip()
                val = val.strip()
                if key in _DEFAULT_REC:
                    if _is_json_field(key):
                        try:
                            rec[key] = json.loads(val) if val else []
                        except (ValueError, TypeError):
                            rec[key] = []
                    elif key == "occurrences":
                        try:
                            rec[key] = int(val)
                        except ValueError:
                            rec[key] = 1
                    else:
                        rec[key] = val
            i += 1
        records.append(rec)
        # i 现在指向 end 行或越界；外层循环自增跳过 end
    return records


def serialize(records, kind="lesson"):
    """记录列表 -> KB*.md 文本（含文件头横幅 + 记录围栏）。kind 选横幅。"""
    out = _header(kind)
    if not records:
        if kind == "business":
            out.append("<!-- 暂无业务知识记录。kb reconcile --kind business 后聚合 Knowledge_*.md。 -->")
        elif kind == "expert":
            out.append("<!-- 暂无专家方法论记录。kb add-expert 沉淀 draft、endorse 后注入。 -->")
        else:
            out.append("<!-- 暂无经验记录。纠正发生时 Runtime 自动沉淀 draft。 -->")
        out.append("")
        return "\n".join(out)
    for r in records:
        rid = r.get("id") or ""
        out.append("<!-- @kb:record start id=%s -->" % rid)
        out.append("kind: %s" % r.get("kind", "lesson"))
        out.append("id: %s" % rid)
        out.append("phase: %s" % r.get("phase", ""))
        out.append("dimension: %s" % r.get("dimension", "通用"))
        out.append("error_type: %s" % r.get("error_type", "人工纠正"))
        out.append("module: %s" % (r.get("module") or ""))
        out.append("source_req: %s" % (r.get("source_req") or ""))
        out.append("source_reqs: %s" % json.dumps(r.get("source_reqs") or [], ensure_ascii=False))
        out.append("captured: %s" % (r.get("captured") or ""))
        out.append("supersedes: %s" % json.dumps(r.get("supersedes") or [], ensure_ascii=False))
        out.append("superseded_by: %s" % json.dumps(r.get("superseded_by") or [], ensure_ascii=False))
        out.append("occurrences: %d" % (r.get("occurrences", 1) or 1))
        out.append("status: %s" % r.get("status", "draft"))
        out.append("trigger: %s" % json.dumps(r.get("trigger") or [], ensure_ascii=False))
        # raw_text 单行（折叠换行，保持 verbatim 文本但避免破坏行结构）
        raw = r.get("raw_text") or ""
        raw = " ".join(str(raw).splitlines()).strip()
        out.append("raw_text: %s" % raw)
        out.append("variants: %s" % json.dumps(r.get("variants") or [], ensure_ascii=False))
        # expert 专用结构化字段（lesson/business 为空默认值，序列化对齐）
        out.append("category: %s" % (r.get("category") or ""))
        out.append("applicable_phases: %s" % json.dumps(r.get("applicable_phases") or [], ensure_ascii=False))
        out.append("principle: %s" % (r.get("principle") or ""))
        out.append("<!-- @kb:record end -->")
        out.append("")
    return "\n".join(out)


def load_records(path):
    """读取 KB 文件 -> records；不存在返回 []。损坏不抛（best-effort）。"""
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    return parse_records(text)


def _atomic_write(path, text):
    """原子写：mkstemp + os.replace（镜像 manifest._atomic_write 140-161）。

    4 次 PermissionError 退避重试（Windows 文件占用常见）；失败清理临时文件。
    """
    d = os.path.dirname(path) or "."
    if not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".kb_lessons.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        for attempt in range(4):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                time.sleep(0.1 * (2 ** attempt))
        # 最后一次 os.replace 重试失败则抛
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _save_records(path, records, kind="lesson"):
    """原子写记录列表。kind 透传 serialize 选横幅。

    business/lessons/expert 分文件、单文件内 kind 一致：records 非空时按首条记录 kind 推断，
    保证共享的 upsert_lesson/endorse/supersede/prune 写 business/expert 文件时也能选对横幅，
    无需调用方显式传 kind。空记录回退：路径名含 business/expert 则用对应横幅，否则 kind 参数。
    """
    if records and isinstance(records[0], dict) and records[0].get("kind"):
        kind = records[0]["kind"]
    elif not records:
        base = os.path.basename(path).lower()
        if "business" in base:
            kind = "business"
        elif "expert" in base:
            kind = "expert"
    _atomic_write(path, serialize(records, kind=kind))


def _find(records, rec_id):
    for i, r in enumerate(records):
        if r.get("id") == rec_id:
            return i
    return -1


def fingerprint(r):
    """结构键指纹的 sha1 前 12 位（按 kind 派发前缀）。

    - lesson（经验）：键=(phase, dimension)。error_type 对 fail/patch 恒为"人工纠正"
      不入指纹；不同措辞留 variants 不拆类 -> occurrences 真能跨需求累积
      （否则永远=1，自我进化特性失效）。前缀 `KB-lesson-`。
    - business（业务知识）：键=(module, dimension)。同模块同维度跨需求累积
      （module 取 Knowledge 元数据"更新模块"，人类标注，非模型生成）。前缀 `KB-business-`。
    - expert（通用方法论）：键=(category, principle[:40])。同类方法不同 principle 各自一条；
      同 principle 跨需求只 occ++ 不拆类（方法论收敛而非发散）。前缀 `KB-expert-`。
    """
    kind = r.get("kind", "lesson")
    if kind == "business":
        key = "%s|%s" % (r.get("module", ""), r.get("dimension", "通用"))
        return "KB-business-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    if kind == "expert":
        key = "%s|%s" % (r.get("category", ""), (r.get("principle") or "")[:40])
        return "KB-expert-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    key = "%s|%s" % (r.get("phase", ""), r.get("dimension", "通用"))
    return "KB-lesson-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _normalize_rec(rec):
    """规范传入记录：仅保留已知字段，补默认值。"""
    out = dict(_DEFAULT_REC)
    for k in _DEFAULT_REC:
        if k in rec and rec[k] is not None:
            out[k] = rec[k]
    return out


def upsert_lesson(path, rec):
    """插入或合并经验记录（指纹去重）。返回指纹 id。

    命中同类指纹：occurrences 仅对不同 source_req +1，trigger 取并集，
    variants 无损追加；raw_text/captured 更新为最新。新类则追加。
    调用方须在 locking.FileLock 内调用。
    """
    records = load_records(path)
    rec = _normalize_rec(rec)
    fp = fingerprint(rec)
    idx = _find(records, fp)
    if idx >= 0:
        r = records[idx]
        # 规范 source_reqs：若空则从 source_req 初始化
        src_reqs = list(r.get("source_reqs") or [])
        if not src_reqs and r.get("source_req"):
            src_reqs = [r["source_req"]]
        new_req = rec.get("source_req") or ""
        if new_req and new_req not in src_reqs:
            src_reqs.append(new_req)
            r["occurrences"] = (r.get("occurrences", 1) or 1) + 1
        r["source_reqs"] = src_reqs
        r["trigger"] = sorted(set(r.get("trigger") or []) | set(rec.get("trigger") or []))
        if rec.get("raw_text"):
            r.setdefault("variants", []).append({"from": new_req, "text": rec["raw_text"]})
        r["captured"] = rec.get("captured") or r.get("captured") or _today()
        r["raw_text"] = rec.get("raw_text") or r.get("raw_text") or ""
        r["module"] = r.get("module") or rec.get("module") or ""
    else:
        rec["id"] = fp
        src_reqs = list(rec.get("source_reqs") or [])
        if not src_reqs and rec.get("source_req"):
            src_reqs = [rec["source_req"]]
        rec["source_reqs"] = src_reqs
        if not rec.get("variants") and rec.get("raw_text"):
            rec["variants"] = [{"from": rec.get("source_req") or "", "text": rec["raw_text"]}]
        if not rec.get("captured"):
            rec["captured"] = _today()
        if not rec.get("occurrences"):
            rec["occurrences"] = 1
        records.append(rec)
    _save_records(path, records)
    return fp


def get_surface_map(skill_dir):
    """经子进程取 verify_cases.py 的 surface 词表（单一真源，零漂移）。

    调用 `python verify_cases.py --dump-surface-map`，解析其
    `json.dumps(_CLARIFY_CATEGORIES)` 输出。进程内 memoize（键=skill_dir）。
    失败返回 {}（不阻断，best-effort）。
    """
    if skill_dir in _surf_cache:
        return _surf_cache[skill_dir]
    script = os.path.join(skill_dir, "scripts", "verify_cases.py")
    try:
        proc = subprocess.run(
            [sys.executable, script, "--dump-surface-map"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30,
        )
        out = proc.stdout or ""
        m = json.loads(out) if out.strip() else {}
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        m = {}
    _surf_cache[skill_dir] = m
    return m


def list_records(path, status=None, phase=None, dimension=None):
    """只读返回记录列表（供 kb list 输出 JSON；可按 status/phase/dimension 过滤）。"""
    records = load_records(path)
    out = []
    for r in records:
        if status and r.get("status") != status:
            continue
        if phase and str(r.get("phase")) != str(phase):
            continue
        if dimension and r.get("dimension") != dimension:
            continue
        out.append(r)
    return out


def get_record(path, rec_id):
    """返回单条记录（供 kb show）；不存在返回 None。"""
    for r in load_records(path):
        if r.get("id") == rec_id:
            return r
    return None


def endorse(path, rec_id):
    """draft -> endorsed（人工背书）。返回 (ok, message)。调用方须持锁。"""
    records = load_records(path)
    idx = _find(records, rec_id)
    if idx < 0:
        return (False, "经验 id 不存在: %s" % rec_id)
    if records[idx].get("status") == "endorsed":
        return (True, "已是 endorsed: %s" % rec_id)
    records[idx]["status"] = "endorsed"
    _save_records(path, records)
    return (True, "endorsed id=%s" % rec_id)


def endorse_all(path, kind=None):
    """批量背书：所有非 superseded_by 且 status==draft 的记录置 endorsed（一键背书）。

    v0.11.11：闭合 RC-c（单条 endorse 摩擦）——用户回「通过」即全背。返回 (count, message)。
    `kind` 可选过滤（lesson/business/expert），None 全库。调用方须持锁。
    """
    records = load_records(path)
    count = 0
    for r in records:
        if r.get("superseded_by"):
            continue
        if r.get("status") != "draft":
            continue
        if kind is not None and r.get("kind") != kind:
            continue
        r["status"] = "endorsed"
        count += 1
    if count:
        _save_records(path, records)
    return (count, "endorsed %d draft(s)" % count)


def supersede(path, old_id, new_id):
    """老经验被新经验取代：老 superseded_by += [new]，新 supersedes += [old]。

    检索跳过被废止者。返回 (ok, message)。调用方须持锁。
    """
    records = load_records(path)
    oi = _find(records, old_id)
    ni = _find(records, new_id)
    if oi < 0:
        return (False, "老经验 id 不存在: %s" % old_id)
    if ni < 0:
        return (False, "新经验 id 不存在: %s" % new_id)
    old_sup = list(records[oi].get("superseded_by") or [])
    if new_id not in old_sup:
        old_sup.append(new_id)
    records[oi]["superseded_by"] = old_sup
    new_sup = list(records[ni].get("supersedes") or [])
    if old_id not in new_sup:
        new_sup.append(old_id)
    records[ni]["supersedes"] = new_sup
    _save_records(path, records)
    return (True, "superseded %s by %s" % (old_id, new_id))


def _parse_date(s):
    try:
        return datetime.date(*time.strptime(s, "%Y-%m-%d")[:3])
    except (ValueError, TypeError):
        return None


def prune(path, status=None, older_than_days=None, rec_id=None):
    """删除候选经验（清噪）。返回 (ok, message, removed_count)。调用方须持锁。

    - `rec_id` 指定：删该条（优先）
    - `status` + `older_than_days`：删同时满足者（AND 语义）
    - 无任何过滤参数：拒绝（防误清空）
    """
    records = load_records(path)
    if rec_id:
        before = len(records)
        records = [r for r in records if r.get("id") != rec_id]
        removed = before - len(records)
        _save_records(path, records)
        return (True, "pruned by id=%s" % rec_id, removed)
    if status is None and older_than_days is None:
        return (False, "拒绝无过滤参数的 prune（防误清空）", 0)
    today = datetime.date.today()
    keep = []
    pruned = []
    for r in records:
        drop = True
        if status is not None and r.get("status") != status:
            drop = False
        if older_than_days is not None:
            d = _parse_date(r.get("captured") or "")
            if not d or (today - d).days < older_than_days:
                drop = False
        if drop:
            pruned.append(r)
        else:
            keep.append(r)
    _save_records(path, keep)
    return (True, "pruned status=%s older_than=%s" % (status, older_than_days), len(pruned))


# Knowledge_*.md 13 维度标题顺序（镜像 verify_knowledge.py:33-36，固定不得调换）
_KB_DIMENSIONS = [
    "业务流程", "状态机", "业务逻辑", "业务规则", "数据规则", "权限模型",
    "异常处理", "配置项", "存储信息", "接口信息", "上下游依赖", "变更历史", "待澄清项",
]
# Knowledge 元数据字段（镜像 verify_knowledge.py:38）
_KB_META_FIELDS = ["需求名称", "当前版本", "首次生成", "最近更新", "来源统计", "更新模块", "本轮变更"]
# 维度标题正则（镜像 verify_knowledge.py:96）：#+ 序号/中文序号 + 维度名
_KB_DIM_TITLE_RE = re.compile(
    r"^(#+\s*.*?([一二三四五六七八九十\d]+[、.\s]*)?(%s))" % "|".join(_KB_DIMENSIONS)
)
# 元数据字段行正则（镜像 verify_knowledge.py:71）：字段名：值
_KB_META_RE = {fld: re.compile(r"%s\s*[:：]\s*(.+)" % re.escape(fld)) for fld in _KB_META_FIELDS}


def _kb_parse_knowledge(text):
    """解析单个 Knowledge_*.md 文本 -> (meta_dict, segments)。

    meta_dict: {"需求名称":..., "更新模块":..., ...}（缺字段空串）。
    segments: [(dimension_name, section_text), ...] 按 13 维度标题拆段（含该段标题行之后
    到下一维度标题之前的全部文本）。非"本需求不涉及"的段才返回。无维度返 []。
    纯 stdlib，零模型——只切分既有模型产出的文本，不生成。
    """
    meta = {}
    for fld, rx in _KB_META_RE.items():
        m = rx.search(text or "")
        meta[fld] = m.group(1).strip() if m else ""
    lines = (text or "").splitlines()
    # 定位各维度标题行号（去重取首次出现，保 13 维度顺序）
    dim_positions = []  # [(dim_name, start_idx), ...]
    seen = set()
    for i, ln in enumerate(lines):
        s = ln.strip()
        m = _KB_DIM_TITLE_RE.match(s)
        if m:
            dim = m.group(3)
            if dim not in seen:
                seen.add(dim)
                dim_positions.append((dim, i))
    segments = []
    for idx, (dim, start) in enumerate(dim_positions):
        end = dim_positions[idx + 1][1] if idx + 1 < len(dim_positions) else len(lines)
        body = "\n".join(lines[start + 1:end]).strip()
        # "本需求不涉及" 标注的维度跳过（无可检索业务知识）
        if "本需求不涉及" in body:
            continue
        segments.append((dim, body))
    return meta, segments


def _kb_first_line(text, max_chars=200):
    """取段文本首条非空非表头行（确定性截断 ≤max_chars）。机制操作非生成。"""
    for ln in (text or "").splitlines():
        s = ln.strip().strip("|").strip()
        if not s:
            continue
        # 跳过纯表头分隔行（| -- |）与列表/表格语法残留
        if set(s) <= {"-", ":"}:
            continue
        if s.startswith("|"):
            s = s.strip("|").strip()
        if len(s) > max_chars:
            s = s[:max_chars]
        return s
    return ""


def reconcile_business(path, workdir, output_dir="case-design-out", skill_dir=None):
    """从所有 Knowledge_*.md 聚合业务知识索引到 KB_business.md。

    镜像 manifest.reconcile 的 glob→解析→upsert 模式：glob Knowledge_*.md -> regex 抽 rid
    -> 解析元数据"更新模块"为 module（人类标注，非模型生成）-> 按 13 维度标题拆段
    -> 每段（跳过"本需求不涉及"）用 surface map 派生 trigger -> upsert business 记录。

    Knowledge_*.md 是既有模型产物（Phase 14 经 verify_knowledge.py + 人工 confirm），
    本函数只索引元数据+维度文本，绝不生成内容——聚合/打标全 stdlib 确定性。
    Runtime 独占，调用方须在 locking.FileLock 内。返回 (ok, message, count)。

    business 信任模型：Knowledge 已过 verify+confirm -> 记录初始 status="endorsed"
    （信任门恒过），但相关性门仍过滤（trigger 不重叠 REQ -> 不注入）。occ 跨需求累积：
    同 module+dimension 被 N 个 Knowledge 命中 -> occ=N。
    """
    import glob
    out = os.path.join(workdir, output_dir)
    if not os.path.isdir(out):
        return (False, "输出目录不存在: %s" % out, 0)
    surfmap = get_surface_map(skill_dir) if skill_dir else {}
    # Knowledge 文件 glob（锚定前缀，镜像 manifest:262）
    k_files = glob.glob(os.path.join(out, "Knowledge_*.md"))
    if not k_files:
        return (False, "无 Knowledge_*.md 可聚合（business KB no-op）", 0)
    # rid 抽取：Knowledge_<rid>.md
    rid_re = re.compile(r"^Knowledge_(.+)\.md$")
    for kf in sorted(k_files):
        base = os.path.basename(kf)
        m = rid_re.match(base)
        if not m:
            continue
        rid = m.group(1)
        try:
            with open(kf, "r", encoding="utf-8") as f:
                ktext = f.read()
        except OSError:
            continue
        meta, segments = _kb_parse_knowledge(ktext)
        module = (meta.get("更新模块") or "").strip() or rid
        for dim, body in segments:
            # trigger 派生：用维度段文本做 surface 命中（mirror runtime _derive_dim_trigger，
            # 但 dimension 取 Knowledge 维度标题保结构真值，非 surface 类别）
            trigger_union = []
            for _cat, words in (surfmap or {}).items():
                trigger_union += [w for w in words if w in body]
            trigger = sorted(set(trigger_union))
            raw_text = _kb_first_line(body)
            if not raw_text:
                continue
            rec = {
                "kind": "business", "phase": "14", "dimension": dim,
                "error_type": "业务知识", "module": module, "source_req": rid,
                "captured": _today(), "raw_text": raw_text,
                "status": "endorsed", "occurrences": 1, "trigger": trigger,
            }
            # upsert_lesson 调 fingerprint(rec) -> kind=business 自动选 KB-business- 前缀；
            # 同 module+dim 跨需求命中 -> occ 累积（business 信任模型，相关性门仍过滤）
            upsert_lesson(path, rec)
    count = len(load_records(path))
    return (True, "reconciled business", count)
