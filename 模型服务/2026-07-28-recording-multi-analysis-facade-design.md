# 录音多通 AI 分析建议接口设计文档

- **日期**: 2026-07-28
- **模块**: rmp-api / rmp-app
- **作者**: tanguang-jk
- **状态**: 待评审

---

## 1. 背景与目标

### 1.1 背景

`电销录音总结.md` 定义了三套模型输入输出格式。接口 1（单通预定义输入输出格式）已在 rmp-app 落地实现：消费质检 Kafka 录音报文 → 调模型 HTTP → 通过 Dubbo `CallRecordSummaryFacade#receiveRecord` 推送给电销系统。

电销系统现需主动调用 rmp 获取多通分析结果，包含两个接口：
- **接口 2**：客户特征 ai 分析建议（多通）—— 输入意向/异议/失败三类客户特征聚合，输出特征建议 + 坐席表现 + 转化断点 + 总结
- **接口 3**：挂机节点 ai 分析建议（多通）—— 输入按挂机节点聚合的客户主要关注点，输出 AI 建议

### 1.2 目标

- 在 rmp-api 新增 `ICallRecordMultiAnalysisFacade`，对外暴露两个 Dubbo 方法
- 在 rmp-app 实现该 facade，内部调用模型 HTTP 服务（vLLM `/v1/chat/completions`）拼装响应返回
- 同步请求-响应模式，电销方通过 Dubbo 调用
- 同时通过 `@RestfulApi` 暴露 HTTP 端点供测试调用

### 1.3 非目标

- 不做 HTTP 模型调用重试（失败直接返回错误码）
- 不做幂等控制（同步接口，调用方自行控制重复调用）
- 不做告警（同步接口，调用方可感知失败）
- 不做异步/回调/轮询
- 不落库（无审计需求）

---

## 2. facade 接口与实现定义

### 2.1 facade 接口（rmp-api）

**位置**：`rmp-api/src/main/java/com/qihoo/finance/dirp/rmp/api/facade/ICallRecordMultiAnalysisFacade.java`

```java
public interface ICallRecordMultiAnalysisFacade {

    /**
     * 客户特征 ai 分析建议（多通）
     * 输入：意向/异议/失败 三类客户特征聚合
     * 输出：prospective/objecting/failed + assitant_performance + conversion_breakpoint + summary
     */
    Response<CustFeatureAnalysisResponseVo> analyzeCustFeature(CustFeatureAnalysisRequestVo request);

    /**
     * 挂机节点 ai 分析建议（多通）
     * 输入：按挂机节点聚合的客户主要关注点
     * 输出：ai_advice
     */
    Response<HungupNodeAnalysisResponseVo> analyzeHungupNode(HungupNodeAnalysisRequestVo request);
}
```

**命名说明**：
- 接口名 `ICallRecordMultiAnalysisFacade` 与接口 1 的 `CallRecordSummaryFacade`（电销方提供）在"CallRecord"前缀上保持一致，便于跨系统识别
- 方法名 `analyze*` 前缀，语义清晰（AI 分析建议）
- 请求/响应 VO 命名遵循项目惯例（`xxxRequestVo` / `xxxResponseVo`）

### 2.2 facade 实现（rmp-app）

**位置**：`rmp-app/src/main/java/com/qihoo/finance/dirp/rmp/app/facade/CallRecordMultiAnalysisFacadeImpl.java`

```java
@Slf4j
@Service(validation = "true", timeout = 60000, registry = {"zj", "zjb"})
@RestfulApi(value = "/callRecordMultiAnalysis")
public class CallRecordMultiAnalysisFacadeImpl implements ICallRecordMultiAnalysisFacade {

    @Autowired
    private RecordMultiAnalysisHandler recordMultiAnalysisHandler;

    @Override
    @RestfulInterfaceApi(value = "analyzeCustFeature", timeout = 60000, method = "POST", verifyAuth = false)
    public Response<CustFeatureAnalysisResponseVo> analyzeCustFeature(CustFeatureAnalysisRequestVo request) {
        return recordMultiAnalysisHandler.handleCustFeature(request);
    }

    @Override
    @RestfulInterfaceApi(value = "analyzeHungupNode", timeout = 60000, method = "POST", verifyAuth = false)
    public Response<HungupNodeAnalysisResponseVo> analyzeHungupNode(HungupNodeAnalysisRequestVo request) {
        return recordMultiAnalysisHandler.handleHungupNode(request);
    }
}
```

