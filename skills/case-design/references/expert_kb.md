# 专家知识库 KB_expert.md 唯一细则来源（v0.11.3）

> 本参考文件为**专家知识库**（`case-design-out/KB_expert.md`，`kind=expert`）的**唯一细则来源**。第0-14阶段每轮重入契约卡时，Runtime 经 `_prior_expert_kb_block` 注入 `##PRIOR_EXPERT_KB##`；本文件规定"何时沉淀、何时注入、怎么分类、怎么提炼"。SKILL.md 铁律 #5 仅含要点速记，细则以本文件为准。

> **与经验库/业务知识库的分工（强制·三类不串台）**：
> - `KB_lessons.md`（`kind=lesson`）：人类纠正**原话 verbatim**，按阶段+维度归档，occ 累积；既可存"本次业务特例"也可存"方法提醒"。**未经提炼**。
> - `KB_business.md`（`kind=business`）：从各需求 `Knowledge_*.md` 聚合的**业务知识**（模块+维度+元数据），绑定具体业务实体。
> - `KB_expert.md`（`kind=expert`，本文件主题）：从用户纠正中**提炼出的通用测试设计方法论**，脱业务实体后仍成立，只存方法不存业务。
>
> 三者**分文件、同禁写纪律**（模型禁止 Write/Edit，经 Runtime 命令在 FileLock 下落盘）。

---

## 一、分类决策树：用户纠正/方法论指导怎么路由

用户对测试用例的纠正补充**或测试设计方法论指导**（含审核/许可环节给出的通用方法建议，如"多条件判定须用判定表穷举 2^n 组合"），按下树**三选一**路由，禁止串台：

> **捕获时机（v0.11.11·自动识别+提炼）**：`fail`/`patch` 触发时 `_maybe_capture_lesson` 自动捕获 verbatim 入 `KB_lessons.md`；同时 `_flag_expert_candidate` 嗅探 reason 命中可抽象信号（`_ABSTRACTION_SIGNALS`）→ 置位 `pending_expert_extraction`，约束模型必须跑 `kb extract-expert` 提炼落 draft（带确定性别忽略门：reason 不含信号即拒绝）。但**审核门(14)/许可门(15)的方法论反馈是对话式给出、不经 fail/patch**（无 reason 字段供 Runtime 嗅探），故这两阶段契约卡常驻 `##METHODOLOGY_CAPTURE##` 提醒——由见到反馈的模型主动分类并执行 `kb add-expert`/`kb extract-expert`/`kb add-lesson`。**禁止以写入 Claude 个人记忆/项目记忆（`~/.claude/.../memory`）替代**：个人记忆不注入 qamaster 任何阶段、对后续需求设计不可见；方法论须经 Runtime `kb` 命令落盘（draft）方可经 endorse 或 occ≥3 注入 `##PRIOR_EXPERT_KB##`。

```
用户纠正
  │
  ├─① 含【需求层新增/修改/补充】？
  │   判据：纠正引入了新规则/新字段/新业务约束/新验收点/新状态/新接口
  │        （即"需求规格本身变了"，而非"测试设计漏了"）
  │   → 路由：补进 Knowledge_<需求标识>.md 对应维度
  │     时机：第14阶段（人工审核通过后）更新知识总结
  │     命令：无（知识总结由第14阶段流程维护，详见 references/knowledge.md）
  │     ✗ 不进专家库（专家库只存方法，不存业务）
  │
  ├─② 含【测试设计覆盖不全】？
  │   判据：纠正指出"漏测边界/漏状态机流转/漏异常子类/方法选错/断言不完整"
  │        （即"需求没变，是测试设计方法有缺口"）
  │   → 再分两支：
  │     │
  │     ├─ 能提炼为【通用方法论】？（见下"二、可提炼判定"）
  │     │   → 路由：kb extract-expert 沉淀 draft（fail/patch 命中信号时 Runtime 已强制）
  │     │     命令：kb extract-expert --reason "<纠正原话>" --req-id <id> \
  │     │            --category <类> --principle "<原则>" --applicable-phases <阶段>
  │     │     状态：draft（不注入）；endorse 或 occ≥3 后进 ##PRIOR_EXPERT_KB##
  │     │
  │     └─ 不可提炼（仅本次业务特例）？
  │         → 路由：留 KB_lessons.md（经验库，原话）
  │           机制：fail/patch 时 _maybe_capture_lesson 自动捕获 verbatim
  │           理由：离开本次需求即无意义，强行抽象会污染跨需求方法论
  │
  └─③ 两者兼有？
      → 拆分：需求层部分进 Knowledge_*.md；方法层可提炼部分进 KB_expert.md；
        不可提炼的方法层部分留 KB_lessons.md。三类各归其位。
```

