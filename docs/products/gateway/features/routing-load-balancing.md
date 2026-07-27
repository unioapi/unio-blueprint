---
title: 路由负载均衡（balanced 权重调度）
description: Gateway 当前 Balanced 候选评分、排序、sticky 与逐候选准入行为。
status: active
owner: 网关团队
last_updated: 2026-07-27
related:
  - ../overview.md
  - ../glossary.md
  - ../decisions/adr-0001-domain-terminology.md
  - ../decisions/adr-0009-objective-balanced-routing.md
  - ../decisions/adr-0014-provider-breaker-attribution.md
  - admission-control.md
---

# 路由负载均衡（balanced 权重调度）

## 适用范围

本文记录 `balanced` Route 在显式 Channel 池内形成候选顺序的当前行为。`fixed` Route 只接受恰好一个
Channel 的候选池，不执行多候选加权排序。候选资源由 transport 前的 `AttemptPermit` 取得，不由排序快照
预占。

## 候选输入

Router 按 API Key 绑定的 Route 与请求模型生成同协议候选，并在进入 lifecycle 前处理以下事实：

- Provider、Channel、Model 与 Channel-Model 状态；
- Channel protocol、Adapter key、上游模型映射和 credential validity；
- 客户售价、Channel 成本、币种与 pricing unit；
- 七个归一化计价分项中的 Provider 成本与客户售价比。

任一计价分项为正成本和零售价，或成本高于售价时，该候选不进入计划。通过检查的候选冻结各分项比值中的
最大值为 `CostRatio`。

## 当前调度流程

1. Adapter registry 按 ingress protocol 与本次 operation capability 过滤候选。
2. `SnapshotMany` 在同一次 Redis Lua 调用中核验 integrity、control revision 和候选 revision，并读取各候选的
   Provider/Channel breaker、429 cooldown、permission pause、并发、RPM、RPD、TPM、错误窗口、Channel TTFT
   和当前 routing-balance control。
3. runtime-sync、pending 或候选 revision/config stale 使整批快照返回错误。Provider disabled、cooldown、
   permission pause、breaker open 或 half-open busy 等候选状态只排除对应候选。
4. 对进入计划的候选逐一计算权重。`SnapshotMany` 是只读操作，不取得候选并发、RPM、RPD 或 TPM。
5. 普通 closed 候选按权重加权随机且不放回排序。half-open 候选不参加普通随机，并按原顺序追加。
6. sticky 在上述排序后，把仍存在于计划中的绑定 Channel 移到首位，其他候选保持相对顺序。
7. 执行器按冻结顺序逐个候选调用 `AcquireAttempt`。每个真实 transport 使用新的 permit ID；denied 候选不创建
   attempt 或 transport。Go/Store 错误或 `breaker_store_unavailable` 终止执行，其他 denied reason 可继续
   后续候选。

## 权重公式

```text
并发剩余率 = 1 - 并发已用 / 并发上限
TPM 剩余率 = 1 - TPM 已用 / TPM 上限
容量分 = min(并发剩余率, TPM 剩余率)

延迟惩罚 = TTFT_EWMA / (TTFT_EWMA + TTFT目标)
运行因子 = max(最小路由因子,
                 (1 - 错误率) * (1 - TTFT权重 * 延迟惩罚))

成本因子 = max(最小路由因子,
                 1 - 成本权重 * clamp(CostRatio, 0, 1))

最终权重 = 容量分 * 运行因子 * 成本因子
```

计算规则如下：

- 某容量维度的上限为 0 时，该维度剩余率为 1。
- 容量已用值按不小于 0 处理，剩余率限制在 0 到 1。
- Channel 没有 TTFT 样本时，延迟惩罚为 0。
- 错误率和 `CostRatio` 在评分时限制在 0 到 1。
- half-open 候选的运行因子与最终权重为 0。
- `fixed` 模式记录容量与 `CostRatio` 事实，但成本因子为 1，不改变 SQL 候选顺序。

