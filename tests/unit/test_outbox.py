"""Bildirim kuyruğu işleyicisi.

Kuyruktan alınan event'ler kurallara göre süzülür, aciliyetine göre anında
ya da özet olarak gönderilir ve ancak gönderim başarılıysa işaretlenir.
"""
from decimal import Decimal

import pytest

from monitor_notify.model import EventKind, Notification
from monitor_notify.outbox import OutboxDispatcher
from monitor_notify.profile import RetailerProfile
from monitor_notify.rules.matcher import Rule, RuleKind

PROFILE = RetailerProfile(name="shop.example")


class FakeCatalog:
    """Bellek içi EventSource."""

    def __init__(self, pending: list[Notification]) -> None:
        self._pending = pending
        self.marked: list[int] = []

    async def pending(self, limit: int) -> list[Notification]:
        return self._pending[:limit]

    async def mark_notified(self, ids) -> None:
        self.marked.extend(ids)
        self._pending = [p for p in self._pending if p.id not in set(ids)]


class FakeRules:
    def __init__(
        self,
        rules: tuple[Rule, ...],
        targets: tuple[int, ...] = (1,),
        admins: tuple[int, ...] = (9,),
    ) -> None:
        self._rules = rules
        self._targets = targets
        self._admins = admins

    async def list_rules(self, *, only_active: bool = True) -> tuple[Rule, ...]:
        return self._rules

    async def list_notify_targets(self) -> tuple[int, ...]:
        return self._targets

    async def list_admin_chats(self) -> tuple[int, ...]:
        return self._admins


class FakeNotifier:
    """Yayın hedeflerine gönderimi kontrollü şekilde başarısız kılabilir."""

    def __init__(self, *, fail: bool = False, fail_chats: set[int] | None = None) -> None:
        self.sent: list[tuple[int, str]] = []
        self.messages: list[object] = []
        self.fail = fail
        self.fail_chats = fail_chats or set()

    async def send(self, chat_id: int, message) -> bool:
        text = getattr(message, "text", message)
        if self.fail or chat_id in self.fail_chats:
            return False
        self.sent.append((chat_id, text))
        self.messages.append(message)
        return True


def pending(
    event_id: int,
    event_type: EventKind = EventKind.RESTOCK,
    *,
    name: str = "Air Max Plus VII",
    brand: str | None = "Nike",
    label: str = "42",
    image_url: str | None = None,
) -> Notification:
    return Notification(
        id=event_id,
        kind=event_type,
        product_name=name,
        brand=brand,
        categories=("Sneaker",),
        variant_label=label,
        product_url="https://shop.example/air-max-plus-vii",
        image_url=image_url,
        sell_price=Decimal("10999"),
        old_stock=0,
        new_stock=3,
    )


NIKE_RULE = Rule(id=1, kind=RuleKind.BRAND, pattern="Nike")
MUTE_CORAP = Rule(id=2, kind=RuleKind.NEGATIVE_KEYWORD, pattern="çorap")


def build(events, rules=(NIKE_RULE,), *, fail=False, max_per_cycle=40, **kwargs):
    catalog = FakeCatalog(list(events))
    notifier = FakeNotifier(fail=fail)
    dispatcher = OutboxDispatcher(
        source=catalog,
        profile=PROFILE,
        store=FakeRules(rules),
        notifier=notifier,
        max_per_cycle=max_per_cycle,
        **kwargs,
    )
    return dispatcher, catalog, notifier


# --- temel akış -----------------------------------------------------------


async def test_acil_event_aninda_tek_mesaj_gonderilir():
    dispatcher, catalog, notifier = build([pending(1, EventKind.RESTOCK)])
    await dispatcher.run_once()

    assert len(notifier.sent) == 1
    assert "RESTOCK" in notifier.sent[0][1]
    assert catalog.marked == [1]


def _digest_messages(notifier):
    return [text for _, text in notifier.sent if "Tur özeti" in text]


async def test_acil_olmayan_eventler_tek_ozette_toplanir():
    events = [pending(i, EventKind.STOCK_DOWN, label=str(i)) for i in range(1, 4)]
    dispatcher, catalog, notifier = build(events)
    await dispatcher.run_once()

    assert len(_digest_messages(notifier)) == 1
    assert sorted(catalog.marked) == [1, 2, 3]


