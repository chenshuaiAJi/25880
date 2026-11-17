import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from psycopg import Connection, sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import REPO_ROOT

MIGRATION_DIR = REPO_ROOT / "database" / "migrations"
_DB_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def database_name(database_url: str) -> str:
    name = urlparse(database_url).path.lstrip("/")
    if not _DB_NAME.fullmatch(name):
        raise ValueError("数据库名不合法")
    return name


def replace_database(database_url: str, name: str) -> str:
    parts = urlparse(database_url)
    return urlunparse(parts._replace(path=f"/{name}"))


def ensure_database(database_url: str) -> None:
    name = database_name(database_url)
    admin_url = replace_database(database_url, "postgres")
    with Connection.connect(admin_url, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (name,),
        ).fetchone()
        if exists is None:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def apply_migrations(conn: Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version text PRIMARY KEY,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    for path in sorted(MIGRATION_DIR.glob("*.sql")):
        applied = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = %s",
            (path.name,),
        ).fetchone()
        if applied is not None:
            continue
        for statement in _sql_statements(path.read_text(encoding="utf-8")):
            conn.execute(statement)
        conn.execute(
            "INSERT INTO schema_migrations (version) VALUES (%s)",
            (path.name,),
        )


def _sql_statements(script: str) -> list[str]:
    """按行末分号切分。迁移文件不把分号写进字符串。"""
    statements: list[str] = []
    current: list[str] = []
    for line in script.splitlines():
        if line.strip().startswith("--"):
            continue
        current.append(line)
        if line.strip().endswith(";"):
            statement = "\n".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
    tail = "\n".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def create_pool(database_url: str) -> ConnectionPool:
    return ConnectionPool(
        database_url,
        min_size=1,
        max_size=8,
        kwargs={
            "row_factory": dict_row,
            "options": "-c timezone=Asia/Shanghai",
        },
        open=True,
    )
