---
title: "ADR-0007：原子准入控制"
description: "记录当前请求级限流、只读候选快照、Channel 原子并发与逐 transport AttemptPermit 边界。"
status: active
owner: 网关团队
last_updated: 2026-07-31
related:
  - ../features/admission-control.md
  - ../features/routing-load-balancing.md
  - adr-0013-provider-runtime-fencing.md
  - adr-0011-runtime-deployment-boundaries.md
  - adr-0016-five-factor-routing-and-cas-sticky.md
---

# ADR-0007：原子准入控制

## 范围

本文记录 Gateway 的 request-admission token、只读候选快照、请求 TPM Reserve、逐 transport
`AttemptPermit`、Channel 原子并发和资源终结。五项排序、全池短等与 CAS Sticky 由
[ADR-0016](adr-0016-five-factor-routing-and-cas-sticky.md) 修订。

## 当前实现结论

当前代码采用“两层 request/candidate admission + 只读候选快照 + 每个真实 transport 前独立
`AttemptPermit`”。请求层执行 Route/User 的 RPM、RPD、TPM 和并发；候选层执行 Channel 并发、breaker、
cooldown、permission 与 revision 门禁。Channel RPM、RPD、TPM 只作为自动聚合的观测事实，不是候选资源。

## 当前实现

1. 受保护的公开 `/v1` 请求只取得一个 `(Route, User Account)` request-admission token。入口 RPM、RPD 和
   并发属于该 session；只有生成或压缩请求在候选估算后由同一 token 一次性 Reserve TPM。Route 四类值都使用
   `NULL` 继承、`0` 不限、正数上限的语义。
2. 生成或压缩请求先形成候选计划并执行只读快照。快照校验 runtime epoch、Provider/Channel revision、
   committed control、breaker、cooldown、permission 与并发容量，再结合 request attempt 时间窗口样本形成五项
   确定性顺序。任一关键 control 或 identity pending、缺失、stale 会使整批失败，不创建 permit。
3. 每个候选按最终上游 wire 计算完整 `input_estimate`；request TPM Reserve 使用可执行候选输入估算的最大值，
   再以独立的保守输出估算完成账务授权。客户显式输出上限按协议校验和映射，省略 OpenAI 输出上限时不注入
   默认值或模型能力上限；输出上限、账务风险估算与 Redis TPM 输入占用互相独立。候选 fallback 不重复 Reserve。
4. 每个真实 transport 前使用新的 `AttemptPermit`。Acquire 原子校验 request token、runtime identity、Provider
   双 revision、Channel config/capacity revision、breaker、half-open、cooldown、permission 与 Channel 并发。
   全部通过后才创建 permit 和并发租约，随后才创建 attempt。
5. candidate 业务拒绝发生在 attempt/transport 前并可继续 fallback；Store 或 Lua 执行错误停止执行。Channel
   并发满只跳过当前候选。只有整池候选都仅因并发满而拒绝时共享一次有界等待，随后完整重扫一次；等待与
   Sticky 无关，单请求禁止再次 transport 已尝试过的 Channel。
6. 整池重扫后仍满返回 503、`routing_channel_capacity_exhausted` 和 `Retry-After: 1`。整池 cooldown 返回 429、
   `channel_rate_limited` 和最短可证明 `Retry-After`，不进入并发等待。breaker、permission、revision 或混合
   denial 不等待。
7. request TPM Reserve 返回 limited 时不写 TPM 桶，但会把 limited 结果固化在仍 active 的 request token 上；
   已记录的 Route RPM/RPD 不回滚，handler 返回前继续持有入口并发，随后由 Finalize 收口。可靠 usage 按
   `actual_total - input_estimate` 调整原分钟桶；无可靠 usage 时，明确未写出上游请求才释放输入占用，已写出、
   收到响应头或结果不确定时保留输入。本地或 partial usage 不修改 Redis TPM。
8. Abort 只用于能够确认 transport 未开始的路径，释放 Channel 并发和 half-open lease；Finish 用于 transport
   已开始或结果不确定的路径，释放并发并应用 breaker、cooldown、permission 和评分样本。Channel 不再存在
   RPM/RPD/TPM 的预占、释放或对账。
