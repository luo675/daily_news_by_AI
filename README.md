# daily_news

`daily_news` 是一个面向 AI 领域的个人知识数据库与本地知识工作台。

它的目标不是做一个普通资讯抓取器，而是把高价值 AI 信息沉淀成可持续积累、可检索、可关联、可供通用 AI Agent 读取的结构化知识资产，用于支持：

- 每日简报
- 产品机会判断
- 风险与不确定性跟踪
- 专题串联
- 基于本地知识的问答

## 当前状态

项目已经不是纯设计阶段，当前已有一条可运行的 MVP 主链：

- 最小 URL 导入与批处理入口已打通
- PostgreSQL + pgvector 路径已验证过
- Web MVP 已落地
- Review 已扩展到：
  - `summary`
  - `opportunities`
  - `risks`
  - `uncertainties`
- Ask / Q&A 已保持 `local retrieval first` 边界，并开始优先消费 reviewed evidence

当前正式产品形态是：

- 网页优先
- 本地存储优先
- 外部 AI 通过 provider 配置接入
- 终端主要用于维护、验证、批处理和运维

更完整的最新状态以 [ARCH_CONTEXT.md](./ARCH_CONTEXT.md) 为准。

## 你应该先读什么

如果你是新接手的开发者或 AI：

1. 先读 [ARCH_CONTEXT.md](./ARCH_CONTEXT.md)
2. 再读 [goal.md](./goal.md)
3. 需要更细的项目说明时再读：
   - [docs/project_overview.md](./docs/project_overview.md)
   - [docs/architecture.md](./docs/architecture.md)
   - [docs/roadmap.md](./docs/roadmap.md)
   - [docs/testing_strategy.md](./docs/testing_strategy.md)

`ARCH_CONTEXT.md` 是当前最重要的交接文件，里面包含：

- 已完成阶段
- 当前稳定边界
- 不该再动的区域
- 下一会话最合理的起点
- 当前已知残留问题

## 当前能力边界

### 已有能力

- 原始内容导入与最小批处理
- 结构化处理流水线骨架
- 本地数据库持久化
- Web 页面：
  - Dashboard
  - Sources
  - Documents / Knowledge
  - Review
  - Watchlist
  - Ask / Q&A
  - AI Settings
  - System / Storage
- 人工审核覆盖自动结果
- Ask 优先消费本地知识，再按条件使用外部 AI 做受限推理

### 明确不是当前目标

- advanced RAG
- 向量问答主链重构
- 通用爬虫平台
- 多租户 / 复杂权限系统
- 生产级 secrets 管理

## 项目结构

```text
daily_news/
├─ ARCH_CONTEXT.md
├─ goal.md
├─ README.md
├─ pyproject.toml
├─ docs/
├─ configs/
├─ scripts/
├─ src/
└─ tests/
```

关键目录说明：

- `src/domain/`
  - 核心领域模型与共享枚举
- `src/ingestion/`
  - 原始内容输入、来源适配、URL 导入
- `src/processing/`
  - 清洗、摘要、抽取、冲突检测骨架
- `src/application/`
  - 应用编排与最小持久化
- `src/admin/`
  - review schema 与 review service
- `src/api/`
  - FastAPI 路由与 Web 页面入口
- `src/web/`
  - Web MVP 服务层
- `scripts/`
  - 验证脚本与手工批处理脚本
- `tests/`
  - pytest 测试

## 快速开始

### 环境要求

- Python `>= 3.11`
- PostgreSQL
- `pgvector`

### 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

### 数据库环境变量

当前项目从环境变量读取数据库配置：

- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`

仓库中已有一个本地样例文件：

- `.env.local`

### 常用验证命令

```powershell
python scripts\verify_models.py
python scripts\verify_ingestion.py
python scripts\verify_review.py
python scripts\verify_pipeline.py
python scripts\verify_application_flow.py
python scripts\verify_application_persistence_db.py
pytest tests -q
```

### 常用批处理命令

当前最小批处理入口：

```powershell
.\.venv\Scripts\python.exe scripts\run_application_batch.py --url <URL> --no-persist
.\.venv\Scripts\python.exe scripts\run_application_batch.py --url-list scripts\real_seed_sources --no-persist
```

## Web MVP 说明

当前 Web MVP 的定位是：

- 本地优先的个人知识工作台
- 不是终端优先工具
- 不是完整数据平台

当前 Review 已支持：

- `summary`
- `opportunities`
- `risks`
- `uncertainties`

当前 Ask 的边界是：

- 先做本地检索
- 本地 evidence 优先
- reviewed 结果优先于自动结果
- 外部 AI 只能消费“问题 + 已选本地证据”

## 当前重要实现约束

以下边界默认不要随意改动，除非有明确回归或明确新需求：

- `src/application/orchestrator.py`
- `src/application/persistence.py`
- `src/domain/*`
- `src/processing/*`
- 已稳定的 CLI / API 主路径
- 当前 `url_importer` 的“最薄 HTML 导入器”定位
- Ask 的 `local retrieval first` 主边界

不要擅自扩展为：

- Playwright 抓取平台
- 通用爬虫系统
- advanced RAG
- 主知识存储重构

## 当前优先级

如果你准备继续推进项目，先以 [ARCH_CONTEXT.md](./ARCH_CONTEXT.md) 的“下个会话最合理的工作起点”为准。

就当前状态而言：

- 内容维护主线：
  - 继续 baseline maintenance
  - 观察 `what-openai-did`
- 网页产品主线：
  - 当前应视为 `Web MVP baseline stable`
  - 不要重开 `uncertainty_status` 修复、Ask 展示收口、Ask history 本地存储收口、AI provider config 收口
  - 下一步应选择新的小型页面质量任务，而不是重复做已完成收口

## 文档导航

- [ARCH_CONTEXT.md](./ARCH_CONTEXT.md)
- [goal.md](./goal.md)
- [docs/project_overview.md](./docs/project_overview.md)
- [docs/architecture.md](./docs/architecture.md)
- [docs/roadmap.md](./docs/roadmap.md)
- [docs/task_breakdown.md](./docs/task_breakdown.md)
- [docs/task_cards.md](./docs/task_cards.md)
- [docs/api_spec.md](./docs/api_spec.md)
- [docs/testing_strategy.md](./docs/testing_strategy.md)
- [docs/review_implementation.md](./docs/review_implementation.md)

## Latest Status Update (2026-04-28)

This section supplements the older progress summary above.

- Ask result display optimization has been completed and accepted.
- The `/web/ask` page contract is now documented, including required fields, optional fields, and downgrade behavior for missing data.
- Ask history is already `DB-first + JSON fallback`.
- AI provider config is already `DB-first + JSON fallback`.
- Review and Ask now share a mostly unified manual-correction loop across:
  - `summary`
  - `opportunities`
  - `risks`
  - `uncertainties`

What this means in practice:

- auto values remain read-only
- manual changes are stored in `review_edits`
- effective values are resolved at read time
- `reset to auto` is supported
- Ask consumes effective values instead of blindly trusting raw automatic output

For the latest handoff status and the most reasonable next-session starting point, always prefer [ARCH_CONTEXT.md](./ARCH_CONTEXT.md).

## Latest Status Update (2026-04-29)

This section supplements the older update above.

- Formal seed baseline maintenance was rerun again on 2026-04-29.
- In restricted environment, the first failure was `URLError: [WinError 10013]`, treated as environment/network restriction rather than code regression.
- In a network-enabled environment, the formal baseline rerun succeeded with `4/4` items passed.
- `what-openai-did` succeeded in observation rerun, but remains `deferred`.
- `/web/ask` display-layer cleanup has been completed.
- `/web/review` and `/web/ask` now share more consistent page-level wording and empty-state semantics.
- Web MVP route-level smoke acceptance is now calibrated and repeatable.
- The current smoke suite is explicitly route-level and service-mocked, not real browser or live DB integration.
- The first-pass Web page-layer bilingual baseline has now been implemented; see `docs/web_i18n_task.md`.
- The Web page-layer bilingual shell-copy baseline has been completed across the current MVP pages.
- Default Web UI language is `zh`; explicit `?lang=en` and cookie fallback are supported.

What this means in practice:

- content maintenance baseline remains stable
- Web MVP display semantics have been further unified
- page-contract and acceptance documentation are now consolidated
- Ask display cleanup and Review / Ask wording cleanup should not be reopened as default next tasks
- page-layer bilingual switching is established for shell copy, but knowledge content is not auto-translated
- the next Web task should be a new focused page-quality task, not another default localization cleanup pass

For the latest handoff status and the most reasonable next-session starting point, always prefer [ARCH_CONTEXT.md](./ARCH_CONTEXT.md).

## Latest Status Update (2026-05-01)

This section supplements the older update above.

- `/web/review` now supports lightweight `type` filtering with `all`, `summary`, `opportunity`, `risk`, and `uncertainty`.
- Review type filtering is complete.
- `type=all` remains the default and preserves the existing assembled Review behavior.
- Invalid `type` values fall back to `all`.
- The Review page now exposes filter links at the top of the page and preserves the current `lang` query parameter.
- Review edit form actions and save redirects preserve the current `lang` and effective `type` context.
- Review current-filter label and type-specific empty states are complete.
- This is a Review page scanability and efficiency improvement only. It does not change review override semantics or review storage shape.
- Latest verification completed successfully with `126 passed`.

What this means in practice:

- Review type filtering is complete
- Review current-filter label and type-specific empty states are complete
- the next Web task should not reopen Review filter design or review storage semantics
- the project should move on to the next small page-quality or workflow-efficiency task on top of the stable baseline

For the latest handoff status and the most reasonable next-session starting point, always prefer [ARCH_CONTEXT.md](./ARCH_CONTEXT.md).

## Latest Status Update (2026-04-30)

This section supplements the older update above.

- Documents / Knowledge page scanability optimization is complete.
- Dashboard information-density optimization is complete and `/web/dashboard` is now a stronger daily Web MVP entry page.
- System / Storage overview is complete and now distinguishes:
  - main knowledge storage: `PostgreSQL + pgvector`
  - Ask history: `DB-first + JSON fallback`
  - AI provider config: `DB-first + JSON fallback`
  - `Source.config["_web"]`: retained, not a migration target
- Sources scanability / maintenance metadata display is complete; the page now shows source name, notes, type, URL, credibility, `enabled` / `disabled`, Web maintenance metadata, and existing actions while preserving extra `_web` metadata on edit/import write-back.
- Watchlist scanability / related-document presentation is complete; `/web/watchlist` now uses a service page-view contract and shows value, type, priority, status, group, notes, linked entity, updated/created time, related documents, and existing status actions.
- `risk_count=0` remains the conservative display when no document-level risk association exists.
- Current verification for the latest page-quality round was:
  - `pytest tests/test_web_mvp_acceptance.py tests/test_web_i18n.py -q` with `15 passed`
  - `pytest -q` with `115 passed`

Do not reopen these as default next tasks:

- Documents signals/detail-column optimization
- Dashboard quick actions/signals optimization
- System storage overview
- Sources scanability / maintenance metadata display
- Watchlist scanability / related-document presentation

The next Web product task should be a new small page-quality or workflow-efficiency task, such as a small Review page efficiency improvement, rather than reworking Documents / Dashboard / System / Sources / Watchlist.

Watchlist related documents still use the existing lightweight text-match helper. This was not an advanced RAG, vector retrieval, crawler, source-discovery, or entity-matching expansion.

For the latest handoff status and the most reasonable next-session starting point, always prefer [ARCH_CONTEXT.md](./ARCH_CONTEXT.md).
