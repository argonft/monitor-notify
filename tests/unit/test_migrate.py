"""Migration kaynaklarının paketleme hatalarına karşı davranışı."""
from pathlib import Path

import pytest

from monitor_notify.store.migrate import (
    NOTIFY_MIGRATIONS,
    MigrationSource,
    MigrationsMissingError,
    migrate,
)


class UnusedPool:
    def acquire(self):  # pragma: no cover - çağrılırsa test zaten başarısız
        raise AssertionError("Migration planı geçersizken veritabanına gidilmemeli.")


def test_kutuphane_migrationlari_pakette():
    assert [path.name for path in NOTIFY_MIGRATIONS.files()][0] == "001_rules_targets.sql"
    assert NOTIFY_MIGRATIONS.prefix == "notify/"


def test_bos_klasor_hata_verir(tmp_path: Path):
    with pytest.raises(MigrationsMissingError):
        MigrationSource(prefix="x/", directory=tmp_path).files()


async def test_bos_kaynakla_veritabanina_gidilmez(tmp_path: Path):
    with pytest.raises(MigrationsMissingError):
        await migrate(UnusedPool(), MigrationSource(prefix="", directory=tmp_path))


async def test_kaynaksiz_cagri_reddedilir():
    with pytest.raises(ValueError):
        await migrate(UnusedPool())


async def test_ayni_kayit_adi_iki_kez_reddedilir(tmp_path: Path):
    (tmp_path / "001_a.sql").write_text("SELECT 1;")
    source = MigrationSource(prefix="", directory=tmp_path)
    with pytest.raises(ValueError):
        await migrate(UnusedPool(), source, source)
