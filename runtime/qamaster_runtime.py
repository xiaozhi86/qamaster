#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qamaster_runtime.py — qamaster Runtime Controller（流程状态机 CLI）

设计依据：qamaster-Agent-Runtime-Engineering-Refactor-Design-v1.0.0.md
    模型负责思考，Runtime 负责控制。任何模型不可绕过。

本 CLI 是 0-14(+Excel) 阶段流程的唯一权威控制点：
  - 阶段迁移（next）：只允许 current+1（按流程深度裁剪后的序列），非法跳转被拒绝
  - 质量门（gate）：机器门跑确定性检查（文件存在性 + skill 自带校验脚本），
    人工门（confirm/license）在完整模式必须用户 confirm 才放行
  - 契约卡渲染：每个阶段向模型输出 CURRENT PHASE / ALLOWED / FORBIDDEN /
    PRODUCES / EXIT CONDITION，模型无法决定下一阶段

用法（cwd = 用户工作目录）：
  python qamaster_runtime.py start   [--req-id X] [--mode full|auto|light] [--user-input "..."] [--workdir DIR]
  python qamaster_runtime.py status  [--workdir DIR]
  python qamaster_runtime.py next    [--workdir DIR]
  python qamaster_runtime.py gate    [--workdir DIR]
  python qamaster_runtime.py confirm [--workdir DIR]
  python qamaster_runtime.py reject  [--workdir DIR]
  python qamaster_runtime.py fail    --to <阶段号|阶段名> --reason "..." [--workdir DIR]
  python qamaster_runtime.py set     --req-id X [--depth heavy|medium|light] [--input-kind requirement|contract]
                                     [--knowledge done] [--excel asked|na] [--workdir DIR]
  python qamaster_runtime.py plan    [--workdir DIR]
  python qamaster_runtime.py verify  [--workdir DIR]
  python qamaster_runtime.py reset   [--workdir DIR]

约定：
  - 状态文件：<workdir>/case-design-out/.runtime/state.json（与产出物同目录，不入库）
  - skill 资产（scripts/references/config）通过插件根自动定位，不要求 cwd 是插件目录
  - 所有 gate 输出遵循"机器判定为准，禁止模型自证"：PASS/FAIL 由脚本退出码与确定性检查给出
