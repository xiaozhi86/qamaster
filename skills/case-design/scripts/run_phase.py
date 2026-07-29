#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_phase.py — 阶段门禁包装器 + 跳过检测 + 状态机（Tier B 降本·跨平台）

用途：把"自愿跑脚本"提升为"包装器统一触发并留痕"。skill 在各阶段门禁点经 Bash 调用本脚本，
由本脚本串联 verify_cases / verify_md / verify_knowledge，并把每次运行写进
case-design-out/.gate_log（sentinel，含 stdout 短哈希防伪造），同时读写
case-design-out/.phase_state.json（外置循环计数 + 幂等防覆盖）。

闭合的本方案洞：
  - 跳过检测（项1）：脚本不跑 -> .gate_log 无对应条目 -> 交付摘要可被核对"门禁缺失"
  - 自动触发门禁（项2）：模型/hook 只需调 `python scripts/run_phase.py <子命令>`，
    包装器内部串好 verify 链，非零 exit 中止并留痕
  - 交付摘要机器可验证块（项4）：读取 verify_cases.py 末尾的 json-gate-digest 块，
    原样回显供交付摘要粘贴；同时把该块的 hash 写进 sentinel（防手编）
  - 状态外置 + 幂等防覆盖（项5/优化3）：.phase_state.json 带 version/last_phase，
    每次调用先打印"当前阶段=last_phase，本次将进=phase N"，与 .gate_log 交叉引用
  - REQ 落盘硬校验（优化1）：进第8 gate 前查 REQ 是否存在且含 ## 二级标题，
    缺失则记 REQ_MISSING（闭合 #4 静默跳过）
  - MANIFEST 联动检测另生新文件（项10-5）：落盘后核对新 Write 的文件名 ∈ MANIFEST 已登记集合，
    未登记则记 UNEXPECTED_NEW_FILE

新增功能（v0.6.0 - 2026-07-29）：
  - **Phase 0-7 前置门禁验证**：gate8 在执行前强制验证 Phase 0-7 是否完成
    - 检查 MANIFEST.md 是否存在（Phase 0 必须产出）
    - 检查 Clarification_Ledger_*.md 是否存在（Phase 1 必须产出）
    - 缺少任一产出物，拒绝执行，返回错误码 1
  - **阶段签名机制**：每个阶段完成后可调用 gate-phase 写入签名
    - 记录阶段完成时间、产出文件、文件哈希
    - .phase_signatures.json 记录所有阶段的完成状态
    - gate8 验证签名是否完整（可选，增强验证）

新增功能（v0.7.0 - 2026-07-29）：
  - **Phase 2-7 硬拒绝**：check_phase_dependencies 从"可选警告"提为"硬拒绝"，
    gate8 要求 Phase 0-7 签名齐全才放行，闭合弱模型跳过中间阶段（规则建模/
    风险分析/策略匹配/测试点建模）的漏洞。
  - **阶段顺序校验**：cmd_gate_phase 签 Phase N 前须先签 Phase N-1，
    禁止跨阶段跳签（PHASE_ORDER_VIOLATION）。
  - **preflight 自动注入**：cmd_gate_phase 内嵌 _inject_preflight，随门禁
    stdout 注入本阶段 ref 40 行大纲摘要，不再依赖模型自觉读 ref。
  - **PreToolUse hook 联动**：.claude/hooks/case_design_gate.py 在 Write/Edit
    TestCases_*.md|.xlsx 前 hard-block，未过 gate8 且 Phase 0-7 签名不全即
    exit 2 阻止工具调用，把"模型自觉合规"升级为"harness 强制合规"。

跨平台（强制·不可违背）：
  - 纯 Python 标准库（os / json / hashlib / subprocess / sys），无平台依赖；
  - 路径用 os.path.join，相对路径 case-design-out/...；
  - 调 verify 脚本统一用 sys.executable（当前 Python 解释器），避免 python/python3 分歧；
  - 行尾统一 \\n，json.dump(ensure_ascii=False)；
  - 禁止 .sh/.bat/.ps1（本文件即全部自动化逻辑，.py 跨平台）。

