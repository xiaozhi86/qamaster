# 录音智能解读需求设计文档

- **日期**: 2026-07-28
- **模块**: rmp-app
- **作者**: tanguang-jk
- **状态**: 待评审

---

## 1. 背景与目标

### 1.1 背景

质检系统将电销录音 ASR 转写结果写入 Kafka 报文 `electrin_record_info_template`。需要在 rmp-app 新增 Kafka 消费能力，对录音文本调用模型服务做智能解读（AI 总结、标签、评分、挂机节点），再把模型结果 + 质检原报文字段通过 Dubbo 推送给电销系统。

### 1.2 目标

- 消费质检系统 Kafka 录音报文
- 前置过滤：基于 Apollo 可配的 SpEL 表达式（上下文根对象为 `electrinRecordInfo`），默认 `#root.recodeDuration >= 20` 秒才放行，后续可灵活扩展过滤规则不改代码
- 调用模型 HTTP 服务（vLLM `/v1/chat/completions` 端点，Bearer Token 鉴权，请求/响应按 `电销录音总结.md` 中"1. 单通预定义输入输出格式"）
- 将模型输出 + 质检原报文字段组装后通过 Dubbo `CallRecordSummaryFacade#receiveRecord` 推送给电销系统
- HTTP 调用、Dubbo 推送失败均有重试机制，跨进程重启不丢数据

### 1.3 非目标

- 不在 rmp-api 对外暴露 facade 接口
- 不实现多通预定义输入输出格式（客户特征/挂机节点 ai 分析建议）—— 仅单通
- 不做死信队列（DLQ）—— 超过最大重试次数后告警丢弃
- 不实现 Web 管理界面

---

## 2. 调用链路

```
质检系统 ──Kafka(topic_electrin_record_info)──> rmp-app/service/recordsummary
                                                 │
                                                 ▼
       ┌─── ElectrinRecordSummaryListener ─────────────────┐
       │  1) 解析 KafkaMessage payload → ElectrinRecordInfo  │
       │     + textInfo                                     │
       │  2) 过滤：SpEL 表达式不通过 → 丢弃+记日志         │
       │     默认 #root.recodeDuration >= 20              │
       │  3) textInfo 按 startTime 升序排序                 │
       │     channel=0 → "assitant" / channel=1 → "user"    │
       │  4) 提交专用线程池异步处理                          │
       └────────────────────┬──────────────────────────────┘
                            ▼
       ┌─────────── RecordSummaryHandler ───────────────────┐
       │ Step1 RecordSummaryModelService.callModel()         │
       │   · HTTP POST，URL/Token/超时/重试 Apollo 可配        │
       │   · 失败指数退避重试 5 次（1s/2s/4s/8s/16s）            │
       │   · 全部失败 → 告警日志 + 丢弃（不落 Kafka）          │
       │ Step2 组装 CallRecordSummaryRequest                 │
       │   · 模型输出字段 + ElectrinRecordInfoRequest(质检字段)│
       │ Step3 调用 CallRecordSummaryFacade#receiveRecord     │
       │   · 成功 (Response.success && data=true) → 完成      │
       │   · 失败 → 发送 dirp_record_summary_retry topic      │
       └──────────────────────────────────────────────────────┘
                            │ 失败
                            ▼
       ┌─── RecordSummaryRetryListener ─────────────────────┐
       │  · 消费 dirp_record_summary_retry topic              │
       │  · payload = CallRecordSummaryRequest JSON + retryCount│
       │  · 退避 30s/60s/120s/300s/600s，最多 5 次           │
       │  · 只重试 Dubbo 部分，不重新调模型                    │
       │  · 超过 5 次 → 告警日志 + 丢弃                       │
       └──────────────────────────────────────────────────────┘
```

---

## 3. 数据映射

### 3.1 输入映射：质检报文 → 模型 HTTP 请求

模型 HTTP 请求体（按 `电销录音总结.md` 单通预定义输入输出格式）：

```json
{
  "user_no": "xxx",
  "connection_time": "yyyy-MM-dd HH:mm:ss",
  "duration_seconds": 20.1,
  "conversation": [
    {"role": "assitant", "content": "xxx", "start_time": 1},
    {"role": "user", "content": "xxx", "start_time": 2}
  ]
}
```

