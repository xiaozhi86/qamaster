# qamaster Agent Runtime Engineering 重构详细设计方案

版本：v1.0.0

## 1. 背景与目标

当前 qamaster Claude Code Plugin 采用 SKILL.md 驱动方式定义 0-14
阶段测试设计流程。该设计理念符合 SDD + TDD + AI Test Factory
思想，但执行依赖模型自身指令遵循能力。

目标：

将 qamaster 从 Prompt Engineering 升级为 Agent Runtime Engineering，使：

-   SKILL.md 定义业务规范
-   Runtime 控制执行流程
-   Workflow Engine 管理阶段状态
-   Quality Gate 控制质量
-   Validator 防止非法跳转
-   Memory 记录企业知识

最终实现：

无论 Claude、GPT、GLM、Gemini、DeepSeek 等模型，均必须按照 0-14
阶段执行。

------------------------------------------------------------------------

# 2. 核心架构变化

## 当前模式

User ↓ Claude Code ↓ Model ↓ SKILL.md ↓ 模型自主执行

问题：

-   模型拥有流程控制权
-   可以跳过阶段
-   可以忽略确认点
-   可以提前输出结果

## 重构模式

User ↓ Claude Code Plugin ↓ qamaster Runtime Controller ↓ Workflow State
Machine ↓ Quality Gate Engine ↓ Phase Executor ↓ LLM Worker

原则：

模型负责思考。 Runtime负责控制。

------------------------------------------------------------------------

# 3. 总体目录设计

    qamaster/

    .claude-plugin/
        plugin.json

    commands/
        case-design.md

    skills/
        case-runtime/

    runtime/

        engine/
            workflow_engine.py
            phase_executor.py
            state_manager.py

        gate/
            quality_gate.py

        validator/
            contract_validator.py

        memory/
            execution_log.py


    workflow/

        case-design-flow.yaml


    state/

        runtime-state.json

------------------------------------------------------------------------

# 4. Runtime Core设计

## 4.1 Workflow Engine

职责：

-   加载流程定义
-   管理当前阶段
-   控制阶段迁移
-   防止非法跳转

状态模型：

``` json
{
 "workflow":"case-design",
 "current_phase":3,
 "completed":[0,1,2],
 "status":"WAIT_CONFIRM"
}
```

------------------------------------------------------------------------

# 5. Phase State Machine

将原SKILL.md 0-14流程转换为状态机。

示例：

    Phase0 输入分析
     |
    Gate
     |
    Phase1 需求澄清
     |
    Human Confirm
     |
    Phase2 规格建模
     |
    Gate
     |
    ...
     |
    Phase14 知识沉淀

禁止：

-   Phase0 -\> Phase8
-   未确认继续执行
-   未产出物进入下一阶段

------------------------------------------------------------------------

# 6. Phase Executor设计

每个阶段独立执行。

输入：

-   当前Phase
-   上阶段输出
-   用户输入

输出：

-   当前阶段产物

执行规则：

    execute_phase()

    1. 检查state
    2. 加载phase skill
    3. 调用模型
    4. 校验输出
    5. 更新state
    6. 进入下一阶段

------------------------------------------------------------------------

# 7. SKILL.md Runtime化改造

SKILL.md不再承担流程控制。

职责：

-   定义业务规则
-   定义输入输出
-   定义质量标准

新增：

## Runtime Contract

包括：

-   当前阶段
-   允许动作
-   禁止动作
-   输出格式
-   验收标准

------------------------------------------------------------------------

# 8. Phase拆分设计

拆分：

    phase00-input-analysis
    phase01-requirement-clarification
    phase02-specification-model
    phase03-test-point-analysis
    phase04-test-case-design
    ...
    phase14-knowledge-evolution

每个Phase：

独立SKILL.md。

优势：

-   降低上下文压力
-   防止模型混淆
-   支持独立升级

------------------------------------------------------------------------

# 9. Quality Gate Engine设计

Gate类型：

## 自动Gate

例如：

检查：

-   文件是否存在
-   字段是否完整
-   格式是否正确

## 人工Gate

例如：

需求澄清完成：

状态：

WAIT_USER_APPROVAL

用户确认：

APPROVE

进入下一阶段。

------------------------------------------------------------------------

# 10. Contract Validator设计

验证：

## 输入约束

例如：

Phase3必须存在：

-   Requirement.md
-   Rule_Model.md

## 输出约束

例如：

测试用例必须包含：

-   前置条件
-   Given
-   When
-   Then
-   验证点

失败：

阻断流程。

------------------------------------------------------------------------

# 11. Model Independent协议

Runtime发送给模型：

    CURRENT PHASE:

    Phase 03 Test Point Analysis


    Allowed:

    - 分析测试点
    - 创建测试模型


    Forbidden:

    - 编写完整测试用例
    - 输出Excel
    - 修改流程状态

模型无法决定下一阶段。

------------------------------------------------------------------------

# 12. Memory系统设计

保存：

-   用户确认记录
-   规则模型
-   决策历史
-   缺陷经验
-   企业测试知识

结构：

    memory/

    decision-log.json
    phase-history.json
    knowledge-base/

------------------------------------------------------------------------

# 13. Claude Code Plugin适配

plugin.json负责：

-   注册plugin
-   注册command
-   注册skill

command：

    /qamaster case-design

实际调用：

    runtime.start("case-design")

------------------------------------------------------------------------

# 14. 企业级增强方向

## Multi-Agent Runtime

增加：

-   BA Agent
-   PM Agent
-   QA Agent
-   Architect Agent
-   Risk Agent

由Runtime调度。

------------------------------------------------------------------------

## Observability

增加：

-   执行日志
-   阶段耗时
-   模型调用记录
-   质量指标

------------------------------------------------------------------------

# 15. 迁移实施路线

## Phase 1

Runtime Core

完成：

-   State Machine
-   Executor
-   Gate

## Phase 2

SKILL迁移

完成：

-   0-14阶段拆分
-   Contract定义

## Phase 3

企业能力

完成：

-   Multi Agent
-   Memory
-   Audit

------------------------------------------------------------------------

# 最终目标

qamaster从：

"依赖模型理解流程的Skill"

升级为：

"由Runtime控制、模型执行的企业级Agent系统"

核心原则：

Runtime控制流程。

模型执行任务。

任何模型不可绕过。
