---
title: "ADR-0007：原子准入控制"
description: "记录当前请求级 admission、只读候选快照与逐 transport AttemptPermit 边界。"
status: active
owner: 网关团队
last_updated: 2026-07-26
related:
  - ../features/admission-control.md
  - ../features/routing-load-balancing.md
  - adr-0008-runtime-state-fencing.md
  - adr-0011-runtime-deployment-boundaries.md
---

# ADR-0007：原子准入控制

## 范围

本文记录当前 Gateway 的 request-admission token、只读候选快照、请求 TPM Reserve、逐 transport
`AttemptPermit`、资源终结和公开错误聚合行为。术语遵循[网关词汇表](../glossary.md)：Channel 挂在
Provider Origin 上。

## 当前实现结论

当前代码采用“两层 request/candidate admission + 只读候选快照 + 每个真实 transport 前独立
`AttemptPermit`”。详细调用流程、状态矩阵与错误语义统一维护在[准入控制](../features/admission-control.md)，
排序细节统一维护在[路由负载均衡](../features/routing-load-balancing.md)。

## 当前实现

1. 当前注册且受保护的公开 `/v1` 请求只取得一个 `(Route, User Account)` request-admission token；入口
   RPM/RPD/并发属于该 request session。该范围也包括 `/v1/models`、`responses/input_tokens` 和当前返回 501 的
   状态操作；只有生成或压缩请求会在候选估算后由同一 token 一次性 Reserve TPM。
2. 生成或压缩请求先形成 Route/候选计划并执行一次 `SnapshotMany`，再 Reserve 请求 TPM、完成账务授权并进入
   执行。快照是整批只读线性化点；任一 control 或 identity pending、缺失、stale 会使整批失败，不创建 permit
   或预占 Channel 资源。
3. 每个真实 transport 前使用新的 `AttemptPermit` 原子取得候选资源，包括 compact 原生调用失败后的透明回落。
   Acquire 强读 integrity、ChannelRate、
   GlobalConcurrency 与 CircuitBreaker control facts；RouteRate 已绑定 request token，RoutingBalance 只用于快照，
   ChannelAdmission 与 Origin/Channel config revision 来自冻结候选计划。
4. candidate 业务拒绝发生在 attempt/transport 前，不调用该候选上游并可继续 fallback；Go/Store 错误或
   `breaker_store_unavailable` 终止执行。正常返回的业务 denial 不创建 permit 或候选资源；该保证不扩展到 Redis
   Lua 运行错误或响应结果不确定的情形。只有 rate/concurrency 的全部拒绝聚合为 429，混合或其他拒绝聚合为 503。
5. 首 Route 候选只有在 `concurrency_limited`/`rate_limited` 时可短等一次。等待计入客户 deadline，并继续持有
   request token、入口并发、已 Reserve TPM 与账务预授权冻结；入口 RPM/RPD 已计数但不是等待租约。重试使用
   新 permit ID 和新读 control facts。
6. request TPM Reserve 返回 limited 时不写 TPM 桶，但会把 limited 结果固化在仍 active 的 request token 上；
   handler 返回前继续持有入口并发，随后由 Finalize 收口。输入估算为零时不会预占请求或 Channel TPM，后到的
   正数 actual TPM 也不会补记到 Channel TPM。
7. token/permit 的同 ID、同 fingerprint 幂等重试只覆盖 active 状态；终态同 ID 返回冲突。普通 control 或
   Origin/Channel revision 热更新只影响新 Acquire，旧 permit 按固化桶身份收口；integrity epoch 换代则会在
   Redis 调用前阻止 request Finalize 及 permit Finish/Abort，资源只能依赖租约或 TTL 过期。

## 当前边界

