---
title: 渠道模型发现与清单
description: Gateway 对上游渠道模型列表、成功快照、绑定匹配与逐模型验证的当前契约。
status: active
owner: 网关团队
last_updated: 2026-08-07
related:
  - ../glossary.md
  - provider-adaptation.md
  - model-capabilities-catalog.md
  - data-lifecycle.md
  - ../decisions/adr-0012-provider-channel-route-lifecycle.md
  - ../../admin/features/operations-management.md
  - ../../admin/pages/provider-channel-management.md
---

# 渠道模型发现与清单

## 摘要

Gateway 可以按 Channel 的 `(protocol, adapter_key)` 与当前 Provider API Root、凭据读取真实上游模型列表，
并把最近成功结果保存为运营快照。渠道模型清单把该快照与现有 `channel_models` 绑定、本地模型、外部参考
目录和逐模型验证事实对账，但发现本身不创建模型、不创建绑定，也不改变任何运行状态。

这项能力属于 Admin 上游供给管理，不改变客户可见的 Gateway `/v1/models`。客户接口继续按 Route 可见性
返回 Unio 模型；渠道发现读取的是 Provider 自己的模型列表入口。

## 协议与 Adapter 边界

模型列表能力与生成能力一样按 `(protocol, adapter_key)` 注册：

| Channel 协议与 Adapter | 上游列表调用 |
| --- | --- |
| OpenAI / `openai` | Bearer 认证的 OpenAI-compatible `/v1/models`。 |
| OpenAI / `deepseek` | Bearer 认证的 OpenAI-compatible `/v1/models`。 |
| Anthropic / `anthropic` | `x-api-key` 与固定 `anthropic-version` 的 Anthropic `/v1/models`，支持 `after_id` 分页。 |
| Anthropic / `deepseek` | Bearer 认证的 OpenAI-compatible `/v1/models`。 |

Provider API Root 可以带或不带末尾 `/v1`；标准操作路径只保留一个 `/v1`。模型列表读取禁止跟随重定向，
限制响应体、分页次数、模型数量和单个模型 ID 长度，并对结果去重排序。持久事实只保存模型 ID、可选 Owner、
可选上游创建时间和受控错误，不保存完整上游响应正文。

## 发现运行与成功快照

手工、新建流程和定时发现都创建独立运行记录。每次运行冻结 Channel 配置 revision、Provider 地址 revision
和 Provider 状态 revision：

- 成功且三个 revision 仍匹配时，结果成为该 Channel 的新成功快照；空列表作为成功快照保存并带警告。
- 配置在执行期间变化时，运行进入 `stale`，结果不能替换当前成功快照。
- 限流、超时、不可达和上游临时错误最多尝试三次，并采用有界退避；认证、权限、端点不支持和协议错误直接失败。
- 发现失败保留最近成功快照，不改变 `credential_valid`、Channel 状态、模型、绑定、价格或 Route。
- 周期发现由独立热更新配置控制，只为启用中的到期 Channel 创建任务；它不复用渠道凭据巡检的开关或状态写入。

同一 Channel 同时最多有一个活动发现任务。成功快照和运行历史按 Channel 隔离；保留数量由发现配置控制。

## 清单与匹配

清单是“最近成功快照中的上游模型”与“当前全部渠道绑定”的并集。绑定在本次快照中不存在时显示为
`not_seen`，但不能据此认定上游已停止支持，也不会自动停用或删除绑定。

未绑定的上游模型按以下优先级生成建议：

1. 上游模型 ID 与本地 `models.model_id` 精确匹配；
2. 参考目录 canonical ID 去掉 lab 前缀后匹配，且该目录条目已经采纳为唯一一个本地模型；
3. 单个未采纳参考目录候选；
4. 多个参考目录候选，需要运营人员选择；
5. 无匹配，使用手工选择本地模型。

匹配只产生动态建议，不保存“发现模型”实体，也不自动采纳参考目录。参考目录采纳与渠道绑定可在一个事务中
完成；批量绑定也在一个事务中完成。两条路径创建的绑定都固定为 `disabled`，重复提交同一模型和同一上游名
按幂等成功处理，不隐式覆盖已有的不同映射。

## 逐模型验证与启用证据

逐模型验证使用真实生成 Adapter 对指定 `(Channel, 本地模型, 上游模型)` 发起最小请求，并把探测事实交给
Provider 探测账务路径。验证不会创建客户请求或客户账单；可靠 usage 可以形成 Provider 探测成本，usage
不可靠时遵循现有成本风险规则。

验证批次冻结与发现相同的三个 revision。认证、限流、超时、不可达、协议和通用上游错误属于 Channel 级失败，
会停止本批次剩余项目；精确模型的 403 或 404 属于模型级失败，批次继续验证其他模型。配置变化使结果成为
`stale`，不能作为当前证据。

`models.status`、`channels.status`、`channel_models.status` 和验证结果是四个独立事实：

- 新建 Channel 固定为 `disabled`；
- 新建渠道模型绑定固定为 `disabled`；
- 验证成功不自动启用模型、Channel 或绑定；
- 把停用绑定改为启用，或替换绑定的上游模型名，必须提交当前 revision 下同一 Channel、本地模型和上游模型的
  成功验证项目；
- 停用绑定不需要验证证据，也不改变本地模型状态。

## Admin 契约

Admin 的 Channel 子资源提供发现创建、发现历史和单次结果、当前模型清单、验证创建和单次结果、原子批量
绑定，以及参考目录采纳并绑定。任务创建返回排队事实，由 worker 异步执行；调用方通过单次结果读取终态。

所有入口均受现有 Admin 认证保护。响应和错误不包含凭据、完整上游正文或非白名单上游元数据。

## 当前边界

- 发现证明“列表接口本次返回了什么”，不是逐模型可调用性的证明；启用仍依赖逐模型验证。
- 上游列表不支持或权限不足时，运营人员可继续手工绑定和验证。
- 本次未发现不能自动解释为模型下架，已有绑定保持原状态。
- 发现和验证当前都是单 worker 队列消费；同一 Channel 的同类活动任务由数据库唯一约束串行化。
- 运行记录冻结 revision，但 worker 进程在领取后异常退出时，当前没有自动回收长期停留在 `running` 的任务。

## 状态说明

本文于 2026-08-07 按当前 Gateway 代码、Schema 和测试接收为 `active`。
