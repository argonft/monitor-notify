"""Ortak Telegram komutlarının iş mantığı.

Bu katman Telegram'ı tanımaz: komut argümanını alır, metin döndürür. PTB
bağlantısı ``bot/handlers.py`` içindedir.
"""
from __future__ import annotations

from typing import Protocol, Sequence

from ..model import EventKind
from ..profile import RetailerProfile
from ..rules.matcher import Rule, RuleKind
from ..store.notify_store import NotifyTarget
from .extra import ExtraCommand

_KIND_BY_WORD: dict[str, RuleKind] = {
    "marka": RuleKind.BRAND,
    "kelime": RuleKind.KEYWORD,
    "kategori": RuleKind.CATEGORY,
}

_KIND_LABEL: dict[RuleKind, str] = {
    RuleKind.BRAND: "marka",
    RuleKind.KEYWORD: "kelime",
    RuleKind.CATEGORY: "kategori",
    RuleKind.NEGATIVE_KEYWORD: "sustur",
}

_EVENT_WORDS = {str(kind) for kind in EventKind}

WATCH_USAGE = (
    "Kullanım:\n"
    "/watch marka Nike\n"
    "/watch kelime air max\n"
    "/watch kategori Sneaker\n\n"
    "Belirli olaylara daraltmak için + öneki kullan:\n"
    "/watch marka Nike +restock +price_drop"
)
MUTE_USAGE = "Kullanım: /mute çorap"
UNWATCH_USAGE = "Kullanım: /unwatch 3  (id için /rules)"
ADDTARGET_USAGE = (
    "Kullanım:\n"
    "/addtarget -1001234567890          — duyuru kanalı ekler\n"
    "/addtarget 987654321 admin         — komut yetkisi de verir\n\n"
    "Kanal id'sini bulmak için kanaldan bir mesajı bu sohbete forward et."
)
RMTARGET_USAGE = "Kullanım: /rmtarget -1001234567890  (id için /targets)"


class StorePort(Protocol):
    async def add_rule(self, kind, pattern, *, event_types=None, created_by=None) -> int: ...
    async def list_rules(self, *, only_active: bool = True) -> tuple[Rule, ...]: ...
    async def deactivate_rule(self, rule_id: int) -> bool: ...
    async def list_all_targets(self) -> tuple[NotifyTarget, ...]: ...
    async def ensure_target(
        self, chat_id, *, receives_notifications=True, can_manage=True, title=None
    ) -> None: ...
    async def remove_target(self, chat_id: int) -> bool: ...


