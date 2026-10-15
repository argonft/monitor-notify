"""Bildirim kuyruğu işleyicisi (outbox pattern).

Retailer bildirimleri kendi veritabanında tutar; gönderim buradan, ayrı bir
döngüde yapılır. Telegram çökse ya da konteyner yeniden başlasa bile
bildirilmemiş kayıt kuyrukta kalır ve sonra gönderilir.

Bir bildirim ancak **gerçekten işlendiyse** işaretlenir:
- Kural eşleşmediği için elenen işaretlenir (kuyrukta birikmez).
- Gönderilmesi gereken ama gönderimi başarısız olan işaretlenmez.
"""
from __future__ import annotations

import logging
from typing import Protocol, Sequence

from .delivery.message import OutgoingMessage
from .formatting.messages import format_digest, format_urgent
from .model import Notification
from .ports import EventSource
from .profile import RetailerProfile
from .rules.matcher import ProductContext, Rule, matches

logger = logging.getLogger(__name__)


class StorePort(Protocol):
    async def list_rules(self, *, only_active: bool = True) -> tuple[Rule, ...]: ...
    async def list_notify_targets(self) -> tuple[int, ...]: ...
    async def list_admin_chats(self) -> tuple[int, ...]: ...


class NotifierPort(Protocol):
    async def send(self, chat_id: int, message: OutgoingMessage | str) -> bool: ...


def delivery_alert(chat_id: int) -> str:
    """Bot kanala yönetici yapılmadıysa gönderim sessizce başarısız olur.

    Bu mesaj, kuyruk sessizce şişmesin diye admin sohbetine gider.
    """
    return (
        f"⚠️ Bildirimler şu hedefe gönderilemiyor: `{chat_id}`\n\n"
        "Kontrol et:\n"
        "• Bot kanala *yönetici* olarak eklendi mi?\n"
        "• 'Mesaj Gönder' yetkisi verildi mi?\n"
        "• Kanal id'si doğru mu? (/targets ile bak)\n\n"
        "Bildirimler kaybolmadı; başka bir hedefe gitmediyse kuyrukta bekliyor "
        "ve düzelince gönderilecek."
    )


