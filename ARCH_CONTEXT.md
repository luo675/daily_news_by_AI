# 最小上下文摘要

## 0. Latest Web Storage Status

This section overrides older notes that described Ask history and AI provider config as JSON-only.

- Ask history is now DB-first with JSON fallback.
- AI provider config is now DB-first with JSON fallback.
- Old `configs/web/qa_history.json` is still tolerated as fallback, but is not auto-imported into DB.
- Old `configs/web/ai_settings.json` is still tolerated as fallback, but is not auto-imported into DB.
- `Source.config["_web"]` is still intentionally retained and is not part of the current migration target.
- Main knowledge storage boundaries are unchanged.

See:

- `docs/web_local_storage_boundary.md`
- `docs/ask_result_display_optimization.md`

## 1. 项目结构（精简版）

### 根目录

- `goal.md`
  - 项目目标与初始架构草稿
- `ARCH_CONTEXT.md`
  - 当前最小上下文摘要；新会话优先读取
- `pyproject.toml`
  - Python 项目配置
- `alembic.ini`
  - Alembic 配置

### 文档目录 `docs/`

- `project_overview.md`
  - 项目总览
- `architecture.md`
  - 架构设计
- `roadmap.md`
  - 里程碑规划
- `task_breakdown.md`
  - 任务拆分
- `task_cards.md`
  - 可派发任务卡
- `api_spec.md`
  - API 草案
- `testing_strategy.md`
  - 测试与质量策略
- `review_implementation.md`
  - 人工修订实现说明

### 代码目录 `src/`

- `domain/`
  - `base.py`
  - `enums.py`
  - `models.py`
  - 第一阶段核心领域模型与共享枚举
- `ingestion/`
  - `schemas.py`
  - `source_registry.py`
  - `adapters.py`
  - `validators.py`
  - 统一采集输入与来源注册骨架
- `processing/`
  - `schemas.py`
  - `cleaning.py`
  - `summarization.py`
  - `extraction.py`
  - `conflicts.py`
  - `pipeline.py`
  - 清洗、摘要、实体/主题抽取、冲突检测骨架
- `scoring/`
  - `schemas.py`
  - `service.py`
  - 产品机会评分骨架
- `briefing/`
  - `schemas.py`
  - `service.py`
  - 日报草稿结构与生成骨架
- `application/`
  - `schemas.py`
  - `mappers.py`
  - `persistence.py`
  - `orchestrator.py`
  - 应用层映射、最小持久化、编排入口
- `watchlist/`
  - `schemas.py`
  - `service.py`
  - `weight.py`
  - watchlist 服务层
- `api/`
  - `app.py`
  - `auth.py`
  - `deps.py`
  - `schemas.py`
  - `routes/`
  - API 骨架与路由
- `admin/`
  - `review_schemas.py`
  - `review_service.py`
  - `review_service_db.py`
  - 人工修订服务
- `config.py`
  - 数据库与 session 配置

### 配置与脚本

- `configs/sources/default_sources.yaml`
  - 默认来源配置
- `scripts/`
  - `verify_models.py`
  - `verify_ingestion.py`
  - `verify_watchlist.py`
  - `verify_api.py`
  - `verify_review.py`
  - `verify_pipeline.py`
  - `verify_application_flow.py`
  - 当前主要验收脚本

---

## 2. 当前需求目标

### 项目定位

- 项目名：`daily_news`
- 目标不是普通资讯抓取器，而是面向 AI 领域的个人知识数据库
- 第一阶段按个人使用设计，后续可将结果开放给其他人或 AI Agent 消费
- 正式产品形态已进一步明确为：本地优先的网页工作台，而不是终端优先工具
- 正式使用时应以网页为主入口；终端主要保留给维护、验证、批处理和运维

### 第一阶段核心目标

- 收集高价值 AI 信息
- 将原始内容处理为结构化知识
- 支持检索、串联、问答、日报
- 支持产品机会判断，优先于泛投资研究
- 提供面向 AI Agent 的结构化 API
- 为后续网页产品提供本地知识底座、人工修订底座与问答底座

### 第一阶段重点输出

- 中英双语每日简报
- 产品机会列表
- 风险列表
- 不确定性与冲突提示
- watchlist 更新
- 结构化 API 响应
- 后续网页工作台所需的可展示、可检索、可修订知识结果

### 第一阶段优先数据源

- 英文优先
- 技术博客
- 演讲文字稿
- 访谈文字稿
- 播客文字稿

### 推荐的 P0 来源样板

- 技术博客与研究者长文
  - Andrej Karpathy
  - Ethan Mollick
  - 李飞飞相关公开文字内容
  - Jim Fan 公开文字内容
- 高价值访谈与深度对谈文字稿
  - Dwarkesh Podcast
  - a16z Podcast
  - 20VC
  - The Robot Brains Podcast
- 投资与创业视角节目文字稿
  - All-In Podcast
  - Interplay VC Podcast
  - TechCrunch Equity Podcast
  - TBPN

---

## 3. 已确定的设计决策

### 用户与使用方式

- 第一阶段只给个人使用
- 外部主要消费对象是通用 AI Agent
- 后续可扩展为多人共享，但当前不做多租户设计
- 正式产品主入口应为网页后台
- 外部 AI 应作为可配置 provider 接入，而不是写死到代码逻辑中
- 数据、配置和人工修订记录应优先保存在本地

### 输出与语言

- 数据源以英文为主
- 输出采用中英双语并列
- 日报第一阶段输出 Markdown
- 每天固定生成一份日报
- 用户可按需额外生成一份最新简报

### 产品机会判断

- 产品机会判断优先于投资研究判断
- 重点回答两个问题：
  - 需求是否真实存在
  - 市场是否仍有空白
- 默认评分维度：
  - `需求真实性` 30%
  - `市场空白度` 30%
  - `产品化可行性` 20%
  - `跟进优先级` 10%
  - `证据充分度` 10%
- 冲突会增加不确定性，不应抬高优先级

### 冲突与不确定性

- 优先自动判断
- 判断不了时保留不确定性
- 输出时明确标记冲突与待确认项
- 来源可信度必须参与冲突判断

### 来源可信度

- 使用 `S / A / B / C`
- 区分一手来源、原始发言、机构原文、二手整理、评论转述

### 存储策略

- 第一阶段不强求保存网页快照或全文归档
- 优先保存：
  - 来源链接
  - 元数据
  - 摘要
  - 结构化处理结果
  - 评分结果
  - 人工修订记录

### watchlist

- 必须支持
- 支持对象类型：
  - 人物
  - 公司
  - 产品
  - 模型
  - 主题
  - 赛道
  - 关键词
- 支持按对象类型、按优先级组织

### API

- 第一阶段 API 面向外部 AI Agent
- API 返回必须结构化
- 统一高层字段包括：
  - `summary`
  - `evidence`
  - `opportunities`
  - `risks`
  - `uncertainties`
  - `related_topics`
  - `watchlist_updates`
  - `meta`
- 后续网页问答也应优先复用这些结构化结果，而不是绕过本地知识库直接问外部 AI

### API 鉴权与配额

- 第一阶段使用单用户 API Key
- 保留后续升级空间
- 配额按 token 或返回条数控制

### 人工修订

- 第一阶段必须支持人工修订入口
- 人工结果优先于自动结果
- 需要保留审计记录
- 数据库不可用时，review API 允许降级到内存服务

### 技术选型

- 后端：`Python + FastAPI`
- 数据库：`PostgreSQL`
- 向量：`pgvector`
- 调度：`Celery` 或 `Prefect`
- 抓取：`RSS + requests`，必要时 `Playwright`
- 部署：`Docker Compose`
- 正式产品前端：轻量 Web 后台
- 外部 AI：provider-based，可配置 API Key / model / task routing

### 当前已落地的关键架构调整

- `api/deps.py` 已改为延迟创建数据库 session，避免导入期硬依赖数据库驱动
- review API 已支持优先数据库、失败时降级到内存服务
- `watchlist` API 已接到真实 `WatchlistService`
- 共享枚举已抽到 `src/domain/enums.py`
- 处理流水线骨架已补齐：
  - 清洗与去重
  - 双语摘要
  - 实体抽取
  - 主题归类
  - 冲突检测
  - 机会评分
  - 日报生成
- 应用层已补齐：
  - pipeline 输出到 domain model 的 mapper
  - 最小持久化服务
  - `run_document_pipeline(...)` 编排入口

### 当前验证状态

