#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
state_store.py — qamaster Runtime 权威状态存储（原子 JSON 读写）

Runtime Engineering 核心原则（见 qamaster-Agent-Runtime-Engineering-Refactor-Design-v1.0.0.md）：
    模型负责思考，Runtime 负责控制。任何模型不可绕过。

本模块是唯一被允许读写 runtime state.json 的代码路径（单一事实源）。
状态文件默认位于 <工作目录>/case-design-out/.runtime/state.json，
与需求产出物同目录（case-design-out/ 已在 .gitignore，不入库）。

并发/中断安全：
  - 写入采用 tmp 文件 + os.replace 原子替换，避免会话中断留下半个 JSON
  - 读取失败（文件损坏）时不静默覆盖，抛 StateCorruptError 交上层显式处理

仅用 Python 标准库。
"""
import json
import os
import tempfile
import time

SCHEMA_VERSION = 2

# 运行模式与流程深度枚举（与 SKILL.md 6.5 / phase0_manifest.md 步骤五 一致）
RUN_MODES = ("full", "auto", "light")          # full=完整(默认) / auto=连跑 / light=轻量
DEPTHS = ("heavy", "medium", "light")          # heavy=重型15步 / medium=中型 / light=轻型
INPUT_KINDS = ("requirement", "contract")      # requirement=纯需求 / contract=契约驱动分支
PHASE_KINDS = ("auto", "confirm", "license")   # auto=自动门 / confirm=人工确认 / license=许可门

# status 取值：
#   RUNNING          — 当前阶段产物尚未通过出口门禁
#   GATE_PASSED      — 当前阶段出口门禁已通过，允许 next 推进
#   WAIT_USER_CONFIRM— confirm 类阶段产物已生成，等待用户答复/审核
#   WAIT_LICENSE     — license 类阶段等待用户许可（Excel 生成许可）
#   REVIEW_PENDING   — 连跑/轻量模式下人工门禁已标注待审核、自动放行（审计痕迹）
#   DONE             — 流程全部完成
TERMINAL_STATUS = "DONE"


class StateCorruptError(Exception):
    """state.json 存在但无法解析——禁止静默重置（会丢失用户确认记录）。"""


def default_state_path(workdir):
    return os.path.join(workdir, "case-design-out", ".runtime", "state.json")


def new_state(workflow, req_id, workdir):
    return {
        "schema": SCHEMA_VERSION,
        "workflow": workflow,                # "case-design"
        "req_id": req_id or "",              # 需求标识（用户未提供时由 Phase0 后 set 补写）
        "workdir": os.path.abspath(workdir),
        "current_phase": 0,
        "completed": [],                     # 已通过出口门禁的阶段编号
        "status": "RUNNING",
        "run_mode": "full",
        "depth": None,                       # Phase0 判定的流程深度（heavy/medium/light）
        "input_kind": "requirement",         # Phase0 输入形态探测结果
        "skipped_phases": [],                # 按 depth 裁剪的阶段
        "failed_gates": {},                  # {"<phase>": {"script":..,"rc":..,"at":..}} 审计痕迹
        "confirm_rounds": 0,                 # 当前 confirm 门禁的往返轮次（审核反馈修改次数）
        "gate_rounds": {},                   # v0.7.0: {"<phase>": n} 自动门原地返修轮次（≥3 强制人工）
        "artifacts": {},                     # v0.7.0: 制品注册表 {"req":.., "ledger":.., "3":{rule_ids}, "5":{risk_ids,levels}, "7":{tp_ids}, "8":{case_ids,rule_refs}}
        "history": [],                       # 阶段迁移审计日志 [{ts,event,phase,detail}]
        "created_at": _now(),
        "updated_at": _now(),
    }


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def load(path):
    """读取状态；不存在返回 None；损坏抛 StateCorruptError。"""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            st = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise StateCorruptError("state.json 损坏: %s (%s)" % (path, e))
    if not isinstance(st, dict):
        raise StateCorruptError("state.json 损坏: %s (非 dict)" % path)
    schema = st.get("schema")
    if schema not in (1, 2):
        raise StateCorruptError("state.json schema 不符: %s (schema=%s)" % (path, schema))
    # v0.7.0: schema=1 兼容——自动补 artifacts/gate_rounds，不报错
    if schema == 1:
        st["schema"] = 2
        st.setdefault("artifacts", {})
        st.setdefault("gate_rounds", {})
    return st


def save(path, st):
    """原子写入状态（Windows 上 os.replace 偶发 PermissionError：杀毒/索引短暂锁定，有限重试）。"""
    st["updated_at"] = _now()
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".state.", suffix=".tmp", dir=d or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
        last_err = None
        for attempt in range(4):
            try:
                os.replace(tmp, path)
                return
            except PermissionError as e:
                last_err = e
                time.sleep(0.1 * (2 ** attempt))
        raise last_err
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def log_event(st, event, phase=None, detail=""):
    st["history"].append({
        "ts": _now(),
        "event": event,
        "phase": st.get("current_phase") if phase is None else phase,
        "detail": detail,
    })
    # 历史日志有界（防无限增长），保留最近 500 条
    if len(st["history"]) > 500:
        st["history"] = st["history"][-500:]
