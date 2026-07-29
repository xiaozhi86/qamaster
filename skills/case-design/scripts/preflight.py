#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preflight.py — 阶段进入前 ref 摘要注入器（Tier B 降本脚本·跨平台）

用途：skill 进入第 N 阶段前，由模型/hook 经 Bash 调用本脚本，打印对应
references/<file>.md 的紧凑摘要（标题级大纲 + 关键约束行），即使模型不主动读 ref，
摘要也已进入上下文——等价于把 verify_cases.py --dump-rules 思路推广到每个阶段。

降本红线（防反噬）：
  - 摘要硬上限 40 行/阶段（只取标题大纲 + 少量关键行，不全量灌入）；
  - 仅在"进入该阶段"时注入一次（同一阶段重复调用幂等：打印同样的摘要）；
  - 超长需求（用例数 > 60）场景：本脚本输出降为"计数 + 一句指引"，由模型改读
    SKILL.md 内联的承重规则（见 SKILL.md §六 关键规则内联），避免摘要叠加反噬上下文。

跨平台：
  - 纯 Python 标准库（os / re），无平台依赖；路径用 os.path.join；行尾统一 \\n。
  - Windows 用 python、macOS/Linux 用 python3（见 README §8.4）。

用法：
  python preflight.py --phase <N>            # 打印第 N 阶段对应 ref 摘要
  python preflight.py --phase <N> --big       # 超长需求模式（用例数>60），降级输出
  python preflight.py --list                  # 列出全部阶段-ref 映射

退出码：0=摘要已打印；1=阶段号越界/无对应 ref/文件缺失。
本脚本是 skill 自带可复用资产，不删除（与 verify_md/verify_cases 同级）。
"""
import sys
import os
import re

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REFS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references")

# 阶段号 -> 对应 ref 文件（与 SKILL.md 参考文件索引一致）
PHASE_REF = {
    0: "phase0_manifest.md",
    1: "clarification.md",
    2: "coverage.md",
    3: "modeling.md",
    4: "modeling.md",
    5: "risk.md",
    6: "methods.md",
    7: "coverage.md",
    8: "quality_rules.md",
    9: "dedup_coverage.md",
    10: "dedup_coverage.md",
    11: "selfcheck.md",
    12: "output_write.md",
    13: "output_write.md",
    14: "review_gate.md",
    15: "excel.md",
}

MAX_LINES = 40  # 摘要硬上限行数


def extract_outline(ref_path, max_lines=MAX_LINES):
    """从 ref 文件提取标题大纲（# / ## / ###）+ 少量关键约束行，上限 max_lines 行。
    关键约束行：含 强制/禁止/必须/≤/轮/检查N 等强信号词的非标题行，各取前若干。"""
    try:
        with open(ref_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        return None, "读取失败: %s" % e

    out = []
    # 先收全部标题行
    headings = []
    for i, ln in enumerate(lines, start=1):
        s = ln.rstrip("\n")
        m = re.match(r"^(#{1,6})\s+(.+)", s)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            headings.append((level, title, i, s))

    # 标题大纲优先；按层级缩进
    for level, title, ln_no, raw in headings:
        indent = "  " * (level - 1)
        out.append("%s%s" % (indent, title))
        if len(out) >= max_lines:
            return out, None

    # 标题不足时，补关键约束行（含强信号词）
    if len(out) < max_lines:
        kw_re = re.compile(r"(强制|禁止|必须|不得|≤|轮|检查\d|阻断|门禁)")
        for ln in lines:
            s = ln.rstrip("\n").strip()
            if not s or s.startswith("#"):
                continue
            if kw_re.search(s):
                # 截断过长行
                out.append((s[:120] + "…") if len(s) > 120 else s)
                if len(out) >= max_lines:
                    break
    return out, None


def main():
    args = sys.argv[1:]
    if not args or "--list" in args:
        print("===== 阶段-ref 映射 =====")
        for ph in sorted(PHASE_REF.keys()):
            print("第%d阶段 -> %s" % (ph, PHASE_REF[ph]))
        print("用法: python preflight.py --phase <N> [--big]")
        return 0

    if "--phase" not in args:
        print("用法: python preflight.py --phase <N> [--big] | --list")
        return 1
    i = args.index("--phase")
    if i + 1 >= len(args):
        print("缺少阶段号")
        return 1
    try:
        phase = int(args[i + 1])
    except ValueError:
        print("阶段号须为整数: %s" % args[i + 1])
        return 1

    if phase not in PHASE_REF:
        print("阶段号越界：%s（合法范围 0-15）" % phase)
        return 1

    ref_name = PHASE_REF[phase]
    ref_path = os.path.join(REFS_DIR, ref_name)
    if not os.path.exists(ref_path):
        print("[preflight] ref 文件缺失: %s" % ref_path)
        return 1

    big = "--big" in args

    print("===== 第%d阶段 preflight 摘要 =====" % phase)
    print("对应 ref: references/%s" % ref_name)
    if big:
        # 超长需求模式：降级为计数 + 一句指引，防摘要反噬
        print("【超长需求模式】用例数>60，preflight 降级输出。")
        print("指引：本阶段承重规则见 SKILL.md §六 内联（优先级/13维测试维度/5循环计数/15列）。")
        print("      需要细则时再 Read references/%s 的对应小节，勿全量载入。" % ref_name)
        print("==================================")
        return 0

    outline, err = extract_outline(ref_path)
    if outline is None:
        print("[preflight] %s" % err)
        return 1

    for line in outline:
        print(line)
    print("（摘要上限 %d 行；细则请按需 Read references/%s 对应小节）" % (MAX_LINES, ref_name))
    print("==================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
