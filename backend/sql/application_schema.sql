CREATE TABLE IF NOT EXISTS medi_users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS medi_profiles (
    user_id TEXT PRIMARY KEY REFERENCES medi_users(id) ON DELETE CASCADE,
    profile_json JSONB NOT NULL,
    tags_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS medi_conversations (
    conversation_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES medi_users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    preview TEXT NOT NULL,
    messages_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_medi_conversations_user_updated
    ON medi_conversations (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS medi_reports (
    report_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES medi_users(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    stored_file_name TEXT,
    report_type TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT,
    profile_tags_json JSONB NOT NULL,
    items_json JSONB NOT NULL,
    raw_text TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_medi_reports_user_created
    ON medi_reports (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS medi_audit_logs (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES medi_users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    detail_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_medi_audit_logs_user_created
    ON medi_audit_logs (user_id, created_at DESC);
