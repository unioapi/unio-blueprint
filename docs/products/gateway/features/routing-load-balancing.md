---
title: 路由负载均衡（五项客观评分）
description: Gateway 当前五项候选评分、确定性排序、原子并发、CAS Sticky、分阶段超时与完整路由 trace。
status: active
owner: 网关团队
last_updated: 2026-07-31
related:
  - ../overview.md
  - ../glossary.md
  - ../decisions/adr-0016-five-factor-routing-and-cas-sticky.md
  - ../decisions/adr-0017-authoritative-first-token.md
  - ../decisions/adr-0014-provider-breaker-attribution.md
  - admission-control.md
---

# 路由负载均衡（五项客观评分）

## 适用范围

本文记录 `balanced` Route 在显式 Channel 池内形成候选顺序、取得真实容量、处理会话绑定和记录路由过程的
当前行为。`fixed` Route 只接受恰好一个 Channel，可以展示评分事实但不按得分重排。评分和排序都不预占
资源；每次真实 transport 仍必须取得独立 `AttemptPermit`。

## 基础池与候选资格

Router 只从 API Key 绑定 Route 的显式 Channel 池生成同协议、同模型候选。以下事实先于评分：

- Route、Provider、Channel 和 Route-Channel 关系有效；
- credential、Provider origin、Protocol、Adapter 和模型映射完整；
- 客户售价与 Provider 成本使用可比较的币种、单位和七项价格向量，且不存在负毛利；
- Provider breaker、Channel breaker、429 cooldown 和 Channel-Model permission 允许本次调用；
- PostgreSQL revision、Redis committed control、runtime epoch 和 server identity 一致。

基础池无效或候选无资格都不是评分项。Channel RPM、RPD、TPM 只作为自动聚合的观测指标，不影响基础池、
候选资格、评分或 Gateway 主动拦截。上游真实返回 429 时仍写 Channel cooldown。

## 五项客观评分

每个指标分范围为 0 到 100，默认总分贡献为成本 25、并发容量 20、TTFT 25、错误率 20、Priority 10：

```text
成本分 = (1 - clamp(成本 / 客户售价, 0, 1)) * 100
并发分 = clamp((上限 - 在途) / 上限, 0, 1) * 100
TTFT分 = max(0, 100 - 平均TTFT / 惩罚单位 * 每单位扣分)
错误率分 = max(0, 100 - 错误率百分比 * 每1%扣分)
Priority分 = clamp(100 - Priority, 0, 100)

最终得分 = 成本分 * 成本权重
         + 并发分 * 并发权重
         + TTFT分 * TTFT权重
         + 错误率分 * 错误率权重
         + Priority分 * Priority权重
```

百分比权重在计算时除以 100，并且五项权重合计必须为 100%。当前默认参数为：

| 配置 | 默认值 | 行为 |
| --- | ---: | --- |
| `cost_weight_pct` | 25 | 成本分贡献上限 |
| `concurrency_weight_pct` | 20 | Channel 并发分贡献上限 |
| `ttft_weight_pct` | 25 | TTFT 分贡献上限 |
| `error_rate_weight_pct` | 20 | 错误率分贡献上限 |
| `priority_weight_pct` | 10 | Priority 分贡献上限 |
| `ttft_window_ms` | 1,800,000 | TTFT 样本窗口，30 分钟 |
| `ttft_penalty_unit_ms` | 1,000 | 每个 TTFT 惩罚单位为 1 秒 |
| `ttft_penalty_points_per_unit` | 2.5 | 每个单位扣 2.5 分，40 秒时归零 |
| `error_window_ms` | 1,800,000 | 错误率样本窗口，30 分钟 |
| `error_penalty_points_per_percent` | 2.5 | 错误率每 1% 扣 2.5 分 |

Channel 并发上限为 `0` 时表示不限，并发分为 100。TTFT 只使用流式 attempt 从真实 transport start 到首个
有效生成 Token 的上游样本；错误率使用明确标记为评分样本的 attempt。任一时间窗口内没有对应样本时，该指标分为
100，不影响其他指标。breaker 自身窗口与这两个评分样本窗口相互独立。Dashboard 与请求级展示使用独立的
Gateway TTFT（`gateway_first_token_at - started_at`），不参与渠道评分。

首字超时只计入错误率样本，不把未产生有效生成 Token 的等待时长伪装成 TTFT 样本；因此超时 attempt 的
`upstream_ttft_ms` 保持为空。

## 确定性顺序

普通 closed 候选按最终得分降序排列；总分相同时按较小 Priority、较小 Channel ID 排序。half-open 候选总分
归零并固定排在普通候选之后，由 breaker 探测许可控制。不存在随机抖动、Priority 分层或全零容量随机分支。

排序形成 `baseline_order`。有效 Sticky 绑定可以把原绑定 Channel 置顶，形成实际扫描顺序，但不会改写任何
候选的分数。一次请求不会对同一 Channel 发起第二次真实 transport，因此实际尝试顺序不能出现 A → B → A。

## 原子并发与全池短等

每个候选在 transport 前原子检查 runtime revision、Provider/Channel breaker、429 cooldown、模型权限和 Channel
并发。只有取得 permit 后才创建 attempt。并发满只跳过当前候选，执行器继续扫描其他候选。

