"""用户注册/登录：bcrypt 哈希 + PyJWT 签发 token。

依赖：
    pip install bcrypt PyJWT
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
import uuid
from functools import lru_cache
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
    invite_code: str | None = Field(default=None, max_length=24)
    phone: str | None = None
    phone_code: str | None = None


class LoginRequest(BaseModel):
    user_id: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6, max_length=64)


class SmsCodeRequest(BaseModel):
    phone: str
    purpose: str = Field(pattern=r"^(bind|reset|register)$")


class BindAccountRequest(BaseModel):
    phone: str | None = None
    phone_code: str | None = None
    wechat_id: str | None = Field(default=None, max_length=64)


class ResetPasswordRequest(BaseModel):
    phone: str
    code: str
    new_password: str = Field(..., min_length=6, max_length=64)


CONTACT_NUMBER = "17635575899"
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _normalize_phone(phone: str) -> str:
    value = re.sub(r"\s+", "", str(phone or ""))
    if not _PHONE_RE.fullmatch(value):
        raise ValueError("请输入有效的中国大陆手机号")
    return value


def _new_invite_code() -> str:
    return "KY" + "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(8))


@lru_cache(maxsize=1)
def ensure_auth_schema() -> None:
    """Apply additive account migrations and backfill invite codes safely."""

    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS invite_code VARCHAR(16)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS invited_by INTEGER REFERENCES users(id)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS wechat_id VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_invite_code ON users(invite_code) WHERE invite_code IS NOT NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone) WHERE phone IS NOT NULL",
        """
        CREATE TABLE IF NOT EXISTS password_reset_codes (
            id BIGSERIAL PRIMARY KEY,
            phone VARCHAR(20) NOT NULL,
            purpose VARCHAR(16) NOT NULL,
            user_id VARCHAR(64),
            code_hash VARCHAR(128) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            used_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "ALTER TABLE password_reset_codes ADD COLUMN IF NOT EXISTS request_ip VARCHAR(64)",
        "CREATE INDEX IF NOT EXISTS idx_password_reset_lookup ON password_reset_codes(phone, purpose, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_password_reset_ip ON password_reset_codes(request_ip, created_at DESC)",
    ]
    for statement in statements:
        db.execute(statement)

    missing = db.fetch_all("SELECT id FROM users WHERE invite_code IS NULL")
    for row in missing:
        for _ in range(20):
            code = _new_invite_code()
            try:
                db.execute(
                    "UPDATE users SET invite_code = %s WHERE id = %s AND invite_code IS NULL",
                    (code, row["id"]),
                )
                break
            except Exception:
                continue


