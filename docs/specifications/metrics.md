---
title: 指标规范
description: 低基数、可告警且与日志互补的服务运行指标规范。
status: draft
owner: 可靠性团队
last_updated: 2026-08-04
related:
  - README.md
  - logging.md
  - ../architecture/quality.md
  - ../products/gateway/quality.md
---

# 指标规范

## 与日志的分工

指标和[日志](logging.md)回答不同层次的问题，互不替代。日志回答「这一条请求发生了什么」，按
`trace_id` 可以还原单次调用的完整过程；指标回答「一段时间内某个维度上发生了多少、多快、是否在恶化」，
用于趋势判断与告警触发。

这条分工同时划定了指标不该承担的职责：按用户、按 API Key、按单条请求的账务事实由业务表回答，不进指标。

## 命名

指标名使用 `unio_` 前缀。平台级公共维度直接跟域名，如 `unio_http_requests_total`、
`unio_ratelimit_decisions_total`；服务自有维度带服务名，Gateway 当前使用 `unio_gateway_` 前缀。

计数器以 `_total` 结尾，直方图以基本单位结尾（当前为 `_seconds`）。同一含义在不同服务间必须复用同名
指标与同名 label，不得另造。

## 标签基数

label 只允许取值有界、且由管理端控制的业务维度。Gateway 当前使用的 label 集合为 `method`、
`route`、`status`、`outcome`、`model`、`provider`、`channel`、`error_category`、`event`、`decision`。

以下值任何情况下都不得作为 label：用户标识、API Key、request_id、trace_id、完整 URL、prompt 或响应
正文、上游原始错误文本。HTTP 维度使用路由模板而非原始请求路径，未匹配路由统一记为 `unmatched`。

即便是有界维度，实体数量也会随业务增长。因此按 Provider、Channel、Route、Model、breaker 与 revision
fence 等标识组合构成的 series，每个指标族最多接纳 1024 组，超出部分归并到 `__overflow__`，避免 series
随历史实体持续累积。该上限同时记录在 [Gateway 质量属性](../products/gateway/quality.md)。

## 暴露

服务通过 HTTP `GET /metrics` 以 Prometheus 文本格式暴露指标。该端点与 `/healthz`、`/readyz` 一同豁免
业务鉴权，不接受也不校验客户 API Key，因此**必须由部署侧限制为内网可达**，不得随公开 API 一起暴露到
公网。

成功的 `/metrics` 抓取只记 DEBUG 日志，避免轮询在生产制造 INFO 噪声。

## Gateway 当前覆盖面

Gateway 当前注册 60 个指标，其中 38 个计数器、13 个 gauge、9 个直方图，覆盖以下域：

| 域 | 当前回答的问题 |
| --- | --- |
| HTTP 入口 | 按方法、路由模板、状态码的请求数与耗时分布 |
| 请求与结算 | chat 请求终态分布、结算结果、部分结算、零价放行 |
| 上游调用 | 上游请求数与失败归因、总耗时、TTFT、流式事件数、Provider 与 Channel 维度失败 |
| 路由 | 候选选中与跳过原因、五项评分权重与负载偏斜、池大小与候选数、容量短等耗时、毛利硬摘除、fallback、trace 写入与失败 |
| 熔断 | 两层 breaker 当前状态与状态转换、跳过原因、被忽略的归因结果、permit 活跃数与操作结果、breaker store 就绪性与操作延迟 |
| 准入与限流 | 请求级准入活跃数与操作结果、限流决策分布（含 fail-closed） |
| 运行控制 | control 操作结果与待决时长、revision 不匹配、代际围栏、runtime state 完整性与恢复 |
| 能力与凭据 | 能力校验与缺失、凭据轮换验证结果 |

按域而非按单个指标名维护本表：新增指标若落在既有域内不需要更新此处，新增域时才补充。

## 采集与告警

指标本身只是在服务进程内累积，必须被采集后才具备历史与告警能力。完整链路为
`服务 /metrics -> Prometheus -> 告警投递`。

Prometheus 负责抓取与规则评估；告警的去重、分组与投递由独立的告警投递组件负责，Prometheus 自身不发送
通知。规则文件与投递配置属于部署产物，不在本规范内固定。

## 验证

实现必须验证：指标名与 label 命名符合本规范；禁止的高基数与敏感值不出现在任何 label 上；超过 series
上限时归并到 `__overflow__` 而不是持续新增；`/metrics` 可被解析为合法 Prometheus 文本格式；同一埋点
不因暴露端点被轮询而产生生产 INFO 日志。

## 当前状态与待完善

以下为**尚未实现**的部分，按本仓库规则与已实现事实分开记录，不得据此推断当前行为：

- **采集未接入**。Gateway 与 Admin 的 `/metrics` 端点已在服务并持续累积真实数据，但当前部署产物中的
  Prometheus 未配置任何抓取目标，因此不存在指标历史，也无法基于指标评估告警规则。现阶段的可观测能力
  完全由日志链路承担。
- **告警投递缺失**。当前部署未包含告警投递组件，Prometheus 也未配置投递目标。既有规则文件即使命中也
  无法送达任何接收方。
- **展示形态未定**。是否引入独立看板、或由 Admin 运维页查询 Prometheus 提供健康面板，尚未决定。在决定
  之前，指标只能通过 Prometheus 自带界面查看。
- **与 Admin 运维视图的边界未厘清**。Admin 当前的成功率、延迟分位与吞吐视图由业务表实时聚合得出，与
  指标覆盖面存在重叠。哪些时序视图应迁移到指标、哪些必须保留在业务表（尤其涉及金额与按用户维度的
  事实），需要单独决策。

上述四项完成前，本规范中「采集与告警」一节描述的是目标链路而非当前部署事实。