- 已通过：
  - `scripts/verify_models.py`
  - `scripts/verify_ingestion.py`
  - `scripts/verify_watchlist.py`
  - `scripts/verify_api.py`
  - `scripts/verify_review.py`
  - `scripts/verify_pipeline.py`
  - `scripts/verify_application_flow.py`
  - `scripts/verify_application_persistence_db.py`
- 其中：
  - `verify_application_flow.py` 已覆盖 memory 路径
  - `verify_application_persistence_db.py` 已覆盖真实 SQLAlchemy Session 路径
  - PostgreSQL 真环境已实证通过一次，不再只是 SQLite fallback 验证

---

## 4. 当前阶段结论与剩余问题

### 当前阶段结论：Application Persistence Reuse Stabilization 已完成

- `src/application/persistence.py` 已成为实体/主题复用的唯一入口
- Entity 复用键已按 `entity_type + name`
- Topic 复用键已按：
  - 优先 `name_en`
  - 若 `name_en` 为空则回退 `name_zh`
  - 统一 `strip().lower()`
- `DocumentEntity.entity_id` / `DocumentTopic.topic_id` 会回写为最终复用后的主记录 ID
- 同一文档内重复关联已在持久化前去重：
  - `DocumentEntity`: `(document_id, entity_id)`
  - `DocumentTopic`: `(document_id, topic_id)`
- MemorySession 与真实 SQLAlchemy Session 两条路径均已验证通过

### 本次阶段性实证结果

- `scripts/verify_application_flow.py` 已通过
- `scripts/verify_application_persistence_db.py` 已通过
- PostgreSQL 真环境已明确通过一次，输出为 `Database mode: PostgreSQL`
- 已确认无以下唯一约束冲突：
  - `uq_entities_type_name`
  - `uq_doc_entities_doc_entity`
  - `uq_doc_topics_doc_topic`
- DB 验证脚本已支持重复运行

### DB 验证脚本当前已具备的能力

- 为每次运行生成唯一 `run_id`
- 测试文档 `title/url` 使用 run-scoped 值，避免撞历史数据
- 对处理结果中的 entity/topic link 增加非空前置断言，避免直接下标报错
- PostgreSQL 路径下会精确清理本次 run 创建的测试数据
- 额外补上了本次 run 新建 `Entity` / `Topic` 主记录的回收逻辑
- 清理策略仅按本次 run 记录的 ID 精确删除，不按 name 宽删

### 本地 PostgreSQL 验证前置条件

- `src/config.py` 读取以下环境变量：
  - `DB_HOST`
  - `DB_PORT`
  - `DB_NAME`
  - `DB_USER`
  - `DB_PASSWORD`
- 当前本地验证依赖：
  - PostgreSQL 可连接
  - `psycopg2` 可用
  - `daily_news` 数据库存在
  - `pgvector` 已安装并已执行 `CREATE EXTENSION vector`
- 若密码错误或扩展未安装，`verify_application_persistence_db.py` 会回退 SQLite

### 当前剩余问题

- 当前阶段主问题已收尾，不再继续扩散修改 persistence
- 本节属于较早阶段结论，后续真实进展以第 6 节“最新阶段增量说明”为准
- 其中以下事项已在后续阶段完成：
  - application pipeline 最小批处理入口
  - application pipeline 最小 API 入口
  - 最小 URL 外部输入链路
  - baseline maintenance 与单候选试跑闭环
- 当前真正未收尾的事项已不再是“搭入口”，而是：
  - 继续执行 observation-oriented maintenance
  - 对 `what-openai-did` 再观察一个 cycle
  - 在不改架构的前提下决定其是否进入更明确的 promotion 讨论

---

## 5. 当前阶段状态与下一步

### 当前阶段结论：最小人工喂数基线建立完成

这一小阶段已经完成，可以明确视为 `Manual Feeding Workflow Baseline Established`。

本阶段已经完成的闭环包括：
- 最小 URL 列表批量导入可用
- seed 目录组织方式落地
- 操作员约定与工作流文档补齐
- 首次真实人工喂数 trial 已完成
- seed 分类清理已完成
- 极小扩容 maintenance trial 已完成
- baseline 状态已记录，不再只是口头约定

### 新增产品方向结论：正式使用形态已明确

当前已新增明确的产品方向约束，后续新会话不应再默认把项目理解为“终端优先工具”，而应理解为“网页优先、本地存储优先、外部 AI 可配置”的本地知识工作台。

已确认的正式产品形态：
- 正式使用时以网页为主入口
- 用户可在网页中配置资料来源
- 用户可在网页中配置外部 AI Provider 与 API Key
- 外部 AI 用于分析、摘要、问答等任务，但知识资产保留在本地
- 终端入口继续保留，但主要用于维护、验证、批处理与运维

网页版 MVP 最小页面范围：
- Dashboard
- Sources
- Documents / Knowledge
- Review
- Watchlist
- Ask / Q&A
- AI Settings
- System / Storage

网页版 MVP 的核心能力要求：
- 网页中配置来源
- 网页中配置外部 AI Provider
- 浏览已处理知识结果
- 支持人工修订
- 支持基于本地知识库的问答
- 本地保存数据、配置与人工修订结果

网页版 MVP 明确非目标：
- 当前不要求多人协作
- 当前不要求复杂权限系统
- 当前不要求自动发现来源或通用爬虫能力
- 当前不要求复杂前端交互与完整运维后台

### 当前 formal seed baseline

当前 formal seed 已固定为下一轮 maintenance cycle 的 baseline set：
- `https://simonwillison.net/2024/May/29/training-not-chatting/`
- `https://simonwillison.net/2024/Dec/31/llms-in-2024/`
- `https://www.anthropic.com/news/claude-3-5-sonnet`
- `https://www.anthropic.com/news/announcing-our-updated-responsible-scaling-policy`

相关记录文件：
- `scripts/real_seed_sources/BASELINE_SEED_STATUS.md`
- `scripts/real_seed_sources/SEED_MAINTENANCE_NOTE.md`

### 当前 deferred candidates

以下候选继续保持 deferred，不在当前阶段自动纳入 formal seed：
- `https://www.oneusefulthing.org/p/what-openai-did`
- `https://www.anthropic.com/news/a-new-initiative-for-developing-third-party-model-evaluations/`

### 当前明确不再成立的旧判断

- OpenAI `https://openai.com/index/hello-gpt-4o/` 不再归类为 `known failure`
- 但当前也没有被提升为 formal seed
- 该 URL 如需重新纳入，应在后续 maintenance cycle 中重新观察，而不是基于单次成功直接升级

### 下一轮 maintenance cycle 的起点

下一轮不要从“继续建入口”或“继续扩抓取能力”起手，而应从 baseline maintenance 起手：

1. 先原样复跑当前 formal seed baseline
2. 判断 baseline 是否继续稳定
3. 只有在 baseline 再稳定通过一个 cycle 之后，再考虑 deferred candidates

### 当前阶段不应再做的事

- 不要重新开启 CLI / API 最小入口建设
- 不要重新讨论“要不要做单 URL 导入”或“要不要做目录 seed”
- 不要继续扩种子列表，只因为最近几轮 trial 成功
- 不要把 seed 维护扩展成 source registry / 平台化来源管理
- 不要扩展抓取器到 Playwright、403 绕过、JS 渲染抓取
- 不要重构 `orchestrator` / `persistence` / `processing` / `domain`

---

## 6. 最新阶段增量说明（供新会话优先对齐）

本节是当前真实状态的最新增量上下文。新会话应优先以本节为主，不要回到已经完成的旧阶段任务。

### 已完成阶段 A：Application Persistence Reuse Stabilization

这一阶段已经完成，不要重新开启，除非出现明确回归。

已确认事实：
- `src/application/persistence.py` 已是 entity/topic 复用唯一入口
- Entity 复用键：`entity_type + name`
- Topic 复用键：
  - 优先 `name_en`
  - 若 `name_en` 为空则回退 `name_zh`
  - 统一使用 `strip().lower()`
- `DocumentEntity.entity_id` / `DocumentTopic.topic_id` 会回写为最终复用后的主记录 ID
- 同一文档内重复关联已在持久化前去重：
  - `DocumentEntity`: `(document_id, entity_id)`
  - `DocumentTopic`: `(document_id, topic_id)`
- 以下两条路径都已验证通过：
  - `MemorySession`
  - 真实 SQLAlchemy `Session`

### 已完成阶段 B：最小批处理 CLI 入口

这一阶段已经完成。