子命令：
  python run_phase.py gate8 <TC.md> [REQ.md]            # 第8阶段出口 gate（写前内存内）
  python run_phase.py readback <TC.md> [REQ.md]         # 第13阶段回读（verify_md + verify_cases 文件入口）
  python run_phase.py gate-phase <phase> <outputs>      # 阶段门禁：验证产出物并写入签名
  python run_phase.py check-new-file <文件名>           # 核对该文件名 ∈ MANIFEST
  python run_phase.py state show                         # 打印当前 .phase_state.json
  python run_phase.py state set <phase>                 # 更新 last_phase
  python run_phase.py verify <TC.md> [REQ.md]           # 校验交付摘要粘贴的 sentinel 块哈希
  python run_phase.py summary                           # 打印 .gate_log 全部 sentinel（交付前核对）

退出码：0=门禁通过/状态操作成功；1=门禁失败/校验不通过/缺失门禁。
本脚本是 skill 自带可复用资产，不删除（与 verify_md/verify_cases 同级）。
"""
import sys
import os
import json
import hashlib
import subprocess
import glob
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPTS_DIR)
PROJECT_ROOT = os.getcwd()  # 当前项目根（skill 运行时 cwd 即项目根）
OUT_DIR = os.path.join(PROJECT_ROOT, "case-design-out")
GATE_LOG = os.path.join(OUT_DIR, ".gate_log")
STATE_FILE = os.path.join(OUT_DIR, ".phase_state.json")
SIGNATURES_FILE = os.path.join(OUT_DIR, ".phase_signatures.json")
PY = sys.executable


def _ensure_out_dir():
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR, exist_ok=True)


def _read_manifest_files():
    """读 case-design-out/MANIFEST.md，解析索引表，返回已登记文件名集合。
    MANIFEST 不存在返回空集合（首跑场景）。已登记产出物文件名特征：
    REQ_*.md / TestCases_*.md / TestCases_*.xlsx / Clarification_Ledger_*.md / Knowledge_*.md
    （含逗号分隔的多 PART 清单）。"""
    mp = os.path.join(OUT_DIR, "MANIFEST.md")
    files = set()
    if not os.path.exists(mp):
        return files
    try:
        with open(mp, "r", encoding="utf-8") as f:
            for ln in f:
                if "|" not in ln:
                    continue
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                for c in cells:
                    if not c:
                        continue
                    # 必须形如 已知产出物文件名前缀 + 含 .md/.xlsx 扩展名
                    if any(c.startswith(p) for p in
                           ("REQ_", "TestCases_", "Clarification_Ledger_", "Knowledge_")):
                        # 逗号分隔的多文件清单拆开
                        for part in c.split(","):
                            part = part.strip()
                            if part and ("." in part):
                                files.add(part)
    except Exception:
        pass
    return files


def _short_hash(text):
    """sha256 前 8 位（防伪造 sentinel）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def append_sentinel(script, phase, exit_code, stdout_text, state_version=None, note=""):
    """向 .gate_log 追加一条 sentinel。含 stdout 摘要哈希，防模型手编假 sentinel。"""
    _ensure_out_dir()
    digest_hash = _short_hash(stdout_text[:200])
    line_fields = [
        "ts_idx",  # 占位，由调用方填；此处用一个稳定序号避免时间戳（脚本环境禁用 Date.now）
    ]
    # 字段：script | phase | exit | digest_hash | note | state_version
    # 用 | 分隔，单行，避免换行差异
    rec = "|".join([
        script,
        str(phase),
        str(exit_code),
        digest_hash,
        note or "",
        str(state_version) if state_version is not None else "",
    ])
    with open(GATE_LOG, "a", encoding="utf-8") as f:
        f.write(rec + "\n")
    return digest_hash