def _create_unique_invite_code(cur) -> str:
    for _ in range(30):
        code = _new_invite_code()
        cur.execute("SELECT 1 FROM users WHERE invite_code = %s", (code,))
        if not cur.fetchone():
            return code
    raise RuntimeError("邀请码生成失败，请稍后重试")


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
    """注册新用户，可选邀请码/手机号，并为新用户生成独立邀请码。"""
    ensure_auth_schema()
    invite_input = str(req.invite_code or "").strip().upper()

    # 手机号注册：先校验短信验证码（一个手机号只能注册一个账号）。
    phone: str | None = None
    if req.phone:
        try:
            phone = _normalize_phone(req.phone)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        if not req.phone_code or not _consume_sms_code(phone, "register", req.phone_code):
            return {"success": False, "error": "手机验证码错误或已过期"}

    try:
        with db.get_cursor() as cur:
            cur.execute("SELECT id FROM users WHERE user_id = %s", (req.user_id,))
            if cur.fetchone() is not None:
                return {"success": False, "error": "用户名已被占用"}
            if phone:
                cur.execute("SELECT id FROM users WHERE phone = %s", (phone,))
                if cur.fetchone() is not None:
                    return {"success": False, "error": "该手机号已注册，请直接登录"}
            inviter_id = None
            if invite_input:
                cur.execute("SELECT id FROM users WHERE invite_code = %s", (invite_input,))
                inviter = cur.fetchone()
                if not inviter:
                    return {"success": False, "error": "邀请码不存在或已失效"}
                inviter_id = inviter["id"]
            own_invite_code = _create_unique_invite_code(cur)
            cur.execute(
                """
                INSERT INTO users (
                    user_id, password_hash, nickname, target_school, target_major,
                    invite_code, invited_by, phone, phone_verified_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    req.user_id,
                    _hash_password(req.password),
                    req.nickname or req.user_id,
                    req.target_school,
                    req.target_major,
                    own_invite_code,
                    inviter_id,
                    phone,
                    dt.datetime.now() if phone else None,
                ),
            )
    except Exception as exc:
        text = str(exc).lower()
        if "unique" in text or "duplicate" in text:
            if phone and "phone" in text:
                return {"success": False, "error": "该手机号已注册，请直接登录"}
            return {"success": False, "error": "用户名已被占用"}
        raise
    return {
        "success": True,
        "user_id": req.user_id,
        "token": _create_token(req.user_id),
        "invite_code": own_invite_code,
    }


def login_user(req: LoginRequest) -> dict[str, Any]:
    """验证密码并返回 JWT。支持用用户名或已绑定手机号登录。"""
    identifier = str(req.user_id or "").strip()
    row = db.fetch_one(
        "SELECT user_id, password_hash FROM users WHERE user_id = %s",
        (identifier,),
    )
    # 未按用户名命中且形如手机号时，再尝试用已验证的手机号登录。
    if row is None and _PHONE_RE.fullmatch(identifier):
        row = db.fetch_one(
            "SELECT user_id, password_hash FROM users WHERE phone = %s AND phone_verified_at IS NOT NULL",
            (identifier,),
        )
    if row is None or not row.get("password_hash"):
        return {"success": False, "error": "账号或密码错误"}
    if not _verify_password(req.password, row["password_hash"]):
        return {"success": False, "error": "账号或密码错误"}
    return {
        "success": True,
        "user_id": row["user_id"],
        "token": _create_token(row["user_id"]),
    }


def account_profile(user_id: str) -> dict[str, Any]:
    ensure_auth_schema()
    row = db.fetch_one(
        """
        SELECT user_id, nickname, invite_code, phone, wechat_id, phone_verified_at
        FROM users WHERE user_id = %s
        """,
        (user_id,),
    )
    if not row:
        raise ValueError("账号不存在")
    phone = str(row.get("phone") or "")
    return {
        "user_id": row["user_id"],
        "nickname": row.get("nickname") or row["user_id"],
        "invite_code": row.get("invite_code") or "",
        "phone": phone,
        "phone_masked": f"{phone[:3]}****{phone[-4:]}" if phone else "",
        "phone_verified": bool(row.get("phone_verified_at")),
        "wechat_id": row.get("wechat_id") or "",
        "customer_service": {"phone": CONTACT_NUMBER, "wechat": CONTACT_NUMBER},
    }


def change_password(user_id: str, req: ChangePasswordRequest) -> dict[str, Any]:
    row = db.fetch_one("SELECT password_hash FROM users WHERE user_id = %s", (user_id,))
    if not row or not row.get("password_hash") or not _verify_password(req.current_password, row["password_hash"]):
        return {"success": False, "error": "当前密码不正确"}
    if req.current_password == req.new_password:
        return {"success": False, "error": "新密码不能与当前密码相同"}
    db.execute(
        "UPDATE users SET password_hash = %s, password_changed_at = CURRENT_TIMESTAMP WHERE user_id = %s",
        (_hash_password(req.new_password), user_id),
    )
    return {"success": True}


def _code_digest(phone: str, purpose: str, code: str) -> str:
    secret = get_settings().jwt_secret
    return hashlib.sha256(f"{phone}:{purpose}:{code}:{secret}".encode("utf-8")).hexdigest()


def _aliyun_percent_encode(value: str) -> str:
    """阿里云 RPC 签名要求的 RFC3986 编码。"""
    encoded = urllib.parse.quote(str(value), safe="")
    return encoded.replace("+", "%20").replace("*", "%2A").replace("%7E", "~")


def _send_sms_aliyun(phone: str, code: str) -> None:
    """直接调用阿里云短信 SendSms 接口（RPC 风格，手写 HMAC-SHA1 签名）。"""
    settings = get_settings()
    params = {
        "AccessKeyId": settings.aliyun_sms_access_key_id,
        "Action": "SendSms",
        "Format": "JSON",
        "PhoneNumbers": phone,
        "RegionId": settings.aliyun_sms_region_id,
        "SignName": settings.aliyun_sms_sign_name,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "TemplateCode": settings.aliyun_sms_template_code,
        "TemplateParam": json.dumps({"code": code}, ensure_ascii=False),
        "Timestamp": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version": "2017-05-25",
    }
    canonical = "&".join(
        f"{_aliyun_percent_encode(k)}={_aliyun_percent_encode(params[k])}"
        for k in sorted(params)
    )
    string_to_sign = "POST&" + _aliyun_percent_encode("/") + "&" + _aliyun_percent_encode(canonical)
    signing_key = (settings.aliyun_sms_access_key_secret + "&").encode("utf-8")
    signature = base64.b64encode(
        hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    params["Signature"] = signature
    body = urllib.parse.urlencode(params).encode("utf-8")
    request = urllib.request.Request(
        settings.aliyun_sms_endpoint,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        raise RuntimeError(f"短信发送失败，请稍后重试（{detail[:120]}）") from exc
    except Exception as exc:
        raise RuntimeError("短信发送失败，请稍后重试") from exc
    if payload.get("Code") != "OK":
        message = payload.get("Message") or payload.get("Code") or "未知错误"
        raise RuntimeError(f"短信发送失败：{message}")


def _send_sms(phone: str, purpose: str, code: str) -> None:
    settings = get_settings()
    # 优先使用阿里云短信；未配置时回退到通用 webhook。
    if (
        settings.aliyun_sms_access_key_id
        and settings.aliyun_sms_access_key_secret
        and settings.aliyun_sms_sign_name
        and settings.aliyun_sms_template_code
    ):
        _send_sms_aliyun(phone, code)
        return
    if not settings.sms_webhook_url:
        raise RuntimeError(f"短信服务尚未配置，请联系客服 {CONTACT_NUMBER}")
    body = json.dumps(
        {"phone": phone, "code": code, "purpose": purpose, "ttl_minutes": settings.sms_code_ttl_minutes},
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if settings.sms_webhook_token:
        headers["Authorization"] = f"Bearer {settings.sms_webhook_token}"
    request = urllib.request.Request(settings.sms_webhook_url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=8) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError("短信发送失败，请稍后重试")


def request_sms_code(
    phone: str,
    purpose: str,
    user_id: str | None = None,
    request_ip: str | None = None,
) -> dict[str, Any]:
    ensure_auth_schema()
    phone = _normalize_phone(phone)
    if purpose == "bind":
        if not user_id:
            raise ValueError("请先登录")
        occupied = db.fetch_one("SELECT user_id FROM users WHERE phone = %s AND user_id <> %s", (phone, user_id))
        if occupied:
            raise ValueError("该手机号已绑定其他账号")
    elif purpose == "reset":
        row = db.fetch_one("SELECT user_id FROM users WHERE phone = %s AND phone_verified_at IS NOT NULL", (phone,))
        # Do not reveal whether a phone is registered.
        if not row:
            return {"success": True, "message": "如手机号已绑定，验证码将发送至该号码"}
    elif purpose == "register":
        exists = db.fetch_one(
            "SELECT user_id FROM users WHERE phone = %s AND phone_verified_at IS NOT NULL", (phone,)
        )
        if exists:
            raise ValueError("该手机号已注册，请直接登录或找回密码")
    else:
        raise ValueError("不支持的验证码用途")

    settings = get_settings()
    latest = db.fetch_one(
        "SELECT created_at FROM password_reset_codes WHERE phone = %s AND purpose = %s ORDER BY created_at DESC LIMIT 1",
        (phone, purpose),
    )
    if latest and latest.get("created_at"):
        elapsed = (dt.datetime.now() - latest["created_at"]).total_seconds()
        if elapsed < settings.sms_code_cooldown_seconds:
            raise ValueError(f"请在 {int(settings.sms_code_cooldown_seconds - elapsed) + 1} 秒后重试")

    # 防刷：单手机号每日上限
    day_ago = dt.datetime.now() - dt.timedelta(days=1)
    phone_count = db.fetch_one(
        "SELECT COUNT(*) AS n FROM password_reset_codes WHERE phone = %s AND created_at > %s",
        (phone, day_ago),
    )
    if phone_count and int(phone_count.get("n") or 0) >= settings.sms_daily_limit_per_phone:
        raise ValueError("该手机号今日验证码次数已达上限，请明日再试或联系客服")

    # 防刷：单 IP 每日上限（防止换号刷余额）
    if request_ip:
        ip_count = db.fetch_one(
            "SELECT COUNT(*) AS n FROM password_reset_codes WHERE request_ip = %s AND created_at > %s",
            (request_ip, day_ago),
        )
        if ip_count and int(ip_count.get("n") or 0) >= settings.sms_daily_limit_per_ip:
            raise ValueError("操作过于频繁，请稍后再试")

    code = f"{secrets.randbelow(1_000_000):06d}"
    _send_sms(phone, purpose, code)
    db.execute(
        """
        INSERT INTO password_reset_codes(phone, purpose, user_id, code_hash, expires_at, request_ip)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            phone,
            purpose,
            user_id,
            _code_digest(phone, purpose, code),
            dt.datetime.now() + dt.timedelta(minutes=settings.sms_code_ttl_minutes),
            request_ip,
        ),
    )
    return {"success": True, "message": "验证码已发送"}