| 模型字段 | 来源（质检报文） | 说明 |
|---|---|---|
| `user_no` | `electrinRecordInfo.custNo` | 客户号 |
| `connection_time` | `electrinRecordInfo.recordStartTime` | 接通时间，格式化为 yyyy-MM-dd HH:mm:ss |
| `duration_seconds` | `electrinRecordInfo.recodeDuration` | 通话时长（秒，BigDecimal） |
| `conversation[]` | `textInfo[]` | 按 startTime 升序排序后逐条映射 |
| `conversation[].role` | `textInfo[].channel` | `channel=0 → "assitant"`（拼写按模型文档保留，不修正），`channel=1 → "user"` |
| `conversation[].content` | `textInfo[].text` | 文本 |
| `conversation[].start_time` | `textInfo[].startTime` | 句子开始时间 |

### 3.2 输出映射：模型 HTTP 响应 + 质检字段 → CallRecordSummaryRequest

模型 HTTP 响应体：

```json
{
  "summary": "xxx",
  "labels": [{"value":"...","category":"...","evidence":"..."}],
  "cust_intent_score": 5,
  "cust_objection_score": 1,
  "cust_failure_score": 0,
  "evaluation": {"score":85.5,"evaluation_dimensions":[{"name":"...","score":90}]},
  "hungup_node": "xxx"
}
```

| Dubbo 字段（CallRecordSummaryRequest） | 来源 | 说明 |
|---|---|---|
| `userNo` | `electrinRecordInfo.custNo` | 与模型输入一致 |
| `callSheetId` | `electrinRecordInfo.callSheetId` | 通话流水 ID |
| `connectionTime` | `electrinRecordInfo.recordStartTime` | Date 类型直接传 |
| `durationSeconds` | `electrinRecordInfo.recodeDuration` | BigDecimal |
| `summary` | 模型响应 `summary` | 原样 |
| `labels` | 模型响应 `labels[]` | 逐条映射 value/category/evidence |
| `custIntentScore` | 模型响应 `cust_intent_score` | Integer |
| `custObjectionScore` | 模型响应 `cust_objection_score` | Integer |
| `custFailureScore` | 模型响应 `cust_failure_score` | Integer |
| `evaluation.score` | 模型响应 `evaluation.score` | BigDecimal（注意模型返回 String，需 `new BigDecimal(str)` 转换，异常时置 null） |
| `evaluation.evaluationDimensions` | 模型响应 `evaluation.evaluation_dimensions` | 逐条 name/score（score BigDecimal） |
| `hungupNode` | 模型响应 `hungup_node` | String |
| `electrinRecordInfo` | 质检报文 `electrinRecordInfo` 整体映射到 `ElectrinRecordInfoRequest` | 字段名一致，仅 `_id` → `id` 需手工处理；其余可 BeanCopy |

### 3.3 重试 topic payload 结构

```json
{
  "request": {CallRecordSummaryRequest 完整 JSON},
  "retryCount": 0,
  "firstFailTime": 1722...
}
```

---

## 4. 错误处理与重试

### 4.1 HTTP 模型调用重试

**失败需重试的情形：**
- 网络异常（IOException、SocketTimeoutException、连接拒绝）
- HTTP 状态码非 200
- HTTP 200 但响应体解析失败（JSON 解析异常、字段缺失）
- HTTP 200 但响应体业务字段异常（如 `summary` 为空且 labels 为空）

**不重试直接丢弃 + 告警：**
- 请求构造异常（如 conversation 为空）
- 模型返回明确业务错误（如 `error_code` 表明输入非法）

**重试参数：**
```properties
record.summary.model.retry.max-attempts = 5
record.summary.model.retry.backoff-base-ms = 1000
```

退避序列：第 1 次重试等 1000ms，第 2 次等 2000ms，第 3 次等 4000ms，第 4 次等 8000ms，第 5 次等 16000ms。总退避约 31s。全部失败后告警丢弃，不落 Kafka。

### 4.2 Dubbo 推送重试

**失败需进重试 topic 的情形：**
- Dubbo 抛异常（RpcException、超时、网络问题）
- Dubbo 返回非成功：`response == null` 或 `!response.checkIfSuccess()` 或 `response.getData() == null` 或 `response.getData() == false`

**重试参数：**
```properties
record.summary.dubbo.retry.topic = dirp_record_summary_retry
record.summary.dubbo.retry.max-attempts = 5
record.summary.dubbo.retry.backoff-ms = 30000,60000,120000,300000,600000
```

