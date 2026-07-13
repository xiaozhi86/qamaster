#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
project_cases.py — 知识综合用例投影（Tier B 降本脚本）

用途：知识总结生成（references/knowledge.md 31.2 综合来源）时，
由 skill 经 Bash 调用本脚本，从 TestCases_<需求标识>.md 抽取【紧凑 5 列投影】
喂给 LLM，避免用 Read 把整份 15 列 .md（含冗长 Given/When/Then）读进上下文。

抽取列（保留规则/场景/风险语义，剔除冗长步骤与固定值列）：
  用例ID | 关联规则 | 用例名称 | 用例等级 | 测试类型

综合来源逻辑不变（仍综合需求文档+台账+测试用例三来源），
只改变"用例以何种粒度进入上下文"。需求文档与台账仍读全文。

用法：
  python project_cases.py <TC文件.md>

退出码：0=成功输出投影；1=解析失败/文件不可读
本脚本是 skill 自带可复用资产，不删除（见 references/output_write.md ch30）。
"""
import sys
import os

# Windows 控制台默认 cp936，强制 stdout 输出 UTF-8，避免中文乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 15 列顺序（0-based）：
# 0用例ID 1关联需求ID 2关联规则 3测试类型 4测试维度 5所属模块 6用例名称
# 7Given 8When 9Then 10编辑模式 11标签 12责任人 13用例等级 14用例状态
PROJECTION = [
    (0, "用例ID"),
    (2, "关联规则"),
    (6, "用例名称"),
    (13, "用例等级"),
    (3, "测试类型"),
]


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


def main():
    if len(sys.argv) < 2:
        print("用法: python project_cases.py <TC文件.md>")
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

    # 定位表头行
    header_idx = None
    for i, ln in enumerate(lines):
        cells = split_row(ln)
        if cells and "用例ID" in cells[0]:
            header_idx = i
            break

    if header_idx is None:
        print("未找到表头行（含‘用例ID’的表格行）")
        return 1

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

    # 输出紧凑投影表
    print("===== 用例投影（知识综合用，共 %d 条）=====" % len(data_rows))
    header = " | ".join(name for _, name in PROJECTION)
    sep = " | ".join("---" for _ in PROJECTION)
    print("| %s |" % header)
    print("| %s |" % sep)
    for row in data_rows:
        cells = []
        for idx, _ in PROJECTION:
            val = row[idx] if idx < len(row) else ""
            # 折叠换行为空格，避免破坏表格
            val = val.replace("\n", " ").replace("\r", " ").strip()
            cells.append(val)
        print("| %s |" % " | ".join(cells))
    print("==========================================")

    return 0


if __name__ == "__main__":
    sys.exit(main())