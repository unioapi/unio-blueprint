---
title: "ADR-0009：Balanced 路由"
description: "记录 Balanced 当前候选过滤、权重计算、排序与准入时序。"
status: active
owner: 网关团队
last_updated: 2026-07-26
related:
  - ../features/routing-load-balancing.md
  - ../features/admission-control.md
  - ../features/resilience-circuit-breakers.md
  - adr-0001-domain-terminology.md
---

# ADR-0009：Balanced 路由

## 范围

本文记录当前 Gateway 的 Balanced 候选过滤、容量与运行态评分、成本因子、加权排序、Channel TTFT 和
候选准入时序。

## 当前实现

1. Router 只从 API Key 所绑定 Route 的显式 Channel 池生成候选。候选在进入 lifecycle 前经过状态、协议、
   模型映射、凭据、价格与非负毛利检查，并冻结七个归一化计价分项中最大的 Provider 成本与客户售价比
   `CostRatio`。
2. lifecycle 先按 Adapter operation capability 过滤候选，再通过一次只读 `SnapshotMany` 获取候选运行态、
   容量与当前 `gateway.routing_balance` control。Snapshot 状态为 current、no-sample 或 half-open 的候选进入
   排序；其他状态不进入此次候选计划。没有 request session 的直接调用保持 SQL 顺序并生成中性运行态评分。
3. Balanced 当前权重为：

   ```text
   容量分 = min(并发剩余率, TPM 剩余率)
   延迟惩罚 = TTFT_EWMA / (TTFT_EWMA + TTFT目标)
   运行因子 = max(最小路由因子, (1 - 错误率) * (1 - TTFT权重 * 延迟惩罚))
   成本因子 = max(最小路由因子, 1 - 成本权重 * clamp(CostRatio, 0, 1))
   最终权重 = 容量分 * 运行因子 * 成本因子
   ```

   限额为 0 的容量维度按剩余率 1 计算；没有 TTFT 样本时延迟惩罚为 0。closed breaker 的 eligible 窗口
   已过期时，`SnapshotMany` 只在返回副本中把错误样本按无样本处理，不修改 Redis 状态或 Channel TTFT。
4. 普通 closed 候选按最终权重加权随机且不放回排序。此次全部普通候选容量分为 0 时，候选按并发与 TPM
   压力的组合值稳定升序排列。half-open 候选的运行因子和权重为 0，不参与普通加权随机，并按原顺序追加。
   sticky 在上述排序完成后把仍在候选计划中的绑定 Channel 移到首位。
5. Channel 只保存一套 stream-only TTFT EWMA。样本从 Adapter 紧邻 `http.Client.Do` 前记录的 transport start
   到协议标记为 `FirstTokenEligible` 的首个应用层流事件；非流式调用不生成该样本。样本随 stream permit
   `Finish` 应用到当前 Channel generation，EWMA alpha 从当时已提交的 `gateway.routing_balance` control 读取。
6. `gateway.routing_balance` 当前包含 `ttft_target_ms`、`ttft_weight`、`cost_weight`、
   `minimum_routing_factor` 和 `ttft_ewma_alpha`。默认值分别为 2000、0.35、0.5、0.05 和 0.2。严格旧四字段
   payload 被解释为 `cost_weight=0`。新 control revision 影响后续快照评分；热更新不清除既有 breaker、错误
   窗口、TTFT、限流或 sticky 状态。
7. 排序快照不取得候选资源。每个真实上游 transport 前，Gateway 使用新的 permit ID 调用
   `AcquireAttempt`，原子取得该候选的 breaker、half-open、Channel 并发、RPM、RPD 与 TPM 资源。普通业务
   拒绝不创建 attempt 或 transport，并可继续后续候选；Go/Store 错误或 `breaker_store_unavailable` 终止执行。
8. 请求 `ttft_ms`、attempt `upstream_ttft_ms` 与 Channel TTFT EWMA 使用不同存储位置。请求值从请求开始到
   客户首帧，attempt 值和 Channel 样本从上游 transport start 到 `FirstTokenEligible`；Channel EWMA 还受
   permit Finish 与 revision/generation 围栏约束。

## 代码与测试证据

当前代码和测试覆盖 Route 候选与毛利过滤、`CostRatio` 冻结、Adapter capability 与运行态快照过滤、容量与
错误率评分、stream-only TTFT、成本因子、旧四字段 control、加权随机且不放回、全零容量压力排序、half-open
追加、sticky 置顶、过期错误窗口只读中性化，以及每个真实 transport 前的新 `AttemptPermit` 准入。

## 来源谱系

| 原 DEC | 原始日期 | 原状态 | 当前处理与修订关系 |
| --- | --- | --- | --- |
| DEC-034 | 2026-07-20；2026-07-21 取代 | superseded by DEC-035 | 非流式延迟样本和双 EWMA 未进入当前实现。 |
| DEC-035 | 2026-07-21 | accepted，来源标注待实现 | 当前 Channel stream-only TTFT EWMA 与无样本中性行为。 |
| DEC-047 | 2026-07-21 | accepted，来源称已实现，DEC-055 扩展 | 当前运行因子、默认参数、热更新和快照 control。 |
| DEC-049 | 2026-07-21 | accepted，来源标注待实现 | 当前运行态接口展示 breaker、错误率、TTFT、容量、权重和分流事实。 |
| DEC-055 | 2026-07-23 | accepted，来源称已实现 | 当前成本因子与过期错误窗口只读中性化。 |

## 取代关系

- 取代：无 Blueprint ADR；这是对上述来源的合并记录。
- 被取代：无。

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码、Schema 与现有测试接收为 `active`。

## 参考资料

- [路由负载均衡](../features/routing-load-balancing.md)
- [准入控制](../features/admission-control.md)
- [韧性与熔断器](../features/resilience-circuit-breakers.md)
