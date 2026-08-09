#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qamaster_runtime.py — qamaster Runtime Controller（通用 workflow 状态机 CLI）

设计依据：qamaster-Agent-Runtime-Engineering-Refactor-Design-v2.0.0.md
    模型负责思考，Runtime 负责控制。任何模型不可绕过。

本 CLI 是流程阶段机的唯一权威控制点：
  - 阶段迁移（next）：只允许 current+1（按流程深度裁剪后的序列），非法跳转被拒绝
  - 质量门（gate）：机器门跑确定性检查（文件存在性 + skill 自带校验脚本），
    人工门（confirm/license）在完整模式必须用户 confirm 才放行
  - 契约卡渲染：每个阶段向模型输出 CURRENT PHASE / ALLOWED / FORBIDDEN /
    PRODUCES / EXIT CONDITION，模型无法决定下一阶段

【多需求并行】状态按 (workflow, req_id) 分区：<workdir>/.qamaster/<workflow>/<req_id>/state.json
每个在途需求独立 state.json/checkpoint，单写者无并发 clobber。MANIFEST.md 是唯一共享可变资源，
由 Runtime 在 gate PASS 时经 FileLock 自动维护（cmd_manifest / _manifest_side_effect），
模型禁止 Write/Edit MANIFEST.md（铁律 4）。

【通用 workflow】控制器按 --workflow 路由取 WorkflowSpec（runtime/workflows/registry.py）。
新增 skill 只需注册自己的阶段机即可继承隔离 + 强控。

用法（cwd = 用户工作目录）：
  bootstrap --user-input "..." [--req-id X]            派生需求标识（不创状态，幂等）
  start --req-id X [--mode full|auto|light]            启动/恢复流程（req_id 必需）
  status --req-id X | --all                            查看状态
  next | gate | confirm | reject                       阶段推进/门禁
  fail --to <阶段号|名> --reason "..."                 回退重走
  set --depth ... --input-kind ... --mode ... --knowledge done --excel ...
  manifest add|update|complete|list|reconcile --req-id X   MANIFEST 维护（Runtime 独占）
  plan | verify | reset [--legacy]                     计划/自证/重置

约定：
  - 状态文件：<workdir>/.qamaster/<workflow>/<req_id>/state.json（不入库，.gitignore 含 .qamaster/）
  - 产物层：<workdir>/<spec.output_dir>/（如 case-design-out/，向后兼容）
  - MANIFEST：<workdir>/<spec.output_dir>/MANIFEST.md（Runtime 在 FileLock 下维护）
  - skill 资产通过插件根自动定位，不要求 cwd 是插件目录
  - 所有 gate 输出遵循"机器判定为准，禁止模型自证"：PASS/FAIL 由脚本退出码与确定性检查给出
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "workflows"))
import state_store  # noqa: E402
import locking  # noqa: E402
import manifest  # noqa: E402
import kb_store  # noqa: E402
from registry import get_workflow, list_workflows  # noqa: E402

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WORKFLOW = "case-design"

APPROVE_HINT = "审核通过 / 无问题 / confirm / approve"


def _utf8():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _register_workflows():
    """显式注册已知 workflow（无 import 副作用；R7 规避）。幂等。"""
    try:
        import case_design as _cd  # noqa: E402
        _cd.register()
    except Exception:
        pass


def _spec(a_or_workflow):
    """取 WorkflowSpec；未注册则 die。接受 args 对象或 workflow 字符串。"""
    wf = a_or_workflow if isinstance(a_or_workflow, str) else a_or_workflow.workflow
    spec = get_workflow(wf)
    if spec is None:
        _die("未知 workflow: %s（已注册: %s）" % (wf, ",".join(list_workflows()) or "(无)"))
    return spec


def _skill_scripts(spec):
    return os.path.join(PLUGIN_ROOT, spec.skill_dir, "scripts")


def _skill_md_abs(spec):
    return os.path.join(PLUGIN_ROOT, spec.skill_md)


def _checkpoint_path(workdir, spec, req_id, phase):
    """分区检查点路径：<workdir>/.qamaster/<workflow>/<req_id>/checkpoint_<N>.md"""
    return os.path.join(workdir, state_store.QAMASTER_ROOT, spec.name, req_id,
                        "checkpoint_%d.md" % phase)


def _manifest_path(workdir, spec):
    return os.path.join(workdir, spec.output_dir, "MANIFEST.md")


def _kb_path(workdir, spec, kind="lessons"):
    """KB 文件路径（镜像 _manifest_path）。kind=lessons -> KB_lessons.md。

    与 MANIFEST.md 同目录、同纪律：仅 Runtime 在 FileLock 下写，模型禁止 Write/Edit。
    """
    name = "KB_%s.md" % kind
    return os.path.join(workdir, spec.output_dir, name)


def _read_req_text(workdir, spec, req_id):
    """读取 case-design-out/REQ_<id>.md 正文（供 surface 命中）。失败返回 ""。"""
    if not req_id:
        return ""
    p = os.path.join(workdir, spec.output_dir, "REQ_%s.md" % req_id)
    if not os.path.isfile(p):
        return ""
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _manifest_name(st):
    """从 state 取需求名称（MANIFEST name 代理，仅溯源展示不参与聚类）。失败回退 req_id。"""
    return st.get("name") or st.get("req_id") or ""


def _load_or_die(workdir, workflow, req_id, need=True):
    """按 (workflow, req_id) 定位分区状态。lookup 前惰性迁移 legacy state（幂等、廉价）。"""
    # 惰性迁移旧 case-design-out/.runtime/state.json → 分区路径（仅 case-design 有 legacy）
    try:
        state_store.migrate_legacy_state(workdir, workflow)
    except Exception:
        pass  # 迁移失败不阻断 lookup；legacy 仍在原处，可 reset --legacy 处理
    path = state_store.default_state_path(workdir, workflow, req_id)
    st = state_store.load(path)
    if st is None and need:
        _die("未找到运行状态（workflow=%s, req_id=%s, path=%s）。"
             "请先执行: bootstrap + start --req-id <需求标识>" % (workflow, req_id or "(空)", path))
    return st, path


def _die(msg, rc=2):
    print("RUNTIME_ERROR: %s" % msg)
    sys.exit(rc)


def _require_req_id(a):
    rid = (a.req_id or "").strip()
    if not rid:
        _die("本命令需 --req-id（由 bootstrap 派生）；workflow=%s" % a.workflow)
    return rid


def _audit_degraded_artifacts(workdir, spec, st, req_id):
    """降级产物对账（v0.6.0 事故修复·C2 修正）：检测『无 Runtime 裁决却已有用例落盘』的降级执行痕迹。

    C2 修正：glob 限定为当前 req_id（TestCases_<req_id>*.md），不再命中其他需求的用例，
    避免多需求下新起需求 Y 时误报需求 X 的 TestCases。
    """
    if not req_id:
        return []
    try:
        tc_hits = sorted(glob.glob(os.path.join(workdir, spec.output_dir,
                                                "TestCases_%s*.md" % req_id)))
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
        print("  ! %s/%s" % (spec.output_dir, n))
    print("  原因: %s" % ("state.json 缺失——用例为无状态机裁决的降级执行产物" if st is None
                       else "当前阶段=Phase %s(<13)——用例先于写盘门落盘，未过机器校验" % phase))
    print("  处置（强制·先补验后信任）: 对每个文件补跑写盘门同口径校验——")
    print("    python \"%s\" \"%s/<文件>\"  （结构）" % (os.path.join(_skill_scripts(spec), "verify_md.py"), spec.output_dir))
    print("    python \"%s\" \"%s/<文件>\" \"%s/REQ_%s.md\"  （内容+覆盖硬门）"
          % (os.path.join(_skill_scripts(spec), "verify_cases.py"), spec.output_dir, spec.output_dir, req_id))
    print("  verify_cases.py 现含覆盖硬门（#4-H 需求引用率/#6-H 接口三类/RK P0-P1 风险），")
    print("  exit=1 即覆盖不达标——须补齐用例后重写，禁止以『核心用例已交付』收尾。")
    print("  降级期间该产出物的交付摘要若『脚本校验摘要』填了数值而非『未执行』，一律视为编造（SKILL.md 3.1 红线）。")
    print("!" * 64)
    print()
    return names


def _rt_cmd():
    return 'python "%s"' % os.path.abspath(__file__)


def _fmt_cmd(cmd, st, spec):
    req = st.get("req_id") or "<需求标识>"
    return (cmd.replace("{skill_scripts}", _skill_scripts(spec))
              .replace("{req_id}", req)
              .replace("{workflow}", spec.name)
              .replace("{output_dir}", spec.output_dir))


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


def _maybe_upgrade_depth_on_p0(st, phase, stdout_lines):
    """P0-1 修复·两段式规模升级：Phase 5 gate PASS 后，若风险清单含 P0/P1 风险且
    state.depth != heavy → 自动升级 depth=heavy 并补跑被裁剪阶段。

    破"P0 风险循环依赖"：第0阶段按 P0 域信号初判规模（可能判中型/轻型裁剪了 phase 3/4/10），
    第5阶段实测产出 P0/P1 风险时由 Runtime 兜底升级——两道闸（域信号初判 + 风险实测）都过才
    放行中型/轻型。VERIFY_SUMMARY 的 risk_p0p1 字段为风险实测信号（>0 即存在 P0/P1）。
    """
    if phase != 5:
        return False
    cur_depth = (st.get("depth") or "heavy")
    if cur_depth == "heavy":
        return False
    import re
    p0p1 = 0
    for ln in stdout_lines or []:
        s = ln.strip()
        if s.startswith("##VERIFY_SUMMARY##"):
            m = re.search(r"risk_p0p1=(\d+)", s)
            if m:
                p0p1 = int(m.group(1))
            break
    if p0p1 > 0:
        st["depth"] = "heavy"
        state_store.log_event(st, "depth_upgrade",
                              detail="phase5 P0/P1 风险实测 %d 条 → depth %s→heavy（补跑被裁剪阶段）"
                              % (p0p1, cur_depth))
        return True
    return False


