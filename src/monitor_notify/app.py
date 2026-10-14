"""Bildirim katmanını tek nesnede toplar: hedef kaydı, bot ve outbox döngüsü.

Retailer yalnızca bağlantıyı kurar::

    notify = NotifyApp(pool=pool, profile=PROFILE, source=source, config=config)
    async with notify.running():
        await scrape_loop(...)
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable, Protocol, Sequence

import asyncpg

from .bot.commands import CommandService
from .bot.extra import ExtraCommand, validate_extra_commands
from .bot.handlers import build_application
from .config import NotifyConfig
from .delivery.telegram import RateLimiter, TelegramNotifier
from .outbox import OutboxDispatcher
from .ports import EventSource
from .profile import RetailerProfile
from .store.notify_store import NotifyStore

logger = logging.getLogger(__name__)


class TargetStore(Protocol):
    async def ensure_target(
        self, chat_id, *, receives_notifications=True, can_manage=True, title=None
    ) -> None: ...


class Dispatcher(Protocol):
    async def run_once(self) -> int: ...


async def register_targets(store: TargetStore, config: NotifyConfig) -> None:
    """Yapılandırmadaki admin ve kanal hedeflerini yazar.

    Admin her zaman komut yetkisine sahiptir. Kanal tanımlıysa bildirimler
    yalnızca oraya gider; aksi halde admin sohbetine.
    """
    await store.ensure_target(
        config.admin_chat_id,
        receives_notifications=config.channel_id is None,
        can_manage=True,
    )
    if config.channel_id is not None:
        await store.ensure_target(
            config.channel_id, receives_notifications=True, can_manage=False
        )
        logger.info("Duyuru kanalı hedefi kayıtlı: %s", config.channel_id)


async def run_outbox_loop(
    dispatcher: Dispatcher,
    interval: float,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Kuyruğu sürekli boşaltır; tek bir turun hatası döngüyü durdurmaz."""
    while True:
        try:
            await dispatcher.run_once()
        except Exception:  # noqa: BLE001 - bildirim hatası servisi düşürmemeli
            logger.exception("Bildirim turu başarısız.")
        await sleep(interval)


class NotifyApp:
    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        profile: RetailerProfile,
        source: EventSource,
        config: NotifyConfig,
        extra_commands: Sequence[ExtraCommand] = (),
    ) -> None:
        self._profile = profile
        self._source = source
        self._config = config
        self._extras = validate_extra_commands(extra_commands)
        self.store = NotifyStore(pool)

    @asynccontextmanager
    async def running(self) -> AsyncIterator[NotifyApp]:
        """Bot polling'i ve outbox döngüsünü başlatır; çıkışta düzgünce durdurur.

        Çıkış anında yarıda kalan bildirim işaretlenmediği için sonraki
        açılışta yeniden gönderilir.
        """
        await register_targets(self.store, self._config)
        service = CommandService(self.store, profile=self._profile, extra_commands=self._extras)
        application = build_application(
            self._config.bot_token,
            service,
            extra_commands=self._extras,
            allowed_chat_ids=self.store.list_admin_chats,
            proxy_url=self._config.proxy_url,
        )
        dispatcher = OutboxDispatcher(
            source=self._source,
            store=self.store,
            notifier=TelegramNotifier(application.bot, limiter=RateLimiter()),
            profile=self._profile,
            max_per_cycle=self._config.max_per_cycle,
        )

        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        task = asyncio.create_task(
            run_outbox_loop(dispatcher, self._config.poll_interval_seconds), name="notifier"
        )
        try:
            yield self
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