退避序列 30s/60s/120s/300s/600s。纯退避总和约 18.5 分钟，加上 6 次 Dubbo 调用超时（10s × 6 = 60s），总耗时约 19.5 分钟。第 5 次重试仍失败后告警丢弃。

### 4.3 重试 topic 消费策略

- **消费组**：`dirp-rmp-app-record-summary-retry`（独立于主消费组，避免阻塞主链路）
- **max-poll-records**：50（避免大批量重试冲击 Dubbo）
- **同步处理**：不提交线程池，重试量级低，避免线程池二次异步化导致追踪困难
- **退避实现**：根据 `retryCount` 从 Apollo 配置取间隔，`Thread.sleep` 阻塞当前消息处理（kafka 消费阻塞会拉长消费间隔，自然限流）
- **失败计数**：payload 里的 `retryCount` 自增；超过 max-attempts 则记 error 日志 + 告警 + 提交 offset（不进死信队列）

### 4.4 幂等性

- 同一 `callSheetId` 可能因为 kafka 重投递被重复消费
- Dubbo 侧 `receiveRecord` 应自身保证幂等（电销方按 `callSheetId` 去重）
- rmp 侧基于 Redis SETNX `record_summary:lock:{callSheetId}` 做 5 分钟短期去重，避免重复调模型浪费成本

```properties
record.summary.idempotent.expire-seconds = 300
```

### 4.5 告警

复用现有 `TeamsSendComponent` 发送告警到团队群：
- HTTP 模型连续 5 次失败丢弃 → 告警
- Dubbo 重试 5 次仍失败 → 告警
- 告警内容：`callSheetId`、失败原因摘要、时间

### 4.6 监控日志关键字

| 场景 | 日志关键字 |
|---|---|
| 收到 Kafka 消息 | `RecordSummary received` |
| 过滤丢弃（SpEL 不通过） | `RecordSummary filtered` |
| 模型调用成功 | `RecordSummary model success` |
| 模型调用失败重试 | `RecordSummary model retry` |
| 模型调用最终失败 | `RecordSummary model failed` |
| Dubbo 推送成功 | `RecordSummary dubbo success` |
| Dubbo 推送失败入重试 | `RecordSummary dubbo retry` |
| Dubbo 重试最终失败 | `RecordSummary dubbo exhausted` |

---

## 5. 模块/类设计

### 5.1 包结构

```
rmp-app/src/main/java/com/qihoo/finance/dirp/rmp/app/
├── aurorafacade/
│   └── TmkFacadeProviders.java              # 新增：电销 Dubbo 引用
├── config/
│   └── RecordSummaryConfig.java             # 新增：线程池 + Apollo 配置类
└── service/recordsummary/                   # 新增子包
    ├── ElectrinRecordSummaryListener.java   # Kafka 主 topic 消费
    ├── RecordSummaryHandler.java            # 业务编排：模型调用 + Dubbo 推送
    ├── RecordSummaryRetryListener.java      # 重试 topic 消费
    ├── RecordSummaryModelService.java       # HTTP 调用模型 + 重试
    ├── RecordSummaryConverter.java          # 报文转换
    ├── RecordSummaryFilterService.java      # SpEL 过滤（根对象 = electrinRecordInfo）
    └── RecordSummaryIdempotentService.java  # Redis 幂等控制
```

### 5.2 类职责

#### `TmkFacadeProviders`
```java
@Component
@Data
public class TmkFacadeProviders {
    @Reference(check = false, timeout = 10000, retries = 0, registry = "zj")
    private CallRecordSummaryFacade callRecordSummaryFacade;
}
```

#### `RecordSummaryConfig`
- `@Configuration`
- 暴露 `RECORD_SUMMARY_EXECUTORS` 线程池 Bean（core/max/queue Apollo 可配）
- 持有所有 `record.summary.*` 配置项

#### `ElectrinRecordSummaryListener`
- `@KafkaListener(topics = "${record.summary.kafka.topic:dirp_electrin_record_info}")`
- 解析 `KafkaMessage` payload → `ElectrinRecordInfo` + `textInfo`
- 调用 `RecordSummaryFilterService` 执行 Apollo 配置的 SpEL 表达式（根对象为 `electrinRecordInfo`），表达式返回 false → 丢弃
- 提交 `RECORD_SUMMARY_EXECUTORS` 异步执行 `RecordSummaryHandler.handle()`
- 同步提交 offset

