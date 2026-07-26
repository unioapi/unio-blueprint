---
title: 韧性与熔断器
description: Gateway 对真实上游故障进行归因、隔离、恢复与可观察解释的当前行为。
status: active
owner: 网关团队
last_updated: 2026-07-26
related:
  - ../glossary.md
  - admission-control.md
  - runtime-control-recovery.md
  - routing-load-balancing.md
  - ../decisions/adr-0010-upstream-breaker-attribution.md
---

# 功能设计：韧性与熔断器

## 摘要

Gateway 只把已经进入真实上游 transport、且可归因到对应作用域的结果写入共享 breaker。Provider Origin
承载公共地址与服务故障域，Channel 承载单渠道故障；认证、请求准入、平台、Store、数据库、账务、本地构造
和客户取消等结果不会被伪装成上游失败。Channel 与 Origin 使用 Redis 中独立但同构的状态机，多 Gateway
共享同一运行事实。

## 当前职责边界

| 机制 | 当前责任 | 不负责的内容 |
| --- | --- | --- |
| Provider Origin breaker | 公共连接、地址和服务故障；部分歧义故障经跨 Channel、跨模型证据后升级 | 单凭据、单模型权限和客户错误 |
| Channel breaker | 已真实调用的 timeout、5xx 和明确协议失败 | 401、403、429、准入和平台错误 |
| 429 cooldown | 按 Channel 保存独立、跨 Gateway 的限流冷却 | breaker 样本和 open level |
| Channel-Model permission pause | 暂停精确的 Channel、Model 与 revision 组合 | 整个 Channel 的凭据有效性 |
| credential gate | 处理连续真实上游 401 和凭据轮换 | 403 权限与 breaker 状态 |
| AttemptPermit | 在 transport 前原子取得 breaker、half-open、限额和并发资格，并负责终结资源 | 根据业务错误猜测归因 |

历史进程内失败软冷却不再参与候选降级或熔断；当前 breaker 事实只来自共享运行态。

## 当前状态机

Channel 与 Provider Origin 分别维护 `closed`、`open`、`half_open`、状态 generation、eligible 窗口、
连续失败、open level 和 half-open lease。默认运行配置为：

| 参数 | 当前默认值 | 当前行为 |
| --- | --- | --- |
| eligible 窗口 | 30 秒 | 窗口到期后的下一次 Finish 清空成功/失败计数再应用本次结果 |
| 比例触发最小样本 | 20 | 样本不足时不按失败比例打开 |
| 失败率阈值 | 0.5 | `eligible_failure / eligible_total >= 0.5` 时打开 |
| 快速触发 | 10 秒内连续 3 次 eligible failure | 不要求达到 20 个样本 |
| half-open 恢复 | 2 个成功 | 必须来自不同、仍有效的 permit |
| open 退避 | 15、30、60、120、300 秒 | 每次重新 open 进入下一档，最后一档封顶 |
| permit 生命周期 | TTL 30 秒、每 10 秒续租、终态 tombstone 5 分钟 | 参数在取得 permit 时固化 |
| 歧义 Origin 证据门槛 | 2 个不同 Channel 且 2 个不同模型 | 每种证据类别独立统计 |

状态转换遵循以下当前规则：

1. `closed` 中的 eligible success 进入分母并清空连续失败；eligible failure 同时进入分子、分母和连续失败。
   `ignored` 不增加样本，也不充当成功清空连续失败。
2. 快速触发或比例触发满足任一条件时进入 `open`，推进 state generation，并使用当前 open level 的退避时长。
3. open 到期后，Acquire 进入 `half_open` 并取得单个 lease；同一作用域 lease 有效时其他 Acquire 得到
   `half_open_busy`。
4. half-open 的 eligible success 释放 lease并累计成功；第二个不同 permit 成功后回到 `closed`，清空窗口、
   连续失败、half-open 成功和 open level，并推进 generation。
5. half-open 的 eligible failure 立即重新 `open`，进入下一退避档并推进 generation；`ignored` 只释放当前 lease。
6. 重复 Finish/Abort 服从 first-terminal-wins，不能重复计样本、释放资源或冒充第二次 half-open 成功。

`SnapshotMany` 是只读操作。closed 状态的 eligible 窗口已经过期时，它只在返回副本中把成功、失败和错误率
显示为无样本，不修改 Redis 状态，也不清除 Channel TTFT。

## 当前结果归因

### 直接结果矩阵

| 已开始真实 transport 后的结果 | Channel | Provider Origin | 其他运行态反馈 |
| --- | --- | --- | --- |
| 成功且取得有效协议 facts | eligible success | eligible success | 可按 usage 对账 Channel TPM |
| timeout、HTTP 5xx | eligible failure | 按下节的直接或条件规则 | 无 |
| 2xx 但响应无法满足协议契约 | eligible failure | ignored | 无 |
| 401 | ignored | ignored | 交给进程内连续 401 凭据闸门 |
| 403 | ignored | ignored | Finish 确认后暂停精确 Channel-Model-revision 权限绑定 |
| 429 | ignored | ignored | Finish 确认后写独立 Channel cooldown |
| 400、404、405、422 及其他 4xx | ignored | ignored | 无 breaker 反馈 |
| 客户取消 | ignored | ignored | 按请求交付和账务路径收口 |
| transport 开始前的 adapter 查找、attempt 持久化或其他本地失败 | 不形成结果；已取得 permit 时 Abort | 不形成结果；已取得 permit 时 Abort | 作为平台或依赖错误处理 |
| transport 回调内的请求编码、本地 panic、协议处理或客户流式写出错误 | 按当前错误分类 Finish；多数本地错误 ignored，明确协议失败可成为 eligible failure | 通常 ignored | 客户流式写出错误属于当前 transport 结果的一部分 |
| 已取得有效成功 facts 后发生的非流式结算、数据库或交付错误 | 先前 Finish 已记录 eligible success | 先前 Finish 已记录 eligible success | 后续错误不反向覆盖 breaker 结果 |

