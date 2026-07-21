---
title: 蓝图文档总览
description: UnioAPI 知识系统的导航与权责地图。
status: active
owner: 平台团队
last_updated: 2026-07-21
related:
  - ../README.md
  - specifications/documentation.md
---

# 蓝图文档总览

## 目的

为所有需要长期维护的 UnioAPI 知识提供统一入口。

## 范围

本目录包含平台架构、共享规范、产品领域文档、路线图、决策、模板和共享资源。

## 职责

- 将读者引导到每个主题唯一的权威位置。
- 区分平台级规则与领域自有知识。
- 在代码仓库变化时保持知识导航稳定。
- 明确展示文档负责人和生命周期。

## 适合存放的内容

- 超越单个代码仓库、具有长期价值的产品和架构知识。
- 已接受或待评审的规范与决策。
- 计划、设计方案和可复用文档模板。

## 不应存放的内容

- 源代码、部署清单或由代码生成的 API 参考。
- 某个仓库专用的安装、测试和发布命令。
- 本蓝图其他位置已经维护的重复文档。

## 平台级知识

| 区域 | 负责内容 |
| --- | --- |
| [平台架构](architecture/README.md) | 平台目标、上下文、约束和设计依据 |
| [平台规范](specifications/README.md) | 跨产品的建设与体验标准 |
| [平台路线图](roadmap/README.md) | 跨产品的目标与推进顺序 |
| [全局决策](decisions/README.md) | 影响整个平台的架构决策记录 |
| [文档模板](templates/README.md) | 新文档可复用的统一结构 |
| [共享资源](assets/README.md) | 具有明确所有权的共享视觉资源 |

## 产品领域

| 领域                                             | 范围            |
| ---------------------------------------------- | ------------- |
| [Website（官网）](website/README.md)               | 面向公众的官网产品知识   |
| [Documentation Site（文档站）](docs-site/README.md) | 面向开发者发布的文档体验  |
| [Console（用户控制台）](console/README.md)            | 面向客户的管理体验     |
| [Admin（管理后台）](admin/README.md)                 | 面向内部人员的运营体验   |
| [Gateway（网关）](gateway/README.md)               | API 流量与平台网关行为 |
| [SDK（软件开发工具包）](sdk/README.md)                  | 开发者类库与集成体验    |