#### `RecordSummaryHandler`
- 编排方法 `handle(ElectrinRecordInfo, List<TextInfo>)`
- Step1：`RecordSummaryModelService.callModel(...)` → 模型响应
- Step2：`RecordSummaryConverter.buildDubboRequest(...)` → `CallRecordSummaryRequest`
- Step3：调用 `tmkFacadeProviders.callRecordSummaryFacade.receiveRecord(req)`
- Step3 失败 → `KafkaMsgSendComponent.sendMsg("dirp_record_summary_retry", retryPayload)`

#### `RecordSummaryModelService`
- `callModel(ElectrinRecordInfo, List<TextInfo>)` → `ModelResponse`
- 内部用 `HttpUtil.httpClient(...)` POST 调用
- 失败重试逻辑：循环 max-attempts 次，间隔 `backoff-base-ms * 2^(attempt-1)`
- 最终失败返回 null，由 handler 决定丢弃

#### `RecordSummaryConverter`
- `buildModelRequest(ElectrinRecordInfo, List<TextInfo>)` → 模型请求 JSON
- `parseModelResponse(String)` → 模型响应对象
- `buildDubboRequest(ElectrinRecordInfo, ModelResponse)` → `CallRecordSummaryRequest`
- `buildRetryPayload(CallRecordSummaryRequest, int retryCount)` → 重试 topic JSON
- `parseRetryPayload(String)` → 反序列化

#### `RecordSummaryRetryListener`
- `@KafkaListener(topics = "${record.summary.dubbo.retry.topic:dirp_record_summary_retry}")`
- 同步处理（不提交线程池）
- 取 `retryCount`，按 Apollo 配置的退避序列阻塞等待
- 调用 `CallRecordSummaryFacade.receiveRecord(...)`
- 成功 → 完成；失败 → retryCount+1 重新入 topic；超过 max-attempts → 告警 + 丢弃

#### `RecordSummaryFilterService`
- `@Component`
- `boolean shouldProcess(ElectrinRecordInfo info)` — 执行 Apollo 配置的 SpEL 表达式
- 启动时解析 `record.summary.filter.spel-expression`，编译为 `Expression` 缓存（Apollo 配置变更时通过 `@ApolloConfigChangeListener` 重新编译）
- 解析失败的配置视为「放行」（避免因配置错误丢数据，由日志告警）
- 表达式异常时记 error 日志并放行（避免单条脏数据阻断整批消费）
- 根对象：`electrinRecordInfo`，支持任意公共字段（`#root.recodeDuration`、`#root.callDirection`、`#root.firstCall`、`#root.callTimes` 等）

### 5.3 线程池设计

```java
public static final String RECORD_SUMMARY_EXECUTORS = "recordSummaryExecutors";

@Bean(name = RECORD_SUMMARY_EXECUTORS)
public ThreadPoolExecutor recordSummaryExecutors(
        @Value("${record.summary.executor.core-pool-size:8}") int core,
        @Value("${record.summary.executor.max-pool-size:32}") int max,
        @Value("${record.summary.executor.queue-capacity:200}") int queue) {
    return new ThreadPoolExecutor(
        core, max, 60L, TimeUnit.SECONDS,
        new LinkedBlockingQueue<>(queue),
        new ThreadFactoryBuilder().setNameFormat("RecordSummary-%d").build(),
        new ThreadPoolExecutor.CallerRunsPolicy()
    );
}
```

拒绝策略 `CallerRunsPolicy`：让 kafka 消费线程自己跑，自然限流。

### 5.4 现有代码复用

- `HttpUtil.httpClient(...)` - 已有 HTTP 工具，直接用
- `KafkaMsgSendComponent.sendMsg(...)` - 已有 Kafka 发送组件，用于发重试 topic
- `KafkaMessage` - 已有 Kafka 包装类，重试 topic 也用同样格式
- `TeamsSendComponent` - 已有告警组件
- `MDCUtil.putTraceId()` / `CurrentTenantThreadLocalComponent` - 已有的链路追踪和多租户上下文

---

## 6. Dubbo 接入

### 6.1 接口签名（电销方已提供）

```java
// com.qihoo.finance.tmk.ai.helper.facade.CallRecordSummaryFacade
Response<Boolean> receiveRecord(CallRecordSummaryRequest req);
```

### 6.2 关键 DTO 结构

