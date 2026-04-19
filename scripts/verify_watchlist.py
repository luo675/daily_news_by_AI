"""验证 watchlist 模块完整性

检查：
1. 七类对象类型支持
2. 优先级和分组功能
3. 状态流转（active/paused/removed）
4. CRUD 操作
5. 权重计算
6. 分组视图
"""

import sys
import io

# Windows 终端兼容
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from uuid import UUID

from src.watchlist.schemas import (
    WatchlistItemCreate,
    WatchlistItemUpdate,
    WatchlistItemResponse,
    WatchlistGroup,
    ItemType,
    PriorityLevel,
    WatchlistStatus,
)
from src.watchlist.service import WatchlistService, DuplicateItemError, ItemNotFoundError
from src.watchlist.weight import WatchlistWeightCalculator


def test_seven_item_types() -> None:
    """测试七类对象类型"""
    service = WatchlistService()
    test_items = [
        ("Sam Altman", ItemType.PERSON),
        ("OpenAI", ItemType.COMPANY),
        ("GPT-5", ItemType.PRODUCT),
        ("Claude 4", ItemType.MODEL),
        ("AI Agents", ItemType.TOPIC),
        ("AI Coding Tools", ItemType.TRACK),
        ("chain-of-thought", ItemType.KEYWORD),
    ]
    for value, itype in test_items:
        item = service.add(WatchlistItemCreate(item_type=itype, item_value=value))
        assert item.item_type == itype
        assert item.item_value == value
        assert item.status == WatchlistStatus.ACTIVE

    assert service.count() == 7
    print("  [PASS] 七类对象类型支持")


def test_priority_levels() -> None:
    """测试优先级"""
    service = WatchlistService()

    # 高优先级
    h = service.add(WatchlistItemCreate(
        item_type=ItemType.PERSON, item_value="Andrej Karpathy", priority_level=PriorityLevel.HIGH
    ))
    assert h.priority_level == PriorityLevel.HIGH

    # 中优先级（默认）
    m = service.add(WatchlistItemCreate(
        item_type=ItemType.COMPANY, item_value="Anthropic"
    ))
    assert m.priority_level == PriorityLevel.MEDIUM

    # 低优先级
    l = service.add(WatchlistItemCreate(
        item_type=ItemType.KEYWORD, item_value="RAG", priority_level=PriorityLevel.LOW
    ))
    assert l.priority_level == PriorityLevel.LOW

    # 按优先级查询
    high_items = service.list_by_priority(PriorityLevel.HIGH)
    assert len(high_items) == 1
    assert high_items[0].item_value == "Andrej Karpathy"

    print("  [PASS] 优先级功能")


def test_group_name() -> None:
    """测试分组名"""
    service = WatchlistService()

    service.add(WatchlistItemCreate(
        item_type=ItemType.PERSON, item_value="Sam Altman", group_name="AI Leaders"
    ))
    service.add(WatchlistItemCreate(
        item_type=ItemType.PERSON, item_value="Andrej Karpathy", group_name="AI Leaders"
    ))
    service.add(WatchlistItemCreate(
        item_type=ItemType.COMPANY, item_value="OpenAI", group_name="Big Tech"
    ))

    ai_leaders = service.list_by_group("AI Leaders")
    assert len(ai_leaders) == 2

    big_tech = service.list_by_group("Big Tech")
    assert len(big_tech) == 1

    print("  [PASS] 分组名功能")


def test_status_transitions() -> None:
    """测试状态流转"""
    service = WatchlistService()

    item = service.add(WatchlistItemCreate(
        item_type=ItemType.PERSON, item_value="Test Person"
    ))
    assert item.status == WatchlistStatus.ACTIVE

    # 暂停
    paused = service.pause(item.id)
    assert paused.status == WatchlistStatus.PAUSED

    # 恢复
    resumed = service.resume(item.id)
    assert resumed.status == WatchlistStatus.ACTIVE

    # 移除（软删除）
    removed = service.remove(item.id)
    assert removed.status == WatchlistStatus.REMOVED

    # 活跃列表不包含已移除项
    active = service.list_active()
    assert len(active) == 0

    print("  [PASS] 状态流转（active -> paused -> active -> removed）")


def test_duplicate_prevention() -> None:
    """测试重复项防护"""
    service = WatchlistService()

    service.add(WatchlistItemCreate(
        item_type=ItemType.PERSON, item_value="Sam Altman"
    ))

    try:
        service.add(WatchlistItemCreate(
            item_type=ItemType.PERSON, item_value="Sam Altman"
        ))
        assert False, "应该抛出 DuplicateItemError"
    except DuplicateItemError:
        pass

    # 不同类型同名可以
    item = service.add(WatchlistItemCreate(
        item_type=ItemType.COMPANY, item_value="Sam Altman"  # 作为公司名（虽然不合理，但类型不同）
    ))
    assert item.item_type == ItemType.COMPANY

    print("  [PASS] 重复项防护")


