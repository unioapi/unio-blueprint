---
title: Gateway（网关）概览
description: 网关当前公开入口、身份、线路、供给与账务边界。
status: active
owner: 网关团队
last_updated: 2026-07-28
related:
  - README.md
  - glossary.md
  - features/access-control.md
  - features/billing-settlement.md
  - features/model-capabilities-catalog.md
  - decisions/adr-0001-domain-terminology.md
  - decisions/adr-0002-route-product-pricing.md
  - decisions/adr-0003-billing-settlement.md
  - decisions/adr-0005-request-identity.md
---

# Gateway（网关）概览

## 当前职责

Gateway 为客户程序提供 OpenAI Chat Completions、OpenAI Responses、Responses Compact 和 Anthropic
Messages 公开入口。请求通过 API Key 解析用户账户与 Route，在该 Route 的显式 Channel 池内完成候选选择、
Provider 适配、上游调用、用量记录和结算。

## 当前领域关系

| 概念 | 当前关系 | 公开可见性 |
| --- | --- | --- |
| User Account | 持有余额和 API Key | 客户身份与余额主体 |
| API Key | 直接归属 User Account，并显式绑定一条 Route | 客户凭据 |
| Route | 保存客户定价倍率、模式和显式 Channel 池 | 客户产品边界 |
| Model | 保存客户请求标识、基准价格和能力声明 | 通过模型目录公开 |
| Provider | 保存唯一 `origin`、独立地址/状态 revision、公共 breaker 故障域，并归属 Channel | 不公开 |
| Channel | 归属一个 Provider，保存上游凭据、协议、Adapter、模型映射、成本和运行控制 revision | 不公开 |
| Request | 生成或压缩调用进入持久生命周期后的业务记录 | 使用服务端生成的业务 ID |
| Attempt | 对一个候选发起的真实上游 transport 记录 | 不公开内部供给结构 |

当前 Schema 和认证路径中没有 Project 或独立 Billing Account 身份层。领域术语见
[网关词汇表](glossary.md)和[ADR-0001](decisions/adr-0001-domain-terminology.md)。

## 请求边界

1. API Key 认证解析 User Account 与显式绑定 Route。
2. Route 限定模型可见范围、客户定价和候选 Channel 池。
3. 候选按 ingress protocol、Adapter operation capability、模型映射、凭据、状态、价格和运行态过滤。
4. `fixed` Route 只接受恰好一个 Channel 的候选池；`balanced` Route 按经济、健康、容量和 Priority
   客观分在池内生成确定性 fallback 顺序。
5. 每个真实 transport 前取得独立 `AttemptPermit`，并在调用后按实际结果记录 attempt、usage、运行态反馈和
   账务事实。
6. fallback 不改变本次请求锁定的 Route 或客户价格。

## 当前能力

- API Key 认证、Route 绑定和服务端业务请求 ID。
- OpenAI 与 Anthropic 两个 ingress 协议族及同协议 Provider 适配。
- Route 内候选过滤、fixed/balanced 排序、sticky、fallback、请求准入和候选准入。
- 预付余额授权、token 计费、capture、overage debit、write-off、partial settlement 与 recovery job。
- Provider、Channel、Model、价格、成本和运行 control 的管理服务。
- 模型能力字典、模型声明、外部目录采纳/刷新 service 和 Adapter 画像物化。
- 请求、attempt、usage、价格、成本、账本、routing trace 和审计记录。

## 当前边界

- 公开响应不包含 Provider、Channel、上游地址、上游凭据、渠道成本或内部毛利。
- 路由不跨越 API Key 绑定的 Route，也不接受客户直接选择 Channel。
- OpenAI ingress 只使用 OpenAI protocol Channel；Anthropic ingress 只使用 Anthropic protocol Channel。
- 模型能力声明不参与真实候选准入；运行时是否可执行由 Adapter registry 的 operation capability 决定。
- Console、Admin 前端、SDK 与文档站属于其他产品或实现范围。
- Gateway 代码当前由三个常驻进程和一个 maintenance CLI 复用同一 Go module；具体见
  [ADR-0011](decisions/adr-0011-runtime-deployment-boundaries.md)。

## 参考资料

- [访问控制](features/access-control.md)
- [公开 API 契约](features/public-api-contracts.md)
- [请求生命周期](features/request-lifecycle.md)
- [账务与结算](features/billing-settlement.md)
- [路由负载均衡](features/routing-load-balancing.md)
