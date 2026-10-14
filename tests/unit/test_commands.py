"""Ortak yönetim komutları: kural ekleme, listeleme, kapatma ve yardım."""
import pytest

from monitor_notify.bot.commands import CommandService
from monitor_notify.bot.extra import ExtraCommand
from monitor_notify.model import EventKind
from monitor_notify.profile import RetailerProfile
from monitor_notify.rules.matcher import Rule, RuleKind

PROFILE = RetailerProfile(name="shop.example")


class FakeRulesRepo:
    def __init__(self) -> None:
        self.rules: list[Rule] = []
        self.next_id = 1
        self.deactivated: list[int] = []

    async def add_rule(self, kind, pattern, *, event_types=None, created_by=None) -> int:
        rule_id = self.next_id
        self.next_id += 1
        self.rules.append(Rule(id=rule_id, kind=kind, pattern=pattern, event_types=event_types))
        return rule_id

    async def list_rules(self, *, only_active: bool = True):
        return tuple(self.rules)

    async def deactivate_rule(self, rule_id: int) -> bool:
        if any(r.id == rule_id for r in self.rules):
            self.deactivated.append(rule_id)
            self.rules = [r for r in self.rules if r.id != rule_id]
            return True
        return False


@pytest.fixture
def repo() -> FakeRulesRepo:
    return FakeRulesRepo()


@pytest.fixture
def service(repo: FakeRulesRepo) -> CommandService:
    return CommandService(repo, profile=PROFILE)


# --- /watch ---------------------------------------------------------------


async def test_watch_marka_kurali_ekler(service, repo):
    reply = await service.watch("marka Nike", user_id=1)

    assert repo.rules[0].kind is RuleKind.BRAND
    assert repo.rules[0].pattern == "Nike"
    assert "Nike" in reply


async def test_watch_kelime_kurali_ekler(service, repo):
    await service.watch("kelime air max", user_id=1)
    assert repo.rules[0].kind is RuleKind.KEYWORD
    assert repo.rules[0].pattern == "air max"


async def test_watch_kategori_kurali_ekler(service, repo):
    await service.watch("kategori Sneaker", user_id=1)
    assert repo.rules[0].kind is RuleKind.CATEGORY


async def test_watch_event_tipi_ile_sinirlandirilabilir(service, repo):
    await service.watch("marka Nike +restock", user_id=1)
    assert repo.rules[0].event_types == frozenset({EventKind.RESTOCK})


async def test_watch_birden_fazla_event_tipi_alir(service, repo):
    await service.watch("marka Nike +restock +price_drop", user_id=1)
    assert repo.rules[0].event_types == frozenset({EventKind.RESTOCK, EventKind.PRICE_DROP})


async def test_watch_gecersiz_tur_kullanim_mesaji_verir(service, repo):
    reply = await service.watch("renk kırmızı", user_id=1)
    assert repo.rules == []
    assert "marka" in reply.lower()


async def test_watch_bos_arguman_kullanim_mesaji_verir(service, repo):
    reply = await service.watch("", user_id=1)
    assert repo.rules == []
    assert "kullanım" in reply.lower()


async def test_watch_desen_bossa_reddedilir(service, repo):
    reply = await service.watch("marka   ", user_id=1)
    assert repo.rules == []
    assert "kullanım" in reply.lower()


async def test_watch_gecersiz_event_tipi_reddedilir(service, repo):
    reply = await service.watch("marka Nike +zıpzıp", user_id=1)
    assert repo.rules == []
    assert "zıpzıp" in reply


async def test_watch_cok_kelimeli_desen_bozulmadan_kaydedilir(service, repo):
    """Önek olmadan hiçbir sözcük event sanılmamalı."""
    await service.watch("kelime air max plus", user_id=1)
    assert repo.rules[0].pattern == "air max plus"
    assert repo.rules[0].event_types is None


async def test_watch_event_bayragi_desenin_basinda_da_olabilir(service, repo):
    await service.watch("marka +restock Nike Air", user_id=1)
    assert repo.rules[0].pattern == "Nike Air"
    assert repo.rules[0].event_types == frozenset({EventKind.RESTOCK})


# --- /mute ----------------------------------------------------------------


async def test_mute_negatif_kural_ekler(service, repo):
    reply = await service.mute("çorap", user_id=1)

    assert repo.rules[0].kind is RuleKind.NEGATIVE_KEYWORD
    assert repo.rules[0].pattern == "çorap"
    assert "çorap" in reply


async def test_mute_bos_arguman_reddedilir(service, repo):
    reply = await service.mute("  ", user_id=1)
    assert repo.rules == []
    assert "kullanım" in reply.lower()


# --- /rules, /unwatch -----------------------------------------------------


async def test_rules_bos_listede_aciklama_verir(service):
    reply = await service.rules()
    assert "kural" in reply.lower()


async def test_rules_kurallari_id_ile_listeler(service, repo):
    await service.watch("marka Nike", user_id=1)
    await service.mute("çorap", user_id=1)

    reply = await service.rules()
    assert "#1" in reply and "#2" in reply
    assert "Nike" in reply and "çorap" in reply


async def test_unwatch_kurali_pasiflestirir(service, repo):
    await service.watch("marka Nike", user_id=1)
    reply = await service.unwatch("1")

    assert repo.deactivated == [1]
    assert "1" in reply


async def test_unwatch_olmayan_id_bildirir(service):
    reply = await service.unwatch("99")
    assert "bulunamadı" in reply.lower()


async def test_unwatch_sayisal_olmayan_id_reddedilir(service):
    reply = await service.unwatch("abc")
    assert "kullanım" in reply.lower()


# --- /help ----------------------------------------------------------------


async def _noop(args: str) -> str:
    return ""


def test_yardim_basligi_profilden_gelir(service):
    assert service.help_text().startswith("shop.example stok takip botu")


def test_yardim_ek_komutlari_listeler(repo):
    extras = (ExtraCommand("find", "/find <kelime> — anlık stok durumunu gösterir", _noop),)
    text = CommandService(repo, profile=PROFILE, extra_commands=extras).help_text()

    assert "/find <kelime> — anlık stok durumunu gösterir" in text
    assert text.index("/unwatch") < text.index("/find") < text.index("Duyuru kanalı")


def test_ek_komut_yoksa_yardim_yine_tam(service):
    text = service.help_text()
    for command in ("/watch", "/mute", "/rules", "/unwatch", "/targets", "/addtarget", "/rmtarget", "/chatid"):
        assert command in text