关键事实：
- `scripts/run_application_batch.py` 是当前最小 CLI 入口
- 支持 JSON 文件、`--url` 单 URL、`--url-list`
- 直接复用 `DocumentPipelineOrchestrator.run_document_pipeline(...)`
- 输出保持最小结构化结果
- 事务语义保持 `per_document`

### 已完成阶段 C：最小 API 入口

这一阶段已经完成。

关键事实：
- `POST /api/v1/application/pipeline/run` 可直接触发 application orchestrator
- route 只做薄编排，不复制 persistence 逻辑
- `persist=false` 不建 DB session，`persist=true` 复用 `src/api/deps.py`
- 成功/错误路径都已验证过

### 已完成阶段 D：真实 PostgreSQL + pgvector 验证闭环

这一阶段已经完成。

关键事实：
- `verify_application_persistence_db.py` 已去掉 SQLite fallback
- `verify_application_api.py` 已去掉 `persist=true` skip
- PostgreSQL 与 `pgvector` 在真实环境下已验证通过
- 当前不要再把“环境验证闭环”当主线任务

### 已完成阶段 E：最小 URL 外部输入链路

这一阶段已经完成。

关键事实：
- `src/ingestion/url_importer.py` 已支持最薄单页 HTML 导入
- `scripts/run_application_batch.py` 已支持 `--url` 与 `--url-list`
- `--url-list` 现已支持：
  - 单文件 `.txt`
  - 单文件 `.json`
  - seed 目录输入
- 目录模式只是一层薄的输入组织约定，不是 source registry
- 目录内按文件名排序加载，URL 去重规则为 `first occurrence wins`

### 已完成阶段 F：人工喂数工作流收口与 baseline 建立

这一阶段是当前最新完成的小阶段，新会话应优先对齐这里。

已完成事实：
- `docs/application_url_batch_workflow.md` 已补齐操作员使用约定
- `scripts/real_seed_sources/` 已形成真实人工喂数目录
- 首次真实 manual feeding trial 已在可联网环境完成
- 后续极小扩容 maintenance trial 也已完成
- 当前 formal seed baseline 已记录在：
  - `scripts/real_seed_sources/BASELINE_SEED_STATUS.md`
- 当前 seed 分类修正与维护说明已记录在：
  - `scripts/real_seed_sources/SEED_MAINTENANCE_NOTE.md`

当前 formal seed baseline：
- `https://simonwillison.net/2024/May/29/training-not-chatting/`
- `https://simonwillison.net/2024/Dec/31/llms-in-2024/`
- `https://www.anthropic.com/news/claude-3-5-sonnet`
- `https://www.anthropic.com/news/announcing-our-updated-responsible-scaling-policy`

当前 deferred candidates：
- `https://www.oneusefulthing.org/p/what-openai-did`
- `https://www.anthropic.com/news/a-new-initiative-for-developing-third-party-model-evaluations/`

已明确不要误判：
- OpenAI `hello-gpt-4o` 当前不再视为 `known failure`
- 但当前也不是 formal seed
- 当前阶段结论不是“继续扩种子”，而是“baseline 已建立”

### 已完成阶段 G：baseline maintenance 复跑与单候选试跑评审

这是在 baseline 建立之后新增完成的最新进度，新会话应优先参考这里判断下一步，而不是回到“是否继续搭入口”。

已完成事实：
- 2026-04-21 已完成一次 formal seed baseline maintenance rerun
- baseline 复跑命令继续复用现有薄入口：
  - `.\.venv\Scripts\python.exe scripts\run_application_batch.py --url-list scripts\real_seed_sources --no-persist`
- 受限环境下曾出现一次网络型 transient failure（WinError 10013），已确认不是代码回归
- 在可联网环境下原样复跑通过，结果为 `total=4, succeeded=4, failed=0`
- 已确认当前 workflow 稳定，且当前阶段不需要实现层修复
- `scripts/real_seed_sources/BASELINE_SEED_STATUS.md` 已更新为 2026-04-21 的 baseline rerun 记录

单候选极小扩容 trial：
- trial candidate：`https://www.oneusefulthing.org/p/what-openai-did`
- 本轮 trial 只新增了一个试跑输入文件：
  - `scripts/real_seed_sources/trial_oneusefulthing_minimal.txt`
- trial 复用命令：
  - `.\.venv\Scripts\python.exe scripts\run_application_batch.py --url-list scripts\real_seed_sources\trial_oneusefulthing_minimal.txt --no-persist`
- 试跑结果为 `total=5, succeeded=5, failed=0`
- 该 candidate 在当前 thin HTML importer 边界内可运行，没有破坏 baseline 稳定性
- trial 记录已写入：
  - `scripts/real_seed_sources/SEED_MAINTENANCE_NOTE.md`

对 `what-openai-did` 的人工结果评审结论：
- 当前结论不是 formal seed promotion
- 当前结论也不再是“仅仅 keep deferred、没有观察价值”
- 当前正式判断应视为：
  - `eligible for future promotion after another cycle`
- 该 candidate 已证明：
  - 能稳定落入项目关心的 AI 主题范围
  - 能产出至少一个具备跟踪价值的 opportunity draft
  - 能产出可供人工继续判断的 open question
  - 能提供对下游 agent 有基础价值的 topics / entities
- 当前主要质量问题：
  - 实体抽取存在明显噪声，例如 `But`
  - opportunity 输出可用但偏模板化
  - risk 信号偏弱
  - related_topics 略显宽泛，个别主题相关性偏弱
- 因此，这条 candidate 的状态应理解为：
  - 已从“仅能跑通的 deferred candidate”提升为“可进入未来 promotion 观察区间”
  - 但尚未达到“可直接纳入 formal seed”标准

下一轮 maintenance decision 的正确焦点：
- 继续只观察 `what-openai-did`
- 不要在下一轮同时推进第二个 deferred candidate
- 重点复核三类信号：
  - 实体噪声是否仍明显存在，尤其是 `But` 这类低质量项
  - `opportunities / risks / open questions` 是否仍有基本可读性与判断价值
  - `related_topics` 是否继续稳定落在项目关心的 AI 主题范围内
- 只有在再观察一个 cycle 后仍稳定，才进入更明确的 promotion 讨论

### 已完成阶段 H：网页版 MVP 主链最小落地与回归收口

这一阶段已经完成，当前不应再把网页版理解为“仅有目标、尚未实施”。后续新会话如果进入网页产品主线，应把当前状态理解为：最小 Web MVP 已落地，并已完成一轮主链回归收口。

已确认事实：
- FastAPI 内已接入服务端渲染的 Web MVP 页面
- 当前 8 个已同意的 MVP 页面均已存在并可访问：
  - Dashboard
  - Sources
  - Documents / Knowledge
  - Review
  - Watchlist
  - Ask / Q&A
  - AI Settings
  - System / Storage
- Web 层未重构 `orchestrator` / `persistence` / `processing` / `domain`
- Web 层继续复用现有 application pipeline、review service 与本地存储边界

当前网页版 MVP 范围：
- Dashboard：查看最近处理结果、日报、机会、风险与系统状态
- Sources：管理资料来源
- Documents / Knowledge：浏览结构化知识结果
- Review：人工修订自动结果
- Watchlist：管理关注对象
- Ask / Q&A：基于本地知识库提问，再调用外部 AI 生成回答
- AI Settings：配置 provider、API Key、模型与任务用途
- System / Storage：查看本地存储状态与基础系统信息

该阶段已经实际落地并验证的最小闭环包括：
- Sources
  - 可创建 source
  - 可编辑 source
  - 可启停 source
  - 可执行 import now
  - `maintenance_status / notes / last_import_at / last_result` 当前作为 `Source.config["_web"]` 元数据承载
  - `formal_seed` 在普通 Web 编辑中保持“可见但不可直接编辑/提升”的语义
- Documents / Knowledge
  - 可浏览文档列表与详情
  - 可查看 source 关联、summary、key points、entities、topics 与正文预览
- Review
  - 当前最小审核闭环已覆盖 `summary_zh / summary_en / key_points`
  - review edits 可真实写入并保留审计记录
- AI Settings
  - 当前 provider 配置为本地优先
  - 已支持最小 provider 对象：`name / provider_type / base_url / api_key / model / is_enabled / is_default / supported_tasks / notes / last_test_status / last_test_message`
  - 当前 `provider_type` 仅支持 `openai_compatible`
  - 已支持 provider detail/edit 与最小 test provider 动作
  - provider 仍保存在本地 JSON，中短期不视为回归问题
  - provider detail 页不再回显明文 API key