**路由铁律**：① 走 Knowledge，②可提炼走 KB_expert，②不可提炼走 KB_lessons。**禁止**把需求层业务知识写进专家库（违反"只存方法不存业务"）；**禁止**把仅本次业务特例强行抽象进专家库（污染跨需求方法论）；**禁止**以 Claude 个人记忆/项目记忆替代 `kb add-expert`/`kb extract-expert`/`kb add-lesson` 沉淀方法论（个人记忆不注入任何阶段，对后续需求设计不可见——v0.11.4 根因修复）。

---

## 二、可提炼 vs 不可提炼判定

### 可提炼为通用方法论（→ `kb add-expert`）

**判据**：脱去具体业务实体后，方法原则**仍成立、仍可跨需求复用**。

| 纠正原话（业务绑定） | 提炼后的通用原则（脱业务） | 可提炼？ |
|----|----|----|
| "需求B的 RK16 风险没引" | （无通用原则，仅本次业务） | ✗ 留 lessons |
| "边界值只测了 min/max，漏了 min+1/max-1" | "边界内邻接值（min+1/max-1）是 off-by-one 高发区，须独立用例" | ✓ |
| "订单状态机漏了'已退款后再次退款'的非法流转拦截" | "状态机须覆盖终态后操作 + 不可逆流转拦截" | ✓ |
| "只测了正常券叠加，没测互斥券叠加" | "判定表须穷举互斥/共存/约束组合分支" | ✓ |
| "N个前置条件须同时满足，只测了全符合+每条件单独失败(4行)，漏了部分符合/全不符合" | "N个AND门前置条件(每条件布尔)→判定表须穷举2ⁿ真值表全行：全符合/全不符合/各部分符合(恰一/恰二…成立)/各单条件不成立+边界；2ⁿ有界(3条件=8行)不适用pairwise；不得以MCDC式短路覆盖替代" | ✓ |
| "支付接口没测重复提交的幂等" | "资金类接口须覆盖并发竞态窗口（重复提交/乐观锁冲突）" | ✓ |
| "需求A的字段 mobile 没脱敏" | "涉敏感字段时须覆盖脱敏断言（输出不含原文）" | ✓ |

**提炼操作**：
1. 剥离业务实体（订单/券/支付/手机号……）→ 保留方法骨架
2. 问"换个需求，这条原则还成立吗？"→ 成立 → 可提炼；不成立 → 留 lessons
3. principle 字段写**脱业务后的通用原则**，不写原话

### 不可提炼（→ 留 `KB_lessons.md`）

**判据**：离开本次需求即无意义，或强依赖具体业务实体/具体字段名。

- "RK16 风险未引"——风险 ID 是本次需求专属
- "ORD_CREATE_003 断言模糊"——用例 ID 是本次需求专属
- "优惠券叠加规则漏了券A+券B"——具体券组合是业务知识
- "需求C的 mobile 字段要脱敏"——字段名是业务实体（但"敏感字段须脱敏"可提炼）

**这类纠正**：经 `fail`/`patch` 由 `_maybe_capture_lesson` 自动捕获原话入 `KB_lessons.md`，occ 累积，endorse 或 occ≥3 后注入 `##PRIOR_LESSONS##`/`##RELEVANT_LESSONS##`。**不进专家库**。

---

## 三、category 词表（与 methods.md 决策表对齐）

`--category` 须取自下表（便于第6阶段方法决策匹配）。新增类目须在此登记：

