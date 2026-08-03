---
title: UnioAPI 平台路线图
description: UnioAPI 跨领域目标、推进顺序与决策门槛。
status: draft
owner: 产品团队
last_updated: 2026-08-03
related:
  - README.md
  - ../architecture/strategy.md
  - ../architecture/email-delivery-center.md
---

# UnioAPI 平台路线图

## 规划周期

添加路线图事项前，由产品负责人确定规划周期。

## 当前

该阶段暂未批准跨平台目标。

## 下一步

该阶段暂未批准跨平台目标。

## 未来

| 结果 | 预期价值 | 负责人 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| 建成服务商无关的[邮件投递中心](../architecture/email-delivery-center.md) | 使用自有发件域名可靠发送身份、账务和运维邮件，并能在 Admin 配置、审计和排查 | 平台团队、管理后台团队 | SMTP 服务商与域名验证、Worker 投递运行面、数据保留决策 | 已确认方向，待实施 |

## 依赖与决策门槛

- 邮件投递中心进入实施前，需要确定首个生产 SMTP 服务商、投递记录保留期限和分类重试参数；最终送达、
  退信与投诉不属于通用 SMTP 首个版本承诺。
- 其他跨领域事项必须链接到对应提案、架构决策记录或风险后才能进入路线图。

## 复审节奏

在状态调整为 `active` 前，先确定负责人、复审周期以及移动或移除事项的规则。
