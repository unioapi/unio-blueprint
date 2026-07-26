---
title: "ADR-0011：运行时部署边界"
description: "记录 Gateway 当前进程、PostgreSQL、Redis、健康探针与运行控制边界。"
status: active
owner: 网关团队
last_updated: 2026-07-26
related:
  - ../features/admission-control.md
  - ../features/runtime-control-recovery.md
  - adr-0007-atomic-admission-control.md
  - adr-0008-runtime-state-fencing.md
  - ../../../architecture/deployment.md
---

# ADR-0011：运行时部署边界

## 范围

本文记录当前 Gateway 仓库的进程入口、PostgreSQL 与 Redis client、启动预检、运行控制恢复、HTTP 健康探针
和新请求准入边界。

## 当前实现

1. 当前仓库是一个 Go module。代码入口包括常驻的 `gateway-server`、`admin-server`、`worker-server`，一次性
   `runtime-state-maintenance` CLI，以及 `worker-server sync-models` 一次性子命令。当前没有
   `console-server` Go 入口。
2. 各入口直接复用同一 module 的 core、service、platform 与 bootstrap 包，不通过 RPC 调用 billing、ledger、
   routing 或 runtime-control 服务。每个进程独立读取配置并建立自己的依赖 client；代码不校验不同进程配置的
   PostgreSQL 或 Redis endpoint 是否相同。
3. 每个使用数据库的入口通过 `DATABASE_URL` 建立 PostgreSQL pool。`OpenPostgres` 解析连接配置、建立 pool
   并执行 `Ping`；当前没有 migration runner 或 schema-version 检查。入口装配随后执行各自使用的
   schema-dependent 查询。预授权、结算、ledger 与运行控制发布在执行它们的进程内使用 PostgreSQL 事务。
4. Redis 配置包含单个 `Addr`，client 由 `redis.NewClient` 建立并执行 `Ping`。当前代码不使用 Redis Cluster
   client、Sentinel discovery 或自动 failover client。`VerifySingleNodeDeployment` 读取 Redis server 信息，拒绝
   `cluster_enabled=1`，并要求 Redis major version 不低于 7。
5. Gateway、常驻 Worker 和 maintenance CLI 调用 `VerifySingleNodeDeployment`；Gateway 与常驻 Worker 还调用
   BreakerStore `Ping`。Admin 不调用这两项检查。生产 Admin 入口仍要求 PostgreSQL 与 Redis client 成功打开。
   `worker-server sync-models` 只连接 PostgreSQL。
6. Gateway 启动时确保 runtime state epoch，开始一次全量 reconciliation，依次处理 Provider Origin、普通
   runtime operation、五项关键 app setting 与全部 Channel admission control，并提交 instance reconciliation
   proof。启动期任一步返回错误都会使装配返回错误；运行期后台 reconciler 每 5 秒重复同一流程。
7. Admin 在 PostgreSQL pool 和非 nil Redis client 下执行一次并周期执行 control reconciliation，但不执行
   state epoch ensure、`BeginRuntimeReconciliation`、instance proof 提交或 fault latch 清除。Admin bootstrap
   接受 nil Redis；该路径下普通 settings 使用 PostgreSQL/default 与本地缓存，不装配 runtime-control
   publisher/fencer。常驻 Worker 不运行 control reconciler。maintenance CLI 只编排 state epoch 的
   `begin`、`commit` 与 `release`。
8. Gateway `/healthz` 固定返回 200。`/readyz` 每次读取 PostgreSQL 的 ready epoch、五项关键 control revision
   与相关 operation 终态，然后 Ping Redis 并原子核验 marker、control active/pending/revision/payload hash、
   instance reconciliation proof 与 fault latch；响应体只返回 `ready` 或 `not_ready`。普通 `/readyz` 不扫描
   全部 Origin/Channel control，也不检查 migration 或 schema version。
9. Redis `run_id` 与 reconciliation proof 同时用于 readiness、request admission、candidate Snapshot 和
   Acquire。`run_id` 变化后，这些路径在新的全量 reconciliation proof 完成前拒绝准入。state epoch recovery
   处于 `awaiting_release` 时，全量 proof 可允许 maintenance smoke；普通 `/readyz` 在 release 前仍返回 503。
10. Admin 只有固定返回的 `/healthz`，另有受 Admin 认证保护的 runtime diagnostics；Worker 与 maintenance CLI
    不提供 HTTP 健康端点。
11. request admission 的 Store、integrity 或 control 错误发生在 handler 前并映射为 503。`SnapshotMany` 的
    runtime-sync、pending 或 revision/config stale 在 TPM Reserve、账务授权、attempt 和上游调用前终止请求。
    Snapshot 后的 candidate Acquire denied 不创建 attempt 或 transport，并可继续后续候选；Go/Store 错误或
    `breaker_store_unavailable` 终止候选执行。已开始 transport 的调用继续按实际 usage、账务、attempt 与审计
    路径收口。

## 代码与测试证据

当前代码和测试覆盖各 `cmd` 入口、PostgreSQL/Redis client、单节点 verifier、Gateway/Admin/Worker 的不同装配
路径、state epoch 与全量 reconciliation、readiness 原子核验、control commit 响应丢失恢复、两个 Gateway 共享
运行态、Redis stop/restart、完整 state-loss maintenance 生命周期、AOF/RDB restore、长流 revision fence、
half-open lease 接管，以及 Cluster verifier 拒绝与跨 slot 多键 Lua 返回 `CROSSSLOT`。

## 来源谱系

| 原 DEC | 原始日期 | 原状态 | 当前处理与修订关系 |
| --- | --- | --- | --- |
| DEC-040 | 2026-07-21 | accepted，来源标注待实现 | 当前 request、snapshot 与 candidate Store/control 错误的分层拒绝行为。 |
| DEC-043 | 2026-07-21 | accepted，来源称已实现，部分修订 | 当前 Redis control、revision、durable operation 与 reconciliation。 |
| DEC-050 | 2026-07-21 | accepted，来源标注待实现 | 来源中的停机空库重建只描述可重建开发环境，不是当前生产数据迁移流程。 |
| DEC-051 | 2026-07-21 | accepted，来源标注待实现 | 当前单地址 Redis client，以及 Gateway、Worker 和 maintenance 的非 Cluster 与 Redis 7+ 检查。 |
| DEC-053 | 2026-07-23 | accepted，来源称已实现，部分修订 | 当前默认不限与计数行为；作用域由 DEC-054 修订。 |
| DEC-054 | 2026-07-23 | accepted，来源称已实现 | 当前 Route request admission 与 Channel candidate admission 的独立 control 与 key。 |

## 取代关系

- 取代：无 Blueprint ADR；这是对上述来源的合并记录。
- 被取代：无。

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码、Schema 与现有测试接收为 `active`。

## 参考资料

- [准入控制](../features/admission-control.md)
- [运行控制与恢复](../features/runtime-control-recovery.md)
- [ADR-0007：原子准入控制](adr-0007-atomic-admission-control.md)
- [概念部署架构](../../../architecture/deployment.md)