def _prior_artifacts_block(st, phase, spec):
    """v0.7.0: 渲染契约卡的 PRIOR_ARTIFACTS 段——按当前阶段 consumes 注入上游制品 ID 范围。

    不靠模型记忆：runtime 把已沉淀阶段的实际 ID 范围（R1-R24 / RK1-RK17 等）+ 台账/REQ
    注入契约卡。模型无需读检查点文件即可知上游有哪些 ID 可引用。
    """
    consumes = phase.get("consumes", [])
    if not consumes:
        return ""
    workdir = st.get("workdir", os.getcwd())
    req_id = st.get("req_id", "")
    if not req_id:
        return ""
    out = os.path.join(workdir, spec.output_dir)
    artifacts = st.get("artifacts", {})
    lines = ["PRIOR_ARTIFACTS（本阶段必须消费的上游制品·由 Runtime 注入，勿凭记忆）:"]
    for c in consumes:
        if c == "req":
            p = os.path.join(out, ("REQ_%s.md" % req_id))
            lines.append("  需求文档: %s/%s" % (spec.output_dir, os.path.basename(p)))
        elif c == "ledger":
            p = os.path.join(out, "Clarification_Ledger_%s.md" % req_id)
            if os.path.exists(p):
                lines.append("  澄清台账: %s/%s（已解决/待确认/假设 见台账）" % (spec.output_dir, os.path.basename(p)))
        elif c.isdigit():
            art = artifacts.get(c, {})
            ids = art.get("ids", {})
            if ids:
                id_desc = " | ".join("%s=%s" % (k, v) for k, v in ids.items())
                lines.append("  Phase %s 制品: %s（已沉淀·ID 范围）" % (c, id_desc))
            else:
                # v0.8.1 Gap4: 区分"无 phase_gate 的内存阶段"与"真未完成"，消除"未沉淀"误导
                src_phase = spec.get_phase(int(c))
                has_gate = bool(src_phase and src_phase.get("gate_checks"))
                if has_gate:
                    cp = _checkpoint_path(workdir, spec, req_id, int(c))
                    mark = "（已沉淀）" if os.path.exists(cp) else "（未沉淀·前置阶段未完成？）"
                    lines.append("  Phase %s 制品: .qamaster/%s/%s/checkpoint_%s.md %s"
                                 % (c, spec.name, req_id, c, mark))
                else:
                    # 无 phase_gate 的纯内存阶段：不写检查点，靠下游 Phase 8/10/13 gate 校验追溯性 section
                    lines.append("  Phase %s 制品: （内存产物·无 phase_gate·由下游 gate 校验追溯性 section）" % c)
    lines.append("  消费约束: 关联规则列 R/RK/TP/API 须在上游清单内（悬空引用 exit=1）；用例等级须映射 RK 等级；")
    lines.append("            台账'已解决'事实须落成断言；假设A<n> 须在台账假设清单内；台账'待确认'须闭环或转假设")
    return "\n".join(lines)


def _derive_dim_trigger(req_text, reason, surfmap):
    """从 REQ 正文 + 纠正 reason 派生 (dimension, trigger_words)。

    dimension = 命中 surface 词最多的类别（无命中→"通用"）；
    trigger = 全类命中词的并集（检索用，跨需求累积）。纯 stdlib，零模型。
    """
    combined = (req_text or "") + " " + (reason or "")
    best, best_hit = "通用", 0
    trigger_union = []
    for cat, words in (surfmap or {}).items():
        hits = [w for w in words if w in combined]
        if hits:
            trigger_union += hits
        if len(hits) > best_hit:
            best, best_hit = cat, len(hits)
    return best, sorted(set(trigger_union))


def _maybe_capture_lesson(st, phase, reason, spec):
    """纠正发生时自动沉淀候选经验(draft)。纯 Runtime，零模型，静默，幂等，best-effort。

    挂载点：cmd_fail（log_event 前）/ cmd_patch（append 后）。不挂 gate_fail（无人类文本）。
    要点：①静默（除 WARN 外无 stdout，护既有 substring 断言）；②best-effort（锁超时/写失败
    跳过，纠正永远成功）；③不写 per-req history（KB 文件自带审计）；④落 draft/occ=1，
    不过信任门→预防/反应都不注入→输出与无 KB 时一致（护 150/0）。
    """
    if not (reason and reason.strip()):
        return None
    req_id = st.get("req_id", "")
    workdir = st.get("workdir", os.getcwd())
    req_text = _read_req_text(workdir, spec, req_id)
    surfmap = kb_store.get_surface_map(os.path.join(PLUGIN_ROOT, spec.skill_dir))
    dim, trigger = _derive_dim_trigger(req_text, reason, surfmap)
    rec = {
        "kind": "lesson", "phase": str(phase) if phase is not None else "",
        "dimension": dim, "error_type": "人工纠正",
        "module": _manifest_name(st), "source_req": req_id,
        "captured": kb_store._today(), "raw_text": reason.strip(),
        "status": "draft", "occurrences": 1, "trigger": trigger,
    }
    try:
        with locking.FileLock(_kb_path(workdir, spec, "lessons"), timeout=30):
            kb_store.upsert_lesson(_kb_path(workdir, spec, "lessons"), rec)
    except Exception:
        # 锁超时/写失败：绝不阻断纠正本身（best-effort）
        import traceback
        print("  [WARN] 经验沉淀失败(不阻断): %s"
              % traceback.format_exc().splitlines()[-1])
    return None


def _render_lessons_block(cands, tag, footer=""):
    """渲染经验块（人类原话 verbatim）。cands=[(score, rec), ...]，已排序截断。"""
    if not cands:
        return ""
    lines = ["##%s##（历史经验·Runtime 自动检索注入，参考而非硬约束）" % tag]
    for score, r in cands:
        phase = r.get("phase", "?")
        dim = r.get("dimension", "?")
        etype = r.get("error_type", "人工纠正")
        raw = r.get("raw_text") or "(无原文)"
        src_reqs = r.get("source_reqs") or []
        occ = r.get("occurrences", 1)
        src_desc = src_reqs[0] if src_reqs else (r.get("source_req") or "?")
        if len(src_reqs) > 1:
            src_desc = "%s 等 %d 需求" % (src_reqs[0], len(src_reqs))
        trig = r.get("trigger") or []
        trig_str = "/".join(trig[:8]) if trig else "(无)"
        lines.append("  - [Phase %s·%s·%s] %s" % (phase, dim, etype, raw))
        lines.append("    （来源 %s，命中 %d 次；触发词: %s）" % (src_desc, occ, trig_str))
    if footer:
        lines.append("  适用原则：%s" % footer)
    else:
        lines.append("  适用原则：本需求命中上述经验触发词；据此自查是否同样出错，命中则补，不命中则忽略。")
    return "\n".join(lines)


def _prior_kb_block(st, phase, spec, kind="lesson"):
    """预防式检索+注入：开工前按 REQ 相关性 + 双门注入 ##PRIOR_LESSONS##。

    双门：①相关性门（surface≥2 或 module 标题命中）②信任门（endorsed 或 occ≥3）。
    draft/occ=1 过不了信任门→不注入→与无 KB 时一致（护 150/0）。
    No-op：无 KB 文件、或无记录同时过双门 → 返回 ""。
    """
    p = _kb_path(st.get("workdir", os.getcwd()), spec, "lessons")
    if not os.path.isfile(p):
        return ""
    recs = kb_store.load_records(p)
    rtext = _read_req_text(st.get("workdir", os.getcwd()), spec, st.get("req_id", "")) or ""
    phase_id = phase.get("id") if isinstance(phase, dict) else phase
    cands = []
    for r in recs:
        if r.get("superseded_by"):
            continue
        if str(r.get("phase", "")) != str(phase_id):
            continue
        surface = sum(1 for w in r.get("trigger", []) if w in rtext)
        title_hit = bool(r.get("module")) and r["module"] in rtext
        relevant = surface >= 2 or title_hit
        if not relevant:
            continue
        trusted = (r.get("status") == "endorsed") or (r.get("occurrences", 1) >= 3)
        if not trusted:
            continue
        score = 3 * surface + 4 * (1 if title_hit else 0) + r.get("occurrences", 1) + (2 if r["status"] == "endorsed" else 0)
        cands.append((score, r))
    cands.sort(key=lambda sr: (-sr[0], -sr[1].get("occurrences", 1)))
    return _render_lessons_block(cands[:3], tag="PRIOR_LESSONS") if cands else ""


def _relevant_lessons_on_fail(st, phase, fail_context, spec):
    """反应式失败定向应用：检测到问题时按失败上下文文本 surface 命中查 KB，注入 ##RELEVANT_LESSONS##。

    比预防式更锐：用失败文本（FAIL 明细 / 人类 reason）做命中，"和这次栽的跟头最像"的经验排最前。
    不解析 check 名（规避中文标签/1200 截断）。同信任门。相关性门：失败文本命中≥1 或 REQ 命中≥2。
    No-op：无 KB / 无信任经验 / 失败文本无命中 → 返回 "" → gate_fail 输出与今天一致。
    """
    p = _kb_path(st.get("workdir", os.getcwd()), spec, "lessons")
    if not os.path.isfile(p) or not (fail_context or "").strip():
        return ""
    recs = kb_store.load_records(p)
    req_text = _read_req_text(st.get("workdir", os.getcwd()), spec, st.get("req_id", "")) or ""
    phase_id = phase.get("id") if isinstance(phase, dict) else phase
    cands = []
    for r in recs:
        if r.get("superseded_by"):
            continue
        if str(r.get("phase", "")) != str(phase_id):
            continue
        trusted = (r.get("status") == "endorsed") or (r.get("occurrences", 1) >= 3)
        if not trusted:
            continue
        hit_fail = sum(1 for w in r.get("trigger", []) if w in fail_context)
        hit_req = sum(1 for w in r.get("trigger", []) if w in req_text)
        if not (hit_fail >= 1 or hit_req >= 2):
            continue
        score = 5 * hit_fail + 3 * hit_req + r.get("occurrences", 1) + (2 if r["status"] == "endorsed" else 0)
        cands.append((score, r))
    cands.sort(key=lambda sr: (-sr[0], -sr[1].get("occurrences", 1)))
    return _render_lessons_block(
        cands[:3], tag="RELEVANT_LESSONS",
        footer="本门失败/本次纠正疑似与此历史经验相关·请据此修正，参考而非硬约束") if cands else ""


