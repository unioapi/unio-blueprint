---
title: Website（官网）页面设计
description: 官网页面与用户旅程的索引和所有权规则。
status: active
owner: 官网团队
last_updated: 2026-07-24
related:
  - ../README.md
  - ../overview.md
  - ../../../templates/page-design.md
  - ../../../specifications/navigation.md
  - ../../docs-site/README.md
  - ../../console/README.md
---

# Website（官网）页面设计

## 目的

定义官网页面和跨页面旅程的目标、内容、状态与交互。

## 范围

官网自有页面设计、与具体路由无关的旅程、内容要求和验收标准。

## 职责

- 为每个页面或旅程建立唯一权威设计。
- 将共享模式链接到平台规范。
- 覆盖响应式、无障碍、加载、空状态和错误状态。

## 适合存放的内容

- 使用[页面设计模板](../../../templates/page-design.md)创建的官网页面设计。
- 官网用户旅程图和页面级内容模型。

## 不应存放的内容

- 组件源码、框架路由、共享 UI 规范或其他产品领域负责的页面。

## 当前确认的一级入口

| 入口 | 类型 | 权威领域 | 页面设计状态 |
| --- | --- | --- | --- |
| Home（首页） | 官网自有页面 | Website（官网） | 内容待讨论，尚未建立页面设计文档 |
| Pricing（定价） | 官网自有页面 | Website（官网） | 暂时保留，订阅套餐确定后再完善 |
| Docs（文档） | 跨产品入口 | [Documentation Site（文档站）](../../docs-site/README.md) | 不在本目录建立重复页面设计 |
| Console（用户控制台） | 跨产品入口 | [Console（用户控制台）](../../console/README.md) | 不在本目录建立重复页面设计 |

当前列表只确认入口及其所有权，不确认完整网站地图、导航顺序、URL 或交付状态。
具体边界见[官网概览](../overview.md)。

## 后续建档规则

- Home（首页）和 Pricing（定价）的内容开始设计时，使用
  [页面设计模板](../../../templates/page-design.md)分别建立权威页面文档。
- Docs（文档）和 Console（用户控制台）的产品设计必须维护在各自产品领域；本目录只记录
  官网如何提供入口。
- 内容尚未进入讨论的页面不提前创建空白占位文档。
