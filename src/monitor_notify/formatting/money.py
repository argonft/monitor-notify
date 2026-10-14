"""Türk Lirası biçimi.

Tutarlar ``5.499,50 TL`` biçiminde yazılır - binlik ayracı nokta, ondalık
ayracı virgül, son ek ``TL``. Türk Lirası sembolü hiçbir çıktıda kullanılmaz;
kaynak sistem sembol döndürse bile yok sayılır.
"""
from __future__ import annotations

from decimal import Decimal

NO_PRICE = "—"


def format_money(amount: Decimal | None) -> str:
    """Tutarı Türk Lirası biçimine çevirir. Sembol değil, ``TL`` son eki kullanılır."""
    if amount is None:
        return NO_PRICE
    quantized = amount.quantize(Decimal("0.01"))
    whole, _, fraction = f"{quantized:.2f}".partition(".")
    grouped = f"{int(whole):,}".replace(",", ".")
    if fraction == "00":
        return f"{grouped} TL"
    return f"{grouped},{fraction} TL"