**关键点**：
- `@Service` + `@RestfulApi` 双注解：同一 facade 实现既暴露 Dubbo 服务（注册到 `zj` / `zjb` 双集群），又通过 `DubboRestfulApiResourceLoaderComponent` 自动生成 HTTP 映射（POST `/callRecordMultiAnalysis/analyzeCustFeature`、POST `/callRecordMultiAnalysis/analyzeHungupNode`）
- `registry = {"zj", "zjb"}`：双集群注册，电销系统从任一集群消费都能拿到服务
- `timeout = 60000`：覆盖模型 30s 调用 + 余量
- `verifyAuth = false`：不鉴权（电销内部调用）
- facade 实现仅做委托，不含业务逻辑

---

## 3. 请求/响应 VO 字段映射

### 3.1 接口 2：客户特征 ai 分析建议

**请求 VO**：`CustFeatureAnalysisRequestVo`（rmp-api/domain/multianalysis/）

| VO 字段（camelCase） | 模型 HTTP 字段（snake_case） | 类型 | 说明 |
|---|---|---|---|
| `rawProspectiveCustFeature` | `raw_prospective_cust_feature` | `Map<String, Map<String, Integer>>` | 意向客户特征：外层 key=一级标签名，内层 map 含 `totals` + 各二级/三级标签计数 |
| `rawObjectingCustFeature` | `raw_objecting_cust_feature` | `Map<String, Map<String, Integer>>` | 异议客户特征 |
| `rawFailedCustFeature` | `raw_failed_cust_feature` | `Map<String, Map<String, Integer>>` | 失败客户特征 |

**响应 VO**：`CustFeatureAnalysisResponseVo`

| VO 字段（camelCase） | 模型 HTTP 字段（snake_case） | 类型 | 说明 |
|---|---|---|---|
| `prospectiveCustFeature` | `prospective_cust_feature` | `List<String>` | 意向特征建议 |
| `objectingCustFeature` | `objecting_cust_feature` | `List<String>` | 异议特征建议 |
| `failedCustFeature` | `failed_cust_feature` | `List<String>` | 失败特征建议 |
| `assitantPerformance` | `assitant_performance` | `String` | 坐席表现（保留原文 `assitant` 拼写，不修正） |
| `conversionBreakpoint` | `conversion_breakpoint` | `String` | 转化断点 |
| `summary` | `summary` | `String` | 总结 |

### 3.2 接口 3：挂机节点 ai 分析建议

**请求 VO**：`HungupNodeAnalysisRequestVo`

| VO 字段 | 模型 HTTP 字段 | 类型 | 说明 |
|---|---|---|---|
| `nodeFeatureMap` | （直接作为 JSON root） | `Map<String, Map<String, Integer>>` | 外层 key=挂机节点名（如"开场白挂断"），内层 map 含 `totals` + 各客户主要关注点计数 |

**响应 VO**：`HungupNodeAnalysisResponseVo`

| VO 字段（camelCase） | 模型 HTTP 字段（snake_case） | 类型 | 说明 |
|---|---|---|---|
| `aiAdvice` | `ai_advice` | `String` | AI 建议 |

### 3.3 字段命名转换说明

- **facade 层（Dubbo）**：camelCase，符合 Java 规范。电销方走 Dubbo 调用，Java 对象序列化，无命名兼容问题
- **模型 HTTP 层**：snake_case，符合模型文档定义
- **转换位置**：`RecordMultiAnalysisConverter` 负责 camelCase ↔ snake_case 双向映射（同接口 1 的 `RecordSummaryConverter` 模式）
- **HTTP 暴露场景**：HTTP 端点仅测试用，传 JSON 时用 camelCase 字段名（与 VO 字段名一致，Jackson 默认映射）

### 3.4 内层 Map 结构说明

