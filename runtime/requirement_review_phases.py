#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
requirement_review_phases.py — qamaster requirement-review 轻量状态机阶段注册表

把 SKILL.md 的「并行评审 + 汇总仲裁」9 阶段压缩为 8 个受控阶段（0-7）：
  0 输入预处理与需求定位   — 落盘 REQ_<id>.md（extract_text.py 预处理）
  1 并行评审               — 7 Agent 输出评审问题清单
  2 结果汇总去重 + 冲突检测 — Review Master 汇总去重、检测 Agent 冲突
  3 优化方案总览           — P0/P1/P2 优先级 + 影响范围
  4 用户确认（人工确认门）  — 必须用户确认方案才推进
  5 需求文档重构           — 多 Agent 融合版最终需求文档
  6 自动复查 + 二次修复    — Self-Review 复查，发现问题就地修复
  7 最终输出               — 最终需求文档 + 评审问题清单

与 case-design 的差异：requirement-review 是「单次评审产出」，无知识总结后置动作、
无 Excel 许可门（末阶段=auto）；阶段门禁为确定性文件存在性检查（exists_any，
req_id 绑定 glob，{req_id} 占位经 _fmt_cmd 替换），人工确认门（Phase 4）复用控制器
confirm 机制，模型不可绕过；Phase 0/1/5/7 副作用维护 requirement-review-out/MANIFEST.md
聚合索引（多需求并发隔离）。

gate 取值：
  auto    — 自动门：产物达标即放行（gate_checks 全部通过）
  confirm — 人工确认门：必须用户 confirm（SKILL.md 第五阶段「用户确认」）
