# 人工修订模块实现说明

## 1. 可修订字段

根据 TC-20（人工修订规则卡），第一阶段支持修订以下目标类型及其字段：

| 目标类型            | 字段名               | 说明                                              |
| ------------------- | -------------------- | ------------------------------------------------- |
| `summary`           | `summary_zh`         | 中文摘要                                          |
|                     | `summary_en`         | 英文摘要                                          |
|                     | `key_points`         | 关键点列表                                        |
| `tags`              | `tags`               | 标签列表                                          |
| `opportunity_score` | `need_realness`      | 需求真实性评分 (1-10)                             |
|                     | `market_gap`         | 市场空白度评分 (1-10)                             |
|                     | `feasibility`        | 产品化可行性评分 (1-10)                           |
|                     | `priority_score`     | 跟进优先级评分 (1-10)                             |
|                     | `evidence_score`     | 证据充分度评分 (1-10)                             |
|                     | `total_score`        | 加权总分                                          |
|                     | `uncertainty`        | 不确定性标记 (bool)                               |
|                     | `uncertainty_reason` | 不确定性原因                                      |
|                     | `status`             | 机会状态 (candidate/confirmed/dismissed/watching) |
| `conclusion`        | `conclusion_zh`      | 中文结论                                          |
|                     | `conclusion_en`      | 英文结论                                          |
| `priority`          | `priority_level`     | 优先级 (high/medium/low)                          |
| `topic`             | `name_zh`            | 主题中文名称                                      |
|                     | `name_en`            | 主题英文名称                                      |
|                     | `description`        | 主题描述                                          |
| `uncertainty`       | `uncertainty_status` | 不确定性状态                                      |
|                     | `uncertainty_note`   | 不确定性备注                                      |
| `risk`              | `severity`           | 风险严重程度                                      |
|                     | `description`        | 风险描述                                          |

字段映射定义在 `src/admin/review_schemas.py` 的 `ALLOWED_FIELD_NAMES` 字典中，确保 `target_type` + `field_name` 组合合法。

## 2. 人工覆盖自动的实现

### 核心逻辑
- 每个字段的当前值由 **人工修订记录** 和 **自动生成值** 共同决定。
- 人工修订优先级高于自动结果，即“人工覆盖自动”。
- 实现位于 `DatabaseReviewService.get_effective_value()` 方法中。

### 工作流程
1. 业务层（如摘要服务、机会评分服务）生成自动值。
2. 调用 `get_effective_value(target_type, target_id, field_name, auto_value)`。
3. 服务查询该字段的最新人工修订记录：
   - 如果存在，返回 `new_value`（人工值）。
   - 如果不存在，返回传入的 `auto_value`（自动值）。
4. 业务层使用返回的有效值进行后续处理。

### 覆盖状态查询
可通过 `GET /api/v1/reviews/{target_type}/{target_id}/override/{field_name}` 获取字段的覆盖状态（`manual` 或 `auto`），以及最近一次人工修订的值和时间。

## 3. 审计记录的保存

### 存储设计
- 所有修订记录保存在 `review_edits` 表中（参见 `src/domain/models.py` 的 `ReviewEdit` 模型）。
- 每条记录包含：
  - `target_type`, `target_id`：修订目标标识。
  - `field_name`, `old_value`, `new_value`：字段变更详情。
  - `reason`, `reviewer`：修订原因和执行人。
  - `created_at`：修订时间戳。
- `old_value` / `new_value` 使用 JSON 序列化存储，支持任意类型（字符串、数字、列表、对象等）。

### 历史追溯
- 通过 `GET /api/v1/reviews/{target_type}/{target_id}` 可获取目标的所有修订历史，按时间倒序排列。
- 响应中包含 `latest_values` 字段，汇总各字段的最新人工值，便于快速获取覆盖状态。

### 撤销操作
- 撤销操作本身也记录为一条新的修订（`old_value` 与 `new_value` 互换），保证审计链条完整。
- 通过 `POST /api/v1/reviews/{edit_id}/revert` 可撤销单条修订。

## 4. 后续扩展为真正管理后台的建议

