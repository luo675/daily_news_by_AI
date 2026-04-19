# 最小上下文摘要

## 1. 项目结构（精简版）

### 根目录

- `goal.md`
  - 项目目标与架构初稿
- `ARCH_CONTEXT.md`
  - 当前最小上下文摘要
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
  - 可派发给单独模型的任务卡
- `api_spec.md`
  - API 草案
- `testing_strategy.md`
  - 测试与质量策略
- `review_implementation.md`
  - 人工修订相关实现文档

### 代码目录 `src/`

- `domain/`
  - `base.py`
  - `models.py`
  - 第一阶段核心数据模型
- `ingestion/`
  - `schemas.py`
  - `source_registry.py`
  - `adapters.py`
  - `validators.py`
  - 来源注册与统一采集输入骨架
- `watchlist/`
  - `schemas.py`
  - `service.py`
  - `weight.py`
  - watchlist 骨架
- `api/`
  - `app.py`
  - `auth.py`
  - `deps.py`
  - `schemas.py`
  - `routes/`
  - API 骨架
- `admin/`
  - `review_schemas.py`
  - `review_service.py`
  - `review_service_db.py`
  - 人工修订骨架
- `config.py`
  - 数据库和 session 配置

### 其他目录

- `configs/sources/default_sources.yaml`
  - 默认来源配置
- `scripts/`
  - `verify_models.py`
  - `verify_ingestion.py`
  - `verify_watchlist.py`
  - `verify_api.py`
  - `verify_review.py`
  - 若干当前验收脚本

## 2. 当前需求目标

### 项目定位

- 项目名：`daily_news`
- 目标不是普通资讯抓取器，而是一个面向 AI 领域的个人知识数据库
- 第一阶段按个人使用设计，后续分享成果给其他人
- 需要支持通用 AI Agent 通过 API 读取知识库

### 核心目标

- 收集高价值 AI 信息
- 处理为结构化知识
- 支持检索、串联、问答、日报
- 支持投资研究辅助
- 第一阶段优先支持产品机会判断

### 第一阶段重点输出

- 中英双语每日简报
- 产品机会列表
- 风险列表
- 趋势判断
- watchlist 更新
- 面向 AI Agent 的结构化 API

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

## 3. 已确定的设计决策

### 用户与使用方式

- 第一阶段只给个人使用
- 后续会分享结果给其他人
- 外部消费对象主要是通用 AI Agent

### 输出与语言

- 数据源以英文为主
- 输出采用中英双语并列
- 日报第一阶段输出为 Markdown
- 每天固定生成一份日报
- 用户可按需额外生成一份最新简报

### 第一阶段主目标

- 产品机会判断优先于投资研究判断
- 重点判断两个问题：
  - 需求是否真实存在
  - 市场是否还空白

### 产品机会评分

- 评分制：`1-10`
- `10` 分表示最有创意、最让人眼前一亮
- 默认评分维度：
  - `需求真实性` 30%
  - `市场空白度` 30%
  - `产品化可行性` 20%
  - `跟进优先级` 10%
  - `证据充分度` 10%

### 冲突处理

- 优先自动判断
- 如果判断不了，保留不确定性
- 输出时明确标注冲突或待确认
- 来源可信度必须参与冲突判断

### 来源可信度

- 需要分级
- 建议分为 `S / A / B / C`
- 区分：
  - 一手来源
  - 原始发言
  - 机构原文
  - 二手整理
  - 评论和转述

### 存储策略

- 第一阶段不强求保存原始全文或网页快照
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
- 支持两种组织方式：
  - 按对象类型
  - 按优先级
- 支持优先级和分组

### API

- 第一阶段需要支持外部 AI 通过 API 读取知识库
- 第一阶段 API 全部开放的范围包括：
  - 检索结果
  - 专题聚合结果
  - 日报
  - 产品机会判断
  - 风险与不确定性
- API 返回必须结构化，便于 Agent 消费
- 统一返回高层字段建议包括：
  - `summary`
  - `evidence`
  - `opportunities`
  - `risks`
  - `uncertainties`
  - `related_topics`
  - `watchlist_updates`
  - `meta`

### API 鉴权与配额

- 第一阶段鉴权采用单用户密钥
- 要保留未来升级口子
- 配额按：
  - token
  - 或返回条数
- 当前主要调用对象是通用 AI Agent

### 人工修订

- 第一阶段必须支持人工修订入口
- 人工权限最大
- 人工结果优先于自动结果
- 支持修订：
  - 摘要
  - 标签
  - 主题
  - 机会分数
  - 风险标记
  - 结论
  - 优先级
  - 不确定性标记
- 需要保留审计记录

### 技术选型

