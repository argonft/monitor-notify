"""Gönderime hazır mesaj.

Metin, opsiyonel bir eylem butonu ve opsiyonel bir görsel taşır. Formatter bu nesneyi üretir,
Telegram katmanı butonu ``InlineKeyboardMarkup``a çevirir. Böylece formatter
Telegram API'sini hiç tanımaz ve saf kalır.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BUTTON_LABEL = "🛒 Ürüne git"


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    text: str
    button_url: str | None = None
    button_label: str = DEFAULT_BUTTON_LABEL
    photo_url: str | None = None

    @property
    def has_button(self) -> bool:
        return bool(self.button_url)
