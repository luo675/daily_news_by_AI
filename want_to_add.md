# 已推进功能：文档管理控制台与 Ask 提问范围

默认回复和新增 Web 文案使用中文。现有英文切换能力继续保留，不要求翻译用户导入的知识内容。

## 1. 背景

当前项目已经具备 Web MVP：

- 可以通过 `/web/import` 手动导入粘贴文本或 `.md/.markdown/.txt` 文件
- 可以在 Documents 页面浏览已入库文章
- 可以在 Review 页面人工修订自动处理结果
- 可以在 Ask 页面基于本地知识库提问

本轮已把当前 Web MVP 从“可浏览、可导入、可提问”推进到“可日常管理和定向提问”的第一版闭环。

当前完成状态：

- Ask 已支持全库提问和单篇文章提问范围选择
- 导入后仍进入文档详情页，详情页可一键进入“基于本文提问”
- 文档详情页已支持编辑基础字段
- 文档详情页已支持归档 / 恢复文章
- 归档是 Web 侧软删除，不物理删除数据库记录

## 2. 功能一：我的文档管理控制台

### 目标

用户可以在 Web 中管理已经保存到本地数据库的文章，而不需要直接操作数据库或终端脚本。

### 第一版能力与当前状态

- 在 Documents / Knowledge 中查看已入库文章
- 打开文章详情
- 编辑文章基础信息：
  - 标题
  - URL
  - 来源
  - 发布时间
  - 语言
  - 正文内容
- 对文章执行归档或软删除
- 对正文被修改过的文章标记为需要重新处理，或提供重新处理入口
- 显示文章当前状态：
  - 正常
  - 已归档
  - 需要重新处理
  - 处理失败

当前实现说明：

- 编辑字段包括 title / url / language / published_at / content_text
- source 当前仍为只读展示，未做下拉选择器
- content_text 变更后写入 `metadata_.web_edit.needs_reprocess` 并显示重新处理建议
- 归档状态写入 `metadata_.web_management.archived / archived_at`
- 默认 Documents 列表隐藏归档文章
- `/web/documents?show_archived=1` 可显示归档文章
- 默认 Documents 列表的归档过滤已前移到数据库查询，归档文章不会挤占默认 50 条未归档列表名额

### 设计约束

- 第一版优先做软删除或归档，不默认硬删除数据库记录
- 如果正文内容被修改，原有 summary / opportunities / risks / uncertainties 等派生结果需要被视为可能过期
- 人工 review edits 的优先级仍然高于自动处理结果
- 不改变现有 ingestion / processing / persistence 主链，除非确认现有结构无法承载最小状态字段
- 当前没有改数据库 schema，也没有改 `Document.status` 的处理生命周期语义

### 第一版不做

- 多人权限系统
- 复杂角色管理
- 批量删除
- 文件归档系统
- PDF / Word / 多文件上传
- 通用爬虫或自动发现来源
- Playwright / JS 渲染抓取平台

## 3. 功能二：Ask 提问范围选择

### 目标

用户提问时可以明确选择回答依据，避免系统在全库、单篇文章、刚导入文章之间混淆。

### 提问模式

1. 基于本地数据库全部内容
   - 默认模式
   - 复用当前 Ask 的 local retrieval first 链路
   - 当前已实现

2. 只基于某一篇已入库文章
   - 用户必须选择一篇 document
   - evidence、opportunities、risks、uncertainties、context 都只能来自该 document
   - 结果页需要显示当前使用的文章标题和 document_id
   - 当前已实现

3. 先外部导入数据库，再基于该文章提问
   - 复用现有 `/web/import`
   - 导入成功后进入文档详情
   - 文档详情提供“基于本文提问”入口
   - Ask 页面带着 document_id 进入单篇文章提问模式
   - 当前已实现为 Import -> Document Detail -> Ask about this document

### 设计约束

- Ask 仍然必须保持 local retrieval first
- 外部 AI 只能消费“问题 + 已选本地证据 + bounded context”
- 不允许把问题直接裸发给外部 AI
- 不允许因为单篇文章提问而扩展成 advanced RAG 或向量问答主链重构
- Ask history 需要记录提问范围元数据，至少包含：
  - answer_scope
  - document_id（如果是单篇文章模式）
  - document_title（如果可用）

当前遗留说明：

- Ask history 的 `answer_scope / document_id / document_title` 目前只在运行结果中携带，没有做 schema 持久化扩展

## 4. 功能三：导入后提问工作流

### 目标

把现有手动导入和 Ask 连接起来，使用户可以自然完成：

导入文章 -> 查看文章 -> 基于该文章提问。

### 第一版能力与当前状态

- `/web/import` 成功后继续跳转到 `/web/documents/{document_id}`
- Document Detail 页面提供“基于本文提问”入口
- `/web/ask` 支持通过 query 参数或表单字段接收 `document_id`
- 当存在 `document_id` 时，Ask 默认进入“只基于某一篇文章”模式

当前已完成。

### 第一版不做

- 在 Ask 页面内实现完整文件上传器
- PDF / Word 解析
- 多文件批量导入
- 文件管理系统
- 自动来源发现
- 通用爬虫

## 5. 已完成开发顺序

本轮实际完成顺序：

1. 补充需求与页面契约文档
2. 实现 Ask `answer_scope` 与单篇文章范围限制
3. 串联 Import -> Document Detail -> Ask about this document
4. 实现文档基础字段编辑
5. 实现文档归档 / 恢复软删除

## 6. 已知未收口问题

- 归档状态当前存储在 `metadata_.web_management`，不是正式 schema 字段。
- 硬删除不是当前目标，仍未实现。
- Ask history 的 scope 元数据尚未做 DB schema 持久化扩展。

## 7. 验收标准

- 用户可以在 Web 中编辑一篇已入库文章的基础信息
- 用户可以归档或软删除一篇文章，且不会破坏历史 review / ask 数据
- 用户可以在 Ask 中选择“基于本地数据库”或“只基于某一篇文章”
- 单篇文章模式下，返回 evidence 只来自目标文章
- 导入一篇文章后，可以从文章详情一键进入“基于本文提问”
- 新增文案默认中文，英文切换能力不回归

当前这些第一版验收标准已完成；上述剩余问题除外。
