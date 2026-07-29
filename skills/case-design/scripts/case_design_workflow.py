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
  Phase 0: case-design-out/MANIFEST.md, case-design-out/REQ_*.md
  Phase 1: case-design-out/Clarification_Ledger_*.md
  Phase 2-7: 内存中（签空串）
  Phase 8: case-design-out/TestCases_*.md（需 gate8）
  Phase 9-12: 内存处理
  Phase 13: 最终 Write
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
    """调用 run_phase.py gate-phase。返回 True=成功。"""
    import subprocess
    script = os.path.join(SCRIPTS_DIR, "run_phase.py")
    outputs_str = ",".join(outputs) if outputs else ""
    cmd = [sys.executable, script, "gate-phase", str(phase), outputs_str]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return result.returncode == 0


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
        "instruction": "创建 case-design-out/ 目录，写入 MANIFEST.md 和 REQ_<需求标识>.md",
        "outputs": ["MANIFEST.md"],
        "model_action": "请创建输出目录和索引文件。将需求文档内容写入 case-design-out/REQ_<需求标识>.md",
        "check": lambda: os.path.exists(os.path.join(OUT_DIR, "MANIFEST.md"))
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
        "model_action": "请阅读 references/coverage.md，进行测试需求分析（内存操作，无需写文件）",
        "check": None  # 内存阶段
    },
    3: {
        "name": "规则建模",
        "instruction": "建立业务规则模型，详见 references/modeling.md",
        "outputs": [],
        "ref": "references/modeling.md",
        "model_action": "请阅读 references/modeling.md §规则建模，建立规则模型（内存操作）",
        "check": None
    },
    4: {
        "name": "规格建模",
        "instruction": "建立规格模型（SDD），详见 references/modeling.md",
        "outputs": [],
        "ref": "references/modeling.md",
        "model_action": "请阅读 references/modeling.md §规格建模，建立状态/异常/契约模型（内存操作）",
        "check": None
    },
    5: {
        "name": "风险分析",
        "instruction": "识别风险，产出 P0-P3 优先级，详见 references/risk.md",
        "outputs": [],
        "ref": "references/risk.md",
        "model_action": "请阅读 references/risk.md，进行风险分析，产出 P0-P3 风险清单（内存操作）",
        "check": None
    },
    6: {
        "name": "测试策略匹配",
        "instruction": "选择测试方法，决策表见 references/methods.md",
        "outputs": [],
        "ref": "references/methods.md",
        "model_action": "请阅读 references/methods.md，匹配测试策略（内存操作）",
        "check": None
    },
    7: {
        "name": "测试点建模",
        "instruction": "设计测试点，维度见 references/coverage.md",
        "outputs": [],
        "ref": "references/coverage.md",
        "model_action": "请阅读 references/coverage.md，设计测试点（内存操作）",
        "check": None
    },
    8: {
        "name": "测试用例生成",
        "instruction": "生成测试用例，运行 gate8，详见 references/modeling.md",
        "outputs": [],  # 动态获取
        "ref": "references/modeling.md",
        "model_action": "请阅读 references/modeling.md §用例生成，生成测试用例。完成后运行 gate8",
        "check": lambda: len(find_testcases_files()) > 0
    },
    9: {
        "name": "去重",
        "instruction": "去重测试用例，详见 references/dedup_coverage.md",
        "outputs": [],
        "ref": "references/dedup_coverage.md",
        "model_action": "请阅读 references/dedup_coverage.md，去除重复用例",
        "check": None
    },
    10: {
        "name": "覆盖率校验",
        "instruction": "校验覆盖率，详见 references/dedup_coverage.md",
        "outputs": [],
        "ref": "references/dedup_coverage.md",
        "model_action": "请阅读 references/dedup_coverage.md，校验覆盖率和反向追溯",
        "check": None
    },
    11: {
        "name": "输出前自查",
        "instruction": "15项自查，详见 references/selfcheck.md",
        "outputs": [],
        "ref": "references/selfcheck.md",
        "model_action": "请阅读 references/selfcheck.md，执行15项自查",
        "check": None
    },
    12: {
        "name": "用例展示",
        "instruction": "在对话中展示用例投影和覆盖矩阵",
        "outputs": [],
        "model_action": "请在对话中展示测试用例摘要和覆盖矩阵（不写文件）",
        "check": None
    },
    13: {
        "name": "最终输出",
        "instruction": "写入测试用例文件",
        "outputs": [],  # 动态获取
        "ref": "references/output_write.md",
        "model_action": "请阅读 references/output_write.md，将测试用例写入 case-design-out/TestCases_<需求标识>.md",
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

    # 运行门禁（内存阶段签空串）
    outputs = info.get('outputs', [])
    if phase >= 2 and phase <= 7:
        # 内存阶段
        pass
    elif phase == 1:
        # Phase 1 需要澄清台账
        clarification_files = find_clarification_files()
        if clarification_files:
            outputs = [os.path.basename(f) for f in clarification_files]
    elif phase == 8:
        # Phase 8 需要 TestCases
        testcases_files = find_testcases_files()
        if testcases_files:
            outputs = [os.path.basename(f) for f in testcases_files]

    if outputs or (phase >= 2 and phase <= 7):
        print(f"[workflow] 运行门禁: gate-phase {phase}")
        if run_gate_phase(phase, outputs):
            print("[workflow] ✅ 门禁通过")
        else:
            print("[workflow] ❌ 门禁失败，请检查产出物")
            return 1

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
    if run_gate_phase(phase, []):
        print("[workflow] ✅ 门禁通过")
        return 0
    else:
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