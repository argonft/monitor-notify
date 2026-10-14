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


# --- takılan kuyruk uyarısı -------------------------------------------------


class AlwaysFailing:
    def __init__(self, failures: int) -> None:
        self.remaining = failures
        self.calls = 0

    async def run_once(self) -> int:
        self.calls += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise ValueError("'weird' is not a valid EventKind")
        return 0


def stop_after(count: int):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= count:
            raise asyncio.CancelledError

    return fake_sleep


async def test_ust_uste_hatada_admin_bir_kez_uyarilir():
    alerts: list[Exception] = []

    async def on_stuck(error: Exception) -> None:
        alerts.append(error)

    with pytest.raises(asyncio.CancelledError):
        await run_outbox_loop(
            AlwaysFailing(10), 2.0, sleep=stop_after(10), on_stuck=on_stuck, stuck_threshold=3
        )

    assert len(alerts) == 1
    assert isinstance(alerts[0], ValueError)


async def test_esik_altinda_uyari_gonderilmez():
    alerts: list[Exception] = []

    async def on_stuck(error: Exception) -> None:
        alerts.append(error)

    with pytest.raises(asyncio.CancelledError):
        await run_outbox_loop(
            AlwaysFailing(2), 2.0, sleep=stop_after(5), on_stuck=on_stuck, stuck_threshold=3
        )

    assert alerts == []


async def test_duzelme_sonrasi_yeni_takilma_tekrar_uyarir():
    alerts: list[Exception] = []

    class FlipFlop:
        def __init__(self) -> None:
            self.pattern = [True] * 3 + [False] + [True] * 3

        async def run_once(self) -> int:
            if self.pattern and self.pattern.pop(0):
                raise RuntimeError("db koptu")
            return 0

    async def on_stuck(error: Exception) -> None:
        alerts.append(error)

    with pytest.raises(asyncio.CancelledError):
        await run_outbox_loop(FlipFlop(), 2.0, sleep=stop_after(7), on_stuck=on_stuck, stuck_threshold=3)

    assert len(alerts) == 2


async def test_uyari_gonderimi_hatasi_donguyu_durdurmaz():
    async def broken_alert(error: Exception) -> None:
        raise RuntimeError("telegram yok")

    dispatcher = AlwaysFailing(10)
    with pytest.raises(asyncio.CancelledError):
        await run_outbox_loop(dispatcher, 2.0, sleep=stop_after(5), on_stuck=broken_alert, stuck_threshold=1)

    assert dispatcher.calls == 5


def test_takilma_uyarisi_ic_ayrinti_sizdirmaz():
    from monitor_notify.app import stuck_alert

    text = stuck_alert(ValueError("password=hunter2"), failures=30)

    assert "ValueError" in text
    assert "hunter2" not in text
    assert "30" in text