| category | 适用场景 | 对应 methods.md |
|----|----|----|
| 边界值 | 长度/数量/金额/时间阈值 | 边界值 4 值模型 |
| 等价类 | 表单/API参数/搜索条件输入 | 等价类（合法+非法） |
| 状态迁移 | 订单/审批/生命周期 | 状态迁移（合法+非法流转+回滚+终态） |
| 判定表 | 多条件业务规则组合 | 判定表/pairwise |
| 场景法 | 端到端业务链路 | 场景法 |
| 错误推测 | 高风险异常/历史缺陷密集区 | 错误推测法（对照 0.6 隐含风险） |
| 契约测试 | 变更接口契约（入参/出参/鲁棒性） | 统一接口测试矩阵 |
| 安全 | 敏感数据脱敏/越权/注入/泄露 | safety_coverage 硬门 |
| 幂等 | 重复提交/重复消费 | 幂等专项 |
| 并发 | 竞态窗口/乐观锁/缓存DB一致性 | 并发专项 |

**填法**：`--category 边界值`（取词表枚举值，不加修饰词）。一条记录一个 category；跨类目的复合方法拆成多条。

---

## 四、applicable_phases 填法

`--applicable-phases` 用 `/`、`|`、`,` 或全角 `、`、`，` 分隔的阶段编号（如 `6/8/11`，Runtime `_split_tokens` 统一接受这些分隔符）。**空则全阶段适用兜底**（慎用——多数方法有明确落点阶段）。参考映射：

| category | 典型 applicable_phases | 理由 |
|----|----|----|
| 边界值 | 6/8/11 | 第6方法决策、第8用例生成、第11对抗补漏（边界组合遗漏盲区） |
| 等价类 | 6/8 | 第6方法决策、第8用例生成 |
| 状态迁移 | 5/6/8/11 | 第5风险（P0状态流转）、第6方法、第8用例、第11对抗（非法流转遗漏盲区） |
| 判定表 | 6/8 | 第6方法决策、第8用例生成 |
| 场景法 | 6/8 | 第6方法决策、第8用例生成 |
| 错误推测 | 5/8/11 | 第5风险、第8用例、第11对抗（异常子类未覆盖盲区） |
| 契约测试 | 6/8/11 | 第6方法、第8用例、第11对抗（契约类覆盖） |
| 安全 | 5/8/11 | 第5风险（安全P0）、第8用例、第11对抗（安全风险遗漏盲区） |
| 幂等 | 5/8/11 | 第5风险、第8用例、第11对抗（并发竞态盲区） |
| 并发 | 5/8/11 | 同上 |

**对抗生成遍专属**：检查14 对抗遍的方法论常把 `11` 纳入 applicable_phases（自检轮参考）。第11阶段自检每轮重入时，若 phase=11 ∈ applicable_phases，且需求命中 trigger，则注入。

**填法铁律**：
- 列实际落点阶段，不贪多（不是越多越好——不适用的阶段注入是噪声）
- 对抗生成相关的方法论务必含 `11`（否则自检轮注入不到）
- 全阶段适用（`applicable_phases=[]`）仅限真正跨所有阶段的方法（极少）

---

## 五、信任门：endorsed 或 occ≥3

| 门 | lessons/business | **expert** |
|----|----|----|
| 注入条件 | endorsed **OR** occ≥3 | **endorsed OR occ≥3**（v0.11.11 重开逃生口） |
| draft 行为 | 可存不注入 | 可存不注入（occ<3 且未 endorse 时不注入） |
| 逃生口理由 | 经验/业务知识偶发误判可容忍 | occ≥3 是 ≥3 个独立需求命中同一指纹的强现实信号（非模型自信）；自动生效记录可 supersede 撤销 |

**endorse 流程**：
1. `kb add-expert --category <类> --principle "<原则>" --applicable-phases <阶段> --trigger <词>` → 落盘 `KB_expert.md`，`status=draft`，不注入
2. 人工审阅 principle 是否真通用（脱业务成立）、category 是否准确、applicable_phases 是否合理
3. `kb endorse --kind expert --id <KB-expert-xxxxxxxxxxxx>` → `status=endorsed` → 进 `##PRIOR_EXPERT_KB##`（或 `--all-drafts` 一键全背）
4. 误沉淀的 endorsed 记录 → `kb supersede --kind expert --id <id> --by <newid>` 归档，不再注入

**自动生效（v0.11.11）**：同一 `category|principle[:40]` 指纹被 ≥3 个独立需求命中（`occurrences≥3`）→ 即便 `status=draft` 也注入（信任门 `status != "endorsed" and occurrences < 3` 才跳过）。误生效 → `kb supersede` 撤销。

