-- Kütüphaneden önce bu tabloları kendisi kuran bir retailer şemasının ilk hali.
-- Uyumluluk testi bu dosyayı uygular, ardından notify/001'in no-op olduğunu doğrular.

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
