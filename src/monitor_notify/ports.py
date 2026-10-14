"""Retailer'ın kütüphaneye bildirim verdiği arayüz."""
from __future__ import annotations

from typing import Protocol, Sequence

from .model import Notification


class EventSource(Protocol):
    async def pending(self, limit: int) -> Sequence[Notification]:
        """En eski bildirimden başlayarak en fazla ``limit`` kayıt.

        Yan etkisizdir: işaretlenmeyen kayıt sonraki çağrıda yeniden döner.
        """
        ...

    async def mark_notified(self, ids: Sequence[int]) -> None:
        """Verilen bildirimleri işlenmiş sayar; boş liste geçerlidir."""
        ...
