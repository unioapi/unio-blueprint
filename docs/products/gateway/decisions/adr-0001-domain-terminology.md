---
title: "ADR-0001：统一领域术语（协议 / 端点 / 上游源站）"
description: "厘清网关三个被混用的核心概念：协议、端点、上游源站。"
status: active
owner: 网关团队
last_updated: 2026-07-24
related:
  - README.md
  - ../glossary.md
  - ../features/routing-load-balancing.md
  - ../../../templates/adr.md
---

# ADR-0001：统一领域术语（协议 / 端点 / 上游源站）

## 背景

网关有三个本质不同的概念，长期被「协议」「端点」两个词混用，导致代码、API、文档
互相打架：

- **API 格式族**：OpenAI 式 / Anthropic 式的请求-响应 schema。
- **API 路径/操作**：`/v1/chat/completions`、`/v1/responses`、`/v1/messages` 等对外接口。
- **上游根地址**：供应商的 `base_url`/host（如 `https://open.codex521.cc`），也是熔断的单故障域。

冲突点：官方把第二类（API 路径）称为 **endpoint（端点）**，但本系统把「端点」用在了第三类
（上游根地址，代码里叫 `ProviderEndpoint`），而第二类在代码里叫 `Operation`；「协议」则从
格式族下探到了子端点层（例如把 `/responses/compact` 称作「子集协议」）。

## 决策驱动因素

- 与行业/官方术语对齐，降低沟通与上手成本。
- 一个词一个含义，消除代码、DB、API、前端、文档之间的歧义。
- 术语先于实现固化，作为后续所有设计与代码的统一语言（Blueprint 单一事实来源规则）。

## 备选方案

### 方案：保留现状（端点=上游、协议=格式族+子端点）

**优点**

- 无迁移成本。

**缺点**

- 与官方术语相反（端点被安在上游地址上），持续误导；「协议」含义漂移。

### 方案：端点归还给 API 路径，上游改名（选中）

把「端点」还给官方含义（API 路径），上游根地址另起名，「协议」收紧为格式族。

**优点**

- 与官方一致；三概念各有唯一名字；中文 UI 自然变正确。

**缺点**

- 一次性大范围改名（DB、Go、API、前端、指标）。

## 决策

采用以下唯一术语，全平台（网关代码、Admin API、前端、文档）一致使用：

- **协议 Protocol** = API 格式族，取值 `openai` / `anthropic`；一个协议涵盖多个端点。仅用于格式族层，不下探到端点/子端点。
- **端点 Endpoint** = 网关对外的一个 API 操作/路径（`/v1/chat/completions`、`/v1/responses`、`/v1/messages` 等）。代码中原 `Operation` 概念改称端点。
- **上游源站 Provider Origin** = 上游供应商根地址（`base_url`/host），同时是熔断与流式首字延迟统计的单故障域。代码中原 `ProviderEndpoint` 概念改称上游源站。

关系：**协议 1 — N 端点**；渠道走某协议、挂在某上游源站上，支持哪些端点由 adapter 能力决定。
权威定义见[网关词汇表](../glossary.md)。

## 影响

### 正面影响

- 术语与官方对齐、彼此不再冲突；文档与代码可长期一致引用。
- 中文 UI 歧义消除：「端点」= API 路径，「上游源站」= 上游地址。

### 负面影响

- 需要一次跨 DB / Go / Admin API / 前端 / 指标的大范围改名。

### 中性影响或后续工作

- 字符串值（`openai`/`anthropic`/`chat_completions`/`responses`/`messages`/`responses_compact`）与字段 `base_url` 保持不变。
- 迁移按「先上游源站、后端点」顺序执行，避免「endpoint」一词在过渡期冲突。

## 风险与缓解措施

| 风险 | 缓解措施 | 负责人 |
| --- | --- | --- |
| 改名触及资金/结算路径（request_attempts/request_records 列） | 连同 settlement/recovery 一起改并跑回归 | 网关团队 |
| breakerstore Lua 硬编码字段与 Go 读取端不一致 | 同步改 + 真实 Redis 测试 | 网关团队 |
| 「端点」新旧含义在过渡期混淆 | 先完成上游源站改名腾空「endpoint」，再赋予端点 | 网关团队 |

## 落地与验证

- 本地开发库可重建、Redis 可 FLUSH、无外部 API 客户端，采用直接改迁移 + 重建库、无兼容层。
- 验收：后端 `go test -race`、空库重建、真实 Redis、blackbox；前端 lint/build/vitest/Playwright；重启后 `/readyz` 与真实 smoke。

## 取代关系

- 取代：无
- 被取代：无

## 参考资料

- [路由负载均衡（balanced 权重调度）](../features/routing-load-balancing.md)
- [网关词汇表](../glossary.md)
