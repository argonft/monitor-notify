"""Telegram gönderim katmanı: hız sınırı ve hata dayanıklılığı.

Gönderim hataları istisna olarak dışarı taşmaz; ``send`` başarısızlıkta
``False`` döner ve çağıran (outbox) event'i işaretlemeyerek sonraki turda
yeniden dener.

Görselli mesajlar fotoğraf + altyazı olarak gider. Görsel süstür: Telegram
görseli reddederse (CDN erişilemez, biçim kabul edilmez) mesaj düz metin
olarak yeniden gönderilir; bildirim görsel yüzünden kaybolmaz.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any, Awaitable, Callable, Protocol

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, RetryAfter, TelegramError

from .message import OutgoingMessage

logger = logging.getLogger(__name__)

#: Telegram tek mesajda en fazla bu kadar karakter kabul eder.
MAX_MESSAGE_LENGTH = 4096
#: Fotoğraf altyazısı sınırı; aşan mesaj görselsiz gönderilir.
MAX_CAPTION_LENGTH = 1024
_TRUNCATION_SUFFIX = "\n… (kısaltıldı)"


class BotPort(Protocol):
    async def send_message(self, *, chat_id: int, text: str, **kwargs: object) -> object: ...

    async def send_photo(
        self, *, chat_id: int, photo: str, caption: str, **kwargs: object
    ) -> object: ...


class RateLimiter:
    """Token bucket.

    Telegram saniyede ~30 mesaja izin verir; varsayılanımız çok daha sakindir,
    çünkü amacımız hız değil, ban yememek.
    """

    def __init__(
        self,
        *,
        rate_per_minute: float = 20.0,
        capacity: int = 5,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute sıfırdan büyük olmalı.")
        self._rate_per_second = rate_per_minute / 60.0
        self._capacity = max(1, capacity)
        self._tokens = float(self._capacity)
        self._clock = clock
        self._sleep = sleep
        self._updated_at = clock()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Bir jeton alır; yoksa dolana kadar bekler."""
        async with self._lock:
            self._refill()
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._rate_per_second
                await self._sleep(wait)
                self._refill()
            self._tokens -= 1.0

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._updated_at)
        self._updated_at = now
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate_per_second)


class TelegramNotifier:
    def __init__(
        self,
        bot: BotPort,
        *,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_attempts: int = 3,
    ) -> None:
        self._bot = bot
        self._limiter = limiter or RateLimiter()
        self._sleep = sleep
        self._max_attempts = max(1, max_attempts)

    async def send(self, chat_id: int, message: OutgoingMessage | str) -> bool:
        """Mesajı gönderir. Başarısızlıkta ``False`` döner, istisna fırlatmaz.

        Düz metin de kabul edilir; teşhis mesajları için sarmalamaya gerek yok.
        """
        outgoing = message if isinstance(message, OutgoingMessage) else OutgoingMessage(message)
        payload = _truncate(outgoing.text)
        if not payload:
            return False
        markup = _keyboard(outgoing)

        if outgoing.photo_url and len(payload) <= MAX_CAPTION_LENGTH:
            try:
                return await self._deliver(
                    lambda: self._bot.send_photo(
                        chat_id=chat_id,
                        photo=outgoing.photo_url,
                        caption=payload,
                        reply_markup=markup,
                    ),
                    chat_id,
                    fallback_on=(BadRequest,),
                )
            except BadRequest as exc:
                logger.info("Görsel gönderilemedi, düz metne geçiliyor: %s", exc)

        return await self._deliver(
            lambda: self._bot.send_message(
                chat_id=chat_id,
                text=payload,
                disable_web_page_preview=True,
                reply_markup=markup,
            ),
            chat_id,
        )

    async def _deliver(
        self,
        call: Callable[[], Awaitable[Any]],
        chat_id: int,
        *,
        fallback_on: tuple[type[TelegramError], ...] = (),
    ) -> bool:
        """Hız sınırına uyarak çağrıyı dener; 429'da bekleyip yineler.

        ``fallback_on`` içindeki hatalar yutulmaz, çağıranın başka bir yolla
        denemesi için dışarı aktarılır.
        """
        for attempt in range(1, self._max_attempts + 1):
            await self._limiter.acquire()
            try:
                await call()
                return True
            except fallback_on:
                raise
            except RetryAfter as exc:
                delay = _retry_seconds(exc)
                logger.warning(
                    "Telegram hız sınırı, %.1fs bekleniyor (deneme %d/%d).",
                    delay, attempt, self._max_attempts,
                )
                await self._sleep(delay)
            except TelegramError as exc:
                logger.warning("Telegram gönderimi başarısız (chat %s): %s", chat_id, exc)
                return False
        return False


def _keyboard(message: OutgoingMessage) -> InlineKeyboardMarkup | None:
    """Mesajın butonunu Telegram inline klavyesine çevirir."""
    if not message.has_button:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(message.button_label, url=message.button_url)]]
    )


def _retry_seconds(error: RetryAfter) -> float:
    """``retry_after`` sürümlere göre saniye ya da timedelta olabilir; ikisini de kabul et."""
    raw = getattr(error, "retry_after", 1.0)
    if isinstance(raw, timedelta):
        return raw.total_seconds()
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 1.0


def _truncate(text: str) -> str:
    stripped = (text or "").strip()
    if len(stripped) <= MAX_MESSAGE_LENGTH:
        return stripped
    keep = MAX_MESSAGE_LENGTH - len(_TRUNCATION_SUFFIX)
    return stripped[:keep] + _TRUNCATION_SUFFIX
