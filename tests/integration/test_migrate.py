"""Çok kaynaklı migration ve mevcut retailer şemasıyla uyumluluk."""
from pathlib import Path

import pytest

from monitor_notify.store.migrate import NOTIFY_MIGRATIONS, MigrationSource, migrate

pytestmark = pytest.mark.asyncio

LEGACY = MigrationSource(prefix="", directory=Path(__file__).parent.parent / "fixtures" / "legacy_schema")
TABLES = ["watch_rules", "notify_targets"]


async def _shape(pool) -> tuple[list[tuple], list[tuple]]:
    columns = await pool.fetch(
        """
        SELECT table_name, column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ANY($1::text[])
        ORDER BY table_name, ordinal_position
        """,
        TABLES,
    )
    indexes = await pool.fetch(
        """
        SELECT tablename, indexname, indexdef FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = ANY($1::text[])
        ORDER BY tablename, indexname
        """,
        TABLES,
    )
    return [tuple(row) for row in columns], [tuple(row) for row in indexes]


async def test_kayitlar_onekle_tutulur(clean_pool):
    applied = await migrate(clean_pool, NOTIFY_MIGRATIONS)
    assert applied == ["notify/001_rules_targets.sql"]


async def test_ikinci_calistirma_bir_sey_uygulamaz(clean_pool):
    await migrate(clean_pool, NOTIFY_MIGRATIONS)
    assert await migrate(clean_pool, NOTIFY_MIGRATIONS) == []


async def test_kaynaklar_verilen_sirada_uygulanir(clean_pool, tmp_path: Path):
    (tmp_path / "001_after.sql").write_text(
        "INSERT INTO notify_targets (chat_id) VALUES (1);"
    )
    retailer = MigrationSource(prefix="", directory=tmp_path)

    applied = await migrate(clean_pool, NOTIFY_MIGRATIONS, retailer)

    assert applied == ["notify/001_rules_targets.sql", "001_after.sql"]


async def test_mevcut_semada_notify_migration_degisiklik_yapmaz(clean_pool):
    await migrate(clean_pool, LEGACY)
    before = await _shape(clean_pool)

    applied = await migrate(clean_pool, NOTIFY_MIGRATIONS, LEGACY)

    assert applied == ["notify/001_rules_targets.sql"]
    assert await _shape(clean_pool) == before


async def test_bos_semada_ayni_tablo_yapisi_kurulur(clean_pool):
    await migrate(clean_pool, LEGACY)
    legacy_shape = await _shape(clean_pool)

    async with clean_pool.acquire() as connection:
        await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    await migrate(clean_pool, NOTIFY_MIGRATIONS)

    assert await _shape(clean_pool) == legacy_shape
