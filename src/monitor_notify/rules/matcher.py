"""Bir event'in bildirilip bildirilmeyeceğine karar veren saf fonksiyon.

Değerlendirme sırası (tasarım dokümanı, Bölüm 8) - negatif her zaman kazanır:

1. ``negative_keyword`` eşleşti mi -> ELE
2. ``brand`` / ``keyword`` / ``category`` eşleşti mi -> GEÇ
3. Hiçbiri -> ELE (varsayılan sessizlik)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Sequence

from ..model import EventKind, Notification
from .normalize import contains, normalize


class RuleKind(StrEnum):
    BRAND = "brand"
    KEYWORD = "keyword"
    CATEGORY = "category"
    NEGATIVE_KEYWORD = "negative_keyword"


POSITIVE_KINDS: frozenset[RuleKind] = frozenset(
    {RuleKind.BRAND, RuleKind.KEYWORD, RuleKind.CATEGORY}
)


@dataclass(frozen=True, slots=True)
class Rule:
    id: int
    kind: RuleKind
    pattern: str
    event_types: frozenset[EventKind] | None = None
    is_active: bool = True

    def covers(self, event_type: EventKind) -> bool:
        """Kural bu event tipini kapsıyor mu? ``None`` = hepsi."""
        return self.event_types is None or event_type in self.event_types


@dataclass(frozen=True, slots=True)
class ProductContext:
    """Eşleştirmede kullanılan ürün bilgisi."""

    name: str
    brand: str | None
    categories: tuple[str, ...]

    @property
    def haystack(self) -> str:
        """Ad, marka ve kategorilerin birleşimi - keyword aramasının alanı."""
        parts = [self.name, self.brand or "", *self.categories]
        return normalize(" ".join(parts))

    @classmethod
    def of(cls, notification: Notification) -> ProductContext:
        """Bildirimden eşleştirme bağlamı kurar."""
        return cls(
            name=notification.product_name,
            brand=notification.brand,
            categories=notification.categories,
        )


@dataclass(frozen=True, slots=True)
class MatchDecision:
    allowed: bool
    reason: str
    matched_rule_id: int | None = None


_NO_RULES = MatchDecision(False, "kural tanımlı değil")
_NO_POSITIVE = MatchDecision(False, "hiçbir pozitif kural eşleşmedi")


def matches(
    event_type: EventKind,
    product: ProductContext,
    rules: Sequence[Rule] | Iterable[Rule],
) -> MatchDecision:
    """Event bildirilmeli mi? Yan etkisiz."""
    active = [rule for rule in rules if rule.is_active and rule.covers(event_type)]
    if not active:
        return _NO_RULES

    for rule in active:
        if rule.kind is RuleKind.NEGATIVE_KEYWORD and _hits(rule, product):
            return MatchDecision(False, f"negatif kural eşleşti: {rule.pattern}", rule.id)

    for rule in active:
        if rule.kind in POSITIVE_KINDS and _hits(rule, product):
            return MatchDecision(True, f"{rule.kind} kuralı eşleşti: {rule.pattern}", rule.id)

    return _NO_POSITIVE


def _hits(rule: Rule, product: ProductContext) -> bool:
    """Kuralın kendi türüne göre hangi alanda arayacağını belirler."""
    if rule.kind is RuleKind.BRAND:
        return bool(product.brand) and contains(product.brand, rule.pattern)
    if rule.kind is RuleKind.CATEGORY:
        return any(contains(category, rule.pattern) for category in product.categories)
    return contains(product.haystack, rule.pattern)