文档中内层 JSON 同时含 `totals` 和子标签计数（平铺在一个 map 里），如：
```json
{"totals": 20, "二级标签1": 10, "二级标签2": 20}
```

facade 请求 VO 直接用 `Map<String, Map<String, Integer>>` 透传，**不**把 `totals` 单独拎出做字段。理由：
1. 与电销方已有聚合数据结构一致，电销方无需额外转换
2. rmp 侧不需要访问 `totals` 做业务逻辑，仅透传给模型
3. Jackson 默认反序列化为 `LinkedHashMap`，保留顺序

---

## 4. 错误处理与错误码

### 4.1 错误码定义

| code | 含义 | 触发场景 |
|---|---|---|
| `200` | 成功 | 模型返回有效响应，字段映射成功 |
| `40001` | 请求参数非法 | 请求 VO 为 null / 三类特征 map 全为空 / 挂机节点 map 为空 |
| `50001` | 模型 HTTP 调用失败 | IOException、SocketTimeoutException、连接拒绝、HTTP 状态码非 200 |
| `50002` | 模型响应解析失败 | HTTP 200 但 JSON 解析异常、字段缺失、类型不匹配 |
| `50003` | 模型响应业务异常 | HTTP 200 且解析成功，但 `summary` 为空且三特征列表为空（客户特征接口）/ `ai_advice` 为空（挂机节点接口） |
| `50099` | 系统内部异常 | 未预期的 RuntimeException（如 NPE） |

**错误码规则**：
- `4xxxx`：客户端错误（参数问题）
- `5xxxx`：服务端错误（模型/系统问题）
- 与项目现有 `Response<T>` 的 `code` 字段对齐（`Response.success(data)` → code=200；`Response.fail(code, msg)` → 自定义 code）

### 4.2 失败场景处理流程

```
请求进入
  │
  ▼
参数校验
  │ 空值/空 map → Response.fail(40001, "请求参数非法: xxx")
  ▼
调模型 HTTP
  │ IOException / 非 200 → Response.fail(50001, "模型调用失败: " + 异常摘要)
  │                        + log.error("MultiAnalysis model failed", e)
  ▼
解析响应
  │ JSON 解析异常 → Response.fail(50002, "模型响应解析失败: " + 异常摘要)
  │ 字段缺失       → 走默认值（空集合/空串），不视为失败
  ▼
业务字段校验
  │ 关键字段全空 → Response.fail(50003, "模型响应业务异常: xxx 为空")
  ▼
返回 Response.success(响应 VO)
```

**与接口 1 的区别**：
- 接口 1（`receiveRecord`）：失败重试 5 次 + 进重试 topic + 告警丢弃（异步推送场景）
- 接口 2/3（本设计）：失败不重试，分类返回错误码给调用方（同步请求-响应场景，调用方自行决定是否重试）

### 4.3 异常捕获层级

**异常类型说明**：
- `IllegalArgumentException`（JDK 标准运行时异常）—— 参数校验失败
- `MultiAnalysisParseException extends RuntimeException`（新增自定义运行时异常）—— 模型响应解析失败，构造器 `(String message, Throwable cause)`
- `MultiAnalysisBusinessException extends RuntimeException`（新增自定义运行时异常）—— 业务字段校验失败，构造器 `(String message)`
- 均为运行时异常，方法签名无需声明 `throws`，避免污染 facade 接口

```java
public Response<CustFeatureAnalysisResponseVo> handleCustFeature(req) {
    try {
        // 1. 参数校验
        validate(req);  // 抛 IllegalArgumentException → 40001

        // 2. 调模型
        String modelRespJson = modelService.callModel(req);  // 内部不重试，失败返回 null
        if (modelRespJson == null) {
            return Response.fail(50001, "模型调用失败");
        }

        // 3. 解析 + 业务校验
        CustFeatureAnalysisResponseVo vo = converter.parseResponse(modelRespJson);  // 抛 MultiAnalysisParseException → 50002
        validateBusiness(vo);  // 抛 MultiAnalysisBusinessException → 50003

        return Response.success(vo);
    } catch (IllegalArgumentException e) {
        log.warn("MultiAnalysis param invalid: {}", e.getMessage());
        return Response.fail(40001, "请求参数非法: " + e.getMessage());
    } catch (MultiAnalysisParseException e) {
        log.error("MultiAnalysis model parse failed", e);
        return Response.fail(50002, "模型响应解析失败: " + e.getMessage());
    } catch (MultiAnalysisBusinessException e) {
        log.error("MultiAnalysis model business invalid", e);
        return Response.fail(50003, "模型响应业务异常: " + e.getMessage());
    } catch (Exception e) {
        log.error("MultiAnalysis system error", e);
        return Response.fail(50099, "系统内部异常: " + e.getMessage());
    }
}
```

