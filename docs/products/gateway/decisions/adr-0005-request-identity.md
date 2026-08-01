---
title: "ADR-0005：请求关联与持久身份分层"
description: "X-Request-ID 与 trace_id 贯穿 HTTP；request、attempt 和上游请求使用各自独立标识。"
status: active
owner: 网关团队
last_updated: 2026-08-01
related:
  - ../overview.md
  - ../features/public-api-contracts.md
  - ../features/access-control.md
  - ../features/request-lifecycle.md
  - ../../../specifications/logging.md
  - adr-0003-billing-settlement.md
---

# ADR-0005：请求关联与持久身份分层

## 背景

一次客户 HTTP 请求、一个持久业务请求、一次真实上游尝试和上游自己的请求记录具有不同生命周期。
将它们都叫 `request_id` 会造成认证失败无法关联、fallback attempt 混淆，以及把客户可控值误用于账务或
数据库关系。因此 Gateway 固定使用四种 ID，不再使用 `correlation_id` 或 `client_request_id` 命名。

## 决策

| ID | 对象与生命周期 | 来源与出现边界 | 用途 |
| --- | --- | --- | --- |
| `trace_id` | 一次入口 HTTP 请求，从进入 Gateway 到响应结束。 | 完全等于本次采用并回传的 `X-Request-ID`；入口 middleware 即建立。 | 所有请求级日志的首要关联字段，包括尚未创建业务记录的认证和准入失败。 |
| `request_id` | 一条持久业务 Request。 | `request_records` 插入成功后使用该行的 `request_records.request_id`；格式为 `req_` 加 32 位十六进制。 | Admin 查询、请求审计和日志关联。 |
| `attempt_id` | 一次真实上游 Attempt。 | `request_attempts` 插入成功后使用其 bigint 主键；Permit denied 的候选没有 attempt。 | 区分同一业务请求的候选 fallback 或透明 fallback。 |
| `upstream_request_id` | 上游系统为某个 attempt 返回的可选请求标识。 | 从该 attempt 的上游响应头或协议元数据提取；未返回时省略。 | 与上游客服、日志和账单核对。 |

内部数据库关系、usage、账务和恢复仍通过 `request_records.id` bigint 主键关联；文本 `request_id` 不是这些
表的外键。request-admission 自己生成的 UUID、公开协议 response ID 和 Sticky ID 也不属于上述四种请求 ID。

## `X-Request-ID = trace_id`

Gateway 对 Router 处理的每个 HTTP 请求执行以下规则：

1. 客户提供 `X-Request-ID`，且长度不超过 128、只含 ASCII 字母、数字、`.`、`_`、`-`、`:` 时原样采用。
2. 缺失或不安全时生成 16 个随机字节的 32 位十六进制值；随机源失败时使用包含时间和进程内递增序列的
   `fallback-...` 安全值。
3. 采用值同时写入请求 context、日志 `data.trace_id` 和响应 `X-Request-ID`。

因此客户发送 `X-Request-ID: ABC` 时，Gateway 日志与响应都使用 `ABC`，不会另返回一个不同 ID。客户负责
其自带值的唯一性；Gateway 不建立唯一约束，也不因重复 `trace_id` 合并请求。客户可以提交 `req_...` 形状，
因此不能凭前缀判断响应头中的值是否是持久业务 ID。

## 传播规则

- 所有请求级日志必须携带 `trace_id`。
- `request_records` 插入成功后的日志同时携带 `trace_id + request_id`；插入失败不得留下孤立 `request_id`。
- `request_attempts` 插入成功后的 attempt 日志增加 `attempt_id`。
- 取得上游请求 ID 后，该 attempt 的后续时序、完成和失败日志增加 `upstream_request_id`。
- 一个 `trace_id` 在正常生成请求中对应一个 `request_id`；一个 `request_id` 可以对应多个 `attempt_id`；
  每个 attempt 最多有一个 `upstream_request_id`。
- `upstream_request_id` 不参与内部关联、Sticky、路由、幂等或计费，不覆盖客户响应的 `X-Request-ID`。
- 上游请求 ID 不保证跨 Provider 全局唯一；反查至少结合 Provider 和上游请求 ID，并以 `attempt_id` 为
  Gateway 内部权威定位。

一次 fallback 请求的关系为：

```text
trace_id=ABC
└── request_id=req_123
    ├── attempt_id=101, upstream_request_id=provider_req_A
    └── attempt_id=102, upstream_request_id=provider_req_B
```

## 持久请求创建边界

当前会创建 `request_records` 的公开操作是 Chat Completions、Responses 主操作、Responses compact 和
Messages。它们只有在通过认证、request admission 与协议前置校验并进入 service 后才创建持久记录。
`/v1/models`、Responses input-tokens、当前 501 状态操作，以及业务记录创建前的认证、准入、decode 或
validation 拒绝只有 `trace_id`，没有 `request_id`。

业务 `request_id` 不通过 `X-Request-ID` 或常规客户响应返回。公开协议 response ID、Anthropic 错误体中的
`request_id` 和上游 request ID 都不能解释为 `request_records.request_id`。

## 账务与幂等

授权和结算幂等键由 `request_records.id` 形成，当前分别为 `chat:authorize:<id>` 和 `chat:settle:<id>`。
客户可控的 `trace_id`、文本 `request_id` 和 `upstream_request_id` 都不参与账务幂等。attempt、usage、
价格/成本快照、ledger reservation/entry、settlement recovery job 和 routing trace 通过数据库主键关系关联。

## 影响

- 即使请求在认证或准入阶段失败，也能只用响应 `X-Request-ID` 在日志中定位完整过程。
- 进入持久生命周期后，可由同一日志行取得 `trace_id + request_id`，再分别查询文件/Loki 和数据库。
- fallback 不会把多个上游 transport 压成一个 attempt；上游核对不再污染 Gateway 内部身份。
- `trace_id` 不持久化到 `request_records`。日志过期后，不能仅凭客户 `X-Request-ID` 从数据库反查业务请求。

## 来源谱系

| 原 DEC | 原始日期 | 原状态 | 当前迁移处理 |
| --- | --- | --- | --- |
| DEC-004 | 未记录 | accepted | 保留 HTTP 与持久业务身份分离，并把日志字段统一为 `trace_id`，补全 attempt 与上游请求 ID。 |

## 参考资料

- [日志规范](../../../specifications/logging.md)
- [Gateway 公开 API 契约](../features/public-api-contracts.md)
- [网关访问控制](../features/access-control.md)
- [Gateway 请求生命周期](../features/request-lifecycle.md)
- [预付账务与可审计结算](adr-0003-billing-settlement.md)
