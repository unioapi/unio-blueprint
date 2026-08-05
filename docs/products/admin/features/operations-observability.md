---
title: 运营可观测性
description: 管理后台以客观事实支持运行判断和经营分析的设计。
status: draft
owner: 管理后台团队
last_updated: 2026-08-05
related:
  - ../overview.md
  - ../quality.md
  - ../pages/operations-dashboard.md
  - ../decisions/adr-0001-objective-operational-facts.md
  - ../../gateway/decisions/adr-0015-deterministic-cost-aware-routing.md
  - ../../../specifications/logging.md
---

# 功能设计：运营可观测性

## 摘要

运营可观测性为运营人员提供经营、分析和实时运行视图。它并列展示可核验事实，而非将不同时间尺度和不同故障原因压缩成主观健康标签。

## 目标

- 在当前运行判断中区分可服务、不可服务、基础设施故障和无样本。
- 在经营金额展示中按币种分组，不引入汇率或跨币种求和。
- 将首页决策、深度分析和实时监控分层，避免首页成为数据仓库。

## 非目标

- 派生或展示 `healthy`、`degraded`、`unhealthy`、`no_data` 等主观健康桶。
- 将 24 小时历史成功率或检测成功冒充当前 breaker、容量或可服务性。
- 将缓存贡献与账本收入、成本或利润混为一项事实金额。

## 使用体验

运营人员先在经营驾驶舱首屏于 30 秒内判断收入、毛利、利润率、缓存贡献估算、请求数、成功率、异常请求和客户余额池的变化；需要解释时进入利润、渠道、模型、缓存、用户或异常分析中心；需要即时运行状态时进入独立实时监控页。

## 需求

### 功能需求

- Provider、Channel、模型、线路和 Dashboard 并列展示客观事实：Provider 双 revision 与 breaker、凭据状态、
  主动检测、eligible 错误率与样本、Channel 最近 30 分钟平均上游 TTFT、请求 Gateway TTFT、attempt 上游
  TTFT、流式/非流式总耗时、容量与临时超限、运行态同步、成本/并发容量/TTFT/错误率/Priority 五项分数、
  最终得分和实际分流。
- Route runtime 必须区分 `eligible`、`probe_only` 和 `excluded`：`probe_only` 只显示“仅探测”，不承担普通流量，
  不展示或解释普通候选排序总分；`excluded` 的稳定原因使用页面中文映射，数据库预先排除且未执行毛利检查时不伪造
  一条失败的 margin check。
- 当前“可服务/不可服务/基础设施故障”只能由当前硬门禁和运行态 readiness 直接推导；基础设施故障必须明确表示准入已拒绝，并与无样本区分。
- Channel TTFT 评分只使用流式 attempt 从 transport start 到有效生成 Token 的样本，并按最近 30 分钟窗口
  做算术平均；请求级 Gateway TTFT 使用业务建档到对应有效生成 Token 成功写入客户的时间。两者不得互相
  代填，非流式只显示总耗时。stale 版本不得展示旧的 breaker、Channel TTFT 或评分。
- 系统设置展示成本、并发容量、TTFT、错误率与 Priority 五项整数百分比，实时显示合计；合计不为 100 时
  禁止保存。Route runtime 同时展示算法版本、五项分数、五项权重、完整计算过程和最终得分；旧 trace 缺字段
  时保留旧视图。
- Route runtime 对每个 Channel 展示当前筛选模型实际采用的成本来源。绝对成本、模型基准价乘价格倍率与
  充值倍率、成本未配置三种状态必须区分；倍率事实与本次候选评分来自同一运行快照，首屏不按 Channel
  追加独立定价请求。
- 首页为决策层，仅显示 8 项 KPI、本期与上期同长度窗口比较和状态 Banner；不放逐项明细、排行榜或 Token 拆解。
- 金额按币种拆卡；利润率只在同币种内计算；缓存贡献是反事实估算，必须标为“估算”。
- 二级分析中心和实时监控页使用独立视图与数据源。实时 QPS、TPS、RPM、TPM、P99 和错误率不得伪装为数据库经营聚合。
- 模型详情的缓存命中率只计算 `cache_read_tokens / input_tokens`；cache write 作为独立缓存事实展示，不并入命中率。

### 数据边界

运营视图消费经过授权的请求、用量、账务、检测和运行态事实；不展示凭据、上游正文或内部敏感诊断。
Provider 列表不逐行读取 Redis 运行态，详细运行态属于 Provider 详情或实时路由页面。

### Gateway 日志监控

“系统设置 > 日志监控”是当前 Gateway 文件日志的内置运维入口，同时提供临时 DEBUG 控制、实例应用状态
和 Loki 基础查询，不承担日志采集、持久化、全文索引或告警计算。

