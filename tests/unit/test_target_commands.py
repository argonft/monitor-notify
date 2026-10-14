"""Duyuru kanalı yönetimi komutları: /targets, /addtarget, /rmtarget, /chatid."""
import pytest

from monitor_notify.bot.commands import CommandService
from monitor_notify.profile import RetailerProfile
from monitor_notify.store.notify_store import NotifyTarget

CHANNEL = -1001234567890
ADMIN = 987654321


class FakeRepo:
    def __init__(self) -> None:
        self.targets: dict[int, NotifyTarget] = {}
        self.removed: list[int] = []

    async def list_all_targets(self) -> tuple[NotifyTarget, ...]:
        return tuple(self.targets.values())

    async def ensure_target(self, chat_id, *, receives_notifications=True, can_manage=True, title=None):
        self.targets[chat_id] = NotifyTarget(chat_id, receives_notifications, can_manage, title)

    async def remove_target(self, chat_id: int) -> bool:
        if chat_id in self.targets:
            del self.targets[chat_id]
            self.removed.append(chat_id)
            return True
        return False


@pytest.fixture
def repo() -> FakeRepo:
    return FakeRepo()


@pytest.fixture
def service(repo: FakeRepo) -> CommandService:
    return CommandService(repo, profile=RetailerProfile(name="shop.example"))


# --- /targets -------------------------------------------------------------


async def test_targets_bos_listede_aciklama_verir(service):
    reply = await service.targets()
    assert "hedef" in reply.lower()


async def test_targets_rolleriyle_listeler(service, repo):
    await repo.ensure_target(CHANNEL, receives_notifications=True, can_manage=False, title="Shop Drops")
    await repo.ensure_target(ADMIN, receives_notifications=False, can_manage=True)

    reply = await service.targets()

    assert str(CHANNEL) in reply
    assert "Shop Drops" in reply
    assert str(ADMIN) in reply


async def test_targets_bildirim_ve_yetki_rollerini_ayirir(service, repo):
    await repo.ensure_target(CHANNEL, receives_notifications=True, can_manage=False)
    reply = await service.targets()

    assert "bildirim" in reply.lower()


# --- /addtarget -----------------------------------------------------------


async def test_addtarget_kanali_yayin_hedefi_olarak_ekler(service, repo):
    reply = await service.add_target(str(CHANNEL))

    assert repo.targets[CHANNEL].receives_notifications is True
    assert repo.targets[CHANNEL].can_manage is False
    assert str(CHANNEL) in reply


async def test_addtarget_admin_anahtar_kelimesiyle_yetki_verir(service, repo):
    await service.add_target(f"{ADMIN} admin")

    assert repo.targets[ADMIN].can_manage is True


async def test_addtarget_negatif_kanal_idsini_kabul_eder(service, repo):
    """Kanal id'leri -100 ile başlar; eksi işareti argüman sanılmamalı."""
    await service.add_target("-1009876543210")
    assert -1009876543210 in repo.targets


async def test_addtarget_sayisal_olmayan_id_reddedilir(service, repo):
    reply = await service.add_target("@shopdrops")

    assert repo.targets == {}
    assert "kullanım" in reply.lower()


async def test_addtarget_bos_arguman_reddedilir(service, repo):
    reply = await service.add_target("  ")
    assert repo.targets == {}
    assert "kullanım" in reply.lower()


async def test_addtarget_mevcut_hedefin_rolunu_gunceller(service, repo):
    await service.add_target(str(ADMIN))
    await service.add_target(f"{ADMIN} admin")

    assert repo.targets[ADMIN].can_manage is True


# --- /rmtarget ------------------------------------------------------------


async def test_rmtarget_hedefi_kaldirir(service, repo):
    await service.add_target(str(CHANNEL))
    reply = await service.remove_target(str(CHANNEL))

    assert repo.removed == [CHANNEL]
    assert str(CHANNEL) in reply


async def test_rmtarget_olmayan_hedefi_bildirir(service):
    reply = await service.remove_target("-100999")
    assert "bulunamadı" in reply.lower()


async def test_rmtarget_gecersiz_id_reddedilir(service):
    reply = await service.remove_target("abc")
    assert "kullanım" in reply.lower()


# --- /chatid ve forward ---------------------------------------------------


def test_chatid_mevcut_sohbetin_idsini_verir(service):
    reply = service.describe_chat(ADMIN, title=None)
    assert str(ADMIN) in reply


def test_forward_kanal_idsini_ve_hazir_komutu_verir(service):
    """Kanal id'sini bulmak zor; forward edilen mesajdan çıkarıp komutu hazırla."""
    reply = service.describe_forwarded(CHANNEL, title="Shop Drops")

    assert str(CHANNEL) in reply
    assert "Shop Drops" in reply
    assert f"/addtarget {CHANNEL}" in reply


def test_forward_basliksiz_kanalda_cokmez(service):
    reply = service.describe_forwarded(CHANNEL, title=None)
    assert str(CHANNEL) in reply
