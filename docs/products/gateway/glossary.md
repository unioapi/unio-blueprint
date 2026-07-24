---
title: Gateway（网关）词汇表
description: 网关领域专用术语的占位文档。
status: active
owner: 网关团队
last_updated: 2026-07-24
related:
  - README.md
  - ../../architecture/glossary.md
  - decisions/adr-0001-domain-terminology.md
---

# Gateway（网关）词汇表

## 领域术语

| 术语                   | 定义                                                                                                               |
| -------------------- | ---------------------------------------------------------------------------------------------------------------- |
| 协议 Protocol          | API 格式族，决定请求/响应的 schema 家族。当前有 `openai` 与 `anthropic` 两种。一个协议涵盖多个端点。                                             |
| 端点 Endpoint          | 网关对外暴露的一个 API 操作/路径，如 `/v1/chat/completions`、`/v1/responses`（OpenAI 协议）、`/v1/messages`（Anthropic 协议）。每个端点归属唯一协议。 |
| 上游源站 Provider Origin | 一个上游供应商的根地址（`base_url`/host，如 `https://open.codex521.cc`）。它是熔断与流式首字延迟统计的**单故障域**；多条渠道可共享同一源站。                    |
| 渠道 Channel           | 一次上游调用的凭据、定价与适配单元。声明所走协议、挂在某个上游源站上；支持哪些端点由 adapter 能力决定。                                                         |
| 候选 Candidate         | 路由时「渠道 × 该渠道支持的上游模型」的一个可尝试项。                                                                                     |

## 维护规则

这里只定义网关独有术语。共享术语属于[平台词汇表](../../architecture/glossary.md)，
应通过链接引用，不得重复定义。

