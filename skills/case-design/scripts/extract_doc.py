#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_doc.py — case-design 内置文档解析落盘入口（v0.9.0·根因5 修复）。

根因：case-design 无自己的文档解析器，.docx/.pdf/.png/.pptx 全靠 harness Read 工具，
Word 丢页眉页脚/文本框/形状/批注、PDF 复杂版式 OCR 文末汇总丢顺序、扫描件/低置信 OCR 返回空——
内容在进入流水线前就部分丢失，后续门禁补不回来。本脚本把 requirement-review 的 extract_text.py
能力下沉为 case-design 可直接调用的落盘入口：非 .md 输入强制 --full 全文抽取并落盘 REQ/DESIGN；
检测到降级标记（OCR 失败/空文本）时硬阻断要求用户补文本，而非静默继续。

用法（cwd = 用户工作目录）：
  python skills/case-design/scripts/extract_doc.py <输入文件> --kind req|design \
      --req-id <需求标识> --out-dir case-design-out

退出码：0=已落盘（stdout 首行 [OK] + 文件名/字符数）；1=降级/失败（硬阻断，要求用户补 Markdown/纯文本）。
"""
import argparse
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXTRACT_TEXT = os.path.normpath(
    os.path.join(_HERE, "..", "..", "requirement-review", "scripts", "extract_text.py"))


def _run(args, timeout):
    return subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def main():
    ap = argparse.ArgumentParser(prog="extract_doc", add_help=False)
    ap.add_argument("input", help="用户提供的文档文件路径（.docx/.pdf/.pptx/.xlsx/.png/.txt/.md ...）")
    ap.add_argument("--kind", required=True, choices=["req", "design"], help="req=需求文档 design=设计文档")
    ap.add_argument("--req-id", required=True, help="需求标识（决定落盘文件名 REQ/DESIGN_<id>.md）")
    ap.add_argument("--out-dir", default="case-design-out", help="落盘目录，默认 case-design-out")
    ap.add_argument("--timeout", type=int, default=900, help="单次抽取超时秒数（OCR 可能较慢）")
    a = ap.parse_args()

    if not os.path.exists(a.input):
        print("[FAIL] 输入文件不存在: %s" % a.input)
        return 1
    if not os.path.exists(_EXTRACT_TEXT):
        print("[FAIL] 未找到文档解析器: %s" % _EXTRACT_TEXT)
        print("  requirement-review skill 须与 case-design 同 bundle 安装。")
        return 1

    # 1) --json：取降级标记与字符数（不灌全文，降本）
    try:
        pj = _run([sys.executable, _EXTRACT_TEXT, a.input, "--json"], timeout=a.timeout)
    except subprocess.TimeoutExpired:
        print("[FAIL] 文档解析超时（%ds）：文件过大或 OCR 卡住。请改提供 Markdown/纯文本。" % a.timeout)
        return 1
    except Exception as e:
        print("[FAIL] 文档解析执行异常: %s" % e)
        return 1
    if pj.returncode != 0:
        print("[FAIL] 文档解析器异常退出。请改提供 Markdown/纯文本。")
        if pj.stderr:
            sys.stderr.write(pj.stderr)
        return 1
    try:
        meta = json.loads(pj.stdout)
    except Exception:
        print("[FAIL] 文档解析器 JSON 输出不可解析。请改提供 Markdown/纯文本。")
        return 1

    chars = int(meta.get("字符数", 0) or 0)
    degrade = (meta.get("降级标记") or "").strip()
    if chars == 0 or degrade:
        tag = "需求" if a.kind == "req" else "设计"
        print("[FAIL] 文档解析降级/失败（字符数=%d，降级标记=%s）。" % (chars, degrade or "空文本"))
        print("  常见原因：扫描版 PDF 缺 poppler/OCR 引擎缺失、Word 含文本框/形状未抽取、低置信 OCR。")
        print("  处置（硬阻断·不得静默继续）：请用户将该文档转为 Markdown/纯文本后以")
        print("    <<<%s文档开始>>>…<<<%s文档结束>>> 内联提供，或直接给 .md 文件路径。" % (tag, tag))
        return 1

    # 2) --full：取全文（降级标记为空，安全灌全文）
    try:
        pf = _run([sys.executable, _EXTRACT_TEXT, a.input, "--full"], timeout=a.timeout)
    except subprocess.TimeoutExpired:
        print("[FAIL] 全文抽取超时（%ds）。请改提供 Markdown/纯文本。" % a.timeout)
        return 1
    if pf.returncode != 0 or not (pf.stdout or "").strip():
        print("[FAIL] 全文抽取失败（空文本）。请改提供 Markdown/纯文本。")
        return 1
    text = pf.stdout

    # 3) 落盘 REQ/DESIGN_<id>.md（既有文件不覆盖，由 phase0_manifest 既有文件处理语义决定；
    #    用户本轮若提供修订版应由 agent 整表覆盖——此处仅首次抽取落盘）
    os.makedirs(a.out_dir, exist_ok=True)
    fname = ("REQ_%s.md" if a.kind == "req" else "DESIGN_%s.md") % a.req_id
    out_path = os.path.join(a.out_dir, fname)
    if os.path.exists(out_path):
        print("[SKIP] 目标文件已存在，未覆盖: %s/%s（既有需求匹配成功，读入为权威基准）" % (a.out_dir, fname))
        print("  若用户本轮提供修订版，由 agent 整表覆盖落盘，本脚本不重复抽取。")
        return 0
    body = text if text.endswith("\n") else text + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(body)
    print("[OK] %s 文档已落盘: %s/%s （%d 字符）" % (
        "需求" if a.kind == "req" else "设计", a.out_dir, fname, len(text)))
    print("  预处理方式: %s | 置信度: %s | 图片数: %s" % (
        meta.get("预处理方式", ""), meta.get("置信度"), meta.get("图片数", 0)))
    if a.kind == "req":
        print("  注：#4 解析器已增强为按标题+正文语义分解（编号项/项目符号/含行为信号词散文句），")
        print("      纯散文无需人工补 ## 标题即可切出可追溯子条目；表格行不分解（由别处处理）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
