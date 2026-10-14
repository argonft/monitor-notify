"""Çok kaynaklı migration çalıştırıcı.

Kütüphane kendi tablolarının migration'larını taşır; retailer kendi
klasörünü ekler. Uygulanan dosyalar ``schema_migrations`` tablosunda
``önek + dosya adı`` olarak izlenir, böylece iki kaynakta aynı adlı dosya
çakışmaz. Açılışta her seferinde çağrılabilir; uygulanmış dosya atlanır.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


class MigrationsMissingError(RuntimeError):
    """Migration klasörü boş: büyük ihtimalle .sql dosyaları pakete girmedi."""


@dataclass(frozen=True, slots=True)
class MigrationSource:
    #: ``schema_migrations.filename`` öneki, örn. ``"notify/"``.
    prefix: str
    directory: Path

    def files(self) -> tuple[Path, ...]:
        """Klasördeki ``.sql`` dosyaları, ad sırasıyla.

        Raises:
            MigrationsMissingError: Klasörde hiç dosya yoksa. Sessizce geçmek
                şemayı eksik bırakır ve hata ilk sorguda alakasız bir yerde çıkar.
        """
        paths = tuple(sorted(self.directory.glob("*.sql")))
        if not paths:
            raise MigrationsMissingError(
                f"{self.directory} içinde migration dosyası yok; "
                "paket .sql dosyalarını içermiyor olabilir."
            )
        return paths


NOTIFY_MIGRATIONS = MigrationSource(
    prefix="notify/", directory=Path(__file__).parent / "migrations"
)


async def migrate(pool: asyncpg.Pool, *sources: MigrationSource) -> list[str]:
    """Kaynakları verilen sırayla uygular, uygulanan kayıt adlarını döner."""
    plan = _plan(sources)
    applied: list[str] = []
    async with pool.acquire() as connection:
        await connection.execute(_TRACKING_TABLE)
        done = {
            row["filename"]
            for row in await connection.fetch("SELECT filename FROM schema_migrations")
        }
        for name, path in plan:
            if name in done:
                continue
            async with connection.transaction():
                await connection.execute(path.read_text(encoding="utf-8"))
                await connection.execute(
                    "INSERT INTO schema_migrations (filename) VALUES ($1)", name
                )
            applied.append(name)
            logger.info("Migration uygulandı: %s", name)
    return applied


def _plan(sources: tuple[MigrationSource, ...]) -> list[tuple[str, Path]]:
    """Veritabanına gitmeden önce planı doğrular."""
    if not sources:
        raise ValueError("En az bir migration kaynağı gerekli.")
    plan = [(source.prefix + path.name, path) for source in sources for path in source.files()]
    names = [name for name, _ in plan]
    if len(set(names)) != len(names):
        raise ValueError("Aynı kayıt adına sahip iki migration var; önekleri ayırın.")
    return plan
