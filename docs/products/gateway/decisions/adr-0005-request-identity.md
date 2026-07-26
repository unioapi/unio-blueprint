---
title: "ADR-0005：HTTP 关联标识与持久请求标识分离"
description: "X-Request-ID 承担 HTTP 关联；持久请求、账务和恢复使用独立的服务端标识与数据库主键。"
status: active
owner: 网关团队
last_updated: 2026-07-26
related:
  - ../overview.md
  - ../features/public-api-contracts.md
  - ../features/access-control.md
  - ../features/request-lifecycle.md
  - adr-0003-billing-settlement.md
---

# ADR-0005：HTTP 关联标识与持久请求标识分离

## 背景

Gateway 同时处理客户可传入的 HTTP 关联标识，以及由服务端创建的持久业务请求事实。前者可以缺失、
重复或由客户选择，不能承担账务、恢复和数据库关系键的职责。当前代码还存在 request-admission token、
上游 request ID 和协议 response ID；这些标识也不等同于持久业务请求标识。

## 当前决策

Gateway 将以下两类标识分开：

- HTTP correlation ID 用于一次 HTTP 处理过程的响应头、context 和日志关联；客户可控，不持久化到
  `request_records`，也不作为账务幂等键。
- 持久业务请求 ID 由服务端为进入持久请求生命周期的调用另行生成，写入
  `request_records.request_id`，用于 Admin 查询、审计展示和日志关联。
- 数据库关系、账务、用量和恢复以 `request_records.id` 的 bigint 主键关联；唯一文本
  `request_records.request_id` 不是这些表的外键。

两类标识不能互相替代。客户重复使用同一个 correlation ID 不会合并持久请求，也不会形成请求或账务幂等。

## HTTP correlation ID

公共 Gateway API Router 的全局 RequestID middleware 覆盖健康检查、受保护 API、未匹配路由和已挂载的指标入口：

- 读取请求 `X-Request-ID`；长度不超过 128 且只包含 ASCII 字母、数字、`.`、`_`、`-`、`:` 时原样保留。
- 缺失或不安全时生成 16 个随机字节的 32 位十六进制值；随机源失败时当前回退为固定字符串 `unknown`，
  因而该极端分支不保证唯一。
- 选定值写入响应 `X-Request-ID`、请求 context 和结构化日志字段集合，部分 Anthropic admission 错误体也会
  把它作为 `request_id` 返回。允许字符规则只限制头部与日志注入，不判断客户值是否包含业务敏感信息。
- 该值没有唯一约束，也没有数据库列保存 correlation-to-request 映射；跨两类标识排障依赖日志仍然可用。

常规 access log 使用 `correlation_id` 字段。进入持久生命周期并完成业务 ID 生成后，同一条 access log
还可以包含 `request_id`。panic recovery 的专用日志当前把 correlation ID 写在名为 `request_id` 的字段中，
与常规 access log 的字段语义不一致；不能据此把 panic 日志中的该字段认作持久业务 ID。

## 持久业务请求 ID

持久请求 ID 由服务端随机生成，格式为 `req_` 加 32 位十六进制字符。随机源失败时创建直接报错，
不会使用 HTTP correlation ID 回退。Schema 对 `request_records.request_id` 建立唯一约束。

当前会创建持久请求记录的公开操作是：

- `POST /v1/chat/completions`；
- `POST /v1/responses`；
- `POST /v1/responses/compact`，其请求记录当前仍使用 `responses` endpoint 分类；
- `POST /v1/messages`。

这些操作也只有在通过认证、request admission、JSON decode/validation 等前置步骤并进入 service 后才创建记录。
路由、授权、候选执行或结算等后续失败仍可在已经创建的持久请求记录上收口。

当前不会创建 `request_records` 的入口包括 `/v1/models`、`/v1/responses/input_tokens`、Responses 的
501 状态操作、健康/就绪/指标入口，以及发生在业务记录创建前的认证、admission、decode 或 validation 拒绝。
这些请求仍有 HTTP correlation ID。

业务 ID 在数据库插入前先写入 access-log 字段集合；如果插入失败，access log 可能出现一个没有对应新
`request_records` 行的 `req_` ID。客户也可以提交一个合法的 `req_...` correlation ID，因此不能只凭前缀
判断响应头中的 ID 类型。业务 ID 当前不通过 `X-Request-ID` 或常规客户成功/错误响应返回；
公开协议中的 response ID、Anthropic 错误体 `request_id` 和上游 request ID 都不能据此解释为该业务 ID。

## 数据与账务关联

`request_records.id` 是数据库主键。request attempts、usage records、价格/成本快照、ledger reservations、
ledger entries、settlement recovery jobs 和 routing traces 等事实通过该数值 ID 关联。

授权和结算幂等键当前分别由内部 `request_record_id` 形成 `chat:authorize:<id>` 和
`chat:settle:<id>`；它们不读取客户 `X-Request-ID`。`request_records.request_id` 则提供唯一文本查询和
Admin 展示入口，但不改变数据库关系键。

request-admission 使用另行生成的 UUID 管理 Redis 入口资源；attempt 可保存上游返回的 request ID；
request record 和 attempt 还分别保存协议 response ID 与上游 response ID。这些标识各自承担不同职责，
当前没有统一成同一个 ID。

## 当前行为与边界

- 客户可稳定取得并复用 HTTP correlation ID，但不能用它查询或控制账务幂等。
- 持久业务 ID 能关联数据库审计事实，但常规客户 API 不返回该 ID。
- 两类标识只有日志级关联，没有持久 correlation-to-request 映射；日志缺失或过期后不能仅凭 correlation ID
  从数据库反查业务请求。
- correlation 随机生成失败时会回退为可重复的 `unknown`；panic 专用日志还存在字段命名不一致。
- 客户 correlation ID 可以使用 `req_` 形状；前缀只定义服务端业务 ID 的生成格式，不是响应头值的可信证明。
- Responses compact 会创建和结算持久请求，但当前与主 Responses 共用 `responses` ingress endpoint 分类。

## 代码与测试证据

当前代码、Schema 和测试覆盖 Router middleware、请求生命周期创建路径、结构化 access log、
request ID 生成、`request_records` 唯一约束、相关外键和账务幂等键。

## 来源谱系

| 原 DEC | 原始日期 | 原状态 | 当前迁移处理 |
| --- | --- | --- | --- |
| DEC-004 | 未记录 | accepted | 当前有效并按代码补全：HTTP correlation ID 与持久业务请求 ID 分离；无后续来源 DEC 取代或修订。 |

## 取代关系

- 取代：无 Blueprint ADR。
- 被取代：无。

## 参考资料

- [Gateway 公开 API 契约](../features/public-api-contracts.md)
- [网关访问控制](../features/access-control.md)
- [Gateway 请求生命周期](../features/request-lifecycle.md)
- [预付账务与可审计结算](adr-0003-billing-settlement.md)
