# API 草案

## 1. 设计目标

API 面向通用 AI Agent，而不是只面向人工界面。

因此设计目标是：

- 返回结构化结果
- 避免大段松散文本
- 明确区分摘要、证据、机会、风险和不确定性
- 便于 Agent 进行二次推理和编排

## 2. 鉴权与配额

第一阶段策略：

- 鉴权方式：单用户密钥
- 配额控制：按 token 或返回条数限制
- 未来扩展：预留升级到多密钥、更复杂鉴权和更细粒度配额策略的接口

## 3. 统一响应原则

建议统一包含以下高层字段：

- `summary`
- `evidence`
- `opportunities`
- `risks`
- `uncertainties`
- `related_topics`
- `watchlist_updates`
- `meta`

错误响应建议统一包含：

- `error_code`
- `message`
- `details`

## 4. 接口草案

### 4.1 `POST /api/v1/search`

用途：

- 按 query、topic、时间范围搜索知识结果

请求示例：

```json
{
  "query": "AI coding tools market gap",
  "topics": ["agent", "developer tools"],
  "watchlist_only": false,
  "date_from": "2026-04-01",
  "date_to": "2026-04-19",
  "limit": 10
}
```

响应示例：

```json
{
  "summary": {
    "zh": "围绕 AI coding tools 的结果显示，当前关注点集中在工作流整合和可靠性。",
    "en": "Results around AI coding tools focus on workflow integration and reliability."
  },
  "evidence": [],
  "opportunities": [],
  "risks": [],
  "uncertainties": [],
  "related_topics": [],
  "meta": {
    "result_count": 10
  }
}
```

### 4.2 `GET /api/v1/briefs/latest`

用途：

- 获取最新日报

响应示例：

```json
{
  "date": "2026-04-19",
  "summary": {
    "zh": "今日重点集中在 AI Agent 工作流和具身智能工具链。",
    "en": "Today's highlights focus on AI agent workflows and embodied AI toolchains."
  },
  "opportunities": [],
  "risks": [],
  "uncertainties": [],
  "watchlist_updates": [],
  "meta": {
    "brief_type": "scheduled"
  }
}
```

### 4.3 `POST /api/v1/briefs/generate`

用途：

- 按指定时间点生成一份固定或按需简报

请求示例：

```json
{
  "as_of": "2026-04-19T09:00:00+08:00",
  "watchlist_scope": true,
  "force_refresh": false
}
```

### 4.4 `GET /api/v1/opportunities`

用途：

- 获取产品机会判断结果

查询参数：

- `min_score`
- `topic`
- `limit`
- `uncertainty`

响应示例：

```json
{
  "items": [
    {
      "title_zh": "面向小团队的 AI 工作流可观测性工具",
      "title_en": "AI workflow observability tools for small teams",
      "scores": {
        "need_realness": 8,
        "market_gap": 8,
        "feasibility": 7,
        "priority": 7,
        "evidence": 6,
        "total": 7.5
      },
      "evidence": [],
      "uncertainty": false
    }
  ]
}
```

### 4.5 `GET /api/v1/topics/{id}`

用途：

- 获取主题详情、相关文档、关联实体和趋势摘要

### 4.6 `GET /api/v1/watchlist`

用途：

- 获取当前关注列表

### 4.7 `POST /api/v1/watchlist`

用途：

- 新增关注项

请求体建议字段：

- `item_type`
- `item_value`
- `priority_level`
- `group_name`
- `notes`

### 4.8 `PATCH /api/v1/reviews/{target_type}/{target_id}`

用途：

- 修订摘要、标签、评分、结论等

### 4.9 `GET /api/v1/health`

用途：

- 健康检查和配额状态查询

## 5. 数据约定

### 5.1 双语字段

所有摘要性文本建议支持：

- `zh`
- `en`

### 5.2 机会评分字段

建议至少包含：

- `need_realness`
- `market_gap`
- `feasibility`
- `priority`
- `evidence`
- `total`

### 5.3 不确定性表达

建议使用：

- `uncertainty: true/false`
- `uncertainty_reason`

## 6. 错误响应约定

错误响应示例：

```json
{
  "error_code": "quota_exceeded",
  "message": "API quota exceeded",
  "details": {
    "quota_mode": "token",
    "quota_limit": 100000
  }
}
```

## 7. 后续扩展预留

- 多用户密钥
- 更细粒度权限控制
- 异步任务式报告生成
- 更复杂的主题聚合接口
- 针对 Agent 的流式响应