- Ask / Q&A
  - 当前已形成 `local retrieval first` 的最小问答链路
  - Ask provider 选择已按 `enabled + supports qa` 收敛
  - Ask 结果当前已明确区分：
    - `local_only`
    - `local_with_external_reasoning`
    - `local_fallback`
    - `insufficient_local_evidence`
  - 外部 AI 只能消费“问题 + 已选本地证据”，不应裸转发用户问题
  - Ask 检索当前已做最小稳定化：
    - query token 去重
    - 小型 stopword 过滤
    - 相关性优先、时间次之排序
    - 证据数量与候选检查数量有上限
    - 用户可见证据优先采用本地 summary / key points
  - Ask 当前仍不是向量检索，也不是 advanced RAG
- Dashboard / System
  - 已能展示近期文档、topic、provider、Q&A 历史与基础系统状态

该阶段已完成的回归收口结论：
- 当前 Web MVP 主链已完成一轮正式回归，未发现新的明确回归
- 已验证的主链包括：
  - Sources -> Import -> Documents -> Review -> Ask
  - AI Settings -> provider test -> Ask provider selection
- Ask 自动化测试当前已通过，回归结论可视为：
  - `Web MVP baseline stable`

当前 Web MVP 可以真实宣称：
- 提供本地优先的个人知识工作台网页入口
- 支持 Sources、Documents、Review、Watchlist、Ask、AI Settings、System 基本链路
- Ask 会先做本地检索，再按条件选择是否使用外部 AI 做受限推理
- 人工 review 后的本地字段优先于低信任自动结果
- AI provider 可本地配置、测试，并按 task 能力用于 Ask

当前 Web MVP 仍不能真实宣称：
- 先进语义检索或向量 RAG
- 自主研究 / 多跳推理系统
- 安全级别较高的 secrets 管理
- 外部 AI 作为知识源的开放式问答
- 完整生产级数据治理或爬取平台

### 已完成阶段 I：Review 结构化审核闭环扩展

这一阶段已经完成，后续不应再把 Review 理解为“只支持 summary 的最小审核”。当前应理解为：Review 已经覆盖三类结构化判断输出，并保持统一的“自动只读 + review_edits 人工覆盖 + reset to auto + 原子提交”模式。

已确认事实：
- `opportunities` 人工审核闭环已落地：
  - review target：单条 `OpportunityAssessment`
  - 自动结果继续只读
  - 人工修订仅写入 `review_edits`
  - 页面读取时通过 `DatabaseReviewService.get_effective_value(...)` 覆盖显示
  - 已支持 `reset to auto`
  - 已修复单次提交原子性
- `risks` 人工审核闭环已落地：
  - 自动来源：`DailyBrief.risks`
  - review target：单条 risk item
  - 未新建独立 risk 表，也未绑定 `Conflict`
  - 已形成 `item_id / route_id / target_id` 三层标识：
    - `item_id` 为内部稳定标识
    - `route_id` 为对外 Web 安全路由标识，直接使用派生后的 `target_id` UUID 字符串
    - `target_id` 为 `uuid5(brief_id + ":risk:" + item_id)`
  - 对同一 brief 内内容相同的重复 risk，已通过“基础标识 + 出现序号”拆分为不同 target
  - 当前开放审核字段仅：
    - `severity`
    - `description`
- `uncertainties` 人工审核闭环已落地：
  - 自动来源：`DailyBrief.uncertainties`
  - review target：单条 uncertainty item
  - 未新建独立 uncertainty 表，也未绑定 `Conflict`
  - 标识策略沿用 `risks`：
    - `base_item_id` 基于 uncertainty 字符串确定性生成
    - 同一 brief 内重复项追加 occurrence index
    - `target_id = uuid5(brief_id + ":uncertainty:" + item_id)`
    - `route_id = str(target_id)`
  - 当前开放审核字段仅：
    - `uncertainty_note`
    - `uncertainty_status`
- 当前 Review 页面已可同时展示并提交：
  - `Uncertainty Review`
  - `Risk Review`
  - `Opportunity Review`
  - `Summary Review`
- review 相关自动化验证已扩展覆盖：
  - 自动值 + 人工覆盖显示
  - reset to auto
  - 重复项 distinct target
  - 页面渲染
  - 页面 POST 提交
  - `DatabaseReviewService.create_batch(...)` 原子性

当前明确残留问题：
- `DailyBrief.uncertainties` 的自动源当前仍是 `list[str]`，因此 `uncertainty_status` 没有天然自动值。
- 之前 Review 页面在 `uncertainty_status=None` 时会因为浏览器默认行为隐式提交 `open`；这个问题已经修复：
  - 页面现在使用显式占位值，未选择状态时不会写入人工覆盖
  - 只有用户显式选择 `open / watching / resolved` 时才会写入 `review_edits.uncertainty_status`
  - 已补 service 层与 route 层回归测试，覆盖占位值保留与“只改 note 不误写 status”两段链路
- 因此当前网页产品主线不再需要把这个问题作为最高优先级；后续应转向 Ask 结果展示优化与已有能力收口。

### 已完成阶段 J：Ask reviewed evidence 优先消费

这一阶段已经完成，当前不应再把 Ask 理解为“只能消费 document summary / key points”。当前应理解为：Ask 仍保持 `local retrieval first` 的最小边界，但已开始优先消费 Review 之后的高信任结构化结果。

已确认事实：
- `WebMvpService.ask_question()` 已接入 reviewed 优先消费逻辑
- Ask 当前本地 evidence 组装分为两段：
  - `search_documents_for_question()`
  - `search_briefs_for_question()`
- document evidence：
  - 仍以 `Document` 为基础
  - 已在 `_build_evidence_from_documents()` 中附加 reviewed `OpportunityAssessment`
- brief evidence：
  - 已新增 `DailyBrief` 维度
  - 已在 `_build_evidence_from_briefs()` 中组装 reviewed `risks / uncertainties`
- reviewed 读取继续复用 `DatabaseReviewService.get_effective_value(...)`
- Ask 当前已优先覆盖以下 reviewed 字段：
  - opportunities：
    - `status`
    - `priority_score`
    - `total_score`
    - `uncertainty`
    - `uncertainty_reason`
  - risks：
    - `severity`
    - `description`
  - uncertainties：
    - `uncertainty_note`
    - `uncertainty_status`
- 无人工值时会自动回退到自动值；`reset to auto` 继续通过现有 review 机制生效
- Ask 结果页已做最小兼容调整：
  - document evidence 继续保留文档链接
  - brief evidence 不再强依赖 `document_id`，可直接文本展示

当前明确边界：
- Ask 仍然不是 advanced RAG
- brief 检索仍是当前的 term matching，不是向量检索
- 如果问题只命中人工修订值、但完全不命中自动文本，当前仍可能检索不到对应 brief/document
- `DailyBrief.opportunities` 当前尚未纳入 Ask；当前接入的是 `OpportunityAssessment + OpportunityEvidence.document` 这条链

### 当前真实稳定边界

截至当前阶段，以下边界已经形成并应继续保持：
- `src/application/orchestrator.py` 是 application pipeline 正确编排入口
- `src/application/persistence.py` 是 entity/topic 复用唯一入口
- CLI 和 API 都必须直接复用 orchestrator
- CLI 和 API 都只应作为薄入口层
- URL importer 的定位仍是“最薄 HTML 导入器”，不是通用爬虫
- `--url-list` 的目录模式是输入组织方式，不是新 ingestion 主路径
- 批处理继续保持 `per_document` 语义
- 当前 formal seed 已可作为 baseline set 周期性复跑
- Web 层当前主要落在：
  - `src/web/service.py`
  - `src/api/routes/web.py`
- Review 当前已稳定覆盖四类页面审核对象：
  - summary
  - opportunities
  - risks
  - uncertainties
- `opportunities / risks / uncertainties` 当前统一遵循：
  - 自动结果只读
  - 人工修订只写 `review_edits`
  - 读取时通过 `get_effective_value(...)` 覆盖显示
  - 支持 `reset to auto`
  - 单次批量提交保持原子性
- Ask history 当前已是 `DB-first + JSON fallback`
- AI provider config 当前已是 `DB-first + JSON fallback`
- 两者都保留旧 JSON 兼容兜底，但不会自动把旧 JSON 导入 DB
- `Source.config["_web"]` 当前承担 Web 维护元数据承载职责；这在当前 MVP 中可接受，不应为了字段“更漂亮”而立即重构 domain/schema
- Ask 当前已在现有 `local retrieval first + bounded evidence + optional external reasoning` 边界内优先消费 reviewed `opportunities / risks / uncertainties`