async def test_acil_ve_ozet_birlikte_calisir():
    events = [pending(1, EventKind.RESTOCK), pending(2, EventKind.STOCK_DOWN)]
    dispatcher, catalog, notifier = build(events)
    await dispatcher.run_once()

    assert len(notifier.sent) == 2
    assert sorted(catalog.marked) == [1, 2]


async def test_kuyruk_bossa_mesaj_gonderilmez():
    dispatcher, _, notifier = build([])
    await dispatcher.run_once()
    assert notifier.sent == []


# --- filtreleme -----------------------------------------------------------


async def test_kural_eslesmeyen_event_gonderilmez_ama_islenmis_sayilir():
    """Elenen event kuyrukta sonsuza kadar birikmemeli."""
    adidas = pending(1, EventKind.RESTOCK, brand="Adidas", name="Samba OG")
    dispatcher, catalog, notifier = build([adidas])
    await dispatcher.run_once()

    assert notifier.sent == []
    assert catalog.marked == [1]


async def test_negatif_keyword_eslesen_event_susturulur():
    corap = pending(1, EventKind.RESTOCK, name="Nike Everyday Çorap")
    dispatcher, catalog, notifier = build([corap], rules=(NIKE_RULE, MUTE_CORAP))
    await dispatcher.run_once()

    assert notifier.sent == []
    assert catalog.marked == [1]


async def test_kural_yoksa_hicbir_sey_gonderilmez():
    dispatcher, catalog, notifier = build([pending(1)], rules=())
    await dispatcher.run_once()

    assert notifier.sent == []
    assert catalog.marked == [1]


# --- hata dayanıklılığı ---------------------------------------------------


async def test_gonderim_basarisizsa_event_isaretlenmez():
    """Telegram çökerse event kuyrukta kalmalı ve sonra yeniden denenmeli."""
    dispatcher, catalog, notifier = build([pending(1)], fail=True)
    await dispatcher.run_once()

    assert catalog.marked == []
    assert len(await catalog.pending(200)) == 1


async def test_gonderim_basarisizken_elenen_eventler_yine_de_isaretlenir():
    adidas = pending(1, EventKind.RESTOCK, brand="Adidas")
    dispatcher, catalog, notifier = build([adidas, pending(2)], fail=True)
    await dispatcher.run_once()

    assert catalog.marked == [1]


async def test_ozet_gonderimi_basarisizsa_o_eventler_isaretlenmez():
    events = [pending(i, EventKind.STOCK_DOWN) for i in (1, 2)]
    dispatcher, catalog, _ = build(events, fail=True)
    await dispatcher.run_once()

    assert catalog.marked == []


# --- sel koruması ---------------------------------------------------------


async def test_ust_sinir_asilinca_ozet_kisalir_ama_hepsi_isaretlenir():
    events = [pending(i, EventKind.STOCK_DOWN, label=str(i)) for i in range(1, 101)]
    dispatcher, catalog, notifier = build(events, max_per_cycle=10)
    await dispatcher.run_once()

    digest = _digest_messages(notifier)[0]
    assert "90 değişiklik daha" in digest
    assert len(catalog.marked) == 100


async def test_acil_mesaj_sayisi_da_sinirlanir():
    events = [pending(i, EventKind.RESTOCK) for i in range(1, 51)]
    dispatcher, catalog, notifier = build(events, max_per_cycle=10)
    await dispatcher.run_once()

    urgent = [t for _, t in notifier.sent if "RESTOCK" in t]
    assert len(urgent) <= 10
    assert len(catalog.marked) == 50


# --- çoklu hedef ----------------------------------------------------------


async def test_birden_fazla_hedefe_gonderilir():
    catalog = FakeCatalog([pending(1)])
    notifier = FakeNotifier()
    dispatcher = OutboxDispatcher(
        source=catalog,
        profile=PROFILE,
        store=FakeRules((NIKE_RULE,), targets=(1, 2)),
        notifier=notifier,
        max_per_cycle=40,
    )
    await dispatcher.run_once()

    assert {chat_id for chat_id, _ in notifier.sent} == {1, 2}
    assert catalog.marked == [1]