"""
from state_store import PHASE_KINDS  # noqa: F401  (re-export, 供调用方校验)

# workflow 元数据常量（供 workflows/requirement_review.py 与控制器引用，单一事实源）
WORKFLOW_NAME = "requirement-review"
OUTPUT_DIR = "requirement-review-out"
SKILL_DIR = "skills/requirement-review"

PHASES = [
    {
        "id": 0, "name": "输入预处理与需求定位", "gate": "auto",
        "refs": [],
        "objective": "将用户需求文档（含图片/扫描件）经 extract_text.py 预处理为纯文本并落盘 requirement-review-out/REQ_<需求标识>.md（纯散文补 ## 二级标题分节）；读 config/agents.json 路由评审专家团，落盘 requirement-review-out/Agents_<需求标识>.md（核心团 PM/QA/Dev 恒参与 + 信号词命中 / co_trigger 连带 / 语义兜底的扩展团）。",
        "allowed": [
            "需求文档含图片/扫描件时先跑 python skills/requirement-review/scripts/extract_text.py <文件> --json 抽取文本",
            "将预处理后的需求文档落盘为 requirement-review-out/REQ_<需求标识>.md",
            "读 config/agents.json 路由评审专家团（core_agents 恒参与；扩展团命中 required_signals 任一即启用；co_trigger 连带启用；未命中但视角仍有价值则启用并记理由）",
            "扩展团采用「存疑即启用、宁多勿漏」默认偏向：仅当明确无关（如后端接口无 UI → UX）才裁掉",
            "专家团名单落盘 requirement-review-out/Agents_<需求标识>.md（逐行列出启用专家 id + 中文名 + 命中依据/启用理由）",
            "需求标识由 bootstrap 预先派生写入 state.req_id，本阶段不再派生 id",
        ],
        "forbidden": ["跳过需求文档落盘直接进入评审", "漏选核心团（PM/QA/Dev 任一缺失）", "仅按字面信号词硬裁专家（忽略语义兜底与 co_trigger 连带）", "生成评审结论或最终需求文档"],
        "produces": ["requirement-review-out/REQ_<需求标识>.md", "requirement-review-out/Agents_<需求标识>.md"],
        "exit_condition": "REQ 文件 + 专家团名单存在于磁盘，且专家团名单含核心团（Runtime 机器判定）",
        "gate_checks": [
            {"kind": "exists_any", "patterns": ["requirement-review-out/REQ_{req_id}.md"], "label": "需求文档已落盘"},
            {"kind": "exists_any", "patterns": ["requirement-review-out/Agents_{req_id}.md"], "label": "评审专家团名单已落盘"},
            {"kind": "contains", "path": "requirement-review-out/Agents_{req_id}.md", "must_contain": ["PM", "QA", "Dev"], "label": "核心团（PM/QA/Dev）齐全"},
        ],
    },
    {
        "id": 1, "name": "并行评审", "gate": "auto",
        "refs": [],
        "objective": "按 Agents_<需求标识>.md 指定的评审专家团并行评审（核心团 PM/QA/Dev 恒参与 + Phase 0 命中的扩展团），各输出 ✅/❌/⚠ 问题清单，落盘 requirement-review-out/ReviewIssues_<需求标识>.md。",
        "allowed": ["按 Agents_<需求标识>.md 列出的专家并行评审（各输出问题建议+依据）", "问题清单落盘 ReviewIssues_<需求标识>.md"],
        "forbidden": ["启用专家团名单之外的 Agent", "跳过任一已启用 Agent 直接汇总", "评审结论与问题清单不落盘"],
        "produces": ["requirement-review-out/ReviewIssues_<需求标识>.md"],
        "exit_condition": "评审问题清单已落盘（Runtime 机器判定）",
        "gate_checks": [
            {"kind": "exists_any", "patterns": ["requirement-review-out/ReviewIssues_{req_id}.md"], "label": "评审问题清单已落盘"},
        ],
    },
    {
        "id": 2, "name": "结果汇总去重与冲突检测", "gate": "auto",
        "refs": [],
        "objective": "Review Master 汇总本专家团结果、去重，检测实际参与专家两两间的建议冲突（如业务 vs 技术 / 体验 vs 风控），输出冲突清单与权衡推荐（内存，回填 ReviewIssues 清单）。",
        "allowed": ["汇总去重本专家团问题", "按实际参与专家两两组合输出【冲突清单】（冲突点/涉及 Agent/原因/推荐方案）"],
        "forbidden": ["遗漏实际参与专家间冲突", "跳过去重导致问题清单重复"],
        "produces": [],
        "exit_condition": "汇总去重 + 冲突检测完成（内存产物，Runtime 记录通过）",
        "gate_checks": [],
    },
    {
        "id": 3, "name": "优化方案总览", "gate": "auto",
        "refs": [],
        "objective": "按 P0/P1/P2 优先级输出【优化方案汇总】，标注影响范围（开发/测试/业务）。",
        "allowed": ["输出优化方案总览（P0/P1/P2 + 影响范围）"],
        "forbidden": ["无优先级/影响范围的方案", "在用户确认前进入重构"],
        "produces": [],
        "exit_condition": "优化方案总览完成（内存产物，Runtime 记录通过）",
        "gate_checks": [],
    },
    {
        "id": 4, "name": "用户确认", "gate": "confirm",
        "refs": [],
        "objective": "输出【问题详情列表】+【请确认】三项问题（是否接受全部优化/忽略或修改/补充业务），停止等待用户明确确认。",
        "allowed": ["输出问题详情列表与请确认项", "等待用户明确答复（接受/忽略/修改/补充）"],
        "forbidden": ["用户未明确确认即推进", "跳过用户确认直接重构"],
        "produces": [],
        "exit_condition": "用户明确确认后执行 confirm（Runtime 人工门判定）",
        "gate_checks": [],
    },
    {
        "id": 5, "name": "需求文档重构", "gate": "auto",
        "refs": [],
        "objective": "基于确认结果生成多 Agent 融合版最终需求文档，落盘 requirement-review-out/ReviewedReq_<需求标识>.md（10 节齐全）。",
        "allowed": ["基于确认结果重构需求文档", "最终需求文档落盘 ReviewedReq_<需求标识>.md（10 节齐全）"],
        "forbidden": ["重构与确认结果不符", "最终需求文档不落盘"],
        "produces": ["requirement-review-out/ReviewedReq_<需求标识>.md"],
        "exit_condition": "最终需求文档已落盘（Runtime 机器判定）",
        "gate_checks": [
            {"kind": "exists_any", "patterns": ["requirement-review-out/ReviewedReq_{req_id}.md"], "label": "最终需求文档已落盘"},
        ],
    },
    {
        "id": 6, "name": "自动复查与二次修复", "gate": "auto",
        "refs": [],
        "objective": "Self-Review Agent 复查最终文档（遗漏流程/未定义状态/不可测点/歧义/缺异常/缺边界），发现问题就地修复并标注修改点。",
        "allowed": ["复查最终文档", "发现问题就地修复 + 标注修改点"],
        "forbidden": ["跳过复查直接输出", "发现问题不修复"],
        "produces": [],
        "exit_condition": "复查通过或问题已修复（内存产物，Runtime 记录通过）",
        "gate_checks": [],
    },
    {
        "id": 7, "name": "最终输出", "gate": "auto",
        "refs": [],
        "objective": "输出【最终需求文档（高专业版）】+【评审问题详情列表】（含已解决/未解决），产物已落盘 requirement-review-out/。",
        "allowed": ["输出最终需求文档与评审问题详情列表"],
        "forbidden": ["产物未落盘宣称完成"],
        "produces": [],
        "exit_condition": "最终需求文档 + 评审问题清单均存在于磁盘（Runtime 机器判定）",
        "gate_checks": [
            {"kind": "exists_any", "patterns": ["requirement-review-out/ReviewedReq_{req_id}.md"], "label": "最终需求文档存在"},
            {"kind": "exists_any", "patterns": ["requirement-review-out/ReviewIssues_{req_id}.md"], "label": "评审问题清单存在"},
        ],
    },
]

PHASE_BY_ID = {p["id"]: p for p in PHASES}
LAST_PHASE = PHASES[-1]["id"]

# requirement-review 无流程深度裁剪（单次评审，全阶段执行）
DEPTH_SKIPS = {"heavy": [], "medium": [], "light": []}


def get_phase(phase_id):
    return PHASE_BY_ID.get(phase_id)


def effective_phases(depth):
    """按流程深度返回应执行的阶段 id 列表（顺序）。requirement-review 无裁剪。"""
    skips = set(DEPTH_SKIPS.get(depth or "heavy", []))
    return [p["id"] for p in PHASES if p["id"] not in skips]


def next_phase_id(current, depth):
    seq = effective_phases(depth)
    if current not in seq:
        return None
    i = seq.index(current)
    return seq[i + 1] if i + 1 < len(seq) else None


def find_phase_by_name(token):
    """按阶段号或中文名模糊定位（供 fail 回退解析）。"""
    token = (token or "").strip()
    if not token:
        return None
    if token.isdigit():
        return PHASE_BY_ID.get(int(token))
    for p in PHASES:
        if token in p["name"]:
            return p
    return None
