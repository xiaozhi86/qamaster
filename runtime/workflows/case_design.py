#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_design.py — 把 phases.py 包成 WorkflowSpec 并显式注册

不重构 phases.py 的 dict 形状（最小改动；Phase dataclass 化推迟到后续）。
phases.py 仍是 case-design 阶段定义的单一事实源；本文件只做适配层。

WorkflowSpec.extra_card_text：Phase 8（用例生成）与 Phase 10（覆盖率校验）
的 case-design 专属卡片文案。控制器 _card 调 spec.extra_card_text 追加，
无需在通用路径硬编码 workflow 专属文本。
"""
import os

from registry import WorkflowSpec, register as _registry_register
import phases  # case-design 阶段机单一事实源

WORKFLOW_NAME = "case-design"
OUTPUT_DIR = "case-design-out"
SKILL_DIR = "skills/case-design"

# Phase 8 / 10 case-design 专属卡片片段（与旧 _card 硬编码文案保持一致）
_EXTRA_PHASE8 = (
    "\n🧪 用例生成须在**内存**中完成，零文件操作——写前不落盘，由 Phase 13 统一 Write。"
)
_EXTRA_PHASE10 = (
    "\n🎯 覆盖率校验须按停止条件收敛，缺口转待确认问题/假设并回显清单；台账待确认项须闭环或转假设。"
)


def _extra_card_text(phase, st):
    if phase == 8:
        return _EXTRA_PHASE8
    if phase == 10:
        return _EXTRA_PHASE10
    return ""


def register():
    """显式注册 case-design workflow（由 qamaster_runtime.main() 调用）。"""
    spec = WorkflowSpec(
        name=WORKFLOW_NAME,
        output_dir=OUTPUT_DIR,
        skill_dir=SKILL_DIR,
        phases=phases.PHASES,
        depth_skips=phases.DEPTH_SKIPS,
        knowledge_gate=phases.KNOWLEDGE_GATE,
        extra_card_text=_extra_card_text,
    )
    # last_phase 由 __post_init__ 从 phases 末尾推导，但显式取 phases.py 的权威值
    # 保持与 phases.LAST_PHASE 一致（防 phases 顺序异常时静默错位）
    spec.last_phase = phases.LAST_PHASE
    _registry_register(spec)


# 暴露给控制器/测试的便捷入口
def spec() -> WorkflowSpec:
    from registry import get_workflow
    s = get_workflow(WORKFLOW_NAME)
    if s is None:
        register()
        s = get_workflow(WORKFLOW_NAME)
    return s
