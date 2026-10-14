"""Kanal aramasında işe yarayacak hashtag üretimi.

Telegram hashtag'leri harf/rakam/alt çizgi kabul eder; Türkçe karakterler ve
boşluklar temizlenmelidir.
"""
import pytest

from monitor_notify.formatting.hashtags import hashtag, hashtags_for
from monitor_notify.model import EventKind, Notification


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Nike", "#Nike"),
        ("adidas", "#adidas"),  # marka kendi yazımını korur
        ("Air Jordan", "#AirJordan"),
        ("New Balance", "#NewBalance"),
        ("Off-White", "#OffWhite"),
        ("Beşiktaş", "#Besiktas"),
        ("Erkek Ayakkabı", "#ErkekAyakkabi"),
        ("Çocuk Giyim", "#CocukGiyim"),
        ("Mont & Ceket", "#MontCeket"),
        ("restock", "#restock"),
        ("price_drop", "#price_drop"),  # alt çizgi geçerli, bozulmamalı
    ],
)
def test_hashtag_temizlenir(raw: str, expected: str):
    assert hashtag(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", None, "550", "---", "42"])
def test_hashtaga_donmeyen_degerler_atlanir(raw):
    """Boş ve tamamen sayısal değerler geçerli hashtag değildir."""
    assert hashtag(raw) is None


def test_hashtag_turkce_buyuk_i_dogru_katlanir():
    assert hashtag("İstanbul") == "#Istanbul"


def test_hashtag_zaten_tek_kelimeyse_bozulmaz():
    assert hashtag("Salomon") == "#Salomon"


def test_olay_tipi_hashtagi_alt_cizgiyi_korur():
    tags = hashtags_for(item(event_type=EventKind.PRICE_DROP))
    assert "#price_drop" in tags


# --- ürün için hashtag seti -----------------------------------------------


def item(brand="Nike", categories=("Erkek Ayakkabı", "Sneaker"), event_type=EventKind.RESTOCK):
    return Notification(
        id=1,
        kind=event_type,
        product_name="Air Max Plus VII",
        brand=brand,
        categories=categories,
        variant_label="42",
        product_url="https://shop.example/air-max",
        old_stock=0,
        new_stock=1,
    )


def test_marka_ve_olay_hashtaglenir():
    tags = hashtags_for(item())
    assert "#Nike" in tags
    assert "#restock" in tags


def test_ilk_kategori_hashtaglenir():
    assert "#ErkekAyakkabi" in hashtags_for(item())


def test_markasiz_urunde_cokmeden_calisir():
    tags = hashtags_for(item(brand=None))
    assert "#restock" in tags
    assert all(tag.startswith("#") for tag in tags)


def test_kategorisiz_urunde_cokmeden_calisir():
    assert hashtags_for(item(categories=())) == ["#Nike", "#restock"]


def test_mukerrer_hashtag_uretilmez():
    tags = hashtags_for(item(brand="Sneaker", categories=("Sneaker",)))
    assert len(tags) == len(set(tags))


def test_hashtag_sirasi_sabittir():
    """Kanal akışında tutarlı görünsün diye sıra deterministik olmalı."""
    assert hashtags_for(item()) == ["#Nike", "#restock", "#ErkekAyakkabi"]
