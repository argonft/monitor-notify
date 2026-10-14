"""Komut servisini python-telegram-bot uygulamasına bağlar."""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Sequence

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .commands import CommandService
from .extra import ExtraCommand, run_safely

logger = logging.getLogger(__name__)

Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]
Action = Callable[[str, int | None], Awaitable[str]]


def build_application(
    token: str,
    service: CommandService,
    *,
    extra_commands: Sequence[ExtraCommand],
    allowed_chat_ids: Callable[[], Awaitable[tuple[int, ...]]],
    proxy_url: str | None = None,
) -> Application:
    """Komut işleyicileri bağlanmış bir PTB uygulaması kurar."""
    builder = Application.builder().token(token)
    if proxy_url:
        builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)
    application = builder.build()

    async def guard(update: Update) -> bool:
        """Yalnızca yetkili sohbetler komut çalıştırabilir."""
        chat = update.effective_chat
        if chat is None:
            return False
        if chat.id in await allowed_chat_ids():
            return True
        logger.warning("Yetkisiz komut denemesi: chat %s", chat.id)
        await update.effective_message.reply_text("Bu bot bu sohbete yetkili değil.")
        return False

    def bind(name: str, action: Action) -> Handler:
        async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not await guard(update):
                return
            args = " ".join(context.args or ())
            user = update.effective_user
            user_id = user.id if user else None
            reply = await run_safely(name, lambda: action(args, user_id))
            await update.effective_message.reply_text(reply, disable_web_page_preview=True)

        return handler

    async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Yetki gerektirmez: kurulum sırasında id'yi öğrenebilmek gerekir."""
        chat = update.effective_chat
        if chat is None:
            return
        await update.effective_message.reply_text(
            service.describe_chat(chat.id, title=chat.title)
        )

    async def forwarded(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Kanaldan forward edilen mesajdan kanal id'sini çıkarır."""
        if not await guard(update):
            return
        origin_chat = _forward_origin_chat(update.effective_message)
        if origin_chat is None:
            return
        await update.effective_message.reply_text(
            service.describe_forwarded(origin_chat.id, title=origin_chat.title)
        )

    common: dict[str, Action] = {
        "watch": lambda args, user: service.watch(args, user_id=user),
        "mute": lambda args, user: service.mute(args, user_id=user),
        "rules": lambda args, user: service.rules(),
        "unwatch": lambda args, user: service.unwatch(args),
        "targets": lambda args, user: service.targets(),
        "addtarget": lambda args, user: service.add_target(args),
        "rmtarget": lambda args, user: service.remove_target(args),
        "help": lambda args, user: _static(service.help_text()),
        "start": lambda args, user: _static(service.help_text()),
    }
    for name, action in common.items():
        application.add_handler(CommandHandler(name, bind(name, action)))
    for extra in extra_commands:
        application.add_handler(
            CommandHandler(extra.name, bind(extra.name, lambda args, user, e=extra: e.handler(args)))
        )
    application.add_handler(CommandHandler("chatid", chatid))
    application.add_handler(MessageHandler(filters.FORWARDED & filters.ChatType.PRIVATE, forwarded))
    return application


def _forward_origin_chat(message) -> object | None:
    """Forward kaynağındaki kanalı döner.

    python-telegram-bot 20.8+ ``forward_origin`` kullanıyor; eski alan
    ``forward_from_chat`` hâlâ karşımıza çıkabiliyor. İkisi de desteklenir.
    """
    if message is None:
        return None
    origin = getattr(message, "forward_origin", None)
    chat = getattr(origin, "chat", None)
    if chat is not None:
        return chat
    return getattr(message, "forward_from_chat", None)


async def _static(text: str) -> str:
    return text
