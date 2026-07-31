---
title: Gateway（网关）领域决策
description: 只影响网关领域的架构决策索引。
status: active
owner: 网关团队
last_updated: 2026-07-31
related:
  - ../README.md
  - ../../../decisions/README.md
  - ../../../templates/adr.md
---

# Gateway（网关）领域决策

## 目的

记录影响范围完全位于网关领域内的长期选择。

## 范围

网关产品架构、契约行为、流量职责和领域内部技术约束。

## 职责

- 保存决策背景、备选方案与影响。
- 链接受影响的设计、质量目标和路线图事项。
- 将跨领域选择提升为全局决策。

## 适合存放的内容

- 网关领域已提议、接受、取代或拒绝的 ADR。
- 不会对其他产品领域施加规则的决策。

## 不应存放的内容

- 平台级选择、临时笔记或实现任务。
- 由其他产品领域负责的决策。

## 决策索引

| ADR | 状态 | 主题 |
| --- | --- | --- |
| [ADR-0001](adr-0001-domain-terminology.md) | active | 统一协议、端点与历史 Provider Origin 术语；供给模型部分被 ADR-0012 取代。 |
| [ADR-0002](adr-0002-route-product-pricing.md) | active | API Key 绑定的 Route 供给、调度与客户定价边界。 |
| [ADR-0003](adr-0003-billing-settlement.md) | active | 预付授权、token 结算、补扣/核销、快照与恢复边界。 |
| [ADR-0004](adr-0004-model-capabilities.md) | active | 模型能力声明与运行时可执行能力分离。 |
| [ADR-0005](adr-0005-request-identity.md) | active | HTTP correlation ID、持久业务请求 ID 与数据库关系键分离。 |
| [ADR-0006](adr-0006-protocol-adapter-boundary.md) | active | 公开协议、Adapter registry、原生与桥接路径的当前边界。 |
| [ADR-0007](adr-0007-atomic-admission-control.md) | active | 请求和候选两层原子准入及当前收口限制。 |
| [ADR-0008](adr-0008-runtime-state-fencing.md) | superseded | 历史 Provider Origin、Channel、control 与 runtime epoch 围栏。 |
| [ADR-0009](adr-0009-objective-balanced-routing.md) | superseded | 历史 Balanced 加权随机、成本因子与准入时序。 |
| [ADR-0010](adr-0010-upstream-breaker-attribution.md) | superseded | 历史 Origin/Channel 上游结果归因与 breaker 状态机。 |
| [ADR-0011](adr-0011-runtime-deployment-boundaries.md) | active | 当前进程、依赖、健康探针与运行控制边界。 |
| [ADR-0012](adr-0012-provider-channel-route-lifecycle.md) | active | Provider、Channel 与 Route 的供给关系与生命周期。 |
| [ADR-0013](adr-0013-provider-runtime-fencing.md) | active | Provider 双 revision、Channel、control 与 runtime epoch 围栏。 |
| [ADR-0014](adr-0014-provider-breaker-attribution.md) | active | Provider 与 Channel breaker、证据和独立反馈归因。 |
| [ADR-0015](adr-0015-deterministic-cost-aware-routing.md) | superseded | 历史四项客观分、Channel Sticky 与 Sticky 首候选短等。 |
| [ADR-0016](adr-0016-five-factor-routing-and-cas-sticky.md) | active | 五项客观分、原子并发与全池短等、CAS Sticky 和完整 trace。 |
| [ADR-0017](adr-0017-authoritative-first-token.md) | active | 权威首字判定、前导帧缓冲、上游 TTFT 与 Gateway TTFT 拆分。 |

新建时使用 [ADR 模板](../../../templates/adr.md)。