**Converter 异常处理**：`buildXxxModelRequest` / `parseXxxResponse` 内部捕获 Jackson `JsonProcessingException`（受检异常）并包装为 `MultiAnalysisParseException`（运行时异常）抛出，避免受检异常向上传播。

### 4.4 字段缺失兼容

模型响应字段缺失与空字符串都可能发生，Converter 解析时统一兼容：
- `JsonNode.path("xxx").asText("")`：字段缺失（`MissingNode`）、值为 null、值为空串均返回空串
- `toStrList(node)`：node 为 null/`MissingNode`/`NullNode` 均返回 `Collections.emptyList()`

### 4.5 不做的事

- **不重试**：模型 HTTP 调用失败直接返回错误码
- **不告警**：不调用 `TeamsSendComponent`（同步接口，调用方可感知失败，无需告警群）
- **不幂等**：不做 Redis SETNX 去重
- **不落库**：不记录请求/响应到数据库

### 4.6 日志关键字

| 场景 | 日志关键字 | 级别 |
|---|---|---|
| 收到请求 | `MultiAnalysis received` | INFO |
| 参数校验失败 | `MultiAnalysis param invalid` | WARN |
| 模型调用成功 | `MultiAnalysis model success` | INFO |
| 模型调用失败 | `MultiAnalysis model failed` | ERROR |
| 响应解析失败 | `MultiAnalysis model parse failed` | ERROR |
| 业务字段异常 | `MultiAnalysis model business invalid` | ERROR |
| 系统异常 | `MultiAnalysis system error` | ERROR |

---

## 5. 模块/类设计

### 5.1 包结构

```
rmp-api/src/main/java/com/qihoo/finance/dirp/rmp/api/
├── facade/
│   └── ICallRecordMultiAnalysisFacade.java          # 新增：facade 接口
└── domain/multianalysis/                            # 新增：多通分析 VO 子包
    ├── CustFeatureAnalysisRequestVo.java
    ├── CustFeatureAnalysisResponseVo.java
    ├── HungupNodeAnalysisRequestVo.java
    └── HungupNodeAnalysisResponseVo.java

rmp-app/src/main/java/com/qihoo/finance/dirp/rmp/app/
├── facade/
│   └── CallRecordMultiAnalysisFacadeImpl.java       # 新增：facade 实现（@Service + @RestfulApi）
└── service/multianalysis/                           # 新增子包
    ├── RecordMultiAnalysisHandler.java              # 业务编排：参数校验 + 调模型 + 解析 + 返回
    ├── RecordMultiAnalysisModelService.java         # HTTP 调用模型（不重试）
    ├── RecordMultiAnalysisConverter.java            # VO ↔ 模型 JSON 双向转换
    ├── MultiAnalysisParseException.java             # 解析失败运行时异常
    └── MultiAnalysisBusinessException.java           # 业务校验失败运行时异常
```

**包结构说明**：
- `service/multianalysis/` 与接口 1 的 `service/recordsummary/` 平级，互不耦合
- 不复用接口 1 的 `RecordSummaryConverter` / `RecordSummaryModelService`：请求/响应结构完全不同（多通 vs 单通），强行复用会引入条件分支污染单一职责
- facade 实现放在 `rmp-app/facade/`，与现有 `DirpStrategyGroupFacadeImpl` 等平级

### 5.2 类职责

#### `CallRecordMultiAnalysisFacadeImpl`
见 2.2 节。facade 实现仅做委托。

