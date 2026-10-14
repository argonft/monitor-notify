"""Kural ve bildirim hedefi deposu."""
import pytest

from monitor_notify.model import EventKind
from monitor_notify.rules.matcher import RuleKind

pytestmark = pytest.mark.asyncio


# --- kurallar -------------------------------------------------------------


async def test_kural_eklenir_ve_okunur(store):
    rule_id = await store.add_rule(RuleKind.BRAND, "Nike", created_by=7)
    rules = await store.list_rules()

    assert len(rules) == 1
    assert rules[0].id == rule_id
    assert rules[0].kind is RuleKind.BRAND
    assert rules[0].pattern == "Nike"
    assert rules[0].event_types is None


async def test_event_tipi_kisitli_kural_saklanir(store):
    await store.add_rule(
        RuleKind.BRAND, "Nike", event_types=frozenset({EventKind.RESTOCK, EventKind.PRICE_DROP})
    )
    rule = (await store.list_rules())[0]

    assert rule.event_types == frozenset({EventKind.RESTOCK, EventKind.PRICE_DROP})


async def test_desendeki_bosluklar_temizlenir(store):
    await store.add_rule(RuleKind.KEYWORD, "  air max  ")
    assert (await store.list_rules())[0].pattern == "air max"


async def test_kural_pasiflestirilir(store):
    rule_id = await store.add_rule(RuleKind.BRAND, "Nike")

    assert await store.deactivate_rule(rule_id) is True
    assert await store.list_rules() == ()


async def test_pasif_kural_tekrar_pasiflestirilemez(store):
    rule_id = await store.add_rule(RuleKind.BRAND, "Nike")
    await store.deactivate_rule(rule_id)

    assert await store.deactivate_rule(rule_id) is False


async def test_olmayan_kural_pasiflestirilemez(store):
    assert await store.deactivate_rule(999) is False


async def test_pasif_kurallar_da_istenirse_listelenir(store):
    rule_id = await store.add_rule(RuleKind.BRAND, "Nike")
    await store.deactivate_rule(rule_id)

    assert len(await store.list_rules(only_active=False)) == 1


# --- hedefler -------------------------------------------------------------


async def test_hedef_eklenir(store):
    await store.ensure_target(42)
    assert await store.list_notify_targets() == (42,)


async def test_hedef_iki_kez_eklenince_cogalmaz(store):
    await store.ensure_target(42)
    await store.ensure_target(42)
    assert await store.list_notify_targets() == (42,)


async def test_negatif_chat_id_desteklenir(store):
    """Telegram grup sohbetlerinin id'si negatiftir."""
    await store.ensure_target(-1001234567890)
    assert await store.list_notify_targets() == (-1001234567890,)


# --- aktif kural sayısı ve bilinmeyen event türü --------------------------


async def test_aktif_kural_sayisi(store):
    assert await store.active_rule_count() == 0
    rule_id = await store.add_rule(RuleKind.BRAND, "Nike")
    await store.add_rule(RuleKind.KEYWORD, "air max")
    await store.deactivate_rule(rule_id)

    assert await store.active_rule_count() == 1


async def test_bilinmeyen_event_turu_kurali_cokertmez(pool, store):
    await pool.execute(
        "INSERT INTO watch_rules (kind, pattern, event_types) VALUES ('brand', 'Nike', $1)",
        ["restock", "campaign"],
    )

    rules = await store.list_rules()

    assert rules[0].event_types == frozenset({EventKind.RESTOCK})


async def test_yalnizca_bilinmeyen_event_turu_olan_kural_hicbir_seyi_kapsamaz(pool, store):
    await pool.execute(
        "INSERT INTO watch_rules (kind, pattern, event_types) VALUES ('brand', 'Nike', $1)",
        ["campaign"],
    )

    rule = (await store.list_rules())[0]

    assert not any(rule.covers(kind) for kind in EventKind)


async def test_bilinmeyen_kural_turu_atlanir_digerleri_okunur(pool, store):
    """Bozuk tek bir kural tüm kural listesini (ve dolayısıyla kuyruğu) durdurmamalı."""
    await pool.execute("INSERT INTO watch_rules (kind, pattern) VALUES ('future_kind', 'x')")
    good = await store.add_rule(RuleKind.BRAND, "Nike")

    rules = await store.list_rules()

    assert [rule.id for rule in rules] == [good]