closed breaker 的 eligible 错误窗口已超过当前 breaker window 时，`SnapshotMany` 只在返回副本中把成功数、
失败数和错误率按无样本处理，不修改 Redis state，也不清除 Channel TTFT。

## 全零容量

此次参与评分的全部普通候选容量分都为 0 时，不执行加权随机。候选按并发与 TPM pressure 的组合值稳定升序
排列，half-open 候选继续保序追加。零容量候选仍留在 fallback 计划中，transport 前由 `AcquireAttempt` 决定
是否取得资源。

## TTFT

Channel 保存一套 stream-only TTFT EWMA：

- 起点是 Adapter 紧邻 `http.Client.Do` 前记录的 transport start；
- 终点是协议层标记为 `FirstTokenEligible` 的首个应用层流事件；
- 非流式调用不生成 TTFT 样本；
- stream permit 的 `Finish` 在 Channel generation 与 revision 可应用时更新样本；
- EWMA alpha 从 Finish 当时已提交的 `gateway.routing_balance` control 读取；
- Provider 不保存 TTFT。

请求列表和 Dashboard 的 `ttft_ms` 从请求开始到客户首帧；attempt 的 `upstream_ttft_ms` 从 transport start
到 `FirstTokenEligible`。Channel EWMA 使用 attempt 口径，并额外受 permit Finish 与围栏结果约束。

## 运行设置

`gateway.routing_balance` 当前字段与默认值为：

| 字段 | 默认值 | 当前用途 |
| --- | --- | --- |
| `ttft_target_ms` | 2000 | 延迟惩罚分母中的目标值 |
| `ttft_weight` | 0.35 | 延迟惩罚在运行因子中的系数 |
| `cost_weight` | 0.5 | `CostRatio` 在成本因子中的系数 |
| `minimum_routing_factor` | 0.05 | 运行因子和成本因子的下限 |
| `ttft_ewma_alpha` | 0.2 | 后续 TTFT 样本的 EWMA alpha |

当前解码器接受严格五字段 payload，也接受不含 `cost_weight` 的严格旧四字段 payload；旧形状被解释为
`cost_weight=0`。提交新 control revision 后，后续快照使用新参数。热更新不清除 TTFT、breaker、错误窗口、
限流、cooldown、permission 或 sticky 状态。

## Sticky 与队首短等

- Snapshot 阶段排除 sticky Channel 时，置顶失败并清除绑定。
- Snapshot 后 Acquire 返回 breaker open 或 half-open busy 时清除绑定；rate/concurrency、permission 和其他
  denied reason 不清除绑定。
- 冻结计划首候选首次因 `concurrency_limited` 或 `rate_limited` 被拒时，执行器按
  `gateway.routing_sticky` 预算无资源等待一次，再用新 permit ID 和当时 revision 重试。
- 默认等待预算为 500ms 加 0 到 100ms 抖动，并受请求 deadline 限制。
- 同一首候选的 primary transport 与透明 fallback 共用一次等待预算；后续候选不等待。

## 可观测事实

Route runtime 接口按模型返回候选资格、容量、错误率、TTFT EWMA 与样本数、`CostRatio`、成本因子、最终
权重、breaker、cooldown、permission 和近 1/5 分钟实际选中占比。执行日志与 routing trace 分别记录候选
排除、冻结顺序和真实尝试。当前没有一条记录同时关联评分快照、每次 `AcquireAttempt` 返回、transport 与
permit 终结。

## 代码与测试证据

当前代码和测试覆盖候选过滤、`CostRatio`、容量/错误率/TTFT/成本公式、旧四字段 control、加权随机且不放回、
全零容量压力排序、half-open 追加、sticky 置顶、队首短等、过期错误窗口只读中性化和逐 transport permit。

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码、Schema 与现有测试接收为 `active`。

## 相关决策

- [ADR-0009：Balanced 路由](../decisions/adr-0009-objective-balanced-routing.md)
- [ADR-0014：Provider 与 Channel 熔断归因](../decisions/adr-0014-provider-breaker-attribution.md)
- [ADR-0007：原子准入控制](../decisions/adr-0007-atomic-admission-control.md)
