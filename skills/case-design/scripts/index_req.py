#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
index_req.py — 需求文档结构化索引生成器（Tier B 降本脚本·跨平台）

用途：第0阶段（需求定位）把需求文档落盘为 case-design-out/REQ_<需求标识>.md 后，
由 skill 经 Bash 调用本脚本，扫描其 ## / ### 标题结构，生成同目录索引文件
case-design-out/REQ_<需求标识>.md.index.json，供第1/3/5 阶段"按章节按需读"
（Read 指定行区间）而非"全量载入需求文档进上下文"。

降本定位：把 project_cases.py 的"抽紧凑投影喂给 LLM"思路，从测试用例 .md 推广到
需求文档 .md——索引常驻（小体积 JSON），全文按需读章节。#4/#5 反向追溯仍由
verify_cases.py 读全文件（不变，脚本读盘不占模型上下文）。

索引字段：
  - title：章节标题原文（## / ### / # 文档根标题）
  - level：标题层级（1=文档根 / 2=二级 / 3=三级）
  - start_line：该章节起始行号（1-based）
  - end_line：该章节下一同级/上级标题前一行（末章为文件末行）
  - char_count：该章节（起行到 end_line）去空白后字符数估算（供 token 预估）
  - keywords：该章节文本中提取的关键词（标题切词 + 高频中文 2-gram，前 8 个）

跨平台：
  - 纯 Python 标准库（os / json / re），无平台依赖；
  - 路径用 os.path.join，输出 json.dump(ensure_ascii=False)，行尾统一 \\n；
  - Windows 用 python、macOS/Linux 用 python3，调用方统一（见 README §8.4）。

用法：
  python index_req.py <REQ文件.md>
  python index_req.py <REQ文件.md> --out <输出.json>   # 缺省输出 = 源 .md 同名 .index.json

退出码：0=索引生成成功；1=文件不可读/无章节/写盘失败。
本脚本是 skill 自带可复用资产，不删除（与 verify_md/verify_cases 同级）。
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


def split_sections(lines):
    """扫描行列表，按 #/##/### 标题切分章节。返回 [{title,level,start_line,...}, ...]。
    行号 1-based。# 文档根标题（level 1）也记录，供"全文档根"定位。"""
    sections = []
    cur = None
    for i, ln in enumerate(lines, start=1):
        s = ln.lstrip()
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", s)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            # 收尾上一节
            if cur is not None:
                cur["end_line"] = i - 1
                sections.append(cur)
            cur = {"title": title, "level": level, "start_line": i, "end_line": None}
        # 非标题行累计到当前节
    if cur is not None:
        cur["end_line"] = len(lines)
        sections.append(cur)
    return sections


def fill_char_count_and_keywords(sections, lines):
    """为每个章节填充 char_count 与 keywords（基于 start_line..end_line 的文本）。"""
    for sec in sections:
        s = sec["start_line"]
        e = sec["end_line"]
        chunk = "".join(ln for ln in lines[s - 1:e])
        # 去空白
        compact = re.sub(r"\s+", "", chunk)
        sec["char_count"] = len(compact)
        # 关键词：标题切词（英文段+数字章节号）+ 中文 2-gram 高频
        title = sec["title"]
        kws = []
        for m in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,}", title):
            kws.append(m)
        for m in re.findall(r"\d+(?:\.\d+)*", title):
            kws.append(m)
        # 中文 2-gram 滑动窗取高频前若干
        grams = {}
        for run in re.findall(r"[一-龥]+", chunk):
            if len(run) >= 2:
                for i in range(len(run) - 1):
                    g = run[i:i + 2]
                    grams[g] = grams.get(g, 0) + 1
        # 标题词优先，再补 2-gram 高频，去重保序
        seen = set()
        ordered = []
        for k in kws + [g for g, _ in sorted(grams.items(), key=lambda kv: (-kv[1], kv[0]))]:
            if k and k not in seen:
                seen.add(k)
                ordered.append(k)
        sec["keywords"] = ordered[:8]
    return sections


def build_index(req_path):
    """读取需求文档，构建索引 dict。返回 (index_dict, None) 或 (None, error_msg)。"""
    try:
        with open(req_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        return None, "读取失败: %s" % e

    sections = split_sections(lines)
    if not sections:
        return None, "未找到任何 #/##/### 标题章节（需求文档须先补 ## 二级标题分节，见 phase0_manifest.md 步骤零）"

    sections = fill_char_count_and_keywords(sections, lines)

    total_chars = sum(sec["char_count"] for sec in sections)
    # token 估算口径：中文 ~1.6 字符/token，英文/混合 ~3.5 字符/token；取折中 2.5
    token_est = int(total_chars / 2.5)

    index = {
        "source_file": os.path.basename(req_path),
        "total_lines": len(lines),
        "total_chars": total_chars,
        "token_est": token_est,
        "needs_split": token_est > 24000,  # 超阈值需分批落盘（见 run_phase.py 方案 B）
        "section_count": len(sections),
        "sections": sections,
    }
    return index, None


def main():
    if len(sys.argv) < 2:
        print("用法: python index_req.py <REQ文件.md> [--out <输出.json>]")
        return 1

    req_path = sys.argv[1]
    if not os.path.exists(req_path):
        print("文件不存在: %s" % req_path)
        return 1

    # 输出路径：--out 指定或缺省源 .md 同名 .index.json（写回 case-design-out/ 下）
    out_path = None
    if "--out" in sys.argv:
        i = sys.argv.index("--out")
        if i + 1 < len(sys.argv):
            out_path = sys.argv[i + 1]
    if out_path is None:
        base, _ = os.path.splitext(req_path)
        out_path = base + ".index.json"

    index, err = build_index(req_path)
    if index is None:
        print("[索引生成失败] %s" % err)
        return 1

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[索引写入失败] %s" % e)
        return 1

    # stdout 摘要（供 LLM 读取索引结构，不读全文）
    print("===== 需求文档章节索引 =====")
    print("源文件: %s" % index["source_file"])
    print("总行数: %d | 总字符: %d | token估算: ~%d | 需分批落盘: %s" % (
        index["total_lines"], index["total_chars"], index["token_est"],
        "是(>24000)" if index["needs_split"] else "否"))
    print("章节数: %d" % index["section_count"])
    for sec in index["sections"]:
        indent = "  " * (sec["level"] - 1)
        print("%s[L%d] %d-%d (%d字) %s  %s" % (
            indent, sec["level"], sec["start_line"], sec["end_line"],
            sec["char_count"], sec["title"],
            ("关键词:%s" % "/".join(sec["keywords"])) if sec["keywords"] else ""))
    print("索引已写入: %s" % out_path)
    print("============================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