9. 普通 control 或 Provider/Channel revision 热更新只影响新快照和 Acquire；旧 permit 先按固化身份终结资源，
   旧运行反馈可以成为 stale/no-op。integrity epoch 换代会在 Redis 调用前阻止旧 token/permit 的主动终结，
   资源只能等待租约 TTL。

## 当前边界

- request token 不包含候选级资源，不能跨多个真实 transport 复用一个候选 permit。
- 只读快照不预占候选资源，也不一次锁定全部 fallback 候选。
- Channel `concurrency_limit = NULL` 继承全局 Channel 默认，`0` 表示不限，正数为硬上限。
- Channel RPM、RPD、TPM 来自 attempt 记录的时间窗口聚合；即使显示数值也不证明 Gateway 执行对应硬限额。
- 请求层 TPM 是软限制：运行中请求只占输入，可靠 usage 到达后才结算为 actual；完成后的正差额可以使原分钟桶
  超过限额。终态只调整取得占用时冻结的分钟桶，该桶已过期时不重建，减量以零为下限。可靠 `actual_total`
  包含互斥的 uncached input、cache read、各类 cache write 与输出总量；reasoning 只作为输出分解，不重复计数。
- Redis 不可用时没有退回本机限流、并发或 breaker 估计的放行路径。
- permit 同 ID、同 fingerprint 的幂等只覆盖 active 状态；terminal 同 ID 返回冲突。

## 代码与测试证据

当前测试覆盖 request admission 接线、request session 所有权、最大候选输入 TPM 占用、可靠 actual
小于/等于/大于输入的差额结算、过期分钟桶不重建、TPM 无 usage 输入保留、候选 denial 在 attempt 前、
Channel 原子并发、全池只因并发满才短等、整池重扫、整池 cooldown、混合拒绝、单请求不重复 Channel、
Abort/Finish、ordinary revision stale、integrity epoch mismatch、pending/缺失和 Store 错误。

## 来源谱系

| 原 DEC | 原始日期 | 当前处理与修订关系 |
| --- | --- | --- |
| DEC-028 | 2026-07-01 | 旧 cache-read 排除与输出预算预占口径由当前完整输入加可靠 actual 的软 TPM 取代。 |
| DEC-029 | 2026-07-10 | 保留过载保护目标；Channel 并发由原子 permit 与 ADR-0016 全池短等接管。 |
| DEC-040 | 2026-07-21 | 保留关键运行态故障 fail closed。 |
| DEC-041 | 2026-07-21 | 保留候选原子 Acquire、permit 所有权与请求/候选分层；移除 Channel 三维限额资源。 |
| DEC-042 | 2026-07-21 | 保留普通 control 更新只影响新 Acquire；epoch 换代依赖租约 TTL。 |
| DEC-043 | 2026-07-21 | 保留 Redis control、revision 与 durable 发布。 |
| DEC-044 | 2026-07-21 | Route 请求层继续使用 `0=不限`；Channel 用量改为观测聚合。 |
| DEC-048 | 2026-07-21 | 容量结果由 ADR-0016 修订为并发耗尽 503、整池 cooldown 429。 |
| DEC-051 | 2026-07-21 | 单逻辑主节点 Redis 仍是原子性前提。 |
| DEC-053 / DEC-054 | 2026-07-23 | Route 请求层默认继续有效；Channel rate 默认和硬门槛由 ADR-0016 移除。 |

## 取代关系

- 取代：无 Blueprint ADR；这是对来源决策的当前实现合并记录。
- 被取代：未整体取代；Channel 三维限额、容量结果和短等范围由
  [ADR-0016](adr-0016-five-factor-routing-and-cas-sticky.md) 修订。

## 参考资料

- [准入控制](../features/admission-control.md)
- [运行控制与恢复](../features/runtime-control-recovery.md)
- [ADR-0013：Provider 运行态代际围栏](adr-0013-provider-runtime-fencing.md)
- [ADR-0011：运行时部署边界](adr-0011-runtime-deployment-boundaries.md)
- [ADR-0016：五项客观路由、原子容量与 CAS Sticky](adr-0016-five-factor-routing-and-cas-sticky.md)
