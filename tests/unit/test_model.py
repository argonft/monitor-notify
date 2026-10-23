"""Retailer ile kütüphane arasındaki tek sözleşme: Notification."""
from decimal import Decimal

import pytest

from monitor_notify.model import EventKind, Notification, VariantStock


def note(**overrides) -> Notification:
    fields = {
        "id": 1,
        "kind": EventKind.RESTOCK,
        "product_name": "Air Max Plus VII",
        "brand": "Nike",
        "categories": ("Sneaker",),
        "variant_label": "42",
        "product_url": "https://shop.example/air-max",
    }
    fields.update(overrides)
    return Notification(**fields)


def test_event_kind_degerleri_sabit():
    """Değerler DB'de metin olarak durur; değişmeleri kural ve kuyruğu bozar."""
    assert [str(kind) for kind in EventKind] == [
        "restock", "out_of_stock", "stock_up", "stock_down", "price_drop",
        "price_up", "new_product", "new_variant", "variant_removed",
    ]


def test_duz_metin_kind_enuma_cevrilir():
    assert note(kind="restock").kind is EventKind.RESTOCK


def test_bilinmeyen_kind_reddedilir():
    with pytest.raises(ValueError):
        note(kind="campaign")


def test_https_olmayan_urun_url_reddedilir():
    with pytest.raises(ValueError):
        note(product_url="http://shop.example/x")


def test_bos_urun_adi_reddedilir():
    with pytest.raises(ValueError):
        note(product_name="   ")


def test_http_olmayan_gorsel_reddedilir():
    with pytest.raises(ValueError):
        note(image_url="ftp://cdn.example/x.jpeg")


def test_gorsel_http_veya_https_olabilir():
    assert note(image_url="http://cdn.example/x.jpeg").image_url.startswith("http://")


def test_baslik_marka_ile_birlesir():
    assert note().title == "Nike · Air Max Plus VII"


def test_markasiz_baslik_yalnizca_ad():
    assert note(brand=None).title == "Air Max Plus VII"


def test_gorunen_url_semasiz():
    assert note().display_url == "shop.example/air-max"


def test_indirim_orani_hesaplanir():
    item = note(sell_price=Decimal("10000"), discount_price=Decimal("7500"))
    assert item.discount_ratio == 25


@pytest.mark.parametrize(
    ("sell", "discount"),
    [(None, None), (Decimal("100"), None), (Decimal("100"), Decimal("100")), (Decimal("0"), Decimal("0"))],
)
def test_indirim_yoksa_oran_none(sell, discount):
    assert note(sell_price=sell, discount_price=discount).discount_ratio is None


def test_model_degistirilemez():
    with pytest.raises(AttributeError):
        note().product_name = "x"  # type: ignore[misc]


# --- varyant listesi --------------------------------------------------------


def test_varyant_listesi_varsayilan_bos():
    assert note().variants == ()


def test_varyant_listesi_tuplea_cevrilir():
    item = note(variants=[VariantStock("42", 3), VariantStock("43", 0)])
    assert item.variants == (VariantStock("42", 3), VariantStock("43", 0))


def test_varyant_listesi_toplam_stok():
    item = note(variants=(VariantStock("42", 3), VariantStock("43", 2)))
    assert item.total_stock == 5


def test_negatif_varyant_stogu_reddedilir():
    with pytest.raises(ValueError):
        VariantStock("42", -1)