def _consume_sms_code(phone: str, purpose: str, code: str, user_id: str | None = None) -> bool:
    if user_id is None:
        row = db.fetch_one(
            """
            SELECT id, code_hash FROM password_reset_codes
            WHERE phone = %s AND purpose = %s AND used_at IS NULL
              AND expires_at > CURRENT_TIMESTAMP AND attempts < 5
            ORDER BY created_at DESC LIMIT 1
            """,
            (phone, purpose),
        )
    else:
        row = db.fetch_one(
            """
            SELECT id, code_hash FROM password_reset_codes
            WHERE phone = %s AND purpose = %s AND user_id = %s AND used_at IS NULL
              AND expires_at > CURRENT_TIMESTAMP AND attempts < 5
            ORDER BY created_at DESC LIMIT 1
            """,
            (phone, purpose, user_id),
        )
    if not row:
        return False
    valid = secrets.compare_digest(row["code_hash"], _code_digest(phone, purpose, str(code or "")))
    if valid:
        db.execute("UPDATE password_reset_codes SET used_at = CURRENT_TIMESTAMP WHERE id = %s", (row["id"],))
    else:
        db.execute("UPDATE password_reset_codes SET attempts = attempts + 1 WHERE id = %s", (row["id"],))
    return valid


def bind_account(user_id: str, req: BindAccountRequest) -> dict[str, Any]:
    ensure_auth_schema()
    updates: list[str] = []
    params: list[Any] = []
    if req.phone is not None:
        phone = _normalize_phone(req.phone)
        if not req.phone_code or not _consume_sms_code(phone, "bind", req.phone_code, user_id):
            return {"success": False, "error": "手机验证码错误或已过期"}
        occupied = db.fetch_one("SELECT user_id FROM users WHERE phone = %s AND user_id <> %s", (phone, user_id))
        if occupied:
            return {"success": False, "error": "该手机号已绑定其他账号"}
        updates.extend(["phone = %s", "phone_verified_at = CURRENT_TIMESTAMP"])
        params.append(phone)
    if req.wechat_id is not None:
        wechat_id = req.wechat_id.strip()
        if wechat_id and not re.fullmatch(r"[A-Za-z0-9_\-\u4e00-\u9fff]{2,64}", wechat_id):
            return {"success": False, "error": "微信号格式不正确"}
        updates.append("wechat_id = %s")
        params.append(wechat_id or None)
    if not updates:
        return {"success": False, "error": "没有需要保存的资料"}
    params.append(user_id)
    db.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id = %s", tuple(params))
    return {"success": True, "account": account_profile(user_id)}


def reset_password(req: ResetPasswordRequest) -> dict[str, Any]:
    ensure_auth_schema()
    phone = _normalize_phone(req.phone)
    if not _consume_sms_code(phone, "reset", req.code):
        return {"success": False, "error": "手机验证码错误或已过期"}
    row = db.fetch_one("SELECT user_id FROM users WHERE phone = %s AND phone_verified_at IS NOT NULL", (phone,))
    if not row:
        return {"success": False, "error": "手机号未绑定账号"}
    db.execute(
        "UPDATE users SET password_hash = %s, password_changed_at = CURRENT_TIMESTAMP WHERE user_id = %s",
        (_hash_password(req.new_password), row["user_id"]),
    )
    return {"success": True, "user_id": row["user_id"]}


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
