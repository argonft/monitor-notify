"""Entegrasyon testleri için gerçek Postgres bağlantısı.

Veritabanı ``MONITOR_NOTIFY_TEST_DATABASE_URL`` ile verilir; yoksa testler
atlanır. Her test ``public`` şemasını sıfırlar - bu adres asla gerçek bir
veritabanını göstermemeli.
"""
import os

import asyncpg
import pytest
import pytest_asyncio

from monitor_notify.store.migrate import NOTIFY_MIGRATIONS, migrate
from monitor_notify.store.notify_store import NotifyStore

DSN = os.environ.get("MONITOR_NOTIFY_TEST_DATABASE_URL")


async def _reset(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as connection:
        await connection.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")


@pytest_asyncio.fixture
async def clean_pool():
    """Şeması boş bir veritabanı; migration uygulanmamış."""
    if not DSN:
        pytest.skip("MONITOR_NOTIFY_TEST_DATABASE_URL tanımlı değil")
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    await _reset(pool)
    try:
        yield pool
    finally:
        await pool.close()


@pytest_asyncio.fixture
async def pool(clean_pool):
    await migrate(clean_pool, NOTIFY_MIGRATIONS)
    return clean_pool


@pytest_asyncio.fixture
async def store(pool) -> NotifyStore:
    return NotifyStore(pool)