### 当前通常不应再动的区域

除非出现明确回归或新的明确需求，否则不要优先修改：
- `src/application/persistence.py`
- `src/application/orchestrator.py`
- `src/domain/*`
- `src/processing/*`
- 已稳定的 CLI / API 主路径
- 当前 `url_importer` 的能力边界
- 已形成的 seed 目录工作流结构
- 当前 Ask 的“local retrieval first + bounded evidence + optional external reasoning”边界本身
- 当前 Sources 中 `formal_seed` 的普通 Web 只读语义

不要重复做：
- 不要再回头收尾 environment validation
- 不要再重构 entity/topic 复用逻辑
- 不要再重新建设最小 CLI / API 入口
- 不要因为成功几轮 trial 就扩成来源管理平台
- 不要引入 `Playwright`
- 不要扩成通用爬虫系统

### 新会话建议优先阅读

新会话开始后，建议优先阅读这些文件：
- `ARCH_CONTEXT.md`
- `docs/application_url_batch_workflow.md`
- `scripts/real_seed_sources/BASELINE_SEED_STATUS.md`
- `scripts/real_seed_sources/SEED_MAINTENANCE_NOTE.md`
- `src/web/service.py`
- `src/api/routes/web.py`
- `scripts/run_application_batch.py`
- `src/ingestion/url_importer.py`
- `src/application/orchestrator.py`
- `src/application/persistence.py`

如果需要补充验证上下文，再读：
- `scripts/verify_application_persistence_db.py`
- `scripts/verify_application_api.py`
- `scripts/verify_application_url_import.py`
- `scripts/verify_application_url_list_import.py`

### 下个会话最合理的工作起点

下个会话不应再从“搭工作流”起手，也不应直接写代码；当前最合理的起点有两条，取决于会话目标：

- 如果继续沿当前内容维护主线推进：基于 2026-04-29 的 latest maintenance 结论，准备下一轮 observation-oriented maintenance
- 如果继续沿当前网页产品主线推进：不要再回到信息架构空谈；Review 的最小结构化审核能力、Ask reviewed evidence 优先消费、Ask history DB-first 收口、AI provider config DB-first 收口、Ask 最小展示收口、Review / Ask 共享展示术语统一都已落地。当前最合理的下一步应是新的小型页面质量任务，而不是继续做 Ask 展示收口或新的周边存储迁移。

推荐起手顺序：
1. 先确认当前是走“内容维护主线”还是“网页版 MVP 规划主线”
2. 如果走内容维护主线：
   - 确认当前 formal seed baseline 与 deferred 列表
   - 明确 `what-openai-did` 当前状态仍是 `deferred`，且可在后续 cycle 中继续观察
   - 下一轮 maintenance 中继续复跑 baseline，并只额外观察这一条 candidate
3. 如果走网页版 MVP 主线：
   - 先把当前状态视为 `Web MVP baseline stable`
   - 不要重新讨论页面清单、Sources/AI Settings/Ask 的大方向设计
   - 当前 `uncertainty_status` 默认提交语义问题已修复，不要重复开工
   - 当前 Ask history 与 AI provider config 都已完成 `DB-first + JSON fallback` 收口，不要再把它们当成未完成主线
   - 当前 `/web/ask` 展示层最小收口已完成，不要重开 Ask metadata / evidence / empty state 统一任务
   - 当前 `/web/review` 与 `/web/ask` 的共享展示术语已统一，不要再把 wording 收口当默认下一步
   - 下一步优先级应为：
     - 在现有稳定基线之上选择新的小型页面质量任务
     - 或回到内容维护主线继续 baseline maintenance
4. 无论走哪条主线，都不要擅自扩展抓取器能力或重构稳定主链路

### 给下个会话的明确提示词

可以直接把下面这段作为下个对话的起手提示：

> 先阅读 `ARCH_CONTEXT.md`、`docs/application_url_batch_workflow.md`、`scripts/real_seed_sources/BASELINE_SEED_STATUS.md`、`scripts/real_seed_sources/SEED_MAINTENANCE_NOTE.md`。  
> 当前项目已经明确两条主线：内容维护主线，以及网页版 MVP 主线。  
> 如果当前目标是内容维护：不要重新讨论 CLI/API 最小入口、URL 导入器、seed 目录结构或环境验证闭环；继续围绕 baseline maintenance 与 `what-openai-did` 的 observation-oriented maintenance 推进。  
> 如果当前目标是网页产品主线：当前应把项目理解为“Web MVP baseline stable + Review 结构化审核已扩到 opportunities/risks/uncertainties + Ask 已开始优先消费 reviewed evidence + Ask history / AI provider config 已完成 DB-first 收口 + `/web/ask` 展示层最小收口已完成 + `/web/review` 与 `/web/ask` 共享展示术语已统一”。不要再回到信息架构空谈，也不要重开 Sources / AI Settings / Ask 的大方向设计；优先选择新的小型页面质量任务，而不是重复做 Ask 展示收口、存储收口或 `uncertainty_status` 修复。  
> 无论哪条主线，除非暴露明确回归，否则都不要修改 `orchestrator`、`persistence`、`processing`、`domain`、CLI/API 主路径，也不要扩展抓取器能力。
### 最小本地存储改造方案（不动主知识存储）

这个方向在当前阶段已经完成前两步，可作为历史记录保留；后续不要把它重新当作下一步默认主线。它的性质一直是“补充型本地存储收口”，不是“替换主知识存储”。

已完成：

1. Phase 1：Ask history JSON -> local DB
2. Phase 2：AI provider config JSON -> local DB

两者当前都采用：

- `DB-first`
- `JSON fallback`
- old JSON tolerated but not auto-imported

后续会话如果继续接这个方向，应先固定边界：
- 不动 `src/application/orchestrator.py`
- 不动 `src/application/persistence.py`
- 不动 `src/domain/*`
- 不动 `src/processing/*`
- 不替换当前 PostgreSQL + pgvector 主知识存储路径
- 不引入新的“可插拔主知识引擎”或跨语言存储内核

当前要解决的不是“主数据库不够用”，而是 Web MVP 周边本地存储还比较分散，存在一些 MVP 时期的 JSON/临时元数据承载方式。它们当前可用，但不利于后续：
- 历史记录查询
- 回归验证一致性
- 页面级本地审计
- 存储边界清晰化

当前已识别的周边本地存储对象：
- `configs/web/qa_history.json`
  - 当前是 Ask history 的本地 JSON 存储
  - 这是最适合先收口到 local DB 的目标，因为它独立、低风险、不牵动主知识模型
- `configs/web/ai_settings.json`
  - 当前是 AI provider config 的本地 JSON 存储
  - 当前 MVP 可接受，但不应长期作为唯一正式配置存储边界
- `Source.config["_web"]`
  - 当前承担 Sources 页面 maintenance metadata 承载职责
  - 当前继续保留，不作为优先改造目标
- 原始资产 / 快照 / 附件存储
  - 当前还没有正式抽象边界
  - 后续如需要支持 HTML snapshot / PDF / image / raw asset，可单独定义最小 local asset storage 边界

历史上的推荐顺序与当前状态：

1. Phase 1：Ask history JSON -> local DB
- 目标：把 Ask history 从零散文件收口到更稳定的本地持久化
- 只动 Ask history，不动 document / summary / entity / topic / review 主知识对象
- 最小承载字段可包括：
  - `question`
  - `answer`
  - `answer_mode`
  - `provider_name`
  - `evidence`
  - `error`
  - `note`
  - `created_at`
- 这一步的价值在于：
  - 更稳定的历史查询
  - 更明确的本地审计
  - 更容易做 Ask 页面历史展示和回归验证

当前状态：已完成并已通过测试、migration 与页面链路验证。

2. Phase 2：AI provider config JSON -> local DB
- 目标：把 provider 配置从本地 JSON 收口到本地配置存储
- 仍保持：
  - local-first
  - single-user
  - provider-based
  - external AI as compute only
- 这一阶段只改配置存储边界，不顺便重做：
  - provider routing
  - Ask flow
  - 外部 AI 调用策略
- API key 在当前阶段仍可接受“本地存储 + 基本 UI 遮罩/不回显明文”的处理，不要把它升级成复杂 secrets-management 项目

当前状态：已完成并已通过测试、migration 与页面链路验证。

3. Phase 3：定义最小 local asset storage 边界（可先只写 design note）
- 目标：为后续可能引入的原文快照、PDF、图片、原始 HTML、原始资产保留做边界准备
- 推荐只定义最小接口，例如：
  - `save_asset(...)`
  - `read_asset(...)`
  - `delete_asset(...)`
  - `exists_asset(...)`
