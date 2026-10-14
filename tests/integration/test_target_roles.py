"""Bildirim hedefi ve komut yetkisinin ayrılması."""
import pytest

pytestmark = pytest.mark.asyncio

CHANNEL = -1001234567890
ADMIN = 987654321


async def test_kanal_bildirim_alir_komut_calistiramaz(store):
    await store.ensure_target(CHANNEL, receives_notifications=True, can_manage=False)

    assert await store.list_notify_targets() == (CHANNEL,)
    assert await store.list_admin_chats() == ()


async def test_admin_komut_calistirir_bildirim_almaz(store):
    await store.ensure_target(ADMIN, receives_notifications=False, can_manage=True)

    assert await store.list_notify_targets() == ()
    assert await store.list_admin_chats() == (ADMIN,)


async def test_kanal_ve_admin_birlikte_yasar(store):
    await store.ensure_target(CHANNEL, receives_notifications=True, can_manage=False)
    await store.ensure_target(ADMIN, receives_notifications=False, can_manage=True)

    assert await store.list_notify_targets() == (CHANNEL,)
    assert await store.list_admin_chats() == (ADMIN,)


async def test_ayni_hedef_iki_role_de_sahip_olabilir(store):
    await store.ensure_target(ADMIN, receives_notifications=True, can_manage=True)

    assert await store.list_notify_targets() == (ADMIN,)
    assert await store.list_admin_chats() == (ADMIN,)


async def test_rol_guncellenebilir(store):
    """Kanal eklenince admin'in bildirim alması kapatılabilmeli."""
    await store.ensure_target(ADMIN, receives_notifications=True, can_manage=True)
    await store.ensure_target(ADMIN, receives_notifications=False, can_manage=True)

    assert await store.list_notify_targets() == ()
    assert await store.list_admin_chats() == (ADMIN,)


async def test_baslik_saklanir(store):
    await store.ensure_target(CHANNEL, receives_notifications=True, can_manage=False, title="Shop Drops")
    rows = await store.list_all_targets()

    assert rows[0].title == "Shop Drops"


async def test_hedef_kaldirilir(store):
    await store.ensure_target(CHANNEL, receives_notifications=True, can_manage=False)

    assert await store.remove_target(CHANNEL) is True
    assert await store.list_notify_targets() == ()


async def test_olmayan_hedef_kaldirilamaz(store):
    assert await store.remove_target(404) is False


async def test_kaldirilan_hedef_tekrar_kaldirilamaz(store):
    await store.ensure_target(CHANNEL, receives_notifications=True, can_manage=False)
    await store.remove_target(CHANNEL)

    assert await store.remove_target(CHANNEL) is False


async def test_tum_hedefler_rolleriyle_listelenir(store):
    await store.ensure_target(CHANNEL, receives_notifications=True, can_manage=False, title="Kanal")
    await store.ensure_target(ADMIN, receives_notifications=False, can_manage=True)

    rows = {row.chat_id: row for row in await store.list_all_targets()}

    assert rows[CHANNEL].receives_notifications is True
    assert rows[CHANNEL].can_manage is False
    assert rows[ADMIN].can_manage is True


async def test_eski_kayitlar_her_iki_yetkiyi_korur(pool, store):
    """Migration geriye uyumlu olmalı: mevcut hedefler davranış değiştirmemeli."""
    await pool.execute("INSERT INTO notify_targets (chat_id, is_active) VALUES ($1, true)", 555)

    assert 555 in await store.list_notify_targets()
    assert 555 in await store.list_admin_chats()
