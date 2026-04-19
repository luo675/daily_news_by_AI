"""API 鉴权与配额中间件

对应 TC-19（API 鉴权与配额卡）。

第一阶段策略：
  - 单用户密钥鉴权
  - 配额控制：按 token 或返回条数限制
  - 预留升级到多密钥的接口

实现方式：
  - FastAPI 依赖注入
  - 密钥通过 X-API-Key 请求头传递
  - 配额检查预留接口，当前仅做计数
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader


# ──────────────────────────── 配置 ────────────────────────────

# 从环境变量读取 API 密钥（明文），运行时只存储哈希
API_KEY_ENV = "DAILY_NEWS_API_KEY"
DEFAULT_API_KEY = "dn-dev-key-change-in-production"  # 仅开发用


def _get_configured_key() -> str:
    """获取配置的 API 密钥"""
    return os.getenv(API_KEY_ENV, DEFAULT_API_KEY)


def _hash_key(key: str) -> str:
    """对密钥做 SHA-256 哈希"""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# ──────────────────────────── 鉴权 ────────────────────────────

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class APIKeyAuth:
    """API 密钥鉴权

    第一阶段：单用户密钥，从环境变量读取。
    后续可切换到数据库查询 api_keys 表。
    """

    def __init__(self) -> None:
        self._configured_key_hash: str | None = None

    @property
    def configured_key_hash(self) -> str:
        """懒加载配置密钥的哈希"""
        if self._configured_key_hash is None:
            self._configured_key_hash = _hash_key(_get_configured_key())
        return self._configured_key_hash

    def verify_key(self, provided_key: str | None) -> str:
        """验证 API 密钥

        Args:
            provided_key: 请求中提供的密钥

        Returns:
            验证通过的密钥哈希

        Raises:
            HTTPException: 密钥无效
        """
        if provided_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "missing_api_key", "message": "X-API-Key header is required"},
            )

        provided_hash = _hash_key(provided_key)
        if provided_hash != self.configured_key_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "invalid_api_key", "message": "Invalid API key"},
            )

        return provided_hash


# 全局鉴权实例
_auth = APIKeyAuth()


async def require_api_key(api_key: Annotated[str | None, Depends(api_key_header)]) -> str:
    """FastAPI 依赖：要求有效的 API 密钥"""
    return _auth.verify_key(api_key)


async def optional_api_key(api_key: Annotated[str | None, Depends(api_key_header)]) -> str | None:
    """FastAPI 依赖：可选 API 密钥（health 等端点使用）"""
    if api_key is None:
        return None
    return _auth.verify_key(api_key)


# ──────────────────────────── 配额 ────────────────────────────


class QuotaTracker:
    """配额追踪器

    第一阶段：内存计数，不做持久化。
    后续可切换到 Redis 或数据库。
    """

    def __init__(self, quota_limit: int = 100000, quota_mode: str = "token") -> None:
        self.quota_limit = quota_limit
        self.quota_mode = quota_mode
        self._used: int = 0
        self._last_reset: datetime = datetime.now(timezone.utc)

    def check_quota(self) -> bool:
        """检查是否还有配额"""
        return self._used < self.quota_limit

    def consume(self, amount: int = 1) -> None:
        """消耗配额"""
        self._used += amount

    def reset(self) -> None:
        """重置配额"""
        self._used = 0
        self._last_reset = datetime.now(timezone.utc)

    @property
    def remaining(self) -> int:
        return max(0, self.quota_limit - self._used)

    @property
    def status(self) -> dict:
        """配额状态（用于 health 端点）"""
        return {
            "mode": self.quota_mode,
            "limit": self.quota_limit,
            "used": self._used,
            "remaining": self.remaining,
            "last_reset": self._last_reset.isoformat(),
        }


# 全局配额追踪实例
_quota_tracker = QuotaTracker()


async def check_quota(request: Request) -> None:
    """FastAPI 依赖：检查配额"""
    if not _quota_tracker.check_quota():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error_code": "quota_exceeded",
                "message": "API quota exceeded",
                "details": {
                    "quota_mode": _quota_tracker.quota_mode,
                    "quota_limit": _quota_tracker.quota_limit,
                },
            },
        )
    _quota_tracker.consume()


def get_quota_tracker() -> QuotaTracker:
    """获取全局配额追踪器"""
    return _quota_tracker