def _prior_business_kb_block(st, phase, spec):
    """预防式业务知识检索+注入：开工前（Phase 0）按 REQ 相关性 + 双门注入 ##PRIOR_BUSINESS_KB##。

    镜像 _prior_kb_block，3 处差异：path="business"（KB_business.md）、
    tag="PRIOR_BUSINESS_KB"、**不按 phase 过滤**（business 知识 phase 无关——Knowledge
    记录统一标 phase=14，但业务背景对所有阶段有意义，故全记录为候选）。
    双门同 lessons：相关性（surface≥2 或 module 标题命中）+ 信任（endorsed 或 occ≥3，
    business 起步 endorsed → 信任门恒过，靠相关性门过滤）。
    仅在 Phase 0 注入（开工前一次性业务背景，非每阶段）——调用方 _card 控制时机。
    No-op：无 KB_business.md、或无记录过双门 → 返回 "" → 卡片与无 KB 时逐字节一致。
    """
    p = _kb_path(st.get("workdir", os.getcwd()), spec, "business")
    if not os.path.isfile(p):
        return ""
    recs = kb_store.load_records(p)
    rtext = _read_req_text(st.get("workdir", os.getcwd()), spec, st.get("req_id", "")) or ""
    cands = []
    for r in recs:
        if r.get("superseded_by"):
            continue
        # business phase 无关：不按 phase 过滤
        surface = sum(1 for w in r.get("trigger", []) if w in rtext)
        title_hit = bool(r.get("module")) and r["module"] in rtext
        relevant = surface >= 2 or title_hit
        if not relevant:
            continue
        trusted = (r.get("status") == "endorsed") or (r.get("occurrences", 1) >= 3)
        if not trusted:
            continue
        score = 3 * surface + 4 * (1 if title_hit else 0) + r.get("occurrences", 1) + (2 if r["status"] == "endorsed" else 0)
        cands.append((score, r))
    cands.sort(key=lambda sr: (-sr[0], -sr[1].get("occurrences", 1)))
    return _render_lessons_block(cands[:3], tag="PRIOR_BUSINESS_KB",
                                 footer="本需求命中上述历史业务知识触发词；据此参考历史沉淀，参考而非硬约束") if cands else ""


def _relevant_business_kb_on_fail(st, phase, fail_context, spec):
    """反应式业务知识定向应用：检测到问题时按失败上下文文本 surface 命中查 business KB，
    注入 ##RELEVANT_BUSINESS_KB##。

    镜像 _relevant_lessons_on_fail，3 处差异：path="business"、tag="RELEVANT_BUSINESS_KB"、
    **不按 phase 过滤**。信任门同（business endorsed 恒过）。相关性门：hit_fail≥1 或 hit_req≥2。
    在 gate_fail/fail/patch 任意阶段触发——失败定向递送相关历史业务知识。
    No-op：无 KB_business / 无信任经验 / 失败文本无命中 → 返回 ""。
    """
    p = _kb_path(st.get("workdir", os.getcwd()), spec, "business")
    if not os.path.isfile(p) or not (fail_context or "").strip():
        return ""
    recs = kb_store.load_records(p)
    req_text = _read_req_text(st.get("workdir", os.getcwd()), spec, st.get("req_id", "")) or ""
    cands = []
    for r in recs:
        if r.get("superseded_by"):
            continue
        # business phase 无关：不按 phase 过滤
        trusted = (r.get("status") == "endorsed") or (r.get("occurrences", 1) >= 3)
        if not trusted:
            continue
        hit_fail = sum(1 for w in r.get("trigger", []) if w in fail_context)
        hit_req = sum(1 for w in r.get("trigger", []) if w in req_text)
        if not (hit_fail >= 1 or hit_req >= 2):
            continue
        score = 5 * hit_fail + 3 * hit_req + r.get("occurrences", 1) + (2 if r["status"] == "endorsed" else 0)
        cands.append((score, r))
    cands.sort(key=lambda sr: (-sr[0], -sr[1].get("occurrences", 1)))
    return _render_lessons_block(cands[:3], tag="RELEVANT_BUSINESS_KB",
                                 footer="本门失败/本次纠正疑似与此历史业务知识相关·请据此参考，参考而非硬约束") if cands else ""


def _run_check(chk, st, spec):
    """执行单条确定性检查，返回 (ok, detail)。"""
    workdir = st["workdir"]
    req_id = st.get("req_id", "")
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
        # v0.7.1: 空 req_id 防护——不构造字面量 REQ_<需求标识>.md，显式报错阻断
        # C4: 新流程下 req_id 恒非空（来自 bootstrap），此分支保留为防御性兜底
        if not req_id:
            return (False, "%s: req_id 未设置（state.json req_id 为空——不应发生，bootstrap 应已派生）。"
                    "请先执行 bootstrap + start --req-id。" % chk["label"])
        cp = _checkpoint_path(workdir, spec, req_id, phase)
        req_path = os.path.join(workdir, spec.output_dir, "REQ_%s.md" % req_id)
        if not os.path.exists(req_path):
            return (False, "%s: REQ 文件不存在 %s。按 phase0_manifest.md 步骤零落盘 REQ_%s.md 后重试。"
                    % (chk["label"], req_path, req_id))
        ledger_path = os.path.join(workdir, spec.output_dir, "Clarification_Ledger_%s.md" % req_id)
        # v0.9.0·根因2/6 修复：DESIGN 落盘时必须传 --design
        design_path = os.path.join(workdir, spec.output_dir, "DESIGN_%s.md" % req_id)
        # REQ 为必需输入（phase_gate 校验 #4/#5 依赖它）；ledger/design 可选（不存在不阻断）
        parts = ['python "%s" --phase-gate %d "%s" --req "%s"'
                 % (os.path.join(_skill_scripts(spec), "verify_cases.py"), phase, cp, req_path)]
        if os.path.exists(ledger_path):
            parts.append('--ledger "%s"' % ledger_path)
        if os.path.exists(design_path):
            parts.append('--design "%s"' % design_path)
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
        if proc.returncode != 0:
            fail_lines = [ln for ln in all_lines
                          if ln.strip().startswith("[FAIL]") or ln.lstrip().startswith("- ")]
            summary = [ln for ln in all_lines if ln.startswith("##VERIFY_SUMMARY##")]
            if fail_lines:
                detail += "\n----- phase-gate FAIL 明细 -----\n" + "\n".join(fail_lines[:200])
            elif all_lines:
                detail += "\n----- 输出(尾部) -----\n" + "\n".join(all_lines[-60:])
            if summary:
                detail += "\n" + summary[-1][:1200]
        # v0.7.0: gate PASS 时回填 artifacts + 重置 gate_rounds
        if proc.returncode == 0:
            _backfill_artifacts(st, phase, cp, stdout_lines=all_lines)
            st["gate_rounds"][str(phase)] = 0
            # P0-1 修复：Phase 5 gate PASS 后按 P0/P1 风险实测升级 depth→heavy
            if _maybe_upgrade_depth_on_p0(st, phase, all_lines):
                detail += " | depth→heavy（Phase5 P0/P1 风险实测触发两段式升级）"
        return (proc.returncode == 0, detail)
    if kind == "script":
        cmd = _fmt_cmd(chk["cmd"], st, spec)
        try:
            proc = subprocess.run(cmd, shell=True, cwd=workdir, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=600)
        except Exception as e:
            return (False, "%s: 执行异常 %s" % (chk["label"], e))
        all_lines = (proc.stdout or "").strip().splitlines()
        tail = all_lines[-40:] if len(all_lines) > 40 else all_lines
        detail = "%s: exit=%d" % (chk["label"], proc.returncode)
        if proc.returncode != 0:
            if tail:
                detail += "\n----- 脚本输出(尾部) -----\n" + "\n".join(tail)
            fail_lines = [ln for ln in all_lines if ln.strip().startswith("[FAIL]")]
            missing_fails = [ln for ln in fail_lines if not any(ln in t for t in tail)]
            if missing_fails:
                detail += "\n----- 硬门 FAIL 明细(补捞) -----\n" + "\n".join(missing_fails[:60])
        else:
            keep = [ln for ln in all_lines if ln.startswith("##VERIFY_SUMMARY##") or "结论" in ln or "硬门" in ln]
            if keep:
                detail += " | " + " ; ".join(keep)[:300]
        return (proc.returncode == 0, detail)
    return (False, "未知检查类型: %s" % kind)