- 第一阶段只考虑 `local` backend
- 不要现在就做 S3 / Supabase / 多后端平台化

当前明确非目标：
- 不要替换主知识存储
- 不要引入新的主知识引擎抽象层
- 不要把类似 `gbrain` 的 `page / compiled_truth / timeline` 数据模型迁入 `daily_news`
- 不要为了存储“更漂亮”而动 `orchestrator` / `persistence` / `domain`
- 不要现在强行把 `Source.config["_web"]` 升级为正式 schema 列

如果后续会话要继续这个方向，最合理的理解是：
1. Phase 1 与 Phase 2 已完成，不要重复开工
2. 当前没有必须立即启动的 Phase 3
3. 只有在明确要支持 raw assets / snapshots 时，才单独定义最小 local asset storage 边界

给下一个接手 AI 的执行提示：
> 当前“本地存储改造”只针对 Web 周边本地存储，不针对核心知识存储。  
> `configs/web/qa_history.json` 与 `configs/web/ai_settings.json` 的 DB-first 收口都已完成，不要重复把它们当作下一步主线。  
> `Source.config["_web"]` 当前继续保留，不是优先改造目标。  
> 不要把这个任务扩成“替换主存储模式”或“引入新的主知识引擎”。  
> 如未来要支持 HTML snapshot / PDF / image / raw asset，再单独定义最小 local asset storage 边界。  
> 如果继续沿网页产品主线推进，优先阅读 `docs/ask_result_display_optimization.md`，从 Ask 页面结果展示优化起手。

---

## 7. Latest Progress Addendum (2026-04-28)

This addendum overrides older notes that still describe Ask result display optimization or summary review alignment as unfinished.

### Completed in this round

- Ask result display optimization was completed and accepted.
- The `/web/ask` page contract was documented and stabilized.
- Ask reviewed-evidence verification now explicitly covers:
  - `opportunities`
  - `risks`
  - `uncertainties`
  - auto value -> manual override -> `reset to auto`
- `summary` is now formally aligned with the same review override model:
  - automatic value stays read-only
  - manual edits write only to `review_edits`
  - `reset to auto` is supported
  - Review UI shows auto/effective comparison
  - Ask document evidence consumes effective `summary` / `key_points`

### Updated stable understanding

At the current stage, the Web MVP should be understood as:

- `Web MVP baseline stable`
- Ask display optimization is no longer the active unfinished gap
- Ask history is already `DB-first + JSON fallback`
- AI provider config is already `DB-first + JSON fallback`
- Review and Ask now share a mostly unified manual-correction loop across:
  - `summary`
  - `opportunities`
  - `risks`
  - `uncertainties`

### Important boundary that remains

- Do not retroactively repair historical `summary` rows that were directly overwritten in older flows.
- Current `reset to auto` for summary means “return to the current persisted summary baseline”.
- Do not reopen as default next tasks:
  - Ask display optimization
  - Ask history DB migration
  - AI provider config DB migration
  - summary review alignment

### Updated next-session starting point

The next session should no longer start from “finish Ask display” or “align summary review semantics”.

Use this rule instead:

1. If the goal is content maintenance:
   - continue `baseline maintenance`
   - re-check formal seed baseline
   - observe deferred candidates such as `what-openai-did`
2. If the goal is Web/product iteration:
   - treat Review + Ask core manual-correction semantics as already established
   - prioritize quality/efficiency work on top of the existing baseline
   - do not restart information-architecture debates for Ask / Review / AI Settings

### Direct handoff prompt for the next AI

> Read `ARCH_CONTEXT.md` first.
> Current project status is no longer “finish Ask display optimization” or “align summary review”.
> The accurate understanding is:
> `Web MVP baseline stable + Ask display accepted + Ask contract stabilized + review-to-Ask effective-value loop validated + summary/opportunities/risks/uncertainties all aligned to the same review override model`.
>
> Do not reopen Ask display optimization, Ask history DB migration, AI provider config DB migration, or summary review alignment as the default next step.
> If the session goal is content maintenance, continue baseline maintenance.
> If the session goal is Web/product iteration, start from the next highest-value quality/efficiency task on top of the already-stable Review/Ask baseline.

## 8. Latest Progress Addendum (2026-04-29)

This addendum overrides older notes that still treat the 2026-04-21 maintenance rerun or Ask/Review display-wording cleanup as unfinished.

### Completed in this round

- Formal seed baseline maintenance was rerun again on 2026-04-29.
- Under restricted local environment, the rerun first failed with `URLError: [WinError 10013]`.
- This failure was classified as environment/network restriction rather than application regression.
- In a network-enabled environment, the same baseline rerun succeeded with `4/4` items passed.
- `what-openai-did` was rerun as an observation-only candidate and succeeded, but remains `deferred`.
- `/web/ask` display-layer cleanup has been completed:
  - history/result metadata presentation is unified
  - evidence labels and empty-state wording are easier to scan
  - behavior remains unchanged
- `/web/review` and `/web/ask` now also share more consistent page-level wording:
  - `Effective Values`
  - `Review History`
  - aligned empty-state wording for reviewed objects

### Updated stable understanding

At the current stage, the project should now be understood as:

- `content maintenance baseline stable`
- `Web MVP baseline stable`
- formal baseline rerun is proven again as of 2026-04-29 in network-enabled environment
- `what-openai-did` is still observation-only and remains `deferred`
- Ask display optimization is complete
- Review / Ask shared display semantics have been further unified

### Important boundary that remains

- Do not misclassify `URLError: [WinError 10013]` in restricted local environment as a code regression by default.
- Do not promote `what-openai-did` to formal seed automatically from a single successful observation rerun.
- Do not reopen as default next tasks:
  - Ask display cleanup
  - Review / Ask wording cleanup
  - Ask history DB migration
  - AI provider config DB migration

### Updated next-session starting point

The next session should now start from one of these two paths:

1. If the goal is content maintenance:
   - continue baseline maintenance on the existing formal set
   - keep distinguishing environment-restricted failure from true source failure
   - continue observing `what-openai-did` without automatic promotion
2. If the goal is Web/product iteration:
   - treat Ask and Review display-semantics cleanup as already done
   - pick a new small page-quality task on top of the stable baseline
   - do not restart Ask display or Review wording cleanup as the default next step

## 9. Latest Progress Addendum (2026-04-29 Web MVP route-level smoke acceptance)

This addendum overrides older notes that still describe the Web MVP acceptance work as a broad end-to-end pass.

### Completed in this round

- The Web MVP acceptance layer was calibrated to be explicitly route-level and service-mocked.
- `tests/test_web_mvp_acceptance.py` now uses narrower smoke names and checks key content blocks plus redirect targets.
- `docs/web_mvp_acceptance_checklist.md` now states the acceptance boundary clearly:
  - route-level
  - service-mocked
  - not real browser automation
  - not real database integration
- The page-contract set is now consolidated into `docs/web_page_contract.md`.

### Updated stable understanding

At the current stage, the project should now be understood as:

- `content maintenance baseline stable`
- `Web MVP baseline stable`
- page-layer contracts are consolidated in `docs/web_page_contract.md`
- route-level smoke acceptance is calibrated and repeatable
- current Web smoke coverage verifies contract stability and primary flow closure, not live DB/browser integration

### Important boundary that remains

- Do not describe the current `web_mvp_acceptance` suite as full end-to-end browser verification.
- Do not reopen page wording cleanup or route-level smoke calibration as default next tasks.
- Do not treat mocked route acceptance as proof of production persistence behavior.

### Updated next-session starting point

The next session should no longer start from acceptance cleanup or page-contract cleanup as the default task.

Use this rule instead:

1. If the goal is content maintenance:
   - continue baseline maintenance
   - re-check formal seed baseline
   - observe deferred candidates such as `what-openai-did`
2. If the goal is Web/product iteration:
   - treat page contracts and route-level smoke acceptance as already established
   - pick the next highest-value small task on top of the stable baseline
   - if stronger confidence is needed, use a separate real integration or browser automation layer instead of expanding this smoke suite by default

## 10. Historical note: deferred Web task for bilingual UI switching

This section records the earlier point at which bilingual UI switching was still deferred. The current status is defined by Section 11 below.

### Task intent

- Add a stable Chinese / English UI switch for the Web MVP.
- Keep the scope on page-layer wording and navigation labels first.
- Do not turn this into a content translation system by default.

