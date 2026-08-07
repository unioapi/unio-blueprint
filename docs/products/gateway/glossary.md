---
title: Gateway（网关）词汇表
description: 网关当前领域术语及其实现边界。
status: active
owner: 网关团队
last_updated: 2026-08-07
related:
  - README.md
  - overview.md
  - ../../architecture/glossary.md
  - decisions/adr-0012-provider-channel-route-lifecycle.md
  - decisions/adr-0002-route-product-pricing.md
  - decisions/adr-0005-request-identity.md
  - decisions/adr-0017-authoritative-first-token.md
---

# Gateway（网关）词汇表

## 领域术语

| 术语                        | 当前定义                                                                                         |
| ------------------------- | -------------------------------------------------------------------------------------------- |
| User Account（用户账户）        | 当前认证、余额和 API Key 的归属主体。                                                                      |
| Client Application（客户端应用） | 使用 API Key 调用公开 API 的程序。                                                                     |
| Project（项目）               | 历史来源中的应用与用量归集概念；当前 Schema 和认证路径没有该身份层。                                                       |
| API Key                   | 客户端凭据；直接归属 User Account 并显式绑定一条 Route。                                                       |
| Protocol（协议）              | API 格式族。当前 ingress 值为 `openai` 或 `anthropic`。                                                |
| Endpoint（端点）              | Gateway 公开的 API 操作或路径，每个 Endpoint 归属一个 Protocol。                                             |
| Provider（服务商）             | 上游供给主体；保存唯一 `origin`、地址/状态 revision、围栏和公共 breaker 故障域，并归属 Channel。                           |
| Origin（上游根地址）             | Provider 上的 URL 值，不是独立领域实体；同一地址全局唯一。                                                         |
| Channel（渠道）               | 归属一个 Provider，保存上游凭据、Protocol、Adapter、模型映射、成本和运行控制事实。                                        |
| Candidate（候选）             | Route 内一个 Channel 与其上游模型映射形成的可尝试项。                                                           |
| Route（线路）                 | API Key 绑定的客户定价与供给边界，保存模式和显式 Channel 池。                                                      |
| Model（模型）                 | 客户请求的模型标识，关联基准价格与模型能力声明。                                                                     |
| Channel Model Binding（渠道模型绑定） | Channel 到本地 Model 的路由边，保存真实上游模型名和独立启停状态；新绑定固定停用，当前验证成功后才可人工启用。 |
| Upstream Model Snapshot（上游模型快照） | 某 Channel 最近一次成功模型列表发现的结果；与客户 `/v1/models`、本地 Model 和运行绑定相互独立。 |
| Trace ID                  | 一次入口 HTTP 请求采用并回传的 `X-Request-ID`；日志字段为 `trace_id`，从认证前贯穿到响应结束，但不承担数据库或账务身份。               |
| Request（请求）               | 生成或压缩调用进入持久生命周期后的端到端业务记录。                                                                    |
| Request ID                | `request_records` 创建成功后使用的 `req_...` 文本业务标识；日志字段为 `request_id`，一个 Trace ID 在正常生成请求中对应一个 Request ID。 |
| Attempt（尝试）               | Request 对一个 Candidate 发起的一次真实上游 transport。                                                   |
| Attempt ID                | 已创建 Attempt 的数据库 bigint 主键；日志字段为 `attempt_id`，一个 Request ID 可以对应多个 Attempt ID。                            |
| Upstream Request ID       | 上游为某次 Attempt 返回的可选请求标识；日志字段为 `upstream_request_id`，不参与 Gateway 路由、Sticky、幂等或计费。                   |
| AttemptPermit（候选许可）       | Candidate 在 transport 前原子取得的并发、breaker、cooldown、permission 与 revision 资格；取得后才创建 Attempt。     |
| Routing Trace（路由过程）       | 与 Request 一对一绑定的结构化决策记录，保存候选资格、五项评分、扫描、Sticky、容量等待和最终结果。                                     |
| Sticky Binding（粘性绑定）      | 以 Protocol、Route、API Key、Model 和会话键哈希隔离的 Channel 亲和提示；通过 Channel 与 binding version 的 CAS 修改。 |
| Usage（用量）                 | Gateway 保存并用于计费、限额或审计的计量事实。                                                                  |
| Price Snapshot（价格快照）      | Request 锁定的客户 token 价格向量、Route 倍率和公式版本。                                                      |
| Cost Snapshot（成本快照）       | Attempt 锁定的 Channel token 成本向量、倍率和来源事实。                                                      |
| Capability（能力）            | 模型目录声明或 Adapter operation capability；两者分别存储并由不同路径读取。                                         |
| 有效生成 Token                | 按协议判定会改变最终模型输出的生成负载；长度大于零即有效，不做 TrimSpace。                                                   |
| 上游 TTFT                   | 单次 Attempt 从 transport start 到成功解析首个有效生成 Token 的耗时；驱动首字超时与渠道评分。                              |
| Gateway TTFT              | 一次 Request 从业务 `started_at` 到首个有效生成 Token 成功写入客户响应的耗时；驱动 Dashboard 与请求展示。                    |
| 前导帧（prelude）              | 权威首字之前的协议事件（如 `message_start`、`response.created`、role-only）；首字前暂存，失败时丢弃。                     |

`ProviderEndpoint` 与 `Provider Origin` 是已被
[ADR-0012](decisions/adr-0012-provider-channel-route-lifecycle.md) 取代的历史实体名称。当前 `origin` 仅指
Provider 上的上游根地址字段；Endpoint 仍只指 Gateway 对外 API 操作或路径。

上游 TTFT 与 Gateway TTFT 的判定、字段和计费边界见
[ADR-0017](decisions/adr-0017-authoritative-first-token.md)。
四种请求关联 ID 的传播与一对多关系见
[ADR-0005](decisions/adr-0005-request-identity.md)。
