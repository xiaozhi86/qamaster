#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
manifest.py — MANIFEST.md 共享索引的 read-modify-write（Runtime 独占）

设计原则：MANIFEST 是多需求共享可变资源，**所有变更必须经本模块**，
且调用方须在 `locking.FileLock` 内调用（cmd_manifest 全程持锁）。
模型被明确禁止 Write/Edit MANIFEST.md（强化"与模型无关"铁律）。

MANIFEST 格式：markdown 表格，列固定为
  需求标识 | 需求名称 | 需求文档 | 设计文档 | 台账文件 | 测试用例文件 | 知识总结 | 状态 | 更新时间
（与 references/phase0_manifest.md §索引表 一致；既有文件缺列向后兼容）

本模块仅做解析/序列化/行级操作，不持锁、不写 state。
仅用 Python 标准库。
"""
import json
import os
import re
import tempfile
import time

# 列顺序（单一事实源；序列化与解析共用）
COLUMNS = ["req_id", "name", "req_file", "design_file", "ledger_file",
           "testcase_files", "knowledge_file", "status", "updated_at"]
COLUMN_HEADERS = ["需求标识", "需求名称", "需求文档", "设计文档",
                  "台账文件", "测试用例文件", "知识总结", "状态", "更新时间"]

STATUS_IN_PROGRESS = "进行中"
STATUS_DONE = "已完成"
STATUS_ARCHIVED = "已归档"

_DEFAULT_ROW = {
    "req_id": "", "name": "", "req_file": "", "design_file": "-",
    "ledger_file": "-", "testcase_files": "-", "knowledge_file": "-",
    "status": STATUS_IN_PROGRESS, "updated_at": "",
}


def _today():
    return time.strftime("%Y-%m-%d")


def _clean(val):
    """容忍读取：去首尾空白、去包裹的反引号/引号。"""
    if val is None:
        return ""
    v = str(val).strip()
    # 去成对反引号
    if len(v) >= 2 and v[0] == "`" and v[-1] == "`":
        v = v[1:-1].strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1].strip()
    return v


def _empty_row(req_id=""):
    r = dict(_DEFAULT_ROW)
    r["req_id"] = req_id
    r["updated_at"] = _today()
    return r


def parse(text):
    """解析 MANIFEST.md 文本 -> (rows: list[dict], had_table: bool)。

    无表格 -> ([], False)。容错：列数不足补 "-"，多余截断；缺列向后兼容。
    表头行定位：含全部 COLUMN_HEADERS 关键词的首行；分隔行（|--|）跳过。
    """
    rows = []
    had_table = False
    header_idx = -1
    lines = text.splitlines() if text else []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if header_idx < 0:
            # 定位表头：前两列关键词命中
            if len(cells) >= 2 and "需求标识" in cells[0] and "需求名称" in cells[1]:
                header_idx = i
                had_table = True
            continue
        # 跳过分隔行（-- 为主）
        if all(re.match(r"^:?-+:?$", c) for c in cells if c != ""):
            continue
        # 数据行
        row = dict(_DEFAULT_ROW)
        for j, col in enumerate(COLUMNS):
            if j < len(cells):
                row[col] = _clean(cells[j])
            # 缺列保持默认
        if row["req_id"]:
            rows.append(row)
    return rows, had_table


def serialize(rows):
    """行列表 -> MANIFEST.md 文本（含固定前言 + 表头 + 表体）。"""
    out = []
    out.append("# 需求文件索引 MANIFEST")
    out.append("")
    out.append("> 本文件为所有需求产出物的快速定位入口；由 qamaster Runtime 在阶段 gate PASS 时自动维护。")
    out.append("> 模型禁止 Write/Edit 本文件（Runtime 控制协议铁律 4）。")
    out.append("> 产出物均位于本目录（`case-design-out/`）下，索引列填相对文件名。")
    out.append("")
    out.append("---")
    out.append("")
    out.append("## 索引表")
    out.append("")
    out.append("| " + " | ".join(COLUMN_HEADERS) + " |")
    out.append("| " + " | ".join(["--"] * len(COLUMN_HEADERS)) + " |")
    for r in rows:
        cells = []
        for col in COLUMNS:
            v = r.get(col, "")
            if col == "req_id" and v:
                cells.append("`%s`" % v)
            else:
                cells.append(v if v else "-")
        out.append("| " + " | ".join(cells) + " |")
    out.append("")
    return "\n".join(out)


def load_rows(path):
    """读取 MANIFEST 文件 -> rows；不存在返回 []。损坏不抛（best-effort 索引）。"""
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    rows, _ = parse(text)
    return rows


def _atomic_write(path, text):
    d = os.path.dirname(path) or "."
    if not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".manifest.", suffix=".tmp", dir=d)
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


def _save_rows(path, rows):
    _atomic_write(path, serialize(rows))


def _find(rows, req_id):
    for i, r in enumerate(rows):
        if r.get("req_id") == req_id:
            return i
    return -1


def _extract_req_name(workdir, output_dir, req_id):
    """从 REQ_<id>.md 首个 `# ` 标题抽取需求名称；失败回退 req_id。"""
    req_path = os.path.join(workdir, output_dir, "REQ_%s.md" % req_id)
    if not os.path.isfile(req_path):
        return req_id
    try:
        with open(req_path, "r", encoding="utf-8") as f:
            for ln in f:
                s = ln.strip()
                if s.startswith("# "):
                    return s[2:].strip() or req_id
    except OSError:
        pass
    return req_id


def add(path, req_id, workdir=None, output_dir="case-design-out", name=None):
    """新增索引行；req_id 已存在则报错。返回 (ok, message)。"""
    if not req_id:
        return (False, "req_id 为空")
    rows = load_rows(path)
    if _find(rows, req_id) >= 0:
        return (False, "req_id 已存在: %s" % req_id)
    row = _empty_row(req_id)
    row["req_file"] = "REQ_%s.md" % req_id
    # 探测设计文档
    design_path = os.path.join(workdir or "", output_dir, "DESIGN_%s.md" % req_id)
    if workdir and os.path.isfile(design_path):
        row["design_file"] = "DESIGN_%s.md" % req_id
    row["name"] = name or (_extract_req_name(workdir, output_dir, req_id) if workdir else req_id)
    row["status"] = STATUS_IN_PROGRESS
    row["updated_at"] = _today()
    rows.append(row)
    _save_rows(path, rows)
    return (True, "added req_id=%s" % req_id)


def update(path, req_id, **fields):
    """更新指定行的列（幂等）。req_id 不存在则报错。返回 (ok, message)。

    支持字段：name/design_file/ledger_file/testcase_files/knowledge_file/status。
    updated_at 自动刷新。"""
    if not req_id:
        return (False, "req_id 为空")
    allowed = {"name", "design_file", "ledger_file", "testcase_files", "knowledge_file", "status"}
    bad = set(fields) - allowed
    if bad:
        return (False, "不支持的字段: %s" % ",".join(sorted(bad)))
    rows = load_rows(path)
    i = _find(rows, req_id)
    if i < 0:
        return (False, "req_id 不存在: %s（须先 add）" % req_id)
    for k, v in fields.items():
        if v is not None:
            rows[i][k] = v
    rows[i]["updated_at"] = _today()
    _save_rows(path, rows)
    return (True, "updated req_id=%s fields=%s" % (req_id, ",".join(sorted(fields))))


def complete(path, req_id):
    """置某行为已完成（Phase 14 confirm 后置动作）。返回 (ok, message)。"""
    rows = load_rows(path)
    i = _find(rows, req_id)
    if i < 0:
        return (False, "req_id 不存在: %s" % req_id)
    rows[i]["status"] = STATUS_DONE
    rows[i]["updated_at"] = _today()
    _save_rows(path, rows)
    return (True, "completed req_id=%s" % req_id)


def list_rows(path):
    """返回行列表（只读，供 manifest list 输出 JSON）。"""
    return load_rows(path)


def reconcile(path, workdir, output_dir="case-design-out"):
    """从磁盘 REQ_*.md / TestCases_*.md 重建索引（兜底，防 gate PASS 成功但 add 锁超时失步）。

    保留已有行（不删），补全缺失行，刷新可探测的文件列。返回 (ok, message, count)。
    """
    import glob
    out = os.path.join(workdir, output_dir)
    rows = load_rows(path)
    by_id = {r["req_id"]: r for r in rows}
    # 从 REQ_*.md 探测需求标识
    req_files = glob.glob(os.path.join(out, "REQ_*.md"))
    seen = set()
    for rf in req_files:
        base = os.path.basename(rf)
        m = re.match(r"^REQ_(.+)\.md$", base)
        if not m:
            continue
        rid = m.group(1)
        seen.add(rid)
        if rid not in by_id:
            row = _empty_row(rid)
            row["req_file"] = base
            row["name"] = _extract_req_name(workdir, output_dir, rid)
            by_id[rid] = row
            rows.append(row)
        else:
            row = by_id[rid]
            row["req_file"] = base
            if not row.get("name") or row["name"] == rid:
                row["name"] = _extract_req_name(workdir, output_dir, rid)
    # 探测 TestCases / Knowledge / DESIGN / Ledger 列
    for row in rows:
        rid = row["req_id"]
        tcs = sorted(glob.glob(os.path.join(out, "TestCases_%s*.md" % rid)))
        if tcs:
            row["testcase_files"] = ",".join(os.path.basename(t) for t in tcs)
        kf = os.path.join(out, "Knowledge_%s.md" % rid)
        if os.path.isfile(kf):
            row["knowledge_file"] = "Knowledge_%s.md" % rid
            if row.get("status") != STATUS_ARCHIVED:
                row["status"] = STATUS_DONE
        df = os.path.join(out, "DESIGN_%s.md" % rid)
        if os.path.isfile(df):
            row["design_file"] = "DESIGN_%s.md" % rid
        lf = os.path.join(out, "Clarification_Ledger_%s.md" % rid)
        if os.path.isfile(lf):
            row["ledger_file"] = "Clarification_Ledger_%s.md" % rid
        row["updated_at"] = _today()
    _save_rows(path, rows)
    return (True, "reconciled", len(rows))