def _card(st, phase, spec, extra="", correction_context=None):
    """渲染阶段契约卡（发送给模型的唯一控制协议）。

    correction_context: 非空时（cmd_fail/cmd_patch 传入人类 reason）追加反应式
    ##RELEVANT_LESSONS## 块——失败定向经验。无 KB/无信任经验/无命中 → no-op。
    """
    eff = spec.effective_phases(st.get("depth") or "heavy")
    idx = eff.index(phase["id"]) + 1 if phase["id"] in eff else 0
    total = len(eff)
    mode_cn = {"full": "完整", "auto": "连跑", "light": "轻量"}.get(st.get("run_mode"), st.get("run_mode"))
    depth_cn = {"heavy": "重型", "medium": "中型", "light": "light"}.get(st.get("depth") or "heavy")
    lines = []
    lines.append("=" * 64)
    lines.append("【RUNTIME CONTRACT — 由 qamaster Runtime 颁发，模型必须遵守，不得自改流程】")
    lines.append("=" * 64)
    lines.append("CURRENT PHASE: Phase %d — %s （流程进度 %d/%d）" % (phase["id"], phase["name"], idx, total))
    # C4: req_id 恒非空（来自 bootstrap）；空则报错而非 fallback 文案
    req_id = st.get("req_id") or ""
    if not req_id:
        _die("state.req_id 为空——不应发生（bootstrap 应已派生）。请重新 bootstrap + start --req-id。")
    lines.append("需求标识: %s | 运行模式: %s | 流程深度: %s | 输入形态: %s" % (
        req_id, mode_cn, depth_cn,
        "契约驱动" if st.get("input_kind") == "contract" else "纯需求"))
    lines.append("本阶段规范: %s（全局核心）+ 下方细则参考（阶段唯一细则来源，进入本阶段前先读）" % spec.skill_md)
    for r in phase.get("refs", []):
        lines.append("细则参考: %s" % os.path.join(spec.skill_dir, r))
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
        lines.append("  %s gate --workflow %s --req-id %s" % (_rt_cmd(), spec.name, req_id))
        lines.append("  - PASS → 再执行 `next` 进入下一阶段；FAIL → 按修复指令原地修复后重跑 gate（禁止自行跳阶段）")
    elif gate == "confirm":
        lines.append("GATE 类型: 人工确认门。向用户输出本阶段确认请求后【停止等待】；")
        lines.append("  收到用户答复后执行: %s gate --workflow %s --req-id %s（查看放行判定）" % (_rt_cmd(), spec.name, req_id))
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
    lines.append("  4. 产出物全部写入 <工作目录>/%s/ 下；写盘约束见 output_write.md（单文件一次 Write，禁止 Edit 增量）" % spec.output_dir)
    lines.append("  5. MANIFEST.md 由 Runtime 在 gate PASS 时自动维护（add/update/complete），模型禁止 Write/Edit MANIFEST.md")
    # v0.8.1: Phase 8/10 检查点含 15 列用例表时，check_fields 逐行校验枚举契约
    if phase["id"] in (8, 10) and phase.get("gate_checks"):
        lines.append("")
        lines.append("字段硬约束（check_fields 逐行校验，违约即 exit=1；枚举以 config/validation_rules.json 为准）:")
        lines.append("  测试类型∈{兼容性,功能,可靠性,契约,安全,幂等,并发,异常,权限,状态迁移,边界,集成}（无\"测试\"后缀）")
        lines.append("  测试维度∈{兼容性验证,安全验证,幂等验证,并发验证,接口验证,数据验证,权限验证,状态验证,输入验证,边界验证,集成验证,风险验证,界面验证}（无\"场景/异常\"后缀）")
        lines.append("  用例名称=4段【模块】【功能】【场景】【预期】（name_segments=4）")
        lines.append("  固定列: 编辑模式=STEP 标签=AI 责任人=AI 用例状态=Completed")
        lines.append("  用例等级∈{P0,P1,P2,P3}；用例ID=<需求标识>_<功能缩写>_<序号>（全局唯一、连续不跳号）")
        lines.append("  追溯性 section 须内联 R/RK/TP 实体内容（非\"见 Phase N\"指针），否则 D1悬空引用/D2跳号/coverage 静默失效")
    # workflow 专属卡片片段（Phase 8/10 等）经 spec.extra_card_text 钩子注入，通用路径不硬编码
    if spec.extra_card_text:
        ect = spec.extra_card_text(phase["id"], st)
        if ect:
            lines.append(ect)
    # v0.7.0: 注入 PRIOR_ARTIFACTS（按当前阶段 consumes）
    prior = _prior_artifacts_block(st, phase, spec)
    if prior:
        lines.append("")
        lines.append(prior)
    # G-FB1 修复：注入 PATCH_FEEDBACK（增量反哺指令，不回退阶段，模型就地修正前置产物切片）
    directives = st.get("patch_directives") or []
    if directives:
        lines.append("")
        lines.append("##PATCH_FEEDBACK##（后续阶段对前置产物的修正意见·就地修正，不回退重跑）")
        for d in directives:
            lines.append("  - [→ Phase %d %s] %s" % (d.get("target_phase"), d.get("target_name", ""), d.get("reason", "")))
        lines.append("  修复要求：在当前阶段产物中就地修正上述前置产物切片（如补漏标的风险/规则/测试点），")
        lines.append("  并在重写本阶段产物时把修正同步进来；修正完成后执行 `patch --clear` 清除指令。")
        lines.append("  与 fail --to 区别：patch 不回退 current_phase，避免整阶段重跑；仅当前阶段产物会重写。")
    # v0.9.0: 预防式注入 ##PRIOR_LESSONS##（开工前提醒"这类坑以前栽过"）
    # 双门（相关+信任）不过 → _prior_kb_block 返回 "" → 卡片与无 KB 时逐字节一致（护 150/0）
    les = _prior_kb_block(st, phase, spec, kind="lesson")
    if les:
        lines.append("")
        lines.append(les)
    # v0.11.0: 预防式注入 ##PRIOR_BUSINESS_KB##（仅 Phase 0 开工前业务背景，phase 无关）
    # No-op：无 KB_business.md / 无记录过双门 → 返回 "" → 卡片与无 KB 时逐字节一致
    if str(phase.get("id")) == "0":
        bus = _prior_business_kb_block(st, phase, spec)
        if bus:
            lines.append("")
            lines.append(bus)
    # v0.9.0: 反应式注入 ##RELEVANT_LESSONS##（cmd_fail/cmd_patch 经 correction_context 传入 reason）
    # 失败定向：用人类 reason 做 surface 命中，"和这次栽的跟头最像"的经验排最前。同双门，不过 → no-op
    if correction_context:
        rel = _relevant_lessons_on_fail(st, phase, correction_context, spec)
        if rel:
            lines.append("")
            lines.append(rel)
        # v0.11.0: 反应式注入 ##RELEVANT_BUSINESS_KB##（失败定向业务知识，phase 无关）
        relb = _relevant_business_kb_on_fail(st, phase, correction_context, spec)
        if relb:
            lines.append("")
            lines.append(relb)
    if extra:
        lines.append("")
        lines.append(extra)
    return "\n".join(lines)


def _resume_hint(st, spec):
    phase = spec.get_phase(st["current_phase"])
    if phase is None:
        return "状态: 当前阶段 %d 未定义" % st["current_phase"]
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
        return "状态: DONE（流程已完成）。如需修改，用 `start --fresh` 重启（Runtime 会定位已有产出物）。"
    if st["status"] == "GATE_PASSED":
        return "状态: GATE_PASSED（当前阶段门禁已通过）\n处理: 执行 `next` 进入下一阶段"
    return "状态: RUNNING（阶段产物尚未过出口门禁）"


# ---------------------------------------------------------------- MANIFEST 副作用

def _manifest_side_effect(st, phase, spec, workdir):
    """gate PASS 时 Runtime 在 FileLock 下更新 MANIFEST（best-effort，不阻断 gate）。

    Phase 0 PASS → manifest add（从 REQ_<id>.md 首个 # 标题抽需求名称）
    Phase 1 PASS → manifest update（台账文件列）
    Phase 13 PASS → manifest update（TestCases_<id>*.md 实际落盘文件列）
    Phase 14 confirm → manifest complete（置已完成）

    失败不阻断 gate（MANIFEST 是 best-effort 索引；失步可 `manifest reconcile` 重建——C6 兜底）。
    """
    pid = phase["id"]
    req_id = (st.get("req_id") or "").strip()
    if not req_id or pid not in (0, 1, 13, 14):
        return
    mp = _manifest_path(workdir, spec)
    try:
        with locking.FileLock(mp, timeout=30):  # P2 修复：锁超时统一为 30s（与 cmd_manifest/reconcile 一致，旧 10s 在并发多需求下偏短）
            if pid == 0:
                manifest.add(mp, req_id, workdir=workdir, output_dir=spec.output_dir)
            elif pid == 1:
                ledger = "Clarification_Ledger_%s.md" % req_id
                manifest.update(mp, req_id, ledger_file=ledger)
            elif pid == 13:
                tcs = sorted(glob.glob(os.path.join(workdir, spec.output_dir,
                                                    "TestCases_%s*.md" % req_id)))
                if tcs:
                    files = ",".join(os.path.basename(t) for t in tcs)
                    manifest.update(mp, req_id, testcase_files=files)
            elif pid == 14:
                manifest.complete(mp, req_id)
                # G-2 修复：Phase 14 完成后清理中间检查点（checkpoint_N.md），
                # 终态产物 TestCases_<id>.md 已含全部追溯性 section，检查点冗余。
                # 保留 state.json 作为完成记录；失败不阻断（审计可重建）。
                try:
                    cp_dir = os.path.dirname(_checkpoint_path(workdir, spec, req_id, 0))
                    removed = 0
                    for f in glob.glob(os.path.join(cp_dir, "checkpoint_*.md")):
                        os.remove(f)
                        removed += 1
                    if removed:
                        print("  [INFO] 已清理 %d 个中间检查点（Phase 14 完成；终态产物 TestCases_%s*.md 已含全部内容）"
                              % (removed, req_id))
                except Exception as ce:
                    print("  [WARN] 检查点清理失败（不阻断完成；可手动删除 .qamaster/%s/%s/checkpoint_*.md）: %s"
                          % (spec.name, req_id, ce))
    except Exception as e:
        print("  [WARN] MANIFEST 副作用失败（不阻断 gate；可执行 `manifest reconcile --req-id %s` 修复）: %s"
              % (req_id, e))


# ---------------------------------------------------------------- bootstrap

_ID_KEEP = set("-")


def _clean_id(s):
    """清洗需求标识：保留中文/英文/数字/连字符，其余替换为 -。"""
    import re
    s = (s or "").strip()
    s = re.sub(r"<<<[^>]*>>>", "", s)          # 去 <<<需求文档开始>>> 等标记
    s = re.sub(r"^[#>\s]+", "", s)              # 去 markdown 标题/引用前缀
    out = []
    for ch in s:
        if "一" <= ch <= "龥" or ch.isalnum() or ch == "-":
            out.append(ch)
        else:
            out.append("-")
    s = "".join(out)
    s = re.sub(r"-+", "-", s).strip("-")
    if len(s) > 30:
        # 截到 30 字符内（中文按字符计），再清尾部连字符
        s = s[:30].rstrip("-")
    return s


def _derive_from_file(path):
    """从 .md/.txt 文件首个 # 标题派生 id；二进制文件用文件名 stem。"""
    ext = os.path.splitext(path)[1].lower()
    stem = os.path.splitext(os.path.basename(path))[0]
    if ext in (".md", ".txt", ""):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for ln in f:
                    s = ln.strip()
                    if s.startswith("# "):
                        cand = _clean_id(s[2:])
                        if cand:
                            return cand
                    elif s.startswith("## "):
                        cand = _clean_id(s[3:])
                        if cand:
                            return cand
        except OSError:
            pass
        # 文件无标题 → 用文件名 stem
    return _clean_id(stem) or _clean_id(os.path.basename(path))


def _derive_from_text(text):
    """从内联文本首个 # 标题派生 id；无标题取首个非空行。"""
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("# "):
            cand = _clean_id(s[2:])
            if cand:
                return cand
        if s.startswith("## "):
            cand = _clean_id(s[3:])
            if cand:
                return cand
    # 取首个非空、非标记行
    for ln in (text or "").splitlines():
        s = ln.strip()
        if s and not s.startswith("<<<") and not s.startswith("#"):
            cand = _clean_id(s)
            if cand:
                return cand
    return ""


def _derive_req_id(a, spec, workdir):
    """派生需求标识。优先级：--req-id > 文件路径 > 内联文本。"""
    if a.req_id:
        return a.req_id.strip()
    ui = (a.user_input or "").strip()
    if not ui:
        return ""
    # 去除外层引号
    if len(ui) >= 2 and ui[0] in "\"'" and ui[-1] == ui[0]:
        ui = ui[1:-1].strip()
    if os.path.isfile(ui):
        return _derive_from_file(ui)
    return _derive_from_text(ui)


def cmd_bootstrap(a):
    """派生 req_id 但不创建状态（幂等）。已有进行中则输出 RESUME。"""
    spec = _spec(a)
    workdir = a.workdir
    # 惰性迁移 legacy
    state_store.migrate_legacy_state(workdir, spec.name)
    req_id = _derive_req_id(a, spec, workdir)
    if not req_id:
        _die("bootstrap 无法从输入派生需求标识。请显式传 --req-id <需求标识>。")
    # 碰撞检查：in-flight 状态 → RESUME
    active = state_store.list_active_reqs(workdir, spec.name)
    if req_id in active:
        st_path = state_store.default_state_path(workdir, spec.name, req_id)
        st = state_store.load(st_path)
        ph = spec.get_phase(st["current_phase"]) if st else None
        print("BOOTSTRAP RESUME req_id=%s phase=%s status=%s"
              % (req_id, st.get("current_phase") if st else "?", st.get("status") if st else "?"))
        print("  （检测到进行中状态，start 将走 resume 分支，不重建状态）")
        return
    # 碰撞检查：manifest 已有（完成/归档）→ 追加日期
    mp = _manifest_path(workdir, spec)
    existing_rows = manifest.load_rows(mp)
    if any(r["req_id"] == req_id for r in existing_rows):
        cand = "%s-%s" % (req_id, time.strftime("%Y%m%d"))
        print("BOOTSTRAP NOTE req_id=%s 与已归档需求同名，改用 %s" % (req_id, cand), file=sys.stderr)
        req_id = cand
    print("BOOTSTRAP OK req_id=%s" % req_id)


