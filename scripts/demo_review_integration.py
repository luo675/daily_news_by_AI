"""人工修订集成示例

展示业务层如何读取有效值（人工覆盖自动）。
"""

import uuid
from datetime import datetime, timezone

from src.config import create_session_factory
from src.admin.review_service_db import DatabaseReviewService
from src.admin.review_schemas import ReviewEditCreate, ReviewTargetType, ReviewFieldName


def demo_effective_value():
    """演示人工修订如何覆盖自动值"""
    # 创建数据库会话
    SessionLocal = create_session_factory()
    session = SessionLocal()

    try:
        service = DatabaseReviewService(session)

        # 模拟一个文档摘要的 target
        target_type = ReviewTargetType.SUMMARY
        target_id = uuid.uuid4()  # 假设的文档摘要 ID

        # 假设自动生成的摘要
        auto_summary_zh = "自动生成的中文摘要：AI 领域的最新进展..."
        auto_summary_en = "Auto-generated English summary: Latest progress in AI..."

        print("=== 初始状态 ===")
        print(f"自动摘要 (zh): {auto_summary_zh}")
        print(f"自动摘要 (en): {auto_summary_en}")

        # 检查是否有修订
        effective_zh = service.get_effective_value(
            target_type=target_type,
            target_id=target_id,
            field_name=ReviewFieldName.SUMMARY_ZH,
            auto_value=auto_summary_zh,
        )
        effective_en = service.get_effective_value(
            target_type=target_type,
            target_id=target_id,
            field_name=ReviewFieldName.SUMMARY_EN,
            auto_value=auto_summary_en,
        )
        print(f"有效摘要 (zh): {effective_zh}")
        print(f"有效摘要 (en): {effective_en}")
        print("（目前没有人工修订，所以有效值等于自动值）")

        # 创建人工修订
        print("\n=== 创建人工修订 ===")
        edit_zh = service.create_edit(
            target_type=target_type,
            target_id=target_id,
            create=ReviewEditCreate(
                field_name=ReviewFieldName.SUMMARY_ZH,
                new_value="人工修订后的中文摘要：重点突出了产品机会...",
                reason="自动摘要不够准确，需要强调产品机会",
                reviewer="owner",
            ),
        )
        print(f"已创建修订 ID: {edit_zh.id}")

        # 再次获取有效值
        effective_zh2 = service.get_effective_value(
            target_type=target_type,
            target_id=target_id,
            field_name=ReviewFieldName.SUMMARY_ZH,
            auto_value=auto_summary_zh,
        )
        effective_en2 = service.get_effective_value(
            target_type=target_type,
            target_id=target_id,
            field_name=ReviewFieldName.SUMMARY_EN,
            auto_value=auto_summary_en,
        )
        print(f"有效摘要 (zh): {effective_zh2}")
        print(f"有效摘要 (en): {effective_en2}")
        print("（中文摘要已被人工修订覆盖，英文摘要仍为自动值）")

        # 获取覆盖状态
        print("\n=== 覆盖状态 ===")
        status_zh = service.get_override_status(
            target_type=target_type,
            target_id=target_id,
            field_name=ReviewFieldName.SUMMARY_ZH,
        )
        status_en = service.get_override_status(
            target_type=target_type,
            target_id=target_id,
            field_name=ReviewFieldName.SUMMARY_EN,
        )
        print(f"中文摘要状态: source={status_zh.source}, last_manual_at={status_zh.last_manual_at}")
        print(f"英文摘要状态: source={status_en.source}")

        # 获取修订历史
        print("\n=== 修订历史 ===")
        history = service.get_history(target_type, target_id)
        print(f"总修订记录数: {history.total_count}")
        for edit in history.edits:
            print(f"  - {edit.field_name}: {edit.old_value} -> {edit.new_value} ({edit.created_at})")

        # 撤销修订
        print("\n=== 撤销修订 ===")
        revert = service.revert_edit(edit_zh.id, reviewer="owner")
        if revert:
            print(f"已撤销修订，新修订 ID: {revert.id}")

        # 再次检查有效值
        effective_zh3 = service.get_effective_value(
            target_type=target_type,
            target_id=target_id,
            field_name=ReviewFieldName.SUMMARY_ZH,
            auto_value=auto_summary_zh,
        )
        print(f"撤销后有效摘要 (zh): {effective_zh3}")
        print("（撤销后恢复为自动值）")

    finally:
        session.close()


def demo_batch_edits():
    """演示批量修订"""
    SessionLocal = create_session_factory()
    session = SessionLocal()

    try:
        service = DatabaseReviewService(session)
        target_type = ReviewTargetType.OPPORTUNITY_SCORE
        target_id = uuid.uuid4()

        batch = [
            ReviewEditCreate(
                field_name=ReviewFieldName.NEED_REALNESS,
                new_value=8,
                reason="需求真实性较高",
            ),
            ReviewEditCreate(
                field_name=ReviewFieldName.MARKET_GAP,
                new_value=9,
                reason="市场空白明显",
            ),
        ]

        print("\n=== 批量修订 ===")
        edits = service.create_batch(target_type, target_id, batch, reason="整体调整机会评分")
        for edit in edits:
            print(f"  - {edit.field_name}: {edit.new_value}")

    finally:
        session.close()


if __name__ == "__main__":
    print("人工修订集成示例")
    print("=" * 50)
    demo_effective_value()
    demo_batch_edits()
    print("\n示例完成。")