"""Türkçe metin normalizasyonu ve bildirim filtresi."""
import pytest

from monitor_notify.model import EventKind
from monitor_notify.rules.matcher import (
    MatchDecision,
    ProductContext,
    Rule,
    RuleKind,
    matches,
)
from monitor_notify.rules.normalize import normalize


# --- normalizasyon --------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ÇORAP", "corap"),
        ("çorap", "corap"),
        ("Çorap", "corap"),
        ("ŞAPKA", "sapka"),
        ("Göz", "goz"),
        ("Ürün", "urun"),
        ("Iğdır", "igdir"),
        ("İSTANBUL", "istanbul"),
        ("istanbul", "istanbul"),
        ("ıslak", "islak"),
        ("  Nike   Air  ", "nike air"),
        ("", ""),
    ],
)
def test_normalize_turkce_harfleri_esitler(raw: str, expected: str):
    assert normalize(raw) == expected


def test_normalize_noktali_ve_noktasiz_i_ayrimini_kaldirir():
    """Türkçe I/İ/ı/i dörtlüsü eşleşmede ayrım yaratmamalı."""
    assert normalize("IPHONE") == normalize("iphone") == normalize("İPHONE") == normalize("ıphone")


# --- filtre ---------------------------------------------------------------

NIKE = ProductContext(
    name="Air Max Plus VII 'White Black'",
    brand="Nike",
    categories=("Erkek Ayakkabı", "Sneaker"),
)
CORAP = ProductContext(name="Nike Everyday Çorap", brand="Nike", categories=("Aksesuar",))


def rule(kind: RuleKind, pattern: str, *, rule_id: int = 1, event_types=None, active=True) -> Rule:
    return Rule(
        id=rule_id,
        kind=kind,
        pattern=pattern,
        event_types=frozenset(event_types) if event_types else None,
        is_active=active,
    )


def test_kural_yoksa_bildirim_gitmez():
    """Varsayılan sessizlik: gürültü değil, sessizlik."""
    decision = matches(EventKind.RESTOCK, NIKE, ())
    assert decision.allowed is False


def test_marka_kurali_esleseni_gecirir():
    decision = matches(EventKind.RESTOCK, NIKE, (rule(RuleKind.BRAND, "Nike"),))
    assert decision.allowed is True
    assert decision.matched_rule_id == 1


def test_marka_kurali_eslesmeyeni_eler():
    decision = matches(EventKind.RESTOCK, NIKE, (rule(RuleKind.BRAND, "Adidas"),))
    assert decision.allowed is False


def test_keyword_urun_adinda_aranir():
    decision = matches(EventKind.RESTOCK, NIKE, (rule(RuleKind.KEYWORD, "air max"),))
    assert decision.allowed is True


def test_kategori_kurali_kategorilerde_aranir():
    decision = matches(EventKind.RESTOCK, NIKE, (rule(RuleKind.CATEGORY, "sneaker"),))
    assert decision.allowed is True


def test_negatif_keyword_pozitif_kurali_ezer():
    """Negatif her zaman kazanır: marka eşleşse bile çorap susturulur."""
    rules = (rule(RuleKind.BRAND, "Nike", rule_id=1), rule(RuleKind.NEGATIVE_KEYWORD, "çorap", rule_id=2))
    decision = matches(EventKind.RESTOCK, CORAP, rules)

    assert decision.allowed is False
    assert decision.matched_rule_id == 2


def test_negatif_keyword_ilgisiz_urunu_etkilemez():
    rules = (rule(RuleKind.BRAND, "Nike", rule_id=1), rule(RuleKind.NEGATIVE_KEYWORD, "çorap", rule_id=2))
    assert matches(EventKind.RESTOCK, NIKE, rules).allowed is True


def test_negatif_keyword_buyuk_kucuk_harf_farki_gozetmez():
    rules = (rule(RuleKind.BRAND, "nike", rule_id=1), rule(RuleKind.NEGATIVE_KEYWORD, "ÇORAP", rule_id=2))
    assert matches(EventKind.RESTOCK, CORAP, rules).allowed is False


def test_pasif_kural_dikkate_alinmaz():
    assert matches(EventKind.RESTOCK, NIKE, (rule(RuleKind.BRAND, "Nike", active=False),)).allowed is False


def test_pasif_negatif_kural_susturmaz():
    rules = (
        rule(RuleKind.BRAND, "Nike", rule_id=1),
        rule(RuleKind.NEGATIVE_KEYWORD, "çorap", rule_id=2, active=False),
    )
    assert matches(EventKind.RESTOCK, CORAP, rules).allowed is True


def test_kural_event_tipiyle_sinirlandirilabilir():
    """'Nike'ta sadece restock istiyorum' senaryosu."""
    only_restock = (rule(RuleKind.BRAND, "Nike", event_types=[EventKind.RESTOCK]),)

    assert matches(EventKind.RESTOCK, NIKE, only_restock).allowed is True
    assert matches(EventKind.STOCK_DOWN, NIKE, only_restock).allowed is False


def test_event_tipi_kisitsiz_kural_tum_tipleri_gecirir():
    any_event = (rule(RuleKind.BRAND, "Nike"),)
    assert matches(EventKind.PRICE_UP, NIKE, any_event).allowed is True


def test_farkli_kurallar_farkli_event_tipleri_icin_birlesir():
    """Nike'ta restock + her markada price_drop."""
    rules = (
        rule(RuleKind.BRAND, "Nike", rule_id=1, event_types=[EventKind.RESTOCK]),
        rule(RuleKind.KEYWORD, "", rule_id=2, event_types=[EventKind.PRICE_DROP]),
    )
    adidas = ProductContext(name="Samba OG", brand="Adidas", categories=("Sneaker",))

    assert matches(EventKind.RESTOCK, NIKE, rules).allowed is True
    assert matches(EventKind.PRICE_DROP, adidas, rules).allowed is True
    assert matches(EventKind.RESTOCK, adidas, rules).allowed is False


def test_marka_bos_olan_urun_cokmeden_elenir():
    markasiz = ProductContext(name="Bilinmeyen", brand=None, categories=())
    assert matches(EventKind.RESTOCK, markasiz, (rule(RuleKind.BRAND, "Nike"),)).allowed is False


def test_karar_nesnesi_sebep_tasir():
    decision = matches(EventKind.RESTOCK, NIKE, ())
    assert isinstance(decision, MatchDecision)
    assert decision.reason


def test_bildirimden_urun_baglami_kurulur():
    from monitor_notify.model import Notification
    from monitor_notify.rules.matcher import ProductContext

    notification = Notification(
        id=1, kind=EventKind.RESTOCK, product_name="Air Max", brand="Nike",
        categories=("Sneaker",), variant_label="42", product_url="https://shop.example/a",
    )
    assert ProductContext.of(notification) == ProductContext("Air Max", "Nike", ("Sneaker",))
