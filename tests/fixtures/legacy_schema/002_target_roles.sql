-- Bildirim hedefi ile komut yetkisini ayırır.
--
-- Önceki sürümde notify_targets iki işi birden yapıyordu: hem bildirimin
-- gideceği yer, hem komut çalıştırma yetkisi. Duyuru kanalı eklenince bu
-- ayrışması gerekti: kanal bildirim alır ama komut çalıştıramaz; admin
-- komut çalıştırır ama (istenirse) bildirim almaz.
--
-- Varsayılanlar true olduğu için mevcut satırlar her iki yetkiyi de korur;
-- bugünkü davranış değişmez.

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