日志等级有三种页面模式：

| 模式 | 含义 | 可执行操作 |
| --- | --- | --- |
| `info` | Gateway 以生产 INFO 基线运行。 | 开启 5、15、30 或 60 分钟临时 DEBUG，默认选择 15 分钟且必须填写原因。 |
| `debug` | 全 Gateway 临时 DEBUG 会话有效。 | 查看开始/到期时间、原因、操作人和 revision；延长会话或手动关闭。 |
| `environment_debug` | 实例由开发环境变量以 DEBUG 为启动基线。 | 不允许再创建临时会话，也不显示关闭操作。 |

临时会话最长 60 分钟，没有永久选项。延长当前有效会话保留 session ID 和原开始时间，以本次提交时间重新
计算到期点。Gateway 设置轮询应用最新 revision，并在每个实例内建立独立到期 timer；即使后续 Redis 或
设置轮询中断，也会按已应用的 `expires_at` 自动恢复 INFO。进程重启后重新读取当前设置，已过期会话不会
恢复 DEBUG。页面每 5 秒读取 configured Gateway 实例的实际基线、当前等级、会话 ID 和应用 revision，并以
`applied`、`pending`、`unreachable` 或 `environment_debug` 展示，不能只把控制行写入成功当成全实例已生效。

最近日志查询由 Admin Server 访问内网 Loki，浏览器不会获得 `LOKI_URL` 或直连 Loki。页面支持
`15m/1h/6h/24h/7d` 时间范围、level、type、event、关联 ID、内容和 50/100/200 条上限筛选，结果倒序展示；
V1 不提供分页。单条日志使用右侧详情面板展示信封与完整结构化 `data`，不把对象压成不可读文本。Loki 查询
超时为 5 秒，不可用返回 503，非法筛选返回 400。

当前部署链路为 `Gateway JSONL -> Grafana Alloy -> Loki -> Admin Server`；Grafana 不在 V1 部署范围内。
Alloy、Loki 和 Prometheus 是独立容器与持久卷，日志仍以 Gateway 本地 JSONL 为第一份文件事实。Loki 执行
ERROR、WARNING、HTTP 5xx、上游首字超时和结算失败规则；Prometheus 执行 Alloy 停采、Loki 不可用/写入失败
和日志磁盘容量规则。

## 状态与边界情况

| 状态或条件 | 预期行为 | 恢复方式 |
| --- | --- | --- |
| Channel 无上游 TTFT 样本 | 显示样本为零，TTFT 维按满分参与评分；合法 0ms 样本仍有正样本数 | 等待真实流式 attempt 解析出有效生成 Token。 |
| Channel 当前配置尚无运行身份 | 按无样本展示；runtime Channel revision 为空不视为版本不一致，不隐藏当前容量与评分 | 首次真实请求取得 permit 时延迟建立运行身份。 |
| 运行态基础设施故障 | 显示准入已拒绝，不回退为“健康”或无样本 | 运行态恢复与对账后重新观察。 |
| 配置版本 stale | 不展示旧 breaker、Channel TTFT 或评分 | 等待当前版本事实。 |
| 多币种金额 | 分币种展示，不计算总和 | 在币种内查看金额与比率。 |
| 缓存贡献 | 作为估算展示 | 不并入账本利润。 |

## 可观测性

页面自身应记录安全的加载、查询失败、数据新鲜度和下钻行为证据。数据缺失是事实，应明确呈现并进入[路线图](../roadmap.md)，而非以估计值填补。

## 验收标准

- [ ] 页面没有主观健康标签、阈值配置、筛选或派生健康分桶。
- [ ] 当前可服务性、基础设施故障和无样本在页面上可区分。
- [ ] 首页不跨币种相加，缓存贡献标为估算。
- [ ] 请求 Gateway TTFT 与 attempt/Channel 上游 TTFT 分别标明口径；非流式不展示伪造的 TTFT，stale 版本不展示旧运行态事实。
- [ ] 五项评分、逐项计算过程、权重合计、最终得分和实际分流可区分；旧 trace 不伪造缺失的新评分字段。
- [x] Route runtime 展示当前模型的实际成本来源与倍率，线路渠道数增长不会增加首屏独立定价请求数量。
- [x] Route runtime 区分仅探测与普通候选，排除原因可读且未执行的毛利检查不会额外显示失败。
- [x] 模型详情缓存命中率只统计 cache read / input。
- [x] Gateway 日志页可创建有期限 DEBUG、展示逐实例应用状态，并在到期后自动恢复基线。
- [x] 日志查询由 Admin Server 受控访问 Loki，支持固定范围和筛选，浏览器不直连日志存储。