**draft 状态的记录**：结构合法（`verify_kb.py` 通过），但 occ<3 且未 endorse 时 Runtime 不注入——`_prior_expert_kb_block` 的信任门 `if r.get("status") != "endorsed" and (r.get("occurrences", 1) or 1) < 3: continue` 跳过。

---

## 六、注入机制（Runtime 实现，模型只读）

`_prior_expert_kb_block`（runtime）每阶段每轮（含自检轮）执行**三门过滤**：

1. **适用性门**：当前 phase ∈ 记录 `applicable_phases`（空列表视为全阶段适用兜底）
2. **信任门**：`status == "endorsed"` **或** `occurrences ≥ 3`（v0.11.11 重开 occ≥3 逃生口）
3. **相关性门**：trigger 在 REQ 文本命中 ≥2 **或** module 标题命中 REQ

三门全过 → 渲染进 `##PRIOR_EXPERT_KB##`（`_render_expert_block`：category/principle/applicable_phases/trigger），注入当前阶段契约卡。

**No-op 保证**：无 `KB_expert.md` / 无 endorsed 记录 / 当前 phase 无适用 / 无相关 → 返回 `""` → 契约卡与 v0.11.2 逐字节一致（护既有 150/0 substring 断言）。

**自检轮覆盖**：Phase 11 入口契约卡跨自修迭代常驻上下文，入口卡已含 `##PRIOR_EXPERT_KB##`（applicable_phases 含 11 的记录）→ 自修/对抗补漏时参考，无需新 Runtime 命令。详见 `references/selfcheck.md` 自检轮专家方法论注入说明 + 检查14。

---

## 七、与 methods.md 的边界（互补不重复）

| 维度 | methods.md | KB_expert.md |
|----|----|----|
| 性质 | **静态出厂种子** | **从纠正中累积的新方法论** |
| 时机 | skill 出厂即携带 | 运行中随用户纠正进化 |
| 内容 | 第6阶段方法决策表 + 各方法适用说明 + 边界值4值模型 + 统一接口测试矩阵 | 纠正中提炼的、methods.md 未穷尽的方法原则 |
| 维护 | 版本升级时人工更新 | Runtime `kb add-expert`/`endorse` 进化 |
| 注入 | 第6阶段方法决策阶段读取 | 0-14 每轮 `##PRIOR_EXPERT_KB##` |

**边界铁律**：
- methods.md 已穷尽的方法原则**不重复沉淀**进 KB_expert.md（如"边界值4值模型"已在 methods.md，不再 add-expert）
- KB_expert.md 只沉淀**methods.md 未覆盖**的新方法论（如某次纠正发现的"配置热更新致 token 泄露到日志"——methods.md 错误推测清单无此项，可提炼进 expert）
- 二者**互补**：methods.md 是出厂基线，KB_expert.md 是增量进化。第6阶段读 methods.md 做方法决策；0-14 每轮读 KB_expert.md 做适用方法论参考。

---

## 八、维护命令速查

```bash
# 沉淀 draft（不注入）—— 自动提炼入口（v0.11.11：带确定性别忽略门，纠正原话命中可抽象信号才落盘）
python runtime/qamaster_runtime.py kb extract-expert \
  --reason "边界只测 min/max 漏 min+1" \
  --req-id <req_id> \
  --category 边界值 \
  --principle "边界内邻接值 min+1/max-1 是 off-by-one 高发区，须独立用例不得合并" \
  --applicable-phases 6/8/11
# （reason 不含可抽象方法信号时 Runtime 拒绝：自动忽略，不进专家库）

# endorse 后注入（单条 / 一键全背）
python runtime/qamaster_runtime.py kb endorse --kind expert --id KB-expert-xxxxxxxxxxxx
python runtime/qamaster_runtime.py kb endorse --kind expert --all-drafts

# 查询某阶段适用方法论（验证注入）
python runtime/qamaster_runtime.py kb query --kind expert --phase 6 --against <req文件>

# 结构校验
python skills/case-design/scripts/verify_kb.py case-design-out/KB_expert.md

# 归档误沉淀记录
python runtime/qamaster_runtime.py kb supersede --kind expert --id <旧id> --by <新id>
```

**铁律 #5**：模型禁止 Write/Edit `KB_expert.md`。所有写操作经 Runtime 命令（FileLock 下落盘），进化机制与模型无关。
