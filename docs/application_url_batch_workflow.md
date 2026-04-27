# Application URL Batch Workflow

目标：在不改动现有 application pipeline 边界的前提下，把当前 `--url-list` 批量导入路径收口成一个可重复使用的最小人工喂数工作流。

## 输入模式

`scripts/run_application_batch.py` 目前支持三种互斥输入模式，一次只能使用一种：

- JSON 文件输入
- `--url` 单个 URL 输入
- `--url-list` URL 列表输入

如果同时提供多个输入模式，脚本会直接报错。

说明：

- 单文件 `--url-list` 行为保持不变，仍支持原有 `.txt` 和 `.json` 两种格式
- 目录模式只是 `--url-list` 的新增输入形态，不替代原有单文件模式
- 目录模式内部仍然复用现有 batch 导入路径，不新增新的 ingestion 主流程

## 常用命令

1. JSON 文件输入

```powershell
.\.venv\Scripts\python.exe scripts\run_application_batch.py scripts\sample_application_batch_input.json --no-persist
```

2. 单 URL 输入

```powershell
.\.venv\Scripts\python.exe scripts\run_application_batch.py --url https://simonwillison.net/2024/May/29/training-not-chatting/ --no-persist
```

3. URL 列表文件输入

```powershell
.\.venv\Scripts\python.exe scripts\run_application_batch.py --url-list scripts\sample_application_url_list.txt --no-persist
```

4. Seed 目录输入

```powershell
.\.venv\Scripts\python.exe scripts\run_application_batch.py --url-list scripts\sample_seed_sources --no-persist
```

## `--url-list` 支持的输入形态

`--url-list` 现在支持两类输入：

1. 单个 URL 列表文件

- `.txt`：每行一个 URL，空行和 `#` 注释行会被忽略
- `.json`：文件内容必须是 URL 字符串数组

示例文件：

- `scripts/sample_application_url_list.txt`
- `scripts/sample_application_url_list.json`

2. Seed 目录

- 目录下可放多个 `.txt` 或 `.json` 文件
- 文件按文件名排序后依次加载
- 多个文件中的重复 URL 会按首次出现去重
- 这样可以按“来源”“主题”或“人工维护批次”拆分管理，而仍然复用同一个 `--url-list` 入口

示例目录：

- `scripts/sample_seed_sources/ai_blog_watch.txt`
- `scripts/sample_seed_sources/blocklist_check.txt`

## 推荐的最小 Seed 组织方式

当前阶段推荐直接使用目录 + 多文件，而不是新建数据库表、Source 管理模块或新的抓取入口。

建议约定：

- seed 目录命名使用清晰、稳定的用途名，例如 `scripts/real_seed_sources/`
- 文件名使用英文小写下划线，例如 `model_labs.txt`、`research_blogs.txt`、`manual_batch_weekly.txt`
- 一个文件只表达一种主要用途，优先按“来源集合”分组；需要时才按“人工批次”补充
- 当前阶段不建议同时混用来源、主题、批次三种拆分维度
- 文件内容只保留当前确实要手工跟踪的文章 URL
- 如果想保留失败样本用于验收或观察，单独放在类似 `known_failures.txt` 的文件里

这个方案的优点是：

- 不改变 orchestrator / persistence / CLI 主路径
- 不引入新的 ingestion 类型
- 操作员只需要维护文本或 JSON 文件
- 现有 `--url-list` 已经可以直接消费

## 去重规则

目录模式下，URL 去重规则是“首次出现优先”。

- 先按文件名排序加载目录中的 `.txt` 和 `.json` 文件
- 再按每个文件中的出现顺序读取 URL
- 同一个 URL 后续再次出现时会被忽略

如果同一个 URL 被放进多个文件，最终以第一次读到它的那个位置为准。建议人工尽量清理重复项，避免长期分散维护。

## 异常输入行为

`--url-list` 使用目录模式时，当前预期行为如下：

- 空目录：报错。目录下至少需要一个受支持的 `.txt` 或 `.json` 文件。
- 非法 JSON 文件：报错。该目录加载失败，不继续进入后续 batch。
- 不支持的文件类型：忽略。当前只读取 `.txt` 和 `.json` 文件。

## 运行语义

当前 batch 入口继续保持 `per_document` 语义。

- URL 列表会逐条导入
- 每条 URL 先尝试抓取并映射成 `RawDocumentInput`
- 映射成功后再进入现有 application pipeline
- 单条 URL 抓取失败不会阻塞后续项目
- 失败项会作为独立的 `failed item` 输出到最终 JSON 结果中

这意味着：

- 成功 URL 和失败 URL 可以混在同一个 seed 文件或 seed 目录里
- 只要脚本本身没有整体级别错误，后续 URL 仍会继续处理

## 失败 URL 的最小处理规则

当前阶段不做失败 URL 管理平台，只保持最小人工处理规则：

- 临时失败的 URL 可以先保留，并在文件中加注释说明
- 确认不适合当前 importer 的 URL，应从正式 seed 文件移除
- 需要长期保留的失败样本，单独放入 `known_failures.txt`
- 不建议把已知失败 URL 长期混在正式喂数文件里

## 当前支持的页面类型

当前路径只覆盖“最薄 URL 导入”边界，适合：

- 静态或偏静态 HTML 文章页
- 标题可从 `<title>` 或 `og:title` 提取的页面
- 正文主要由标准 `<p>` 段落组成的博客或新闻页
- 不需要登录、没有强反爬、无须 JS 渲染正文的英文文章页

## 当前不支持的页面类型

当前明确不处理以下情况：

- 返回 `403` 的页面
- 强反爬页面
- 依赖 JS 渲染正文的页面
- 需要浏览器自动化才能拿到正文的页面
- 复杂站点专用适配

本阶段不引入 Playwright，不做 `403` 绕过，也不扩成通用爬虫系统。

## 现有样例

当前仓库提供两类样例：

- 单文件 URL 列表：
  - `scripts/sample_application_url_list.txt`
  - `scripts/sample_application_url_list.json`
- Seed 目录：
  - `scripts/sample_seed_sources/`

这些样例包含：

- 2 个更适合当前最薄导入器的静态或偏静态英文文章页
- 1 个预期失败样本，用来验证 `per_document` 失败隔离语义
- 1 个重复 URL，用来验证 seed 目录汇总时的去重行为

## 建议验收步骤

1. 先确认 JSON 文件路径未回归

```powershell
.\.venv\Scripts\python.exe scripts\run_application_batch.py scripts\sample_application_batch_input.json --no-persist
```

2. 再确认单 URL 路径未回归

```powershell
.\.venv\Scripts\python.exe scripts\verify_application_url_import.py https://www.example.com/
```

3. 最后跑 URL 列表与 seed 目录验证

```powershell
.\.venv\Scripts\python.exe scripts\verify_application_url_list_import.py
```

如果后续要换成真实人工维护 seed，优先继续使用静态或偏静态英文文章页，不要直接替换成强反爬或纯前端渲染页面。
