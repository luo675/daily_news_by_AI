"""验证人工修订模块完整性

检查：
1. 可修订字段覆盖 TC-20 要求
2. target_type + field_name 校验
3. 审计记录保存
4. 人工覆盖自动逻辑
5. 修订历史查询
6. 撤销功能
7. API 端点集成
"""

import sys
import io

# Windows 终端兼容
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import uuid

from src.admin.review_schemas import (
    ReviewTargetType,
    ReviewFieldName,
    ReviewEditCreate,
    ReviewEditResponse,
    ReviewHistoryResponse,
    OverrideStatus,
    ALLOWED_FIELD_NAMES,
)
from src.admin.review_service import ReviewService, InvalidReviewError


def test_target_types() -> None:
    """测试修订目标类型覆盖 TC-20 要求"""
    required = {"summary", "tags", "opportunity_score", "conclusion", "priority", "topic", "uncertainty", "risk"}
    actual = {t.value for t in ReviewTargetType}
    assert required == actual, f"缺少目标类型: {required - actual}"
    print("  [PASS] 修订目标类型覆盖 TC-20 要求（8 种）")


def test_allowed_fields() -> None:
    """测试每种目标类型有允许的字段列表"""
    for tt in ReviewTargetType:
        assert tt in ALLOWED_FIELD_NAMES, f"缺少 {tt} 的字段映射"
        assert len(ALLOWED_FIELD_NAMES[tt]) > 0, f"{tt} 没有允许的字段"

    # 关键字段检查
    summary_fields = [fn.value for fn in ALLOWED_FIELD_NAMES[ReviewTargetType.SUMMARY]]
    assert "summary_zh" in summary_fields
    assert "summary_en" in summary_fields

    opp_fields = [fn.value for fn in ALLOWED_FIELD_NAMES[ReviewTargetType.OPPORTUNITY_SCORE]]
    assert "need_realness" in opp_fields
    assert "market_gap" in opp_fields
    assert "total_score" in opp_fields
    assert "uncertainty" in opp_fields

    print(f"  [PASS] 字段映射完整（{len(ALLOWED_FIELD_NAMES)} 种目标类型）")


def test_create_edit() -> None:
    """测试创建修订记录"""
    service = ReviewService()
    target_id = uuid.uuid4()

    edit = service.create_edit(
        target_type="summary",
        target_id=target_id,
        create=ReviewEditCreate(
            field_name="summary_zh",
            new_value="人工修订的中文摘要",
            old_value="自动生成的中文摘要",
            reason="自动摘要不准确",
        ),
    )

    assert edit.target_type == "summary"
    assert edit.field_name == "summary_zh"
    assert edit.new_value == "人工修订的中文摘要"
    assert edit.old_value == "自动生成的中文摘要"
    assert edit.source == "manual"
    assert edit.reviewer == "owner"
    print("  [PASS] 创建修订记录")


def test_invalid_target_type() -> None:
    """测试无效 target_type"""
    service = ReviewService()

    try:
        service.create_edit(
            target_type="invalid_type",
            target_id=uuid.uuid4(),
            create=ReviewEditCreate(field_name="summary_zh", new_value="x"),
        )
        assert False, "应该抛出 InvalidReviewError"
    except InvalidReviewError:
        pass

    print("  [PASS] 无效 target_type 校验")


def test_invalid_field_name() -> None:
    """测试不允许的 field_name"""
    service = ReviewService()

    # summary 目标不允许修订 need_realness
    try:
        service.create_edit(
            target_type="summary",
            target_id=uuid.uuid4(),
            create=ReviewEditCreate(field_name="need_realness", new_value=8),
        )
        assert False, "应该抛出 InvalidReviewError"
    except InvalidReviewError:
        pass

    print("  [PASS] 不允许的 field_name 校验")


def test_audit_trail() -> None:
    """测试审计记录"""
    service = ReviewService()
    target_id = uuid.uuid4()

    # 创建两条修订
    service.create_edit(
        target_type="summary",
        target_id=target_id,
        create=ReviewEditCreate(
            field_name="summary_zh",
            new_value="第一次修订",
            old_value="原始值",
        ),
    )
    service.create_edit(
        target_type="summary",
        target_id=target_id,
        create=ReviewEditCreate(
            field_name="summary_en",
            new_value="First revision",
            old_value="Original",
        ),
    )

    # 查询历史
    history = service.get_history("summary", target_id)
    assert history.total_count == 2
    assert len(history.edits) == 2

    print("  [PASS] 审计记录保存")


def test_override_logic() -> None:
    """测试人工覆盖自动逻辑"""
    service = ReviewService()
    target_id = uuid.uuid4()

    # 自动值为 5
    auto_value = 5

    # 没有人工修订时，返回自动值
    effective = service.get_effective_value("opportunity_score", target_id, "need_realness", auto_value)
    assert effective == 5

    # 人工修订为 8
    service.create_edit(
        target_type="opportunity_score",
        target_id=target_id,
        create=ReviewEditCreate(
            field_name="need_realness",
            new_value=8,
            old_value=5,
        ),
    )

    # 人工值覆盖自动值
    effective = service.get_effective_value("opportunity_score", target_id, "need_realness", auto_value)
    assert effective == 8

    # 覆盖状态
    status = service.get_override_status("opportunity_score", target_id, "need_realness")
    assert status.source == "manual"
    assert status.last_manual_value == 8

    print("  [PASS] 人工覆盖自动逻辑")