class CommandService:
    def __init__(
        self,
        store: StorePort,
        *,
        profile: RetailerProfile,
        extra_commands: Sequence[ExtraCommand] = (),
    ) -> None:
        self._store = store
        self._profile = profile
        self._extras = tuple(extra_commands)

    def help_text(self) -> str:
        lines = [
            f"{self._profile.name} stok takip botu",
            "",
            "/watch marka|kelime|kategori <değer> — bildirim kuralı ekler",
            "/mute <kelime> — eşleşenleri susturur (negatif kural)",
            "/rules — aktif kuralları listeler",
            "/unwatch <id> — kuralı kapatır",
            *(extra.help for extra in self._extras),
            "",
            "Duyuru kanalı:",
            "/targets — bildirim hedeflerini listeler",
            "/addtarget <id> [admin] — hedef ekler",
            "/rmtarget <id> — hedefi kaldırır",
            "/chatid — bulunduğun sohbetin id'sini söyler",
            "",
            "Kanal id'sini öğrenmek için kanaldan bir mesajı bana forward et.",
        ]
        return "\n".join(lines)

    # --- kural ekleme -----------------------------------------------------

    async def watch(self, args: str, *, user_id: int | None = None) -> str:
        parts = (args or "").split()
        if len(parts) < 2:
            return WATCH_USAGE

        kind = _KIND_BY_WORD.get(parts[0].lower())
        if kind is None:
            return WATCH_USAGE

        pattern_words, event_words = _split_event_flags(parts[1:])
        if not pattern_words:
            return WATCH_USAGE

        invalid = [word for word in event_words if word not in _EVENT_WORDS]
        if invalid:
            return f"Bilinmeyen event tipi: {', '.join(invalid)}\n\n{_event_help()}"

        event_types = frozenset(EventKind(word) for word in event_words) if event_words else None
        pattern = " ".join(pattern_words)
        rule_id = await self._store.add_rule(
            kind, pattern, event_types=event_types, created_by=user_id
        )
        scope = f" ({', '.join(sorted(event_words))})" if event_words else " (tüm olaylar)"
        return f"✅ #{rule_id} eklendi — {_KIND_LABEL[kind]}: {pattern}{scope}"

    async def mute(self, args: str, *, user_id: int | None = None) -> str:
        pattern = (args or "").strip()
        if not pattern:
            return MUTE_USAGE
        rule_id = await self._store.add_rule(
            RuleKind.NEGATIVE_KEYWORD, pattern, created_by=user_id
        )
        return f"🔇 #{rule_id} eklendi — susturulan: {pattern}"

    # --- kural listeleme --------------------------------------------------

    async def rules(self) -> str:
        rules = await self._store.list_rules()
        if not rules:
            return "Henüz kural yok. Bildirim almak için önce /watch ile kural ekle."

        lines = ["📋 Aktif kurallar", ""]
        for rule in rules:
            scope = (
                ", ".join(sorted(str(event) for event in rule.event_types))
                if rule.event_types
                else "tüm olaylar"
            )
            marker = "🔇" if rule.kind is RuleKind.NEGATIVE_KEYWORD else "🔔"
            lines.append(f"{marker} #{rule.id} {_KIND_LABEL[rule.kind]}: {rule.pattern} — {scope}")
        lines.append("")
        lines.append("Kapatmak için: /unwatch <id>")
        return "\n".join(lines)

    async def unwatch(self, args: str) -> str:
        raw = (args or "").strip()
        if not raw.lstrip("#").isdigit():
            return UNWATCH_USAGE
        rule_id = int(raw.lstrip("#"))
        if await self._store.deactivate_rule(rule_id):
            return f"🗑 #{rule_id} kapatıldı."
        return f"#{rule_id} bulunamadı ya da zaten kapalı."

    # --- duyuru kanalı / hedefler -----------------------------------------

    async def targets(self) -> str:
        rows = await self._store.list_all_targets()
        if not rows:
            return (
                "Henüz bildirim hedefi yok.\n\n"
                "Duyuru kanalı eklemek için kanaldan bir mesajı bana forward et."
            )

        lines = ["📡 Bildirim hedefleri", ""]
        for row in rows:
            roles = []
            if row.receives_notifications:
                roles.append("bildirim")
            if row.can_manage:
                roles.append("komut yetkisi")
            name = f" — {row.title}" if row.title else ""
            lines.append(f"• `{row.chat_id}`{name}\n  {', '.join(roles) or 'rol yok'}")
        lines.extend(["", "Kaldırmak için: /rmtarget <id>"])
        return "\n".join(lines)

    async def add_target(self, args: str) -> str:
        parts = (args or "").split()
        if not parts:
            return ADDTARGET_USAGE

        chat_id = _parse_chat_id(parts[0])
        if chat_id is None:
            return ADDTARGET_USAGE

        is_admin = any(word.lower() == "admin" for word in parts[1:])
        await self._store.ensure_target(
            chat_id, receives_notifications=True, can_manage=is_admin
        )
        role = "bildirim + komut yetkisi" if is_admin else "yalnızca bildirim"
        return f"✅ `{chat_id}` eklendi — {role}"

    async def remove_target(self, args: str) -> str:
        chat_id = _parse_chat_id(args or "")
        if chat_id is None:
            return RMTARGET_USAGE
        if await self._store.remove_target(chat_id):
            return f"🗑 `{chat_id}` kaldırıldı."
        return f"`{chat_id}` bulunamadı ya da zaten kapalı."

    def describe_chat(self, chat_id: int, *, title: str | None = None) -> str:
        name = f" ({title})" if title else ""
        return f"Bu sohbetin id'si: `{chat_id}`{name}"

    def describe_forwarded(self, chat_id: int, *, title: str | None = None) -> str:
        """Forward edilen kanal mesajından id çıkarıp hazır komut sunar."""
        name = title or "bu kanal"
        return (
            f"📡 {name}\n"
            f"id: `{chat_id}`\n\n"
            f"Duyuru hedefi yapmak için:\n"
            f"/addtarget {chat_id}\n\n"
            "Botu kanala *yönetici* olarak eklemeyi ve 'Mesaj Gönder' yetkisi "
            "vermeyi unutma."
        )


def _parse_chat_id(raw: str) -> int | None:
    """Kanal id'leri ``-100`` ile başlar; eksi işareti argüman sanılmamalı."""
    candidate = raw.strip().lstrip("#")
    if not candidate:
        return None
    body = candidate[1:] if candidate[0] == "-" else candidate
    return int(candidate) if body.isdigit() else None


def _split_event_flags(words: list[str]) -> tuple[list[str], list[str]]:
    """``+`` önekli sözcükleri event tipi olarak ayırır, gerisini desen sayar.

    Önek zorunludur: ``/watch marka Nike restok`` gibi bir yazım hatası
    sessizce hiç eşleşmeyen bir kural yaratmak yerine, ``+restok`` biçiminde
    yazıldığında açıkça reddedilir.
    """
    pattern: list[str] = []
    events: list[str] = []
    for word in words:
        if word.startswith("+") and len(word) > 1:
            events.append(word[1:].lower())
        else:
            pattern.append(word)
    return pattern, events


def _event_help() -> str:
    return "Geçerli tipler: " + ", ".join(sorted(_EVENT_WORDS))
