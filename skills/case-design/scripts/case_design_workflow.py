#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_design_workflow.py — 脚本驱动的测试用例设计流程

设计动机：
  原 skill 完全依赖模型自觉执行 15 阶段流程，弱模型会跳阶段。
  本脚本作为"流程指挥官"，强制执行阶段顺序：
  - 脚本决定当前阶段、检查产出物、运行门禁
  - 模型只需按脚本指令执行当前阶段
  - 跳阶段 = 脚本拒绝执行

工作方式：
  1. 模型调用：python scripts/case_design_workflow.py <需求文档路径>
  2. 脚本检测当前状态，打印"请执行 Phase N：XXX"
  3. 模型执行，脚本等待用户确认或自动检测产出物
  4. 产出物就绪后，脚本运行 gate-phase N
  5. 门禁通过，进入下一阶段
  6. 直到 Phase 15 完成

阶段产出物：
  Phase 0: case-design-out/MANIFEST.md, case-design-out/REQ_*.md（签名须含 REQ）
  Phase 1: case-design-out/Clarification_Ledger_*.md
  Phase 2-7: case-design-out/.phase_digest_<N>.md（内存阶段可哈希摘要，不再签空串）
  Phase 8: case-design-out/TestCases_*.md + gate8（驱动器强制 gate8 exit=0 才放行）
  Phase 9-12: 内存处理（签空串）
  Phase 13: 最终 Write + readback（驱动器强制 readback exit=0 才放行）
  Phase 14: 人工审核（暂停等待用户）
  Phase 15: Excel 生成

退出码：
  0 = 当前阶段完成，可继续
  1 = 错误/门禁失败
  2 = 等待用户/模型执行

用法：
  python scripts/case_design_workflow.py start <需求文档路径>
  python scripts/case_design_workflow.py status
  python scripts/case_design_workflow.py next
  python scripts/case_design_workflow.py gate <phase>
