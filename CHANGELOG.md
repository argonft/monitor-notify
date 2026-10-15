# Değişiklik Günlüğü

Sürüm `1.0`'a kadar `0.x` sürümlerinde bozucu değişiklikler **BOZUCU** etiketiyle işaretlenir.

## 0.2.0 — 2026-10-15

- `RetailerProfile.notify_without_rules` (varsayılan `False`): açıkken bu event'i
  kapsayan hiç pozitif kural (`/watch`) yoksa bildirim gönderilir. Kullanıcının
  ürünleri tek tek takibe aldığı retailer'lar içindir. `/mute` her durumda susturur,
  pozitif kural varsa yine daraltır. Varsayılan davranış değişmedi.
- `matches(..., allow_without_rules=...)` parametresi.
- `contains` genel API'ye eklendi: Türkçe ve büyük/küçük harf duyarsız alt metin araması.

## 0.1.0 — 2026-10-14

- İlk sürüm: `Notification` sözleşmesi, `EventSource`, `RetailerProfile`,
  outbox, kurallar, Telegram gönderimi (görsel + düz metin fallback),
  ortak yönetim komutları, ek komutlar, çok kaynaklı migration,
  `check_event_source_contract`.
- Kuyruk üst üste 30 tur işlenemezse admin'e tek seferlik teşhis gönderilir.
- Türü bilinmeyen kural (`watch_rules.kind`) uyarıyla atlanır; kuyruğu durdurmaz.
