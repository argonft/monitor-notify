"""Hedef kaydı ve outbox döngüsünün dayanıklılığı."""
import asyncio

import pytest

from monitor_notify.app import NotifyApp, register_targets, run_outbox_loop
from monitor_notify.bot.extra import ExtraCommand
from monitor_notify.config import NotifyConfig
from monitor_notify.profile import RetailerProfile


class FakeStore:
    def __init__(self) -> None:
        self.calls: list[tuple[int, bool, bool]] = []

    async def ensure_target(self, chat_id, *, receives_notifications=True, can_manage=True, title=None):
        self.calls.append((chat_id, receives_notifications, can_manage))


async def test_kanal_yoksa_admin_bildirim_alir():
    store = FakeStore()
    await register_targets(store, NotifyConfig(bot_token="t:t", admin_chat_id=1))
    assert store.calls == [(1, True, True)]


async def test_kanal_varsa_bildirimler_kanala_gider():
    store = FakeStore()
    await register_targets(store, NotifyConfig(bot_token="t:t", admin_chat_id=1, channel_id=-100))
    assert store.calls == [(1, False, True), (-100, True, False)]


async def test_dongu_hatada_durmaz():
    class FlakyDispatcher:
        def __init__(self) -> None:
            self.calls = 0

        async def run_once(self) -> int:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("db koptu")
            return 0

    dispatcher = FlakyDispatcher()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= 3:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_outbox_loop(dispatcher, 2.0, sleep=fake_sleep)

    assert dispatcher.calls == 3
    assert sleeps == [2.0, 2.0, 2.0]


def test_ek_komut_cakismasi_kurulumda_yakalanir():
    async def reply(args: str) -> str:
        return ""

    with pytest.raises(ValueError):
        NotifyApp(
            pool=object(),
            profile=RetailerProfile(name="shop.example"),
            source=object(),
            config=NotifyConfig(bot_token="t:t", admin_chat_id=1),
            extra_commands=[ExtraCommand("rules", "/rules — x", reply)],
        )
