"""PostgreSQL 数据库连接与轻量封装。

通过环境变量或 .env 文件配置连接（见 .env.example）：
    DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator

import psycopg2
import psycopg2.extras
from psycopg2 import pool
from pydantic_settings import BaseSettings, SettingsConfigDict


class DBSettings(BaseSettings):
    """数据库配置（独立于主 Settings，避免循环依赖）。"""

    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "kaoyan_ai"
    db_user: str = "postgres"
    db_password: str = "postgres"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def _get_db_settings() -> DBSettings:
    return DBSettings()


_POOL: pool.SimpleConnectionPool | None = None


def _build_dsn() -> str:
    """拼接 PostgreSQL DSN 连接串。"""
    s = _get_db_settings()
    return (
        f"host={s.db_host} port={s.db_port} dbname={s.db_name} "
        f"user={s.db_user} password={s.db_password}"
    )


def init_pool(minconn: int = 1, maxconn: int = 10) -> pool.SimpleConnectionPool:
    """初始化全局连接池。"""
    global _POOL
    if _POOL is None:
        _POOL = pool.SimpleConnectionPool(minconn, maxconn, dsn=_build_dsn())
    return _POOL


@contextmanager
def get_conn() -> Iterator[psycopg2.extensions.connection]:
    """从连接池取一个连接，使用完毕后自动归还。"""
    if _POOL is None:
        init_pool()
    assert _POOL is not None
    conn = _POOL.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _POOL.putconn(conn)


@contextmanager
def get_cursor() -> Iterator[psycopg2.extras.RealDictCursor]:
    """取连接 + RealDictCursor（结果以字典形式返回）。"""
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cur
        finally:
            cur.close()


def execute(sql: str, params: tuple | dict | None = None) -> None:
    """执行单条 SQL（INSERT/UPDATE/DELETE/CREATE）。"""
    with get_cursor() as cur:
        cur.execute(sql, params)


def executemany(sql: str, seq_of_params: list[tuple | dict]) -> None:
    """批量执行同一条 SQL。"""
    with get_cursor() as cur:
        psycopg2.extras.execute_batch(cur, sql, seq_of_params, page_size=500)


def fetch_one(sql: str, params: tuple | dict | None = None) -> dict | None:
    with get_cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def fetch_all(sql: str, params: tuple | dict | None = None) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def close_pool() -> None:
    global _POOL
    if _POOL is not None:
        _POOL.closeall()
        _POOL = None
