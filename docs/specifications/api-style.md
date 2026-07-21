---
title: API 风格规范
description: API 契约与生命周期一致性规则的占位文档。
status: draft
owner: 网关团队
last_updated: 2026-07-21
related:
  - README.md
  - naming.md
  - permissions.md
  - logging.md
---

# API 风格规范

## 目的

为 UnioAPI 产品提供和消费的 API 定义一致、与技术实现无关的规则。

## 待定义标准

- 资源与操作命名
- 请求、响应与错误结构
- 身份认证与权限状态表达
- 分页、筛选、排序与幂等性
- 版本、兼容性、弃用与移除
- 流式传输、重试、速率限制与请求关联
- Schema 发布与契约测试

## 证据要求

每项强制规则都应包含设计依据、正确示例、错误示例以及采用或迁移说明。

## 边界

接口清单与处理器实现属于对应产品领域或代码仓库。

