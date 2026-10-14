"""Retailer'ın eklediği komutlar: ad kuralları, çakışma ve hata yalıtımı."""
import logging

import pytest

from monitor_notify.bot.extra import (
    BUILTIN_COMMANDS,
    FAILURE_REPLY,
    ExtraCommand,
    run_safely,
    validate_extra_commands,
)


async def _reply(args: str) -> str:
    return f"ok {args}"


def extra(name: str = "find") -> ExtraCommand:
    return ExtraCommand(name=name, help=f"/{name} — açıklama", handler=_reply)


@pytest.mark.parametrize("name", ["/find", "Find", "find me", "", "f" * 33, "bul-uyor"])
def test_gecersiz_komut_adi_reddedilir(name):
    with pytest.raises(ValueError):
        extra(name)


def test_bos_yardim_metni_reddedilir():
    with pytest.raises(ValueError):
        ExtraCommand(name="find", help="  ", handler=_reply)


@pytest.mark.parametrize("name", sorted(BUILTIN_COMMANDS))
def test_ortak_komutla_cakisan_ad_reddedilir(name):
    with pytest.raises(ValueError):
        validate_extra_commands([extra(name)])


def test_ayni_ad_iki_kez_reddedilir():
    with pytest.raises(ValueError):
        validate_extra_commands([extra("find"), extra("find")])


def test_gecerli_liste_sirasi_korunur():
    commands = validate_extra_commands([extra("status"), extra("find")])
    assert [command.name for command in commands] == ["status", "find"]


async def test_hata_veren_komut_genel_yanit_doner(caplog):
    async def broken() -> str:
        raise RuntimeError("db şifresi: hunter2")

    with caplog.at_level(logging.ERROR):
        reply = await run_safely("find", broken)

    assert reply == FAILURE_REPLY
    assert "hunter2" not in reply
    assert "/find" in caplog.text


async def test_basarili_komut_yanitini_aynen_doner():
    assert await run_safely("find", lambda: _reply("x")) == "ok x"


def test_uygulama_ek_komutlari_kaydeder():
    from telegram.ext import CommandHandler

    from monitor_notify.bot.commands import CommandService
    from monitor_notify.bot.handlers import build_application
    from monitor_notify.profile import RetailerProfile

    async def no_chats() -> tuple[int, ...]:
        return ()

    extras = (extra("find"),)
    service = CommandService(object(), profile=RetailerProfile(name="shop.example"), extra_commands=extras)
    application = build_application(
        "123456:TEST", service, extra_commands=extras, allowed_chat_ids=no_chats
    )

    names = {
        command
        for handler in application.handlers[0]
        if isinstance(handler, CommandHandler)
        for command in handler.commands
    }
    assert {"find", "watch", "chatid", "help"} <= names
