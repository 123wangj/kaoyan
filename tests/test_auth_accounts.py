from __future__ import annotations

from contextlib import contextmanager

import pytest

from kaoyan_ai import auth
from kaoyan_ai import api


class _RegisterCursor:
    def __init__(self):
        self.last_query = ""
        self.last_params = None
        self.insert_params = None

    def execute(self, query, params=None):
        self.last_query = " ".join(str(query).split())
        self.last_params = params
        if self.last_query.startswith("INSERT INTO users"):
            self.insert_params = params

    def fetchone(self):
        if "WHERE user_id" in self.last_query:
            return None
        if "WHERE invite_code" in self.last_query and "SELECT id" in self.last_query:
            return {"id": 7} if self.last_params == ("KYFRIEND1",) else None
        return None


def test_registration_accepts_optional_inviter_and_assigns_own_code(monkeypatch):
    cursor = _RegisterCursor()

    @contextmanager
    def fake_cursor():
        yield cursor

    monkeypatch.setattr(auth, "ensure_auth_schema", lambda: None)
    monkeypatch.setattr(auth.db, "get_cursor", fake_cursor)
    monkeypatch.setattr(auth, "_new_invite_code", lambda: "KYOWNCODE1")
    monkeypatch.setattr(auth, "_create_token", lambda user_id: f"token-{user_id}")

    result = auth.register_user(
        auth.RegisterRequest(user_id="new_user", password="123456", invite_code="kyfriend1")
    )

    assert result["success"] is True
    assert result["invite_code"] == "KYOWNCODE1"
    # 列顺序：..., invite_code, invited_by, phone, phone_verified_at
    assert cursor.insert_params[6] == 7  # invited_by = 邀请人 id
    assert cursor.insert_params[7] is None  # 未填手机号
    assert cursor.insert_params[8] is None  # 未验证手机号


def test_account_profile_masks_phone_and_exposes_customer_service(monkeypatch):
    monkeypatch.setattr(auth, "ensure_auth_schema", lambda: None)
    monkeypatch.setattr(
        auth.db,
        "fetch_one",
        lambda *_args, **_kwargs: {
            "user_id": "alice",
            "nickname": "Alice",
            "invite_code": "KYABC12345",
            "phone": "17635575899",
            "wechat_id": "alice_wx",
            "phone_verified_at": object(),
        },
    )
    profile = auth.account_profile("alice")
    assert profile["phone_masked"] == "176****5899"
    assert profile["phone_verified"] is True
    assert profile["customer_service"] == {"phone": "17635575899", "wechat": "17635575899"}


def test_login_accepts_phone_when_username_lookup_misses(monkeypatch):
    password_hash = auth._hash_password("secret1")

    def fake_fetch_one(query, params=None):
        if "WHERE user_id" in query:
            return None
        if "WHERE phone" in query and "phone_verified_at IS NOT NULL" in query:
            return {"user_id": "alice", "password_hash": password_hash}
        return None

    monkeypatch.setattr(auth.db, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(auth, "_create_token", lambda user_id: f"token-{user_id}")

    result = auth.login_user(auth.LoginRequest(user_id="17635575899", password="secret1"))
    assert result["success"] is True
    assert result["user_id"] == "alice"  # token 绑定真实用户名而非手机号
    assert result["token"] == "token-alice"


def test_phone_registration_rejects_wrong_code(monkeypatch):
    monkeypatch.setattr(auth, "ensure_auth_schema", lambda: None)
    monkeypatch.setattr(auth, "_consume_sms_code", lambda *a, **k: False)
    # 验证码校验失败时不应触碰数据库游标。
    monkeypatch.setattr(
        auth.db, "get_cursor", lambda: pytest.fail("不应在验证码失败后写库")
    )
    result = auth.register_user(
        auth.RegisterRequest(
            user_id="phone_user", password="123456", phone="17635575899", phone_code="000000"
        )
    )
    assert result["success"] is False
    assert "验证码" in result["error"]


def test_change_password_requires_current_password(monkeypatch):
    password_hash = auth._hash_password("oldpass")
    writes = []
    monkeypatch.setattr(auth.db, "fetch_one", lambda *_args, **_kwargs: {"password_hash": password_hash})
    monkeypatch.setattr(auth.db, "execute", lambda query, params=None: writes.append((query, params)))

    denied = auth.change_password(
        "alice", auth.ChangePasswordRequest(current_password="wrong", new_password="newpass")
    )
    allowed = auth.change_password(
        "alice", auth.ChangePasswordRequest(current_password="oldpass", new_password="newpass")
    )
    assert denied["success"] is False
    assert allowed["success"] is True
    assert len(writes) == 1
    assert auth._verify_password("newpass", writes[0][1][0])


def test_sms_code_is_never_returned_when_sender_is_unconfigured(monkeypatch):
    settings = auth.get_settings()
    old_url = settings.sms_webhook_url
    settings.sms_webhook_url = None
    monkeypatch.setattr(settings, "aliyun_sms_access_key_id", None)
    monkeypatch.setattr(settings, "aliyun_sms_template_code", None)
    monkeypatch.setattr(auth, "ensure_auth_schema", lambda: None)
    monkeypatch.setattr(
        auth.db,
        "fetch_one",
        lambda query, *_args, **_kwargs: {"user_id": "alice"} if "FROM users" in query else None,
    )
    try:
        with pytest.raises(RuntimeError, match="17635575899"):
            auth.request_sms_code("17635575899", "reset")
    finally:
        settings.sms_webhook_url = old_url


def test_sms_endpoints_are_hidden_while_feature_is_disabled():
    old = api.settings.sms_feature_enabled
    api.settings.sms_feature_enabled = False
    try:
        with pytest.raises(Exception) as exc_info:
            api.api_request_sms(auth.SmsCodeRequest(phone="17635575899", purpose="reset"), request=None)
        assert getattr(exc_info.value, "status_code", None) == 404
    finally:
        api.settings.sms_feature_enabled = old
