---
title: 路由负载均衡（客观评分）
description: Gateway 当前 Balanced 候选客观评分、确定性排序、Channel Sticky 与逐候选准入行为。
status: active
owner: 网关团队
last_updated: 2026-07-28
related:
  - ../overview.md
  - ../glossary.md
  - ../decisions/adr-0015-deterministic-cost-aware-routing.md
  - ../decisions/adr-0014-provider-breaker-attribution.md
  - admission-control.md
---

# 路由负载均衡（客观评分）

## 适用范围

本文记录 `balanced` Route 在显式 Channel 池内形成候选顺序的当前行为。`fixed` Route 只接受恰好一个
Channel，展示评分事实但不按评分重排。排序快照不预占资源；Channel 的真实容量由每次 transport 前的
`AttemptPermit` 决定。

## 候选输入与硬过滤

Router 只从 API Key 绑定 Route 的显式 Channel 池生成同协议候选。Provider、Channel、模型映射、凭据、
Adapter capability、价格和运行态等硬门禁先于评分处理。成本和客户售价必须使用相同币种与 pricing unit；
任一计价分项为正成本和零售价、成本高于售价或价格无效时，候选不进入可执行计划。通过检查的候选冻结
七个计价分项中最大的 Provider 成本与客户售价比为 `CostRatio`。

`SnapshotMany` 在一次只读 Redis 操作中核验 control 与候选 revision，并读取 breaker、cooldown、permission、
并发、RPM、RPD、TPM、错误窗口、Channel TTFT 和 `gateway.routing_balance`。runtime-sync、pending 或 stale
identity/config 使整批失败；Provider disabled、breaker open、cooldown 和 permission pause 等只排除对应候选。

## 客观评分

四项分数范围均为 0 到 100：

```text
经济分 = (1 - clamp(CostRatio, 0, 1)) * 100

延迟惩罚 = TTFT_EWMA / (TTFT_EWMA + TTFT目标)
健康分 = (1 - 错误率) * (1 - TTFT权重 * 延迟惩罚) * 100

容量分 = min(并发剩余率, TPM剩余率) * 100
Priority分 = 100 - Channel Priority

最终得分 = 经济分 * 经济权重
         + 健康分 * 健康权重
         + 容量分 * 容量权重
         + Priority分 * Priority权重
```

百分比权重在计算时除以 100。默认值是经济 45%、健康 25%、容量 20%、Priority 10%。计算规则如下：

- Priority 只允许 `0,10,...,100`，`0` 的 Priority 分为 100，`100` 的 Priority 分为 0；Priority 不形成分层。
- 某容量维度上限为 0 时剩余率为 1；只有一个容量维度可知时使用该维度；都不可知时容量分为 100。
- 没有错误率和 TTFT 样本时健康分为 100；只有 TTFT 样本时仍计算延迟惩罚。
- half-open 候选健康分和最终得分为 0。
- closed breaker 的 eligible 错误窗口过期时，只在快照副本中按无错误样本处理，不修改 Redis 状态或 TTFT。

## 确定性顺序与容量保护

普通 closed 候选按最终得分降序排列；总分相同时按较小 Priority、较小 Channel ID 排序。half-open 候选
排在普通候选之后并保留原顺序。不存在加权随机或全零容量的随机分支；全部容量分为 0 时仍按同一评分和
破同分规则形成完整 fallback 顺序。

确定性排序不会把首候选视为无限容量。执行器按冻结顺序逐一申请新的 `AttemptPermit`，原子检查 Channel
并发、RPM、RPD、TPM、breaker、cooldown、permission 和当前 control revision。普通候选被拒不创建 attempt
或 transport，并立即尝试下一候选；Store 故障或 `breaker_store_unavailable` 终止执行。

## Channel Sticky

Sticky 不参与评分，而是在客观排序后处理已有绑定：

| Channel 配置 | 行为 |
| --- | --- |
| `sticky_enabled = null` | 继承 `gateway.routing_sticky.enabled_default` 和全局 TTL。 |
| `sticky_enabled = true` | 开启，并要求该 Channel 的 `sticky_ttl_ms > 0`。 |
| `sticky_enabled = false` | 关闭，且 Channel 不接受自定义 TTL。 |

系统默认开启 Sticky，TTL 为 30 分钟。绑定年龄不因普通命中而刷新；到期后回到客观评分首选。`fixed` Route、
缺少会话信号或成功 Channel 禁用 Sticky 时不建立新绑定。旧绑定对应 Channel 被硬摘除或禁用 Sticky 时清除；
临时容量拒绝不清绑定，fallback 成功后按胜出 Channel 的策略决定改绑或清除。

Redis v2 绑定保存 `channel_id` 与 `bound_at_ms`。Channel 开关或 TTL 热更新在绑定下一次读取时惰性生效；
旧整数绑定在访问时比较后升级并继续服务，不要求清空 Redis。只有被有效 Sticky 绑定置顶的首候选在
`concurrency_limited` 或 `rate_limited` 时可按全局预算短等一次；普通评分首候选和后续候选不等待。

## 运行设置

`gateway.routing_balance` 当前字段与默认值为：

| 字段 | 默认值 | 用途 |
| --- | --- | --- |
| `economic_weight_pct` | 45 | 经济分权重 |
| `health_weight_pct` | 25 | 健康分权重 |
| `capacity_weight_pct` | 20 | 容量分权重 |
| `priority_weight_pct` | 10 | Priority 分权重 |
| `ttft_target_ms` | 2000 | 健康分中的延迟目标 |
| `ttft_weight` | 0.35 | TTFT 延迟惩罚系数 |
| `ttft_ewma_alpha` | 0.2 | 后续流式 TTFT 样本的 EWMA alpha |

四项百分比必须分别位于 0 到 100 且合计为 100。严格旧四/五字段 payload 继续兼容读取，并映射为默认
四权重；规范写入只使用新结构。新 control revision 影响后续请求快照，不改变已经冻结的请求计划，也不
清除 breaker、错误窗口、TTFT、限流或 Sticky 数据。

`gateway.routing_sticky` 继续保存系统默认开关、默认 TTL、Sticky 首候选等待和抖动预算。默认等待为 500ms
加 0 到 100ms 抖动，等待受客户 deadline 限制；`tpm_wait_ms=0` 可关闭等待。

## TTFT 与可观测事实

Channel 只保存 stream-only TTFT EWMA，样本从真实 transport start 到协议标记为 `FirstTokenEligible` 的
首个应用层流事件；非流式调用不生成样本。请求客户首帧 TTFT、attempt 上游 TTFT 与 Channel EWMA 是不同
口径，不互相代填。

Route runtime 和 routing trace 展示算法版本、四项分数、四项权重、最终得分、冻结顺序、Sticky 置顶、
候选资格、Permit fallback 与实际分流。旧 trace 缺少新字段时继续按旧成本/权重事实展示，不伪造客观分。

## 相关决策

- [ADR-0015：确定性成本感知路由与 Channel Sticky](../decisions/adr-0015-deterministic-cost-aware-routing.md)
- [ADR-0014：Provider 与 Channel 熔断归因](../decisions/adr-0014-provider-breaker-attribution.md)
- [ADR-0007：原子准入控制](../decisions/adr-0007-atomic-admission-control.md)
