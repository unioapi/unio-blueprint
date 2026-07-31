---
title: "ADR-0016：五项客观路由、原子容量与 CAS Sticky"
description: "以五项客观分形成确定性候选顺序，以原子并发和全池短等保护容量，并以 CAS 状态机维护会话绑定。"
status: active
owner: 网关团队
last_updated: 2026-07-31
related:
  - ../features/routing-load-balancing.md
  - ../features/admission-control.md
  - adr-0007-atomic-admission-control.md
  - adr-0015-deterministic-cost-aware-routing.md
  - adr-0017-authoritative-first-token.md
---

# ADR-0016：五项客观路由、原子容量与 CAS Sticky

## 背景

[ADR-0015](adr-0015-deterministic-cost-aware-routing.md) 建立了确定性排序和 Channel Sticky，但其四项评分把
错误率与 TTFT 合并为健康分，把 TPM 纳入容量分，并允许 Sticky 首候选单独短等。Channel RPM、RPD、TPM
硬门槛和失败后隐式换绑又使一次路由难以解释。当前实现已经改为五项评分、Channel 并发唯一硬容量门槛、
全池短等和无直接 Rebind 的 CAS 状态机，需要以新的决策取代原设计。

## 决策驱动因素

- 每个候选的资格、五项得分、实际扫描、等待和绑定变化都必须可以单独解释。
- 上游只承诺并发限制时，Gateway 不应根据人工填写的 Channel RPM、RPD、TPM 主动拒绝请求。
- 确定性首选不能绕过真实并发容量，也不能让等待时长随候选数量增长。
- 并发请求不能误删或覆盖另一个请求刚建立的新绑定。
- 超时必须区分等待响应头、流式首字、流式空闲和非流式响应体。

## 决策

1. `balanced` Route 使用 `objective_v1` 五项客观分：成本 25%、Channel 并发容量 20%、TTFT 25%、
   错误率 20%、Priority 10%。权重可以热更新，但总和必须为 100%。同分时按较小 Priority、较小 Channel ID
   排序；`fixed` Route 不按分数重排。
2. TTFT 和错误率使用时间窗口内的真实 attempt 样本。TTFT 按算术平均值和可配置单位线性扣分，错误率按
   每 1% 可配置扣分线性惩罚；任一指标无样本时，该指标得 100 分。样本不与 breaker 窗口混用。
3. Channel RPM、RPD、TPM 只由请求记录聚合为观测事实，不参与候选资格、评分或 Gateway 主动拦截。
   Route 与 User Account 请求层的 RPM、RPD、TPM 限流继续独立生效。
4. Channel 并发容量是 Redis 原子硬门槛。候选只有取得 `AttemptPermit` 后才创建 attempt 和发起 transport；
   并发满时继续扫描其他候选。只有整池候选都仅因并发满而拒绝时，才共享一次有界等待，随后完整重扫一次。
   等待耗尽返回 503 和 `Retry-After: 1`；整池 429 冷却返回 429 和可证明的最短 `Retry-After`，不等待。
5. Sticky 键包含 protocol、Route、API Key、Model 和会话键哈希。绑定值只有一个 schema，保存 Channel、
   `binding_version` 和最近完整成功时间。写操作仅允许 `BindIfAbsent`、`RefreshIfCurrent`、
   `ClearIfCurrent`，CAS 同时比较 Channel 与绑定版本，不提供直接 Rebind。
6. 未绑定会话在某 Channel 完整成功后尝试建绑；原绑定 Channel 完整成功才滑动续期。并发满、429 冷却或
   真实上游 429 只保留原绑定且不续期；绕行 Channel 成功也不改绑。确认的凭据、权限、timeout、server
   等绑定 Channel 失败可以 CAS 清除；客户取消、客户请求错误和 Gateway 自身故障不改变绑定。Sticky Store
   失败按 miss 或写失败处理，不阻断请求主链路。
7. Channel 只配置 `response_timeout_ms` 与 `first_token_timeout_ms`。非流式 response timeout 覆盖连接、
   响应头、完整响应体与解析；流式 response timeout 只约束取得响应头。first-token timeout 与响应头计时
   同起点，并在首个有效生成 Token 到达时停止；其后由全局 stream-idle timeout 接管。不存在流式总时长上限。
   权威首字判定与双 TTFT 见 [ADR-0017](adr-0017-authoritative-first-token.md)。
8. 每个进入路由规划的请求保存一条从 `partial` 收口到 `complete` 的结构化 trace，并与请求记录一对一绑定。
   trace 保存资格快照、五项评分、基准和实际扫描顺序、真实 attempt、Sticky CAS、容量等待、最终结果与
   超时阶段；不再使用百分比采样或拼接文本作为主要证据。

## 影响

### 正面影响

- 候选排序、容量拒绝和绑定变化可以由同一条请求 trace 复现。
- 无请求的新 Channel 不因缺少样本被先天惩罚；真实慢或错误样本按明确线性规则扣分。
- 全池短等吸收极短容量波动，同时维持固定的最坏等待边界。
- CAS 阻止并发请求覆盖或误删已经变化的绑定。

### 负面影响

- 无样本 Channel 的 TTFT 与错误率均为满分，首次流量会更积极地探索新 Channel。
- 确定性排序会集中首选流量，错误的成本、Priority、并发容量或评分参数会稳定地放大影响。
- timeout 和 server failure 会清除当前绑定，因此分类错误会损失一次上游缓存亲和性。

## 风险与缓解措施

| 风险 | 缓解措施 | 负责人 |
| --- | --- | --- |
| 新 Channel 满分样本项带来突发流量 | 原子并发门槛、fallback 和完整 trace 限制并解释影响 | 网关团队、运营团队 |
| 全池短等被误用于 429 或 breaker | 进入条件只接受整池 `concurrency_full`，测试冻结 429、混合拒绝和取消分支 | 网关团队 |
| 并发请求误改 Sticky | 所有删除和续期同时比较 Channel 与 `binding_version` | 网关团队 |
| 超时分类不清导致错误处置 | attempt 保存稳定的 `upstream_timeout_phase`，请求 trace 展示阶段 | 网关团队 |

## 落地与验证

当前数据库、Redis control、Gateway 路由、Admin API 和请求 trace 使用同一 `objective_v1` 契约。测试覆盖五项
公式、无样本满分、确定性同分、并发全池短等、整池冷却、单请求不重复 Channel、Sticky CAS 竞态、临时保留、
永久清除、四类超时阶段，以及 trace 的一对一持久化和请求级查询。

## 取代关系

- 取代：[ADR-0015：确定性成本感知路由与 Channel Sticky](adr-0015-deterministic-cost-aware-routing.md)。
- 修订：[ADR-0007：原子准入控制](adr-0007-atomic-admission-control.md) 中 Channel 三维限额和 Sticky 队首短等。
- 被取代：无。

## 参考资料

- [路由负载均衡](../features/routing-load-balancing.md)
- [准入控制](../features/admission-control.md)
- [韧性与熔断器](../features/resilience-circuit-breakers.md)