Channel 的协议失败只包括代码明确识别的解码失败、非法响应、stream 读取失败和响应过大等类别；未知本地错误
不会因为发生在 attempt 内就自动成为 Channel failure。非流式路径在 transport 返回后立即 Finish，结算和最终
客户交付发生在其后；因此后续失败不会撤销已经应用的 eligible success。流式客户写出发生在 transport 回调内，
会进入本次 Finish 的分类流程。

### Provider Origin 归因

以下失败直接成为 Origin eligible failure：

- HTTP 502、503、504；
- 连接类或无 HTTP status 的 server error；
- 发送、握手或等待响应头阶段的 timeout；
- 流读取中的 EOF、连接重置和代理截断等 server error。

HTTP 500、首 token timeout 和 body read timeout 先只计入 Channel。每种类别使用互相隔离的短窗证据集合；
同一 Origin 内同时达到不同 Channel 数和不同请求模型数的当前门槛后，本次 Finish 才额外形成一次 Origin
eligible failure。HTTP 500 与两类 timeout 不能互相拼样本，单 Channel 或单模型证据也不能摘除整个 Origin。

## Permit、围栏与迟到结果

每次真实上游调用前，Gateway 取得新的 `AttemptPermit`。服务端 permit 固化 integrity epoch、Origin Base URL
revision、Origin status revision、Channel config revision、两个 breaker generation、half-open 权利、模型、
operation、传输模式和资源 token。

- 未开始 transport 的路径调用 Abort，只释放 permit 持有的资源，不写 breaker 或 TTFT。
- 已开始 transport 的路径调用 Finish；无论 breaker 结果是否可应用，都先释放并发，并按当前规则保留 RPM/RPD、
  对账或释放 TPM。
- Origin fence、Channel revision 或 generation 已变化且 integrity epoch 仍匹配时，旧结果返回明确的 stale
  disposition；资源仍终结，但当前 breaker、Origin 证据和 Channel TTFT 不被修改。
- integrity epoch 已换代时，Manager 在 Redis 调用前拒绝 Finish/Abort，旧 permit 资源不会由该调用收口，只能
  等待租约或 TTL 过期。
- permit 续租或终结无法确认时按运行态依赖故障处理，不能继续把后续 fallback 当作安全调用。

## 429 与 403 的独立反馈

429 与 403 的反馈只发生在 permit Finish 已确认之后：

- 429 cooldown 取上游 `Retry-After`；缺失时使用热更新默认值，并受热更新上限约束。cooldown 是 Channel 级
  Redis 事实，优先于 breaker 检查；breaker Reset 不清除它。
- 403 permission pause 固化 Channel、Model、Channel config revision 与 Origin 两类 revision。后续复检只在
  这些事实仍匹配时恢复该绑定，不修改整个 Channel 的 `credential_valid`。
- cooldown 或 permission pause 写入失败会返回 `breaker_store_unavailable` 并终止 fallback，避免在运行态反馈
  未知时继续调用其他上游。

## `enabled=false` 的当前语义

`gateway.circuit_breaker.enabled=false` 使 Acquire 不再因 open/half-open 拒绝，并使 Finish 的 Origin/Channel
breaker disposition 返回 `not_applicable`。它不绕过 AttemptPermit、Origin 围栏、integrity、并发、RPM、RPD、
TPM、429 cooldown、Channel-Model permission pause 或 Store fail-closed。

当前 Finish 脚本在 breaker disabled 分支先于 Channel TTFT 更新返回，因此关闭 breaker 也会停止新的 TTFT EWMA
样本；既有 TTFT 不被清除。历史设计资料中“关闭 breaker 仍采集 TTFT”的表述不是当前代码事实。

## 外部错误与可观测性

公开响应不回显 Channel、Provider Origin、Base URL、候选数、breaker key、归因码或内部 revision。首帧前的
最终错误由请求生命周期按候选聚合结果映射；首帧写出后不能改写 HTTP status，只能按协议流中断和账务规则收口。

内部运行态保存和展示两个作用域的状态、样本数、错误率、连续失败、open 剩余时间、open level、half-open
lease、generation、Finish disposition，以及独立的 Channel cooldown、permission pause 和 Channel TTFT。
Provider Origin 不保存 TTFT。

## 代码与测试证据

现有单元测试覆盖 eligible/ignored 样本、连续和比例触发、退避、half-open lease、重复终结、Reset、Origin
独立归因、三类隔离证据、429 cooldown、403 permission pause、revision/generation stale、TTFT stream-only 和
Store fail-closed，以及两个 Gateway 进程间的 Channel half-open lease 接管。

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码、Schema 与现有测试接收为 `active`。

## 相关决策

- [ADR-0010：上游熔断归因](../decisions/adr-0010-upstream-breaker-attribution.md)
- [ADR-0008：运行态代际围栏](../decisions/adr-0008-runtime-state-fencing.md)
