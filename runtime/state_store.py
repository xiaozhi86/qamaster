#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
state_store.py — qamaster Runtime 权威状态存储（原子 JSON 读写）

Runtime Engineering 核心原则（见 qamaster-Agent-Runtime-Engineering-Refactor-Design-v2.0.0.md）：
    模型负责思考，Runtime 负责控制。任何模型不可绕过。

本模块是唯一被允许读写 runtime state.json 的代码路径（单一事实源）。

【多需求并行】状态按 (workflow, req_id) 分区，每个在途需求独立 state.json：
    <工作目录>/.qamaster/<workflow>/<req_id>/state.json
分区后每个 in-flight 需求有独立 state/checkpoint，单写者无并发 clobber。
MANIFEST.md 是唯一共享可变资源，由 locking.FileLock 串行化（见 qamaster_runtime.cmd_manifest）。

并发/中断安全：
  - 写入采用 tmp 文件 + os.replace 原子替换，避免会话中断留下半个 JSON
  - 读取失败（文件损坏）时不静默覆盖，抛 StateCorruptError 交上层显式处理

仅用 Python 标准库。
"""
import json
import os
import tempfile
import time

SCHEMA_VERSION = 3

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

# 状态分区根目录（同 workdir 下按 workflow/req_id 隔离）
QAMASTER_ROOT = ".qamaster"
# 旧单例状态目录（迁移源；迁移后保留，由 reset --legacy 显式清理）
LEGACY_RUNTIME_DIR = os.path.join("case-design-out", ".runtime")


class StateCorruptError(Exception):
    """state.json 存在但无法解析——禁止静默重置（会丢失用户确认记录）。"""


def default_state_path(workdir, workflow=None, req_id=None):
    """返回状态文件路径。

    新分区布局（推荐）：<workdir>/.qamaster/<workflow>/<req_id>/state.json
        —— 每个 (workflow, req_id) 独立，无并发 clobber。
    旧单例路径（deprecated shim，仅迁移/兼容代码用）：
        <workdir>/case-design-out/.runtime/state.json
        —— 不再作为事实源；保留以支撑惰性迁移与 test_runtime.py 兼容期。
    """
    if workflow and req_id:
        return os.path.join(workdir, QAMASTER_ROOT, workflow, req_id, "state.json")
    # deprecated: legacy single-state path
    return os.path.join(workdir, LEGACY_RUNTIME_DIR, "state.json")


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def new_state(workflow, req_id, workdir):
    return {
        "schema": SCHEMA_VERSION,
        "workflow": workflow,                # "case-design"
        "req_id": req_id or "",              # 需求标识（由 bootstrap 派生，恒非空）
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
        "patch_directives": [],              # G-FB1: 增量反哺指令 [{target_phase,target_name,from_phase,reason}]
        "history": [],                       # 阶段迁移审计日志 [{ts,event,phase,detail}]
        "created_at": _now(),
        "updated_at": _now(),
    }


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
    if schema not in (1, 2, 3):
        raise StateCorruptError("state.json schema 不符: %s (schema=%s)" % (path, schema))
    # v0.7.0: schema=1 兼容——自动补 artifacts/gate_rounds，不报错
    if schema == 1:
        st["schema"] = 2
        st.setdefault("artifacts", {})
        st.setdefault("gate_rounds", {})
        schema = 2
    # v0.8.0: schema=2→3 无字段变更，仅版本标记升级
    # （分区路径迁移由 migrate_legacy_state 处理；此处只升版本号让降级可检测）
    if schema == 2:
        st["schema"] = SCHEMA_VERSION
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


def list_active_reqs(workdir, workflow):
    """返回该 workdir 下该 workflow 所有存在 state.json 的 req_id（供 status --all + bootstrap 碰撞检查）。

    含已完成（DONE）的 req——供 bootstrap 复用检测与 status 全量展示；
    调用方需自行按 status 过滤 in-flight。返回排序后的 req_id 列表。
    """
    root = os.path.join(workdir, QAMASTER_ROOT, workflow)
    if not os.path.isdir(root):
        return []
    reqs = []
    for req_id in os.listdir(root):
        if os.path.isfile(os.path.join(root, req_id, "state.json")):
            reqs.append(req_id)
    return sorted(reqs)


def migrate_legacy_state(workdir, workflow):
    """旧 case-design-out/.runtime/state.json → .qamaster/<workflow>/<req_id>/（惰性、幂等、崩溃安全）。

    仅 case-design workflow 有 legacy 路径；其它 workflow 直接 no-op。
    req_id 非空 → 连同 checkpoint 一起迁移到分区路径；
    req_id 为空 → 拒绝自动迁移（归属不明，需人工 `reset --legacy` 清理）。
    新分区已存在 state.json 时跳过状态覆写（新分区是事实源，可能更新），仍尝试补迁 checkpoint。
    旧 .runtime/ 迁移后保留（不自动删用户数据）。

    返回 (migrated: bool, req_id_or_None, reason: str)。
    """
    if workflow != "case-design":
        return (False, None, "non-case-design workflow has no legacy state")
    legacy_dir = os.path.join(workdir, LEGACY_RUNTIME_DIR)
    legacy_state = os.path.join(legacy_dir, "state.json")
    if not os.path.isfile(legacy_state):
        return (False, None, "no legacy state")
    try:
        st = load(legacy_state)
    except StateCorruptError as e:
        return (False, None, "legacy state corrupt: %s" % e)
    if st is None:
        return (False, None, "no legacy state")
    req_id = (st.get("req_id") or "").strip()
    if not req_id:
        return (False, None, "legacy state has empty req_id — ownership ambiguous; run 'reset --legacy' to clear")
    new_path = default_state_path(workdir, workflow, req_id)
    migrated = False
    if not os.path.isfile(new_path):
        # 升版本到当前 schema（load 已升到 3，但显式置防漏）
        st["schema"] = SCHEMA_VERSION
        save(new_path, st)
        migrated = True
    # checkpoint 迁移（幂等、best-effort；os.replace 同盘原子）
    if os.path.isdir(legacy_dir):
        for fname in os.listdir(legacy_dir):
            if fname.startswith("checkpoint_") and fname.endswith(".md"):
                src = os.path.join(legacy_dir, fname)
                dst = os.path.join(os.path.dirname(new_path), fname)
                if os.path.isfile(src) and not os.path.isfile(dst):
                    try:
                        os.replace(src, dst)
                    except OSError:
                        pass
    return (migrated, req_id, "migrated" if migrated else "already migrated")
