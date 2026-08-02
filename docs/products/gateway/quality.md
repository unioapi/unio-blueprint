---
title: Gateway（网关）质量要求
description: Gateway 当前可验证的资源护栏与尚待批准的领域质量目标。
status: draft
owner: 网关团队
last_updated: 2026-08-02
related:
  - README.md
  - ../../architecture/quality.md
---

# Gateway（网关）质量要求

## 当前状态

当前尚未批准 Gateway 专用 SLO、容量基线或负责人。以下资源护栏是代码和测试已经证明的当前行为，
不等同于经过批准的质量目标：

- Gateway 与 Admin JSON 请求体缺省上限分别为 32 MiB 和 4 MiB，非流式上游响应体缺省上限为 8 MiB；
  上游默认连接池和下游 JSON/SSE 写入窗口均有明确边界。具体行为见[公开 API 契约](features/public-api-contracts.md)、
  [Provider 适配](features/provider-adaptation.md)和[请求生命周期](features/request-lifecycle.md)。
- 连续 401 的进程内 Channel 状态最多保留 4096 项，异步凭据 CAS 最多 32 个并发且按 Channel 去重。
- Provider、Channel、Route、Model、breaker 和 revision fence 等业务标识组合按指标族最多接纳 1024 组；
  超出部分归并到 `__overflow__`，避免 Prometheus series 随历史实体持续增长。
- 不阻塞客户 SSE 的 live audit 写入最多 256 个并发；容量已满时丢弃额外 best-effort live observation，
  attempt 终态时序与首字事实仍由同步收口路径持久化。

历史事实当前没有自动保留期清理，见[数据生命周期](features/data-lifecycle.md)。

## 记录格式

Gateway 专用质量目标引用对应的[平台质量属性](../../architecture/quality.md)。
