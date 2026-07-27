---
title: "ADR-0010：上游熔断归因"
description: "记录真实上游结果进入 Channel 与 Provider Origin breaker 的当前分类和状态机。"
status: superseded
owner: 网关团队
last_updated: 2026-07-27
related:
  - ../features/resilience-circuit-breakers.md
  - ../features/routing-load-balancing.md
  - adr-0008-runtime-state-fencing.md
  - adr-0014-provider-breaker-attribution.md
---

# ADR-0010：上游熔断归因

## 范围

本文记录当前 Gateway 的真实上游结果分类、Channel 与 Provider Origin breaker、429 cooldown、403 permission
pause、状态转换和迟到结果围栏。

## 当前实现

1. Channel 与 Provider Origin 分别在 Redis 保存 `closed`、`open`、`half_open` 状态、generation、eligible
   窗口、连续失败、open level 和 half-open lease。多个 Gateway 共享这些状态；候选排序不使用进程内失败
   cooldown。
2. 每个真实 transport 前取得的 `AttemptPermit` 固化两个 breaker generation 和 half-open 权利。调用返回后，
   lifecycle 只在 timing observer 已记录 transport start 时调用 Finish；未记录 transport start 的路径调用 Abort。
   Abort 释放 permit 资源，不写 breaker、Origin 证据或 Channel TTFT。
3. 有有效协议 facts 的成功结果对 Channel 与 Origin 都提交 `eligible_success`。HTTP 5xx、上游 timeout 和代码
   明确分类的协议解码、非法响应、stream 读取或响应过大错误可对 Channel 提交 `eligible_failure`；401、403、
   429、其他 4xx、客户取消和未被分类为上游责任的本地错误对两个 breaker 提交 `ignored`。
4. HTTP 502、503、504，无 HTTP status 的 server error，发送、握手或等待响应头阶段的 timeout，以及 stream
   读取中的 EOF、连接重置或代理截断类 server error，直接对 Provider Origin 提交 `eligible_failure`。HTTP 500、
   首 token timeout 与 body read timeout 先作为 Channel failure，并按错误类别分别收集 Origin 短窗证据；同一
   类别达到不同 Channel 数和不同模型数门槛时，越过门槛的当前 Finish 同时形成一次 Origin failure。当前两个
   门槛默认都为 2。
5. 401 由进程内连续结果计数的 credential gate 处理；429 在 permit Finish 已确认后写 Channel 级 Redis
   cooldown；403 在 Finish 已确认后暂停精确的 Channel、Model、Channel config revision 与 Origin revision
   组合。429 和 403 不写 breaker 样本。breaker Reset 不清除 cooldown 或 permission pause。
6. 默认 breaker control 使用 30 秒 eligible 窗口、20 个比例触发最小样本、0.5 失败率、10 秒内连续 3 次
   failure 快速触发、2 个不同 permit 的 half-open success，以及 15、30、60、120、300 秒 open 退避。
   `eligible_success` 增加分母并清空连续失败；`eligible_failure` 增加分子与分母并推进连续失败；`ignored`
   不改变样本和连续失败。
7. open 到期后的 Acquire 进入 half-open 并占用单个 lease；有效 lease 存在时其他 Acquire 返回
   `half_open_busy`。half-open 的 eligible success 释放 lease并累计成功，第二个不同 permit 成功后进入 closed；
   eligible failure 重新进入 open；ignored 只释放当前 lease。Finish 与 Abort 服从 first-terminal-wins。
8. permit 的 Origin fence、Channel config revision 或相应 breaker generation 已变化时，旧结果按各作用域返回
   stale disposition，未 stale 的作用域仍可独立应用。integrity epoch 已变化时，permit owner 在 Redis 调用前
   拒绝 Finish 或 Abort。
9. `gateway.circuit_breaker.enabled=false` 使 Acquire 不因 open 或 half-open 拒绝，并使 Finish 对两个 breaker
   返回 `not_applicable`。当前 Finish Lua 在该分支先于 Channel TTFT 更新返回，因此该设置同时停止新的 TTFT
   EWMA 样本；AttemptPermit、Origin fence、并发、RPM、RPD、TPM、429 cooldown、permission pause 和 Store
   fail-closed 仍执行。

## 代码与测试证据

当前代码和测试覆盖 transport start 与 Abort/Finish 边界、上游错误分类、eligible 与 ignored 样本、连续和比例
触发、分级 open 退避、half-open 单 lease 与双 permit success、重复终结、Channel 与 Origin 独立 generation、
三类隔离的 Origin 证据、429 cooldown、403 permission pause、revision/generation stale、Reset、共享状态和
跨 Gateway half-open lease 接管。

## 来源谱系

| 原 DEC | 原始日期 | 原状态 | 当前处理与修订关系 |
| --- | --- | --- | --- |
| DEC-029 | 2026-07-10 | accepted，部分被后续决策替换 | 进程内失败 cooldown 未进入当前候选排序；Channel 并发由候选 permit 管理。 |
| DEC-032 | 2026-07-20 | accepted，来源标注待实现 | 当前公共地址与服务故障域由 Provider Origin 承载。 |
| DEC-033 | 2026-07-20 | accepted，来源标注待实现 | 当前 permit generation 隔离迟到结果。 |
| DEC-038 | 2026-07-21 | accepted，来源标注待实现 | 当前 Provider Origin revision 与 fence 隔离旧结果。 |
| DEC-045 | 2026-07-21 | accepted，来源标注待实现 | 当前真实 transport 结果分类、作用域归因、429/403 独立反馈和无进程内失败 cooldown 行为。 |
| DEC-046 | 2026-07-21 | accepted，来源标注待实现 | 当前阈值、eligible 样本、half-open、退避和热更新 control。 |

## 取代关系

- 取代：无 Blueprint ADR；这是对上述来源的合并记录。
- 被取代：[ADR-0014：Provider 与 Channel 熔断归因](adr-0014-provider-breaker-attribution.md)。

## 状态说明

本文于 2026-07-26 按当时 Gateway 代码、Schema 与测试接收；2026-07-27 因 Origin 并入 Provider 被
[ADR-0014](adr-0014-provider-breaker-attribution.md) 取代，保留为决策谱系。

## 参考资料

- [韧性与熔断器](../features/resilience-circuit-breakers.md)
- [ADR-0008：运行态代际围栏](adr-0008-runtime-state-fencing.md)
- [ADR-0001：统一领域术语](adr-0001-domain-terminology.md)
