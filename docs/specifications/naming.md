---
title: 命名规范
description: UnioAPI 跨产品共享语言和标识符约定。
status: active
owner: 架构团队
last_updated: 2026-07-21
related:
  - README.md
  - documentation.md
  - ../architecture/glossary.md
---

# 命名规范

## 目的

保证产品之间的名称可预测、长期有效且含义清楚。

## 通用规则

- 除非缩写已在[平台词汇表](../architecture/glossary.md)定义，否则使用完整、
  描述性的词语。
- 按产品和业务能力命名，不按当前仓库或团队命名。
- 一个术语只表示一个概念，一个概念只使用一个术语。
- 优先使用在实现技术变化后仍然准确的名称。
- 对外公开前先定义公共词汇。

## 文件与目录

- 使用小写 ASCII 字母、具有明确意义的数字和连字符。
- 多单词名称使用 kebab-case。
- 不使用空格、下划线、没有语义的日期或仓库专用前缀。
- `README.md` 只作为目录入口。

## 产品名称

正文统一使用 Website（官网）、Documentation Site（文档站）、Console（用户控制台）、
Admin（管理后台）、Gateway（网关）和 SDK（软件开发工具包）。`docs-site` 是
Documentation Site 已确定的文件系统名称。

## 尚未确定的约定

API 标识符、事件名、权限标识符和语言专用符号，需要在各自规范完成评审后再补充。