"""
import argparse
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state_store  # noqa: E402
import phases as P  # noqa: E402

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_ROOT = os.path.join(PLUGIN_ROOT, "skills", "case-design")
SKILL_SCRIPTS = os.path.join(SKILL_ROOT, "scripts")
SKILL_MD = os.path.join(SKILL_ROOT, "SKILL.md")

APPROVE_HINT = "审核通过 / 无问题 / confirm / approve"


def _utf8():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _load_or_die(workdir, need=True):
    path = state_store.default_state_path(workdir)
    st = state_store.load(path)
    if st is None and need:
        _die("未找到运行状态（%s）。请先执行: python \"%s\" start" % (path, os.path.abspath(__file__)))
    return st, path


def _die(msg, rc=2):
    print("RUNTIME_ERROR: %s" % msg)
    sys.exit(rc)


def _audit_degraded_artifacts(workdir, st):
    """降级产物对账（v0.6.0 事故修复）：检测『无 Runtime 裁决却已有用例落盘』的降级执行痕迹。

    触发条件（任一）：
      a) state.json 不存在（首次 start），但 case-design-out/ 下已有 TestCases_*.md
         —— 用例是在无状态机裁决的情况下落盘的（手动降级或他处生成）；
      b) state.json 存在，current_phase < 13，但 TestCases_*.md 已存在
         —— 用例先于写盘门(Phase 13)落盘，未过 verify_md/verify_cases 机器校验。
    处理：打印显式警告（不阻断、不删除产出物），要求先对这些文件补跑
    verify_md.py + verify_cases.py（Phase 13 的 gate_checks 同口径），
    通过后方可信任其覆盖结论；降级期间交付摘要中『脚本校验摘要』若填了数值，一律视为编造。
    """
    try:
        tc_hits = sorted(glob.glob(os.path.join(workdir, "case-design-out", "TestCases_*.md")))
    except Exception:
        return []
    tc_hits = [t for t in tc_hits if os.path.isfile(t)]
    if not tc_hits:
        return []
    phase = (st or {}).get("current_phase", -1) if st else -1
    degraded = (st is None) or (phase < 13)
    if not degraded:
        return []
    names = [os.path.basename(t) for t in tc_hits]
    print("!" * 64)
    print("【降级产物对账警告】检测到未经 Runtime 裁决的用例产出物（v0.6.0 事故修复）：")
    for n in names:
        print("  ! case-design-out/%s" % n)
    print("  原因: %s" % ("state.json 缺失——用例为无状态机裁决的降级执行产物" if st is None
                       else "当前阶段=Phase %s(<13)——用例先于写盘门落盘，未过机器校验" % phase))
    print("  处置（强制·先补验后信任）: 对每个文件补跑写盘门同口径校验——")
    print("    python \"%s\" \"case-design-out/<文件>\"  （结构）" % os.path.join(SKILL_SCRIPTS, "verify_md.py"))
    print("    python \"%s\" \"case-design-out/<文件>\" \"case-design-out/REQ_<需求标识>.md\"  （内容+覆盖硬门）" % os.path.join(SKILL_SCRIPTS, "verify_cases.py"))
    print("  verify_cases.py 现含覆盖硬门（#4-H 需求引用率/#6-H 接口三类/RK P0-P1 风险），")
    print("  exit=1 即覆盖不达标——须补齐用例后重写，禁止以『核心用例已交付』收尾。")
    print("  降级期间该产出物的交付摘要若『脚本校验摘要』填了数值而非『未执行』，一律视为编造（SKILL.md 3.1 红线）。")
    print("!" * 64)
    print()
    return names


def _rt_cmd():
    return 'python "%s"' % os.path.abspath(__file__)


def _fmt_cmd(cmd, st):
    req = st.get("req_id") or "<需求标识>"
    return cmd.replace("{skill_scripts}", SKILL_SCRIPTS).replace("{req_id}", req)


def _backfill_artifacts(st, phase, checkpoint_path, stdout_lines=None):
    """v0.7.0: gate PASS 时解析检查点产物，回填 state.json['artifacts'][<phase>]。

    从 phase-gate stdout 的 ##PHASE_ARTIFACTS## 行解析各 prefix 的 ID 范围
    （R/RK/TP/API/SC/A），写入 artifacts[<phase>]={"ids":{prefix:"1-24"},...,"passed":True}。
    供契约卡 PRIOR_ARTIFACTS 渲染实际 ID 范围（不靠模型记忆）。stdout 无该行时退回标记。
    """
    if "artifacts" not in st or not isinstance(st.get("artifacts"), dict):
        st["artifacts"] = {}
    entry = {"checkpoint": os.path.basename(checkpoint_path), "passed": True, "ids": {}}
    if stdout_lines:
        for ln in stdout_lines:
            s = ln.strip()
            if s.startswith("##PHASE_ARTIFACTS##"):
                # 格式: ##PHASE_ARTIFACTS## <phase>:R=1-24(24);RK=1-17(17);...
                body = s[len("##PHASE_ARTIFACTS##"):].strip()
                if ":" in body:
                    segs = body.split(":", 1)[1]
                    for seg in segs.split(";"):
                        if "=" in seg:
                            k, v = seg.split("=", 1)
                            entry["ids"][k.strip()] = v.strip()
                break
    st["artifacts"][str(phase)] = entry


def _prior_artifacts_block(st, phase):
    """v0.7.0: 渲染契约卡的 PRIOR_ARTIFACTS 段——按当前阶段 consumes 注入上游制品 ID 范围。

    不靠模型记忆：runtime 把已沉淀阶段的实际 ID 范围（R1-R24 / RK1-RK17 等）+ 台账/REQ
    注入契约卡。模型无需读检查点文件即可知上游有哪些 ID 可引用。
    """
    consumes = phase.get("consumes", [])
    if not consumes:
        return ""
    workdir = st.get("workdir", os.getcwd())
    req_id = st.get("req_id", "")
    out = os.path.join(workdir, "case-design-out")
    artifacts = st.get("artifacts", {})
    lines = ["PRIOR_ARTIFACTS（本阶段必须消费的上游制品·由 Runtime 注入，勿凭记忆）:"]
    for c in consumes:
        if c == "req":
            p = os.path.join(out, ("REQ_%s.md" % req_id) if req_id else "REQ_<需求标识>.md")
            lines.append("  需求文档: case-design-out/%s" % os.path.basename(p))
        elif c == "ledger":
            p = os.path.join(out, ("Clarification_Ledger_%s.md" % req_id) if req_id else "")
            if p and os.path.exists(p):
                lines.append("  澄清台账: case-design-out/%s（已解决/待确认/假设 见台账）" % os.path.basename(p))
        elif c.isdigit():
            art = artifacts.get(c, {})
            ids = art.get("ids", {})
            if ids:
                id_desc = " | ".join("%s=%s" % (k, v) for k, v in ids.items())
                lines.append("  Phase %s 制品: %s（已沉淀·ID 范围）" % (c, id_desc))
            else:
                cp = os.path.join(out, ".runtime", "checkpoint_%s.md" % c)
                mark = "（已沉淀）" if os.path.exists(cp) else "（未沉淀·前置阶段未完成？）"
                lines.append("  Phase %s 制品: case-design-out/.runtime/checkpoint_%s.md %s" % (c, c, mark))
    lines.append("  消费约束: 关联规则列 R/RK/TP/API 须在上游清单内（悬空引用 exit=1）；用例等级须映射 RK 等级；")
    lines.append("            台账'已解决'事实须落成断言；假设A<n> 须在台账假设清单内；台账'待确认'须闭环或转假设")
    return "\n".join(lines)


def _run_check(chk, st):
    """执行单条确定性检查，返回 (ok, detail)。"""
    workdir = st["workdir"]
    kind = chk.get("kind")
    if kind == "exists":
        p = os.path.join(workdir, chk["path"])
        return (os.path.isfile(p), "%s: %s" % (chk["label"], "存在" if os.path.isfile(p) else "缺失"))
    if kind == "exists_any":
        hits = []
        for pat in chk["patterns"]:
            hits.extend(glob.glob(os.path.join(workdir, pat)))
        return (bool(hits), "%s: %s" % (chk["label"], ("命中 %d 个" % len(hits)) if hits else "缺失"))
    if kind == "phase_gate":
        # v0.7.0: 阶段出口门禁——调 verify_cases.py --phase-gate <N> <checkpoint> --req .. --ledger ..
        phase = chk.get("phase")
        if phase is None:
            return (False, "%s: phase_gate 缺 phase 参数" % chk["label"])
        cp = os.path.join(workdir, "case-design-out", ".runtime", "checkpoint_%d.md" % phase)
        req_path = os.path.join(workdir, "case-design-out",
                                ("REQ_%s.md" % st.get("req_id", "")) if st.get("req_id") else "REQ_<需求标识>.md")
        ledger_path = os.path.join(workdir, "case-design-out",
                                  ("Clarification_Ledger_%s.md" % st.get("req_id", "")) if st.get("req_id") else None)
        parts = ['python "%s" --phase-gate %d "%s"' % (os.path.join(SKILL_SCRIPTS, "verify_cases.py"), phase, cp)]
        if os.path.exists(req_path):
            parts.append('--req "%s"' % req_path)
        if ledger_path and os.path.exists(ledger_path):
            parts.append('--ledger "%s"' % ledger_path)
        run_mode = st.get("run_mode", "full")
        parts.append('--run-mode %s' % run_mode)
        cmd = " ".join(parts)
        try:
            proc = subprocess.run(cmd, shell=True, cwd=workdir, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=600)
        except Exception as e:
            return (False, "%s: 执行异常 %s" % (chk["label"], e))
        all_lines = (proc.stdout or "").strip().splitlines()
        detail = "%s: exit=%d" % (chk["label"], proc.returncode)
        fail_lines = [ln for ln in all_lines if ln.strip().startswith("[FAIL]")]
        if proc.returncode != 0:
            if fail_lines:
                detail += "\n----- phase-gate FAIL 明细 -----\n" + "\n".join(fail_lines[:10])
            elif all_lines:
                detail += "\n----- 输出(尾部) -----\n" + "\n".join(all_lines[-15:])
        # v0.7.0: gate PASS 时回填 artifacts（从 ##PHASE_ARTIFACTS## 行解析 ID 范围）+ 重置 gate_rounds
        if proc.returncode == 0:
            _backfill_artifacts(st, phase, cp, stdout_lines=all_lines)
            st["gate_rounds"][str(phase)] = 0
        return (proc.returncode == 0, detail)
    if kind == "script":
        cmd = _fmt_cmd(chk["cmd"], st)
        try:
            proc = subprocess.run(cmd, shell=True, cwd=workdir, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=600)
        except Exception as e:
            return (False, "%s: 执行异常 %s" % (chk["label"], e))
        all_lines = (proc.stdout or "").strip().splitlines()
        tail = all_lines[-25:] if len(all_lines) > 25 else all_lines
        detail = "%s: exit=%d" % (chk["label"], proc.returncode)
        if proc.returncode != 0:
            if tail:
                detail += "\n----- 脚本输出(尾部) -----\n" + "\n".join(tail)
            # [FAIL] 行是修复指令本体；软提示明细较长时可能被截断出 tail，须全量补捞，
            # 否则模型拿不到可执行的修复目标（v0.6.0 事故修复·覆盖硬门）
            fail_lines = [ln for ln in all_lines if ln.strip().startswith("[FAIL]")]
            missing_fails = [ln for ln in fail_lines if not any(ln in t for t in tail)]
            if missing_fails:
                detail += "\n----- 硬门 FAIL 明细(补捞) -----\n" + "\n".join(missing_fails[:10])
        else:
            # 成功时保留摘要行（##VERIFY_SUMMARY##/结论行），供 gate 输出取证与交付摘要摘抄
            keep = [ln for ln in all_lines if ln.startswith("##VERIFY_SUMMARY##") or "结论" in ln or "硬门" in ln]
            if keep:
                detail += " | " + " ; ".join(keep)[:300]
        return (proc.returncode == 0, detail)
    return (False, "未知检查类型: %s" % kind)


def _card(st, phase, extra=""):
    """渲染阶段契约卡（发送给模型的唯一控制协议）。"""
    idx = P.effective_phases(st.get("depth") or "heavy").index(phase["id"]) + 1
    total = len(P.effective_phases(st.get("depth") or "heavy"))
    mode_cn = {"full": "完整", "auto": "连跑", "light": "轻量"}.get(st.get("run_mode"), st.get("run_mode"))
    depth_cn = {"heavy": "重型", "medium": "中型", "light": "light"}.get(st.get("depth") or "heavy")
    lines = []
    lines.append("=" * 64)
    lines.append("【RUNTIME CONTRACT — 由 qamaster Runtime 颁发，模型必须遵守，不得自改流程】")
    lines.append("=" * 64)
    lines.append("CURRENT PHASE: Phase %d — %s （流程进度 %d/%d）" % (phase["id"], phase["name"], idx, total))
    lines.append("需求标识: %s | 运行模式: %s | 流程深度: %s | 输入形态: %s" % (
        st.get("req_id") or "(未提供，Phase0 判定)", mode_cn, depth_cn,
        "契约驱动" if st.get("input_kind") == "contract" else "纯需求"))
    lines.append("本阶段规范: skills/case-design/SKILL.md（全局核心）+ 下方细则参考（阶段唯一细则来源，进入本阶段前先读）")
    for r in phase.get("refs", []):
        lines.append("细则参考: %s" % os.path.join("skills", "case-design", r))
    lines.append("")
    lines.append("OBJECTIVE: %s" % phase["objective"])
    lines.append("")
    lines.append("ALLOWED（本阶段只允许）:")
    for a in phase["allowed"]:
        lines.append("  + %s" % a)
    lines.append("")
    lines.append("FORBIDDEN（本阶段禁止）:")
    for f in phase["forbidden"]:
        lines.append("  - %s" % f)
    if phase.get("produces"):
        lines.append("")
        lines.append("PRODUCES（本阶段必须产出的落盘物）:")
        for p_ in phase["produces"]:
            lines.append("  * %s" % p_)
    lines.append("")
    lines.append("EXIT CONDITION（出口门禁）: %s" % phase["exit_condition"])
    gate = phase["gate"]
    lines.append("")
    if gate == "auto":
        lines.append("GATE 类型: 自动门。完成本阶段产物后立即执行：")
        lines.append("  %s gate" % _rt_cmd())
        lines.append("  - PASS → 再执行 `next` 进入下一阶段；FAIL → 按修复指令原地修复后重跑 gate（禁止自行跳阶段）")
    elif gate == "confirm":
        lines.append("GATE 类型: 人工确认门。向用户输出本阶段确认请求后【停止等待】；")
        lines.append("  收到用户答复后执行: %s gate（查看放行判定）" % _rt_cmd())
        if phase["id"] == 14:
            lines.append("  完整模式必须用户明确回复「%s」后执行 `confirm` 放行；用户反馈问题时执行 `fail --to <受影响最深阶段> --reason \"...\"` 回退重走" % APPROVE_HINT)
        else:
            lines.append("  完整模式 P0/P1 缺口必须等用户答复（答复落盘台账后执行 `confirm`）；连跑/轻量 P2/P3 可登记假设后 gate 自动放行")
    elif gate == "license":
        lines.append("GATE 类型: 许可门。询问用户是否生成 Excel；用户同意 → `confirm` 放行；用户拒绝 → `reject` 结束流程")
    lines.append("")
    lines.append("流程铁律（违反即判定执行缺陷）:")
    lines.append("  1. 严格按 Runtime 颁发的当前阶段执行，禁止跳阶段/合并阶段/提前输出后续阶段产物")
    lines.append("  2. 每次接到用户消息（澄清答复/审核反馈/Excel许可）后，先执行 `status` 或 `gate` 恢复权威状态再继续")
    lines.append("  3. 本阶段产物未过 gate，禁止进入下一阶段；模型无权自行宣布阶段完成")
    lines.append("  4. 产出物全部写入 <工作目录>/case-design-out/ 下；写盘约束见 output_write.md（单文件一次 Write，禁止 Edit 增量）")
    # v0.7.0: 注入 PRIOR_ARTIFACTS（按当前阶段 consumes）
    prior = _prior_artifacts_block(st, phase)
    if prior:
        lines.append("")
        lines.append(prior)
    if extra:
        lines.append("")
        lines.append(extra)
    return "\n".join(lines)


def _resume_hint(st):
    phase = P.get_phase(st["current_phase"])
    if st["status"] == "WAIT_USER_CONFIRM":
        return ("状态: WAIT_USER_CONFIRM（等待用户确认/答复）\n"
                "处理: 用户已答复 → 先将答复落盘（台账/假设），再执行 `gate` 判定放行；\n"
                "      用户反馈问题 → 执行 `fail --to <阶段> --reason \"...\"` 回退到受影响最深阶段重走")
    if st["status"] == "WAIT_LICENSE":
        return ("状态: WAIT_LICENSE（等待 Excel 许可）\n"
                "处理: 用户同意 → `confirm` 执行生成门禁；用户拒绝 → `reject` 结束（流程 DONE）")
    if st["status"] == "REVIEW_PENDING":
        return ("状态: REVIEW_PENDING（连跑/轻量已标注待审核放行，当前阶段门禁已过）\n"
                "处理: 执行 `next` 推进；知识沉淀后置动作在 Excel 许可环节前完成")
    if st["status"] == "DONE":
        return "状态: DONE（流程已完成）。如需修改，用 `start` 开启新一轮（Runtime 会定位已有产出物）。"
    if st["status"] == "GATE_PASSED":
        return "状态: GATE_PASSED（当前阶段门禁已通过）\n处理: 执行 `next` 进入下一阶段"
    return "状态: RUNNING（阶段产物尚未过出口门禁）"


# ---------------------------------------------------------------- commands

def cmd_start(a):
    workdir = a.workdir
    path = state_store.default_state_path(workdir)
    try:
        existing = state_store.load(path)
    except state_store.StateCorruptError as e:
        _die(str(e) + "。请先人工检查/备份后删除该文件再 start")
    if existing and not a.fresh:
        _audit_degraded_artifacts(workdir, existing)
        phase = P.get_phase(existing["current_phase"])
        print("检测到进行中的流程（断点续跑，禁止重新生成覆盖已落盘产物）:")
        print("  req_id=%s phase=%d(%s) status=%s" % (
            existing.get("req_id"), phase["id"], phase["name"], existing["status"]))
        print(_resume_hint(existing))
        print()
        print(_card(existing, phase))
        return
    _audit_degraded_artifacts(workdir, None)
    st = state_store.new_state("case-design", a.req_id or "", workdir)
    if a.mode:
        st["run_mode"] = a.mode
    state_store.log_event(st, "start", detail="mode=%s" % st["run_mode"])
    state_store.save(path, st)
    phase = P.get_phase(0)
    print("Runtime 已启动（workflow=case-design, mode=%s）。" % st["run_mode"])
    print("全局业务规范（避坑红线/输入协议/运行模式细则，一次性阅读）: %s" % SKILL_MD)
    print("其后每个阶段只读 Runtime 颁发的契约卡与对应 references 细则，按契约执行。")
    print()
    print(_card(st, phase))


def cmd_status(a):
    st, _ = _load_or_die(a.workdir)
    phase = P.get_phase(st["current_phase"])
    print(json.dumps({
        "workflow": st["workflow"], "req_id": st.get("req_id"),
        "current_phase": st["current_phase"], "phase_name": phase["name"],
        "completed": st["completed"], "status": st["status"],
        "run_mode": st["run_mode"], "depth": st.get("depth"),
        "input_kind": st.get("input_kind"), "skipped_phases": st.get("skipped_phases"),
        "excel": st.get("excel"), "knowledge": st.get("knowledge"),
        "updated_at": st["updated_at"],
    }, ensure_ascii=False, indent=2))
    print()
    print(_resume_hint(st))
    if a.card:
        print()
        print(_card(st, phase))


def cmd_next(a):
    st, path = _load_or_die(a.workdir)
    if st["status"] in ("WAIT_USER_CONFIRM", "WAIT_LICENSE"):
        _die("当前处于 %s，必须先过人工门禁（gate/confirm/reject）才能推进" % st["status"])
    if st["status"] == "RUNNING":
        _die("当前阶段(Phase %d)尚未通过出口门禁，先执行 `gate`" % st["current_phase"])
    if st["status"] == "DONE":
        _die("流程已完成（DONE），无下一阶段；如需修改用 `fail --to <阶段>` 回退或 `start --fresh` 重启")
    # status ∈ {GATE_PASSED, REVIEW_PENDING} → 允许推进
    nxt = P.next_phase_id(st["current_phase"], st.get("depth") or "heavy")
    if nxt is None:
        _die("已是最后阶段")
    # Phase 14 → 15 前：知识沉淀后置动作必须已登记（强制，防跳过知识总结直接进 Excel）
    if st["current_phase"] == 14 and nxt == 15 and st.get("knowledge") != "done":
        _die("知识沉淀未完成（knowledge!=done）：审核通过后须先生成 case-design-out/Knowledge_<需求标识>.md "
             "并执行 `set --knowledge done`（会跑 verify_knowledge.py 结构校验），再 `next` 进 Excel 许可门。"
             "知识总结为强制后置动作，不可跳过（references/knowledge.md 31.1）")
    prev = st["current_phase"]
    if prev not in st["completed"]:
        st["completed"].append(prev)
        st["completed"].sort()
    st["current_phase"] = nxt
    st["status"] = "RUNNING"
    st["confirm_rounds"] = 0
    state_store.log_event(st, "advance", phase=nxt, detail="from=%d" % prev)
    state_store.save(path, st)
    print(_card(st, P.get_phase(nxt)))


def cmd_gate(a):
    st, path = _load_or_die(a.workdir)
    phase = P.get_phase(st["current_phase"])
    gkind = phase["gate"]

    # --- 人工门：由运行模式与用户意图决定放行/等待
    if gkind in ("confirm", "license"):
        decision = _human_gate_decision(st, phase)
        print("GATE: Phase %d (%s) — %s" % (phase["id"], phase["name"], decision["label"]))
        for ln in decision["lines"]:
            print("  " + ln)
        if decision["pass"]:
            if gkind == "license" and phase["id"] == P.LAST_PHASE:
                # 许可门自动放行（连跑/轻量且用户已声明要 Excel）：直接执行生成门禁，与 confirm 路径等价
                print("已声明要 Excel，自动放行 → 执行生成门禁...")
                ok_all = True
                for chk in phase.get("gate_checks", []):
                    ok, detail = _run_check(chk, st)
                    print(("  [PASS] " if ok else "  [FAIL] ") + detail)
                    ok_all = ok_all and ok
                if ok_all:
                    if P.LAST_PHASE not in st["completed"]:
                        st["completed"].append(P.LAST_PHASE)
                    st["status"] = "DONE"
                    st["excel"] = "generated"
                    state_store.log_event(st, "gate_pass", phase=P.LAST_PHASE, detail="via=declared_auto")
                    state_store.save(path, st)
                    print("\nGATE RESULT: PASS — Excel 已生成并通过校验，流程 DONE")
                else:
                    st["failed_gates"][str(P.LAST_PHASE)] = {"at": state_store._now()}
                    state_store.log_event(st, "excel_fail")
                    state_store.save(path, st)
                    print("\nGATE RESULT: FAIL — Excel 生成/校验未过，按 references/excel.md 生成失败处理")
                return
            st["status"] = "GATE_PASSED"
            state_store.log_event(st, "human_gate_release", phase=phase["id"], detail=decision["via"] or "")
            state_store.save(path, st)
            print("\nGATE RESULT: PASS → 执行 `next` 查看下一阶段契约卡")
        else:
            st["status"] = "WAIT_LICENSE" if gkind == "license" else "WAIT_USER_CONFIRM"
            state_store.log_event(st, "human_gate_wait", phase=phase["id"])
            state_store.save(path, st)
            print("\nGATE RESULT: WAIT — 停止，等待用户；收到答复后重跑 `gate`")
        return

    # --- 自动门：确定性检查
    results = []
    ok_all = True
    for chk in phase.get("gate_checks", []):
        ok, detail = _run_check(chk, st)
        results.append((ok, detail))
        ok_all = ok_all and ok
    print("GATE: Phase %d (%s) — 自动门" % (phase["id"], phase["name"]))
    for ok, detail in results:
        print(("  [PASS] " if ok else "  [FAIL] ") + detail)
    if not results:
        print("  （本阶段无机器检查项，产物为内存产物/已由模型按契约完成；Runtime 记录通过）")
    if ok_all:
        st["status"] = "GATE_PASSED"
        # v0.7.0: 有界返修——gate PASS 时重置 gate_rounds；FAIL 时计数（下方 else 分支）
        if str(phase["id"]) in st.get("gate_rounds", {}):
            st["gate_rounds"][str(phase["id"])] = 0
        state_store.log_event(st, "gate_pass", phase=phase["id"], detail="via=auto")
        state_store.save(path, st)
        print("\nGATE RESULT: PASS → 执行 `next` 查看下一阶段契约卡")
    else:
        # v0.7.0: 有界返修——auto 门 FAIL 计 gate_rounds，≥3 次强制人工提示（堵 silent infinite-retry）
        st.setdefault("gate_rounds", {})
        rounds = st["gate_rounds"].get(str(phase["id"]), 0) + 1
        st["gate_rounds"][str(phase["id"])] = rounds
        st["failed_gates"][str(phase["id"])] = {"at": state_store._now(), "rounds": rounds}
        state_store.log_event(st, "gate_fail", detail="; ".join(d for ok, d in results if not ok))
        state_store.save(path, st)
        print("\nGATE RESULT: FAIL — 禁止进入下一阶段。请按上方 [FAIL] 项原地修复后重跑 `gate`。")
        if rounds >= 3:
            print("【有界返修·v0.7.0】Phase %d 门禁连续失败 %d 次，疑似系统性问题：" % (phase["id"], rounds))
            print("  请人工介入审查 [FAIL] 项，或执行 `fail --to <更早阶段> --reason \"...\"` 回退重走。")
        else:
            print("禁止以任何理由绕过本门禁交付（含『脚本暂未运行/先交付后补验/核心用例先行』）——")
            print("脚本不可运行时按降级协议暂停等待（SKILL.md Runtime 控制协议·降级），不得产出用例文件。")


def _human_gate_decision(st, phase):
    """人工门放行判定（模型无关：只看运行模式 + 用户意图标记，不信模型自证）。"""
    mode = st["run_mode"]
    lines = []
    if phase["id"] == 1:
        # 澄清门：完整模式任何缺口都等用户；连跑等 P0/P1；轻量只等 P0。
        # 是否有未关闭缺口由模型在契约执行中判定并以 confirm 表达"用户已答复"——
        # Runtime 在收到 confirm 前一律 WAIT（机器保守），不放行。
        if mode == "full":
            lines.append("完整模式：无缺口或缺口已答复落盘台账后，执行 `confirm` 放行；有缺口则停止等待用户")
        elif mode == "auto":
            lines.append("连跑模式：仅 P0/P1 缺口阻断；无 P0/P1 缺口（或已记假设）时 `confirm` 放行")
        else:
            lines.append("轻量模式：仅 P0 缺口阻断；无 P0 缺口时 `confirm` 放行")
        lines.append("当前判定: WAIT（人工门默认等待；收到用户答复/确认无缺口后执行 `confirm`）")
        return {"pass": False, "label": "人工确认门(澄清)", "lines": lines, "via": None}
    if phase["id"] == 14:
        if mode == "full":
            lines.append("完整模式：必须用户明确回复「%s」后执行 `confirm` 放行" % APPROVE_HINT)
            lines.append("当前判定: WAIT — 输出审核提示（review_gate.md 话术）后停止等待")
            return {"pass": False, "label": "人工确认门(审核)", "lines": lines, "via": None}
        # 连跑/轻量：标注待审核自动放行（审计痕迹）
        state_store.log_event(st, "auto_release", detail="review gate auto-passed (%s mode), pending human review" % mode)
        lines.append("%s模式：标注「待人工审核」自动放行（审计痕迹：review_pending=true；交付报告须声明本轮未人工审核）" %
                     ("连跑" if mode == "auto" else "轻量"))
        return {"pass": True, "label": "人工确认门(审核)", "lines": lines, "via": "auto_release"}
    if phase["id"] == 15:
        if mode in ("auto", "light") and st.get("excel") == "asked_yes":
            lines.append("用户已声明要 Excel：自动放行生成")
            return {"pass": True, "label": "许可门(Excel)", "lines": lines, "via": "declared"}
        lines.append("默认需用户许可：询问「是否生成 Excel？」后停止等待；同意→`confirm`，拒绝→`reject`")
        return {"pass": False, "label": "许可门(Excel)", "lines": lines, "via": None}
    return {"pass": False, "label": "人工门", "lines": ["WAIT"], "via": None}


def cmd_confirm(a):
    """用户在人工门给出肯定答复（审核通过/同意Excel/澄清已答复）。"""
    st, path = _load_or_die(a.workdir)
    phase = P.get_phase(st["current_phase"])
    if phase["gate"] not in ("confirm", "license"):
        _die("当前阶段(Phase %d)不是人工门，confirm 无效；请执行 `gate`" % phase["id"])

    if phase["id"] == 14:
        # 审核通过 → 标记门禁已过 → 知识沉淀后置动作指引 → next 进 Excel 许可门
        st["status"] = "GATE_PASSED"
        state_store.log_event(st, "review_approved")
        state_store.save(path, st)
        extra = (
            "审核已通过。按顺序执行后置动作（review_gate.md/knowledge.md/phase0_manifest.md 时机四）：\n"
            "  1) 整表更新 MANIFEST：状态=已完成、更新时间、用例文件清单\n"
            "  2) 生成/更新知识总结 case-design-out/Knowledge_<需求标识>.md（13维度，project_cases.py 投影读用例）\n"
            "  3) 执行: %s set --knowledge done（此时会跑 verify_knowledge.py 结构校验，不过则拒绝登记）\n"
            "  4) 执行: %s next（进入 Excel 许可门）\n"
            "若知识总结已生成，直接执行第 3/4 步。" % (_rt_cmd(), _rt_cmd())
        )
        print("CONFIRM ACCEPTED: Phase 14 审核通过")
        print()
        print(extra)
        return

    if phase["id"] == 15:
        # 用户同意 Excel → 跑生成门禁（gen_excel.py）
        print("用户已许可生成 Excel，执行生成门禁...")
        ok_all = True
        for chk in phase.get("gate_checks", []):
            ok, detail = _run_check(chk, st)
            print(("  [PASS] " if ok else "  [FAIL] ") + detail)
            ok_all = ok_all and ok
        if ok_all:
            if 15 not in st["completed"]:
                st["completed"].append(15)
            st["status"] = "DONE"
            st["excel"] = "generated"
            state_store.log_event(st, "gate_pass", phase=15, detail="via=user_license")
            state_store.save(path, st)
            print("\n流程 DONE：Excel 已生成并通过校验。执行临时文件清理复核后输出交付摘要。")
        else:
            st["failed_gates"]["15"] = {"at": state_store._now()}
            state_store.log_event(st, "excel_fail")
            state_store.save(path, st)
            print("\nEXCEL GATE: FAIL — 按 references/excel.md 生成失败处理：显式输出失败报告，禁止口头声明已生成。")
        return

    # 澄清门 confirm：用户已答复（答复应由模型先落盘台账）
    st["status"] = "GATE_PASSED"
    state_store.log_event(st, "gate_pass", phase=phase["id"], detail="via=user_confirm")
    state_store.save(path, st)
    print("CONFIRM ACCEPTED: Phase %d (%s) 人工门禁通过 → 执行 `next`" % (phase["id"], phase["name"]))


def cmd_reject(a):
    """用户在许可门拒绝（不生成 Excel）→ 流程完成。"""
    st, path = _load_or_die(a.workdir)
    phase = P.get_phase(st["current_phase"])
    if phase["gate"] != "license":
        _die("当前阶段不是许可门，reject 无效")
    st["excel"] = "declined"
    st["status"] = "DONE"
    if 15 not in st["completed"]:
        st["completed"].append(15)
    state_store.log_event(st, "license_rejected", detail="user declined excel")
    state_store.save(path, st)
    print("已记录：用户不生成 Excel。流程 DONE。执行临时文件清理复核后输出交付摘要。")


def cmd_fail(a):
    """门禁失败/审核反馈问题 → 回退到受影响最深阶段重走（起点判定由模型按 output_write.md 执行）。"""
    st, path = _load_or_die(a.workdir)
    target = P.find_phase_by_name(a.to)
    if target is None:
        _die("无法解析回退目标阶段: %s（可用阶段号或名称关键词）" % a.to)
    cur = st["current_phase"]
    if target["id"] > cur:
        _die("禁止前进式 fail（目标 Phase %d > 当前 Phase %d）" % (target["id"], cur))
    # 回退：清除 target 及其后的完成记录
    st["completed"] = [c for c in st["completed"] if c < target["id"]]
    st["current_phase"] = target["id"]
    st["status"] = "RUNNING"
    st["confirm_rounds"] = st.get("confirm_rounds", 0) + 1
    state_store.log_event(st, "rollback", phase=target["id"], detail=a.reason or "")
    state_store.save(path, st)
    print("ROLLBACK: 已回退到 Phase %d (%s)，原因: %s" % (target["id"], target["name"], a.reason or ""))
    print("按 output_write.md 修改流程起点判定：从本阶段起依次顺序执行至 Phase 14，不得跳阶段；")
    print("修改范围限定（只改问题点，无问题用例原样保留）。")
    print()
    print(_card(st, target))


def _run_knowledge_gate(st):
    """执行知识沉淀门禁（verify_knowledge.py 结构校验），返回 (ok, detail)。"""
    for chk in P.KNOWLEDGE_GATE:
        ok, detail = _run_check(chk, st)
        if not ok:
            return (False, detail)
    return (True, "verify_knowledge 通过")


def cmd_set(a):
    st, path = _load_or_die(a.workdir)
    changed = []
    if a.req_id is not None:
        st["req_id"] = a.req_id
        changed.append("req_id=%s" % a.req_id)
    if a.depth is not None:
        if a.depth not in state_store.DEPTHS:
            _die("depth 取值须为 %s" % "/".join(state_store.DEPTHS))
        st["depth"] = a.depth
        st["skipped_phases"] = P.DEPTH_SKIPS.get(a.depth, [])
        # 防御：若已处于被裁剪阶段，回退到最近有效阶段
        eff = P.effective_phases(a.depth)
        if st["current_phase"] not in eff:
            st["current_phase"] = max([e for e in eff if e <= st["current_phase"]] or [0])
        st["completed"] = [c for c in st["completed"] if c in eff]
        changed.append("depth=%s skipped=%s" % (a.depth, st["skipped_phases"]))
    if a.input_kind is not None:
        st["input_kind"] = a.input_kind
        changed.append("input_kind=%s" % a.input_kind)
    if a.mode is not None:
        if a.mode not in state_store.RUN_MODES:
            _die("mode 取值须为 %s" % "/".join(state_store.RUN_MODES))
        st["run_mode"] = a.mode
        changed.append("run_mode=%s" % a.mode)
    if a.knowledge is not None:
        if a.knowledge == "done":
            # 知识沉淀门禁：登记前必须真实通过 verify_knowledge.py 结构校验（防口头登记）
            ok, detail = _run_knowledge_gate(st)
            if not ok:
                _die("知识总结门禁未过，拒绝登记 knowledge=done：\n%s" % detail)
            st["knowledge"] = "done"
            changed.append("knowledge=done（verify_knowledge 通过）")
        elif a.knowledge == "na":
            # 知识沉淀为 Phase 14 审核通过后的强制后置动作，不允许声明"不适用"跳过
            _die("knowledge 不支持 na：知识总结为审核通过后的强制后置动作（references/knowledge.md 31.1），"
                 "须生成 case-design-out/Knowledge_<需求标识>.md 后登记 done")
        else:
            _die("knowledge 取值仅支持 done（na 不允许：知识沉淀不可跳过）")
    if a.excel is not None:
        st["excel"] = a.excel
        changed.append("excel=%s" % a.excel)
    if not changed:
        _die("set 无任何字段变更")
    state_store.log_event(st, "set", detail=", ".join(changed))
    state_store.save(path, st)
    print("SET OK: " + ", ".join(changed))


def cmd_plan(a):
    st, path = _load_or_die(a.workdir, need=False)
    depth = (st or {}).get("depth") or "heavy"
    print("执行计划（depth=%s；阶段裁剪=%s）:" % (depth, P.DEPTH_SKIPS.get(depth, [])))
    cur = (st or {}).get("current_phase")
    for pid in P.effective_phases(depth):
        ph = P.get_phase(pid)
        mark = ""
        if st:
            if pid in st["completed"]:
                mark = "  [DONE]"
            elif pid == cur:
                mark = "  <== CURRENT (%s)" % st["status"]
        print("  Phase %-2d %-14s gate=%-7s%s" % (pid, ph["name"], ph["gate"], mark))
    if not st:
        print("（尚未 start，以上为 heavy 默认计划）")


def cmd_verify(a):
    """离线自证校验：状态文件 schema + 迁移合法性 + 产出物一致性（test_runtime.py 复用）。"""
    st, path = _load_or_die(a.workdir)
    problems = []
    eff = P.effective_phases(st.get("depth") or "heavy")
    if st["current_phase"] not in eff:
        problems.append("current_phase %d 不在有效阶段序列" % st["current_phase"])
    for c in st["completed"]:
        if c not in eff:
            problems.append("completed 含被裁剪阶段 %d" % c)
        if c > st["current_phase"]:
            problems.append("completed 含未来阶段 %d" % c)
    if st["status"] in ("WAIT_USER_CONFIRM", "WAIT_LICENSE"):
        g = P.get_phase(st["current_phase"])["gate"]
        if (st["status"] == "WAIT_USER_CONFIRM" and g != "confirm") or \
           (st["status"] == "WAIT_LICENSE" and g != "license"):
            problems.append("status 与阶段 gate 类型不符")
    if problems:
        for p_ in problems:
            print("FAIL " + p_)
        sys.exit(1)
    print("STATE VERIFY OK: phase=%d status=%s completed=%s" % (st["current_phase"], st["status"], st["completed"]))


def cmd_reset(a):
    path = state_store.default_state_path(a.workdir)
    if os.path.exists(path):
        os.remove(path)
        print("已删除运行状态: %s（产出物文件不受影响）" % path)
    else:
        print("无运行状态可删除")


def main():
    _utf8()
    ap = argparse.ArgumentParser(prog="qamaster_runtime", description="qamaster Runtime Controller（流程状态机）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _wd(sp):
        sp.add_argument("--workdir", default=os.getcwd(), help="用户工作目录（产出物与状态根），默认当前目录")

    sp = sub.add_parser("start", help="启动/恢复流程")
    sp.add_argument("--req-id", default="")
    sp.add_argument("--mode", default="full", choices=list(state_store.RUN_MODES))
    sp.add_argument("--user-input", default="", help="原始用户输入（记录审计，不解析）")
    sp.add_argument("--fresh", action="store_true", help="忽略已有状态强制重启")
    _wd(sp)
    sp.set_defaults(fn=cmd_start)

    sp = sub.add_parser("status", help="查看当前状态")
    sp.add_argument("--card", action="store_true", help="同时输出当前阶段契约卡")
    _wd(sp)
    sp.set_defaults(fn=cmd_status)

    sp = sub.add_parser("next", help="推进到下一阶段（仅当前阶段已过 gate）")
    _wd(sp)
    sp.set_defaults(fn=cmd_next)

    sp = sub.add_parser("gate", help="执行当前阶段出口门禁")
    _wd(sp)
    sp.set_defaults(fn=cmd_gate)

    sp = sub.add_parser("confirm", help="人工门：用户已确认/答复/许可")
    _wd(sp)
    sp.set_defaults(fn=cmd_confirm)

    sp = sub.add_parser("reject", help="许可门：用户拒绝（不生成 Excel）")
    _wd(sp)
    sp.set_defaults(fn=cmd_reject)

    sp = sub.add_parser("fail", help="门禁失败/审核反馈 → 回退重走")
    sp.add_argument("--to", required=True, help="回退目标阶段（阶段号或名称关键词）")
    sp.add_argument("--reason", default="")
    _wd(sp)
    sp.set_defaults(fn=cmd_fail)

    sp = sub.add_parser("set", help="登记判定结果/用户意图（req-id/depth/input-kind/mode/knowledge/excel）")
    sp.add_argument("--req-id", default=None)
    sp.add_argument("--depth", default=None)
    sp.add_argument("--input-kind", default=None, choices=list(state_store.INPUT_KINDS))
    sp.add_argument("--mode", default=None)
    sp.add_argument("--knowledge", default=None, choices=["done"])
    sp.add_argument("--excel", default=None, choices=["asked_yes", "asked_no", "generated", "declined", "na"])
    _wd(sp)
    sp.set_defaults(fn=cmd_set)

    sp = sub.add_parser("plan", help="查看执行计划（按深度裁剪后的阶段序列）")
    _wd(sp)
    sp.set_defaults(fn=cmd_plan)

    sp = sub.add_parser("verify", help="离线自证校验状态一致性")
    _wd(sp)
    sp.set_defaults(fn=cmd_verify)

    sp = sub.add_parser("reset", help="删除运行状态（不影响产出物）")
    _wd(sp)
    sp.set_defaults(fn=cmd_reset)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
