#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
phases.py — qamaster case-design 0-14(+Excel) 阶段注册表（流程定义单一事实源）

把 SKILL.md 的 15 阶段主流程（第0~15阶段）固化为状态机。编号沿用 ch23 权威编号：
  0 需求定位(MANIFEST)      — references/phase0_manifest.md
  1 需求分析+澄清(人工确认)  — references/clarification.md
  2 测试需求分析             — references/coverage.md
  3 规则建模(出口gate)       — references/modeling.md
  4 规格建模 SDD             — references/modeling.md
  5 风险分析(出口gate)       — references/risk.md
  6 测试策略匹配             — references/methods.md
  7 测试点建模               — references/coverage.md
  8 用例生成                 — references/modeling.md/quality_rules.md
  9 去重                     — references/dedup_coverage.md
  10 覆盖率校验+反向追溯     — references/dedup_coverage.md
  11 输出前自查(15项)        — references/selfcheck.md
  12 对话展示投影            — references/output_write.md
  13 一次性写盘+脚本回读     — references/output_write.md
  14 人工审核门禁(人工确认)  — references/review_gate.md
  15 Excel 生成(许可门)      — references/excel.md

人工审核通过后的知识沉淀（references/knowledge.md）作为 Phase14 confirm 通过后的
后置动作 POST_CONFIRM_KNOWLEDGE 执行（不占阶段号，保持与 SKILL.md 编号体系一致）。

gate 取值：
  auto     — 自动门：产物达标即放行（gate_checks 全部通过）
  confirm  — 人工确认门：完整模式必须用户 confirm；连跑/轻量可按 SKILL.md 6.5 自动放行（REVIEW_PENDING）
  license  — 许可门：默认需用户许可；连跑/轻量且用户已声明要 Excel 时自动放行

裁剪（与 phase0_manifest.md 步骤五 / dedup_coverage.md ch26 一致）：
  heavy  — 全阶段
  medium — 合并建模（裁剪 phase 4）
  light  — 裁剪 phase 3/4/10（保留澄清/用例/自查/审核门禁；P0 风险强制 heavy 由模型在 Phase0 判定）