# ---------------------------------------------------------------- commands

def cmd_start(a):
    spec = _spec(a)
    workdir = a.workdir
    req_id = (a.req_id or "").strip()
    if not req_id:
        _die("start 需 --req-id <需求标识>（由 bootstrap 派生）。流程：bootstrap → start --req-id。")
    # 惰性迁移 legacy（_load_or_die 也迁，但 start 需先迁移再判断 resume）
    state_store.migrate_legacy_state(workdir, spec.name)
    path = state_store.default_state_path(workdir, spec.name, req_id)
    try:
        existing = state_store.load(path)
    except state_store.StateCorruptError as e:
        _die(str(e) + "。请先人工检查/备份后删除该文件再 start")
    if existing and not a.fresh:
        _audit_degraded_artifacts(workdir, spec, existing, req_id)
        phase = spec.get_phase(existing["current_phase"])
        print("检测到进行中的流程（断点续跑，禁止重新生成覆盖已落盘产物）:")
        print("  workflow=%s req_id=%s phase=%d(%s) status=%s" % (
            spec.name, req_id, phase["id"], phase["name"], existing["status"]))
        print(_resume_hint(existing, spec))
        print()
        print(_card(existing, phase, spec))
        return
    _audit_degraded_artifacts(workdir, spec, None, req_id)
    st = state_store.new_state(spec.name, req_id, workdir)
    if a.mode:
        st["run_mode"] = a.mode
    state_store.log_event(st, "start", detail="mode=%s workflow=%s req_id=%s" % (st["run_mode"], spec.name, req_id))
    state_store.save(path, st)
    phase = spec.get_phase(0)
    print("Runtime 已启动（workflow=%s, req_id=%s, mode=%s）。" % (spec.name, req_id, st["run_mode"]))
    print("全局业务规范（避坑红线/输入协议/运行模式细则，一次性阅读）: %s" % _skill_md_abs(spec))
    print("其后每个阶段只读 Runtime 颁发的契约卡与对应 references 细则，按契约执行。")
    print()
    print(_card(st, phase, spec))


def cmd_status(a):
    spec = _spec(a)
    if a.all:
        reqs = state_store.list_active_reqs(a.workdir, spec.name)
        if not reqs:
            print("无进行中的需求（workflow=%s, workdir=%s）" % (spec.name, a.workdir))
            return
        out = []
        for rid in reqs:
            p = state_store.default_state_path(a.workdir, spec.name, rid)
            st = state_store.load(p)
            if not st:
                continue
            ph = spec.get_phase(st["current_phase"])
            out.append({"req_id": rid, "current_phase": st["current_phase"],
                        "phase_name": ph["name"] if ph else "?", "status": st["status"],
                        "run_mode": st.get("run_mode"), "depth": st.get("depth"),
                        "updated_at": st["updated_at"]})
        print(json.dumps({"workflow": spec.name, "reqs": out}, ensure_ascii=False, indent=2))
        return
    req_id = _require_req_id(a)
    st, _ = _load_or_die(a.workdir, a.workflow, req_id)
    phase = spec.get_phase(st["current_phase"])
    print(json.dumps({
        "workflow": st["workflow"], "req_id": st.get("req_id"),
        "current_phase": st["current_phase"], "phase_name": phase["name"] if phase else "?",
        "completed": st["completed"], "status": st["status"],
        "run_mode": st["run_mode"], "depth": st.get("depth"),
        "input_kind": st.get("input_kind"), "skipped_phases": st.get("skipped_phases"),
        "excel": st.get("excel"), "knowledge": st.get("knowledge"),
        "updated_at": st["updated_at"],
    }, ensure_ascii=False, indent=2))
    print()
    print(_resume_hint(st, spec))
    if a.card:
        print()
        print(_card(st, phase, spec))


def cmd_next(a):
    spec = _spec(a)
    req_id = _require_req_id(a)
    st, path = _load_or_die(a.workdir, a.workflow, req_id)
    if st["status"] in ("WAIT_USER_CONFIRM", "WAIT_LICENSE"):
        _die("当前处于 %s，必须先过人工门禁（gate/confirm/reject）才能推进" % st["status"])
    if st["status"] == "RUNNING":
        _die("当前阶段(Phase %d)尚未通过出口门禁，先执行 `gate`" % st["current_phase"])
    if st["status"] == "DONE":
        _die("流程已完成（DONE），无下一阶段；如需修改用 `fail --to <阶段>` 回退或 `start --fresh` 重启")
    # status ∈ {GATE_PASSED, REVIEW_PENDING} → 允许推进
    nxt = spec.next_phase_id(st["current_phase"], st.get("depth") or "heavy")
    if nxt is None:
        _die("已是最后阶段")
    # Phase 14 → 15 前：知识沉淀后置动作必须已登记
    if st["current_phase"] == 14 and nxt == 15 and st.get("knowledge") != "done":
        _die("知识沉淀未完成（knowledge!=done）：审核通过后须先生成 %s/Knowledge_%s.md "
             "并执行 `set --knowledge done`（会跑 verify_knowledge.py 结构校验），再 `next` 进 Excel 许可门。"
             "知识总结为强制后置动作，不可跳过（references/knowledge.md 31.1）" % (spec.output_dir, req_id))
    prev = st["current_phase"]
    if prev not in st["completed"]:
        st["completed"].append(prev)
        st["completed"].sort()
    st["current_phase"] = nxt
    st["status"] = "RUNNING"
    st["confirm_rounds"] = 0
    state_store.log_event(st, "advance", phase=nxt, detail="from=%d" % prev)
    state_store.save(path, st)
    print(_card(st, spec.get_phase(nxt), spec))


def cmd_gate(a):
    spec = _spec(a)
    req_id = _require_req_id(a)
    st, path = _load_or_die(a.workdir, a.workflow, req_id)
    phase = spec.get_phase(st["current_phase"])
    gkind = phase["gate"]

    # --- 人工门：由运行模式与用户意图决定放行/等待
    if gkind in ("confirm", "license"):
        decision = _human_gate_decision(st, phase, spec)
        print("GATE: Phase %d (%s) — %s" % (phase["id"], phase["name"], decision["label"]))
        for ln in decision["lines"]:
            print("  " + ln)
        if decision["pass"]:
            if gkind == "license" and phase["id"] == spec.last_phase:
                # 许可门自动放行（连跑/轻量且用户已声明要 Excel）：直接执行生成门禁
                print("已声明要 Excel，自动放行 → 执行生成门禁...")
                ok_all = True
                for chk in phase.get("gate_checks", []):
                    ok, detail = _run_check(chk, st, spec)
                    print(("  [PASS] " if ok else "  [FAIL] ") + detail)
                    ok_all = ok_all and ok
                if ok_all:
                    if spec.last_phase not in st["completed"]:
                        st["completed"].append(spec.last_phase)
                    st["status"] = "DONE"
                    st["excel"] = "generated"
                    state_store.log_event(st, "gate_pass", phase=spec.last_phase, detail="via=declared_auto")
                    state_store.save(path, st)
                    print("\nGATE RESULT: PASS — Excel 已生成并通过校验，流程 DONE")
                else:
                    st["failed_gates"][str(spec.last_phase)] = {"at": state_store._now()}
                    state_store.log_event(st, "excel_fail")
                    state_store.save(path, st)
                    print("\nGATE RESULT: FAIL — Excel 生成/校验未过，按 references/excel.md 生成失败处理")
                return
            st["status"] = "GATE_PASSED"
            state_store.log_event(st, "human_gate_release", phase=phase["id"], detail=decision["via"] or "")
            state_store.save(path, st)
            # gate-PASS 副作用（Phase 14 auto-release 时 manifest complete）
            _manifest_side_effect(st, phase, spec, a.workdir)
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
        ok, detail = _run_check(chk, st, spec)
        results.append((ok, detail))
        # optional 检查（如设计文档存在性）FAIL 不阻断——仅提示，不进入 ok_all
        if not chk.get("optional"):
            ok_all = ok_all and ok
    print("GATE: Phase %d (%s) — 自动门" % (phase["id"], phase["name"]))
    for ok, detail in results:
        print(("  [PASS] " if ok else "  [FAIL] ") + detail)
    if not results:
        print("  （本阶段无机器检查项，产物为内存产物/已由模型按契约完成；Runtime 记录通过）")
    if ok_all:
        st["status"] = "GATE_PASSED"
        if str(phase["id"]) in st.get("gate_rounds", {}):
            st["gate_rounds"][str(phase["id"])] = 0
        state_store.log_event(st, "gate_pass", phase=phase["id"], detail="via=auto")
        state_store.save(path, st)
        # gate-PASS 副作用（Phase 0 add / Phase 13 update testcase files）
        _manifest_side_effect(st, phase, spec, a.workdir)
        print("\nGATE RESULT: PASS → 执行 `next` 查看下一阶段契约卡")
    else:
        st.setdefault("gate_rounds", {})
        rounds = st["gate_rounds"].get(str(phase["id"]), 0) + 1
        st["gate_rounds"][str(phase["id"])] = rounds
        st["failed_gates"][str(phase["id"])] = {"at": state_store._now(), "rounds": rounds}
        fail_detail = "; ".join(d for ok, d in results if not ok)
        state_store.log_event(st, "gate_fail", detail=fail_detail)
        state_store.save(path, st)
        print("\nGATE RESULT: FAIL — 禁止进入下一阶段。请按上方 [FAIL] 项原地修复后重跑 `gate`。")
        # v0.9.0: 反应式失败定向应用——用 fail_detail 文本查 KB，递送对症经验供模型修正
        # 不解析 check 名（规避中文标签/1200 截断）；无 KB/无信任经验/无命中 → no-op（护 150/0）
        rel = _relevant_lessons_on_fail(st, phase, fail_detail, spec)
        if rel:
            print("")
            print(rel)
        # v0.11.0: 反应式业务知识定向——失败上下文查 business KB（phase 无关）
        # No-op：无 KB_business / 无信任经验 / 无命中 → 不打印
        relb = _relevant_business_kb_on_fail(st, phase, fail_detail, spec)
        if relb:
            print("")
            print(relb)
        if rounds >= 3:
            print("【有界返修·v0.7.0】Phase %d 门禁连续失败 %d 次，疑似系统性问题：" % (phase["id"], rounds))
            print("  请人工介入审查 [FAIL] 项，或执行 `fail --to <更早阶段> --reason \"...\"` 回退重走。")
        else:
            print("禁止以任何理由绕过本门禁交付（含『脚本暂未运行/先交付后补验/核心用例先行』）——")
            print("脚本不可运行时按降级协议暂停等待（SKILL.md Runtime 控制协议·降级），不得产出用例文件。")


