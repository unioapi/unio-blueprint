---
title: 韧性与熔断器
description: Gateway 对真实上游故障按 Provider 与 Channel 归因、隔离、恢复和解释的当前行为。
status: active
owner: 网关团队
last_updated: 2026-07-27
related:
  - ../glossary.md
  - admission-control.md
  - runtime-control-recovery.md
  - routing-load-balancing.md
  - ../decisions/adr-0014-provider-breaker-attribution.md
---

# 功能设计：韧性与熔断器

## 摘要

Gateway 只把已经进入真实上游 transport、且可归因到对应作用域的结果写入共享 breaker。Provider 承载唯一
地址和公共服务故障域，Channel 承载单渠道故障；认证、请求准入、平台、Store、数据库、账务、本地构造和
客户取消等结果不会被伪装成上游失败。两层状态机由多个 Gateway 共享。

## 职责边界

| 机制 | 当前责任 | 不负责的内容 |
| --- | --- | --- |
| Provider breaker | 公共连接、地址和服务故障；部分歧义故障经跨 Channel、跨模型 evidence 升级 | 单凭据、单模型权限和客户错误 |
| Channel breaker | 已真实调用的 timeout、5xx 和明确协议失败 | 401、403、429、准入和平台错误 |
| 429 cooldown | 按 Channel 保存跨 Gateway 冷却 | breaker 样本和 open level |
| Channel-Model permission pause | 暂停精确的 Channel、Model 与 revision 组合 | 整个 Channel 凭据有效性 |
| credential gate | 处理连续真实上游 401 与凭据轮换 | 403 权限和 breaker 状态 |
| AttemptPermit | 在 transport 前原子取得 breaker、half-open、限额与并发资格，并终结资源 | 根据业务错误猜测归因 |

## 状态机

Provider 与 Channel 分别维护 `closed`、`open`、`half_open`、generation、eligible 窗口、连续失败、open
level 和 half-open lease。默认 control 使用：

| 参数 | 默认值 | 行为 |
| --- | --- | --- |
| eligible 窗口 | 30 秒 | 窗口到期后下一次 Finish 先清空样本再应用本次结果 |
| 比例触发最小样本 | 20 | 样本不足不按比例打开 |
| 失败率阈值 | 0.5 | `eligible_failure / eligible_total >= 0.5` 时打开 |
| 快速触发 | 10 秒内连续 3 次 eligible failure | 不要求 20 个样本 |
| half-open 恢复 | 2 个不同 permit 的成功 | 有效 lease 内串行探测 |
| open 退避 | 15、30、60、120、300 秒 | 重新 open 逐档增长并封顶 |
| Provider 歧义 evidence | 2 个不同 Channel 且 2 个不同模型 | 每个错误类别独立统计 |

`eligible_success` 进入分母并清空连续失败；`eligible_failure` 进入分子、分母和连续失败；`ignored` 不改变
样本。open 到期后的 Acquire 以单 lease 进入 half-open；第二个不同 permit success 回到 closed，failure 立即
重新 open。重复 Finish/Abort 服从 first-terminal-wins。

## 结果归因

| 已开始 transport 的结果 | Channel | Provider | 其他反馈 |
| --- | --- | --- | --- |
| 成功且有有效协议 facts | eligible success | eligible success | 可对账 Channel TPM |
| timeout、HTTP 5xx | eligible failure | 按直接或 evidence 规则 | 无 |
| 明确协议解码、非法响应或 stream 读取失败 | eligible failure | 通常 ignored | 无 |
| 401 | ignored | ignored | 连续凭据闸门 |
| 403 | ignored | ignored | Channel-Model permission pause |
| 429 | ignored | ignored | Channel cooldown |
| 其他 4xx、客户取消、未分类本地错误 | ignored | ignored | 按业务路径收口 |
| transport 前失败 | Abort，不形成 breaker 结果 | Abort，不形成 breaker 结果 | 释放 permit 资源 |

HTTP 502、503、504、无状态 server error、发送/握手/响应头 timeout、连接重置、代理截断和相同性质的 stream
server error 直接形成 Provider failure。HTTP 500、首 token timeout 和 body read timeout 先只形成 Channel
failure；同一 Provider 内相同类别同时达到不同 Channel 和不同模型门槛时，本次 Finish 才额外形成 Provider
failure。类别之间不能拼样本。

## Permit、围栏与迟到结果

每个真实 transport 前取得新的 `AttemptPermit`，固化 runtime epoch、Provider origin/status revision 与 fence、
Channel config revision、两层 breaker generation、half-open 权利、模型、operation、传输模式和资源 token。

- 未开始 transport 的路径 Abort，只释放资源，不写 breaker/evidence/TTFT。
- Finish 无论反馈是否可应用，都先释放并发并按 usage 对账或释放 TPM。
- Provider 双 revision/fence、Channel revision 或 generation 变化时，旧反馈返回 stale disposition；资源仍终结，
  当前 Provider breaker/evidence、Channel breaker 与 TTFT 不被旧事实修改。
- runtime epoch 换代时 Manager 在 Redis 调用前拒绝 Finish/Abort，资源只能等待租约或 TTL。

## 401、403 与 429

- 连续 401 key 绑定 Channel ID、Channel config revision 与 Provider 双 revision；当前 revision 的成功清零，
  达到阈值后以 PostgreSQL CAS 将凭据置 invalid。
- 429 cooldown 取 `Retry-After` 或当前默认值，按 Channel 保存；Provider/Channel breaker reset 都不清除它。
- 403 permission pause 固化 Channel、Model、Channel config revision 与 Provider 双 revision，只通过精确复检恢复。

这些反馈只在 permit Finish 已确认后写入。写入 Store 失败终止普通 fallback，避免在反馈状态未知时继续调用。

## Reset 与归档

Provider 与 Channel breaker 独立 reset。Provider reset 先读取 PostgreSQL 实体；不存在返回 404，不因 Redis
key 是否存在而创建状态。reset 不清除 cooldown 或 permission pause。

Provider/Channel 归档立即清理 breaker、evidence/cooldown、permission 和新准入 control，但保留在途 permit、
并发租约和计数桶。归档前已开始的调用可以完成；其 breaker/evidence/TTFT 反馈成为 stale/no-op。

## `enabled=false`

`gateway.circuit_breaker.enabled=false` 使 Acquire 不因 open/half-open 拒绝，并使两层 breaker disposition
返回 `not_applicable`。它不绕过 AttemptPermit、Provider 围栏、integrity、并发、RPM、RPD、TPM、cooldown、
permission pause 或 Store fail closed。当前脚本在 disabled 分支不写新的 Channel TTFT 样本。

## 安全与可观测性

公开响应不回显 Provider、Channel、上游地址、候选数、breaker key、归因码或内部 revision。内部运行态展示
两层状态、样本、错误率、open 剩余时间、generation、Finish disposition，以及独立 cooldown、permission 和
Channel TTFT。Provider 不保存 TTFT。

Redis 当前 key 使用 Provider/Channel 命名空间；不存在旧 Origin key、combined routing Lua 或兼容读取路径。

## 代码与测试证据

当前测试覆盖 eligible/ignored、连续和比例触发、退避、half-open、重复终结、Provider/Channel 独立 reset、
三类隔离 evidence、429、403、401、双 revision/generation stale、TTFT stream-only、404 reset、Store fail
closed 和多 Gateway 共享状态。

## 相关决策

- [ADR-0014：Provider 与 Channel 熔断归因](../decisions/adr-0014-provider-breaker-attribution.md)
- [ADR-0013：Provider 运行态代际围栏](../decisions/adr-0013-provider-runtime-fencing.md)
