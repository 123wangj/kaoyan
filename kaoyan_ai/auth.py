"""用户注册/登录：bcrypt 哈希 + PyJWT 签发 token。

依赖：
    pip install bcrypt PyJWT
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

import bcrypt
import jwt
from fastapi import Cookie, Header, HTTPException
from pydantic import BaseModel, Field

from kaoyan_ai import db
from kaoyan_ai.config import get_settings


# ============================================================
# Pydantic models
# ============================================================
class RegisterRequest(BaseModel):
    user_id: str = Field(..., min_length=2, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(..., min_length=6, max_length=64)
    nickname: str | None = Field(default=None, max_length=32)
    target_school: str | None = None
    target_major: str | None = None


class LoginRequest(BaseModel):
    user_id: str
    password: str


# ============================================================
# 工具：密码哈希 & JWT
# ============================================================
def _hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=10)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _create_token(user_id: str) -> str:
    settings = get_settings()
    secret = getattr(settings, "jwt_secret", "kaoyan-ai-dev-secret-change-me")
    expires_hours = int(getattr(settings, "jwt_expires_hours", 24 * 7))
    payload = {
        "sub": user_id,
        "iat": dt.datetime.utcnow(),
        "exp": dt.datetime.utcnow() + dt.timedelta(hours=expires_hours),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any] | None:
    """解析 JWT；失败返回 None。"""
    settings = get_settings()
    secret = getattr(settings, "jwt_secret", "kaoyan-ai-dev-secret-change-me")
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except Exception:
        return None


# ============================================================
# 业务
# ============================================================
def register_user(req: RegisterRequest) -> dict[str, Any]:
    """注册新用户。返回 dict，统一给 API 层。"""
    existing = db.fetch_one("SELECT id FROM users WHERE user_id = %s", (req.user_id,))
    if existing is not None:
        return {"success": False, "error": "用户名已被占用"}

    pwd_hash = _hash_password(req.password)
    db.execute(
        """
        INSERT INTO users (user_id, password_hash, nickname, target_school, target_major)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (req.user_id, pwd_hash, req.nickname or req.user_id, req.target_school, req.target_major),
    )
    return {
        "success": True,
        "user_id": req.user_id,
        "token": _create_token(req.user_id),
    }


def login_user(req: LoginRequest) -> dict[str, Any]:
    """验证密码并返回 JWT。"""
    row = db.fetch_one(
        "SELECT id, password_hash FROM users WHERE user_id = %s",
        (req.user_id,),
    )
    if row is None or not row.get("password_hash"):
        return {"success": False, "error": "用户名或密码错误"}
    if not _verify_password(req.password, row["password_hash"]):
        return {"success": False, "error": "用户名或密码错误"}
    return {
        "success": True,
        "user_id": req.user_id,
        "token": _create_token(req.user_id),
    }


# ============================================================
# FastAPI 依赖：从 Authorization: Bearer <token> 解析当前用户
# ============================================================
def get_current_user(
    authorization: str | None = Header(default=None),
    kaoyan_session: str | None = Cookie(default=None),
) -> str:
    """从 Bearer token 解析 user_id。

    兼容策略：
      - 有 token 且有效 -> 用 token 里的 sub
      - 无 token 或 token 无效 -> 回退到 "u1"（保持与历史默认一致）
    """
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = decode_token(token)
        if payload and payload.get("sub"):
            return str(payload["sub"])
    if kaoyan_session:
        payload = decode_token(kaoyan_session)
        if payload and payload.get("sub"):
            return str(payload["sub"])
    return "u1"


def require_user(
    authorization: str | None = Header(default=None),
    kaoyan_session: str | None = Cookie(default=None),
) -> str:
    """严格模式：没有有效 token 时抛 401。"""
    candidates: list[str] = []
    if authorization and authorization.lower().startswith("bearer "):
        candidates.append(authorization.split(" ", 1)[1].strip())
    if kaoyan_session:
        candidates.append(kaoyan_session)
    if not candidates:
        raise HTTPException(status_code=401, detail="missing token")
    for token in candidates:
        payload = decode_token(token)
        if payload and payload.get("sub"):
            return str(payload["sub"])
    raise HTTPException(status_code=401, detail="invalid or expired token")
