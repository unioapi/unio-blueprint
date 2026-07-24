---
title: Gateway（网关）功能设计
description: 网关自有功能与内部调度行为的产品级设计索引。
status: active
owner: 网关团队
last_updated: 2026-07-24
related:
  - ../README.md
  - ../overview.md
  - ../../../templates/feature-design.md
---

# Gateway（网关）功能设计

## 目的

集中维护网关自有功能与内部调度行为的产品级设计，说明"做什么、为什么这样做"，
供实现、评审与运营引用。

## 范围

网关在流量处理链路上的跨请求行为设计：路由负载均衡、准入与限流、熔断与故障域
隔离等调度逻辑及其依据。

## 职责

- 用产品/设计语言描述网关关键行为的逻辑与取舍。
- 为每个功能保留唯一权威说明，避免多处重复。
- 将具体实现留在网关代码仓库，只在此约束其行为。

## 适合存放的内容

- 使用[功能设计模板](../../../templates/feature-design.md)编写的网关功能设计。
- 调度算法、权重公式、状态机等行为级说明与设计依据。

## 不应存放的内容

- 源代码、文件路径、处理器清单或代码生成的 Schema。
- 共享 API 规范或平台架构（分别归 specifications 与 architecture）。
- Console / Admin 等其他领域负责的界面与流程。

## 目录

- [路由负载均衡（balanced 权重调度）](routing-load-balancing.md)
