---
title: Gateway（网关）功能设计
description: 网关自有功能与内部调度行为的产品级设计索引。
status: active
owner: 网关团队
last_updated: 2026-07-31
related:
  - ../README.md
  - ../overview.md
  - ../../../templates/feature-design.md
---

# Gateway（网关）功能设计

## 目的

集中维护 Gateway 当前已经实现的功能契约和内部调度行为，供代码改造、评审与运营引用。
当前代码、Schema 和测试是实现事实的唯一证据。

## 范围

Gateway 的公开入口、Provider 映射、请求与账务生命周期、模型目录、数据生命周期，以及路由、准入、
熔断和运行控制等跨请求行为。

## 职责

- 用领域语言准确描述当前 Gateway 行为、状态机、算法和边界。
- 为每个功能保留唯一权威说明，避免多处重复。
- 代码改造完成且测试通过后，把改变后的事实归档到对应文档；文档不预先声明未实现行为。

## 适合存放的内容

- 当前公开契约、映射规则、状态机、调度算法、权重公式和数据生命周期。
- 由当前代码、Schema 或测试证明的当前边界。

## 不应存放的内容

- 源代码、文件路径、处理器清单或代码生成的 Schema。
- 共享 API 规范或平台架构（分别归 specifications 与 architecture）。
- Console / Admin 等其他领域负责的界面与流程。

## 目录

| 功能设计 | 状态 | 权威内容 |
| --- | --- | --- |
| [访问控制](access-control.md) | active | API Key、用户账户、线路的当前边界、历史 Project 概念和请求身份。 |
| [公开 API 契约](public-api-contracts.md) | active | 公开入口、认证、请求标识与协议包络。 |
| [协议兼容性](protocol-compatibility.md) | active | OpenAI、Anthropic 与 Responses 的 Unio 特有兼容行为。 |
| [Provider 适配](provider-adaptation.md) | active | Adapter 职责、注册分流、Provider 路径、输入估算与 usage 归一。 |
| [Provider 映射契约](provider-mapping-contracts.md) | active | OpenAI、Anthropic 与 DeepSeek 的稳定字段、流式、错误和计量差异。 |
| [请求生命周期](request-lifecycle.md) | active | 从身份确认、路由和调用到交付、结算与恢复。 |
| [错误语义](error-semantics.md) | active | 内部错误分类、公开错误和路由结果聚合。 |
| [预付账务与结算](billing-settlement.md) | active | 授权、结算、核销、快照和恢复不变量。 |
| [模型能力与目录](model-capabilities-catalog.md) | active | 外部目录、能力字典、模型声明与 Adapter 画像边界。 |
| [准入控制](admission-control.md) | active | 请求层与候选层的原子资源取得和收口。 |
| [路由负载均衡](routing-load-balancing.md) | active | balanced 五项客观分、原子并发、CAS Sticky、分阶段超时与完整 trace。 |
| [熔断与韧性](resilience-circuit-breakers.md) | active | 上游责任归因、breaker 与恢复退避。 |
| [运行控制与恢复](runtime-control-recovery.md) | active | 配置代际、围栏、发布和 fail-closed 恢复。 |
| [数据生命周期](data-lifecycle.md) | active | Provider、Channel 与 Route 的归档、恢复和引用保护。 |

状态以各文档的 Front Matter 为准。`active` 确认文中记录的是当前实现事实。改变 Gateway 行为时，先在
Gateway 编写临时改造计划；实现和测试通过后再更新本目录。
