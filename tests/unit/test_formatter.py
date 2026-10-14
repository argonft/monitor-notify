"""Telegram mesaj üretimi.

Para birimi kuralı zorunludur: tutarlar "5.499,50 TL" biçiminde yazılır,
Türk Lirası sembolü hiçbir çıktıda geçmez.
"""
from decimal import Decimal

import pytest

from monitor_notify.formatting.messages import format_digest, format_urgent
from monitor_notify.formatting.money import format_money
from monitor_notify.model import EventKind, Notification
from monitor_notify.profile import RetailerProfile

LIRA_SIGN = "₺"
PROFILE = RetailerProfile(name="shop.example")


def urgent(notification: Notification, profile: RetailerProfile = PROFILE):
    return format_urgent(notification, profile)


def item(
    event_type: EventKind = EventKind.RESTOCK,
    *,
    old_stock: int | None = 0,
    new_stock: int | None = 3,
    old_price: str | None = None,
    new_price: str | None = None,
    sell_price: str | None = "10999",
    discount_price: str | None = None,
    name: str = "Air Max Plus VII 'White Black'",
    brand: str | None = "Nike",
    label: str = "42",
    image_url: str | None = None,
) -> Notification:
    return Notification(
        id=1,
        kind=event_type,
        product_name=name,
        brand=brand,
        categories=(),
        variant_label=label,
        product_url="https://shop.example/air-max-plus-vii-white-black-hq2197-100",
        image_url=image_url,
        sell_price=Decimal(sell_price) if sell_price else None,
        discount_price=Decimal(discount_price) if discount_price else None,
        old_stock=old_stock,
        new_stock=new_stock,
        old_price=Decimal(old_price) if old_price else None,
        new_price=Decimal(new_price) if new_price else None,
    )


# --- para formatı (kritik kural) ------------------------------------------


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("10999", "10.999 TL"),
        ("5499.50", "5.499,50 TL"),
        ("5499.5", "5.499,50 TL"),
        ("1234567.89", "1.234.567,89 TL"),
        ("999", "999 TL"),
        ("0", "0 TL"),
        ("10999.00", "10.999 TL"),
    ],
)
def test_para_formati_binlik_nokta_ondalik_virgul(amount: str, expected: str):
    assert format_money(Decimal(amount)) == expected


def test_para_formati_asla_lira_sembolu_kullanmaz():
    assert LIRA_SIGN not in format_money(Decimal("5499.50"))


def test_fiyat_yoksa_cizgi_doner():
    assert format_money(None) == "—"


# --- acil mesajlar --------------------------------------------------------


def test_restock_mesaji_stok_gecisini_icerir():
    message = urgent(item(EventKind.RESTOCK, old_stock=0, new_stock=3)).text

    assert "RESTOCK" in message
    assert "Nike" in message
    assert "Air Max Plus VII" in message
    assert "42" in message
    assert "0 → 3" in message


# --- buton ve hashtag (duyuru kanalı) -------------------------------------


def test_acil_mesaj_urun_butonu_tasir():
    """Duyuru kanalında link metin yerine butonda durur."""
    message = urgent(item(EventKind.RESTOCK))

    assert message.has_button is True
    assert message.button_url == "https://shop.example/air-max-plus-vii-white-black-hq2197-100"


def test_buton_urlsi_sema_icerir():
    """Telegram şemasız URL kabul etmez."""
    assert urgent(item()).button_url.startswith("https://")


def test_acil_mesaj_marka_ve_olay_hashtagi_tasir():
    message = urgent(item(EventKind.RESTOCK)).text

    assert "#Nike" in message
    assert "#restock" in message


def test_markasiz_urunde_hashtag_satiri_cokmez():
    message = urgent(item(brand=None)).text
    assert "#restock" in message


def test_ozet_buton_tasimaz():
    """Özet birden çok ürün içerir; tek buton anlamsız olurdu."""
    digest = format_digest([item(EventKind.STOCK_DOWN)], max_items=40)
    assert digest.has_button is False


def test_ozet_link_satirlarini_korur():
    digest = format_digest([item(EventKind.STOCK_DOWN)], max_items=40).text
    assert "shop.example/air-max-plus-vii-white-black-hq2197-100" in digest