### Stable boundary

- UI text should be switchable between `zh` and `en`.
- Knowledge content should remain source-of-truth text unless a later task explicitly defines translation rules.
- Do not modify `src/application/*`, `src/domain/*`, or `src/processing/*` for the first pass.
- Prefer server-rendered page-layer i18n over a heavier frontend rewrite.

### Recommended next-session starting point

If the next session is Web/product iteration, the next reasonable task is:

- implement a page-layer bilingual switch for the Web MVP
- cover navigation, titles, buttons, empty states, degraded notes, and table headers
- preserve current page context while switching language
- keep content translation as a separate follow-up decision

## 11. Latest Progress Addendum (2026-04-30 Web page-layer bilingual baseline)

This addendum overrides older notes that still describe bilingual UI switching as unimplemented or only partially completed.

### Completed in this round

- A lightweight page-layer i18n baseline was implemented and completed for the Web MVP shell copy.
- New shared page-layer i18n helpers were added in `src/web/i18n.py`.
- The language rule is now explicitly:
  - URL `lang` parameter first
  - persisted cookie fallback
  - default `zh`
- Supported language values are currently limited to:
  - `zh`
  - `en`
- The persisted language preference currently uses cookie storage only:
  - `daily_news_lang`
- A Web i18n middleware was added in `src/api/app.py` to:
  - resolve the current page language once per request
  - inject page-layer i18n context into `request.state`
  - persist valid `lang` selections back to cookie
- Shared page layout wiring in `src/api/routes/web.py` now supports:
  - localized `<html lang=...>`
  - localized navigation labels
  - localized shared page subtitle
  - language switch links that preserve current path and query while overriding `lang`
- Key Web pages now use the shared page-layer i18n helper for major shell copy:
  - `Dashboard`
  - `Documents`
  - `Document Detail`
  - `Sources`
  - `Review`
  - `Ask`
  - `Watchlist`
  - `AI Settings`
  - `System`
- `Ask` page shell copy was explicitly completed in this round, including:
  - form title
  - placeholder
  - default provider label
  - ask button
  - retrieval note
  - status / question / answer / run details / error state
  - evidence / opportunities / risks / uncertainties / related topics / meta
  - back link
  - ask metadata labels
  - ask empty-state wording
- Ask evidence fallback shell copy is now localized:
  - untitled evidence fallback
  - missing snippet fallback
- `/web` entry redirect now explicitly targets `/web/dashboard?lang=...` and no longer relies on string replacement.
- Ask result status CSS class is now derived from raw `answer_mode`, not from localized status text.
- `t(...)` fallback semantics are now explicitly tested:
  - current language key first
  - default language key fallback second
  - identifiable marker fallback last
- Route-level Web smoke tests and page tests were updated for the new default Chinese shell copy and explicit English query behavior.
- Current local verification result for this round was:
  - `pytest -q`
  - `108 passed`

### Updated stable understanding

At the current stage, the project should now be understood as:

- `content maintenance baseline stable`
- `Web MVP baseline stable`
- page-layer bilingual switching baseline is now implemented for Web shell copy
- default Web UI language is `zh`
- explicit `?lang=en` switching is supported
- cookie-based language persistence is supported
- content translation is still intentionally out of scope
- `Ask` remains the reference page for the bilingual shell-copy pattern
- `Watchlist`, `AI Settings`, and `System` shell copy have been brought into the same baseline

### Important boundary that remains

- Do not reinterpret the current work as a full internationalization platform.
- Do not treat knowledge content, summaries, evidence snippets, review payloads, or source-of-truth domain text as auto-translated.
- Do not modify `src/application/*`, `src/domain/*`, or `src/processing/*` as part of the first-pass bilingual work unless a separate regression requires it.
- Do not reopen Ask display cleanup, Ask history DB migration, AI provider config DB migration, or Review/Ask wording cleanup as default next steps.
- Do not start content translation, locale management, or a heavier frontend/i18n platform without a separate explicit decision.

### Updated next-session starting point

The next session should now start from one of these two paths:

1. If the goal is content maintenance:
   - continue baseline maintenance
   - re-check formal seed baseline
   - continue observing deferred candidates such as `what-openai-did`
2. If the goal is Web/product iteration:
   - treat page-layer bilingual infrastructure as already established
   - do not restart language-resolution design debates
   - do not reopen Ask page shell-copy wiring or completed shell-copy cleanup as the default task
   - pick a new small page-quality task on top of the existing stable baseline

### Recommended next Web task

If the next session is Web/product iteration, the most reasonable next task is:

- choose a new focused Web page-quality task rather than continuing localization cleanup by default
- candidate directions:
  - improve one page's scanability or density
  - add a small route-level smoke check only if it protects an existing contract
  - document a page contract gap before implementation
- keep evidence bodies, summaries, and other knowledge content un-translated
- keep route-level smoke acceptance aligned with:
  - default `zh`
  - explicit `?lang=en`
  - cookie fallback behavior

## 12. Latest Progress Addendum (2026-04-30 Web page quality pass)

This addendum overrides older notes that still treat Documents, Dashboard, or System page scanability as unfinished default Web tasks.

### Completed in this round

- Documents / Knowledge page scanability optimization is complete.
  - The list view now surfaces title, source, status, language, published/created time, summary preview, lightweight structured signals, and a detail link.
  - `?lang=en` switches shell copy to English while leaving knowledge content, summaries, evidence, and review payloads untranslated.
- Dashboard information-density optimization is complete.
  - `/web/dashboard` now works better as the daily Web MVP entry page.
  - It shows recent documents with source, status, time, summary, lightweight signals, system status, and quick entries for Documents, Ask, and Review.
- System / Storage overview is complete.
  - `/web/system` now clearly distinguishes main knowledge storage from Web peripheral configuration storage.
  - It records:
    - main knowledge storage: `PostgreSQL + pgvector`
    - Ask history: `DB-first + JSON fallback`
    - AI provider config: `DB-first + JSON fallback`
    - `Source.config["_web"]`: intentionally retained, not a migration target
  - Database degradation is displayed as a page note rather than becoming a 500.
  - API keys are not shown in plain text.

### Important boundary that remains

- `risk_count=0` on Documents/Dashboard remains the conservative display when there is no document-level risk association available.
- Do not add a new risk model just to make the page signal richer.
- Do not expand System / Storage into a full operations dashboard.
- Do not change the storage strategy while working on System page display.

### Do not reopen by default

The following Web page-quality tasks are now complete and should not be picked as default next steps:

- Documents signals/detail-column optimization
- Dashboard quick actions/signals optimization
- System storage overview

### Updated next-session starting point

If the next session is Web/product iteration, pick a new small page-quality task on top of the stable baseline.

Good candidates include:

- Watchlist page scanability or related-document presentation
- Review page efficiency small improvement

Do not restart Documents, Dashboard, or System information-density work unless a concrete regression is reported.

## 13. Latest Progress Addendum (2026-04-30 Sources scanability pass)

This addendum overrides older notes that still list Sources scanability or maintenance metadata clarity as the default next Web task.

### Completed in this round

- Sources page scanability optimization is complete.
- `/web/sources` now functions as a clearer human-maintained source list.
- The Sources list now surfaces:
  - source name
  - notes / description fallback
  - source type
  - URL
  - credibility level
  - `enabled` / `disabled` status
  - Web maintenance metadata
  - existing action entry points
- `Source.config["_web"]` remains lightweight maintenance metadata for the Web layer.
  - It is read for display.
  - It is not a formal schema.
  - It is not a migration target.
- Extra `_web` metadata, such as `owner`, is preserved when ordinary edit or import metadata write-back updates the standard fields.
- Current verification for this Web page-quality round was:
  - `pytest tests\test_web_dashboard_documents.py -q`
  - `pytest -q`
  - final reported suite result: `111 passed`

### Important boundary that remains

- Do not describe this as source registry expansion.
- Do not describe this as automatic source discovery or crawling support.
- Do not promote `Source.config["_web"]` into a domain schema or migration target by default.
- Do not change source storage strategy just to make the Sources page richer.

### Do not reopen by default

The following Web page-quality tasks are now complete and should not be picked as default next steps:

- Documents signals/detail-column optimization
- Dashboard quick actions/signals optimization
- System storage overview
- Sources scanability / maintenance metadata display

### Updated next-session starting point

If the next session is Web/product iteration, pick a new small page-quality task on top of the stable baseline.

Good candidates include:

- Watchlist page scanability optimization
- Review page efficiency small improvement