**CallRecordSummaryRequest:**
- `userNo` / `callSheetId` / `connectionTime` / `durationSeconds` — 元数据
- `summary` / `labels` / `custIntentScore` / `custObjectionScore` / `custFailureScore` / `evaluation` / `hungupNode` — 模型输出
- `electrinRecordInfo` (ElectrinRecordInfoRequest) — 质检原报文字段

**ElectrinRecordInfoRequest:** 字段与质检报文 `electrinRecordInfo` 基本一致，仅 `_id` → `id`，并新增 `taskId` / `taskName`。

### 6.3 注册中心

- 不新增 registry，复用现有 `zj` 注册中心
- `zj` / `zjb` 双集群，Dubbo 调用只调 `zj` 一个集群

### 6.4 Maven 依赖

pom.xml 新增：
```xml
<dependency>
    <groupId>com.qihoo.finance.tmk.ai</groupId>
    <artifactId>ai-helper-api</artifactId>
    <version>1.2.18-SNAPSHOT</version>
</dependency>
```

---

## 7. Apollo 配置清单

```properties
# ============ Kafka 主 topic ============
record.summary.kafka.topic = dirp_electrin_record_info

# ============ 模型 HTTP ============
# vLLM /v1/chat/completions 端点
record.summary.model.url = http://xxx/v1/chat/completions
# Bearer Token
record.summary.model.token = xxx
# 超时（毫秒）
record.summary.model.connect-timeout = 5000
record.summary.model.read-timeout = 30000
# 重试次数（不含首次）
record.summary.model.retry.max-attempts = 3
# 退避间隔基数（毫秒），实际间隔 = base * 2^(attempt-1)
record.summary.model.retry.backoff-base-ms = 1000

# ============ Dubbo 推送重试 ============
record.summary.dubbo.retry.topic = dirp_record_summary_retry
record.summary.dubbo.retry.max-attempts = 5
record.summary.dubbo.retry.backoff-ms = 30000,60000,120000,300000,600000

# ============ 幂等 ============
record.summary.idempotent.expire-seconds = 300

# ============ 线程池 ============
record.summary.executor.core-pool-size = 8
record.summary.executor.max-pool-size = 32
record.summary.executor.queue-capacity = 200

```

---

## 8. 测试要点

1. **正常链路**：构造 recodeDuration >= 20 的质检报文，验证模型调用成功 + Dubbo 推送成功
2. **过滤丢弃**：构造 recodeDuration < 20 的报文，验证直接丢弃 + 日志含 `RecordSummary filtered`
3. **过滤扩展**：Apollo 修改 SpEL 为 `#root.recodeDuration >= 20 and #root.callDirection == 'OUTBOUND'`，验证 callDirection 不符的报文被丢弃
4. **HTTP 模型重试**：mock 模型服务前 4 次返回 500，第 5 次 200，验证重试成功
5. **HTTP 模型最终失败**：mock 模型服务全部 500，验证告警 + 丢弃
6. **Dubbo 失败重试**：mock Dubbo 抛 RpcException，验证发到重试 topic + 重试 listener 消费重试
7. **Dubbo 重试耗尽**：mock Dubbo 持续失败，验证 5 次后告警 + 丢弃
8. **幂等性**：同一 callSheetId 重复投递，验证第二次被 Redis 锁拦截不调模型
9. **声道映射**：构造混合 channel=0/1 的 textInfo，验证 conversation 顺序正确 + role 映射正确
10. **数据映射**：构造带 evaluation.score 为 String "85.5" 的模型响应，验证 BigDecimal 转换正确
11. **质检字段透传**：验证 ElectrinRecordInfo 字段全部映射到 ElectrinRecordInfoRequest，`_id` → `id`

---

## 9. 风险与待确认

| 项 | 风险/待确认 | 缓解 |
|---|---|---|
| 模型服务 URL/Token | 需要联系模型方获取 | Apollo 占位，部署前填入 |
| vLLM `/v1/chat/completions` 是否接受非 OpenAI 标准字段 | 模型方需在 vLLM 上做业务包装 | 已与模型方约定按电销录音总结.md 报文格式 |
| 电销 Dubbo facade `receiveRecord` 幂等性 | 重复投递可能 | 电销方按 callSheetId 去重 |
| ai-helper-api 1.2.18-SNAPSHOT 版本 | SNAPSHOT 不稳定 | 上线前确认是否发布正式版 |
| Kafka 主 topic 名称 | 与质检方约定 | 待与质检方确认最终 topic 名 |