- 后端：`Python + FastAPI`
- 数据库：`PostgreSQL`
- 向量：`pgvector`
- 调度：`Celery` 或 `Prefect`
- 抓取：`RSS + requests`，必要时 `Playwright`
- 部署：`Docker Compose`
- 当前阶段是规划与骨架，不是完整实现

## 4. 当前代码状态

### 已完成的骨架

- 数据模型骨架
- 来源注册与统一采集输入结构
- watchlist 服务层骨架
- API 路由骨架
- 人工修订服务骨架

### 当前验证结果

- 通过：
  - `scripts/verify_models.py`
  - `scripts/verify_ingestion.py`
  - `scripts/verify_watchlist.py`
- 失败：
  - `scripts/verify_api.py`
  - `scripts/verify_review.py`

## 5. 未解决的问题

### 问题 1：API 导入时强依赖数据库驱动

- 现象：
  - `verify_api.py` 和 `verify_review.py` 失败
  - 报错：`ModuleNotFoundError: No module named 'psycopg2'`
- 根因：
  - `src/api/deps.py` 在模块导入时立即创建 `SessionLocal`
  - `src/config.py` 强制使用 `postgresql+psycopg2`
  - `pyproject.toml` 没有 `psycopg2` 依赖
- 影响：
  - API 骨架本身不可导入
  - reviews 路由拖垮整个 API

### 问题 2：watchlist API 仍是占位实现

- `src/watchlist/service.py` 已实现
- 但 `src/api/routes/watchlist.py` 的 GET/POST 仍返回空数组
- API 未真正接上 watchlist 服务

### 问题 3：数据库版人工修订服务有运行时错误

- `src/admin/review_service_db.py` 的 `count()` 写法错误
- 使用了 `select(...).count()` 这种无效方式
- 真正运行时会炸

### 问题 4：领域枚举定义重复

- `domain.models`
- `ingestion.schemas`
- `watchlist.schemas`
- 多处重复定义相同概念
- 后续容易漂移

### 问题 5：编码乱码

- `pyproject.toml` 描述乱码
- 多个 Python 文件注释乱码
- 当前主要影响可维护性和元数据质量

## 6. 已给出的修改方向

### 修改方向 A：修复 API 启动期硬依赖

- 目标：
  - API 可以在未连接数据库或未安装 `psycopg2` 时仍能导入
- 要点：
  - 不要在模块导入期创建 session factory
  - 数据库依赖改为延迟初始化
  - 只在真正用到时建立连接
  - 必要时补依赖，或改成更一致的驱动方案

### 修改方向 B：把 watchlist API 真正接到 watchlist 服务

- 目标：
  - `GET /watchlist`
  - `POST /watchlist`
  - 不再返回空壳
- 要点：
  - 复用已有 watchlist service
  - 返回 grouped_by_type 和 grouped_by_priority
  - 处理重复项和非法输入

### 修改方向 C：修复数据库版人工修订服务

- 目标：
  - 数据库版 review service 至少达到可运行状态
- 要点：
  - 修复 `count()`
  - 检查 `get_history`
  - 检查 `_get_latest_edit`
  - 检查 `revert_edit`
  - 检查批量事务行为

### 修改方向 D：统一领域枚举

- 目标：
  - 消除重复枚举定义
- 要点：
  - 统一单一来源
  - ingestion/watchlist 优先复用 domain 层或 shared enum
  - 避免循环依赖

### 修改方向 E：修复编码和项目元数据乱码

- 目标：
  - 文件统一 UTF-8
  - 修复包描述和关键注释乱码

## 7. 后续执行步骤（todo list）

### 第一优先级

- [ ] 修复 API 导入阶段的数据库硬依赖
- [ ] 让 `scripts/verify_api.py` 可以通过
- [ ] 让 `scripts/verify_review.py` 至少能跑到 review 模块本身

### 第二优先级

- [ ] 修复 `DatabaseReviewService.count()` 和其他明显运行时错误
- [ ] 确保数据库版 review service 可稳定运行

### 第三优先级

- [ ] 将 watchlist API 接入 watchlist service
- [ ] 让 API 层真实暴露 watchlist 数据

### 第四优先级

- [ ] 消除 ingestion/watchlist/domain 中重复的枚举定义
- [ ] 修复编码乱码

### 第五优先级

- [ ] 开始第二批实现任务：
  - 清洗与去重规则
  - 双语摘要结构
  - 实体抽取结构
  - 主题抽取结构
  - 冲突检测规则
  - 产品机会评分骨架
  - 日报生成骨架

## 8. 新会话继续时建议先读的文件

- `ARCH_CONTEXT.md`
- `goal.md`
- `docs/project_overview.md`
- `docs/architecture.md`
- `docs/task_cards.md`
- `docs/api_spec.md`

## 9. 新会话建议的第一句话

- 先读取 `ARCH_CONTEXT.md`、`docs/task_cards.md` 和当前相关代码，再继续修复第一优先级问题。
