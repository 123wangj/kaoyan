ALTER TABLE users ADD COLUMN IF NOT EXISTS invite_code VARCHAR(16);
ALTER TABLE users ADD COLUMN IF NOT EXISTS invited_by INTEGER REFERENCES users(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS wechat_id VARCHAR(64);
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_invite_code
    ON users(invite_code) WHERE invite_code IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone
    ON users(phone) WHERE phone IS NOT NULL;

CREATE TABLE IF NOT EXISTS password_reset_codes (
    id BIGSERIAL PRIMARY KEY,
    phone VARCHAR(20) NOT NULL,
    purpose VARCHAR(16) NOT NULL,
    user_id VARCHAR(64),
    code_hash VARCHAR(128) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    used_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE password_reset_codes ADD COLUMN IF NOT EXISTS request_ip VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_password_reset_lookup
    ON password_reset_codes(phone, purpose, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_password_reset_ip
    ON password_reset_codes(request_ip, created_at DESC);
