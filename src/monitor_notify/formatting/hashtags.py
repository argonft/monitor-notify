"""Duyuru kanalı için hashtag üretimi.

Kanal abonesi Telegram aramasıyla kendi ilgilendiği markayı ya da olay tipini
filtreleyebilsin diye mesajlara hashtag eklenir.

Telegram hashtag'leri yalnızca harf, rakam ve alt çizgi kabul eder; Türkçe
karakterler ASCII'ye katlanır, boşluklar ve noktalama atılır.
"""
from __future__ import annotations

import re
import unicodedata

from ..model import Notification

#: Telegram hashtag'i harf, rakam ve alt çizgi kabul eder.
_INVALID = re.compile(r"[^0-9A-Za-z_]+")

#: Türkçe harfler doğrudan ASCII karşılıklarına katlanır. ``normalize`` ile
#: aynı eşleme, ama burada sonuç küçük harfe indirilmez - hashtag okunabilir
#: kalsın diye kelime baş harfleri korunur.
_FOLD = str.maketrans(
    {
        "İ": "I", "I": "I", "ı": "i",
        "Ş": "S", "ş": "s",
        "Ğ": "G", "ğ": "g",
        "Ü": "U", "ü": "u",
        "Ö": "O", "ö": "o",
        "Ç": "C", "ç": "c",
    }
)


def hashtag(text: str | None) -> str | None:
    """Metni Telegram hashtag'ine çevirir; çevrilemezse ``None``.

    ``"Air Jordan"`` -> ``"#AirJordan"``, ``"Beşiktaş"`` -> ``"#Besiktas"``.

    Kaynağın kendi yazımı korunur: ``"adidas"`` -> ``"#adidas"``, ``"restock"``
    -> ``"#restock"``. Telegram hashtag araması büyük/küçük harf ayırmadığı
    için dönüştürmeye gerek yok; dönüştürmemek marka adlarını da bozmaz.

    Boş ve tamamen sayısal değerler hashtag olmaz (``"42"`` beden numarasıdır,
    etiket değil).
    """
    if not text or not text.strip():
        return None

    folded = unicodedata.normalize("NFKD", text.translate(_FOLD))
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    joined = "".join(word for word in _INVALID.split(ascii_only) if word)
    if not joined or joined.isdigit() or joined.strip("_") == "":
        return None
    return f"#{joined}"


def hashtags_for(item: Notification) -> list[str]:
    """Bir bildirim için marka, olay tipi ve ana kategori hashtag'leri.

    Sıra deterministiktir; kanal akışında mesajlar tutarlı görünsün diye.
    """
    candidates = [item.brand, str(item.kind)]
    if item.categories:
        candidates.append(item.categories[0])
    return _unique(hashtag(value) for value in candidates)


def brand_hashtags(items: list[Notification], *, limit: int = 8) -> list[str]:
    """Özet mesajının sonuna eklenecek marka hashtag'leri."""
    return _unique((hashtag(item.brand) for item in items))[:limit]


def _unique(tags) -> list[str]:
    seen: dict[str, None] = {}
    for tag in tags:
        if tag is not None:
            seen.setdefault(tag, None)
    return list(seen)