#### `RecordMultiAnalysisHandler`
```java
@Slf4j
@Component
public class RecordMultiAnalysisHandler {

    @Autowired
    private RecordMultiAnalysisModelService modelService;
    @Autowired
    private RecordMultiAnalysisConverter converter;

    public Response<CustFeatureAnalysisResponseVo> handleCustFeature(CustFeatureAnalysisRequestVo req) {
        try {
            // 1. 参数校验
            validateCustFeature(req);  // 三类特征 map 全空 → IllegalArgumentException → 40001

            // 2. 调模型（不重试）
            String modelReqJson = converter.buildCustFeatureModelRequest(req);
            String modelRespJson = modelService.callModel(modelReqJson);
            if (modelRespJson == null) {
                return Response.fail(50001, "模型调用失败");
            }

            // 3. 解析 + 业务校验
            CustFeatureAnalysisResponseVo vo = converter.parseCustFeatureResponse(modelRespJson);  // 抛 MultiAnalysisParseException → 50002
            validateCustFeatureBusiness(vo);  // summary 空 + 三特征空 → MultiAnalysisBusinessException → 50003

            log.info("MultiAnalysis model success");
            return Response.success(vo);
        } catch (IllegalArgumentException e) {
            log.warn("MultiAnalysis param invalid: {}", e.getMessage());
            return Response.fail(40001, "请求参数非法: " + e.getMessage());
        } catch (MultiAnalysisParseException e) {
            log.error("MultiAnalysis model parse failed", e);
            return Response.fail(50002, "模型响应解析失败: " + e.getMessage());
        } catch (MultiAnalysisBusinessException e) {
            log.error("MultiAnalysis model business invalid", e);
            return Response.fail(50003, "模型响应业务异常: " + e.getMessage());
        } catch (Exception e) {
            log.error("MultiAnalysis system error", e);
            return Response.fail(50099, "系统内部异常: " + e.getMessage());
        }
    }

    // handleHungupNode 同构，略
}
```

**自定义异常类**（新增到 `rmp-app/service/multianalysis/`）：
```java
public class MultiAnalysisParseException extends RuntimeException {
    public MultiAnalysisParseException(String message, Throwable cause) { super(message, cause); }
}
public class MultiAnalysisBusinessException extends RuntimeException {
    public MultiAnalysisBusinessException(String message) { super(message); }
}
```

**要点**：
- 编排顺序：参数校验 → 调模型 → 解析 → 业务校验 → 返回
- 异常分层捕获（与 4.3 节一致）
- 不含线程池/异步：同步调用，调用方阻塞等待

#### `RecordMultiAnalysisModelService`
```java
@Slf4j
@Component
public class RecordMultiAnalysisModelService {

    @Value("${record.summary.model.url:}")
    private String modelUrl;
    @Value("${record.summary.model.token:}")
    private String modelToken;
    @Value("${record.summary.model.connect-timeout:5000}")
    private int connectTimeout;
    @Value("${record.summary.model.read-timeout:30000}")
    private int readTimeout;

    /**
     * 调用模型 HTTP（不重试）
     * @param modelReqJson 已组装好的模型请求 JSON
     * @return 模型响应 JSON；失败返回 null
     */
    public String callModel(String modelReqJson) {
        try {
            // 复用接口 1 的 HttpUtil.httpClient(...)
            return HttpUtil.httpClient(modelUrl, modelReqJson, modelToken, connectTimeout, readTimeout);
        } catch (Exception e) {
            log.error("MultiAnalysis model failed: {}", e.getMessage());
            return null;
        }
    }
}
```

**要点**：
- **复用接口 1 的 Apollo 配置项**：`record.summary.model.url/token/connect-timeout/read-timeout`
- **复用 `HttpUtil.httpClient(...)`**：与接口 1 同款 HTTP 工具
- **不重试**：失败返回 null，由 handler 决定错误码
- **不校验 HTTP 状态码 / 响应体**：交给 `Converter.parse` 时若解析失败抛 `ParseException` → 50002

