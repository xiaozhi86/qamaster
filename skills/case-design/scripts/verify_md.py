#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_md.py — 测试用例 .md 落盘后回读核对（Tier B 降本脚本）

用途：Write 写入 TestCases_<需求标识>.md 后，由 skill 经 Bash 调用本脚本，
读取文件并返回【摘要】供 LLM 核对，避免用 Read 把整份 .md 读进上下文。

核对项（与门禁判定标准一致，仅改变"由谁读、读多少进上下文"）：
  1. 表头：是否包含全部 15 个权威字段（与 references/modeling.md 字段顺序表一致）、顺序一致
  2. 用例条数：数据行数 = N
  3. 末行：是否完整（末单元格非空，防内容过长被截断）
  4. 列宽一致：每条数据行列数 = 表头列数（防字段错位）

说明：原文件多处文字称"16列"，但字段顺序表实际列出 15 个字段（序1-15），
系原文自身计数不一致。拆分版已统一为 15 列。本脚本按权威的 15 字段清单校验。

用法：
  python verify_md.py <TC文件.md>

退出码：0=解析成功（供模型依据摘要判定）；1=文件不可读/无表头
本脚本是 skill 自带可复用资产，不删除（见 references/output_write.md ch30）。
"""
import sys
import os
import json

# Windows 控制台默认 cp936，强制 stdout 输出 UTF-8，避免中文乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 权威字段顺序（序1-15，与 references/modeling.md 字段顺序表一致）
# 单一事实源：与 verify_cases.py 共同从 config/validation_rules.json 加载 header，
# 避免表头在两份脚本里双份维护、漂移（原 15/16 列计数不一致即此类漂移）。
def _load_header_tokens():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "validation_rules.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)["header"]
    except Exception as e:
        print("校验规则清单读取失败(%s)：无法加载表头 -> %s" % (p, e))
        return None


EXPECTED_HEADER_TOKENS = _load_header_tokens()
if EXPECTED_HEADER_TOKENS is None:
    sys.exit(1)
EXPECTED_COLS = len(EXPECTED_HEADER_TOKENS)  # = 15


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
        print("用法: python verify_md.py <TC文件.md>")
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
    header_cells = None
    for i, ln in enumerate(lines):
        cells = split_row(ln)
        if cells and "用例ID" in cells[0]:
            header_idx = i
            header_cells = cells
            break

    if header_idx is None:
        print("未找到表头行（含‘用例ID’的表格行）")
        return 1

    # 收集数据行
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

    n = len(data_rows)
    h_cols = len(header_cells)

    # 表头字段完整性：全部权威字段都在表头中且顺序一致
    missing_tokens = [t for t in EXPECTED_HEADER_TOKENS if t not in header_cells]
    order_ok = (header_cells[:EXPECTED_COLS] == EXPECTED_HEADER_TOKENS)
    header_ok = (not missing_tokens) and order_ok

    # 列宽一致：每条数据行列数 == 表头列数
    width_mismatch = [i + 1 for i, r in enumerate(data_rows) if len(r) != h_cols]
    width_ok = (not width_mismatch)

    # 末行完整性
    if data_rows:
        last = data_rows[-1]
        last_cols = len(last)
        last_cell_nonempty = bool(last[-1].strip()) if last else False
        last_ok = last_cell_nonempty and (last_cols == h_cols)
    else:
        last_cols = 0
        last_cell_nonempty = False
        last_ok = False

    overall = "通过" if (header_ok and width_ok and n > 0 and last_ok) else "不通过"

    print("===== 回读核对摘要 =====")
    print("文件: %s" % os.path.basename(path))
    print("表头: 列数=%d (权威字段数=%d) -> %s%s；顺序%s" % (
        h_cols, EXPECTED_COLS,
        "齐全" if not missing_tokens else "缺字段",
        (" [%s]" % ",".join(missing_tokens)) if missing_tokens else "",
        "一致" if order_ok else "不一致"))
    print("用例条数: %d" % n)
    if width_mismatch:
        print("列宽: 不一致行号(1-based)=%s" % width_mismatch)
    else:
        print("列宽: 全部数据行=%d列 一致" % h_cols)
    if data_rows:
        print("末行: 列数=%d，末单元格非空=%s -> %s" % (
            last_cols, "是" if last_cell_nonempty else "否",
            "完整" if last_ok else "可能截断"))
    else:
        print("末行: 无数据行")
    print("结论: %s" % overall)
    print("========================")

    return 0


if __name__ == "__main__":
    sys.exit(main())
