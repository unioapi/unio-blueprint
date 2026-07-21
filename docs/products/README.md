---
title: Product Domains（产品领域）
description: UnioAPI 所有产品领域的统一入口与所有权边界。
status: active
owner: 产品团队
last_updated: 2026-07-21
related:
  - ../README.md
  - ../architecture/overview.md
  - ../specifications/README.md
---

# Product Domains（产品领域）

## 目的

为 UnioAPI 所有长期产品领域提供统一入口，同时保持每个领域独立维护。

## 范围

Website、Documentation Site、Console、Admin、Gateway 和 SDK 六个产品领域。

## 职责

- 按产品而不是代码仓库组织长期知识。
- 明确各领域的职责、边界和权威文档。
- 为所有领域维持一致的内部文档结构。
- 将跨产品规则链接到平台架构、规范和全局决策。

## 适合存放的内容

- 产品领域目录及其统一导航。
- 领域概览、路线图、词汇、质量要求、决策、页面、图示和资源。
- 只影响单一产品领域的长期知识。

## 不应存放的内容

- 平台级架构、共享规范或全局决策。
- 按代码仓库划分的实现说明。
- 同一概念在多个产品领域中的重复副本。

## 领域目录

| 领域                                             | 范围            |
| ---------------------------------------------- | ------------- |
| [Website（官网）](website/README.md)               | 面向公众的官网产品知识   |
| [Documentation Site（文档站）](docs-site/README.md) | 面向开发者发布的文档体验  |
| [Console（用户控制台）](console/README.md)            | 面向客户的管理体验     |
| [Admin（管理后台）](admin/README.md)                 | 面向内部人员的运营体验   |
| [Gateway（网关）](gateway/README.md)               | API 流量与平台网关行为 |
| [SDK（软件开发工具包）](sdk/README.md)                  | 开发者类库与集成体验    |

## 统一结构

每个产品领域必须包含 `README.md`、`overview.md`、`roadmap.md`、`glossary.md`、
`quality.md`，以及 `decisions/`、`pages/`、`diagrams/` 和 `assets/`。
