"""Bildirim katmanının çalışma ayarları; açılışta doğrulanır."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NotifyConfig:
    bot_token: str
    #: Komut yetkili sohbet; kanal yoksa bildirimleri de alır.
    admin_chat_id: int
    #: Duyuru kanalı; tanımlıysa bildirimler yalnızca oraya gider.
    channel_id: int | None = None
    proxy_url: str | None = None
    max_per_cycle: int = 40
    poll_interval_seconds: float = 2.0

    def __post_init__(self) -> None:
        if not self.bot_token.strip():
            raise ValueError("bot_token boş olamaz.")
        if not _is_int(self.admin_chat_id):
            raise ValueError("admin_chat_id tam sayı olmalı.")
        if self.channel_id is not None and not _is_int(self.channel_id):
            raise ValueError("channel_id tam sayı olmalı.")
        if self.channel_id == self.admin_chat_id:
            raise ValueError("channel_id admin_chat_id ile aynı olamaz.")
        if self.max_per_cycle < 1:
            raise ValueError("max_per_cycle en az 1 olmalı.")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds sıfırdan büyük olmalı.")

    def __repr__(self) -> str:
        return (
            f"NotifyConfig(bot_token='***', admin_chat_id={self.admin_chat_id}, "
            f"channel_id={self.channel_id}, max_per_cycle={self.max_per_cycle})"
        )


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