#### `RecordMultiAnalysisConverter`
```java
@Component
public class RecordMultiAnalysisConverter {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    /**
     * 客户特征：VO → 模型请求 JSON（snake_case）
     */
    public String buildCustFeatureModelRequest(CustFeatureAnalysisRequestVo req) {
        try {
            ObjectNode root = MAPPER.createObjectNode();
            root.set("raw_prospective_cust_feature", MAPPER.valueToTree(req.getRawProspectiveCustFeature()));
            root.set("raw_objecting_cust_feature", MAPPER.valueToTree(req.getRawObjectingCustFeature()));
            root.set("raw_failed_cust_feature", MAPPER.valueToTree(req.getRawFailedCustFeature()));
            return root.toString();
        } catch (Exception e) {
            throw new MultiAnalysisParseException("构建客户特征模型请求失败: " + e.getMessage(), e);
        }
    }

    /**
     * 客户特征：模型响应 JSON → VO
     * @throws MultiAnalysisParseException JSON 解析失败
     */
    public CustFeatureAnalysisResponseVo parseCustFeatureResponse(String json) {
        try {
            JsonNode root = MAPPER.readTree(json);
            CustFeatureAnalysisResponseVo vo = new CustFeatureAnalysisResponseVo();
            vo.setProspectiveCustFeature(toStrList(root.get("prospective_cust_feature")));
            vo.setObjectingCustFeature(toStrList(root.get("objecting_cust_feature")));
            vo.setFailedCustFeature(toStrList(root.get("failed_cust_feature")));
            vo.setAssitantPerformance(root.path("assitant_performance").asText(""));
            vo.setConversionBreakpoint(root.path("conversion_breakpoint").asText(""));
            vo.setSummary(root.path("summary").asText(""));
            return vo;
        } catch (Exception e) {
            throw new MultiAnalysisParseException("解析客户特征模型响应失败: " + e.getMessage(), e);
        }
    }

    /**
     * 挂机节点：VO → 模型请求 JSON（直接以 Map 为 root）
     */
    public String buildHungupNodeModelRequest(HungupNodeAnalysisRequestVo req) {
        try {
            return MAPPER.writeValueAsString(req.getNodeFeatureMap());
        } catch (JsonProcessingException e) {
            throw new MultiAnalysisParseException("构建挂机节点模型请求失败: " + e.getMessage(), e);
        }
    }

    /**
     * 挂机节点：模型响应 JSON → VO
     * @throws MultiAnalysisParseException JSON 解析失败
     */
    public HungupNodeAnalysisResponseVo parseHungupNodeResponse(String json) {
        try {
            JsonNode root = MAPPER.readTree(json);
            HungupNodeAnalysisResponseVo vo = new HungupNodeAnalysisResponseVo();
            vo.setAiAdvice(root.path("ai_advice").asText(""));
            return vo;
        } catch (Exception e) {
            throw new MultiAnalysisParseException("解析挂机节点模型响应失败: " + e.getMessage(), e);
        }
    }

    private List<String> toStrList(JsonNode node) {
        if (node == null || node.isNull() || node.isMissingNode()) return Collections.emptyList();
        List<String> list = new ArrayList<>();
        node.forEach(e -> list.add(e.asText("")));
        return list;
    }
}
```

**要点**：
- 手动做 snake_case ↔ camelCase 映射（不依赖 `@JsonProperty` 注解污染 VO，保持 VO 纯净）
- `assitant_performance` 保留原文拼写（与接口 1 设计文档 3.1 节 `assitant` 拼写保留一致）
- 挂机节点请求直接以 Map 为 JSON root，与文档格式一致
- `JsonNode.path("xxx").asText("")`：字段缺失（`MissingNode`）、值为 null、值为空串均返回空串，统一兼容

### 5.3 现有代码复用

| 复用项 | 用途 | 说明 |
|---|---|---|
| `HttpUtil.httpClient(...)` | HTTP POST 调用模型 | 与接口 1 同款 |
| `record.summary.model.*` Apollo 配置 | URL/Token/超时 | 与接口 1 共享 |
| `Response<T>` / `Response.fail(code, msg)` | 统一响应包装 | 项目规范 |
| `@RestfulApi` / `@RestfulInterfaceApi` | Dubbo ↔ HTTP 映射 | 由 `DubboRestfulApiResourceLoaderComponent` 扫描注册 |
| `@Service` (Dubbo) | 服务暴露 | 双集群 `zj` / `zjb` |

