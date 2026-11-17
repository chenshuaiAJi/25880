import os
from collections.abc import Iterator

import pytest
from psycopg import Connection
from psycopg.rows import dict_row

from app.db import apply_migrations, ensure_database

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://postgres:jlauto_dev@127.0.0.1:5432/jlauto_test",
)


@pytest.fixture(scope="session")
def database_url() -> str:
    ensure_database(TEST_DATABASE_URL)
    with Connection.connect(TEST_DATABASE_URL, row_factory=dict_row, autocommit=True) as conn:
        apply_migrations(conn)
    return TEST_DATABASE_URL


@pytest.fixture()
def conn(database_url: str) -> Iterator[Connection]:
    with Connection.connect(database_url, row_factory=dict_row, autocommit=True) as setup:
        setup.execute(
            """
            TRUNCATE
                date_conflicts,
                import_warnings,
                shipment_lines,
                shipment_orders,
                remittance_cells,
                remittance_rows,
                remittance_sheets,
                bank_transactions,
                bank_import_batches,
                store_aliases,
                stores,
                source_files
            RESTART IDENTITY CASCADE
            """
        )
    with Connection.connect(database_url, row_factory=dict_row) as connection:
        yield connection
        connection.rollback()
