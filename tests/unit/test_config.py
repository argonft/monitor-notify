"""Açılışta yapılandırma doğrulaması."""
import pytest

from monitor_notify.config import NotifyConfig


def config(**overrides) -> NotifyConfig:
    fields = {"bot_token": "123456:TEST", "admin_chat_id": 42}
    fields.update(overrides)
    return NotifyConfig(**fields)


def test_varsayilanlar():
    value = config()
    assert value.channel_id is None
    assert value.max_per_cycle == 40
    assert value.poll_interval_seconds == 2.0


def test_bos_token_reddedilir():
    with pytest.raises(ValueError):
        config(bot_token="  ")


@pytest.mark.parametrize("field", ["admin_chat_id", "channel_id"])
def test_sayi_olmayan_chat_id_reddedilir(field):
    with pytest.raises(ValueError):
        config(**{field: "42"})


def test_kanal_admin_ile_ayni_olamaz():
    """Aynı id'de kanal kaydı admin'in komut yetkisini siler."""
    with pytest.raises(ValueError):
        config(channel_id=42)


@pytest.mark.parametrize(("field", "value"), [("max_per_cycle", 0), ("poll_interval_seconds", 0)])
def test_pozitif_olmayan_sinirlar_reddedilir(field, value):
    with pytest.raises(ValueError):
        config(**{field: value})


def test_repr_token_sizdirmaz():
    assert "123456:TEST" not in repr(config())