### 5.4 不新增的内容

- 不新增 Apollo 配置项（复用 `record.summary.model.*`）
- 不新增线程池（同步调用）
- 不新增 Kafka topic（无重试/异步场景）
- 不新增 `@Reference` 引用（rmp 作为提供方，不消费外部 Dubbo）
- 不新增 Maven 依赖（HTTP 工具、Jackson 都已有）

---

## 6. 测试要点

### 6.1 客户特征接口（`analyzeCustFeature`）

| # | 场景 | 输入构造 | 预期结果 |
|---|---|---|---|
| 1 | 正常链路 | 三类特征 map 各含 2 个一级标签，每个含 `totals` + 2 个子标签计数 | `Response.success(vo)`，6 个字段全部映射正确（snake_case → camelCase） |
| 2 | 参数非法-空对象 | `request = null` | `Response.fail(40001)`，日志含 `param invalid` |
| 3 | 参数非法-三类 map 全空 | 三类特征 map 均 `Collections.emptyMap()` | `Response.fail(40001)` |
| 4 | 参数合法-部分类型为空 | 仅 `rawProspectiveCustFeature` 非空，另两类为空 map | `Response.success(vo)`（允许部分类型为空，模型自行处理） |
| 5 | 模型 HTTP 调用失败 | mock `HttpUtil` 抛 IOException | `Response.fail(50001)`，日志含 `model failed` |
| 6 | 模型响应解析失败 | mock 模型返回非 JSON 字符串 `"not a json"` | `Response.fail(50002)`，日志含 `model parse failed` |
| 7 | 模型响应字段缺失 | mock 模型返回 `{}`，所有字段缺失 | `Response.success(vo)`，各字段为空集合/空串（不视为失败） |
| 8 | 模型响应业务异常 | mock 模型返回 `summary=""` 且三特征列表为空 | `Response.fail(50003)`，日志含 `business invalid` |
| 9 | 系统异常 | mock converter 抛 NPE | `Response.fail(50099)`，日志含 `system error` |
| 10 | 字段命名转换 | 构造含 `assitant_performance` 的模型响应 | VO 的 `assitantPerformance` 正确映射（保留 `assitant` 拼写） |
| 11 | 内层 map 结构 | 构造内层 map 含 `totals` + 子标签 | 透传给模型请求 JSON 时结构不变（`totals` 不被单独提取） |
| 12 | 字段缺失兼容 | mock 模型返回 `{}` | VO 各字段为空集合/空串（不抛 50002） |

### 6.2 挂机节点接口（`analyzeHungupNode`）

| # | 场景 | 输入构造 | 预期结果 |
|---|---|---|---|
| 13 | 正常链路 | `nodeFeatureMap` 含 2 个挂机节点（如"开场白挂断"/"异议处理挂断"），各含 `totals` + 3 个关注点计数 | `Response.success(vo)`，`aiAdvice` 正确映射 |
| 14 | 参数非法-空对象 | `request = null` | `Response.fail(40001)` |
| 15 | 参数非法-map 为空 | `nodeFeatureMap = emptyMap()` | `Response.fail(40001)` |
| 16 | 模型 HTTP 调用失败 | mock `HttpUtil` 抛 SocketTimeoutException | `Response.fail(50001)` |
| 17 | 模型响应解析失败 | mock 模型返回非 JSON | `Response.fail(50002)` |
| 18 | 模型响应业务异常 | mock 模型返回 `ai_advice=""` | `Response.fail(50003)` |
| 19 | 请求 JSON root 结构 | 构造 `nodeFeatureMap` | 模型请求 JSON 直接以 map 为 root（不外包一层字段名） |

### 6.3 Dubbo / HTTP 暴露层

