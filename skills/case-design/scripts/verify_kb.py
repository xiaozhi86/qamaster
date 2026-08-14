#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_kb.py — 知识库 KB_*.md 结构校验（Tier B 降本脚本）

用途：KB_lessons.md / KB_business.md / KB_expert.md 落盘后，由 skill 经 Bash
调用本脚本，校验知识库记录结构完整性，把 kb_store 序列化格式中【可机器判定】
的结构要求客观化。verify_cases.py 校验测试用例 .md；verify_knowledge.py 校验
知识总结 .md；本脚本校验三类 KB_*.md，补自我进化沉淀的闭环缺口。

【设计不变】不新增门禁、不改变知识库记录格式、不改变捕获时机。仅校验
结构完整性（围栏/字段齐全/列表合法/状态合法），不校验内容质量（主观，
留给模型 + 人工 endorse）。

校验项（对应 kb_store.py _DEFAULT_REC）：
  - 文件头模型禁写横幅在位
  - 每条记录围栏 start/end 配对
  - 必填字段齐全：kind/id/phase/dimension/status/raw_text
  - id 形如 KB-lesson-<12 hex> / KB-business-<12 hex> / KB-expert-<12 hex>
    （按记录 kind 派发；lesson/business/expert 分文件，单文件内 kind 一致）
  - status ∈ {draft, endorsed}
  - 列表字段（source_reqs/supersedes/superseded_by/trigger/variants/
    applicable_phases）为合法 JSON 数组
  - occurrences 为正整数

