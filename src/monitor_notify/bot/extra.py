"""Retailer'ın ortak komutlara eklediği kendi komutları.

Ek komut Telegram'ı tanımaz: argüman metnini alır, yanıt metnini döner.
Ortak komutlarla aynı yetki kontrolünden geçer ve ``/help``'te listelenir.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable

logger = logging.getLogger(__name__)

#: Telegram komut adı kuralı: küçük harf, rakam, alt çizgi; en fazla 32 karakter.
_NAME = re.compile(r"^[a-z0-9_]{1,32}$")

BUILTIN_COMMANDS: frozenset[str] = frozenset(
    {"watch", "mute", "rules", "unwatch", "targets", "addtarget", "rmtarget", "chatid", "help", "start"}
)

FAILURE_REPLY = "⚠️ Komut çalıştırılamadı, loglara bak."


@dataclass(frozen=True, slots=True)
class ExtraCommand:
    #: Eğik çizgisiz komut adı, örn. ``"find"``.
    name: str
    #: ``/help`` çıktısında görünen satır.
    help: str
    handler: Callable[[str], Awaitable[str]]

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise ValueError(
                f"Geçersiz komut adı: {self.name!r} (küçük harf, rakam, _; en fazla 32 karakter)"
            )
        if not self.help.strip():
            raise ValueError(f"/{self.name} için yardım metni boş olamaz.")


def validate_extra_commands(extras: Iterable[ExtraCommand]) -> tuple[ExtraCommand, ...]:
    """Ad çakışmalarını açılışta yakalar; sırayı korur."""
    commands = tuple(extras)
    seen: set[str] = set()
    for command in commands:
        if command.name in BUILTIN_COMMANDS:
            raise ValueError(f"/{command.name} ortak bir komut; ek komut olarak tanımlanamaz.")
        if command.name in seen:
            raise ValueError(f"/{command.name} birden fazla kez tanımlandı.")
        seen.add(command.name)
    return commands


async def run_safely(name: str, action: Callable[[], Awaitable[str]]) -> str:
    """Komutu çalıştırır; hata ayrıntısı loga gider, kullanıcıya gitmez."""
    try:
        return await action()
    except Exception:
        logger.exception("/%s komutu başarısız.", name)
        return FAILURE_REPLY