Do not restart Documents, Dashboard, System, or Sources information-density work unless a concrete regression is reported.

## 14. Latest Progress Addendum (2026-04-30 Watchlist scanability pass)

This addendum overrides older notes that still list Watchlist page scanability as the default next Web task.

### Completed in this round

- Watchlist page scanability optimization is complete.
- `/web/watchlist` now consumes a service-level page-view contract instead of reading `WatchlistItem` ORM attributes directly in the route.
- `docs/web_page_contract.md` now includes a Watchlist Contract covering:
  - returned fields
  - empty state
  - database degradation note
  - related-document display boundary
  - explicit non-goals
- `WebMvpService.list_watchlist_page_views()` now provides the page data for the Watchlist route.
- The Watchlist page now surfaces:
  - watchlist value
  - item type
  - priority
  - status
  - group
  - notes
  - linked entity
  - updated / created time
  - top related documents
  - existing status actions
- Related documents remain bounded to the existing `list_watchlist_hits()` text-match behavior and top-3 display.
- Watchlist shell copy is covered in both default `zh` and explicit `?lang=en` modes.
- Current verification for this Web page-quality round was:
  - `pytest tests/test_web_mvp_acceptance.py tests/test_web_i18n.py -q`
  - `15 passed`
  - `pytest -q`
  - `115 passed`

### Important boundary that remains

- Do not describe this as advanced RAG, vector retrieval, or complex entity matching.
- Do not expand Watchlist into automatic source discovery, crawling, or source registry management.
- Do not translate watchlist values, notes, document titles, summaries, evidence, or other knowledge content.
- Do not modify `src/domain/*`, `src/application/*`, or `src/processing/*` for this completed page-quality pass.
- `list_watchlist_hits()` remains a simple text-match related-document helper unless a separate retrieval-quality task is explicitly opened.

### Do not reopen by default

The following Web page-quality tasks are now complete and should not be picked as default next steps:

- Documents signals/detail-column optimization
- Dashboard quick actions/signals optimization
- System storage overview
- Sources scanability / maintenance metadata display
- Watchlist scanability / related-document presentation

### Updated next-session starting point

If the next session is Web/product iteration, pick a new small page-quality or workflow-efficiency task on top of the stable baseline.

Good candidates include:

- Review page efficiency small improvement
- a narrowly scoped real integration or browser automation check if stronger confidence is needed
- documentation cleanup for a newly discovered page-contract gap

Do not restart Documents, Dashboard, System, Sources, or Watchlist information-density work unless a concrete regression is reported.

## 15. Latest Progress Addendum (2026-05-01 Review type filter pass)

This addendum records a completed Review page efficiency improvement and overrides older notes that might still suggest Review type filtering is pending.

### Completed in this round

- `/web/review` now supports lightweight `type` filtering with these values:
  - `all`
  - `summary`
  - `opportunity`
  - `risk`
  - `uncertainty`
- `type=all` remains the default and preserves the existing assembled Review behavior.
- Invalid `type` values fall back to `all`.
- The Review page now exposes filter links at the top of the page and preserves the current `lang` query parameter.
- Review edit form actions now preserve the current `lang` and effective `type`.
- After saving a Review edit, the redirect returns to the same Review `lang` and effective `type` context.
- Review current-filter label and type-specific empty states are complete.
- This change is a Review page scanability and efficiency improvement only.
- It does not change review override semantics.
- It does not change save behavior or review storage shape.

### Verification

- Latest verification completed successfully with `126 passed`.

### Important boundary that remains

- Do not reopen Review override semantics or storage-model design as part of this completed task.
- Do not add more Review filtering, sorting, or search behavior by default.
- Do not treat this as a new review architecture or workflow refactor.

### Updated next-session starting point

If the next session is Web/product iteration, do not continue Review type filtering. Treat it as finished and pick the next small page-quality or workflow-efficiency task on top of the stable baseline.

## 16. Latest Progress Addendum (2026-05-01 Directory-mode seed rerun)

This addendum records the directory-mode rerun and the observation-only rerun for `what-openai-did`.

### Completed in this round

- The directory-mode seed rerun was executed with:
  - `.\.venv\Scripts\python.exe scripts\run_application_batch.py --url-list scripts\real_seed_sources --no-persist`
- The directory-mode rerun produced:
  - `total=5`
  - `succeeded=0`
  - `failed=5`
- Every attempted URL failed with `URLError: [WinError 10013]`.
- The failure pattern is consistent with an environment/network restriction in the current sandboxed environment.
- An observation-only rerun was then attempted with:
  - `.\.venv\Scripts\python.exe scripts\run_application_batch.py --url-list scripts\real_seed_sources\trial_oneusefulthing_minimal.txt --no-persist`
- The observation rerun also produced:
  - `total=5`
  - `succeeded=0`
  - `failed=5`
- The formal baseline definition remains 4 URLs.
- `what-openai-did` remains `deferred`.
- Even if `what-openai-did` succeeds in a future observation run, it should remain deferred until explicitly promoted in a later maintenance decision.

### Important boundary that remains

- Do not classify the current `WinError 10013` pattern as a code regression by default.
- Do not infer that the formal baseline expanded to 5 URLs from the directory-mode rerun.
- Do not expand the importer, seed list, or crawl behavior as part of this maintenance pass.
- Do not auto-promote `what-openai-did` from observation-only status.

### Updated next-session starting point

If the next session is content maintenance, rerun the formal baseline in a network-enabled environment before considering deferred candidates again. If the next session is Web/product iteration, treat this maintenance pass as complete and do not reopen seed promotion or importer design. Review current-filter label and type-specific empty states are already complete and should not be reopened by default.

## 17. Latest Progress Addendum (2026-05-01 AI Settings contract and browser smoke checklist)

This addendum records the AI Settings page-contract pass and the new manual browser smoke checklist.

### Completed in this round

- `docs/web_page_contract.md` now includes an AI Settings Contract covering:
  - `/web/ai-settings`
  - `/web/ai-settings/{provider_id}`
  - `POST /web/ai-settings`
  - `POST /web/ai-settings/{provider_id}/test`
- AI Settings list/detail/save/test language-context behavior is now explicit.
- AI Settings list and detail pages preserve the current `lang` query for:
  - edit links
  - test form actions
  - save form actions
  - back-to-list links
  - save/test redirects
- AI Settings page rendering is explicitly bounded to `provider.masked_key`; raw `api_key` must not be interpolated into HTML.
- The existing AI provider storage boundary remains unchanged:
  - DB-first
  - JSON fallback
  - no automatic legacy JSON import
  - no secrets-management redesign
- `docs/web_browser_smoke_checklist.md` was added as a manual real-browser smoke checklist for the Web MVP.
- The browser checklist covers:
  - Dashboard
  - Documents
  - Sources
  - Review
  - Watchlist
  - Ask
  - AI Settings
  - System
- The browser checklist explicitly distinguishes:
  - route-level smoke
  - manual browser smoke
  - real DB / integration verification
- Data-dependent browser checks are conditional:
  - if documents/sources/watchlist items exist, verify detail/card behavior
  - if they do not exist, verify empty states and navigation

### Verification

- Targeted local verification for the AI Settings route/page changes was run with:
  - `pytest tests/test_web_mvp_acceptance.py tests/test_web_ask.py -q`
  - result: `48 passed`
- Python compile check was run for the touched Web route/service modules:
  - `python -m compileall src\api\routes\web.py src\web\service.py`
- The browser smoke checklist itself is documentation only and records `Date of latest pass: not run yet`.

### Important boundary that remains

- Do not reopen AI Settings language-context or masked-key rendering as a default next task.
- Do not treat the browser smoke checklist as Playwright automation or full end-to-end coverage.
- Do not expand browser smoke into real provider calls, ingestion validation, business-data quality checks, or live persistence verification.
- Do not change `src/domain/*`, `src/application/*`, or `src/processing/*` for this completed Web page-contract/checklist pass.
- Do not change Ask provider routing or AI provider storage semantics as part of this completed task.

### Updated next-session starting point

If the next session is Web/product iteration:

1. Treat AI Settings contract/lang/masking work as complete.
2. Treat the manual browser smoke checklist as established but not yet executed.
3. If confidence work is desired, run the checklist manually in a local browser and record the pass date/result in `docs/web_browser_smoke_checklist.md`.
4. Otherwise pick a new small page-quality or workflow-efficiency task on top of the stable Web MVP baseline.

If the next session is content maintenance, keep using the Section 16 rule: rerun the formal baseline in a network-enabled environment before reconsidering deferred candidates.
