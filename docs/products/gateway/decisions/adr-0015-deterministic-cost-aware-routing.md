---
title: "ADR-0015：确定性成本感知路由与 Channel Sticky"
description: "以经济、健康、容量和 Priority 客观分确定候选顺序，并把 Sticky 策略归属到 Channel。"
status: active
owner: 网关团队
last_updated: 2026-07-28
related:
  - ../features/routing-load-balancing.md
  - ../features/admission-control.md
  - ../../admin/pages/provider-channel-management.md
  - ../../admin/features/operations-observability.md
  - adr-0007-atomic-admission-control.md
  - adr-0009-objective-balanced-routing.md
---

# ADR-0015：确定性成本感知路由与 Channel Sticky

## 背景

传统负载均衡主要追求稳定性和容量利用率，各后端成本接近时，加权随机可以接受。UnioAPI 的 Channel
成本直接影响利润，同等可用条件下随机命中高成本 Channel 会形成不可控的经营结果。旧设计还把 Sticky
放在 Route 全局开关上，无法表达不同 Channel 的缓存收益和绑定时长。

## 决策驱动因素

- 优先使用低成本、可服务且有容量的 Channel，同时避免把最低价 Channel 当成无限容量资源。
- 同一组事实应产生相同候选顺序，便于运营解释、复现和热更新验证。
- Priority 必须是受控的运营偏好，不能变成任意精度的第二套隐式评分。
- Sticky 是 Channel 能力和成本策略，不应进入客观分，也不应继续由 Route 统一决定。
- 配置发布和版本升级不能要求清空业务 Redis。

## 备选方案

### 方案：保留加权随机并提高成本权重

**优点**

- 改动小，天然分散流量。

**缺点**

- 高成本 Channel 仍会被随机选为首候选，单次决策不可解释，利润结果不可控。

### 方案：按 Priority 分层后再评分

**优点**

- 可以强制优先使用某一层 Channel。

**缺点**

- 运营人员必须同时理解层级和评分，容易把 Priority 配成硬路由，增加认知和维护成本。

### 方案：四项客观分确定性排序

**优点**

- 成本、健康、容量和运营偏好使用同一套可解释模型；容量仍由实时 Permit 保护。

**缺点**

- 首候选会更集中，必须依赖准确的 Channel 限额和逐候选 fallback。

## 决策

1. `balanced` Route 的普通 closed 候选按经济、健康、容量和 Priority 四项客观分确定性排序，不再随机。
   默认权重依次为 45%、25%、20%、10%，四项权重允许热更新但总和必须为 100%。
2. Priority 只允许 `0,10,...,100`，`0` 表示最高运营偏好。Priority 进入评分，不形成额外分层；总分相同时
   才依次使用较小 Priority 和较小 Channel ID 破同分。
3. half-open 候选总分为 0，排在普通 closed 候选之后并保留原顺序。`fixed` Route 保持唯一候选顺序，
   可以展示评分事实但不按分数重排。
4. Sticky 不进入评分。策略归属 Channel：`null` 继承系统默认，`true` 必须配置 Channel TTL，`false`
   关闭。系统默认开启，TTL 为 30 分钟；`fixed` Route 不使用 Sticky。
5. 有效旧绑定在客观排序后把对应 Channel 置顶。普通候选遇容量拒绝立即 fallback；只有被 Sticky 固定的
   首候选可按全局短等预算等待并以新 Permit 重试一次。
6. 每个真实 transport 前必须取得独立 `AttemptPermit`。并发、RPM、RPD、TPM、breaker 和 permission
   等硬门槛保护 Channel；确定性首选不代表预占资源或保证放行。
7. Sticky 绑定保存 Channel、绑定时间和物理 TTL。Channel Sticky 配置或 TTL 热更新在绑定下次读取时生效；
   旧 Redis 整数绑定按访问惰性升级，不要求全量删除 Redis 数据。

## 影响

### 正面影响

- 低成本且运行状态良好的 Channel 更稳定地成为首选，路由结果可解释、可复现。
- 容量不足由原子 Permit 和 fallback 消化，不需要用全局随机保护单个 Channel。
- 每个 Channel 可以按自身 prompt cache 收益决定是否 Sticky 以及绑定时长。

### 负面影响

- 错误的成本、限额或权重配置会稳定地影响更多请求，运营配置质量比随机方案更重要。
- Sticky 可能暂时覆盖当前最高分候选，因此需要单独展示 pinned 和非首选 pinned 事实。

### 中性影响或后续工作

- `gateway.routing_balance` 继续保留 TTFT 目标、TTFT 系数和 EWMA alpha；它们只参与健康分及样本更新。
- 旧 routing-balance payload 兼容读取并映射到新默认四权重；规范写入只使用新字段。

## 风险与缓解措施

| 风险 | 缓解措施 | 负责人 |
| --- | --- | --- |
| 最便宜 Channel 被集中打满 | 配置 Channel 限额；每次 transport 前原子取得 Permit，拒绝后立即 fallback。 | 网关团队、运营团队 |
| 权重总和或 Priority 配置错误 | API、数据库和 Admin 控件共同约束；权重合计不为 100 时禁止保存。 | 网关团队、管理后台团队 |
| Sticky 保留过久覆盖低成本首选 | Channel 独立开关与 TTL；系统默认 30 分钟；到期不刷新绑定年龄。 | 运营团队 |
| 升级覆盖并发改绑或要求清缓存 | 旧绑定使用比较后更新的惰性升级，并保留在线数据。 | 网关团队 |

## 落地与验证

数据库、Gateway API、Redis 运行控制、候选评分、Sticky 存储、Permit 执行和 Admin 表单使用同一契约。
验证覆盖四项评分与确定性排序、同分规则、配置兼容、Channel Sticky 三态、旧绑定升级、TTL 变更、容量
fallback、Sticky 首候选短等，以及 Admin 的输入约束和运行态展示。热更新验证不得清空业务 PostgreSQL 或
Redis。

## 取代关系

- 取代：[ADR-0009：Balanced 路由](adr-0009-objective-balanced-routing.md)；并修订
  [ADR-0007](adr-0007-atomic-admission-control.md)中“任意首候选可短等”的范围。
- 被取代：无。

## 参考资料

- [路由负载均衡](../features/routing-load-balancing.md)
- [准入控制](../features/admission-control.md)
- [Provider 与 Channel 管理](../../admin/pages/provider-channel-management.md)
- [运营可观测性](../../admin/features/operations-observability.md)
