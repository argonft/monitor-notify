-- Bildirim kuralları ve hedefleri.
--
-- Bu tabloları daha önce kendi migration'larıyla kurmuş bir retailer
-- veritabanında no-op'tur: her ifade IF NOT EXISTS ile yazılmıştır ve
-- sütunlar o şemayla aynı sırada, aynı varsayılanlarla tanımlanır.
-- Boş bir veritabanında tabloları sıfırdan kurar.

CREATE TABLE IF NOT EXISTS watch_rules (
    id          serial PRIMARY KEY,
    kind        text NOT NULL,
    pattern     text NOT NULL,
    event_types text[],
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    created_by  bigint
);

CREATE TABLE IF NOT EXISTS notify_targets (
    chat_id   bigint PRIMARY KEY,
    is_active boolean NOT NULL DEFAULT true
);

-- Bildirim hedefi ile komut yetkisi ayrıdır: kanal bildirim alır ama komut
-- çalıştıramaz; admin komut çalıştırır ama bildirim almayabilir.
ALTER TABLE notify_targets
    ADD COLUMN IF NOT EXISTS receives_notifications boolean NOT NULL DEFAULT true;

ALTER TABLE notify_targets
    ADD COLUMN IF NOT EXISTS can_manage boolean NOT NULL DEFAULT true;

ALTER TABLE notify_targets
    ADD COLUMN IF NOT EXISTS title text;

ALTER TABLE notify_targets
    ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS notify_targets_notify_idx
    ON notify_targets (chat_id) WHERE is_active AND receives_notifications;