async def test_hedef_yoksa_event_islenmis_sayilir():
    catalog = FakeCatalog([pending(1)])
    notifier = FakeNotifier()
    dispatcher = OutboxDispatcher(
        source=catalog,
        profile=PROFILE,
        store=FakeRules((NIKE_RULE,), targets=()),
        notifier=notifier,
        max_per_cycle=40,
    )
    await dispatcher.run_once()

    assert notifier.sent == []
    assert catalog.marked == [1]


# --- mesaj içeriği --------------------------------------------------------


async def test_mesajlarda_lira_sembolu_gecmez():
    events = [pending(1, EventKind.RESTOCK), pending(2, EventKind.PRICE_UP)]
    dispatcher, _, notifier = build(events)
    await dispatcher.run_once()

    for _, text in notifier.sent:
        assert "₺" not in text


# --- duyuru kanalı --------------------------------------------------------


async def test_bildirimler_yalnizca_yayin_hedeflerine_gider():
    """Admin sohbeti yayın hedefi değilse bildirim almamalı."""
    catalog = FakeCatalog([pending(1)])
    notifier = FakeNotifier()
    dispatcher = OutboxDispatcher(
        source=catalog,
        profile=PROFILE,
        store=FakeRules((NIKE_RULE,), targets=(-1001234567890,), admins=(99,)),
        notifier=notifier,
        max_per_cycle=40,
    )
    await dispatcher.run_once()

    assert {chat_id for chat_id, _ in notifier.sent} == {-1001234567890}


# --- sessiz arıza koruması ------------------------------------------------


def build_failing(threshold: int = 3):
    """Yayın hedefi sürekli reddediyor, admin sohbeti çalışıyor."""
    catalog = FakeCatalog([pending(1)])
    notifier = FakeNotifier(fail_chats={-100})
    dispatcher = OutboxDispatcher(
        source=catalog,
        profile=PROFILE,
        store=FakeRules((NIKE_RULE,), targets=(-100,), admins=(9,)),
        notifier=notifier,
        max_per_cycle=40,
        delivery_alert_threshold=threshold,
    )
    return dispatcher, catalog, notifier


def _alerts(notifier):
    return [text for chat_id, text in notifier.sent if chat_id == 9]


async def test_esik_asilinca_admine_teshis_gonderilir():
    """Bot kanala admin yapılmadıysa kullanıcı bunu öğrenmeli."""
    dispatcher, _, notifier = build_failing(threshold=3)
    for _ in range(3):
        await dispatcher.run_once()

    assert len(_alerts(notifier)) == 1
    assert "kanal" in _alerts(notifier)[0].lower()


async def test_esigin_altinda_teshis_gonderilmez():
    dispatcher, _, notifier = build_failing(threshold=3)
    for _ in range(2):
        await dispatcher.run_once()

    assert _alerts(notifier) == []


async def test_teshis_bir_kez_gonderilir():
    """Her turda tekrar tekrar uyarı yağmamalı."""
    dispatcher, _, notifier = build_failing(threshold=2)
    for _ in range(10):
        await dispatcher.run_once()

    assert len(_alerts(notifier)) == 1


async def test_gonderim_duzelince_sayac_sifirlanir():
    dispatcher, catalog, notifier = build_failing(threshold=3)
    await dispatcher.run_once()
    await dispatcher.run_once()

    notifier.fail_chats.clear()
    await dispatcher.run_once()

    notifier.fail_chats.add(-100)
    catalog._pending = [pending(2)]
    await dispatcher.run_once()
    await dispatcher.run_once()

    assert _alerts(notifier) == []


async def test_duzelme_sonrasi_yeni_ariza_tekrar_uyarir():
    dispatcher, catalog, notifier = build_failing(threshold=2)
    for _ in range(3):
        await dispatcher.run_once()
    assert len(_alerts(notifier)) == 1

    notifier.fail_chats.clear()
    catalog._pending = [pending(2)]
    await dispatcher.run_once()

    notifier.fail_chats.add(-100)
    catalog._pending = [pending(3)]
    await dispatcher.run_once()
    await dispatcher.run_once()

    assert len(_alerts(notifier)) == 2


async def test_yayin_hedefi_yoksa_teshis_gonderilmez():
    """Hedef tanımsızsa bu bir arıza değil, yapılandırma eksikliğidir."""
    catalog = FakeCatalog([pending(1)])
    notifier = FakeNotifier()
    dispatcher = OutboxDispatcher(
        source=catalog,
        profile=PROFILE,
        store=FakeRules((NIKE_RULE,), targets=(), admins=(9,)),
        notifier=notifier,
        max_per_cycle=40,
        delivery_alert_threshold=1,
    )
    for _ in range(3):
        await dispatcher.run_once()

    assert _alerts(notifier) == []


