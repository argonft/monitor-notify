"""Retailer'ların EventSource'u için hazır sözleşme testi."""
import pytest

from monitor_notify.model import EventKind, Notification
from monitor_notify.testing import check_event_source_contract


def note(event_id: int) -> Notification:
    return Notification(
        id=event_id, kind=EventKind.RESTOCK, product_name="Ürün", brand=None,
        categories=(), variant_label="", product_url="https://shop.example/x",
    )


class GoodSource:
    def __init__(self, ids: list[int]) -> None:
        self._items = [note(i) for i in ids]

    async def pending(self, limit: int):
        return self._items[:limit]

    async def mark_notified(self, ids) -> None:
        self._items = [item for item in self._items if item.id not in set(ids)]


async def test_dogru_kaynak_gecer():
    await check_event_source_contract(GoodSource([1, 2, 3]))


async def test_en_az_iki_bildirim_gerekir():
    with pytest.raises(AssertionError, match="en az iki"):
        await check_event_source_contract(GoodSource([1]))


async def test_isaretlemeyi_yok_sayan_kaynak_yakalanir():
    class Sticky(GoodSource):
        async def mark_notified(self, ids) -> None:
            return None

    with pytest.raises(AssertionError, match="işaretlenen"):
        await check_event_source_contract(Sticky([1, 2]))


async def test_limiti_asan_kaynak_yakalanir():
    class Greedy(GoodSource):
        async def pending(self, limit: int):
            return self._items

    with pytest.raises(AssertionError, match="limit"):
        await check_event_source_contract(Greedy([1, 2, 3]))


async def test_yan_etkili_pending_yakalanir():
    class Consuming(GoodSource):
        async def pending(self, limit: int):
            items, self._items = self._items[:limit], self._items[limit:]
            return items

    with pytest.raises(AssertionError, match="yan etkisiz"):
        await check_event_source_contract(Consuming([1, 2, 3]))


async def test_notification_olmayan_kayit_yakalanir():
    class Raw(GoodSource):
        async def pending(self, limit: int):
            return [{"id": 1}, {"id": 2}]

    with pytest.raises(AssertionError, match="Notification"):
        await check_event_source_contract(Raw([1, 2]))
