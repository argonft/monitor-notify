"""Telegram gönderimi: hız sınırı, 429 davranışı ve hata dayanıklılığı."""
import pytest
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError

from monitor_notify.delivery.message import OutgoingMessage
from monitor_notify.delivery.telegram import RateLimiter, TelegramNotifier


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class FakeBot:
    def __init__(
        self,
        *,
        errors: list[Exception] | None = None,
        photo_errors: list[Exception] | None = None,
    ) -> None:
        self.sent: list[tuple[int, str]] = []
        self.markups: list[object] = []
        self.photos: list[tuple[int, str, str]] = []
        self.photo_markups: list[object] = []
        self.errors = errors or []
        self.photo_errors = photo_errors or []

    async def send_photo(self, *, chat_id: int, photo: str, caption: str, **kwargs) -> None:
        if self.photo_errors:
            raise self.photo_errors.pop(0)
        self.photos.append((chat_id, photo, caption))
        self.photo_markups.append(kwargs.get("reply_markup"))

    async def send_message(self, *, chat_id: int, text: str, **kwargs) -> None:
        if self.errors:
            raise self.errors.pop(0)
        self.sent.append((chat_id, text))
        self.markups.append(kwargs.get("reply_markup"))


# --- hız sınırı -----------------------------------------------------------


async def test_kapasite_dahilinde_beklemeden_gecer():
    clock = FakeClock()
    limiter = RateLimiter(rate_per_minute=60, capacity=3, clock=clock, sleep=clock.sleep)

    for _ in range(3):
        await limiter.acquire()

    assert clock.slept == []


async def test_kapasite_dolunca_beklenir():
    clock = FakeClock()
    limiter = RateLimiter(rate_per_minute=60, capacity=2, clock=clock, sleep=clock.sleep)

    for _ in range(3):
        await limiter.acquire()

    assert len(clock.slept) == 1
    assert clock.slept[0] == pytest.approx(1.0, abs=0.01)


async def test_zaman_gecince_jeton_dolar():
    clock = FakeClock()
    limiter = RateLimiter(rate_per_minute=60, capacity=2, clock=clock, sleep=clock.sleep)
    await limiter.acquire()
    await limiter.acquire()

    clock.now += 10
    await limiter.acquire()

    assert clock.slept == []


def test_gecersiz_hiz_reddedilir():
    with pytest.raises(ValueError):
        RateLimiter(rate_per_minute=0)


# --- gönderim -------------------------------------------------------------


async def test_mesaj_gonderilir():
    bot = FakeBot()
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter())

    assert await notifier.send(42, "merhaba") is True
    assert bot.sent == [(42, "merhaba")]


async def test_429_alininca_beklenip_yeniden_denenir():
    clock = FakeClock()
    bot = FakeBot(errors=[RetryAfter(3)])
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter(), sleep=clock.sleep)

    assert await notifier.send(42, "merhaba") is True
    assert clock.slept == [3.0]
    assert bot.sent == [(42, "merhaba")]


async def test_surekli_429_sonunda_false_doner():
    clock = FakeClock()
    bot = FakeBot(errors=[RetryAfter(1), RetryAfter(1), RetryAfter(1)])
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter(), sleep=clock.sleep, max_attempts=3)

    assert await notifier.send(42, "merhaba") is False


async def test_retry_after_timedelta_olarak_gelirse_de_calisir():
    """python-telegram-bot ileride bu alanı timedelta yapacak."""
    from datetime import timedelta

    clock = FakeClock()
    error = RetryAfter(3)
    object.__setattr__(error, "_retry_after", timedelta(seconds=3))
    bot = FakeBot(errors=[error])
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter(), sleep=clock.sleep)

    assert await notifier.send(42, "merhaba") is True
    assert clock.slept == [3.0]


async def test_telegram_hatasi_false_doner_ve_patlamaz():
    """Gönderim hatası tur döngüsünü çökertmemeli; event kuyrukta kalır."""
    bot = FakeBot(errors=[TelegramError("kanal kapalı")])
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter(), max_attempts=1)

    assert await notifier.send(42, "merhaba") is False


