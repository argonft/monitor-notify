"""Retailer testleri için yardımcılar.

Kullanım (retailer'ın entegrasyon testinde, kaynağa en az iki bekleyen
bildirim ekledikten sonra)::

    await check_event_source_contract(MyEventSource(pool))
"""
from __future__ import annotations

from .model import Notification
from .ports import EventSource


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def check_event_source_contract(source: EventSource, *, limit: int = 50) -> None:
    """``EventSource`` sözleşmesini doğrular; ihlalde ``AssertionError``.

    Kaynağın tamamı bu çağrıda tüketilebilir; testin sonunda kaynakta en az
    bir bildirim işaretlenmiş olur.
    """
    first = list(await source.pending(limit))
    _require(len(first) >= 2, "Sözleşme testi için kaynakta en az iki bekleyen bildirim olmalı.")
    _require(
        all(isinstance(item, Notification) for item in first),
        "pending() yalnızca Notification döndürmeli.",
    )
    ids = [item.id for item in first]
    _require(len(set(ids)) == len(ids), "pending() aynı id'yi iki kez döndürmemeli.")

    again = [item.id for item in await source.pending(limit)]
    _require(again == ids, "pending() yan etkisiz olmalı: ikinci çağrı aynı kayıtları dönmeli.")

    _require(len(await source.pending(1)) <= 1, "pending() limit değerini aşmamalı.")

    await source.mark_notified([])
    await source.mark_notified([ids[0]])
    after = [item.id for item in await source.pending(limit)]
    _require(ids[0] not in after, "işaretlenen bildirim pending()'den çıkmalı.")
    _require(
        all(item_id in after for item_id in ids[1:]),
        "işaretlenmeyen bildirimler pending()'de kalmalı.",
    )
