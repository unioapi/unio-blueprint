---
title: "ADR-0001：统一领域术语（协议 / 端点 / 上游源站）"
description: "记录 Gateway 当前协议、端点与 Provider Origin 的领域含义。"
status: active
owner: 网关团队
last_updated: 2026-07-26
related:
  - README.md
  - ../glossary.md
  - ../features/routing-load-balancing.md
  - adr-0009-objective-balanced-routing.md
  - adr-0011-runtime-deployment-boundaries.md
  - ../../../templates/adr.md
---

# ADR-0001：统一领域术语（协议 / 端点 / 上游源站）

## 范围

本文记录 Gateway 当前代码、Schema 与公开路由中 Protocol、Endpoint 和 Provider Origin 的含义。

## 当前术语

| 术语 | 当前含义 | 当前实现事实 |
| --- | --- | --- |
| Protocol（协议） | 公开请求与响应的 API 格式族 | 当前取值为 `openai` 与 `anthropic`；Channel 保存一个 protocol，Adapter registry 也按 protocol 分组。 |
| Endpoint（端点） | Gateway 对外的一项 API 操作或路径 | 例如 Chat Completions、Responses、Responses Compact、Responses Input Tokens 和 Messages；一个端点归属一个公开协议族。 |
| Provider Origin（上游源站） | 上游 API 根地址及公共网络/服务故障域 | `provider_origins` 保存规范化 `base_url` 与独立 revision；Channel 通过 `provider_origin_id` 绑定一个 Origin。 |

Provider 表示上游供给或结算主体，不保存 Channel 的凭据与适配选择，也不直接保存 `base_url`。Channel 保存
凭据、`protocol`、`adapter_key` 和成本配置，并挂在一个 Provider Origin 上。一个 Protocol 包含多个 Endpoint；
Channel 是否能服务某个 Endpoint 由当前 `(protocol, adapter_key, operation capability)` 决定。

Balanced 路由的 stream-only TTFT EWMA 只保存在 Channel 运行态并从 Channel 快照参与评分。Provider Origin
保存 Origin breaker 与围栏事实，不保存该 TTFT EWMA。请求客户首帧时间和 request attempt 的上游首 token 时间
是独立事实。

`ProviderEndpoint` 只作为历史来源名称保留；当前 Blueprint 与 Gateway 管理/运行代码使用 Provider Origin。
权威定义同时维护在[网关词汇表](../glossary.md)。

## 代码与 Schema 证据

当前 Schema 包含 `providers`、`provider_origins`、`channels` 与 `provider_origin_id` 外键；Channel protocol 受
`openai`/`anthropic` 约束。公开 Router 注册各 Endpoint，Gateway lifecycle 按 ingress protocol、Endpoint 与
Adapter operation capability 选择候选和执行路径。

## 取代关系

- 取代：无
- 被取代：无
- 迁移事实校正：2026-07-26 按当前代码、Redis 写入脚本和评分读取链路，移除“Provider Origin 承载
  流式 TTFT EWMA”的旧表述；这是现状校正，不建立 ADR 取代关系。

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码、Schema 与现有测试接收为 `active`。

## 参考资料

- [路由负载均衡（balanced 权重调度）](../features/routing-load-balancing.md)
- [网关词汇表](../glossary.md)
- [ADR-0009：客观 Balanced 路由](adr-0009-objective-balanced-routing.md)
- [ADR-0011：运行时部署边界](adr-0011-runtime-deployment-boundaries.md)