- request token 不包含候选级资源，不能跨多个真实 transport 复用一个候选 permit。
- `SnapshotMany` 不预占候选资源，也不一次锁定全部 fallback 候选或强制摘除所有零容量候选。
- 候选资源不是由调用方分步取得；当前 Store Lua 在全部门槛通过后才统一写入 permit 与资源。
- Redis 不可用时没有退回本机限流或本机 breaker 估计的放行路径。
- request concurrency 当前没有接入 Route override，只继承 global key concurrency limit。
- Channel RPD 与 RPM/TPM 共用 permit TTL 派生的短 TTL，默认约 7.5 分钟，不保存完整 UTC 日历史。

## 代码与测试证据

当前代码与测试已核验 request admission 接线、request session 所有权、逐候选 permit 调用位置、拒绝发生在
attempt/transport 之前、首候选容量拒绝使用新 permit 的至多一次短等、breaker 拒绝不等待，以及非流式、
流式和透明 fallback 的独立 Acquire。现有 Store 与 service 测试还覆盖 active 状态同 ID 幂等、终态冲突、
Abort/Finish、TPM Reserve、普通 revision stale、integrity epoch mismatch、pending/缺失和 Store 错误分支。

## 来源谱系

| 原 DEC | 原始日期 | 原状态 | 当前处理与修订关系 |
| --- | --- | --- | --- |
| DEC-028 | 2026-07-01 | accepted，DEC-041 补充 | 保留 cache_read 不占 TPM、cache_write 保留、未结算预占释放；候选资源所有权由 DEC-041 固定。 |
| DEC-029 | 2026-07-10 | accepted，大部分实现被替换 | 保留过载保护目标；入口并发由 DEC-043、Channel 并发由 DEC-041 接管；本机失败软冷却由 DEC-045 废止。 |
| DEC-040 | 2026-07-21 | accepted，来源标注待实现 | 保留关键运行态故障 fail-closed；由 DEC-043/054 细化控制域。 |
| DEC-041 | 2026-07-21 | accepted，来源标注待实现 | 当前候选原子 Acquire、permit 资源所有权与请求/候选分层的主要来源；integrity epoch 换代会在 Redis 调用前阻断主动 Finish/Abort，是资源自然收口结论的例外。 |
| DEC-042 | 2026-07-21 | accepted，来源标注待实现 | 普通 control/revision 热更新只影响新 Acquire；既有 permit 按固化桶身份收口，但 integrity epoch 换代只能依赖租约/TTL 释放。 |
| DEC-043 | 2026-07-21 | accepted，来源称已实现，部分修订 | Redis control/revision 与 durable 发布有效；仅旧共享 rate-control 作用域由 DEC-054 修订。 |
| DEC-044 | 2026-07-21 | accepted，来源标注待实现 | `0=不限` 仍记录入口与候选用量；Channel RPD 约 7.5 分钟短 TTL 无法维持完整 UTC 日历史。 |
| DEC-048 | 2026-07-21 | accepted，来源标注待实现 | 保留容量 429、基础设施/混合原因 503 的边界；协议包络不在本 ADR 详细规定。 |
| DEC-051 | 2026-07-21 | accepted，来源标注待实现 | 单逻辑主节点 Redis 是本 ADR 原子性前提；部署边界由 ADR-0011 合并。 |
| DEC-053 | 2026-07-23 | accepted，来源称已实现，部分修订 | 两类默认 `0/0/0` 和不限仍计数有效；共享 key 由 DEC-054 取代。 |
| DEC-054 | 2026-07-23 | accepted，来源称已实现 | 当前线路默认与 Channel 默认完全拆分，分别作用于请求和候选层；只修订 DEC-043/053 的旧共享作用域。 |

## 取代关系

- 取代：无 Blueprint ADR；这是对上述来源的迁移合并记录。
- 被取代：无。

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码、Schema 与现有测试接收为 `active`。

## 参考资料

- [准入控制](../features/admission-control.md)
- [运行控制与恢复](../features/runtime-control-recovery.md)
- [ADR-0011：运行时部署边界](adr-0011-runtime-deployment-boundaries.md)
