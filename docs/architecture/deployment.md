---
title: 概念部署架构
description: 当前 Gateway 进程、依赖、健康语义与已核验部署边界。
status: draft
owner: 架构团队
last_updated: 2026-07-26
related:
  - README.md
  - context.md
  - quality.md
  - risks.md
  - ../decisions/README.md
---

# 概念部署架构

## 文档状态

本文只记录当前 Gateway 代码、Schema 与测试能够证明的部署事实，以及由这些事实直接暴露的实现缺口。
`draft` 表示该 Blueprint 文档尚未完成状态接收，不表示当前代码仍在多个部署方案之间选择。Gateway 的详细
依赖边界以 [ADR-0011](../products/gateway/decisions/adr-0011-runtime-deployment-boundaries.md) 为准。

## 当前运行概览

```text
客户端与运营入口
        |
        v
Gateway / Admin / Worker 进程边界 ----> 外部上游
        |
        +----业务与账务事实----> PostgreSQL
        |
        +----控制、计数与租约--> Redis
```

当前 Gateway 仓库是一个 Go module 内的模块化单体，实际运行面由 Gateway、Admin、Worker 三类常驻服务和
一次性运行态维护 CLI 组成。它们复用核心业务与数据访问模块；当前没有 `console-server` 代码入口，也没有独立
billing、ledger、routing 或 runtime-control RPC 服务。

## 状态与依赖概览

- PostgreSQL 保存业务、账务、审计和控制发布事实；每个进程独立建立连接池，代码不强制所有进程连接同一
  物理实例。需要原子提交的单次业务操作在执行它的进程内使用 PostgreSQL 事务，不存在跨进程事务。
- Redis 保存当前 control、完整性、计数、租约和 permit 等运行事实，不是金额、usage、request 或 ledger
  历史的唯一来源。
- Gateway 提供静态 liveness 与动态 readiness；依赖运行控制的新 Gateway 准入在事实不可信时 fail-closed，
  已开始 transport 的业务事实继续收口。Admin、Worker 和维护 CLI 的健康面与恢复职责并不相同。

## 当前限制概览

- PostgreSQL 启动检查没有显式 migration/schema-version 门禁。
- Redis client 只有单地址配置，代码没有证明 Sentinel、自动 failover、Cluster client 或其他高可用形态。
- Redis topology/version 预检尚未在所有入口统一；生产实例数、主机分布、备份、回滚、容量和服务等级也不由
  当前代码或本地 Compose 证明。

以上是当前实现边界，不是未来部署方案。详细入口矩阵、健康与恢复状态、分层 fail-closed 行为、实现缺口和
DEC-040/043/050/051/053/054 来源谱系统一维护在
[ADR-0011](../products/gateway/decisions/adr-0011-runtime-deployment-boundaries.md)。准入和恢复流程分别见
[准入控制](../products/gateway/features/admission-control.md)与
[运行控制与恢复](../products/gateway/features/runtime-control-recovery.md)。

## 边界

不得包含部署清单、主机名、凭据、环境清单、供应商控制台操作或仓库专用部署命令。