def load_state():
    """读 .phase_state.json，不存在返回初始 dict。"""
    if not os.path.exists(STATE_FILE):
        return {"version": 0, "last_phase": None, "loops": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": 0, "last_phase": None, "loops": {}}


def save_state(state):
    """写 .phase_state.json（整体覆盖，幂等）。"""
    _ensure_out_dir()
    state["version"] = state.get("version", 0) + 1
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return state["version"]


def load_signatures():
    """读 .phase_signatures.json，不存在返回初始 dict。"""
    if not os.path.exists(SIGNATURES_FILE):
        return {"phases": {}}
    try:
        with open(SIGNATURES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"phases": {}}


def save_signatures(signatures):
    """写 .phase_signatures.json（整体覆盖）。"""
    _ensure_out_dir()
    with open(SIGNATURES_FILE, "w", encoding="utf-8") as f:
        json.dump(signatures, f, ensure_ascii=False, indent=2)


def write_phase_signature(phase_num, outputs):
    """写入阶段完成签名。

    Args:
        phase_num: 阶段编号
        outputs: 产出文件列表（相对 case-design-out/ 的文件名）
    """
    signatures = load_signatures()

    # 计算产出文件哈希
    hash_list = []
    for output in outputs:
        file_path = os.path.join(OUT_DIR, output)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'rb') as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()[:16]
                    hash_list.append(file_hash)
            except Exception:
                pass

    # 写入签名
    signatures["phases"][str(phase_num)] = {
        "completed": True,
        "timestamp": datetime.now().isoformat(),
        "outputs": outputs,
        "signature": hashlib.sha256(
            json.dumps(hash_list, sort_keys=True).encode()
        ).hexdigest()[:16] if hash_list else ""
    }

    save_signatures(signatures)


def check_phase_dependencies(current_phase):
    """检查前置阶段是否完成。

    Args:
        current_phase: 当前要进入的阶段

    Returns:
        (bool, str): (是否通过, 错误信息)
    """
    # 定义每个阶段必须的产出物
    phase_required_outputs = {
        0: ["MANIFEST.md"],  # Phase 0 必须产出 MANIFEST.md
        1: [],  # Phase 1 产出 Clarification_Ledger_*.md（glob匹配）
    }

    signatures = load_signatures()

    # 检查 Phase 0
    if current_phase > 0:
        # 检查 MANIFEST.md 是否存在
        manifest_path = os.path.join(OUT_DIR, "MANIFEST.md")
        if not os.path.exists(manifest_path):
            return False, "Phase 0 未完成：缺少 case-design-out/MANIFEST.md"

        # 检查签名
        phase0_sig = signatures.get("phases", {}).get("0", {})
        if not phase0_sig.get("completed"):
            return False, "Phase 0 未完成：缺少阶段签名"

    # 检查 Phase 1
    if current_phase > 1:
        # 检查 Clarification_Ledger_*.md 是否存在
        ledger_pattern = os.path.join(OUT_DIR, "Clarification_Ledger_*.md")
        ledger_files = glob.glob(ledger_pattern)
        if not ledger_files:
            return False, "Phase 1 未完成：缺少 case-design-out/Clarification_Ledger_*.md"

        # 检查签名
        phase1_sig = signatures.get("phases", {}).get("1", {})
        if not phase1_sig.get("completed"):
            return False, "Phase 1 未完成：缺少阶段签名"

    # 检查 Phase 2-7（强制：缺签名即拒绝，闭合弱模型跳过中间阶段）
    # v0.7.0：从"可选警告"提为"硬拒绝"——glm-5 等弱模型会跳过规则建模(3)/
    # 风险分析(5)/策略匹配(6)/测试点建模(7) 直接生成用例，软警告挡不住。
    if current_phase >= 8:
        for phase in range(2, 8):
            phase_sig = signatures.get("phases", {}).get(str(phase), {})
            if not phase_sig.get("completed"):
                return False, "Phase %s 未完成：缺少阶段签名（请先 gate-phase %s）" % (phase, phase)

    return True, ""


def _run_verify(script_name, args):
    """运行 scripts/<script_name>.py，返回 (exit_code, stdout_text)。"""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    if not os.path.exists(script_path):
        print("[run_phase] 脚本缺失: %s" % script_path)
        return 1, ""
    cmd = [PY, script_path] + args
    try:
        # capture stdout；stderr 合并进 stdout 便于留痕
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out
    except Exception as e:
        return 1, "[run_phase] 调用异常: %s" % e


