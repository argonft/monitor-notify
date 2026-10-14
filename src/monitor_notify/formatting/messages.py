"""Bildirimleri Telegram mesajına çeviren saf fonksiyonlar."""
from __future__ import annotations

from collections import OrderedDict
from typing import Sequence

from ..delivery.message import OutgoingMessage
from ..model import EventKind, Notification
from ..profile import RetailerProfile
from .hashtags import brand_hashtags, hashtags_for
from .money import format_money

_HEADLINE: dict[EventKind, str] = {
    EventKind.RESTOCK: "🔥 RESTOCK",
    EventKind.PRICE_DROP: "💸 FİYAT DÜŞTÜ",
    EventKind.OUT_OF_STOCK: "⛔️ TÜKENDİ",
    EventKind.STOCK_UP: "📈 STOK ARTTI",
    EventKind.STOCK_DOWN: "📉 STOK AZALDI",
    EventKind.PRICE_UP: "📊 FİYAT ARTTI",
    EventKind.NEW_PRODUCT: "🆕 YENİ ÜRÜN",
    EventKind.NEW_VARIANT: "➕ YENİ BEDEN",
    EventKind.VARIANT_REMOVED: "🗑 KALDIRILDI",
}

_DIGEST_SECTION: dict[EventKind, str] = {
    EventKind.NEW_PRODUCT: "🆕 Yeni ürünler",
    EventKind.NEW_VARIANT: "➕ Yeni bedenler",
    EventKind.OUT_OF_STOCK: "⛔️ Tükenenler",
    EventKind.STOCK_UP: "📈 Stok artanlar",
    EventKind.STOCK_DOWN: "📉 Stok azalanlar",
    EventKind.PRICE_UP: "📊 Zamlananlar",
    EventKind.PRICE_DROP: "💸 İndirime girenler",
    EventKind.RESTOCK: "🔥 Stoğa girenler",
    EventKind.VARIANT_REMOVED: "🗑 Kaldırılanlar",
}

_STOCK_KINDS = frozenset(
    {
        EventKind.RESTOCK,
        EventKind.OUT_OF_STOCK,
        EventKind.STOCK_UP,
        EventKind.STOCK_DOWN,
        EventKind.VARIANT_REMOVED,
    }
)
_PRICE_KINDS = frozenset({EventKind.PRICE_DROP, EventKind.PRICE_UP})
_NEW_KINDS = frozenset({EventKind.NEW_PRODUCT, EventKind.NEW_VARIANT})


def format_urgent(item: Notification, profile: RetailerProfile) -> OutgoingMessage:
    """Tek bildirim için anında gönderilecek mesaj.

    Ürün linki metne değil, mesajın altındaki butona konur. Görsel varsa
    mesaj fotoğraf altyazısı olarak gider.
    """
    lines = [_HEADLINE[item.kind], item.title, _detail_line(item, profile)]
    price_line = _price_line(item)
    if price_line:
        lines.append(price_line)

    tags = hashtags_for(item)
    if tags:
        lines.extend(["", " ".join(tags)])

    return OutgoingMessage(
        text="\n".join(lines),
        button_url=item.product_url,
        button_label=profile.button_label,
        photo_url=item.image_url,
    )


def format_digest(
    items: Sequence[Notification], *, max_items: int = 40
) -> OutgoingMessage | None:
    """Tur sonunda gönderilecek gruplanmış özet.

    ``max_items`` aşılırsa kalanlar tek satırda toplanır. Özet birden çok ürün
    içerdiği için buton ve görsel taşımaz; linkler satır içinde kalır.
    """
    if not items:
        return None

    shown = list(items[:max_items])
    overflow = len(items) - len(shown)

    sections: OrderedDict[EventKind, list[str]] = OrderedDict()
    for item in shown:
        sections.setdefault(item.kind, []).append(_digest_line(item))

    parts = [f"📦 Tur özeti — {len(items)} değişiklik", ""]
    for kind, lines in sections.items():
        parts.append(f"{_DIGEST_SECTION[kind]} ({len(lines)})")
        parts.extend(lines)
        parts.append("")

    if overflow > 0:
        parts.append(f"… ve {overflow} değişiklik daha (/status ile gör)")

    tags = brand_hashtags(shown)
    if tags:
        parts.extend(["", " ".join(tags)])
    return OutgoingMessage(text="\n".join(parts).strip())


def _detail_line(item: Notification, profile: RetailerProfile) -> str:
    variant = f"{profile.variant_noun} {item.variant_label}" if item.variant_label else "Varyant"
    if item.kind in _STOCK_KINDS:
        return f"{variant} — stok: {item.old_stock} → {item.new_stock}"
    if item.kind in _NEW_KINDS:
        return f"{variant} — stok: {item.new_stock}"
    return variant


def _price_line(item: Notification) -> str:
    if item.kind in _PRICE_KINDS:
        return f"{format_money(item.old_price)} → {format_money(item.new_price)}"

    current = item.discount_price if item.discount_price is not None else item.sell_price
    if current is None:
        return ""
    ratio = item.discount_ratio
    if ratio is None:
        return format_money(current)
    return f"{format_money(current)}  (liste {format_money(item.sell_price)}, %{ratio} indirim)"


def _digest_line(item: Notification) -> str:
    label = item.variant_label or "-"
    if item.kind in _STOCK_KINDS:
        change = f"{item.old_stock}→{item.new_stock}"
    elif item.kind in _PRICE_KINDS:
        change = f"{format_money(item.old_price)} → {format_money(item.new_price)}"
    else:
        change = format_money(item.discount_price or item.sell_price)
    return f"• {item.title} [{label}] {change}\n  {item.display_url}"
