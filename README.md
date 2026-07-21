---
title: UnioAPI 蓝图
description: UnioAPI 生态系统的唯一事实来源。
status: active
owner: 平台团队
last_updated: 2026-07-21
related:
  - docs/README.md
  - docs/architecture/overview.md
  - docs/specifications/documentation.md
---

# UnioAPI 蓝图

本仓库是 UnioAPI 的权威知识系统，用于记录平台架构、产品方向、共享规范、
关键决策、质量要求与发展计划。

它不是文档网站，也不是代码实现仓库。

## 从这里开始

| 想了解的问题 | 权威位置 |
| --- | --- |
| 平台为何存在，为什么这样设计？ | [平台架构](docs/architecture/README.md) |
| 所有产品共同遵守哪些标准？ | [平台规范](docs/specifications/README.md) |
| 某个产品领域负责什么？ | [产品领域](docs/README.md#产品领域) |
| 某项跨产品选择为何这样决定？ | [全局决策](docs/decisions/README.md) |
| 整个生态接下来如何发展？ | [平台路线图](docs/roadmap/README.md) |
| 新文档应该如何编写？ | [文档模板](docs/templates/README.md) |

## 唯一事实来源规则

1. 每个概念只能有一个权威文档。
2. 通过链接引用权威内容，不复制第二份说明。
3. 长期知识按产品领域组织，不按代码仓库名称组织。
4. 具体实现说明留在对应代码仓库，约束实现的决策和规范放在这里。
5. 重要选择必须先形成架构决策记录，再作为确定规则引用。
6. 未确认的信息必须明确标注；宁可保留清晰的占位，也不虚构产品细节。

## 仓库边界

各代码仓库只保留理解和开发本仓库代码所需的轻量内容：

- 项目介绍；
- 快速开始；
- 开发指南；
- 指向本蓝图仓库的链接。

产品文档、平台规范、设计依据和路线图统一维护在本仓库。

## 语言与命名

文档正文默认使用简体中文。产品专名、行业通用缩写、文件路径、YAML 字段名和
代码标识符保留英文。文件与目录继续使用小写 kebab-case，保证 Git、链接和
自动化工具的稳定性。

## 参与维护

新增或移动内容前请阅读 [贡献指南](CONTRIBUTING.md)。AI 工具还必须遵守
[AI 协作规则](AGENTS.md)。

本地校验命令：

```sh
make validate
```
