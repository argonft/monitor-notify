"""Bildirim kuralları ve hedefleri.

Kurallar veritabanında durur ve Telegram komutlarıyla düzenlenir; değişiklik
için yeniden dağıtım gerekmez. Retailer bu tabloları doğrudan sorgulamaz,
gerekiyorsa buradaki salt-okur yardımcıları kullanır.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import asyncpg

from ..model import EventKind
from ..rules.matcher import Rule, RuleKind

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NotifyTarget:
    """Bir Telegram sohbeti ve üstlendiği roller.

    İki rol bağımsızdır: duyuru kanalı bildirim alır ama komut çalıştıramaz;
    admin sohbeti komut çalıştırır ama bildirim almayabilir.
    """

    chat_id: int
    receives_notifications: bool
    can_manage: bool
    title: str | None = None


class NotifyStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # --- kurallar ---------------------------------------------------------

    async def list_rules(self, *, only_active: bool = True) -> tuple[Rule, ...]:
        query = "SELECT id, kind, pattern, event_types, is_active FROM watch_rules"
        if only_active:
            query += " WHERE is_active = true"
        query += " ORDER BY id"
        rows = await self._pool.fetch(query)
        rules = (_to_rule(row) for row in rows)
        return tuple(rule for rule in rules if rule is not None)

    async def add_rule(
        self,
        kind: RuleKind,
        pattern: str,
        *,
        event_types: frozenset[EventKind] | None = None,
        created_by: int | None = None,
    ) -> int:
        return await self._pool.fetchval(
            """
            INSERT INTO watch_rules (kind, pattern, event_types, created_by)
            VALUES ($1, $2, $3, $4) RETURNING id
            """,
            str(kind),
            pattern.strip(),
            [str(event) for event in sorted(event_types)] if event_types else None,
            created_by,
        )

    async def deactivate_rule(self, rule_id: int) -> bool:
        status = await self._pool.execute(
            "UPDATE watch_rules SET is_active = false WHERE id = $1 AND is_active = true",
            rule_id,
        )
        return status.endswith("1")

    async def active_rule_count(self) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM watch_rules WHERE is_active = true"
        )

    # --- bildirim hedefleri -----------------------------------------------

    async def list_notify_targets(self) -> tuple[int, ...]:
        """Bildirimlerin gönderileceği sohbetler."""
        rows = await self._pool.fetch(
            """
            SELECT chat_id FROM notify_targets
            WHERE is_active = true AND receives_notifications = true
            ORDER BY chat_id
            """
        )
        return tuple(row["chat_id"] for row in rows)

    async def list_admin_chats(self) -> tuple[int, ...]:
        """Komut çalıştırmaya yetkili sohbetler."""
        rows = await self._pool.fetch(
            """
            SELECT chat_id FROM notify_targets
            WHERE is_active = true AND can_manage = true
            ORDER BY chat_id
            """
        )
        return tuple(row["chat_id"] for row in rows)

    async def list_all_targets(self) -> tuple[NotifyTarget, ...]:
        rows = await self._pool.fetch(
            """
            SELECT chat_id, receives_notifications, can_manage, title
            FROM notify_targets WHERE is_active = true ORDER BY chat_id
            """
        )
        return tuple(
            NotifyTarget(
                chat_id=row["chat_id"],
                receives_notifications=row["receives_notifications"],
                can_manage=row["can_manage"],
                title=row["title"],
            )
            for row in rows
        )

    async def ensure_target(
        self,
        chat_id: int,
        *,
        receives_notifications: bool = True,
        can_manage: bool = True,
        title: str | None = None,
    ) -> None:
        """Hedefi ekler ya da rollerini günceller."""
        await self._pool.execute(
            """
            INSERT INTO notify_targets (chat_id, is_active, receives_notifications, can_manage, title)
            VALUES ($1, true, $2, $3, $4)
            ON CONFLICT (chat_id) DO UPDATE SET
                is_active = true,
                receives_notifications = EXCLUDED.receives_notifications,
                can_manage = EXCLUDED.can_manage,
                title = coalesce(EXCLUDED.title, notify_targets.title)
            """,
            chat_id, receives_notifications, can_manage, title,
        )

    async def remove_target(self, chat_id: int) -> bool:
        status = await self._pool.execute(
            "UPDATE notify_targets SET is_active = false WHERE chat_id = $1 AND is_active = true",
            chat_id,
        )
        return status.endswith("1")


_KNOWN_KINDS = frozenset(str(kind) for kind in EventKind)
_KNOWN_RULE_KINDS = frozenset(str(kind) for kind in RuleKind)


def _to_rule(row: asyncpg.Record) -> Rule | None:
    """Türü bilinmeyen kural atlanır (örn. daha yeni bir sürümden geri dönüldüyse)."""
    if row["kind"] not in _KNOWN_RULE_KINDS:
        logger.warning("Kural #%s bilinmeyen türde (%s), atlandı.", row["id"], row["kind"])
        return None
    return Rule(
        id=row["id"],
        kind=RuleKind(row["kind"]),
        pattern=row["pattern"],
        event_types=_event_types(row["id"], row["event_types"]),
        is_active=row["is_active"],
    )


def _event_types(rule_id: int, raw: list[str] | None) -> frozenset[EventKind] | None:
    """Bilinmeyen değerler uyarıyla atlanır; tek bozuk kural kuyruğu durdurmamalı."""
    if not raw:
        return None
    unknown = [value for value in raw if value not in _KNOWN_KINDS]
    if unknown:
        logger.warning("Kural #%s bilinmeyen event türleri içeriyor, atlandı: %s", rule_id, unknown)
    return frozenset(EventKind(value) for value in raw if value in _KNOWN_KINDS)