| # | 场景 | 验证点 |
|---|---|---|
| 20 | Dubbo 服务注册 | `@Service(registry = {"zj", "zjb"})` 生效，两个集群都能消费到 |
| 21 | HTTP 映射生成 | `@RestfulApi` + `@RestfulInterfaceApi` 被 `DubboRestfulApiResourceLoaderComponent` 扫描，Redis 缓存写入映射关系 |
| 22 | HTTP 端点可调 | POST `/callRecordMultiAnalysis/analyzeCustFeature` 可正常返回 |
| 23 | HTTP 端点可调 | POST `/callRecordMultiAnalysis/analyzeHungupNode` 可正常返回 |
| 24 | 鉴权关闭 | `verifyAuth = false` 生效，HTTP 调用不带 token 也能通过 |

### 6.4 测试方式

- **单元测试**：`RecordMultiAnalysisHandler` / `RecordMultiAnalysisConverter` 用 Mockito mock `ModelService` / `HttpUtil`，覆盖 1-19 号场景
- **集成测试**：启动 rmp-app，用 Dubbo 直连或 HTTP 调用验证 20-24 号场景
- **不做的测试**：不测真实模型 HTTP 调用（依赖外部服务，CI 不稳定）

---

## 7. 风险与待确认

| 项 | 风险/待确认 | 缓解 |
|---|---|---|
| 模型端点是否支持多通输入格式 | 已确认同一端点支持多通格式，后续模型方优化提示词补充 | 已确认，无风险 |
| 电销方调用方式 | Dubbo 调用（HTTP 仅测试用） | 已确认，字段命名兼容性无风险 |
| 模型响应字段缺失与空字符串 | 都可能发生 | Converter 用 `JsonNode.path().asText("")` 统一兼容，已覆盖 |
| 模型调用超时 60s 是否足够 | Dubbo `@Service(timeout=60000)` + `@RestfulInterfaceApi(timeout=60000)`，模型 read-timeout 30s。若模型偶发慢响应（>30s）会先触发 HTTP 客户端超时返回 50001 | 监控 `MultiAnalysis model failed` 日志频率，若频发慢响应，考虑调大 `record.summary.model.read-timeout` 或 facade timeout |
| 双集群注册影响 | `registry = {"zj", "zjb"}` 双集群暴露，若其中一集群 ZooKeeper 不可用，服务是否仍正常注册到另一集群 | Dubbo 默认行为：单集群失败不影响其他集群注册；上线前确认两集群连通性 |
| 接口 1 vs 接口 2/3 模型配置耦合 | 复用 `record.summary.model.*` 配置，若接口 1 调整 URL/Token 会影响接口 2/3 | 设计预期一致（同模型同端点）；若后续模型方为多通格式分配独立端点，需拆分配置项 |
| `assitant` 拼写 | 模型响应字段为 `assitant_performance`（拼写错误），VO 保留为 `assitantPerformance` | 已与接口 1 设计一致保留原文；可在 VO javadoc 标注"拼写按模型文档保留" |

### 7.1 上线前联调确认

1. ~~模型方是否在同一端点支持多通格式~~（已确认支持）
2. ~~电销方调用方式（Dubbo vs HTTP）~~（已确认 Dubbo）
3. 模型响应字段缺失/空串的真实行为（Converter 已统一兼容，联调时验证测试用例 12）

---

## 8. 与接口 1 的关系

| 维度 | 接口 1（已实现） | 接口 2/3（本设计） |
|---|---|---|
| 调用方向 | rmp 主动推送 → 电销 | 电销主动调用 → rmp |
| facade 提供方 | 电销方（`CallRecordSummaryFacade`） | rmp（`ICallRecordMultiAnalysisFacade`） |
| 调用方式 | Kafka 消费 + Dubbo 推送 + 重试 topic | Dubbo 同步调用 |
| 模型输入格式 | 单通（通话录音转写） | 多通（三类客户特征聚合 / 挂机节点聚合） |
| 模型 HTTP 配置 | `record.summary.model.*` | 复用 `record.summary.model.*` |
| 重试策略 | HTTP 5 次指数退避 + Dubbo 5 次退避 topic | 不重试，分类返回错误码 |
| 幂等 | Redis SETNX 5 分钟去重 | 不做幂等 |
| 告警 | TeamsSendComponent 告警 | 不告警 |