退出码：0=结构通过；1=缺字段/围栏/状态非法/列表非法
本脚本是 skill 自带可复用资产，仅用标准库（机制与模型无关铁律）。
"""
import sys
import os
import re

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 必填标量字段（kb_store._DEFAULT_REC 子集）
REQUIRED_FIELDS = ["kind", "id", "phase", "dimension", "status", "raw_text"]
# 合法状态
VALID_STATUS = {"draft", "endorsed"}
# 列表字段（须为合法 JSON 数组）
LIST_FIELDS = ["source_reqs", "supersedes", "superseded_by", "trigger", "variants", "applicable_phases"]
# id 形状（按 kind 派发前缀；lesson/business/expert 分文件，单文件内 kind 一致）
ID_PATTERNS = {
    "lesson":   re.compile(r"^KB-lesson-[0-9a-f]{12}$"),
    "business": re.compile(r"^KB-business-[0-9a-f]{12}$"),
    "expert":    re.compile(r"^KB-expert-[0-9a-f]{12}$"),
}
# 围栏
RECORD_START = re.compile(r"<!--\s*@kb:record\s+start\s+id=([^\s>]*)\s*-->")
RECORD_END = "<!-- @kb:record end -->"
# 文件头禁写横幅关键词
BANNER_MARK = "模型禁止"


def _parse_records(lines):
    """轻量解析：返回 [(id, field_dict, start_line_no)] 列表（仅校验用）。"""
    records = []
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i].rstrip("\n").strip()
        m = RECORD_START.match(ln)
        if not m:
            i += 1
            continue
        start_id = m.group(1).strip()
        fields = {}
        has_end = False
        i += 1
        while i < n and lines[i].strip() != RECORD_END:
            fl = lines[i].strip()
            if fl and ":" in fl:
                key, _, val = fl.partition(":")
                fields[key.strip()] = val.strip()
            i += 1
        if i < n and lines[i].strip() == RECORD_END:
            has_end = True
            i += 1
        records.append((start_id, fields, has_end))
    return records


def main():
    if len(sys.argv) < 2:
        print("用法: python verify_kb.py <KB_lessons.md | KB_business.md | KB_expert.md>")
        return 1

    path = sys.argv[1]
    if not os.path.exists(path):
        print("文件不存在: %s" % path)
        return 1
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print("读取失败: %s" % e)
        return 1

    text = "".join(lines)
    print("===== 知识库结构校验 =====")
    print("文件: %s" % os.path.basename(path))
    print("-" * 40)

    fails = []
    warns = []

    # 0. 文件头横幅
    print("【文件头横幅】")
    has_banner = BANNER_MARK in text[:400]
    print("  模型禁写横幅: %s" % ("在位" if has_banner else "缺失"))
    if not has_banner:
        fails.append("文件头缺模型禁写横幅")

    # 1. 围栏配对 + 字段
    records = _parse_records(lines)
    print("-" * 40)
    print("【记录围栏·字段】")
    print("  记录数: %d" % len(records))
    for idx, (rid, fields, has_end) in enumerate(records, 1):
        tag = "记录#%d id=%s" % (idx, rid or "(空)")
        rec_kind = fields.get("kind", "lesson")
        if not has_end:
            fails.append("%s: 缺 end 围栏" % tag)
        # 必填字段：kind/expert 的 phase 允许空（方法提炼不绑某阶段），
        # business/expert 的 module 亦非必填——仅强制 key 在位
        for fld in REQUIRED_FIELDS:
            if fld not in fields:
                # key 缺失即结构错误
                fails.append("%s: 缺字段 %s" % (tag, fld))
            elif not fields[fld]:
                # key 在位但值为空：phase 允许空（business/expert 无阶段绑定）
                if fld == "phase":
                    continue
                if fld == "raw_text" and fields.get("raw_text") == "":
                    continue  # raw_text 允许空字符串占位
                # expert 的 principle 映射到 raw_text，已放行；其余标量空值视为结构问题
                fails.append("%s: 缺字段 %s 或值为空" % (tag, fld))
        # id 形状（围栏 id 优先，否则取 fields.id；按记录 kind 派发 pattern）
        id_val = rid or fields.get("id", "")
        id_re = ID_PATTERNS.get(rec_kind, ID_PATTERNS["lesson"])
        if id_val and not id_re.match(id_val):
            pat_kind = rec_kind if rec_kind in ID_PATTERNS else "lesson"
            fails.append("%s: id 不符 KB-%s-<12hex>: '%s'" % (tag, pat_kind, id_val))
        # status
        st = fields.get("status", "")
        if st and st not in VALID_STATUS:
            fails.append("%s: status 非法 '%s'（须 draft|endorsed）" % (tag, st))
        # 列表字段 JSON 合法性
        for lf in LIST_FIELDS:
            if lf in fields and fields[lf]:
                import json
                try:
                    v = json.loads(fields[lf])
                    if not isinstance(v, list):
                        fails.append("%s: %s 非数组" % (tag, lf))
                    # 软 WARN（不升门禁、不入 fails、return 0 不变）：
                    # trigger 字段为单元素且该元素含分隔符 / | , 、 ，
                    # —— 疑似调用方误用 | 等作分隔致整串未分词（相关性门 surface=0）。
                    if lf == "trigger" and isinstance(v, list) and len(v) == 1:
                        single = v[0]
                        if isinstance(single, str) and any(sep in single for sep in ("/", "|", ",", "、", "，")):
                            warns.append("%s: trigger 单元素含分隔符，疑似未分词: %s" % (tag, single))
                except ValueError:
                    fails.append("%s: %s 非法 JSON" % (tag, lf))
        # occurrences
        occ = fields.get("occurrences", "1")
        try:
            iv = int(occ)
            if iv < 1:
                fails.append("%s: occurrences < 1" % tag)
        except ValueError:
            fails.append("%s: occurrences 非整数 '%s'" % (tag, occ))
    print("  字段/围栏: %s" % ("通过" if not any("记录#" in f for f in fails) else "不通过"))

    # 2. 结构结论
    print("-" * 40)
    print("【结构结论】")
    overall = "通过" if not fails else "不通过"
    print("  %s（%d 项问题）" % (overall, len(fails)))
    for v in fails:
        print("  - %s" % v)
    if warns:
        print("  （%d 项软告警·不升门禁·不影响退出码）" % len(warns))
        for w in warns:
            print("  - [WARN] %s" % w)
    print("  （内容质量不校验，留给人工 endorse/supersede）")
    print("=" * 40)

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
