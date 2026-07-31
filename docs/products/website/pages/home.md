---
title: Home（首页）
description: 面向开发者和 AI 应用团队介绍 UnioAPI，并引导获取 API Key 或查看接入文档的首页草稿。
status: draft
owner: 官网团队
last_updated: 2026-07-31
related:
  - README.md
  - ../overview.md
  - ../quality.md
  - ../../gateway/glossary.md
  - ../../gateway/features/protocol-compatibility.md
  - ../../gateway/features/public-api-contracts.md
  - ../../gateway/decisions/adr-0002-route-product-pricing.md
  - ../../docs-site/README.md
  - ../../console/README.md
  - ../../../specifications/navigation.md
  - ../../../templates/page-design.md
---

# 页面设计：Home（首页）

## 草稿状态

本文根据 2026-07-26 的 Home 视觉原型整理，计划在 2026-07-27 讨论。当前内容、文案、视觉、
URL 和跨产品跳转均未批准，不构成交付承诺或正式页面规范；讨论后应更新本文，而不是继续以视觉原型
作为权威来源。

## 目的

让首次接触 UnioAPI 的开发者和 AI 应用团队快速理解产品定位：使用 API Key、线路、模型及熟悉的
OpenAI 或 Anthropic 协议调用模型，由平台在线路边界内处理协议适配、候选选择、流量调度和失败切换。

首页优先引导用户获取 API Key，其次引导用户查看接入文档。

## 用户与入口

| 用户或角色 | 入口 | 预期上下文 |
| --- | --- | --- |
| 开发者 | 直接访问、搜索结果或外部链接 | 正在评估如何用熟悉的 SDK 接入模型。 |
| AI 应用团队 | 直接访问、团队分享或产品介绍 | 正在比较接入方式、协议边界、可用模型和价格。 |
| 已了解产品的用户 | Home、Pricing、Docs 或 Console 间跳转 | 希望快速进入 Console、获取 API Key 或查阅文档。 |

## 目标

- 在首屏明确展示 `UnioAPI` 品牌和“模型不断变化。入口保持统一。”的核心定位。
- 准确表达 OpenAI-compatible 与 Anthropic-compatible 协议兼容，不暗示官方合作或完整兼容。
- 解释统一入口、线路内多模型访问、候选选择和失败切换的价值，但不使用不可验证的绝对承诺。
- 提供清晰的“获取 API Key”“接入文档”和“查看定价”入口。
- 在桌面端和最小 320 px 移动端保持内容顺序、可读性和操作完整性。

## 非目标

- 不在 Home 展示充值要求、充值规则、订阅套餐、模型基准价、线路倍率、渠道成本或平台毛利。
- 不将 Home 作为完整 API 参考、协议兼容矩阵或模型目录；复杂边界属于
  [Gateway 协议兼容性](../../gateway/features/protocol-compatibility.md)和公开接入文档。
- 不展示 Provider Logo 墙，也不把协议品牌标识解释为上游 Provider 列表。
- 不虚构专项场景能力、客户数据、可用性数字、最低价格或无故障承诺。
- 不在 Website 读取 Console 登录状态、管理 API Key 或复制 Console 自有流程。

## 信息层级

用户按以下顺序阅读和决策：

1. **全局导航**：品牌标识、Pricing、Docs、FAQs、Console 和“获取 API Key”。
2. **首屏**：品牌、核心定位、说明文案、两个主要操作，以及请求经 UnioAPI 到模型响应的简洁流程。
3. **协议兼容**：协议族切换、代表性端点、共享 API Origin 和可复制 `curl` 示例。
4. **核心价值**：熟悉的协议；一个入口、多种模型；让上游变化停在平台内部。
5. **使用场景**：AI 应用、Agent 工作流、编程与自动化工具。
6. **Pricing 入口**：说明价格按线路和模型查看，不在 Home 展开计价细节。
7. **FAQs**：回答接入前的高频问题，并把复杂边界引导到接入文档。
8. **最终行动**：再次提供“获取 API Key”和“接入文档”。

