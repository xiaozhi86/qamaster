#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
requirement_review.py — 把 requirement_review_phases.py 包成 WorkflowSpec 并显式注册

不重构 requirement_review_phases.py 的 dict 形状（与 case-design phases.py 同构）。
requirement_review_phases.py 仍是 requirement-review 阶段定义的单一事实源；本文件只做适配层。

WorkflowSpec.extra_card_text：Phase 4（用户确认）的 requirement-review 专属确认话术。
控制器 _card 在渲染人工门文案后调 spec.extra_card_text 追加，无需在通用路径硬编码。
"""
import os

from registry import WorkflowSpec, register as _registry_register
import requirement_review_phases  # requirement-review 阶段机单一事实源

WORKFLOW_NAME = "requirement-review"
OUTPUT_DIR = "requirement-review-out"
SKILL_DIR = "skills/requirement-review"

# Phase 4（用户确认）专属卡片片段：覆盖控制器通用 confirm 文案的「澄清」措辞，
# 给出评审场景的确认指引（问题详情列表 + 请确认三项 + 停止等待）。
_EXTRA_PHASE4 = (
    "\n🙋 本阶段为「用户确认」人工门：输出【问题详情列表】（问题ID/描述/风险等级/类型/"
    "影响范围/优化建议/优化依据）与【请确认】三项（是否接受全部优化 / 忽略或修改 / 补充业务）后停止等待。\n"
    "  用户未明确确认前禁止进入下一阶段；收到用户答复后执行 `gate` 查看放行判定，再 `confirm` 放行。"
)


def _roster_block(st):
    """Phase 1 契约卡注入：读 Agents_<req_id>.md 评审专家团名单，告知模型本次只启用哪些专家。

    名单缺失/空 → 返回空串（Phase 1 契约卡不追加该段，避免破坏逐字节一致性）。
    """
    workdir = st.get("workdir") or ""
    req_id = (st.get("req_id") or "").strip()
    if not workdir or not req_id:
        return ""
    roster_path = os.path.join(workdir, OUTPUT_DIR, "Agents_%s.md" % req_id)
    try:
        with open(roster_path, "r", encoding="utf-8", errors="replace") as f:
            roster = f.read().strip()
    except OSError:
        return ""
    if not roster:
        return ""
    return ("\n🎯 本次评审专家团（Phase 0 路由结果·只启用下列专家，其余不参与）:\n" +
            roster +
            "\n  汇总去重（Phase 2）与冲突检测（Phase 3）也只覆盖上述专家，不引入名单外视角。")


def _extra_card_text(phase, st):
    if phase == 1:
        return _roster_block(st)
    if phase == 4:
        return _EXTRA_PHASE4
    return ""


def register():
    """显式注册 requirement-review workflow（由 qamaster_runtime.main() 调用）。"""
    spec = WorkflowSpec(
        name=WORKFLOW_NAME,
        output_dir=OUTPUT_DIR,
        skill_dir=SKILL_DIR,
        phases=requirement_review_phases.PHASES,
        depth_skips=requirement_review_phases.DEPTH_SKIPS,
        knowledge_gate=[],
        extra_card_text=_extra_card_text,
    )
    # last_phase 由 __post_init__ 从 phases 末尾推导，但显式取权威值
    spec.last_phase = requirement_review_phases.LAST_PHASE
    _registry_register(spec)


# 暴露给控制器/测试的便捷入口
def spec() -> WorkflowSpec:
    from registry import get_workflow
    s = get_workflow(WORKFLOW_NAME)
    if s is None:
        register()
        s = get_workflow(WORKFLOW_NAME)
    return s