async def test_uzun_mesaj_telegram_sinirina_kirpilir():
    bot = FakeBot()
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter())

    await notifier.send(42, "x" * 5000)

    assert len(bot.sent[0][1]) <= 4096


async def test_bos_mesaj_gonderilmez():
    bot = FakeBot()
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter())

    assert await notifier.send(42, "   ") is False
    assert bot.sent == []


def _no_wait_limiter() -> RateLimiter:
    clock = FakeClock()
    return RateLimiter(rate_per_minute=6000, capacity=1000, clock=clock, sleep=clock.sleep)


# --- buton --------------------------------------------------------------


async def test_butonlu_mesaj_inline_klavye_ile_gonderilir():
    bot = FakeBot()
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter())

    await notifier.send(42, OutgoingMessage("merhaba", button_url="https://shop.example/x"))

    markup = bot.markups[0]
    assert markup is not None
    button = markup.inline_keyboard[0][0]
    assert button.url == "https://shop.example/x"
    assert button.text


async def test_butonsuz_mesajda_klavye_gonderilmez():
    bot = FakeBot()
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter())

    await notifier.send(42, OutgoingMessage("merhaba"))

    assert bot.markups[0] is None


async def test_duz_metin_de_kabul_edilir():
    """Teşhis mesajları gibi basit metinler için sarmalamaya gerek olmasın."""
    bot = FakeBot()
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter())

    assert await notifier.send(42, "teşhis") is True
    assert bot.sent == [(42, "teşhis")]


async def test_buton_etiketi_ozellestirilebilir():
    bot = FakeBot()
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter())

    await notifier.send(42, OutgoingMessage("x", button_url="https://a.b", button_label="Bak"))

    assert bot.markups[0].inline_keyboard[0][0].text == "Bak"


async def test_bos_metinli_mesaj_gonderilmez():
    bot = FakeBot()
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter())

    assert await notifier.send(42, OutgoingMessage("   ")) is False
    assert bot.sent == []


# --- görsel ---------------------------------------------------------------

PHOTO = "https://cdn.example/images/m/i/image_1080.jpeg"


async def test_gorselli_mesaj_foto_ve_altyazi_olarak_gider():
    bot = FakeBot()
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter())

    sent = await notifier.send(
        42, OutgoingMessage("restock", button_url="https://shop.example/x", photo_url=PHOTO)
    )

    assert sent is True
    assert bot.photos == [(42, PHOTO, "restock")]
    assert bot.photo_markups[0].inline_keyboard[0][0].url == "https://shop.example/x"
    assert bot.sent == []


async def test_gorsel_reddedilirse_duz_metne_duser():
    """CDN erişilemezse veya Telegram görseli kabul etmezse bildirim kaybolmamalı."""
    bot = FakeBot(photo_errors=[BadRequest("Wrong file identifier/http url specified")])
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter())

    sent = await notifier.send(
        42, OutgoingMessage("restock", button_url="https://shop.example/x", photo_url=PHOTO)
    )

    assert sent is True
    assert bot.photos == []
    assert bot.sent == [(42, "restock")]
    assert bot.markups[0] is not None


async def test_altyazi_siniri_asilirsa_duz_metin_gider():
    bot = FakeBot()
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter())

    await notifier.send(42, OutgoingMessage("x" * 1500, photo_url=PHOTO))

    assert bot.photos == []
    assert len(bot.sent) == 1


async def test_gorselde_429_alininca_gorselle_yeniden_denenir():
    clock = FakeClock()
    bot = FakeBot(photo_errors=[RetryAfter(2)])
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter(), sleep=clock.sleep)

    assert await notifier.send(42, OutgoingMessage("restock", photo_url=PHOTO)) is True
    assert clock.slept == [2.0]
    assert bot.photos == [(42, PHOTO, "restock")]


async def test_yetki_hatasinda_duz_metin_denenmez():
    """Bot kanalda yetkisizse metin de gitmez; boşuna ikinci istek atılmamalı."""
    bot = FakeBot(photo_errors=[Forbidden("bot is not a member")])
    notifier = TelegramNotifier(bot, limiter=_no_wait_limiter())

    assert await notifier.send(42, OutgoingMessage("restock", photo_url=PHOTO)) is False
    assert bot.sent == []
