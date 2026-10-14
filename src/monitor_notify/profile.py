"""Retailer'a özgü görünüm ayarları.

Mesajların yapısı bütün retailer'larda aynıdır; yalnızca burada tanımlı
ayrıntılar (mağaza adı, varyant ismi, acil sayılan olaylar, buton metni)
değişir.
"""
from __future__ import annotations

from dataclasses import dataclass

from .delivery.message import DEFAULT_BUTTON_LABEL
from .model import EventKind

DEFAULT_URGENT_KINDS: frozenset[EventKind] = frozenset(
    {EventKind.RESTOCK, EventKind.PRICE_DROP}
)


@dataclass(frozen=True, slots=True)
class RetailerProfile:
    #: /help başlığında görünür, örn. "shop.example".
    name: str
    #: Acil mesajda varyant etiketinin önüne gelir: "Beden 42".
    variant_noun: str = "Beden"
    #: Anında tek mesaj olarak gidenler; gerisi özette toplanır.
    urgent_kinds: frozenset[EventKind] = DEFAULT_URGENT_KINDS
    button_label: str = DEFAULT_BUTTON_LABEL

    def __post_init__(self) -> None:
        for field_name in ("name", "variant_noun", "button_label"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"RetailerProfile.{field_name} boş olamaz.")
        object.__setattr__(
            self, "urgent_kinds", frozenset(EventKind(kind) for kind in self.urgent_kinds)
        )