# --- hedef bazında arıza takibi -------------------------------------------


async def test_bir_hedef_bozuksa_digeri_calissa_bile_uyarilir():
    """Çalışan bir hedef, bozuk olanı gizlememeli."""
    catalog = FakeCatalog([])
    notifier = FakeNotifier(fail_chats={-100})
    dispatcher = OutboxDispatcher(
        source=catalog,
        profile=PROFILE,
        store=FakeRules((NIKE_RULE,), targets=(-100, 7), admins=(9,)),
        notifier=notifier,
        max_per_cycle=40,
        delivery_alert_threshold=2,
    )
    for event_id in range(1, 4):
        # Her tarama turu kuyruğa yeni event ekler.
        catalog._pending = [pending(event_id)]
        await dispatcher.run_once()

    alerts = [text for chat_id, text in notifier.sent if chat_id == 9]
    assert len(alerts) == 1
    assert "-100" in alerts[0]


async def test_uyari_bozuk_hedefi_isimle_belirtir():
    dispatcher, _, notifier = build_failing(threshold=2)
    for _ in range(3):
        await dispatcher.run_once()

    assert "-100" in _alerts(notifier)[0]


async def test_calisan_hedef_icin_uyari_gonderilmez():
    catalog = FakeCatalog([pending(1)])
    notifier = FakeNotifier()
    dispatcher = OutboxDispatcher(
        source=catalog,
        profile=PROFILE,
        store=FakeRules((NIKE_RULE,), targets=(7,), admins=(9,)),
        notifier=notifier,
        max_per_cycle=40,
        delivery_alert_threshold=1,
    )
    for _ in range(3):
        await dispatcher.run_once()

    assert [t for c, t in notifier.sent if c == 9] == []


async def test_bozuk_hedefe_giden_event_calisan_hedefe_gittiyse_isaretlenir():
    """Aksi halde çalışan hedefe aynı mesaj tekrar tekrar giderdi."""
    catalog = FakeCatalog([pending(1)])
    notifier = FakeNotifier(fail_chats={-100})
    dispatcher = OutboxDispatcher(
        source=catalog,
        profile=PROFILE,
        store=FakeRules((NIKE_RULE,), targets=(-100, 7), admins=(9,)),
        notifier=notifier,
        max_per_cycle=40,
    )
    await dispatcher.run_once()

    assert catalog.marked == [1]


async def test_acil_mesaj_urun_gorseliyle_gider():
    url = "https://cdn.example/images/m/i/image_1080.jpeg"
    dispatcher, _, notifier = build([pending(1, EventKind.RESTOCK, image_url=url)])
    await dispatcher.run_once()

    assert notifier.messages[0].photo_url == url


# --- profil ve işaretleme hatası -----------------------------------------


async def test_acil_turler_profilden_gelir():
    profile = RetailerProfile(name="shop.example", urgent_kinds=frozenset({EventKind.STOCK_DOWN}))
    catalog = FakeCatalog([pending(1, EventKind.STOCK_DOWN), pending(2, EventKind.RESTOCK)])
    notifier = FakeNotifier()
    dispatcher = OutboxDispatcher(
        source=catalog, profile=profile, store=FakeRules((NIKE_RULE,)), notifier=notifier
    )

    await dispatcher.run_once()

    texts = [text for _, text in notifier.sent]
    assert any("STOK AZALDI" in text for text in texts)
    assert any("Tur özeti" in text and "Stoğa girenler" in text for text in texts)


async def test_isaretleme_hatasi_loglanir_ve_yukari_tasinir(caplog):
    class BrokenMark(FakeCatalog):
        async def mark_notified(self, ids) -> None:
            raise RuntimeError("bağlantı koptu")

    dispatcher = OutboxDispatcher(
        source=BrokenMark([pending(1)]), profile=PROFILE,
        store=FakeRules((NIKE_RULE,)), notifier=FakeNotifier(),
    )

    with pytest.raises(RuntimeError):
        await dispatcher.run_once()
    assert "işaretlenemedi" in caplog.text
