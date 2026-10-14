"""Retailer'ların dayandığı genel API paket kökünden erişilebilir olmalı."""
import monitor_notify

PUBLIC = [
    "EventKind", "Notification", "EventSource", "RetailerProfile", "NotifyConfig",
    "NotifyApp", "ExtraCommand", "MigrationSource", "NOTIFY_MIGRATIONS",
    "MigrationsMissingError", "migrate", "format_money", "NotifyStore",
]


def test_genel_api_disa_aktarilir():
    for name in PUBLIC:
        assert hasattr(monitor_notify, name), name
    assert sorted(monitor_notify.__all__) == sorted(PUBLIC)


def test_surum_tanimli():
    assert monitor_notify.__version__ == "0.1.0"
