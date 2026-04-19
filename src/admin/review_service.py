"""人工修订服务层

提供修订记录的创建、查询和覆盖逻辑。
对应 TC-20（人工修订规则卡）。

核心规则：
  - 人工结果优先级高于自动结果
  - 所有修订保留审计记录
  - target_type + field_name 组合必须合法
  - 同一字段多次修订，最新人工值生效
  - 可查询任意字段的覆盖状态（manual vs auto）

第一阶段使用内存存储，后续可切换到数据库。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from src.admin.review_schemas import (
    ALLOWED_FIELD_NAMES,
    ReviewEditCreate,
    ReviewEditResponse,
    ReviewFieldName,
    ReviewHistoryResponse,
    ReviewTargetType,
    OverrideStatus,
)


class InvalidReviewError(Exception):
    """修订校验错误"""

    pass


class ReviewService:
    """人工修订服务

    管理修订记录和覆盖状态。
    第一阶段使用内存存储，接口设计兼容后续数据库切换。
    """

    def __init__(self) -> None:
        # 修订记录存储：id -> ReviewEditResponse
        self._edits: dict[uuid.UUID, ReviewEditResponse] = {}
        # 按目标索引：(target_type, target_id) -> [edit_id, ...]
        self._target_index: dict[tuple[str, uuid.UUID], list[uuid.UUID]] = {}
        # 覆盖状态索引：(target_type, target_id, field_name) -> latest manual edit
        self._override_index: dict[tuple[str, uuid.UUID, str], uuid.UUID] = {}

    def create_edit(
        self,
        target_type: str,
        target_id: uuid.UUID,
        create: ReviewEditCreate,
    ) -> ReviewEditResponse:
        """创建一条修订记录

        Args:
            target_type: 修订目标类型
            target_id: 修订目标 ID
            create: 修订创建参数

        Returns:
            创建的修订记录

        Raises:
            InvalidReviewError: target_type 不合法或 field_name 不允许
        """
        # 校验 target_type
        try:
            tt = ReviewTargetType(target_type)
        except ValueError:
            valid = sorted(t.value for t in ReviewTargetType)
            raise InvalidReviewError(
                f"无效的 target_type: {target_type!r}，合法值: {valid}"
            )

        # 校验 field_name 是否允许用于该 target_type
        allowed = ALLOWED_FIELD_NAMES.get(tt, [])
        allowed_values = [fn.value for fn in allowed]
        if create.field_name not in allowed_values:
            raise InvalidReviewError(
                f"target_type={target_type!r} 不允许修订字段 {create.field_name!r}，"
                f"允许的字段: {allowed_values}"
            )

        # 创建记录
        edit_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        edit = ReviewEditResponse(
            id=edit_id,
            target_type=target_type,
            target_id=target_id,
            field_name=create.field_name,
            old_value=create.old_value,
            new_value=create.new_value,
            reason=create.reason,
            reviewer=create.reviewer,
            source="manual",
            created_at=now,
        )

        self._edits[edit_id] = edit

        # 更新目标索引
        key = (target_type, target_id)
        self._target_index.setdefault(key, []).append(edit_id)

        # 更新覆盖状态索引（最新人工修订）
        override_key = (target_type, target_id, create.field_name)
        self._override_index[override_key] = edit_id

        return edit

    def create_batch(
        self,
        target_type: str,
        target_id: uuid.UUID,
        batch: list[ReviewEditCreate],
        reason: str | None = None,
    ) -> list[ReviewEditResponse]:
        """批量创建修订记录

        Args:
            target_type: 修订目标类型
            target_id: 修订目标 ID
            batch: 修订创建参数列表
            reason: 整体修订原因（覆盖单条 reason）

        Returns:
            创建的修订记录列表
        """
        results = []
        for create in batch:
            if reason and not create.reason:
                create = create.model_copy(update={"reason": reason})
            results.append(self.create_edit(target_type, target_id, create))
        return results

    def get_edit(self, edit_id: uuid.UUID) -> ReviewEditResponse | None:
        """获取单条修订记录"""
        return self._edits.get(edit_id)

    def get_history(
        self,
        target_type: str,
        target_id: uuid.UUID,
        field_name: str | None = None,
    ) -> ReviewHistoryResponse:
        """获取修订历史

        Args:
            target_type: 目标类型
            target_id: 目标 ID
            field_name: 可选，只看某个字段的历史

        Returns:
            修订历史（含最新人工值）
        """
        key = (target_type, target_id)
        edit_ids = self._target_index.get(key, [])

        edits = []
        for eid in edit_ids:
            edit = self._edits[eid]
            if field_name and edit.field_name != field_name:
                continue
            edits.append(edit)

        # 按时间倒序
        edits.sort(key=lambda e: e.created_at, reverse=True)

        # 计算各字段最新人工值
        latest_values: dict[str, Any] = {}
        for edit in edits:
            if edit.field_name not in latest_values:
                latest_values[edit.field_name] = edit.new_value

        return ReviewHistoryResponse(
            target_type=target_type,
            target_id=target_id,
            edits=edits,
            total_count=len(edits),
            latest_values=latest_values,
        )

    def get_override_status(
        self,
        target_type: str,
        target_id: uuid.UUID,
        field_name: str,
    ) -> OverrideStatus:
        """获取字段覆盖状态

        判断某个字段当前是人工值还是自动值。
        人工值优先级高于自动值。

        Args:
            target_type: 目标类型
            target_id: 目标 ID
            field_name: 字段名

        Returns:
            覆盖状态
        """
        override_key = (target_type, target_id, field_name)
        edit_id = self._override_index.get(override_key)

        if edit_id:
            edit = self._edits[edit_id]
            return OverrideStatus(
                field_name=field_name,
                source="manual",
                last_manual_value=edit.new_value,
                last_manual_at=edit.created_at,
                current_auto_value=None,  # 需要从业务层查询自动值
            )
        else:
            return OverrideStatus(
                field_name=field_name,
                source="auto",
                last_manual_value=None,
                last_manual_at=None,
                current_auto_value=None,
            )

    def get_effective_value(
        self,
        target_type: str,
        target_id: uuid.UUID,
        field_name: str,
        auto_value: Any = None,
    ) -> Any:
        """获取字段有效值

        如果有人工修订，返回人工值；否则返回自动值。
        这是"人工覆盖自动"的核心逻辑。

        Args:
            target_type: 目标类型
            target_id: 目标 ID
            field_name: 字段名
            auto_value: 自动值（默认值）

        Returns:
            有效值
        """
        override_key = (target_type, target_id, field_name)
        edit_id = self._override_index.get(override_key)

        if edit_id:
            edit = self._edits[edit_id]
            return edit.new_value
        return auto_value

    def revert_edit(self, edit_id: uuid.UUID, reviewer: str = "owner") -> ReviewEditResponse | None:
        """撤销一条修订记录

        撤销后，该字段恢复为自动值（即删除覆盖状态）。
        撤销操作本身也记录为一条修订。

        Args:
            edit_id: 要撤销的修订 ID
            reviewer: 执行撤销的人

        Returns:
            撤销产生的修订记录，如果原修订不存在则返回 None
        """
        original = self._edits.get(edit_id)
        if original is None:
            return None

        # 创建撤销记录：将 new_value 恢复为 old_value
        revert = ReviewEditCreate(
            field_name=original.field_name,
            new_value=original.old_value,
            old_value=original.new_value,
            reason=f"撤销修订 {edit_id}",
            reviewer=reviewer,
        )

        # 如果 old_value 为 None，则从覆盖索引中移除
        if original.old_value is None:
            override_key = (original.target_type, original.target_id, original.field_name)
            # 检查是否有更早的人工修订
            key = (original.target_type, original.target_id)
            edit_ids = self._target_index.get(key, [])
            earlier_edits = [
                eid for eid in edit_ids
                if eid != edit_id
                and self._edits[eid].field_name == original.field_name
            ]
            if earlier_edits:
                # 使用次新的人工修订
                latest_earlier = max(
                    earlier_edits,
                    key=lambda eid: self._edits[eid].created_at,
                )
                self._override_index[override_key] = latest_earlier
            else:
                # 没有更早的人工修订，移除覆盖
                self._override_index.pop(override_key, None)

        return self.create_edit(
            target_type=original.target_type,
            target_id=original.target_id,
            create=revert,
        )

    def count(self, target_type: str | None = None) -> int:
        """统计修订记录数量"""
        if target_type is None:
            return len(self._edits)
        return sum(
            1 for e in self._edits.values() if e.target_type == target_type
        )

    def __len__(self) -> int:
        return len(self._edits)

    def __repr__(self) -> str:
        return f"<ReviewService total={len(self._edits)}>"
