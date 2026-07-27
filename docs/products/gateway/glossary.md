---
title: Gateway（网关）词汇表
description: 网关当前领域术语及其实现边界。
status: active
owner: 网关团队
last_updated: 2026-07-27
related:
  - README.md
  - overview.md
  - ../../architecture/glossary.md
  - decisions/adr-0012-provider-channel-route-lifecycle.md
  - decisions/adr-0002-route-product-pricing.md
---

# Gateway（网关）词汇表

## 领域术语

| 术语 | 当前定义 |
| --- | --- |
| User Account（用户账户） | 当前认证、余额和 API Key 的归属主体。 |
| Client Application（客户端应用） | 使用 API Key 调用公开 API 的程序。 |
| Project（项目） | 历史来源中的应用与用量归集概念；当前 Schema 和认证路径没有该身份层。 |
| API Key | 客户端凭据；直接归属 User Account 并显式绑定一条 Route。 |
| Protocol（协议） | API 格式族。当前 ingress 值为 `openai` 或 `anthropic`。 |
| Endpoint（端点） | Gateway 公开的 API 操作或路径，每个 Endpoint 归属一个 Protocol。 |
| Provider（服务商） | 上游供给主体；保存唯一 `origin`、地址/状态 revision、围栏和公共 breaker 故障域，并归属 Channel。 |
| Origin（上游根地址） | Provider 上的 URL 值，不是独立领域实体；同一地址全局唯一。 |
| Channel（渠道） | 归属一个 Provider，保存上游凭据、Protocol、Adapter、模型映射、成本和运行控制事实。 |
| Candidate（候选） | Route 内一个 Channel 与其上游模型映射形成的可尝试项。 |
| Route（线路） | API Key 绑定的客户定价与供给边界，保存模式和显式 Channel 池。 |
| Model（模型） | 客户请求的模型标识，关联基准价格与模型能力声明。 |
| Request（请求） | 生成或压缩调用进入持久生命周期后的端到端业务记录。 |
| Attempt（尝试） | Request 对一个 Candidate 发起的一次真实上游 transport。 |
| Usage（用量） | Gateway 保存并用于计费、限额或审计的计量事实。 |
| Price Snapshot（价格快照） | Request 锁定的客户 token 价格向量、Route 倍率和公式版本。 |
| Cost Snapshot（成本快照） | Attempt 锁定的 Channel token 成本向量、倍率和来源事实。 |
| Capability（能力） | 模型目录声明或 Adapter operation capability；两者分别存储并由不同路径读取。 |

`ProviderEndpoint` 与 `Provider Origin` 是已被
[ADR-0012](decisions/adr-0012-provider-channel-route-lifecycle.md) 取代的历史实体名称。当前 `origin` 仅指
Provider 上的上游根地址字段；Endpoint 仍只指 Gateway 对外 API 操作或路径。
