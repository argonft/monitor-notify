"""Retailer ile bildirim katmanı arasındaki tek sözleşme.

Retailer her bildirimi bir ``Notification`` olarak verir; kütüphane biçimlendirme,
kural eşleştirme ve gönderimi buna dayanarak yapar. Doğrulama oluşturma anında
yapılır: bozuk veri kanalda bozuk mesaj olarak değil, retailer'ın testinde
hata olarak ortaya çıkar.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

_HTTP_SCHEMES = ("http://", "https://")


class EventKind(StrEnum):
    """Bildirim türleri. Değerler DB'de metin olarak saklanır; değiştirilmez."""

    RESTOCK = "restock"
    OUT_OF_STOCK = "out_of_stock"
    STOCK_UP = "stock_up"
    STOCK_DOWN = "stock_down"
    PRICE_DROP = "price_drop"
    PRICE_UP = "price_up"
    NEW_PRODUCT = "new_product"
    NEW_VARIANT = "new_variant"
    VARIANT_REMOVED = "variant_removed"


@dataclass(frozen=True, slots=True)
class VariantStock:
    """Bir varyantın etiketi ve stoğu; ürün düzeyindeki bildirimde listelenir."""

    label: str
    stock: int

    def __post_init__(self) -> None:
        if self.stock < 0:
            raise ValueError(f"Varyant stoğu negatif olamaz: {self.label!r}={self.stock}")


@dataclass(frozen=True, slots=True)
class Notification:
    """Gönderime aday tek bir değişiklik ve mesaj için gereken ürün bilgisi."""

    id: int
    kind: EventKind
    product_name: str
    brand: str | None
    categories: tuple[str, ...]
    variant_label: str
    product_url: str
    image_url: str | None = None
    sell_price: Decimal | None = None
    discount_price: Decimal | None = None
    old_stock: int | None = None
    new_stock: int | None = None
    old_price: Decimal | None = None
    new_price: Decimal | None = None
    #: Ürünün bütün varyantları. Doluysa mesaj tek varyant yerine bu listeyi
    #: gösterir; ürün başına tek gelen ``new_product`` bildirimi için kullanılır.
    variants: tuple[VariantStock, ...] = ()

    def __post_init__(self) -> None:
        # DB'den gelen düz metin kabul edilir; bilinmeyen değer ValueError verir.
        object.__setattr__(self, "kind", EventKind(self.kind))
        object.__setattr__(self, "variants", tuple(self.variants))
        if not self.product_name.strip():
            raise ValueError("product_name boş olamaz.")
        if not self.product_url.startswith("https://"):
            raise ValueError(f"product_url https ile başlamalı: {self.product_url!r}")
        if self.image_url is not None and not self.image_url.startswith(_HTTP_SCHEMES):
            raise ValueError(f"image_url http(s) olmalı: {self.image_url!r}")

    @property
    def title(self) -> str:
        return f"{self.brand} · {self.product_name}" if self.brand else self.product_name

    @property
    def total_stock(self) -> int:
        """Varyant listesinin toplam stoğu."""
        return sum(variant.stock for variant in self.variants)

    @property
    def display_url(self) -> str:
        """Mesaj metninde gösterilen kısa biçim."""
        return self.product_url.removeprefix("https://")

    @property
    def discount_ratio(self) -> int | None:
        """İndirim yüzdesi; indirim yoksa ``None``."""
        if self.discount_price is None or not self.sell_price:
            return None
        if self.discount_price >= self.sell_price:
            return None
        ratio = (self.sell_price - self.discount_price) / self.sell_price * 100
        return int(ratio.quantize(Decimal("1")))
