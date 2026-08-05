---
title: 准入控制
description: Gateway 当前请求层限流与候选层原子并发、运行门禁和资源收口行为。
status: active
owner: 网关团队
last_updated: 2026-08-05
related:
  - ../glossary.md
  - routing-load-balancing.md
  - resilience-circuit-breakers.md
  - ../decisions/adr-0007-atomic-admission-control.md
  - ../decisions/adr-0016-five-factor-routing-and-cas-sticky.md
  - ../decisions/adr-0013-provider-runtime-fencing.md
---

# 功能设计：准入控制

## 摘要

准入控制分为请求层和候选层。受保护的公开 `/v1` 请求在 API Key 认证后取得一次
`(Route, User Account)` request-admission token；生成或压缩请求每次准备真实调用一个 Channel 时，再取得新的
候选级 `AttemptPermit`。两层都以 Redis committed runtime control 为执行权威，并在运行态缺失或不同步时
fail closed。

请求层继续执行 Route/User 的 RPM、RPD 与并发限制。候选层只以 Channel 并发作为容量门槛，
并同时检查 Provider/Channel breaker、429 cooldown、模型权限和 revision。

两层都没有 TPM 门槛。Unio 不主动限制 token 吞吐：上游容量不足只由真实 429、渠道共享冷却、熔断与
fallback 表达。Route 与 Channel 的 TPM 只是分钟级观测事实，既没有上限也没有剩余量。

## 请求层准入

- request token 在 API Key 认证后取得一次，入口 RPM、RPD 与并发在 Acquire 时处理；候选 fallback 不重复
  Acquire。handler 返回后，同一 request session 停止 renewer 并唯一 Finalize。
- Route 的 RPM、RPD 和并发使用 `NULL` / `0` / 正数语义：`NULL` 继承全局默认，`0` 表示不限，正数为
  上限。并发按同一 User Account 在该 Route 上的同时在途请求计数。
- request-token renew 或 handler 后 Finalize 失败只记录日志和指标，不改写已经形成的公开响应。

## 候选准备与评分

生成请求按以下顺序进入执行：

1. 从显式 Route 池形成同协议、同模型候选，完成状态、凭据、Adapter、价格和毛利检查。
2. 读取一次共享运行态快照，校验 epoch、Provider/Channel revision、breaker、cooldown、permission、Channel
   并发容量与五项评分 control；再读取评分时间窗口样本，形成确定性候选顺序。
3. 为每个候选按最终上游 wire 计算完整输入估算，再结合保守输出估算完成账务授权。输入估算不预占任何限额，
   它只服务于余额冻结、价格计算与 TPM 观测。
4. 执行器按实际扫描顺序为每个尚未真实尝试的候选申请新的 `AttemptPermit`。

客户显式提供的输出上限由协议校验并原样映射；客户省略 OpenAI Chat Completions、Responses 或
Responses Compact 输出上限时，Gateway 不用固定默认值或模型能力上限补齐，也不向上游注入人为上限。
账务授权可以使用独立的保守输出估算，但它不改变上游请求。

只读快照不创建 permit，也不预占 Channel 并发。Channel RPM、RPD 与两侧 TPM 都不参与候选快照、资格或
Acquire；Admin 展示的 RPM/RPD 来自 request attempt 记录的时间窗口聚合，TPM 来自独立的分钟级观测桶。

## 候选 `AttemptPermit`

候选 Acquire 在一个 Redis 原子操作中检查：

- request token 仍 active 且未终态；
- runtime state epoch、Redis server identity、fault latch 与 reconciliation proof；
- Provider origin/status control、双 revision、pending fence 和 Channel 对 Provider 的身份绑定；
- Channel config revision、capacity revision 与当前 committed Channel capacity control；
- Provider/Channel breaker、half-open 探测租约、429 cooldown 与 Channel-Model permission；
- Channel 当前有效并发上限与在途 permit 数。

全部通过后，脚本才原子创建服务端 permit、Channel 并发租约和可能的 half-open lease。业务 denial 不创建
attempt、不调用上游，也不改变候选资源。permit 成功后执行器才创建 attempt 和 transport。

同一个 permit ID、同一 fingerprint 的响应丢失重试只在服务端 permit 仍 active 时幂等；fingerprint 不同或
permit 已 terminal 时返回冲突。正常 fallback 和全池重扫使用新的 permit ID。

## 全池短等与 fallback

候选 denial 按原因继续扫描，单个 Channel 并发满不会阻止其他 Channel。执行器对本轮 denial 汇总后，仅在
至少有一个候选且全部候选都只因 `concurrency_full` 被拒绝时等待一次。Sticky 是否命中不参与等待资格。

等待期间继续持有 request token、入口并发和账务授权，但不持有任何 Channel permit。
预算在整池间共享，默认 1 秒，并受客户 deadline 限制；结束后只完整重扫一次。单请求已经发起过真实
transport 的 Channel 不再尝试，禁止 A → B → A。

| 整池结果 | 公开结果 |
| --- | --- |
| 重扫取得 Channel permit | 正常继续，trace 记录 `capacity_wait_result=acquired` |
| 重扫后仍全部并发满 | 503、`routing_channel_capacity_exhausted`、`Retry-After: 1` |
| 全部候选处于 429 cooldown | 429、`channel_rate_limited`、最短可证明 `Retry-After`，不等待 |
| breaker、permission、revision 或混合业务 denial | 不等待，继续可用候选或返回安全 503 |
| Store / Lua 执行错误 | 停止候选循环并返回安全 503 |

