# monitor-notify

Stok ve fiyat takip botları için paylaşılan Telegram bildirim katmanı:
outbox kuyruğu, marka/kelime/kategori kuralları, duyuru kanalı yönetimi,
görselli bildirimler ve yönetim komutları.

Her retailer kendi process'i, veritabanı ve Telegram botuyla çalışır; bu paket
yalnızca kodu paylaşır.

## Kurulum

```
monitor-notify @ git+https://github.com/argonft/monitor-notify@v0.1.0
```

Geliştirirken: `pip install -e ../notify`

## Retailer entegrasyonu

Retailer üç şey sağlar:

1. **`EventSource`** — bekleyen bildirimleri `Notification` olarak döner, gönderilenleri işaretler.
2. **`RetailerProfile`** — mağaza adı, varyant ismi ("Beden", "Gramaj"), acil olay türleri, buton metni.
3. **Migration kaynağı** — kendi şeması; kütüphanenin tabloları `NOTIFY_MIGRATIONS` ile gelir.

```python
from monitor_notify import (
    NOTIFY_MIGRATIONS, ExtraCommand, MigrationSource, NotifyApp, NotifyConfig,
    RetailerProfile, migrate,
)

await migrate(pool, NOTIFY_MIGRATIONS, MigrationSource(prefix="", directory=MY_MIGRATIONS))

notify = NotifyApp(
    pool=pool,
    profile=RetailerProfile(name="shop.example"),
    source=MyEventSource(pool),
    config=NotifyConfig(bot_token=TOKEN, admin_chat_id=ADMIN_ID, channel_id=CHANNEL_ID),
    extra_commands=[ExtraCommand("find", "/find <kelime> — stok durumu", find)],
)
async with notify.running():
    await scrape_forever()
```

`EventSource` uygulamanı hazır sözleşme testiyle doğrula:

```python
from monitor_notify.testing import check_event_source_contract

await check_event_source_contract(MyEventSource(pool))
```

## Ortak komutlar

`/watch`, `/mute`, `/rules`, `/unwatch`, `/targets`, `/addtarget`, `/rmtarget`,
`/chatid`, `/help`. Kanaldan bota forward edilen mesaj kanal id'sini verir.

## Test

```
docker run -d --rm --name notify-test-db -e POSTGRES_USER=t -e POSTGRES_PASSWORD=t \
  -e POSTGRES_DB=t -p 127.0.0.1:55440:5432 postgres:16-alpine
MONITOR_NOTIFY_TEST_DATABASE_URL=postgresql://t:t@127.0.0.1:55440/t pytest
```

Entegrasyon testleri `public` şemasını sıfırlar; adresi asla gerçek bir veritabanına verme.

## Lisans

MIT
