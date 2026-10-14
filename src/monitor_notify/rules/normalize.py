"""Türkçe duyarlı metin normalizasyonu.

Kural eşleştirmede "ÇORAP" ile "çorap", "IPHONE" ile "iphone" aynı sayılmalıdır.
Python'un varsayılan ``lower()`` çağrısı Türkçe I/İ/ı/i dörtlüsünü doğru
çözmez, bu yüzden noktalı/noktasız ayrımı eşleştirme amacıyla tamamen kaldırılır.
"""
from __future__ import annotations

import re
import unicodedata

#: Türkçe'ye özgü harfler ASCII karşılıklarına indirgenir. Amaç doğru yazım
#: değil, kullanıcının klavyesinde ne yazdığından bağımsız eşleşmedir.
_FOLD = str.maketrans(
    {
        "İ": "i", "I": "i", "ı": "i",
        "Ş": "s", "ş": "s",
        "Ğ": "g", "ğ": "g",
        "Ü": "u", "ü": "u",
        "Ö": "o", "ö": "o",
        "Ç": "c", "ç": "c",
    }
)

_COMBINING_DOT_ABOVE = "̇"
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str | None) -> str:
    """Metni karşılaştırmaya hazır biçime indirger.

    Boşluklar tekilleştirilir, Türkçe harfler ASCII'ye katlanır, sonuç
    ``casefold`` edilir. ``None`` güvenle boş dizgeye dönüşür.
    """
    if not text:
        return ""
    folded = text.translate(_FOLD)
    decomposed = unicodedata.normalize("NFKD", folded)
    without_dots = decomposed.replace(_COMBINING_DOT_ABOVE, "")
    recomposed = unicodedata.normalize("NFC", without_dots)
    return _WHITESPACE.sub(" ", recomposed.casefold()).strip()


def contains(haystack: str | None, needle: str | None) -> bool:
    """Normalize edilmiş alt dizge araması. Boş iğne her zaman eşleşir."""
    normalized_needle = normalize(needle)
    if not normalized_needle:
        return True
    return normalized_needle in normalize(haystack)
