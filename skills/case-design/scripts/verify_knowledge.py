#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_knowledge.py — 知识总结 Knowledge_*.md 结构校验（Tier B 降本脚本）

用途：Knowledge_<需求标识>.md 落盘后，由 skill 经 Bash 调用本脚本，校验知识总结
结构完整性，把 references/knowledge.md 31.3/31.4 中【可机器判定】的结构要求客观化。
verify_cases.py 校验测试用例 .md；本脚本校验知识总结 .md，补知识沉淀的闭环缺口。

【设计不变】不新增门禁、不改变知识总结 13 维度定义、不改变生成时机。仅校验结构
完整性（维度齐全+顺序+元数据+来源统计），不校验内容质量（主观，留给模型+人工）。

校验项（对应 knowledge.md 31.3 元数据 / 31.4 13维度）：
  - 元数据块：含 需求名称/当前版本/首次生成/最近更新/来源统计，且值非占位
  - 13 维度标题齐全：业务流程/状态机/业务逻辑/业务规则/数据规则/权限模型/
    异常处理/配置项/存储信息/接口信息/上下游依赖/变更历史/待澄清项
  - 13 维度顺序与标准一致（knowledge.md 31.4 固定顺序，不得调换）
  - 来源统计含三源数值：需求文档/澄清台账/测试用例

退出码：0=结构通过；1=缺维度/缺元数据/顺序错/来源统计缺失
本脚本是 skill 自带可复用资产，不删除（见 references/output_write.md ch30）。
"""
import sys
import os
import re

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 13 维度标准顺序（references/knowledge.md 31.4，固定不得调换）
DIMENSIONS = [
    "业务流程", "状态机", "业务逻辑", "业务规则", "数据规则", "权限模型",
    "异常处理", "配置项", "存储信息", "接口信息", "上下游依赖", "变更历史", "待澄清项",
]
# 元数据必填字段（references/knowledge.md 31.3）
META_FIELDS = ["需求名称", "当前版本", "首次生成", "最近更新", "来源统计"]
# 来源统计三源（references/knowledge.md 31.3）
SOURCE_KEYS = ["需求文档", "澄清台账", "测试用例"]


def main():
    if len(sys.argv) < 2:
        print("用法: python verify_knowledge.py <Knowledge文件.md>")
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
    print("===== 知识总结结构校验 =====")
    print("文件: %s" % os.path.basename(path))
    print("-" * 40)

    fails = []

    # 1. 元数据块校验
    print("【元数据块·knowledge.md 31.3】")
    # 元数据字段行：字段名：值
    meta_hits = {}
    for fld in META_FIELDS:
        m = re.search(r"%s\s*[:：]\s*(.+)" % re.escape(fld), text)
        if not m:
            fails.append("元数据缺字段：%s" % fld)
            meta_hits[fld] = None
        else:
            val = m.group(1).strip()
            # 占位判定：<...> 或空
            if not val or re.match(r"^<.+>$", val):
                fails.append("元数据字段 %s 值为占位/空：'%s'" % (fld, val))
                meta_hits[fld] = val
            else:
                meta_hits[fld] = val
    for fld in META_FIELDS:
        v = meta_hits[fld]
        print("  %s: %s" % (fld, ("缺失" if v is None else v)))
    print("元数据: %s" % ("通过" if all(meta_hits[f] and not re.match(r"^<.+>$", str(meta_hits[f])) for f in META_FIELDS) else "不通过"))

    # 2. 13 维度标题齐全 + 顺序
    print("-" * 40)
    print("【13 维度·knowledge.md 31.4】")
    found_order = []
    found_set = set()
    for ln in lines:
        s = ln.strip()
        # 标题行：#+ 序号/中文序号 + 维度名
        m = re.match(r"^#+\s*.*?([一二三四五六七八九十\d]+[、.\s]*)?(%s)" % "|".join(DIMENSIONS), s)
        if m:
            dim = m.group(2)
            if dim not in found_set:
                found_order.append(dim)
                found_set.add(dim)
    missing = [d for d in DIMENSIONS if d not in found_set]
    # 顺序校验：found_order 去重后与 DIMENSIONS 的相对顺序一致
    order_ok = (found_order == [d for d in DIMENSIONS if d in found_set])
    print("  已找到维度 %d/13：%s" % (len(found_set), "、".join(found_order) if found_order else "无"))
    if missing:
        print("  缺失维度：%s" % "、".join(missing))
    if not order_ok and not missing:
        print("  顺序与标准不一致（标准：%s）" % "、".join(DIMENSIONS))
        fails.append("维度顺序与标准 31.4 不一致")
    for d in missing:
        fails.append("缺维度：%s" % d)
    print("维度齐全+顺序: %s" % ("通过" if not missing and order_ok else "不通过"))

    # 3. 来源统计三源
    print("-" * 40)
    print("【来源统计·knowledge.md 31.3】")
    src_stats = text
    src_hit = {k: bool(re.search(r"%s\s*\D{0,3}\d+\s*条" % re.escape(k), src_stats)) for k in SOURCE_KEYS}
    for k in SOURCE_KEYS:
        print("  %s: %s" % (k, "有数值" if src_hit[k] else "缺失/无数值"))
    if not all(src_hit.values()):
        fails.append("来源统计缺三源数值：%s" % "、".join(k for k in SOURCE_KEYS if not src_hit[k]))

    # 4. 维度"本需求不涉及"标注合理性（无相关内容应标注而非删除，软提示）
    print("-" * 40)
    print("【结构结论】")
    overall = "通过" if not fails else "不通过"
    print("  %s（%d 项问题）" % (overall, len(fails)))
    for v in fails:
        print("  - %s" % v)
    print("  （内容质量不校验，留给模型 selfcheck + 人工审核）")
    print("=" * 40)

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