class OutboxDispatcher:
    def __init__(
        self,
        *,
        source: EventSource,
        store: StorePort,
        notifier: NotifierPort,
        profile: RetailerProfile,
        max_per_cycle: int = 40,
        batch_size: int = 200,
        delivery_alert_threshold: int = 5,
    ) -> None:
        self._source = source
        self._store = store
        self._notifier = notifier
        self._profile = profile
        self._max_per_cycle = max(1, max_per_cycle)
        self._batch_size = batch_size
        self._delivery_alert_threshold = max(1, delivery_alert_threshold)
        # Hedef bazında ardışık arıza sayacı. Çalışan bir hedef, bozuk olanı
        # gizlememeli; bu yüzden "en az biri gitti" yetmiyor.
        self._target_failures: dict[int, int] = {}
        self._alerted_targets: set[int] = set()
        self._cycle_attempted: set[int] = set()
        self._cycle_failed: set[int] = set()

    async def run_once(self) -> int:
        """Kuyruğun bir partisini işler, işaretlenen bildirim sayısını döner."""
        queue = list(await self._source.pending(self._batch_size))
        if not queue:
            return 0

        rules = await self._store.list_rules()
        targets = await self._store.list_notify_targets()

        allowed, processed = self._split_by_rules(queue, rules)
        self._cycle_attempted = set()
        self._cycle_failed = set()

        if not targets:
            # Hedef tanımsız: teslimat arızası değil, yapılandırma eksikliği.
            # Bildirimler kuyrukta birikmesin diye işlenmiş sayılır.
            processed.extend(item.id for item in allowed)
        else:
            urgent = [item for item in allowed if item.kind in self._profile.urgent_kinds]
            digest = [item for item in allowed if item.kind not in self._profile.urgent_kinds]
            processed.extend(await self._send_urgent(urgent, targets))
            processed.extend(await self._send_digest(digest, targets))
            await self._track_delivery()

        await self._mark(processed)
        return len(processed)

    async def _mark(self, ids: list[int]) -> None:
        if not ids:
            return
        try:
            await self._source.mark_notified(ids)
        except Exception:
            # En az bir kez teslimat: kayıp, tekrardan kötüdür.
            logger.error(
                "%d bildirim işlendi ama işaretlenemedi; sonraki turda yeniden gönderilecek.",
                len(ids),
            )
            raise

    async def _track_delivery(self) -> None:
        """Hedef bazında arızayı sayar, eşiği aşanı admin'e bir kez bildirir."""
        broken: list[int] = []
        for chat_id in self._cycle_attempted:
            if chat_id in self._cycle_failed:
                self._target_failures[chat_id] = self._target_failures.get(chat_id, 0) + 1
                if (
                    self._target_failures[chat_id] >= self._delivery_alert_threshold
                    and chat_id not in self._alerted_targets
                ):
                    broken.append(chat_id)
                    self._alerted_targets.add(chat_id)
            else:
                self._target_failures.pop(chat_id, None)
                self._alerted_targets.discard(chat_id)

        if not broken:
            return

        admins = await self._store.list_admin_chats()
        for chat_id in sorted(broken):
            logger.error(
                "Hedef %s %d turdur bildirim alamıyor; admin sohbetine teşhis gönderiliyor.",
                chat_id,
                self._target_failures[chat_id],
            )
            for admin_id in admins:
                await self._notifier.send(admin_id, delivery_alert(chat_id))

    # --- iç adımlar -------------------------------------------------------

    def _split_by_rules(
        self, queue: Sequence[Notification], rules: tuple[Rule, ...]
    ) -> tuple[list[Notification], list[int]]:
        """Kurallara göre gönderilecekleri ve elenecekleri ayırır."""
        allowed: list[Notification] = []
        suppressed: list[int] = []
        for item in queue:
            decision = matches(
                item.kind,
                ProductContext.of(item),
                rules,
                allow_without_rules=self._profile.notify_without_rules,
            )
            if decision.allowed:
                allowed.append(item)
            else:
                suppressed.append(item.id)
        return allowed, suppressed

    async def _send_urgent(
        self, items: Sequence[Notification], targets: tuple[int, ...]
    ) -> list[int]:
        """Acil bildirimleri tek tek gönderir. Üst sınırı aşanlar özete devredilir."""
        sent_ids: list[int] = []
        for item in items[: self._max_per_cycle]:
            if await self._broadcast(format_urgent(item, self._profile), targets):
                sent_ids.append(item.id)

        overflow = list(items[self._max_per_cycle :])
        if overflow:
            sent_ids.extend(await self._send_digest(overflow, targets))
        return sent_ids

    async def _send_digest(
        self, items: Sequence[Notification], targets: tuple[int, ...]
    ) -> list[int]:
        """Acil olmayanları tek özet mesajda toplar."""
        message = format_digest(items, max_items=self._max_per_cycle)
        if message is None:
            return []
        if await self._broadcast(message, targets):
            return [item.id for item in items]
        return []

    async def _broadcast(self, message: OutgoingMessage, targets: tuple[int, ...]) -> bool:
        """Tüm hedeflere gönderir; en az biri başarılıysa işlenmiş sayılır.

        Aksi halde çalışan hedefe aynı mesaj her turda yeniden giderdi. Bozuk
        hedefler ayrıca sayılır ve eşiği aşınca admin'e bildirilir.
        """
        delivered = False
        for chat_id in targets:
            self._cycle_attempted.add(chat_id)
            if await self._notifier.send(chat_id, message):
                delivered = True
            else:
                self._cycle_failed.add(chat_id)
        if not delivered:
            logger.warning("Mesaj hiçbir hedefe gönderilemedi, kuyrukta kalıyor.")
        return delivered