def _human_gate_decision(st, phase, spec):
    """人工门放行判定（模型无关：只看运行模式 + 用户意图标记，不信模型自证）。"""
    mode = st["run_mode"]
    lines = []
    if phase["id"] == 1:
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
        state_store.log_event(st, "auto_release", detail="review gate auto-passed (%s mode), pending human review" % mode)
        lines.append("%s模式：标注「待人工审核」自动放行（审计痕迹：review_pending=true；交付报告须声明本轮未人工审核）" %
                     ("连跑" if mode == "auto" else "轻量"))
        return {"pass": True, "label": "人工确认门(审核)", "lines": lines, "via": "auto_release"}
    if phase["id"] == 15 or phase["id"] == spec.last_phase:
        if mode in ("auto", "light") and st.get("excel") == "asked_yes":
            lines.append("用户已声明要 Excel：自动放行生成")
            return {"pass": True, "label": "许可门(Excel)", "lines": lines, "via": "declared"}
        lines.append("默认需用户许可：询问「是否生成 Excel？」后停止等待；同意→`confirm`，拒绝→`reject`")
        return {"pass": False, "label": "许可门(Excel)", "lines": lines, "via": None}
    return {"pass": False, "label": "人工门", "lines": ["WAIT"], "via": None}


def cmd_confirm(a):
    """用户在人工门给出肯定答复（审核通过/同意Excel/澄清已答复）。"""
    spec = _spec(a)
    req_id = _require_req_id(a)
    st, path = _load_or_die(a.workdir, a.workflow, req_id)
    phase = spec.get_phase(st["current_phase"])
    if phase["gate"] not in ("confirm", "license"):
        _die("当前阶段(Phase %d)不是人工门，confirm 无效；请执行 `gate`" % phase["id"])

    if phase["id"] == 14:
        # 审核通过 → 标记门禁已过 → 知识沉淀后置动作指引 → next 进 Excel 许可门
        st["status"] = "GATE_PASSED"
        state_store.log_event(st, "review_approved")
        state_store.save(path, st)
        # gate-PASS 副作用：manifest complete
        _manifest_side_effect(st, phase, spec, a.workdir)
        extra = (
            "审核已通过。按顺序执行后置动作（review_gate.md/knowledge.md/phase0_manifest.md 时机四）：\n"
            "  1) MANIFEST 已由 Runtime 在本次 confirm 时自动置已完成（模型禁止 Write/Edit MANIFEST.md）\n"
            "  2) 生成/更新知识总结 %s/Knowledge_%s.md（13维度，project_cases.py 投影读用例）\n"
            "  3) 执行: %s set --knowledge done（此时会跑 verify_knowledge.py 结构校验，不过则拒绝登记）\n"
            "  4) 执行: %s next（进入 Excel 许可门）\n"
            "若知识总结已生成，直接执行第 3/4 步。" % (spec.output_dir, req_id, _rt_cmd(), _rt_cmd())
        )
        print("CONFIRM ACCEPTED: Phase 14 审核通过")
        print()
        print(extra)
        return

    if phase["id"] == 15 or phase["id"] == spec.last_phase:
        # 用户同意 Excel → 跑生成门禁（gen_excel.py）
        print("用户已许可生成 Excel，执行生成门禁...")
        ok_all = True
        for chk in phase.get("gate_checks", []):
            ok, detail = _run_check(chk, st, spec)
            print(("  [PASS] " if ok else "  [FAIL] ") + detail)
            ok_all = ok_all and ok
        if ok_all:
            if spec.last_phase not in st["completed"]:
                st["completed"].append(spec.last_phase)
            st["status"] = "DONE"
            st["excel"] = "generated"
            state_store.log_event(st, "gate_pass", phase=spec.last_phase, detail="via=user_license")
            state_store.save(path, st)
            print("\n流程 DONE：Excel 已生成并通过校验。执行临时文件清理复核后输出交付摘要。")
        else:
            st["failed_gates"][str(spec.last_phase)] = {"at": state_store._now()}
            state_store.log_event(st, "excel_fail")
            state_store.save(path, st)
            print("\nEXCEL GATE: FAIL — 按 references/excel.md 生成失败处理：显式输出失败报告，禁止口头声明已生成。")
        return

    # 澄清门 confirm：用户已答复（答复应由模型先落盘台账）
    st["status"] = "GATE_PASSED"
    state_store.log_event(st, "gate_pass", phase=phase["id"], detail="via=user_confirm")
    state_store.save(path, st)
    # gate-PASS 副作用：manifest update ledger
    _manifest_side_effect(st, phase, spec, a.workdir)
    print("CONFIRM ACCEPTED: Phase %d (%s) 人工门禁通过 → 执行 `next`" % (phase["id"], phase["name"]))


def cmd_reject(a):
    """用户在许可门拒绝（不生成 Excel）→ 流程完成。"""
    spec = _spec(a)
    req_id = _require_req_id(a)
    st, path = _load_or_die(a.workdir, a.workflow, req_id)
    phase = spec.get_phase(st["current_phase"])
    if phase["gate"] != "license":
        _die("当前阶段不是许可门，reject 无效")
    st["excel"] = "declined"
    st["status"] = "DONE"
    if spec.last_phase not in st["completed"]:
        st["completed"].append(spec.last_phase)
    state_store.log_event(st, "license_rejected", detail="user declined excel")
    state_store.save(path, st)
    print("已记录：用户不生成 Excel。流程 DONE。执行临时文件清理复核后输出交付摘要。")


def cmd_fail(a):
    """门禁失败/审核反馈问题 → 回退到受影响最深阶段重走。"""
    spec = _spec(a)
    req_id = _require_req_id(a)
    st, path = _load_or_die(a.workdir, a.workflow, req_id)
    target = spec.find_phase_by_name(a.to)
    if target is None:
        _die("无法解析回退目标阶段: %s（可用阶段号或名称关键词）" % a.to)
    cur = st["current_phase"]
    if target["id"] > cur:
        _die("禁止前进式 fail（目标 Phase %d > 当前 Phase %d）" % (target["id"], cur))
    st["completed"] = [c for c in st["completed"] if c < target["id"]]
    st["current_phase"] = target["id"]
    st["status"] = "RUNNING"
    st["confirm_rounds"] = st.get("confirm_rounds", 0) + 1
    # v0.9.0: 纠正发生 → 自动沉淀候选经验(draft)，纯 Runtime/静默/best-effort
    # 不阻断纠正（锁失败仅 WARN）；落 draft/occ=1 不过信任门→预防/反应都不注入（护 150/0）
    _maybe_capture_lesson(st, target["id"], a.reason, spec)
    state_store.log_event(st, "rollback", phase=target["id"], detail=a.reason or "")
    state_store.save(path, st)
    print("ROLLBACK: 已回退到 Phase %d (%s)，原因: %s" % (target["id"], target["name"], a.reason or ""))
    print("按 output_write.md 修改流程起点判定：从本阶段起依次顺序执行至 Phase 14，不得跳阶段；")
    print("修改范围限定（只改问题点，无问题用例原样保留）。")
    print()
    # correction_context 传入 reason → _card 追加反应式 ##RELEVANT_LESSONS## 块（失败定向）
    print(_card(st, target, spec, correction_context=a.reason))


def cmd_patch(a):
    """G-FB1 修复·增量反哺回路：patch --to <phase> --reason <text>。

    与 fail --to（粗粒度回退重走整阶段）互补：patch 不改 current_phase/completed，
    只把"后续阶段对前置产物的修正意见"登记为 patch_directives，由当前阶段契约卡
    的 ##PATCH_FEEDBACK## 段注入模型上下文——模型在当前阶段就地修正前置产物切片
    （如 Phase 8 发现 Phase 5 漏标 RK3，不回退重跑 Phase 5，而在 Phase 8 就地补 RK3
    后重写本阶段产物）。--clear 清除已消化的指令。

    闭合 G-FB1：旧版只有 fail --to 粗粒度回退，"前置小修也要整阶段重跑"代价过高致
    模型倾向于"硬扛不修"；patch 提供轻量增量通道，让后续阶段发现的前置问题能精准反哺。
    """
    spec = _spec(a)
    req_id = _require_req_id(a)
    st, path = _load_or_die(a.workdir, a.workflow, req_id)
    if a.clear:
        cleared = len(st.get("patch_directives", []))
        st["patch_directives"] = []
        if cleared:
            state_store.log_event(st, "patch_clear", phase=st["current_phase"],
                                  detail="清除 %d 条已消化 patch 指令" % cleared)
        state_store.save(path, st)
        print("PATCH CLEAR: 已清除 %d 条 patch 指令" % cleared)
        return
    target = spec.find_phase_by_name(a.to)
    if target is None:
        _die("无法解析 patch 目标阶段: %s（可用阶段号或名称关键词）" % a.to)
    cur = st["current_phase"]
    if target["id"] > cur:
        _die("patch --to 仅支持反哺前置阶段（目标 Phase %d > 当前 Phase %d）。"
             "前进式修正用 set/next，不属 patch 语义。" % (target["id"], cur))
    if not a.reason:
        _die("patch --reason 必填：说明后续阶段发现的前置产物问题（供模型就地修正）")
    st.setdefault("patch_directives", [])
    directive = {"target_phase": target["id"], "target_name": target["name"],
                 "from_phase": cur, "reason": a.reason}
    st["patch_directives"].append(directive)
    # v0.9.0: 纠正发生 → 自动沉淀候选经验(draft)，纯 Runtime/静默/best-effort
    _maybe_capture_lesson(st, target["id"], a.reason, spec)
    state_store.log_event(st, "patch", phase=cur,
                          detail="→ Phase %d %s：%s" % (target["id"], target["name"], a.reason[:80]))
    state_store.save(path, st)
    print("PATCH: 已登记增量反哺指令 → Phase %d (%s)" % (target["id"], target["name"]))
    print("  原因: %s" % a.reason)
    print("  (不回退 current_phase=%d；指令将由当前/后续阶段契约卡的 ##PATCH_FEEDBACK## 段注入)" % cur)
    print()
    # correction_context 传入 reason → _card 追加反应式 ##RELEVANT_LESSONS## 块（失败定向）
    print(_card(st, spec.get_phase(cur), spec, correction_context=a.reason))