## Permit 终结

- Abort 用于已经取得 permit 但能够确认 transport 未开始的路径；释放 Channel 并发和 half-open lease，不写
  breaker、cooldown、permission 或评分样本。
- Finish 用于已经开始 transport 或结果不确定的路径；释放 Channel 并发和 half-open lease，并按结构化结果
  应用 breaker、429 cooldown、permission、credential gate 和 attempt 评分样本。
- permit 固化本次 Provider/Channel revision、generation 和容量身份。普通 revision 更新后仍优先完成资源终结，
  旧 breaker/evidence 反馈可以成为 stale/no-op；attempt 事实仍按请求记录保存。
- runtime epoch 换代是例外：Manager 在 Redis 调用前拒绝旧 token/permit 的 Finalize、Finish 或 Abort，资源只能
  等待租约 TTL。

permit 只冻结 Channel 并发，不存在 RPM/RPD/TPM 的预占、释放或对账。request Finalize 只释放 route-user
并发并关闭 token：RPM/RPD 作为「已接收请求」保留，不回滚，也不接收任何 token 用量。

TPM 观测走完全独立的分钟桶（`obs:tpm:v1:route|channel:{id}:min:{minute}`）。请求发出时按输入估算写入
provisional，流式输出按每个 chunk 的实际观察分钟累加，非流式输出整体归入完整响应到达的分钟。可靠 usage
到达后，输入差额落在输入原始分钟，实际输出按各分钟已观察到的权重等比分配、最后一个分钟承担整数除法余数，
因此分钟合计严格等于实际输出。观测口径与账单一致：输入等于互斥的 uncached input、cache read 与各类
cache write 之和，输出等于 `output_tokens_total`，reasoning 只是输出的分解项，不重复相加。

目标分钟桶已过保留期或超出回溯窗口时放弃该分钟的修正、绝不重建，任何字段都不会变成负数。usage 不可靠时
保留已观察到的估算并增加 `missing_usage_count`，不用不可靠 usage 修正桶。观测写失败只计指标，不影响交付、
结算或准入，也不置位共享基础设施故障 latch。

## Store 故障行为

| 发生位置 | 当前行为 |
| --- | --- |
| request 或 candidate Acquire | fail closed；候选 Acquire 错误停止 fallback 并返回安全 503。 |
| request / permit Renew | 记录日志和指标，已开始的 handler 或 transport 继续。 |
| transport 前 Abort 无法确认 | 记录 unknown；原调用错误仍决定是否 fallback。 |
| 成功 transport 的 Finish 无法确认 | 记录 unknown，不反转已经取得的成功响应和 settlement 主路径。 |
| 失败 transport 的 Finish 无法确认 | 停止普通 fallback，按运行态故障收口。 |
| handler 后 request Finalize | 失败只记录日志；integrity epoch 换代时入口资源等待 TTL。 |

## 状态与边界情况

| 状态或条件 | 当前结果 |
| --- | --- |
| 请求层真实限额命中 | 不创建候选 permit、不调用上游，公开返回 429。 |
| 运行态快照 runtime-sync/pending/stale | 整批失败；尚未授权、创建 attempt 或调用上游。 |
| 单候选并发满 | 立即扫描下一候选，不创建 attempt。 |
| 整池仅因并发满 | 共享一次有界等待后完整重扫；仍满则 503。 |
| 整池 cooldown | 429，不等待。 |
| breaker、permission、revision 或混合业务 denial | 不等待；继续可用候选或返回安全 503。 |
| 候选 Acquire Store 故障 | 停止执行，释放账务授权并返回安全 503。 |
| transport 已开始后配置变化 | 调用、billing 和审计继续；资源按原身份收口，breaker/证据结果可能因当前配置与围栏变为 no-op。 |
| transport 或 handler 结束前 integrity epoch 换代 | Finish/Abort/Finalize 在 Redis 调用前失败；调用结果仍按业务路径处理，运行资源依赖租约/TTL 过期。 |

## 数据、安全与可观测性

PostgreSQL 保存 request、attempt、usage、价格、成本、路由 trace 和审计事实；Redis 保存 request token、permit、
并发租约、breaker/cooldown/permission 以及 revisioned controls。公开 API 不暴露 permit、候选数、Provider、
Channel、上游地址、内部 revision 或 denial reason。

每个进入路由规划的请求持久化一条结构化 trace，关联候选资格、五项排序、实际 acquire 扫描、真实 transport、
Sticky、容量等待、timeout phase 和最终结果。指标和日志仍分别记录 allow、fallback、concurrency full、cooldown、
runtime-sync-required、Store 故障与 permit 终结。

## 当前边界事实

- Redis 状态丢失后的当日 Route RPD 恢复仍遵循 runtime state maintenance 与 fail-closed 规则。
- permit Acquire 的同 ID 幂等只覆盖 active 状态；terminal tombstone 上的同 ID 重试会冲突。
- Renew 指标不能单独证明租约实际延长。
- integrity epoch 换代会阻断旧 request token 和 permit 的主动终结，资源依赖租约 TTL。

## 关联决策

- [ADR-0007：原子准入控制](../decisions/adr-0007-atomic-admission-control.md)
- [ADR-0016：五项客观路由、原子容量与 CAS Sticky](../decisions/adr-0016-five-factor-routing-and-cas-sticky.md)
- [ADR-0011：运行时部署边界](../decisions/adr-0011-runtime-deployment-boundaries.md)