只有本轮所有候选都仅因 `concurrency_full` 被拒绝时，才进入一次全池共享的有界等待。当前默认预算为
`gateway.capacity_wait_timeout_ms = 1000`，等待期间不持有任何 Channel permit，预算受客户 deadline 限制。
等待结束后完整重扫一次候选池；它不只重试 Sticky Channel，也不按 Channel 分别累加等待。

- 重扫取得 permit：继续正常调用并记录 `capacity_wait_result=acquired`。
- 仍然全部并发满：返回 503、`routing_channel_capacity_exhausted` 和 `Retry-After: 1`。
- 全部候选处于 429 cooldown：不等待，返回 429 和最短可证明 `Retry-After`。
- breaker、permission、revision 或混合拒绝：不进入容量等待，按候选或安全 503 规则收口。

## CAS Sticky

Sticky 是客观排序后的会话亲和提示，不保证缓存命中，也不预留容量。`fixed` Route、没有会话信号或当前策略
关闭时不启用。Channel 策略为：

| Channel 配置 | 行为 |
| --- | --- |
| `sticky_enabled = null` | 继承 `gateway.routing_sticky.enabled_default` 与全局 TTL。 |
| `sticky_enabled = true` | 开启，并要求正数 `sticky_ttl_ms`。 |
| `sticky_enabled = false` | 关闭，且不接受 Channel 自定义 TTL。 |

系统默认开启，TTL 为 30 分钟。Redis 键使用
`protocol + route_id + api_key_id + model_id + session_hash`；原始会话标识只做定长哈希，不写入键或日志。绑定值
只有 `{v, channel_id, binding_version, last_success_at_ms}` 一个 schema。`binding_version` 是 CAS 身份，不是兼容版本。

状态只有 Unbound 与 Bound，写操作只有：

- `BindIfAbsent`：未绑定会话在某 Channel 完整成功后建立绑定；首轮并发只有一个请求能成功。
- `RefreshIfCurrent`：原绑定 Channel 完整成功且 Channel 与 binding version 都未变化时，滑动续期完整 TTL。
- `ClearIfCurrent`：只有当前 Channel 与 binding version 都匹配时删除；不提供直接 Rebind。

绑定 Channel 因并发满、cooldown 或真实上游 429 临时绕行时保留原绑定且不续期；其他 Channel 绕行成功也不
改绑。绑定 Channel 的 credential、permission、timeout、server 或其他明确上游故障可以清绑定。客户取消、客户
请求错误、未分类错误和 Gateway 自身的 Store、结算或运行态故障不改变绑定。Sticky Redis 读写失败 fail open，
不会阻断主请求。

候选快照在排序前发现绑定 Channel 处于 cooldown，并以 `rate_limited` 将它排除时，同样属于临时绕行：不得记录
`pin_lost` 或调用 `ClearIfCurrent`，绕行 Channel 成功后也不得建立新绑定。Routing trace 使用
`sticky_cooldown_bypass` 区分这种情况与真正的 `sticky_invalid`，并在候选事实中保留 cooldown 剩余时间。

## 分阶段超时

Channel 只配置两个可继承字段：

| 字段 | 非流式 | 流式 |
| --- | --- | --- |
| `response_timeout_ms` | 从发起调用起，限制连接、响应头、完整响应体与解析 | 从发起调用起，只限制取得 HTTP 响应头 |
| `first_token_timeout_ms` | 不使用 | 与 response timeout 同起点，限制首个有效生成 Token（上游首字超时） |

全局默认分别为 200 秒和 60 秒。流式首个有效生成 Token 后，改由
`gateway.stream_idle_timeout_ms` 限制相邻流活动的最大静默时间，当前默认 10 分钟；没有流式总时长上限。
HTTP 响应头、SSE 空行、注释、纯心跳以及协议前导帧不会停止上游首字计时。attempt 用稳定枚举记录
`response_header`、`first_token`、`stream_idle` 或 `response_body`，客户取消不标记为上游超时。

权威首字判定与双 TTFT 见
[ADR-0017](../decisions/adr-0017-authoritative-first-token.md)。

## 完整路由 trace

每个进入路由规划的请求对应一条独立 `routing_decision_traces` 记录，并通过 request ID 一对一关联。规划开始时
状态为 `partial`，请求收口后为 `complete`；改造前旧行只可标为 `legacy_sampled`，页面不会伪造缺失过程。

结构化 trace 保存：候选资格与原因、五项输入/分数/权重、`baseline_order`、实际扫描和真实 attempt 顺序、
Sticky 前后绑定与 CAS 动作、全池等待时长和结果、最终 Channel、fallback 次数、最终结果及 timeout phase。
trace 随 request record 级联删除，不设置独立采样率或独立保留 worker。

## 相关决策

- [ADR-0016：五项客观路由、原子容量与 CAS Sticky](../decisions/adr-0016-five-factor-routing-and-cas-sticky.md)
- [ADR-0017：权威首字判定与双 TTFT](../decisions/adr-0017-authoritative-first-token.md)
- [ADR-0014：Provider 与 Channel 熔断归因](../decisions/adr-0014-provider-breaker-attribution.md)
- [ADR-0007：原子准入控制](../decisions/adr-0007-atomic-admission-control.md)