def _run_knowledge_gate(st, spec):
    """执行知识沉淀门禁（verify_knowledge.py 结构校验），返回 (ok, detail)。"""
    for chk in spec.knowledge_gate:
        ok, detail = _run_check(chk, st, spec)
        if not ok:
            return (False, detail)
    return (True, "verify_knowledge 通过")


def cmd_set(a):
    """登记判定结果/用户意图。

    C/Risk2: 移除 --req-id（消除危险的状态目录迁移操作；req_id 由 bootstrap 派生，
    start 时确定，不可后续 set 改写——否则状态目录与产物文件名失配）。
    保留 --depth/--input-kind/--mode/--knowledge/--excel。
    """
    spec = _spec(a)
    req_id = _require_req_id(a)
    st, path = _load_or_die(a.workdir, a.workflow, req_id)
    changed = []
    if a.depth is not None:
        if a.depth not in state_store.DEPTHS:
            _die("depth 取值须为 %s" % "/".join(state_store.DEPTHS))
        st["depth"] = a.depth
        st["skipped_phases"] = spec.depth_skips.get(a.depth, [])
        eff = spec.effective_phases(a.depth)
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
            ok, detail = _run_knowledge_gate(st, spec)
            if not ok:
                _die("知识总结门禁未过，拒绝登记 knowledge=done：\n%s" % detail)
            st["knowledge"] = "done"
            changed.append("knowledge=done（verify_knowledge 通过）")
        elif a.knowledge == "na":
            _die("knowledge 不支持 na：知识总结为审核通过后的强制后置动作（references/knowledge.md 31.1），"
                 "须生成 %s/Knowledge_%s.md 后登记 done" % (spec.output_dir, req_id))
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
    spec = _spec(a)
    req_id = (a.req_id or "").strip()
    st = None
    if req_id:
        st, _ = _load_or_die(a.workdir, a.workflow, req_id, need=False)
    depth = (st or {}).get("depth") or "heavy"
    print("执行计划（workflow=%s, depth=%s；阶段裁剪=%s）:" % (spec.name, depth, spec.depth_skips.get(depth, [])))
    cur = (st or {}).get("current_phase")
    for pid in spec.effective_phases(depth):
        ph = spec.get_phase(pid)
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
    spec = _spec(a)
    req_id = _require_req_id(a)
    st, path = _load_or_die(a.workdir, a.workflow, req_id)
    problems = []
    eff = spec.effective_phases(st.get("depth") or "heavy")
    if st["current_phase"] not in eff:
        problems.append("current_phase %d 不在有效阶段序列" % st["current_phase"])
    for c in st["completed"]:
        if c not in eff:
            problems.append("completed 含被裁剪阶段 %d" % c)
        if c > st["current_phase"]:
            problems.append("completed 含未来阶段 %d" % c)
    if st["status"] in ("WAIT_USER_CONFIRM", "WAIT_LICENSE"):
        g = spec.get_phase(st["current_phase"])["gate"]
        if (st["status"] == "WAIT_USER_CONFIRM" and g != "confirm") or \
           (st["status"] == "WAIT_LICENSE" and g != "license"):
            problems.append("status 与阶段 gate 类型不符")
    if problems:
        for p_ in problems:
            print("FAIL " + p_)
        sys.exit(1)
    print("STATE VERIFY OK: workflow=%s req_id=%s phase=%d status=%s completed=%s"
          % (st["workflow"], st.get("req_id"), st["current_phase"], st["status"], st["completed"]))


def cmd_reset(a):
    """删除分区运行状态（不影响产出物）。--legacy 清理旧 .runtime/。"""
    spec = _spec(a)
    if a.legacy:
        legacy = os.path.join(a.workdir, state_store.LEGACY_RUNTIME_DIR)
        if os.path.isdir(legacy):
            shutil.rmtree(legacy)
            print("已清理旧 runtime 目录: %s" % legacy)
        else:
            print("无旧 runtime 目录可清理: %s" % legacy)
        return
    req_id = _require_req_id(a)
    part = os.path.join(a.workdir, state_store.QAMASTER_ROOT, spec.name, req_id)
    if os.path.isdir(part):
        shutil.rmtree(part)
        print("已删除分区状态目录: %s（产出物文件不受影响）" % part)
    else:
        print("无分区状态可删除: %s" % part)


def cmd_manifest(a):
    """MANIFEST.md 共享索引维护（Runtime 独占，全程持 FileLock）。模型禁止直接 Write/Edit。"""
    spec = _spec(a)
    workdir = a.workdir
    mp = _manifest_path(workdir, spec)
    action = a.action
    if action == "list":
        # 只读，无需锁
        rows = manifest.load_rows(mp)
        if not rows:
            print("MANIFEST 为空或不存在: %s" % mp)
            return
        print(json.dumps({"workflow": spec.name, "manifest": mp, "rows": rows},
                         ensure_ascii=False, indent=2))
        return
    if action == "reconcile":
        with locking.FileLock(mp, timeout=30):
            ok, msg, cnt = manifest.reconcile(mp, workdir, spec.output_dir)
        print("MANIFEST RECONCILE: %s (%s, %d rows)" % ("OK" if ok else "FAIL", msg, cnt))
        return
    # add/update/complete 需 --req-id，全程持锁
    req_id = _require_req_id(a)
    with locking.FileLock(mp, timeout=30):
        if action == "add":
            ok, msg = manifest.add(mp, req_id, workdir=workdir, output_dir=spec.output_dir)
        elif action == "update":
            fields = {}
            if a.name is not None:
                fields["name"] = a.name
            if a.design_file is not None:
                fields["design_file"] = a.design_file
            if a.ledger_file is not None:
                fields["ledger_file"] = a.ledger_file
            if a.testcase_files is not None:
                fields["testcase_files"] = a.testcase_files
            if a.knowledge_file is not None:
                fields["knowledge_file"] = a.knowledge_file
            if a.status is not None:
                fields["status"] = a.status
            if not fields:
                _die("manifest update 需至少一个 --<field>")
            ok, msg = manifest.update(mp, req_id, **fields)
        elif action == "complete":
            ok, msg = manifest.complete(mp, req_id)
        else:
            _die("未知 manifest 动作: %s" % action)
    print("MANIFEST %s: %s — %s" % (action, "OK" if ok else "FAIL", msg))
    if not ok:
        sys.exit(1)