### 前端界面
1. **修订入口**：在摘要、机会评分、主题等展示页面添加“编辑”按钮，点击后弹出修订表单。
2. **历史面板**：侧边栏或弹窗展示字段的修订历史，支持按时间筛选。
3. **批量操作**：支持勾选多个字段或目标，批量提交修订。
4. **差异对比**：以 diff 视图展示 `old_value` 与 `new_value` 的差异。

### 权限与工作流
1. **多角色权限**：区分“查看者”、“编辑者”、“管理员”，控制修订权限。
2. **审批流程**：重要字段（如机会评分、结论）可配置为需要审核，修订后进入待审核状态，由管理员批准后生效。
3. **通知机制**：当字段被修订时，通知相关责任人。

### 数据可视化
1. **覆盖统计**：仪表盘展示各目标类型的人工修订比例、最近活跃修订者等。
2. **质量评估**：对比人工修订前后的自动结果质量，用于优化自动处理算法。

### 技术扩展
1. **事件总线**：修订完成后发布领域事件（如 `ReviewEdited`），触发下游更新（如重新生成日报、更新缓存）。
2. **版本快照**：定期为重要目标创建完整版本快照，支持回滚到任意历史版本。
3. **开放 API**：提供更丰富的查询接口，如按时间范围、按修订人、按字段类型筛选修订记录。

### 数据库优化
1. **分区表**：按 `target_type` 或时间对 `review_edits` 表进行分区，提升查询性能。
2. **全文索引**：对 `reason`、`old_value`、`new_value` 等文本字段建立全文索引，支持关键词搜索。

## 5. 已实现的核心文件清单

- `src/domain/models.py`：`ReviewEdit` 数据模型，`ReviewTargetType` 枚举。
- `src/admin/review_schemas.py`：修订 Schema、字段映射、请求/响应结构。
- `src/admin/review_service_db.py`：基于数据库的修订服务（`DatabaseReviewService`）。
- `src/api/routes/reviews.py`：修订 API 端点（单字段修订、批量修订、历史查询、覆盖状态、撤销）。
- `src/api/deps.py`：数据库会话依赖。
- `scripts/demo_review_integration.py`：集成示例脚本。
- `scripts/verify_review.py`：功能验证脚本。

## 6. 使用示例

### 修订摘要
```bash
PATCH /api/v1/reviews/summary/{document_summary_id}
{
  "field_name": "summary_zh",
  "new_value": "人工修订后的中文摘要",
  "reason": "自动摘要遗漏关键点"
}
```

### 批量修订机会评分
```bash
POST /api/v1/reviews/opportunity_score/{opportunity_id}/batch
{
  "edits": [
    {"field_name": "need_realness", "new_value": 8},
    {"field_name": "market_gap", "new_value": 9}
  ],
  "reason": "整体上调评分"
}
```

### 查询覆盖状态
```bash
GET /api/v1/reviews/summary/{document_summary_id}/override/summary_zh
```

### 撤销修订
```bash
POST /api/v1/reviews/{edit_id}/revert
```

## 7. 下一步行动

1. **运行验证脚本**：执行 `python scripts/verify_review.py` 确保功能正常。
2. **集成到业务服务**：在摘要生成、机会评分等模块中调用 `get_effective_value` 实现人工覆盖。
3. **前端对接**：基于 API 开发简易管理界面，供人工修订使用。
4. **监控与告警**：添加修订操作的日志和监控，便于追踪异常。

## 8. Latest Status Update (2026-04-28)

The notes above include older-stage guidance. The current implementation status is:

- `summary` has now been aligned with the same review override model used by `opportunities`, `risks`, and `uncertainties`.
- `save_summary_review()` no longer writes directly back to `DocumentSummary`.
- Summary manual edits are stored in `review_edits`.
- Summary now supports:
  - automatic value display
  - effective value display
  - `reset to auto`
  - review history
- Ask document evidence now consumes effective `summary` / `key_points` values instead of blindly trusting the persisted automatic summary fields.

Current boundary:

- historical summary rows that were directly overwritten in older flows are not retroactively repaired
- for summary, `reset to auto` means returning to the current persisted summary baseline
- this change is limited to Review / Web / Ask result assembly semantics and does not imply a main storage migration
