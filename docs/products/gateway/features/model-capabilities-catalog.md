---
title: 模型能力与目录
description: Gateway 当前的能力字典、模型能力声明、Adapter 画像和外部目录边界。
status: active
owner: 网关团队
last_updated: 2026-07-27
related:
  - ../overview.md
  - ../glossary.md
  - public-api-contracts.md
  - provider-adaptation.md
  - ../decisions/adr-0004-model-capabilities.md
---

# 模型能力与目录

## 摘要

Gateway 当前维护四类不同表示：能力 key 字典、模型能力声明、代码 Adapter 画像和外部模型目录。
模型能力声明会出现在客户模型目录并支持筛选，但不参与真实请求的入口校验、候选路由、Adapter 选择
或计费。外部目录和 Adapter 画像都可经管理路径单向复制到模型声明，因此四者并非完全独立数据集。

## 数据模型

### 能力字典

`capability_keys` 是模型能力声明的外键字典。每个 key 保存 domain、展示名称、说明、排序、软退役标记
和 `protocol_scope`。数据库只接受 `shared`、`openai` 或 `anthropic` 三种 scope；Admin 写入会把空值、
`both` 和未知值归一为 `shared`。`deprecated` 当前只是元数据，不阻止声明写入，也不影响
`/v1/models` 返回。

当前迁移基线包含 33 个 key：

| Capability key | `protocol_scope` |
| --- | --- |
| `text.input` | `shared` |
| `text.output` | `shared` |
| `image.input` | `shared` |
| `image.output` | `shared` |
| `audio.input` | `shared` |
| `audio.output` | `shared` |
| `file.input` | `shared` |
| `tools.function` | `shared` |
| `tools.custom` | `openai` |
| `tools.parallel` | `shared` |
| `tools.choice_required` | `shared` |
| `tools.builtin.web_search` | `openai` |
| `tools.builtin.file_search` | `openai` |
| `tools.builtin.code_interpreter` | `openai` |
| `tools.builtin.computer_use` | `openai` |
| `tools.builtin.image_generation` | `openai` |
| `tools.builtin.mcp` | `openai` |
| `reasoning.effort` | `openai` |
| `reasoning.budget` | `anthropic` |
| `reasoning.summary` | `openai` |
| `response_format.json_object` | `shared` |
| `response_format.json_schema` | `shared` |
| `prompt_cache` | `shared` |
| `logprobs` | `shared` |
| `service_tier` | `openai` |
| `stream` | `shared` |
| `stream.tools` | `shared` |
| `stream.usage` | `shared` |
| `server_state.store` | `openai` |
| `server_state.background` | `openai` |
| `responses.encrypted_content` | `openai` |
| `responses.compact.native` | `openai` |
| `responses.compact.synthetic` | `openai` |

`protocol_scope` 当前只是字典分类。修改 scope 不检查、迁移或重写已有模型声明，也不校验代码 Adapter
画像。

### 模型能力声明

`model_capabilities` 的主键是 `(model_id, capability_key)`。声明只包含以下业务维度：

- `support_level`：`full`、`limited` 或 `unsupported`；
- 可选 `limits` JSON；
- 创建、更新时间和可空的 `updated_by`。

声明表没有来源列，也没有协议列。数据库外键保证 capability key 存在，但写入声明时不会将模型、
Channel 协议或 Adapter 画像与 `protocol_scope` 比较。

## Admin 能力维护

当前 Admin 注册了以下能力：

| 操作面 | 当前行为 |
| --- | --- |
| 能力字典 | 列表、新建、更新和删除能力 key；没有单 key GET 路由。被模型声明引用的 key 由外键阻止删除；目录提示表没有该外键。 |
| 模型声明 | 查询模型声明，并用批量整表 PUT 替换该模型的声明集合。per-key Set/Delete 只存在于 service/interface，没有注册 HTTP 路由。 |
| Adapter 画像 | 列出已注册的静态画像，并可把指定画像物化到模型声明；当前接口不计算画像与模型声明的差异。 |
| 目录同步 | 列出同步任务，并以内联 POST 触发 dry-run 或实际同步。 |
| 目录浏览与采纳 | 注册目录列表、详情和采纳入口。刷新与提醒处置已有 service 实现，但没有注册 HTTP 路由。 |

批量模型声明写入校验 key、support level、limits 和重复项，但没有协议维度。

当前只注册 DeepSeek OpenAI 和 DeepSeek Anthropic 两份画像。画像物化按 key 执行 upsert，同一
`(model_id, capability_key)` 已存在时直接覆盖当前声明。逐 key 写入没有包裹为一个事务；中途失败时，
此前成功写入的 key 不会回滚。画像校验只限制非 `limited` 声明不得携带 limits，不校验 limits JSON
是否有效或其对象结构，也不预检数据库字典、`protocol_scope` 或模型与 Channel 拓扑。字典缺失最终
由对应 upsert 的外键拒绝。DeepSeek Anthropic 画像确实包含多个字典中标为 `openai` scope 的 key，
画像校验和物化不会拒绝这种组合。因为表中没有来源列，物化后也无法从持久数据区分人工、目录采纳
或画像写入。

