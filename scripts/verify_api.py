"""验证 API 骨架完整性

检查：
1. FastAPI app 能正常创建
2. 所有 9 个路由端点已注册
3. 统一响应结构正确
4. 鉴权中间件工作
5. Schema 与 api_spec.md 一致
"""

import sys
import io
import uuid

# Windows 终端兼容
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.schemas import (
    UnifiedResponse,
    ErrorResponse,
    BilingualText,
    MetaInfo,
    SearchRequest,
    BriefGenerateRequest,
    WatchlistCreateRequest,
    ReviewPatchRequest,
)


def test_app_creation() -> None:
    """测试应用创建"""
    app = create_app()
    assert app is not None
    assert app.title == "Daily News API"
    print("  [PASS] FastAPI 应用创建")


def test_routes_registered() -> None:
    """测试路由注册"""
    app = create_app()
    routes = [route.path for route in app.routes if hasattr(route, "path")]

    expected = [
        "/api/v1/search",
        "/api/v1/briefs/latest",
        "/api/v1/briefs/generate",
        "/api/v1/opportunities",
        "/api/v1/topics/{topic_id}",
        "/api/v1/watchlist",
        "/api/v1/reviews/{target_type}/{target_id}",
        "/api/v1/health",
    ]

    for ep in expected:
        # POST 和 GET 共享路径，检查路径是否存在
        assert ep in routes, f"缺少路由: {ep}"

    print(f"  [PASS] 路由注册 ({len(expected)} 个端点)")


def test_health_no_auth() -> None:
    """测试 health 端点无需鉴权"""
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    print("  [PASS] Health 端点（无需鉴权）")


def test_health_with_auth() -> None:
    """测试 health 端点带鉴权时返回配额"""
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/health", headers={"X-API-Key": "dn-dev-key-change-in-production"})
    assert response.status_code == 200
    data = response.json()
    assert data["quota"] is not None
    assert "limit" in data["quota"]
    print("  [PASS] Health 端点（带鉴权返回配额）")


def test_auth_required() -> None:
    """测试需要鉴权的端点"""
    app = create_app()
    client = TestClient(app)

    # 无密钥访问 search 应返回 401
    response = client.post("/api/v1/search", json={"query": "test"})
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    print("  [PASS] 鉴权拦截（无密钥返回 401）")


def test_auth_invalid_key() -> None:
    """测试无效密钥"""
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/api/v1/search",
        json={"query": "test"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401
    print("  [PASS] 鉴权拦截（无效密钥返回 401）")


def test_search_endpoint() -> None:
    """测试搜索端点"""
    app = create_app()
    client = TestClient(app)
    api_key = "dn-dev-key-change-in-production"

    response = client.post(
        "/api/v1/search",
        json={"query": "AI agents", "topics": ["agent"], "limit": 5},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "evidence" in data
    assert "opportunities" in data
    assert "risks" in data
    assert "uncertainties" in data
    assert "meta" in data
    print("  [PASS] POST /api/v1/search")


def test_briefs_latest() -> None:
    """测试获取最新日报"""
    app = create_app()
    client = TestClient(app)
    api_key = "dn-dev-key-change-in-production"

    response = client.get("/api/v1/briefs/latest", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    data = response.json()
    assert "date" in data
    assert "summary" in data
    print("  [PASS] GET /api/v1/briefs/latest")


def test_briefs_generate() -> None:
    """测试生成日报"""
    app = create_app()
    client = TestClient(app)
    api_key = "dn-dev-key-change-in-production"

    response = client.post(
        "/api/v1/briefs/generate",
        json={"watchlist_scope": True},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    print("  [PASS] POST /api/v1/briefs/generate")


def test_opportunities() -> None:
    """测试机会列表"""
    app = create_app()
    client = TestClient(app)
    api_key = "dn-dev-key-change-in-production"

    response = client.get("/api/v1/opportunities", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    print("  [PASS] GET /api/v1/opportunities")


def test_topics() -> None:
    """测试主题详情"""
    app = create_app()
    client = TestClient(app)
    api_key = "dn-dev-key-change-in-production"

    response = client.get("/api/v1/topics/test-topic-id", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    print("  [PASS] GET /api/v1/topics/{id}")


def test_watchlist_get() -> None:
    """测试获取关注列表"""
    app = create_app()
    client = TestClient(app)
    api_key = "dn-dev-key-change-in-production"

    response = client.get("/api/v1/watchlist", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    print("  [PASS] GET /api/v1/watchlist")


def test_watchlist_post() -> None:
    """测试新增关注项"""
    app = create_app()
    client = TestClient(app)
    api_key = "dn-dev-key-change-in-production"

    response = client.post(
        "/api/v1/watchlist",
        json={"item_type": "person", "item_value": "Sam Altman"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    print("  [PASS] POST /api/v1/watchlist")


def test_reviews() -> None:
    """测试人工修订"""
    app = create_app()
    client = TestClient(app)
    api_key = "dn-dev-key-change-in-production"
    target_id = str(uuid.uuid4())

    response = client.patch(
        f"/api/v1/reviews/summary/{target_id}",
        json={"field_name": "summary_zh", "new_value": "修订后的摘要"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    print("  [PASS] PATCH /api/v1/reviews/{target_type}/{target_id}")


def test_schemas() -> None:
    """测试 Schema 结构"""
    # UnifiedResponse
    resp = UnifiedResponse(
        summary=BilingualText(zh="测试", en="test"),
        evidence=[],
        opportunities=[],
        risks=[],
        uncertainties=[],
        related_topics=["AI"],
        meta=MetaInfo(result_count=0),
    )
    assert resp.summary.zh == "测试"
    assert resp.summary.en == "test"

    # ErrorResponse
    err = ErrorResponse(error_code="test_error", message="Test error")
    assert err.error_code == "test_error"

    # SearchRequest
    req = SearchRequest(query="AI agents")
    assert req.query == "AI agents"
    assert req.limit == 10

    print("  [PASS] Schema 结构验证")


def main() -> None:
    print("=" * 60)
    print("API 骨架验证")
    print("=" * 60)

    print("\n1. 应用创建:")
    test_app_creation()

    print("\n2. 路由注册:")
    test_routes_registered()

    print("\n3. 鉴权:")
    test_auth_required()
    test_auth_invalid_key()
    test_health_no_auth()
    test_health_with_auth()

    print("\n4. 端点测试:")
    test_search_endpoint()
    test_briefs_latest()
    test_briefs_generate()
    test_opportunities()
    test_topics()
    test_watchlist_get()
    test_watchlist_post()
    test_reviews()

    print("\n5. Schema 结构:")
    test_schemas()

    print("\n" + "=" * 60)
    print("所有 API 骨架测试通过!")
    print("=" * 60)


if __name__ == "__main__":
    main()
