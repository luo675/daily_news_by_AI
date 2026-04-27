"""基于数据库的人工修订服务层

使用 SQLAlchemy 模型持久化修订记录。
对应 TC-20（人工修订规则卡）。

核心规则：
  - 人工结果优先级高于自动结果
  - 所有修订保留审计记录
  - target_type + field_name 组合必须合法
  - 同一字段多次修订，最新人工值生效
  - 可查询任意字段的覆盖状态（manual vs auto）
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.admin.review_schemas import (
    ALLOWED_FIELD_NAMES,
    ReviewEditCreate,
    ReviewEditResponse,
    ReviewHistoryResponse,
    OverrideStatus,
    ReviewTargetType,
)
from src.domain.models import ReviewEdit

RESET_TO_AUTO_SENTINEL = "__review_reset_to_auto__"


class InvalidReviewError(Exception):
    """修订校验错误"""
    pass


class DatabaseReviewService:
    """基于数据库的人工修订服务

    管理修订记录和覆盖状态。
    使用 SQLAlchemy 会话进行持久化。
    """

    def __init__(self, session: Session) -> None:
        self.session = session

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
        db_edit = self._build_db_edit(target_type, target_id, create)
        self.session.add(db_edit)
        self.session.commit()
        self.session.refresh(db_edit)
        return self._db_to_response(db_edit)

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
        db_edits: list[ReviewEdit] = []
        try:
            for create in batch:
                if reason and not create.reason:
                    create = create.model_copy(update={"reason": reason})
                db_edits.append(self._build_db_edit(target_type, target_id, create))

            for db_edit in db_edits:
                self.session.add(db_edit)
            self.session.commit()
            for db_edit in db_edits:
                self.session.refresh(db_edit)
            return [self._db_to_response(db_edit) for db_edit in db_edits]
        except Exception:
            self.session.rollback()
            raise

    def get_edit(self, edit_id: uuid.UUID) -> ReviewEditResponse | None:
        """获取单条修订记录"""
        stmt = select(ReviewEdit).where(ReviewEdit.id == edit_id)
        db_edit = self.session.scalar(stmt)
        if db_edit is None:
            return None
        return self._db_to_response(db_edit)

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
        stmt = select(ReviewEdit).where(
            ReviewEdit.target_type == target_type,
            ReviewEdit.target_id == target_id,
        )
        if field_name:
            stmt = stmt.where(ReviewEdit.field_name == field_name)
        stmt = stmt.order_by(desc(ReviewEdit.created_at))

        db_edits = list(self.session.scalars(stmt))
        edits = [self._db_to_response(e) for e in db_edits]

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
        latest = self._get_latest_edit(target_type, target_id, field_name)
        if latest:
            if self._is_reset_to_auto_value(self._extract_edit_value(latest.new_value)):
                return OverrideStatus(
                    field_name=field_name,
                    source="auto",
                    last_manual_value=None,
                    last_manual_at=latest.created_at,
                    current_auto_value=None,
                )
            return OverrideStatus(
                field_name=field_name,
                source="manual",
                last_manual_value=self._extract_edit_value(latest.new_value),
                last_manual_at=latest.created_at,
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
        latest = self._get_latest_edit(target_type, target_id, field_name)
        if latest:
            latest_value = self._extract_edit_value(latest.new_value)
            if self._is_reset_to_auto_value(latest_value):
                return auto_value
            return latest_value
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
        original = self.get_edit(edit_id)
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

        return self.create_edit(
            target_type=original.target_type,
            target_id=original.target_id,
            create=revert,
        )

    def count(self, target_type: str | None = None) -> int:
        """统计修订记录数量"""
        stmt = select(func.count()).select_from(ReviewEdit)
        if target_type:
            stmt = stmt.where(ReviewEdit.target_type == target_type)
        return int(self.session.scalar(stmt) or 0)

    # ── 私有辅助方法 ──

    def _get_latest_edit(
        self,
        target_type: str,
        target_id: uuid.UUID,
        field_name: str,
    ) -> ReviewEditResponse | None:
        """获取指定字段的最新修订记录"""
        stmt = select(ReviewEdit).where(
            ReviewEdit.target_type == target_type,
            ReviewEdit.target_id == target_id,
            ReviewEdit.field_name == field_name,
        ).order_by(desc(ReviewEdit.created_at)).limit(1)
        db_edit = self.session.scalar(stmt)
        if db_edit is None:
            return None
        return self._db_to_response(db_edit)

    def _build_db_edit(
        self,
        target_type: str,
        target_id: uuid.UUID,
        create: ReviewEditCreate,
    ) -> ReviewEdit:
        self._validate_target_field_pair(target_type, create.field_name)
        old_value = create.old_value
        if old_value is None:
            latest = self._get_latest_edit(target_type, target_id, create.field_name)
            if latest:
                old_value = self._extract_edit_value(latest.new_value)

        return ReviewEdit(
            target_type=target_type,
            target_id=target_id,
            field_name=create.field_name,
            old_value=json.dumps(old_value) if old_value is not None else None,
            new_value=json.dumps(create.new_value) if create.new_value is not None else None,
            reason=create.reason,
            reviewer=create.reviewer,
            created_at=datetime.now(timezone.utc),
        )

    def _validate_target_field_pair(self, target_type: str, field_name: str) -> None:
        try:
            tt = ReviewTargetType(target_type)
        except ValueError:
            valid = sorted(t.value for t in ReviewTargetType)
            raise InvalidReviewError(
                f"无效的 target_type: {target_type!r}，合法值: {valid}"
            )
        allowed = ALLOWED_FIELD_NAMES.get(tt, [])
        allowed_values = [fn.value for fn in allowed]
        if field_name not in allowed_values:
            raise InvalidReviewError(
                f"target_type={target_type!r} 不允许修订字段 {field_name!r}，"
                f"允许的字段: {allowed_values}"
            )

    def _extract_edit_value(self, value: Any) -> Any:
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return value
            if parsed == RESET_TO_AUTO_SENTINEL:
                return parsed
        return value

    def _is_reset_to_auto_value(self, value: Any) -> bool:
        return value == RESET_TO_AUTO_SENTINEL

    def _db_to_response(self, db_edit: ReviewEdit) -> ReviewEditResponse:
        """将数据库模型转换为响应模型"""
        return ReviewEditResponse(
            id=db_edit.id,
            target_type=db_edit.target_type,
            target_id=db_edit.target_id,
            field_name=db_edit.field_name,
            old_value=json.loads(db_edit.old_value) if db_edit.old_value else None,
            new_value=json.loads(db_edit.new_value) if db_edit.new_value else None,
            reason=db_edit.reason,
            reviewer=db_edit.reviewer,
            source="manual",
            created_at=db_edit.created_at,
        )

    def __repr__(self) -> str:
        return f"<DatabaseReviewService total={self.count()}>"
