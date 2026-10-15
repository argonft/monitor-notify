"""Retailer profili: mesaj görünümünü belirleyen ayarlar."""
import pytest

from monitor_notify.model import EventKind
from monitor_notify.profile import DEFAULT_URGENT_KINDS, RetailerProfile


def test_varsayilanlar():
    profile = RetailerProfile(name="shop.example")
    assert profile.variant_noun == "Beden"
    assert profile.urgent_kinds == frozenset({EventKind.RESTOCK, EventKind.PRICE_DROP})
    assert profile.button_label == "🛒 Ürüne git"
    assert profile.urgent_kinds == DEFAULT_URGENT_KINDS


@pytest.mark.parametrize("field", ["name", "variant_noun", "button_label"])
def test_bos_metin_alanlari_reddedilir(field):
    with pytest.raises(ValueError):
        RetailerProfile(**{"name": "shop.example", field: "  "})


def test_acil_turler_duz_metinle_verilebilir():
    profile = RetailerProfile(name="shop.example", urgent_kinds=frozenset({"restock"}))
    assert profile.urgent_kinds == frozenset({EventKind.RESTOCK})


def test_bilinmeyen_acil_tur_reddedilir():
    with pytest.raises(ValueError):
        RetailerProfile(name="shop.example", urgent_kinds=frozenset({"campaign"}))


def test_kuralsiz_gonderim_varsayilan_kapali():
    assert RetailerProfile(name="shop.example").notify_without_rules is False
    assert RetailerProfile(name="shop.example", notify_without_rules=True).notify_without_rules