协议区域只展示以下代表性公开端点，不表示完整端点清单：

| 协议族 | Home 展示端点 | 展示重点 |
| --- | --- | --- |
| OpenAI-compatible | `POST /v1/responses`、`POST /v1/chat/completions`、`GET /v1/models` | 默认突出 Responses API；可以提示部分 Codex 场景从此验证，但不宣称完整兼容所有 Codex 行为。 |
| Anthropic-compatible | `POST /v1/messages` | 展示 Messages 调用结构，并引导用户查看版本头和字段边界。 |

Gateway 当前公开端点和认证事实见
[公开 API 契约](../../gateway/features/public-api-contracts.md)。Home 的端点选择是内容范围，不修改
Gateway 契约。

## 布局与响应式行为

- 整体采用安静、克制、专业的开发者产品风格，以中性色和少量品牌强调色建立识别。
- 页面分区使用全宽 Band 或无边框内容布局；只有代码工作台等确有边界的工具使用容器，不嵌套卡片。
- 卡片和工具容器圆角不超过 8 px；不使用渐变背景、光球、模糊光斑或装饰性 Hero SVG。
- 桌面端使用紧凑顶部导航、居中首屏、宽内容容器和明显的段落留白；首屏应露出下一分区内容。
- 移动端将导航折叠为菜单，主要操作改为全宽按钮，协议工作台改为单列；端点和代码可以在各自工具
  区域内横向滚动，但页面本身不得横向滚动。
- 支持浅色和深色主题；主题切换不得改变信息层级或隐藏内容。
- 固定格式的导航、按钮、协议控件、代码工具栏和图标按钮应具有稳定尺寸，避免状态变化造成布局跳动。

## 数据与权限

| 数据或操作 | 来源或权威位置 | 可见性或权限 | 新鲜度 |
| --- | --- | --- | --- |
| 产品定位与 Home 文案 | 本文 | 公开 | 随页面草稿评审更新 |
| 协议、端点和兼容边界 | [Gateway 协议兼容性](../../gateway/features/protocol-compatibility.md)与[公开 API 契约](../../gateway/features/public-api-contracts.md) | 公开摘要 | 发布前必须与 Gateway 权威事实核对 |
| 线路、模型和最终售价 | [线路与定价决策](../../gateway/decisions/adr-0002-route-product-pricing.md)及后续 Pricing 页面 | 公开摘要 | Home 不缓存或复制价格明细 |
| 登录状态和 API Key 获取 | [Console](../../console/README.md) | 由 Console 认证与授权 | Website 不读取登录状态 |
| 接入文档 | [Documentation Site](../../docs-site/README.md) | 公开 | Home 只提供入口 |
| API Origin | 发布配置 | 公开 | 草稿原型临时使用 `http://127.0.0.1:8080`；正式发布必须替换并阻止回环地址进入生产页面 |

## 交互

- 品牌标识返回 Home。
- Pricing、Docs 和 FAQs 导航到对应页面或页面分区；最终 URL 和跨产品域名待确认。
- Console 入口直接交给 Console。
- 所有“获取 API Key”入口统一交给 Console 的 API Key 旅程：未登录用户由 Console 完成登录后继续，
  已登录用户直接进入 API Key 页面。Website 不分支判断登录状态。
- 协议控件使用可键盘操作的 Tabs；默认选择 OpenAI-compatible 和 `POST /v1/responses`，切换协议后
  更新端点、说明和 `curl` 示例。
- OpenAI-compatible 端点列表允许在 Responses、Chat Completions 和 Models 间切换。
- 复制按钮复制当前完整 `curl` 示例，并提供“已复制”或失败反馈；示例不得包含真实 API Key。
- FAQ 使用无障碍 Accordion，支持展开、收起、方向键移动焦点、`Home`、`End`、`Enter` 和空格。
- 移动菜单打开时锁定页面背景滚动；选择站内入口后关闭菜单并移动到目标位置。
- 主题按钮在浅色和深色之间切换，具有可读名称和明确焦点状态。