"""
from state_store import PHASE_KINDS  # noqa: F401  (re-export, 供调用方校验)

POST_CONFIRM_KNOWLEDGE = "knowledge"   # Phase14 审核通过后的知识沉淀后置动作标记

PHASES = [
    {
        "id": 0, "name": "需求定位与输入分析", "gate": "auto",
        "refs": ["references/phase0_manifest.md"],
        "objective": "读 MANIFEST 索引定位需求、需求文档强制落盘 REQ_<需求标识>.md、判定需求规模(重/中/轻)与输入形态(纯需求/契约驱动)、确定运行模式。",
        "allowed": [
            "读取 case-design-out/MANIFEST.md（不存在则按需创建目录与空索引）",
            "将用户需求文档落盘为 case-design-out/REQ_<需求标识>.md（纯散文须补 ## 二级标题分节）",
            "已有需求匹配成功时整表更新索引状态=进行中",
            "向用户复述判定结论：需求标识/规模分级/运行模式/输入形态（不调 set 由 Runtime 记录）",
        ],
        "forbidden": ["逐一扫描所有文件定位需求", "跳过 REQ 落盘直接进入澄清", "生成任何测试用例"],
        "produces": ["case-design-out/REQ_<需求标识>.md", "case-design-out/MANIFEST.md"],
        "exit_condition": "REQ 文件与索引文件均存在于磁盘（Runtime 机器判定）",
        "gate_checks": [
            {"kind": "exists_any", "patterns": ["case-design-out/REQ_*.md"], "label": "需求文档已落盘"},
            {"kind": "exists", "path": "case-design-out/MANIFEST.md", "label": "索引文件存在"},
            # v0.8.0: 设计文档存在性校验（optional——仅当用户提供【设计文档】时才校验；
            # runtime 探测 SKILL.md §5【设计文档】输入标记，无则 SKIP，不阻断纯需求驱动流程）
            {"kind": "exists_any", "patterns": ["case-design-out/DESIGN_*.md"], "label": "设计文档已落盘（如提供·#8-H 追溯基准）", "optional": True},
        ],
        "produces": ["case-design-out/REQ_<需求标识>.md", "case-design-out/DESIGN_<需求标识>.md（如提供）", "case-design-out/MANIFEST.md"],
    },
    {
        "id": 1, "name": "需求分析与澄清", "gate": "confirm",
        "refs": ["references/clarification.md"],
        "objective": "Gap Analysis 识别规则/状态/权限/数据/异常/依赖缺口，输出【待确认问题与假设清单】，落盘澄清台账。",
        "allowed": [
            "先读台账（存在则）→ 仅对台账未覆盖缺口提问（角色路由 @开发/@产品/@业务）",
            "按风险分级：P0/P1 阻断等待；连跑/轻量 P2/P3 登记假设继续",
            "用户答复后立即整表写回 case-design-out/Clarification_Ledger_<需求标识>.md",
            "新需求台账生成后整表新增 MANIFEST 索引条目（status=进行中，路径确定性填全）",
        ],
        "forbidden": ["重复提问台账已解决项", "台账只存上下文不落盘", "存在 P0/P1 未关闭缺口时推进（完整/连跑模式）"],
        "produces": ["case-design-out/Clarification_Ledger_<需求标识>.md"],
        "exit_condition": "台账已落盘且 P0/P1 缺口全部关闭（完整模式 P2/P3 亦须关闭）",
        "gate_checks": [],
    },
    {
        "id": 2, "name": "测试需求分析", "gate": "auto",
        "refs": ["references/coverage.md"],
        "objective": "按覆盖矩阵提取正常/异常/组合/跨需求/上下游等测试需求维度，形成测试需求分析结论（内存沉淀，供后续阶段使用）。",
        "allowed": ["按 references/coverage.md 8.x 矩阵分析测试需求维度", "输出测试需求分析摘要（调试模式可见）"],
        "forbidden": ["直接编写测试用例", "跳过需求覆盖矩阵"],
        "produces": [],
        "exit_condition": "测试需求维度分析完成（与台账/需求一致），Runtime 记录通过",
        "gate_checks": [],
    },
    {
        "id": 3, "name": "规则建模", "gate": "auto",
        "refs": ["references/modeling.md"],
        "objective": "沉淀规则建模清单，每条规则标注来源 [来源:需求文档<章节>/台账Q<n>/假设A<n>]，出口机器 gate 校验规则来源 + R 编号连续性。",
        "allowed": ["建立规则建模清单（内存，后续沉淀为 TestCases .md 的 section）", "每条规则项标注来源", "本阶段结束写检查点 case-design-out/.runtime/checkpoint_3.md 供 runtime gate 校验"],
        "forbidden": ["无来源标记的规则项静默保留（须转问题/假设）", "脑补业务规则"],
        "produces": [],
        "exit_condition": "规则清单全部带来源标注 + R 编号连续不跳号（本阶段不写最终文件，由 Phase13 统一沉淀落盘）",
        "gate_checks": [
            {"kind": "phase_gate", "phase": 3, "label": "规则来源+R连续性(项1/2)"},
        ],
        "consumes": ["ledger", "req"],
    },
    {
        "id": 4, "name": "规格建模 SDD", "gate": "auto",
        "refs": ["references/modeling.md"],
        "objective": "Feature/Rule/Constraint/Input/Output/State/Exception/Acceptance 建模；含接口文档时建契约模型+变更影响清单。",
        "allowed": ["按 SDD 八要素建模", "State/Exception/契约标注事实来源由 @开发 校对（完整模式）", "契约驱动分支建变更影响清单"],
        "forbidden": ["跳过规格直接写用例", "杜撰表名/字段名/Redis Key/Topic"],
        "produces": [],
        "exit_condition": "规格建模完成且与规则建模一致（内存产物）",
        "gate_checks": [],
        "consumes": ["3"],
    },
    {
        "id": 5, "name": "风险分析", "gate": "auto",
        "refs": ["references/risk.md"],
        "objective": "三源共验产出 P0-P3 风险清单（含风险来源标注）；出口机器 gate 校验风险来源 + RK 编号连续性 + P0 漏标 critique 循环。",
        "allowed": ["产出风险清单（风险ID/等级/描述/模块/来源）", "技术隐含@开发/业务领域@业务/缺陷反哺来源的风险经台账角色确认（完整模式）", "本阶段结束写检查点 case-design-out/.runtime/checkpoint_5.md 供 runtime gate 校验"],
        "forbidden": ["P0 风险不显式列出", "跳过风险分析直接用例"],
        "produces": [],
        "exit_condition": "风险清单完整含来源 + RK 编号连续不跳号，critique ≤2 轮无新增漏标",
        "gate_checks": [
            {"kind": "phase_gate", "phase": 5, "label": "风险来源+RK连续性(项2)"},
        ],
        "consumes": ["3", "ledger"],
    },
    {
        "id": 6, "name": "测试策略匹配", "gate": "auto",
        "refs": ["references/methods.md"],
        "objective": "对照风险清单按决策表动态匹配方法（等价类/边界值4值/判定表/状态迁移/场景法/错误推测），落地方法→测试类型/维度映射。",
        "allowed": ["按需求特征×风险选择方法组合", "P0 风险强制对应方法（全量穷举）"],
        "forbidden": ["机械套用单一方法", "选了方法不落地到类型/维度列"],
        "produces": [],
        "exit_condition": "方法选择完成且多方法组合（防类型单一化）",
        "gate_checks": [],
        "consumes": ["5"],
    },
    {
        "id": 7, "name": "测试点建模", "gate": "auto",
        "refs": ["references/coverage.md"],
        "objective": "产出测试点清单（测试点ID/场景类型/描述/模块），覆盖主流程/分支/异常/状态/权限/数据一致性/幂等/并发/UI结构；出口机器 gate 校验 TP 编号连续性 + P0/P1 风险→≥1 TP。",
        "allowed": ["按 15.3 维度提取测试点", "测试点清单后续沉淀为 TestCases .md section", "本阶段结束写检查点 case-design-out/.runtime/checkpoint_7.md 供 runtime gate 校验"],
        "forbidden": ["遗漏高风险测试点", "测试点无场景类型标注"],
        "produces": [],
        "exit_condition": "测试点清单完成且覆盖高风险维度 + TP 编号连续不跳号",
        "gate_checks": [
            {"kind": "phase_gate", "phase": 7, "label": "TP连续性+风险→TP(项2)"},
        ],
        "consumes": ["5", "2"],
    },
    {
        "id": 8, "name": "用例生成", "gate": "auto",
        "refs": ["references/modeling.md", "references/quality_rules.md"],
        "objective": "生成全部 Given/When/Then 用例（内存），遵守断言完整性/数据真实/存储保护/方法落地，关联规则列引用 R<n>/TP<n>/API<n>/假设A<n>；出口机器 gate 全量校验 + 反向引用完整性 + 台账传递 + 一致性（消费门禁）。",
        "allowed": ["内存内生成全部用例（不落盘）", "断言可观测且状态变更类双重断言", "关联规则含 ID 引用实现追溯", "本阶段结束写检查点 case-design-out/.runtime/checkpoint_8.md 供 runtime gate 校验"],
        "forbidden": ["脑补无来源业务行为", "模糊断言", "杜撰存储信息", "边生成边写文件", "引用不存在的 R/TP/RK/API（悬空引用）"],
        "produces": [],
        "exit_condition": "全部用例内存生成完毕（写前零文件操作）+ 反向引用完整 + 台账事实传递 + 假设对账",
        "gate_checks": [
            {"kind": "phase_gate", "phase": 8, "label": "全量+引用/消费/一致性/连续性(项1/2/3/4/5)"},
        ],
        "consumes": ["3", "4", "5", "7", "ledger", "req"],
    },
    {
        "id": 9, "name": "去重", "gate": "auto",
        "refs": ["references/dedup_coverage.md"],
        "objective": "按 规则+风险+断言+维度+类型 五者全同才合并；剔除过度设计；保护维度/方法多样性。",
        "allowed": ["内存内合并/剔除", "保留高价值高风险高信息密度用例"],
        "forbidden": ["跨维度/跨类型合并", "以去重为由删除不同方法的边界/异常用例"],
        "produces": [],
        "exit_condition": "去重完成，无五者全同重复",
        "gate_checks": [],
        "consumes": ["8"],
    },
    {
        "id": 10, "name": "覆盖率校验与反向追溯", "gate": "auto",
        "refs": ["references/dedup_coverage.md"],
        "objective": "覆盖率校验 + #4 反向需求追溯 + #5 业务行为来源追溯（契约分支加 #6 接口追溯）+ 台账待确认门禁 + 台账传递；未覆盖/无来源项内存补齐或转问题/假设。",
        "allowed": ["按停止条件收敛（核心规则/高风险/关键状态/核心异常已覆盖即停）", "缺口转待确认问题/假设并回显清单", "本阶段结束写检查点 case-design-out/.runtime/checkpoint_10.md 供 runtime gate 校验"],
        "forbidden": ["为覆盖率而覆盖、无限扩展边缘场景", "REQ 缺失时宣称覆盖率全过", "台账待确认项未闭环即推进"],
        "produces": [],
        "exit_condition": "覆盖缺口闭合或已登记假设 + 台账待确认项已闭环或转假设",
        "gate_checks": [
            {"kind": "phase_gate", "phase": 10, "label": "覆盖硬门+台账门禁(项4)"},
        ],
        "consumes": ["8", "req", "ledger"],
    },
    {
        "id": 11, "name": "输出前自查", "gate": "auto",
        "refs": ["references/selfcheck.md"],
        "objective": "内存内 15 项自查（含检查13断言完整性/检查14对抗生成遍/检查15行为来源追溯），≤3 轮自修；阻断项不过则输出缺口清单停止。",
        "allowed": ["全部自查自修在内存内完成（零文件操作）", "阻断项未过输出【测试设计缺口清单】等待用户"],
        "forbidden": ["批量声明已全部自查通过（声明≠核实）", "跳过对抗生成遍"],
        "produces": [],
        "exit_condition": "自查全部通过 + 写前规模评估完成（单文件/拆PART决策）",
        "gate_checks": [],
    },
    {
        "id": 12, "name": "对话展示投影", "gate": "auto",
        "refs": ["references/output_write.md"],
        "objective": "对话中展示用例紧凑投影（5列）+ 覆盖矩阵，只展示不写文件；随后立即进入 Phase13 写盘（同响应连续完成，不等用户）。",
        "allowed": ["展示投影+覆盖矩阵", "输出【待确认问题与假设清单】回显"],
        "forbidden": ["展示阶段发起任何文件写入", "展示后宣布'下一步将Write'就停顿（评估完立即写盘）"],
        "produces": [],
        "exit_condition": "投影与覆盖矩阵已展示",
        "gate_checks": [],
    },
    {
        "id": 13, "name": "写盘与脚本回读", "gate": "auto",
        "refs": ["references/output_write.md"],
        "objective": "追溯性 section + 15列用例表一次性 Write 落盘 case-design-out/TestCases_<需求标识>.md（默认单文件；超预算按风险拆 PART），verify_md.py + verify_cases.py 回读核对，更新 MANIFEST 进度。",
        "allowed": [
            "每个文件恰好一次 Write（整体创建/覆盖），回读不通过内存修后重新整体 Write（≤2次/文件）",
            "用 python skills/case-design/scripts/verify_md.py + verify_cases.py <TC.md> case-design-out/REQ_<需求标识>.md 串联回读",
            "多 PART 自动续跑（中途不等用户），全部落盘后统一进 Phase14",
            "整表更新 MANIFEST（状态保持进行中 + 实际落盘文件清单）",
        ],
        "forbidden": ["Edit/MultiEdit/append 落盘或补齐", "把整份 .md 用 Read 读回上下文（必须用脚本回读）", "单文件场景写文件调用>2次"],
        "produces": ["case-design-out/TestCases_<需求标识>.md", "case-design-out/MANIFEST.md"],
        "exit_condition": "verify_md.py 结构通过 + verify_cases.py 硬性校验通过（exit=0）",
        "gate_checks": [
            {"kind": "script", "cmd": "python \"{skill_scripts}/verify_md.py\" \"case-design-out/TestCases_{req_id}.md\"", "label": "结构回读(verify_md)"},
            {"kind": "script", "cmd": "python \"{skill_scripts}/verify_cases.py\" \"case-design-out/TestCases_{req_id}.md\" \"case-design-out/REQ_{req_id}.md\" --ledger \"case-design-out/Clarification_Ledger_{req_id}.md\"", "label": "内容回读(verify_cases+台账)"},
            {"kind": "exists", "path": "case-design-out/MANIFEST.md", "label": "索引已更新"},
        ],
        "consumes": ["3", "5", "7", "8", "ledger", "req"],
    },
    {
        "id": 14, "name": "人工审核门禁", "gate": "confirm",
        "refs": ["references/review_gate.md"],
        "objective": "显式提示用户人工审核（覆盖摘要/脚本校验摘要/待确认问题与假设清单/覆盖缺口按实际数值填）；完整模式等待'审核通过'。",
        "allowed": [
            "按 review_gate.md 话术输出审核提示（数值取自 verify_cases.py 回读，禁止只填'通过'）",
            "用户反馈问题 → 按 output_write.md 起点判定重走（Runtime fail 回退到对应阶段）",
            "审核通过后：更新 MANIFEST 状态=已完成 → 生成/更新知识总结 Knowledge_<需求标识>.md（13维度，verify_knowledge.py 校验）",
        ],
        "forbidden": ["默认审核通过", "用户未明确反馈即推进（完整模式）", "审核通过却跳过知识总结", "未经审核直接生成 Excel"],
        "produces": ["case-design-out/Knowledge_<需求标识>.md"],
        "exit_condition": "完整模式：用户 confirm；连跑/轻量：标注待审核自动放行（REVIEW_PENDING）",
        "gate_checks": [],
    },
    {
        "id": 15, "name": "Excel 生成", "gate": "license",
        "refs": ["references/excel.md"],
        "objective": "仅当用户要求 Excel 时：经 scripts/gen_excel.py 脚本产出 .xlsx + 结构验证 + 数据完整性校验；源 .md 为唯一数据源。",
        "allowed": [
            "python skills/case-design/scripts/gen_excel.py case-design-out/TestCases_<需求标识>.md 生成",
            "Excel-only 直通：.md 已存在时先过一致性校验再转换",
            "生成失败显式输出失败报告（依赖缺失尝试安装并兜底报错）",
        ],
        "forbidden": ["用 Write/Edit 直接写 .xlsx", "ad-hoc 即兴 openpyxl 脚本", "口头声明已生成而磁盘无文件"],
        "produces": ["case-design-out/TestCases_<需求标识>.xlsx"],
        "exit_condition": "gen_excel.py exit=0（结构+数据两段校验全过）",
        "gate_checks": [
            {"kind": "script", "cmd": "python \"{skill_scripts}/gen_excel.py\" \"case-design-out/TestCases_{req_id}.md\"", "label": "Excel脚本生成+校验(gen_excel)"},
        ],
    },
]

# 知识沉淀后置动作的门禁（Phase14 confirm 通过后执行）
KNOWLEDGE_GATE = [
    {"kind": "script", "cmd": "python \"{skill_scripts}/verify_knowledge.py\" \"case-design-out/Knowledge_{req_id}.md\"", "label": "知识总结校验(verify_knowledge)"},
]

PHASE_BY_ID = {p["id"]: p for p in PHASES}
LAST_PHASE = PHASES[-1]["id"]

# 流程深度裁剪表（被裁掉的阶段号）
DEPTH_SKIPS = {
    "heavy": [],
    "medium": [4],
    "light": [3, 4, 10],
}


def get_phase(phase_id):
    return PHASE_BY_ID.get(phase_id)


def effective_phases(depth):
    """按流程深度返回应执行的阶段 id 列表（顺序）。"""
    skips = set(DEPTH_SKIPS.get(depth or "heavy", []))
    return [p["id"] for p in PHASES if p["id"] not in skips]


def next_phase_id(current, depth):
    seq = effective_phases(depth)
    if current not in seq:
        return None
    i = seq.index(current)
    return seq[i + 1] if i + 1 < len(seq) else None


def find_phase_by_name(token):
    """按阶段号或中文名模糊定位（供 fail 回退解析）。"""
    token = (token or "").strip()
    if not token:
        return None
    if token.isdigit():
        return PHASE_BY_ID.get(int(token))
    for p in PHASES:
        if token in p["name"]:
            return p
    return None