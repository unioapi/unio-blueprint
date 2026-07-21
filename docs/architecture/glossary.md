---
title: 平台词汇表
description: UnioAPI 蓝图跨领域术语的权威定义。
status: active
owner: 产品团队
last_updated: 2026-07-21
related:
  - README.md
  - ../specifications/naming.md
---

# 平台词汇表

## 目的

为跨多个产品领域使用的术语提供唯一权威定义。只在单一领域使用的词汇应放在
该领域的词汇表中，并通过链接引用这里的共享概念。

## 术语

| 术语                      | 定义                                                                |
| ----------------------- | ----------------------------------------------------------------- |
| API                     | Application Programming Interface，应用程序接口；软件系统交换请求、响应或事件时遵循的契约。    |
| ADR                     | Architecture Decision Record，架构决策记录；保存重要选择的背景、备选方案、理由和影响。         |
| Blueprint（蓝图）           | 本仓库及其承载的权威知识系统。                                                   |
| Domain（领域）              | 围绕用户或业务能力形成的长期产品职责，不以当前源码归属划分。                                    |
| Global Decision（全局决策）   | 对多个产品领域产生约束的架构决策。                                                 |
| Domain Decision（领域决策）   | 影响范围完全位于单一产品领域内的架构决策。                                             |
| SDK                     | Software Development Kit，软件开发工具包；以特定语言的自然方式帮助开发者集成 UnioAPI 的官方类库。 |
| Specification（规范）       | 说明平台应如何设计或建设的跨产品强制性规则。                                            |
| UnioAPI                 | 本蓝图所描述的平台。                                                        |
| Website（官网）             | 面向公众的网站产品领域。                                                      |
| Documentation Site（文档站） | 面向开发者发布文档的产品领域。                                                   |
| Console（用户控制台）          | 面向客户的管理产品领域。                                                      |
| Admin（管理后台）             | 面向内部运营人员的管理产品领域。                                                  |
| Gateway（网关）             | 负责 API 流量与网关行为的产品领域。                                              |

## 新增术语

只有跨领域使用的术语才应加入这里。定义不得循环引用，不得包含未解释的缩写，
也不得依赖具体实现。