"""
import sys
import os
import json
import glob
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPTS_DIR)
PROJECT_ROOT = os.getcwd()
OUT_DIR = os.path.join(PROJECT_ROOT, "case-design-out")
STATE_FILE = os.path.join(OUT_DIR, ".workflow_state.json")
PHASE_STATE_FILE = os.path.join(OUT_DIR, ".phase_state.json")
SIGNATURES_FILE = os.path.join(OUT_DIR, ".phase_signatures.json")


def ensure_out_dir():
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR, exist_ok=True)


def load_workflow_state():
    """加载工作流状态：{phase: 当前阶段, req_doc: 需求文档路径, req_id: 需求标识}"""
    if not os.path.exists(STATE_FILE):
        return {"phase": 0, "req_doc": None, "req_id": None}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"phase": 0, "req_doc": None, "req_id": None}


def save_workflow_state(state):
    ensure_out_dir()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def run_gate_phase(phase, outputs):
    """调用 run_phase.py gate-phase。返回 (ok, output)。"""
    import subprocess
    script = os.path.join(SCRIPTS_DIR, "run_phase.py")
    outputs_str = ",".join(outputs) if outputs else ""
    cmd = [sys.executable, script, "gate-phase", str(phase), outputs_str]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def find_req_files():
    """查找 case-design-out/REQ_*.md 文件。"""
    pattern = os.path.join(OUT_DIR, "REQ_*.md")
    return glob.glob(pattern)


def find_clarification_files():
    """查找 case-design-out/Clarification_Ledger_*.md 文件。"""
    pattern = os.path.join(OUT_DIR, "Clarification_Ledger_*.md")
    return glob.glob(pattern)


def find_testcases_files():
    """查找 case-design-out/TestCases_*.md 文件。"""
    pattern = os.path.join(OUT_DIR, "TestCases_*.md")
    return glob.glob(pattern)


def req_file_path():
    """返回首个 case-design-out/REQ_*.md 的完整路径，无则 None。"""
    files = find_req_files()
    return files[0] if files else None


def testcases_file_path():
    """返回首个 case-design-out/TestCases_*.md 的完整路径，无则 None。"""
    files = find_testcases_files()
    return files[0] if files else None


def _run_run_phase(subcmd, tc_path, req_path=None):
    """调用 run_phase.py <subcmd> <TC.md> [REQ.md]，返回 (exit_code, combined_output)。"""
    import subprocess
    script = os.path.join(SCRIPTS_DIR, "run_phase.py")
    cmd = [sys.executable, script, subcmd, tc_path]
    if req_path:
        cmd.append(req_path)
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def run_gate8(tc_path, req_path=None):
    """第8出口门禁：verify_cases 全量校验。返回 (exit_code, output)。"""
    return _run_run_phase("gate8", tc_path, req_path)


def run_readback(tc_path, req_path=None):
    """第13回读：verify_md + verify_cases 文件入口串联。返回 (exit_code, output)。"""
    return _run_run_phase("readback", tc_path, req_path)


def resolve_outputs(phase):
    """解析某阶段门禁须校验存在性的产出文件列表（相对 case-design-out/ 的文件名）。

    Phase 0: MANIFEST.md + REQ_<id>.md（动态）
    Phase 1: Clarification_Ledger_<id>.md（动态）
    Phase 2-7: .phase_digest_<phase>.md（内存阶段可哈希摘要，闭合"签空串"洞）
    Phase 8/13: TestCases_<id>.md（动态）
    Phase 9-12: []（纯内存，无文件产出，签空串）
    """
    if phase == 0:
        outs = ["MANIFEST.md"]
        req = req_file_path()
        if req:
            outs.append(os.path.basename(req))
        return outs
    if phase == 1:
        return [os.path.basename(f) for f in find_clarification_files()]
    if 2 <= phase <= 7:
        return [".phase_digest_%s.md" % phase]
    if phase in (8, 13):
        return [os.path.basename(f) for f in find_testcases_files()]
    return []


def extract_req_id(req_doc_path):
    """从需求文档路径提取需求标识。"""
    basename = os.path.basename(req_doc_path)
    # 去掉扩展名
    name = os.path.splitext(basename)[0]
    # 简单清理：去掉特殊字符
    import re
    name = re.sub(r'[\\/*?:"<>|]', '_', name)
    return name


# ===== 阶段指令 =====

PHASE_INSTRUCTIONS = {
    0: {
        "name": "需求定位",
        "instruction": "创建 case-design-out/ 目录，写入 MANIFEST.md 和 REQ_<需求标识>.md（REQ 为 #4/#5 反向追溯基准，须含 ## 二级标题）",
        "outputs": [],  # 动态：MANIFEST.md + REQ_<id>.md（见 resolve_outputs）
        "model_action": "请创建输出目录与索引 MANIFEST.md，将需求文档落盘为 case-design-out/REQ_<需求标识>.md（含 ## 二级标题），运行 index_req 生成 .index.json",
        "check": lambda: os.path.exists(os.path.join(OUT_DIR, "MANIFEST.md")) and req_file_path() is not None
    },
    1: {
        "name": "需求澄清",
        "instruction": "分析需求文档，输出澄清台账，提问待确认项",
        "outputs": [],  # 动态获取
        "ref": "references/clarification.md",
        "model_action": "请阅读 references/clarification.md，分析需求文档，输出澄清台账到 case-design-out/Clarification_Ledger_<需求标识>.md",
        "check": lambda: len(find_clarification_files()) > 0
    },
    2: {
        "name": "测试需求分析",
        "instruction": "提取测试需求，维度见 references/coverage.md",
        "outputs": [],
        "ref": "references/coverage.md",
        "model_action": "请阅读 references/coverage.md，进行测试需求分析，将本阶段产出摘要落盘 case-design-out/.phase_digest_2.md（≥1 段，含维度/测试需求清单）",
        "check": lambda: os.path.exists(os.path.join(OUT_DIR, ".phase_digest_2.md"))
    },
    3: {
        "name": "规则建模",
        "instruction": "建立业务规则模型，详见 references/modeling.md",
        "outputs": [],
        "ref": "references/modeling.md",
        "model_action": "请阅读 references/modeling.md §规则建模，建立规则模型，将产出摘要落盘 case-design-out/.phase_digest_3.md（含规则项 R<序号> 与来源）",
        "check": lambda: os.path.exists(os.path.join(OUT_DIR, ".phase_digest_3.md"))
    },
    4: {
        "name": "规格建模",
        "instruction": "建立规格模型（SDD），详见 references/modeling.md",
        "outputs": [],
        "ref": "references/modeling.md",
        "model_action": "请阅读 references/modeling.md §规格建模，建立状态/异常/契约模型，将产出摘要落盘 case-design-out/.phase_digest_4.md",
        "check": lambda: os.path.exists(os.path.join(OUT_DIR, ".phase_digest_4.md"))
    },
    5: {
        "name": "风险分析",
        "instruction": "识别风险，产出 P0-P3 优先级，详见 references/risk.md",
        "outputs": [],
        "ref": "references/risk.md",
        "model_action": "请阅读 references/risk.md，进行风险分析，将 P0-P3 风险清单摘要落盘 case-design-out/.phase_digest_5.md",
        "check": lambda: os.path.exists(os.path.join(OUT_DIR, ".phase_digest_5.md"))
    },
    6: {
        "name": "测试策略匹配",
        "instruction": "选择测试方法，决策表见 references/methods.md",
        "outputs": [],
        "ref": "references/methods.md",
        "model_action": "请阅读 references/methods.md，匹配测试策略，将方法→用例映射摘要落盘 case-design-out/.phase_digest_6.md",
        "check": lambda: os.path.exists(os.path.join(OUT_DIR, ".phase_digest_6.md"))
    },
    7: {
        "name": "测试点建模",
        "instruction": "设计测试点，维度见 references/coverage.md",
        "outputs": [],
        "ref": "references/coverage.md",
        "model_action": "请阅读 references/coverage.md，设计测试点，将测试点清单摘要落盘 case-design-out/.phase_digest_7.md",
        "check": lambda: os.path.exists(os.path.join(OUT_DIR, ".phase_digest_7.md"))
    },
    8: {
        "name": "测试用例生成",
        "instruction": "生成测试用例，运行 gate8，详见 references/modeling.md",
        "outputs": [],  # 动态获取
        "ref": "references/modeling.md",
        "model_action": "请阅读 references/modeling.md §用例生成，生成测试用例。完成后运行 gate8（驱动器将强制 gate8 exit=0 才放行）",
        "check": lambda: len(find_testcases_files()) > 0
    },
    9: {
        "name": "去重",
        "instruction": "去重测试用例，详见 references/dedup_coverage.md",
        "outputs": [],
        "ref": "references/dedup_coverage.md",
        "model_action": "请阅读 references/dedup_coverage.md，去除重复用例，将去重结果落盘 case-design-out/.phase_digest_9.md（含去重记录：哪些用例被合并/删除）",
        "check": lambda: os.path.exists(os.path.join(OUT_DIR, ".phase_digest_9.md"))
    },
    10: {
        "name": "覆盖率校验",
        "instruction": "校验覆盖率，详见 references/dedup_coverage.md",
        "outputs": [],
        "ref": "references/dedup_coverage.md",
        "model_action": "请阅读 references/dedup_coverage.md，校验覆盖率和反向追溯，将覆盖结果落盘 case-design-out/.phase_digest_10.md（含覆盖率/追溯结论）",
        "check": lambda: os.path.exists(os.path.join(OUT_DIR, ".phase_digest_10.md"))
    },
    11: {
        "name": "输出前自查",
        "instruction": "15项自查，详见 references/selfcheck.md",
        "outputs": [],
        "ref": "references/selfcheck.md",
        "model_action": "请阅读 references/selfcheck.md，执行15项自查，将自查结果落盘 case-design-out/.phase_digest_11.md（含检查1..检查15 逐项结论）",
        "check": lambda: os.path.exists(os.path.join(OUT_DIR, ".phase_digest_11.md"))
    },
    12: {
        "name": "用例展示",
        "instruction": "在对话中展示用例投影和覆盖矩阵",
        "outputs": [],
        "model_action": "请在对话中展示测试用例摘要和覆盖矩阵，并将展示摘要落盘 case-design-out/.phase_digest_12.md（含展示/投影/矩阵记录）",
        "check": lambda: os.path.exists(os.path.join(OUT_DIR, ".phase_digest_12.md"))
    },
    13: {
        "name": "最终输出",
        "instruction": "写入测试用例文件",
        "outputs": [],  # 动态获取
        "ref": "references/output_write.md",
        "model_action": "请阅读 references/output_write.md，将测试用例写入 case-design-out/TestCases_<需求标识>.md（15 列标准表头，首列用例ID）。harness 会在写前内存内跑 gate8 校验，不过会拦。",
        "check": lambda: len(find_testcases_files()) > 0
    },
    14: {
        "name": "人工审核",
        "instruction": "等待人工审核通过",
        "outputs": [],
        "ref": "references/review_gate.md",
        "model_action": "测试用例已生成，请用户审核。审核通过后回复'审核通过'继续",
        "check": None,  # 需要用户确认
        "requires_user": True
    },
    15: {
        "name": "Excel生成",
        "instruction": "生成Excel文件，详见 references/excel.md",
        "outputs": [],
        "ref": "references/excel.md",
        "model_action": "请阅读 references/excel.md，生成Excel文件",
        "check": None
    }
}


def cmd_start(req_doc_path):
    """启动工作流。"""
    ensure_out_dir()

    # 检查需求文档是否存在
    if not os.path.exists(req_doc_path):
        print(f"[workflow] 错误：需求文档不存在: {req_doc_path}")
        return 1

    # 提取需求标识
    req_id = extract_req_id(req_doc_path)

    # 保存状态
    state = {
        "phase": 0,
        "req_doc": req_doc_path,
        "req_id": req_id
    }
    save_workflow_state(state)

    print(f"[workflow] 启动测试用例设计流程")
    print(f"[workflow] 需求文档: {req_doc_path}")
    print(f"[workflow] 需求标识: {req_id}")
    print()

    # 执行 Phase 0
    return cmd_next()


def cmd_status():
    """显示当前状态。"""
    state = load_workflow_state()
    phase = state.get("phase", 0)
    req_id = state.get("req_id", "未设置")

    print(f"[workflow] 当前阶段: Phase {phase}")
    print(f"[workflow] 需求标识: {req_id}")
    print()

    # 显示阶段指令
    if phase in PHASE_INSTRUCTIONS:
        info = PHASE_INSTRUCTIONS[phase]
        print(f"阶段名称: {info['name']}")
        print(f"阶段说明: {info['instruction']}")
        if 'ref' in info:
            print(f"参考文档: {info['ref']}")
        print()
        print(f"【模型行动】{info['model_action']}")

    return 0


def cmd_next():
    """推进到下一阶段。"""
    state = load_workflow_state()
    phase = state.get("phase", 0)

    if phase > 15:
        print("[workflow] 流程已完成")
        return 0

    info = PHASE_INSTRUCTIONS.get(phase)
    if not info:
        print(f"[workflow] 未知阶段: {phase}")
        return 1

    print(f"[workflow] ===== Phase {phase}: {info['name']} =====")
    print()
    print(f"【阶段说明】{info['instruction']}")
    if 'ref' in info:
        print(f"【参考文档】{info['ref']}")
    print()
    print(f"【模型行动】{info['model_action']}")
    print()

    # 检查产出物（如果有）
    if info.get('check') and not info['check']():
        print("[workflow] ⚠️  产出物未就绪，请先完成当前阶段")
        return 2

    # 解析本阶段门禁须校验存在性的产出文件（动态）
    outputs = resolve_outputs(phase)

    # Phase 2-7：内存阶段须有 .phase_digest_N.md 可哈希产物（闭合"签空串"洞）
    # Phase 0/1/8/13：文件产出阶段
    if outputs:
        print(f"[workflow] 运行门禁: gate-phase {phase}（校验产出：{', '.join(outputs)}）")
        ok, out = run_gate_phase(phase, outputs)
        if ok:
            print("[workflow] ✅ 阶段门禁通过")
        else:
            print(out)
            print("[workflow] ❌ 阶段门禁失败，请检查产出物")
            return 1

    # ===== 内容门禁（驱动器强制，闭合 v0.7.4"驱动器跳过 gate8/readback"洞） =====
    if phase == 8:
        # 第8出口：verify_cases 全量校验须 exit=0 才放行
        tc = testcases_file_path()
        req = req_file_path()
        if not tc:
            print("[workflow] ❌ Phase 8 缺少 TestCases_*.md，无法运行 gate8")
            return 1
        print(f"[workflow] 运行第8出口门禁: gate8（verify_cases 全量校验）")
        rc, out = run_gate8(tc, req)
        print(out)
        if rc != 0:
            print("[workflow] ❌ gate8 未通过（exit=%s），禁止推进到 Phase 9" % rc)
            print("[workflow] 修复：按 verify_cases 输出修正 TestCases 后重跑 `python scripts/case_design_workflow.py next`")
            return 1
        print("[workflow] ✅ gate8 通过（exit=0）")

    if phase == 13:
        # 第13回读：verify_md + verify_cases 文件入口串联须 exit=0 才放行
        tc = testcases_file_path()
        req = req_file_path()
        if not tc:
            print("[workflow] ❌ Phase 13 缺少 TestCases_*.md，无法运行 readback")
            return 1
        print(f"[workflow] 运行第13回读门禁: readback（verify_md + verify_cases）")
        rc, out = run_readback(tc, req)
        print(out)
        if rc != 0:
            print("[workflow] ❌ readback 未通过（exit=%s），禁止推进到 Phase 14" % rc)
            print("[workflow] 修复：按 verify_md/verify_cases 输出修正 TestCases 后重跑 `python scripts/case_design_workflow.py next`")
            return 1
        print("[workflow] ✅ readback 通过（exit=0）")

    # 更新阶段
    state['phase'] = phase + 1
    save_workflow_state(state)

    print()
    print(f"[workflow] Phase {phase} 完成，进入 Phase {phase + 1}")

    # 如果还有下一阶段，继续提示
    if state['phase'] <= 15:
        next_info = PHASE_INSTRUCTIONS.get(state['phase'])
        if next_info:
            print()
            print(f"下一阶段: Phase {state['phase']} - {next_info['name']}")
            print(f"【行动】{next_info['model_action']}")

    return 0


def cmd_gate(phase):
    """手动运行门禁。"""
    print(f"[workflow] 运行 gate-phase {phase}")
    ok, out = run_gate_phase(phase, resolve_outputs(phase))
    if ok:
        print("[workflow] ✅ 门禁通过")
        return 0
    else:
        print(out)
        print("[workflow] ❌ 门禁失败")
        return 1


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python scripts/case_design_workflow.py start <需求文档路径>")
        print("  python scripts/case_design_workflow.py status")
        print("  python scripts/case_design_workflow.py next")
        print("  python scripts/case_design_workflow.py gate <phase>")
        return 1

    cmd = sys.argv[1]

    if cmd == "start":
        if len(sys.argv) < 3:
            print("用法: python scripts/case_design_workflow.py start <需求文档路径>")
            return 1
        return cmd_start(sys.argv[2])

    elif cmd == "status":
        return cmd_status()

    elif cmd == "next":
        return cmd_next()

    elif cmd == "gate":
        if len(sys.argv) < 3:
            print("用法: python scripts/case_design_workflow.py gate <phase>")
            return 1
        return cmd_gate(int(sys.argv[2]))

    else:
        print(f"未知命令: {cmd}")
        return 1


if __name__ == "__main__":
    sys.exit(main())