## 外部模型目录

当前 models.dev 同步写入独立的 catalog 数据与粗能力提示，不直接创建运行时模型，也不改写路由、
价格、Channel 或现有模型能力声明。目录条目保存来源标识、内容 fingerprint、同步状态与可采纳元数据。

同步可通过 Admin `GET/POST /capability/sync-jobs` 查看或内联触发，也可通过
`worker-server sync-models [--dry-run]` 手动执行；配置启用时，worker-server 还会按间隔周期执行。
实际同步不是整批事务：不同目录条目依次应用，单条条目也先更新元数据、删除旧提示，再逐条插入新提示。
失败任务不会回滚此前已应用的条目，当前条目也可能只留下部分提示。

`model_catalog_capabilities` 不外键引用 `capability_keys`，所以目录同步可以保存当前字典中不存在的提示
key，仅被目录提示引用的字典 key 也可以删除。之后目录采纳会在字典预检时拒绝未知 key；目录刷新则会
在向 `model_capabilities` 写入时触发外键错误，并回滚该次刷新事务。

Admin 采纳目录条目时在同一事务中创建本地 model、写入采纳请求携带的能力声明，并建立 catalog link。
本地模型名称、Owner、状态、窗口、展示价格、发布日期和能力集合都以请求为准；代码不要求它们等于
目录条目，也不拒绝已标记 `removed_upstream_at` 的条目。一个目录条目可以关联多个本地模型；每个本地
模型最多有一个 catalog link。

model catalog service 还实现了刷新和提醒处置：

- 刷新按当前目录条目更新已关联模型的目录快照，并删除后重写该模型的全部能力声明；
- 提醒处置保存当前 fingerprint 的忽略、静音或稍后提醒状态；
- 当前 HTTP router 只暴露目录列表、详情和采纳，没有刷新或提醒处置入口。

因此，刷新与提醒是代码中的 service 能力，但当前不能通过已注册的 Admin HTTP API 调用。

## 客户模型目录

OpenAI-compatible `/v1/models` 从调用方 Route 可见的模型聚合能力声明：

- 只把非 `unsupported` 的声明作为 capability tag 返回；
- `full` 和 `limited` 折叠为相同 tag，响应不返回 support level 或 `limits`；
- 只读取第一个 `?capability=` 参数值，把其中逗号分隔的非空 key 按 AND 语义筛选；重复参数的后续值
  被忽略，未知 key 不报错但通常匹配不到模型；
- 模型可见性检查 Route 中的 Channel 模型绑定，但查询没有按 Channel protocol 过滤；
- 查询不读取能力 key 的 `protocol_scope` 或 `deprecated`；
- 查询不检查 Provider 状态或当前进程的 Adapter registry。

结果可能同时包含 OpenAI、Anthropic 或 shared 分类的 tag；这些 tag 是聚合后的模型声明，不表示当前
请求协议一定有对应 Channel，也不表示 Adapter 会执行该字段。

## 运行时边界

真实生成请求不读取 `model_capabilities`：

- ingress 不用声明拒绝合法协议字段；
- 候选查询按请求协议过滤 Channel；
- 候选准备使用代码 Adapter registry 判断 tokenizer、非流式、流式、Responses 或 Chat bridge 能力；
- Provider 的 Pass、Adapt、Drop 和 Reject 由实际协议 service 与 Adapter 代码决定；
- 价格、授权和结算不读取模型能力声明。

代码中出现的 Adapter operation capability 与 `model_capabilities` 是不同概念。前者决定当前进程能否
执行某种调用，后者只用于 Admin 维护和客户目录标签。

## 当前边界

- `model_capabilities` 没有声明来源和协议维度，无法从表内判断某行由人工、目录采纳还是 Adapter 画像写入。
- Adapter 画像物化会直接 upsert 并覆盖同 key 声明。
- Adapter 画像物化逐 key 非事务写入，中途失败可能留下部分画像；当前只注册两份 DeepSeek 画像。
- models.dev 实际同步不是整批或单条事务，失败时可能留下已应用条目或当前条目的部分能力提示。
- 目录能力提示不受能力字典外键约束；采纳与刷新遇到未知 key 时才分别在预检或声明外键处失败。
- `protocol_scope` 不参与声明、画像、目录采纳、刷新或 `/v1/models` 查询校验；跨 scope 声明当前可以写入
  并公开聚合。
- `deprecated` 不阻止新声明，也不从客户目录隐藏对应 tag。
- 刷新会删除并重写全部能力声明；刷新和提醒 service 当前没有已注册的 HTTP 入口。
- 客户 capability tag 不保留 level/limits，并且不构成运行时能力保证，也不参与真实候选路由。

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码、Schema 和现有测试接收为 `active`。