def test_update() -> None:
    """测试更新操作"""
    service = WatchlistService()

    item = service.add(WatchlistItemCreate(
        item_type=ItemType.TOPIC, item_value="AI Safety"
    ))

    # 更新优先级
    updated = service.update(item.id, WatchlistItemUpdate(priority_level=PriorityLevel.HIGH))
    assert updated.priority_level == PriorityLevel.HIGH

    # 更新分组
    updated = service.update(item.id, WatchlistItemUpdate(group_name="Safety Topics"))
    assert updated.group_name == "Safety Topics"

    # 更新备注
    updated = service.update(item.id, WatchlistItemUpdate(notes="Very important topic"))
    assert updated.notes == "Very important topic"

    print("  [PASS] 更新操作")


def test_group_views() -> None:
    """测试分组视图"""
    service = WatchlistService()

    service.add(WatchlistItemCreate(item_type=ItemType.PERSON, item_value="Person A"))
    service.add(WatchlistItemCreate(item_type=ItemType.COMPANY, item_value="Company A"))
    service.add(WatchlistItemCreate(
        item_type=ItemType.KEYWORD, item_value="keyword1", priority_level=PriorityLevel.HIGH
    ))
    service.add(WatchlistItemCreate(
        item_type=ItemType.KEYWORD, item_value="keyword2", priority_level=PriorityLevel.LOW
    ))

    # 按类型分组
    type_groups = service.group_by_type()
    assert len(type_groups) == 7  # 七种类型都有分组（包括空的）
    person_group = next(g for g in type_groups if g.group_key == ItemType.PERSON)
    assert person_group.count == 1

    # 按优先级分组
    priority_groups = service.group_by_priority()
    assert len(priority_groups) == 3
    high_group = next(g for g in priority_groups if g.group_key == PriorityLevel.HIGH)
    assert high_group.count == 1

    print("  [PASS] 分组视图")


def test_weight_calculator() -> None:
    """测试权重计算"""
    service = WatchlistService()

    service.add(WatchlistItemCreate(
        item_type=ItemType.PERSON, item_value="VIP Person", priority_level=PriorityLevel.HIGH
    ))
    service.add(WatchlistItemCreate(
        item_type=ItemType.COMPANY, item_value="Normal Company", priority_level=PriorityLevel.MEDIUM
    ))
    service.add(WatchlistItemCreate(
        item_type=ItemType.KEYWORD, item_value="Low Keyword", priority_level=PriorityLevel.LOW
    ))

    calculator = WatchlistWeightCalculator()
    items = service.list_active()

    # 单项权重
    vip = next(i for i in items if i.item_value == "VIP Person")
    assert calculator.item_weight(vip) == 2.0  # HIGH * 1.0

    normal = next(i for i in items if i.item_value == "Normal Company")
    assert calculator.item_weight(normal) == 1.5  # MEDIUM * 1.0

    low = next(i for i in items if i.item_value == "Low Keyword")
    assert calculator.item_weight(low) == 1.0  # LOW * 1.0

    # 总提升分数
    total = calculator.compute_boost(items)
    assert total == 4.5  # 2.0 + 1.5 + 1.0

    # 带匹配条件的提升分数
    person_boost = calculator.compute_boost(items, matched_types={ItemType.PERSON})
    assert person_boost == 2.0

    # 高优先级值集合
    high_values = calculator.get_high_priority_values(items)
    assert high_values == {"VIP Person"}

    print("  [PASS] 权重计算")


def test_find_by_type_value() -> None:
    """测试按类型+值查找"""
    service = WatchlistService()

    service.add(WatchlistItemCreate(
        item_type=ItemType.PERSON, item_value="Sam Altman"
    ))

    found = service.find_by_type_value(ItemType.PERSON, "Sam Altman")
    assert found is not None
    assert found.item_value == "Sam Altman"

    not_found = service.find_by_type_value(ItemType.COMPANY, "Sam Altman")
    assert not_found is None

    print("  [PASS] 按类型+值查找")


def main() -> None:
    print("=" * 60)
    print("Watchlist 模块验证")
    print("=" * 60)

    print("\n1. 对象类型:")
    test_seven_item_types()

    print("\n2. 优先级:")
    test_priority_levels()

    print("\n3. 分组名:")
    test_group_name()

    print("\n4. 状态流转:")
    test_status_transitions()

    print("\n5. 重复项防护:")
    test_duplicate_prevention()

    print("\n6. 更新操作:")
    test_update()

    print("\n7. 分组视图:")
    test_group_views()

    print("\n8. 权重计算:")
    test_weight_calculator()

    print("\n9. 按类型+值查找:")
    test_find_by_type_value()

    print("\n" + "=" * 60)
    print("所有 Watchlist 测试通过!")
    print("=" * 60)


if __name__ == "__main__":
    main()
