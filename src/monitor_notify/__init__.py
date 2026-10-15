"""Stok ve fiyat takip botları için paylaşılan Telegram bildirim katmanı."""
from .app import NotifyApp
from .bot.extra import ExtraCommand
from .config import NotifyConfig
from .formatting.money import format_money
from .model import EventKind, Notification
from .ports import EventSource
from .profile import RetailerProfile
from .rules.normalize import contains
from .store.migrate import NOTIFY_MIGRATIONS, MigrationSource, MigrationsMissingError, migrate
from .store.notify_store import NotifyStore

__version__ = "0.2.0"

__all__ = [
    "EventKind",
    "Notification",
    "EventSource",
    "RetailerProfile",
    "NotifyConfig",
    "NotifyApp",
    "ExtraCommand",
    "MigrationSource",
    "NOTIFY_MIGRATIONS",
    "MigrationsMissingError",
    "migrate",
    "format_money",
    "NotifyStore",
    "contains",
]