def test_latest_values() -> None:
    """测试最新值聚合"""
    service = ReviewService()
    target_id = uuid.uuid4()

    # 多次修订同一字段
    service.create_edit(
        target_type="summary",
        target_id=target_id,
        create=ReviewEditCreate(field_name="summary_zh", new_value="第一次", old_value="原始"),
    )
    service.create_edit(
        target_type="summary",
        target_id=target_id,
        create=ReviewEditCreate(field_name="summary_zh", new_value="第二次", old_value="第一次"),
    )
    service.create_edit(
        target_type="summary",
        target_id=target_id,
        create=ReviewEditCreate(field_name="summary_en", new_value="Second", old_value="Original"),
    )

    history = service.get_history("summary", target_id)
    assert history.latest_values["summary_zh"] == "第二次"  # 最新值
    assert history.latest_values["summary_en"] == "Second"

    print("  [PASS] 最新值聚合")


def test_revert() -> None:
    """测试撤销修订"""
    service = ReviewService()
    target_id = uuid.uuid4()

    # 创建修订
    edit = service.create_edit(
        target_type="tags",
        target_id=target_id,
        create=ReviewEditCreate(
            field_name="tags",
            new_value=["AI", "修订后"],
            old_value=["AI", "原始"],
        ),
    )

    # 撤销
    revert = service.revert_edit(edit.id)
    assert revert is not None
    assert revert.new_value == ["AI", "原始"]  # 恢复为旧值
    assert revert.old_value == ["AI", "修订后"]

    # 覆盖状态应更新
    effective = service.get_effective_value("tags", target_id, "tags", ["AI", "auto"])
    assert effective == ["AI", "原始"]  # 撤销后的值

    print("  [PASS] 撤销修订")


def test_batch_edit() -> None:
    """测试批量修订"""
    service = ReviewService()
    target_id = uuid.uuid4()

    results = service.create_batch(
        target_type="opportunity_score",
        target_id=target_id,
        batch=[
            ReviewEditCreate(field_name="need_realness", new_value=9, old_value=5),
            ReviewEditCreate(field_name="market_gap", new_value=8, old_value=6),
            ReviewEditCreate(field_name="feasibility", new_value=7, old_value=4),
        ],
        reason="整体重新评估",
    )

    assert len(results) == 3
    assert all(r.reason == "整体重新评估" for r in results)

    # 检查覆盖状态
    effective = service.get_effective_value("opportunity_score", target_id, "need_realness", 5)
    assert effective == 9

    print("  [PASS] 批量修订")


def test_api_integration() -> None:
    """测试 API 端点集成"""
    from fastapi.testclient import TestClient
    from src.api.app import create_app

    app = create_app()
    client = TestClient(app)
    api_key = "dn-dev-key-change-in-production"

    # PATCH 修订
    response = client.patch(
        "/api/v1/reviews/summary/test-id-123",
        json={
            "field_name": "summary_zh",
            "new_value": "API 修订的摘要",
            "old_value": "自动摘要",
            "reason": "测试 API",
        },
        headers={"X-API-Key": api_key},
    )
    # test-id-123 不是有效 UUID
    assert response.status_code == 400

    # 使用有效 UUID
    valid_uuid = str(uuid.uuid4())
    response = client.patch(
        f"/api/v1/reviews/summary/{valid_uuid}",
        json={
            "field_name": "summary_zh",
            "new_value": "API 修订的摘要",
            "old_value": "自动摘要",
            "reason": "测试 API",
        },
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["field_name"] == "summary_zh"
    assert data["new_value"] == "API 修订的摘要"

    # GET 修订历史
    response = client.get(
        f"/api/v1/reviews/summary/{valid_uuid}",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] >= 1

    print("  [PASS] API 端点集成")


def main() -> None:
    print("=" * 60)
    print("人工修订模块验证")
    print("=" * 60)

    print("\n1. 目标类型覆盖:")
    test_target_types()

    print("\n2. 字段映射:")
    test_allowed_fields()

    print("\n3. 创建修订:")
    test_create_edit()

    print("\n4. 校验逻辑:")
    test_invalid_target_type()
    test_invalid_field_name()

    print("\n5. 审计记录:")
    test_audit_trail()

    print("\n6. 人工覆盖自动:")
    test_override_logic()

    print("\n7. 最新值聚合:")
    test_latest_values()

    print("\n8. 撤销修订:")
    test_revert()

    print("\n9. 批量修订:")
    test_batch_edit()

    print("\n10. API 集成:")
    test_api_integration()

    print("\n" + "=" * 60)
    print("所有人工修订模块测试通过!")
    print("=" * 60)


if __name__ == "__main__":
    main()
