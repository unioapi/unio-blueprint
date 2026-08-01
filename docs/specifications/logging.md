---
title: 日志规范
description: 结构化、可关联且保护隐私的诊断与审计事件规范。
status: active
owner: 可靠性团队
last_updated: 2026-08-01
related:
  - README.md
  - api-style.md
  - ../architecture/quality.md
  - ../products/gateway/decisions/adr-0005-request-identity.md
  - ../products/admin/features/operations-observability.md
---

# 日志规范

## 结构化事件契约

服务日志必须把稳定分类与动态事实分开。Gateway 当前采用以下单行 JSONL 信封；其他服务接入该规范时
应复用字段语义，不能为同一含义另造字段：

| 字段 | 规则 |
| --- | --- |
| `timestamp` | RFC3339 时间，包含毫秒和时区。 |
| `level` | 只使用 `debug`、`info`、`warning`、`error`。 |
| `server` | 产生日志的服务；Gateway 固定为 `gateway`。 |
| `environment` | 服务自身的 `development`、`test` 或 `production` 运行环境，不由采集器覆盖。 |
| `instance` | 产生日志的实例 ID，用于区分同一服务的多个进程。 |
| `type` | 稳定一级业务域。Gateway 当前使用 `system`、`http`、`routing`、`admission`、`runtime`、`upstream`、`billing`。 |
| `event` | `type` 下稳定的对象或子模块，不表达成功或失败结果。 |
| `message` | 固定、简短的英文动作描述；不得拼接 ID、耗时、状态码或错误文本。 |
| `data` | JSON 对象，承载本条事件的动态事实；无动态事实时为 `{}`。 |

同一个埋点必须同时服务文件和开发控制台，不能维护两套事件。文件保存完整 JSON 信封；开发控制台把
同一条事件渲染为带 caller 的单行可读格式，仍保留完整 `data`。

## 等级职责

| 等级 | 当前职责 |
| --- | --- |
| `debug` | 完整诊断过程，包括认证成功、候选评分与扫描、Sticky、Permit、attempt 时序、首字、交付和结算细节。允许字段冗余，但禁止记录正文和凭据。 |
| `info` | 正常生产运行的代表性事实。每个完成的 Gateway 业务请求只保留一条 `http/request/request completed` 摘要；启动、依赖连接、设置变更等低频系统事实可另记 INFO。 |
| `warning` | 可归因的上游失败、fallback、容量耗尽、客户可恢复拒绝、部分结算或其他需要关注的降级。 |
| `error` | Gateway 内部失败、持久化或运行态基础设施失败、Permit/账务终态不确定及 panic。普通上游 5xx 不因状态码本身升级为 ERROR。 |

WARNING 和 ERROR 在 INFO 与临时 DEBUG 两种模式下都完整输出，不抽样，也不能被动态设置关闭。成功的
`/healthz`、`/readyz`、`/metrics` 和内部探针只记 DEBUG，避免轮询制造生产 INFO 噪声。

## 请求关联

Gateway 请求日志使用四种互不替代的 ID：

- `trace_id` 等于本次 HTTP 请求采用并回传的 `X-Request-ID`，从入口到响应结束贯穿全部请求级日志。
- `request_id` 只表示成功创建的 `request_records.request_id`；创建持久记录前不得出现。
- `attempt_id` 只表示成功创建的 `request_attempts.id`；一个 `request_id` 可以对应多个 `attempt_id`。
- `upstream_request_id` 是上游为单次 attempt 返回的可选标识，只用于与上游核对。

认证或准入在持久记录创建前失败时，日志仍能由 `trace_id` 完整关联。持久记录创建后同时携带
`trace_id + request_id`；attempt 创建后再增加 `attempt_id`；上游返回请求标识后才增加
`upstream_request_id`。完整身份决策见
[ADR-0005](../products/gateway/decisions/adr-0005-request-identity.md)。

## 正常摘要与调试事实

Gateway 的 `request completed` 是正常模式下唯一的请求级 INFO/WARNING/ERROR 摘要。已知时包含身份、模型、
Route、最终 Provider/Channel、HTTP 状态、总耗时、双 TTFT、attempt/fallback 数、容量等待、Sticky 动作、
交付与结算状态、usage、收费金额和稳定错误码。Client IP、User-Agent、完整候选过程和逐事件分类不进入
该摘要。

临时 DEBUG 打开后，同一个 `trace_id` 可以串联入口、认证、准入、候选计划、Sticky、Permit、每次 attempt、
上游响应头、首个有效生成 Token、交付和结算。首字前协议事件可以逐事件记录事件类型、分类和字节数，
但不得保存生成负载；首字后只保存 attempt 级事件数和字节数，不逐 Token 写日志。

## 敏感数据

任何等级和 sink 都不得记录：

- API Key 明文或 hash、Provider credential、Authorization、密码和会话令牌；
- Prompt、用户请求正文、生成正文和完整响应；
- 客户原始 Sticky 会话键；只允许不可逆会话 hash 和由该 hash 构成的 Redis key；
- 上游原始错误正文、URL query、URL userinfo 或未经脱敏的 Provider 路径。

`error_message` 只保存稳定安全文案。可变列表必须设置字段数量和单条记录上限；Gateway 单条 JSONL 的硬
上限为 1 MiB，超限时只保留截断标记和可安全关联的 ID。

## 文件、采集与保留

Gateway 权威文件为 `logs/gateway.jsonl`。开发基线为 DEBUG 并启用完整控制台；生产基线为 INFO 且关闭
正常控制台输出，只有文件 sink 本身失效时才允许向 stderr 报告日志系统故障。生产配置禁止永久 DEBUG；
临时 DEBUG 只能通过 Admin 创建 5、15、30 或 60 分钟会话，并在本地计时到期后自动恢复 INFO。

活跃文件达到上限后 rename 轮转，至少保留 30 秒供持续运行的 Alloy 排空旧 inode，再原子 gzip；活跃文件
不压缩。默认最多保留 20 个历史文件和 14 天，任一条件先满足即清理。Alloy 长时间离线跨过排空窗口时，
gzip 仍保存本地事实，但 Loki 不承诺自动补齐，需人工重放。

当前采集链路为 `Gateway -> JSONL -> Grafana Alloy -> Loki`。Loki stream labels 只允许
`environment`、`server`、`instance`、`level`、`type`、`event`；`trace_id`、`request_id`、`attempt_id`、
`upstream_request_id` 以及 User、API Key、Provider、Channel ID 都保留在 JSON 行内，禁止成为 label。
Loki 和本地文件当前均保留 14 天。

## 验证

实现必须验证 JSONL 逐行可解析、请求关联传播、四级职责、动态 DEBUG 到期、文件轮转和压缩、采集时间戳、
低基数 labels、敏感字段缺失，以及 INFO 摘要与持久请求/attempt/usage/账务事实一致。