## 页面状态

| 状态 | 必备表现 | 可用操作 |
| --- | --- | --- |
| 初始 | 立即显示首屏和默认 OpenAI Responses 示例 | 获取 API Key、查看文档或继续浏览 |
| 外部图标加载失败 | 保留品牌文字、协议兼容文字和按钮名称，不因图标缺失隐藏操作 | 继续使用所有入口和控件 |
| 复制成功 | 临时显示“已复制”，不改变代码布局 | 再次复制或切换示例 |
| 复制失败 | 显示简短失败反馈，不宣称成功 | 重试复制或手动选择代码 |
| 目标入口不可达 | 保留当前页面和可理解的目标名称 | 返回 Home 或选择其他入口；错误体验由目标产品负责 |
| 生产 Origin 配置错误 | 发布检查或页面保护必须阻止回环 Origin 作为生产示例继续展示 | 修正发布配置后重新发布 |

## 无障碍

- 页面只有一个 H1，内容为 `UnioAPI`；后续分区按 H2、条目按 H3 排列。
- 导航、主题、菜单、协议 Tabs、端点、复制和 FAQ 都使用语义元素、可读名称和清晰的焦点状态。
- 协议 Tabs 使用 `tablist`、`tab`、`tabpanel`、`aria-selected` 和焦点管理；FAQ 使用
  `aria-expanded`、`aria-controls` 和具名内容区域。
- 复制结果通过可被辅助技术读取的状态反馈表达；颜色不是选中、成功或错误的唯一线索。
- OpenAI 和 Anthropic Logo 旁必须保留文字 `OpenAI-compatible` 与 `Anthropic-compatible`；Logo 的
  非视觉名称不得暗示官方合作。
- 浅色和深色主题都满足正文、按钮、边框、代码和焦点状态的对比度要求。
- 320 px 及以上视口中，文字、按钮、导航和代码工具栏不得互相重叠；长代码只在代码区域内滚动。
- 尊重系统减少动态效果设置，不以动画传达必要状态。

## 文案

以下文案属于当前讨论草稿，评审前不得视为已批准产品契约。

### 首屏

- H1：`UnioAPI`
- 主标题：`模型不断变化。入口保持统一。`
- 正文：`兼容 OpenAI 与 Anthropic 协议，把多上游适配、线路调度和失败切换留给平台。你只管使用熟悉的 SDK 构建产品。`
- 主按钮：`获取 API Key`
- 次按钮：`接入文档`

### 协议兼容

- 标题：`兼容你已经熟悉的 API 协议`
- 协议标签：`OpenAI-compatible`、`Anthropic-compatible`
- 免责声明：品牌标识仅用于指明兼容的协议族，不代表官方合作、背书或上游 Provider 列表。

### 核心价值

| 标题 | 说明 |
| --- | --- |
| 熟悉的协议 | 继续使用 OpenAI 或 Anthropic 的调用方式，减少重复学习和迁移成本。 |
| 一个入口，多种模型 | 使用统一入口访问线路内可用模型，让应用集成保持清晰。 |
| 让上游变化停在平台内部 | 平台在线路边界内处理候选选择和失败切换，减少对客户应用的影响。 |

### 使用场景

- `AI 应用`
- `Agent 工作流`
- `编程与自动化工具`

场景说明只描述通用接入用途，不承诺尚未确认的专项产品能力。

### Pricing 入口

- 标题：`按线路和模型，查看最终售价`
- 说明：`选择适合你的线路，清楚了解每个模型对应的调用价格。`
- 按钮：`查看定价`

### FAQs