def test_ozet_sonunda_marka_hashtagleri_bulunur():
    items = [
        item(EventKind.STOCK_DOWN),
        item(EventKind.STOCK_DOWN, brand="Adidas", name="Samba OG"),
    ]
    digest = format_digest(items, max_items=40).text

    assert "#Nike" in digest
    assert "#Adidas" in digest


def test_indirimli_urun_mesajinda_liste_fiyati_ve_yuzde_gosterilir():
    message = urgent(
        item(EventKind.RESTOCK, sell_price="10999", discount_price="5499.50")
    ).text

    assert "5.499,50 TL" in message
    assert "10.999 TL" in message
    assert "%50" in message


def test_indirim_yoksa_yuzde_satiri_eklenmez():
    message = urgent(item(EventKind.RESTOCK, sell_price="10999")).text
    assert "%" not in message


def test_price_drop_mesaji_eski_ve_yeni_fiyati_gosterir():
    message = urgent(
        item(EventKind.PRICE_DROP, old_price="10999", new_price="5499.50", discount_price="5499.50")
    ).text

    assert "10.999 TL" in message
    assert "5.499,50 TL" in message


def test_hicbir_mesajda_lira_sembolu_gecmez():
    for event_type in EventKind:
        message = urgent(item(event_type, old_price="10999", new_price="5499.50")).text
        assert LIRA_SIGN not in message, event_type


def test_markasiz_urun_mesaji_cokmeden_uretilir():
    message = urgent(item(brand=None)).text
    assert "Air Max Plus VII" in message


# --- özet mesajı ----------------------------------------------------------


def test_ozet_event_tipine_gore_gruplar():
    items = [
        item(EventKind.STOCK_DOWN, old_stock=3, new_stock=1),
        item(EventKind.STOCK_DOWN, old_stock=5, new_stock=2, label="43"),
        item(EventKind.NEW_PRODUCT, name="Samba OG", brand="Adidas"),
    ]
    digest = format_digest(items, max_items=40).text

    assert digest.count("Samba OG") == 1
    assert "43" in digest


def test_ozet_bos_listede_none_doner():
    assert format_digest([], max_items=40) is None


def test_ozet_ust_siniri_asinca_kalani_tek_satirda_toplar():
    """Sel koruması: 500 event tek mesajda boğulmamalı."""
    items = [item(EventKind.STOCK_DOWN, label=str(i)) for i in range(500)]
    digest = format_digest(items, max_items=40).text

    assert "460 değişiklik daha" in digest


def test_ozet_ust_sinirin_altinda_ek_satir_koymaz():
    digest = format_digest([item(EventKind.STOCK_DOWN)], max_items=40).text
    assert "değişiklik daha" not in digest


def test_ozet_lira_sembolu_icermez():
    items = [item(EventKind.PRICE_UP, old_price="5499.50", new_price="10999")]
    assert LIRA_SIGN not in format_digest(items, max_items=40).text


# --- görsel ---------------------------------------------------------------


def test_acil_mesaj_urun_gorselini_tasir():
    message = urgent(item(image_url="https://cdn.example/images/m/i/image_1080.jpeg"))
    assert message.photo_url == "https://cdn.example/images/m/i/image_1080.jpeg"


def test_gorseli_olmayan_urunde_photo_url_bos():
    assert urgent(item()).photo_url is None


def test_ozet_mesaj_gorsel_tasimaz():
    message = format_digest([item(EventKind.STOCK_UP, image_url="https://cdn.example/y.jpeg")])
    assert message.photo_url is None


# --- profil ---------------------------------------------------------------


def test_varyant_ismi_profilden_gelir():
    profile = RetailerProfile(name="shop.example", variant_noun="Gramaj")
    assert "Gramaj 42" in urgent(item(), profile).text


def test_bos_varyant_etiketinde_sarkan_isim_yazilmaz():
    text = urgent(item(label="")).text
    assert "Varyant" in text
    assert "Beden " not in text


def test_buton_etiketi_profilden_gelir():
    profile = RetailerProfile(name="shop.example", button_label="Satın al")
    assert urgent(item(), profile).button_label == "Satın al"


def test_buton_urun_urline_gider():
    assert urgent(item()).button_url == "https://shop.example/air-max-plus-vii-white-black-hq2197-100"
