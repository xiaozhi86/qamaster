#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
registry.py — WorkflowSpec 数据结构 + 注册表

WorkflowSpec 是 workflow 无关的阶段机描述：控制器据此取阶段、裁剪、门禁、
输出目录、skill 目录、专属卡片文案钩子。新增 skill 只需构造一份 WorkflowSpec
并 register()，无需改动控制器（qamaster_runtime.py 按 --workflow 路由）。

显式注册（无 import 副作用）：各 <name>.py 暴露 register()，由 main() 调用。
"""
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class WorkflowSpec:
    """一个 workflow 的阶段机 + 元数据。

    fields:
      name          — "case-design" 等；用于状态分区路径与 --workflow 取值
      output_dir    — 产物目录相对 workdir，如 "case-design-out"
      skill_dir     — skill 根相对 workdir，如 "skills/case-design"
      phases        — 阶段列表（dict 形状，与 phases.py 兼容）
      depth_skips   — {"heavy":[],"medium":[4],"light":[3,4]} 裁剪表
      knowledge_gate— Phase14 confirm 后置动作的门禁（脚本列表；可空）
      last_phase    — 末阶段号
      skill_md      — SKILL.md 相对 workdir 路径（默认 <skill_dir>/SKILL.md）
      extra_card_text — 可选钩子 (phase, st) -> str，给 _card 追加 workflow 专属片段
      methodology_capture_phases — 方法论捕捉提醒（##METHODOLOGY_CAPTURE##）的阶段集合；
        默认 {14, 15}（case-design 审核门/许可门）；requirement-review 设 {4, 7}（用户确认门/最终输出门）
    """
    name: str
    output_dir: str
    skill_dir: str
    phases: List[Dict[str, Any]]
    depth_skips: Dict[str, List[int]]
    knowledge_gate: List[Dict[str, Any]] = field(default_factory=list)
    last_phase: int = 0
    skill_md: Optional[str] = None
    extra_card_text: Optional[Callable[[int, Dict[str, Any]], str]] = None
    methodology_capture_phases: set = field(default_factory=lambda: {14, 15})

    def __post_init__(self):
        if self.skill_md is None:
            self.skill_md = os.path.join(self.skill_dir, "SKILL.md")
        if not self.phases:
            self.last_phase = 0
        else:
            self.last_phase = self.phases[-1]["id"]

    # —— 阶段机 helper（与 phases.py 同名函数保持行为一致）——

    @property
    def phase_by_id(self) -> Dict[int, Dict[str, Any]]:
        return {p["id"]: p for p in self.phases}

    def get_phase(self, phase_id):
        return self.phase_by_id.get(phase_id)

    def effective_phases(self, depth):
        skips = set(self.depth_skips.get(depth or "heavy", []))
        return [p["id"] for p in self.phases if p["id"] not in skips]

    def next_phase_id(self, current, depth):
        seq = self.effective_phases(depth)
        if current not in seq:
            return None
        i = seq.index(current)
        return seq[i + 1] if i + 1 < len(seq) else None

    def find_phase_by_name(self, token):
        token = (token or "").strip()
        if not token:
            return None
        if token.isdigit():
            return self.phase_by_id.get(int(token))
        for p in self.phases:
            if token in p["name"]:
                return p
        return None


# —— 注册表（进程内单例；显式 register，无 import 副作用）——

_REGISTRY: Dict[str, WorkflowSpec] = {}


def register(spec: WorkflowSpec):
    """显式注册一个 workflow。重复注册覆盖（便于测试重置）。"""
    _REGISTRY[spec.name] = spec


def get_workflow(name: str) -> Optional[WorkflowSpec]:
    return _REGISTRY.get(name)


def list_workflows() -> List[str]:
    return sorted(_REGISTRY.keys())


def clear_registry():
    """测试辅助：清空注册表。生产代码不应调用。"""
    _REGISTRY.clear()