| 问题 | 草稿回答 |
| --- | --- |
| UnioAPI 兼容哪些 API 协议？ | 当前展示 OpenAI-compatible 与 Anthropic-compatible 接入。具体端点、字段和行为边界请查看接入文档。 |
| 接入时需要重写现有代码吗？ | 通常可以沿用熟悉的 SDK 和调用结构，重点调整 API Origin、API Key 与模型名称。迁移差异以接入文档为准。 |
| 可以调用哪些模型？ | 可用模型取决于 API Key 绑定的线路。请在 Console 的线路与模型列表中查看当前可用范围。 |
| 什么是线路？ | 线路是客户可见的产品档位和供给边界，关联模型范围、定价与线路内调度。详细定义见[Gateway 词汇表](../../gateway/glossary.md)。 |
| 模型价格在哪里查看？ | 前往 Pricing 页面，按线路和模型查看对应的最终调用价格。 |
| 如何获取 API Key？ | 点击“获取 API Key”进入 Console。Console 统一处理登录状态，并在认证后继续前往 API Key 页面。 |

### 最终行动

- 标题：`准备好少折腾一点了吗？`
- 正文：`获取 API Key，继续使用你已经熟悉的开发方式。`
- 按钮：`获取 API Key`、`接入文档`

不得使用 `99.99% 可用性`、`完全兼容所有 API`、`零故障`、`全网最低价`、`免费使用`、
`注册后立即调用`或同类无法验证的绝对承诺。

## 指标与可观测性

以下指标只作为讨论候选，事件名称、采集方式、隐私边界和目标值尚未批准：

- 获取 API Key、接入文档、Pricing 和 Console 入口的点击与后续到达。
- OpenAI-compatible 与 Anthropic-compatible Tabs 的选择，以及端点示例切换。
- 复制成功、复制失败和重试，不采集 API Key 或完整用户代码。
- FAQ 展开、收起和从 FAQ 前往文档的行为。
- 不同视口和主题下的页面错误、外部资源失败和横向溢出回归。

## 验收标准

- [ ] Home 内容、导航顺序、文案和视觉方向经官网团队批准，文档状态从 `draft` 推进。
- [ ] H1、首屏主标题、正文和主要操作符合本草稿，首屏不显示充值提示。
- [ ] 协议区域明确区分协议兼容与 Provider，不展示 Provider Logo 墙或暗示官方合作。
- [ ] 默认突出 OpenAI Responses，并能切换 Anthropic Messages 与对应 `curl` 示例。
- [ ] API Origin 只有一个共享发布配置来源，生产检查会阻止 `localhost`、`127.0.0.1` 或其他回环地址。
- [ ] Website 不读取登录状态，所有 API Key 入口交给 Console 处理认证和继续跳转。
- [ ] Pricing 区域只提供最终售价入口，不展示充值、订阅、基准价、倍率、成本或毛利细节。
- [ ] 六项 FAQ 内容简短准确，并把复杂兼容边界引导到接入文档。
- [ ] 桌面端、320 px 移动端、浅色和深色主题均无重叠或页面横向溢出。
- [ ] 协议切换、复制、FAQ、导航锚点、移动菜单和主题切换均可通过键盘和指针操作。
- [ ] 外部品牌 Logo 和图标加载失败时，文字标签和主要操作仍然可用。

## 待解决问题与相关决策

- 2026-07-27 讨论是否接受当前内容节奏、视觉方向、导航顺序和文案。
- 确认 Website、Pricing、Documentation Site、Console 和 API Key 旅程的正式 URL、域名与重定向规则。
- 确认 Console 是否已有“登录后继续到 API Key 页面”的稳定产品契约；如需页面设计，应由 Console 建档。
- 确认正式 API Origin、发布配置所有者和回环地址检查落点。
- 确认 Pricing 页面在订阅套餐完善前的最小内容，以及“最终售价”的更新和展示来源。
- 与 Gateway 和文档团队确认 Home 展示端点、Codex 提示、Anthropic 版本头和兼容免责声明的最终措辞。
- 核对 OpenAI 与 Anthropic 品牌资产的使用规范、加载方式和失败回退。
- 决定 UnioAPI 正式品牌标识、强调色、分析指标与成功目标。
