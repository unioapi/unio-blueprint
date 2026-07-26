---
title: "功能设计：网关访问控制"
description: "记录 API Key、用户账户、Route 与请求身份的当前行为。"
status: active
owner: 网关团队
last_updated: 2026-07-26
related:
  - ../overview.md
  - ../glossary.md
  - ../decisions/adr-0002-route-product-pricing.md
  - ../decisions/adr-0005-request-identity.md
---

# 功能设计：网关访问控制

## 摘要

Gateway 以 API Key 鉴别调用方。有效 API Key 直接解析到 User Account 和显式绑定的 Route；当前 Schema 与
认证路径中没有 Project 身份层或项目默认 Route。

## API Key 数据

新 API Key 同时保存：

- 展示前缀；
- SHA-256 hash；
- 完整明文 `key_plaintext`。

认证只按 hash 查询。创建响应、API Key 运维列表、请求列表、更新响应和吊销响应当前可以返回完整明文；
请求详情不包含该字段，当前也没有注册独立的 API Key 详情 HTTP 路由。历史行的 `key_plaintext` 为空时，
响应返回空值或前缀，不能从 hash 恢复完整值。

## 身份与 Route

1. API Key 直接归属 User Account，并显式绑定一条 Route。
2. 认证拒绝无效、停用、吊销或没有可用 Route 的 API Key；这些路径不调用上游。
3. Route 解析完成后，模型筛选、候选选择和 fallback 都限制在该 Route 的显式 Channel 池内。
4. Gateway 不读取客户端声明来确定 User Account、API Key 归属或 Route。
5. User Account 同时是余额归属主体；余额不足在账务授权阶段拒绝请求。

## API Key 生命周期

| 当前状态或操作 | 当前行为 |
| --- | --- |
| 创建 | 保存 prefix、hash 和完整明文；创建响应返回完整值。 |
| 更新 | 可更新名称、Route 或状态；已注册响应可以返回完整明文。 |
| 停用 | 新请求认证失败；Admin 可重新启用同一行。 |
| 吊销 | 新请求永久认证失败；该行保留，后续普通更新被拒绝。 |
| 删除 | 有 request history 引用时数据库拒绝删除；没有 request history 时可物理删除。 |
| 轮换 | 当前没有原子轮换操作；使用创建、状态更新、吊销和受限删除组合处理。 |

Admin API 当前使用单一静态 token。API Key 的创建、更新、停用、重新启用、吊销和删除没有持久化实际操作人
身份；当前也没有 API Key 明文读取审计记录。

## 请求标识

- HTTP middleware 接受或生成 correlation ID，并写入响应头、request context 与 access log。
- correlation ID 不写入 `request_records`，没有数据库唯一约束。
- Chat Completions、Responses、Responses Compact 和 Messages 在进入持久请求生命周期后，生成独立的
  `req_` 业务请求 ID。
- 持久请求记录关联 User Account、API Key、Route、业务请求 ID、attempt、usage 和账务事实。
- correlation ID 与业务请求 ID 只在当前结构化日志字段中关联；数据库没有 correlation-to-request 映射。

## 公开边界

- API Key 认证失败的公开响应不包含 Provider、Provider Origin、Channel、上游凭据或内部 Route 候选。
- 普通请求日志、trace、metrics 和请求审计不保存完整 API Key 或 hash。
- 完整 API Key 当前只由上述 Admin 数据路径和数据库 `key_plaintext` 保存或返回。

## 代码与测试证据

当前代码、Schema 和测试覆盖 API Key hash 认证、User Account 与 Route 解析、无效/停用/吊销 Key 拒绝、
Route 缺失拒绝、余额授权拒绝、业务请求 ID 生成、correlation ID 分离、request history 删除保护，以及
prefix、hash 和完整明文的创建与读取路径。

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码、Schema 与现有测试接收为 `active`。

## 相关决策

- [ADR-0005：HTTP 关联标识与持久请求标识分离](../decisions/adr-0005-request-identity.md)
- [ADR-0002：线路作为 API Key 绑定的供给与定价边界](../decisions/adr-0002-route-product-pricing.md)