def extract_digest_block(stdout_text):
    """从 verify_cases.py stdout 末尾提取 ```json-gate-digest ... ``` 块并解析为 dict。
    无则返回 None。"""
    import re
    m = re.search(r"```json-gate-digest\s*\n(.*?)\n```", stdout_text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


# ===== 子命令实现 =====

def cmd_gate8(tc_path, req_path=None):
    """第8阶段出口 gate（写前内存内）：读 TC.md 行 -> verify_cases.run_inmemory。
    本包装器以文件入口近似（读 TC.md 行后调 verify_cases 文件入口），并提取 digest 块。

    新增：Phase 0-7 前置阶段门禁验证（强制）。
    """
    state = load_state()
    print("[gate8] 当前阶段=last_phase=%s，本次将进=phase 8 出口 gate" % state.get("last_phase"))

    # ===== 新增：Phase 0-7 前置阶段门禁验证 =====
    # 验证 Phase 0 是否完成（必须产出 MANIFEST.md）
    manifest_path = os.path.join(OUT_DIR, "MANIFEST.md")
    if not os.path.exists(manifest_path):
        append_sentinel("verify_cases", "gate8", 1, "",
                        note="MANIFEST_MISSING",
                        state_version=state.get("version"))
        print("[gate8] MANIFEST_MISSING：Phase 0 未完成")
        print("[gate8] 缺少 case-design-out/MANIFEST.md")
        print("[gate8] 请先执行 Phase 0：需求定位和 MANIFEST 创建")
        print("[gate8] 参考：references/phase0_manifest.md")
        save_state(state)
        return 1

    # 验证 Phase 1 是否完成（必须产出 Clarification_Ledger_*.md）
    ledger_pattern = os.path.join(OUT_DIR, "Clarification_Ledger_*.md")
    ledger_files = glob.glob(ledger_pattern)
    if not ledger_files:
        append_sentinel("verify_cases", "gate8", 1, "",
                        note="CLARIFICATION_MISSING",
                        state_version=state.get("version"))
        print("[gate8] CLARIFICATION_MISSING：Phase 1 未完成")
        print("[gate8] 缺少 case-design-out/Clarification_Ledger_*.md")
        print("[gate8] 请先执行 Phase 1：需求澄清和台账创建")
        print("[gate8] 参考：references/clarification.md")
        save_state(state)
        return 1

    # 验证阶段签名（可选，增强验证）
    signatures = load_signatures()
    phase0_sig = signatures.get("phases", {}).get("0", {})
    phase1_sig = signatures.get("phases", {}).get("1", {})
    if not phase0_sig.get("completed"):
        print("[gate8] ⚠️  警告：Phase 0 缺少阶段签名，建议运行 gate_phase.py gate 0")
    if not phase1_sig.get("completed"):
        print("[gate8] ⚠️  警告：Phase 1 缺少阶段签名，建议运行 gate_phase.py gate 1")

    # ===== v0.7.0：Phase 0-7 前置依赖硬校验（接入 check_phase_dependencies） =====
    # check_phase_dependencies 会硬性检查 Phase 0(MANIFEST+签名)/1(台账+签名)/2-7(签名)
    # 任一缺失即拒绝 gate8，与 PreToolUse hook 联动（hook 也查 0-7 签名）。
    dep_ok, dep_msg = check_phase_dependencies(8)
    if not dep_ok:
        append_sentinel("verify_cases", "gate8", 1, "",
                        note="PHASE_DEPS_MISSING",
                        state_version=state.get("version"))
        print("[gate8] PHASE_DEPS_MISSING：%s" % dep_msg)
        print("[gate8] 请先逐阶段补签：python scripts/run_phase.py gate-phase <N> \"<产出物>\"")
        print("[gate8] （Phase 2-7 为内存阶段，无文件产出时传空串 \"\"）")
        save_state(state)
        return 1

    # ===== 原有 REQ 检查逻辑 =====
    if req_path:
        if not os.path.exists(req_path):
            append_sentinel("verify_cases", "gate8", 1, "", note="REQ_MISSING",
                            state_version=state.get("version"))
            print("[gate8] REQ_MISSING：需求文档 %s 不存在，#4 将静默跳过。"
                  "请先落盘 case-design-out/REQ_<需求标识>.md（含 ## 二级标题）。" % req_path)
            save_state(state)
            return 1
        with open(req_path, "r", encoding="utf-8") as f:
            req_text = f.read()
        if "## " not in req_text:
            append_sentinel("verify_cases", "gate8", 1, "", note="REQ_NO_HEADINGS",
                            state_version=state.get("version"))
            print("[gate8] REQ_NO_HEADINGS：需求文档 %s 无 ## 二级标题，#4 不可解析。"
                  "请补 ## 二级标题分节后重跑。" % req_path)
            save_state(state)
            return 1

    args = [tc_path]
    if req_path:
        args.append(req_path)
    rc, out = _run_verify("verify_cases.py", args)
    digest = extract_digest_block(out) or {}
    digest_hash = append_sentinel("verify_cases", "gate8", rc, out,
                                  note="gate8", state_version=state.get("version"))
    print(out)
    print("[gate8] sentinel 已记录：exit=%s digest_hash=%s state_version=%s" % (
        rc, digest_hash, state.get("version")))
    if digest:
        print("[gate8] 交付摘要须粘贴的机器块：")
        print("```json-gate-digest")
        print(json.dumps(digest, ensure_ascii=False))
        print("```")
    state["last_phase"] = "gate8"
    save_state(state)
    return rc


def cmd_readback(tc_path, req_path=None):
    """第13阶段回读：verify_md.py + verify_cases.py 文件入口串联。"""
    state = load_state()
    print("[readback] 当前阶段=last_phase=%s，本次将进=phase 13 回读" % state.get("last_phase"))

    # verify_md 结构
    rc_md, out_md = _run_verify("verify_md.py", [tc_path])
    append_sentinel("verify_md", "readback", rc_md, out_md,
                    note="readback_structure", state_version=state.get("version"))
    # verify_cases 内容
    args = [tc_path]
    if req_path:
        args.append(req_path)
    rc_vc, out_vc = _run_verify("verify_cases.py", args)
    digest = extract_digest_block(out_vc) or {}
    append_sentinel("verify_cases", "readback", rc_vc, out_vc,
                    note="readback_content", state_version=state.get("version"))

    print(out_md)
    print(out_vc)
    overall_rc = 1 if (rc_md != 0 or rc_vc != 0) else 0
    print("[readback] sentinel 已记录：verify_md exit=%s, verify_cases exit=%s -> overall=%s" % (
        rc_md, rc_vc, overall_rc))
    if digest:
        print("[readback] 交付摘要须粘贴的机器块：")
        print("```json-gate-digest")
        print(json.dumps(digest, ensure_ascii=False))
        print("```")
    state["last_phase"] = "readback"
    save_state(state)
    return overall_rc


def cmd_check_new_file(filename):
    """项10-5：核对该文件名 ∈ MANIFEST 已登记集合，未登记记 UNEXPECTED_NEW_FILE。"""
    state = load_state()
    manifest_files = _read_manifest_files()
    # 规范化：取 basename
    base = os.path.basename(filename)
    # 拆 PART 场景：TestCases_<id>_PARTn.md 视为合规重排（主名 TestCases_<id> 已登记即可）
    is_part = ("_PART" in base)
    registered = base in manifest_files
    if is_part:
        # 取去掉 _PARTn 的主名核对
        import re
        main_name = re.sub(r"_PART\d+\.md$", ".md", base)
        registered = main_name in manifest_files or base in manifest_files

    if registered:
        append_sentinel("run_phase", "check-new-file", 0, base,
                        note="file_registered:%s" % base, state_version=state.get("version"))
        print("[check-new-file] OK：%s ∈ MANIFEST 已登记" % base)
        rc = 0
    else:
        append_sentinel("run_phase", "check-new-file", 1, base,
                        note="UNEXPECTED_NEW_FILE:%s" % base, state_version=state.get("version"))
        print("[check-new-file] UNEXPECTED_NEW_FILE：%s 不在 MANIFEST 已登记集合内。"
              "已有产出物修改须在原文件整体 Write 覆盖，禁止另起新文件名（见 SKILL.md §19/§25）。" % base)
        rc = 1
    save_state(state)
    return rc


def _inject_preflight(phase_num):
    """v0.7.0：进入阶段前自动注入对应 ref 的 40 行大纲摘要（降认知负载）。
    即使模型不主动读 ref，摘要也随门禁 stdout 进上下文。best-effort：脚本缺失/异常
    不影响门禁主流程。"""
    pf = os.path.join(SCRIPTS_DIR, "preflight.py")
    if not os.path.exists(pf):
        return
    try:
        proc = subprocess.run([PY, pf, "--phase", str(phase_num)],
                             capture_output=True, text=True, encoding="utf-8",
                             timeout=10)
        out = (proc.stdout or "").strip()
        if out:
            print("----- preflight phase %s 大纲（自动注入，免读 ref） -----" % phase_num)
            print(out)
            print("-" * 60)
    except Exception:
        pass


def cmd_gate_phase(phase_num, outputs_str=None):
    """阶段门禁：验证 Phase N 的产出物并写入签名。

    Args:
        phase_num: 阶段编号
        outputs_str: 产出文件列表（逗号分隔），如 "MANIFEST.md,REQ_001.md"

    用法:
        python run_phase.py gate-phase 0 "MANIFEST.md,REQ_001.md"
        python run_phase.py gate-phase 1 "Clarification_Ledger_001.md"
    """
    state = load_state()
    print("[gate-phase] 当前阶段=last_phase=%s，本次将验证=phase %s" % (
        state.get("last_phase"), phase_num))

    # v0.7.0：阶段顺序校验——签 Phase N 前须先签 Phase N-1，防止弱模型跨阶段跳签
    if phase_num >= 1:
        signatures = load_signatures()
        prev_sig = signatures.get("phases", {}).get(str(phase_num - 1), {})
        if not prev_sig.get("completed"):
            append_sentinel("run_phase", "gate-phase", 1, "",
                            note="PHASE_ORDER_VIOLATION",
                            state_version=state.get("version"))
            print("[gate-phase] PHASE_ORDER_VIOLATION：Phase %s 未签，禁止跳签 Phase %s" % (
                phase_num - 1, phase_num))
            print("[gate-phase] 请先 gate-phase %s" % (phase_num - 1))
            save_state(state)
            return 1

    # v0.7.0：自动注入本阶段 ref 大纲摘要（best-effort，不阻断）
    _inject_preflight(phase_num)

    # 解析产出物列表
    outputs = []
    if outputs_str:
        outputs = [x.strip() for x in outputs_str.split(",") if x.strip()]

    # 验证产出物是否存在
    missing_outputs = []
    for output in outputs:
        output_path = os.path.join(OUT_DIR, output)
        if not os.path.exists(output_path):
            missing_outputs.append(output)

    if missing_outputs:
        append_sentinel("run_phase", "gate-phase", 1, "",
                        note="PHASE_OUTPUTS_MISSING",
                        state_version=state.get("version"))
        print("[gate-phase] PHASE_OUTPUTS_MISSING：Phase %s 缺少产出文件" % phase_num)
        print("[gate-phase] 缺少文件：%s" % ", ".join(missing_outputs))
        save_state(state)
        return 1

    # 写入阶段签名
    write_phase_signature(phase_num, outputs)
    append_sentinel("run_phase", "gate-phase", 0, "",
                    note="phase_%s_completed" % phase_num,
                    state_version=state.get("version"))

    print("[gate-phase] OK：Phase %s 完成，签名已写入" % phase_num)
    print("[gate-phase] 产出文件：%s" % ", ".join(outputs) if outputs else "无文件产出")

    # 更新状态
    state["last_phase"] = "phase_%s" % phase_num
    save_state(state)

    return 0


def cmd_state_show():
    state = load_state()
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def cmd_state_set(phase):
    state = load_state()
    old = state.get("last_phase")
    state["last_phase"] = phase
    v = save_state(state)
    print("[state] last_phase: %s -> %s (version=%s)" % (old, phase, v))
    return 0


def cmd_verify_sentinel(tc_path, req_path=None, digest_text=None):
    """校验交付摘要粘贴的 sentinel 块哈希：重跑 verify_cases 取真实 digest，比对 hash。
    防模型手编假 sentinel。比对口径与 verify_cases.build_digest_block 一致：
    hash 覆盖 file/n/exit/hard/summary，改任一项都会使 hash 失配。

    跨平台要点：digest JSON 含中文，**经 stdin 读取**（不经 sys.argv，避免 Windows
    cp936 把 argv 中文乱码）。调用方：echo '<json>' | run_phase.py verify <TC.md> [REQ.md]"""
    if digest_text is None:
        digest_text = sys.stdin.read()
    try:
        pasted = json.loads(digest_text)
    except Exception as e:
        print("[verify] 粘贴块非合法 JSON：%s" % e)
        return 1
    args = [tc_path]
    if req_path:
        args.append(req_path)
    rc, out = _run_verify("verify_cases.py", args)
    real_digest = extract_digest_block(out)
    if not real_digest:
        print("[verify] 重跑未取得 digest 块（verify_cases 输出异常）")
        return 1
    # 比对：n/exit/hard/summary 须全等（hash 是它们的派生，等同比对内容）
    keys_ok = (pasted.get("n") == real_digest.get("n")
              and pasted.get("exit") == real_digest.get("exit")
              and pasted.get("hard") == real_digest.get("hard")
              and pasted.get("summary") == real_digest.get("summary"))
    if keys_ok and pasted.get("hash") == real_digest.get("hash"):
        print("[verify] OK：粘贴块哈希与脚本重算一致（exit=%s, n=%s, hash=%s）" % (
            real_digest.get("exit"), real_digest.get("n"), real_digest.get("hash")))
        return 0
    print("[verify] 不一致：粘贴 n=%s/exit=%s/hash=%s，真实 n=%s/exit=%s/hash=%s（疑似手编/篡改）" % (
        pasted.get("n"), pasted.get("exit"), pasted.get("hash"),
        real_digest.get("n"), real_digest.get("exit"), real_digest.get("hash")))
    return 1


def cmd_summary():
    """打印 .gate_log 全部 sentinel，供交付前核对门禁是否齐全。"""
    if not os.path.exists(GATE_LOG):
        print("[summary] .gate_log 不存在（无门禁记录）")
        return 1
    with open(GATE_LOG, "r", encoding="utf-8") as f:
        lines = f.readlines()
    print("===== .gate_log sentinel 全量 =====")
    for i, ln in enumerate(lines, 1):
        print("#%d  %s" % (i, ln.rstrip("\n")))
    print("==================================")
    print("核对：gate8(第8出口) + readback(第13回读) 各至少 1 条且 exit=0；"
          "check-new-file 无 UNEXPECTED_NEW_FILE；REQ 无 REQ_MISSING/REQ_NO_HEADINGS。")
    return 0


def main():
    if len(sys.argv) < 2:
        print("用法: python run_phase.py <子命令> [参数]")
        print("子命令:")
        print("  gate8 <TC.md> [REQ.md]           # 第8阶段出口 gate（写前内存内）")
        print("  readback <TC.md> [REQ.md]        # 第13阶段回读（verify_md + verify_cases）")
        print("  gate-phase <phase> <outputs>     # 阶段门禁：验证产出物并写入签名")
        print("  check-new-file <文件名>           # 核对该文件名 ∈ MANIFEST")
        print("  state show                       # 打印当前 .phase_state.json")
        print("  state set <phase>                # 更新 last_phase")
        print("  verify <TC.md> [REQ.md]          # 校验交付摘要粘贴的 sentinel 块哈希")
        print("  summary                          # 打印 .gate_log 全部 sentinel")
        return 1
    sub = sys.argv[1]
    if sub == "gate8":
        if len(sys.argv) < 3:
            print("用法: run_phase.py gate8 <TC.md> [REQ.md]")
            return 1
        return cmd_gate8(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    if sub == "readback":
        if len(sys.argv) < 3:
            print("用法: run_phase.py readback <TC.md> [REQ.md]")
            return 1
        return cmd_readback(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    if sub == "gate-phase":
        if len(sys.argv) < 3:
            print("用法: run_phase.py gate-phase <phase> [outputs]")
            print("  phase: 阶段编号（如 0, 1, 8）")
            print("  outputs: 产出文件列表（逗号分隔），如 MANIFEST.md,REQ_001.md")
            return 1
        phase_num = int(sys.argv[2])
        outputs_str = sys.argv[3] if len(sys.argv) > 3 else None
        return cmd_gate_phase(phase_num, outputs_str)
    if sub == "check-new-file":
        if len(sys.argv) < 3:
            print("用法: run_phase.py check-new-file <文件名>")
            return 1
        return cmd_check_new_file(sys.argv[2])
    if sub == "state":
        if len(sys.argv) < 3:
            print("用法: run_phase.py state show | state set <phase>")
            return 1
        if sys.argv[2] == "show":
            return cmd_state_show()
        if sys.argv[2] == "set":
            if len(sys.argv) < 4:
                print("用法: run_phase.py state set <phase>")
                return 1
            return cmd_state_set(sys.argv[3])
        print("未知 state 子命令：%s" % sys.argv[2])
        return 1
    if sub == "verify":
        if len(sys.argv) < 3:
            print("用法: echo '<digestJSON>' | run_phase.py verify <TC.md> [REQ.md]")
            print("  （digest 经 stdin 读，避免 Windows cp936 把 argv 中文乱码）")
            return 1
        return cmd_verify_sentinel(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    if sub == "summary":
        return cmd_summary()
    print("未知子命令：%s" % sub)
    return 1


if __name__ == "__main__":
    sys.exit(main())