def cmd_kb(a):
    """KB_lessons.md 自我进化经验库维护（Runtime 独占，全程持 FileLock）。

    镜像 cmd_manifest 纪律：模型禁止直接 Write/Edit KB_lessons.md（进化机制与模型
    无关铁律；经验内容归属人类）。捕获已由 fail/patch 自动触发，本命令族供人
    背书/废止/清理/检索/回放/补录。纯 Runtime，零模型调用。

    审计：KB 文件本身即审计源（含 captured/source_reqs/occurrences）；仅在 req_id
    能定位到分区 state 时，best-effort 追加 history（不阻断 kb 写入本身）。
    """
    spec = _spec(a)
    workdir = a.workdir
    # v0.11.0: --kind 选 KB 文件（lesson -> KB_lessons.md；business -> KB_business.md）。
    # 默认 lesson（既有行为）。reconcile 仅对 business 有效（lesson 由 fail/patch 自动捕获）。
    kind = (a.kind or "lesson")
    if kind == "all":
        # list/reconcile 之外不支持 all；此处统一按 lesson 取主路径，list 内部再读双文件
        kind = "lesson"
    p = _kb_path(workdir, spec, "business" if kind == "business" else "lessons")
    action = a.action

    def _audit(req_id, event, detail):
        """best-effort：有分区 state 则 log_event，无则跳过（KB 文件已留痕）。"""
        if not req_id:
            return
        sp = os.path.join(workdir, state_store.QAMASTER_ROOT, spec.name, req_id, "state.json")
        if not os.path.isfile(sp):
            return
        try:
            st = state_store.load(sp)
            state_store.log_event(st, event, detail=detail)
            state_store.save(sp, st)
        except Exception:
            pass  # 审计失败不阻断 kb 操作（KB 文件是事实源）

    def _print_block(title, block):
        if block:
            print("")
            print("===== %s =====" % title)
            print(block)

    # --- 只读路径（无锁） ---
    if action == "list":
        # --kind all：合并读 lessons + business 两文件（business no-op 时退空）
        if (a.kind or "lesson") == "all":
            rows = kb_store.list_records(p, status=a.status, phase=a.phase, dimension=a.dimension)
            pb = _kb_path(workdir, spec, "business")
            rows += kb_store.list_records(pb, status=a.status, phase=a.phase, dimension=a.dimension)
            print("KB LIST: lessons+business — %d 条记录" % len(rows))
        else:
            rows = kb_store.list_records(p, status=a.status, phase=a.phase, dimension=a.dimension)
            print("KB LIST: %s — %d 条记录" % (p, len(rows)))
        print(json.dumps({"workflow": spec.name, "kb": p, "rows": rows},
                         ensure_ascii=False, indent=2))
        return
    if action == "show":
        if not a.id:
            _die("kb show 需 --id <经验id>")
        rec = kb_store.get_record(p, a.id)
        if rec is None:
            _die("经验 id 不存在: %s" % a.id)
        print(json.dumps({"workflow": spec.name, "kb": p, "record": rec},
                         ensure_ascii=False, indent=2))
        return
    if action == "query":
        # 只读预览：针对某 req/文件，打印"会注入什么"（预防式或反应式），供人预览/校准
        req_id = a.against or ""
        # 构造临时 state 供检索 helper
        st_q = {"workdir": workdir, "req_id": req_id}
        phase = spec.get_phase(int(a.phase)) if a.phase else None
        if phase is None:
            _die("kb query 需 --phase <N>（指定阶段号）")
        if (a.kind or "lesson") == "business":
            # business 检索路径（phase 无关；Phase 0 预防 / 失败反应同一 helper）
            if a.context:
                block = _relevant_business_kb_on_fail(st_q, phase, a.context, spec)
                _print_block("RELEVANT_BUSINESS_KB（反应式·失败定向·会注入）", block or "(无命中)")
            else:
                block = _prior_business_kb_block(st_q, phase, spec)
                _print_block("PRIOR_BUSINESS_KB（预防式·Phase 0·会注入）", block or "(无命中)")
            print("  （top=%d；信任门：endorsed 或 occ≥3；相关性门：surface≥2 或标题命中）"
                  % (a.top or 3))
            return
        if a.context:
            block = _relevant_lessons_on_fail(st_q, phase, a.context, spec)
            _print_block("RELEVANT_LESSONS（反应式·失败定向·会注入）", block or "(无命中)")
        else:
            block = _prior_kb_block(st_q, phase, spec, kind="lesson")
            _print_block("PRIOR_LESSONS（预防式·开工前·会注入）", block or "(无命中)")
        print("  （top=%d；信任门：endorsed 或 occ≥3；相关性门：surface≥2 或标题命中）"
              % (a.top or 3))
        return
    if action == "distill":
        # 只读回放：该 req 全部 rollback/patch/gate_fail（含 gate_fail 修正信息，零模型）
        req_id = _require_req_id(a)
        st, _ = _load_or_die(workdir, a.workflow, req_id)
        history = st.get("history") or []
        rows = [h for h in history if h.get("event") in ("rollback", "patch", "gate_fail", "patch_clear")]
        print("KB DISTILL: %s 回放 %d 条纠正事件（供人决定是否手工 add-lesson/endorse）" % (req_id, len(rows)))
        for h in rows:
            ts = h.get("ts", "")
            ev = h.get("event", "")
            ph = h.get("phase", "")
            det = h.get("detail", "")
            print("  - [%s] %s phase=%s: %s" % (ts, ev, ph, det))
        print("  （自动捕获已在 fail/patch 触发；gate_fail 修正信息仅此处回放，零模型）")
        return

    # --- 写路径（持 FileLock） ---
    if action == "reconcile":
        # v0.11.0: business 专用——从 Knowledge_*.md 聚合业务知识索引到 KB_business.md。
        # lesson 无 reconcile（由 fail/patch 自动捕获）。镜像 cmd_manifest reconcile 纪律。
        if (a.kind or "lesson") != "business":
            _die("kb reconcile 仅对 --kind business 有效（lessons 经 fail/patch 自动捕获）")
        skill_dir = os.path.join(PLUGIN_ROOT, spec.skill_dir)
        with locking.FileLock(p, timeout=30):
            ok, msg, cnt = kb_store.reconcile_business(
                p, workdir, spec.output_dir, skill_dir)
        print("KB RECONCILE: %s — %s（business 记录 %d 条）"
              % ("OK" if ok else "NO-OP/FAIL", msg, cnt))
        if not ok:
            # no-op（无 Knowledge 文件/目录）不判失败退出，只提示
            return
        return
    if action == "add-lesson":
        if not a.phase:
            _die("kb add-lesson 需 --phase <N>")
        if not a.summary:
            _die("kb add-lesson 需 --summary <经验原文>（人类原话 verbatim）")
        trig = []
        if a.trigger:
            trig = [t.strip() for t in a.trigger.split("/") if t.strip()]
        rec = {
            "kind": "lesson", "phase": str(a.phase), "dimension": a.dimension or "通用",
            "error_type": "人工纠正", "module": a.module or "",
            "source_req": a.source_req or "manual", "captured": kb_store._today(),
            "raw_text": a.summary.strip(), "status": a.status or "draft",
            "occurrences": 1, "trigger": trig,
        }
        with locking.FileLock(p, timeout=30):
            fp = kb_store.upsert_lesson(p, rec)
        _audit(a.req_id, "kb_add_lesson", detail="id=%s dim=%s" % (fp, rec["dimension"]))
        print("KB ADD-LESSON: OK — id=%s（指纹去重：同类已合并则 occ++）" % fp)
        return
    if action == "endorse":
        if not a.id:
            _die("kb endorse 需 --id <经验id>")
        with locking.FileLock(p, timeout=30):
            ok, msg = kb_store.endorse(p, a.id)
        _audit(a.req_id, "kb_endorse", detail="id=%s" % a.id)
        print("KB ENDORSE: %s — %s" % ("OK" if ok else "FAIL", msg))
        if not ok:
            sys.exit(1)
        return
    if action == "supersede":
        if not a.id or not a.by:
            _die("kb supersede 需 --id <老id> --by <新id>")
        with locking.FileLock(p, timeout=30):
            ok, msg = kb_store.supersede(p, a.id, a.by)
        _audit(a.req_id, "kb_supersede", detail="%s by %s" % (a.id, a.by))
        print("KB SUPERSEDE: %s — %s" % ("OK" if ok else "FAIL", msg))
        if not ok:
            sys.exit(1)
        return
    if action == "prune":
        with locking.FileLock(p, timeout=30):
            if a.id:
                ok, msg, cnt = kb_store.prune(p, rec_id=a.id)
            else:
                ok, msg, cnt = kb_store.prune(p, status=a.status, older_than_days=a.older_than)
        _audit(a.req_id, "kb_prune", detail="%s removed=%d" % (msg, cnt))
        print("KB PRUNE: %s — %s（删除 %d 条）" % ("OK" if ok else "FAIL", msg, cnt))
        if not ok:
            sys.exit(1)
        return
    _die("未知 kb 动作: %s" % action)


def main():
    _utf8()
    _register_workflows()
    ap = argparse.ArgumentParser(prog="qamaster_runtime", description="qamaster Runtime Controller（通用 workflow 状态机）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _wd(sp):
        sp.add_argument("--workdir", default=os.getcwd(), help="用户工作目录（产出物与状态根），默认当前目录")

    def _wf(sp):
        sp.add_argument("--workflow", default=DEFAULT_WORKFLOW, help="workflow 名（默认 case-design）")

    def _ri(sp, required=False):
        sp.add_argument("--req-id", default="", required=required,
                        help="需求标识（由 bootstrap 派生；分区状态定位用）")

    # bootstrap
    sp = sub.add_parser("bootstrap", help="派生需求标识（不创状态，幂等）")
    sp.add_argument("--user-input", default="", help="原始用户输入（文件路径或内联文本）")
    _ri(sp)
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_bootstrap)

    sp = sub.add_parser("start", help="启动/恢复流程（req_id 必需）")
    _ri(sp, required=True)
    sp.add_argument("--mode", default="full", choices=list(state_store.RUN_MODES))
    sp.add_argument("--user-input", default="", help="原始用户输入（记录审计，不解析）")
    sp.add_argument("--fresh", action="store_true", help="忽略已有状态强制重启")
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_start)

    sp = sub.add_parser("status", help="查看状态（--req-id 单需求 | --all 全量）")
    sp.add_argument("--all", action="store_true", help="列出该 workflow 所有在途需求")
    sp.add_argument("--card", action="store_true", help="同时输出当前阶段契约卡")
    _ri(sp)
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_status)

    sp = sub.add_parser("next", help="推进到下一阶段（仅当前阶段已过 gate）")
    _ri(sp)
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_next)

    sp = sub.add_parser("gate", help="执行当前阶段出口门禁")
    _ri(sp)
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_gate)

    sp = sub.add_parser("confirm", help="人工门：用户已确认/答复/许可")
    _ri(sp)
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_confirm)

    sp = sub.add_parser("reject", help="许可门：用户拒绝（不生成 Excel）")
    _ri(sp)
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_reject)

    sp = sub.add_parser("fail", help="门禁失败/审核反馈 → 回退重走")
    sp.add_argument("--to", required=True, help="回退目标阶段（阶段号或名称关键词）")
    sp.add_argument("--reason", default="")
    _ri(sp)
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_fail)

    sp = sub.add_parser("patch", help="增量反哺（G-FB1：不回退，登记前置产物修正指令注入当前阶段）")
    sp.add_argument("--to", default=None, help="前置目标阶段（阶段号或名称关键词）")
    sp.add_argument("--reason", default="")
    sp.add_argument("--clear", action="store_true", help="清除已消化的 patch 指令")
    _ri(sp)
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_patch)

    sp = sub.add_parser("set", help="登记判定结果/用户意图（depth/input-kind/mode/knowledge/excel）")
    sp.add_argument("--depth", default=None)
    sp.add_argument("--input-kind", default=None, choices=list(state_store.INPUT_KINDS))
    sp.add_argument("--mode", default=None, choices=list(state_store.RUN_MODES))
    sp.add_argument("--knowledge", default=None, choices=["done"])
    sp.add_argument("--excel", default=None, choices=["asked_yes", "asked_no", "generated", "declined", "na"])
    _ri(sp)
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_set)

    sp = sub.add_parser("manifest", help="MANIFEST 索引维护（Runtime 独占，模型禁止 Write/Edit）")
    sp.add_argument("action", choices=["add", "update", "complete", "list", "reconcile"])
    sp.add_argument("--name", default=None)
    sp.add_argument("--design-file", default=None)
    sp.add_argument("--ledger-file", default=None)
    sp.add_argument("--testcase-files", default=None)
    sp.add_argument("--knowledge-file", default=None)
    sp.add_argument("--status", default=None, choices=["进行中", "已完成", "已归档"])
    _ri(sp)
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_manifest)

    sp = sub.add_parser("kb", help="KB 经验库维护（自我进化·Runtime 独占，模型禁止 Write/Edit）")
    sp.add_argument("action", choices=["list", "show", "query", "distill", "reconcile",
                                       "add-lesson", "endorse", "supersede", "prune"])
    sp.add_argument("--kind", default="lesson", choices=["lesson", "business", "all"],
                    help="KB 种类：lesson=经验库（默认）/business=业务知识库/all=合并读（list）")
    sp.add_argument("--id", default=None, help="经验 id（show/endorse/supersede --id/prune --id）")
    sp.add_argument("--by", default=None, help="supersede：新经验 id（--id <老> --by <新>）")
    sp.add_argument("--against", default=None, help="query：目标需求 id 或文件（预防式检索用）")
    sp.add_argument("--phase", default=None, help="query/add-lesson：阶段号")
    sp.add_argument("--context", default=None, help="query：失败/纠正文本（走反应式打分）")
    sp.add_argument("--top", default=3, type=int, help="query：返回条数上限（默认 3）")
    sp.add_argument("--dimension", default=None, help="list/add-lesson：业务维度")
    sp.add_argument("--status", default=None, choices=["draft", "endorsed"], help="list/prune：状态过滤")
    sp.add_argument("--older-than", default=None, type=int, help="prune：N 天前（配合 --status draft）")
    sp.add_argument("--summary", default=None, help="add-lesson：经验原文（人类原话 verbatim）")
    sp.add_argument("--trigger", default=None, help="add-lesson：触发词，'/' 分隔")
    sp.add_argument("--module", default=None, help="add-lesson：模块/需求名（仅溯源展示）")
    sp.add_argument("--source-req", default=None, help="add-lesson：来源需求 id")
    _ri(sp)
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_kb)

    sp = sub.add_parser("plan", help="查看执行计划（按深度裁剪后的阶段序列）")
    _ri(sp)
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_plan)

    sp = sub.add_parser("verify", help="离线自证校验状态一致性")
    _ri(sp)
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_verify)

    sp = sub.add_parser("reset", help="删除运行状态（不影响产出物）")
    sp.add_argument("--legacy", action="store_true", help="清理旧 case-design-out/.runtime/ 目录")
    _ri(sp)
    _wf(sp)
    _wd(sp)
    sp.set_defaults(fn=cmd_reset)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
