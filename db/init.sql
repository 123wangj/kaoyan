-- ============================================================
-- 考研学习平台 - PostgreSQL 数据库初始化脚本
-- 数据库名: kaoyan_ai
-- 字符集: UTF8
-- 适用版本: PostgreSQL 14+
-- ============================================================

-- 1. 科目表（4 科：DS / OS / CN / CO）
DROP TABLE IF EXISTS subjects CASCADE;
CREATE TABLE subjects (
    id    SERIAL PRIMARY KEY,
    code  VARCHAR(8)  UNIQUE NOT NULL,
    name  VARCHAR(64) NOT NULL
);
COMMENT ON TABLE subjects IS '考研 4 门计算机专业课';

-- 2. 用户表
DROP TABLE IF EXISTS users CASCADE;
CREATE TABLE users (
    id                 SERIAL PRIMARY KEY,
    user_id            VARCHAR(64)  UNIQUE NOT NULL,   -- 业务 ID（如 u1）
    username           VARCHAR(64)  UNIQUE,
    password_hash      TEXT,
    nickname           VARCHAR(64),
    target_school      TEXT,
    target_major       TEXT,
    exam_date          DATE,
    daily_study_minutes INTEGER DEFAULT 0,
    total_tokens       BIGINT  DEFAULT 0,              -- 累计消耗的 AI token 总量
    total_ai_calls     INTEGER DEFAULT 0,              -- 累计 AI 调用次数
    last_ai_call_at    TIMESTAMP,                      -- 最近一次 AI 调用时间
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE users IS '用户主表';

-- 3. 知识点表
DROP TABLE IF EXISTS knowledge_points CASCADE;
CREATE TABLE knowledge_points (
    id          SERIAL PRIMARY KEY,
    subject_id  INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    chapter     VARCHAR(255),
    difficulty  SMALLINT DEFAULT 1 CHECK (difficulty BETWEEN 1 AND 5),
    description TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (subject_id, name, chapter)
);
CREATE INDEX idx_kp_subject ON knowledge_points(subject_id);
COMMENT ON TABLE knowledge_points IS '知识点主表';

-- 4. 题库表
DROP TABLE IF EXISTS questions CASCADE;
CREATE TABLE questions (
    id            SERIAL PRIMARY KEY,
    external_id   VARCHAR(128) UNIQUE,                -- 原 JSONL 中的 id 字段（如 wd-mcq-数据结-001-1）
    subject_id    INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    question_type VARCHAR(16)  NOT NULL,              -- choice / fill / big
    stem          TEXT NOT NULL,
    options       JSONB,                             -- {"A":"...","B":"..."} 或 ["A","B","C","D"]
    answer        TEXT,
    analysis      TEXT,
    difficulty    VARCHAR(16) DEFAULT '基础',
    source        VARCHAR(128),                       -- '25王道数据结构选择题'
    year          INTEGER,
    is_real_exam  BOOLEAN DEFAULT FALSE,
    chapter       VARCHAR(255),
    section       VARCHAR(255),
    question_number VARCHAR(16),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_questions_subject   ON questions(subject_id);
CREATE INDEX idx_questions_type      ON questions(question_type);
CREATE INDEX idx_questions_difficulty ON questions(difficulty);
CREATE INDEX idx_questions_source    ON questions(source);
COMMENT ON TABLE questions IS '题库主表';

-- 5. 题目-知识点 多对多关联
DROP TABLE IF EXISTS question_kp CASCADE;
CREATE TABLE question_kp (
    question_id        INTEGER REFERENCES questions(id) ON DELETE CASCADE,
    knowledge_point_id INTEGER REFERENCES knowledge_points(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, knowledge_point_id)
);
CREATE INDEX idx_qkp_kp ON question_kp(knowledge_point_id);
COMMENT ON TABLE question_kp IS '题-知识点多对多';

-- 6. 做题记录表
DROP TABLE IF EXISTS answer_records CASCADE;
CREATE TABLE answer_records (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE,
    question_id   INTEGER REFERENCES questions(id) ON DELETE SET NULL,
    is_correct    BOOLEAN NOT NULL,
    user_answer   TEXT,
    spent_seconds INTEGER,
    error_reason  VARCHAR(64),
    mode          VARCHAR(16) DEFAULT 'practice',     -- practice / exam / review
    session_id    VARCHAR(64),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_ar_user_time     ON answer_records(user_id, created_at DESC);
CREATE INDEX idx_ar_user_question ON answer_records(user_id, question_id);
CREATE INDEX idx_ar_correct       ON answer_records(user_id, is_correct);
COMMENT ON TABLE answer_records IS '用户做题记录';

-- 7. 错题本
DROP TABLE IF EXISTS wrong_questions CASCADE;
CREATE TABLE wrong_questions (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER REFERENCES users(id) ON DELETE CASCADE,
    question_id    INTEGER REFERENCES questions(id) ON DELETE CASCADE,
    error_count    INTEGER DEFAULT 1,
    last_error_at  TIMESTAMP,
    mastered       BOOLEAN DEFAULT FALSE,
    mastered_at    TIMESTAMP,
    notes          TEXT,
    UNIQUE (user_id, question_id)
);
CREATE INDEX idx_wq_user_mastered ON wrong_questions(user_id, mastered);
COMMENT ON TABLE wrong_questions IS '错题本';

-- 8. 学习批次/模考
DROP TABLE IF EXISTS study_sessions CASCADE;
CREATE TABLE study_sessions (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
    mode         VARCHAR(16),                          -- daily / exam / review
    subject_id   INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    total        INTEGER DEFAULT 0,
    correct      INTEGER DEFAULT 0,
    duration_sec INTEGER DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_ss_user_time ON study_sessions(user_id, created_at DESC);
COMMENT ON TABLE study_sessions IS '练习/模考批次';

-- 9. 用户推送记录（保留原 u1.json 中的 pushed_* 列表）
DROP TABLE IF EXISTS push_history CASCADE;
CREATE TABLE push_history (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    item_type   VARCHAR(16) NOT NULL,                  -- knowledge / question
    item_id     VARCHAR(128) NOT NULL,
    pushed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, item_type, item_id)
);
CREATE INDEX idx_ph_user ON push_history(user_id);
COMMENT ON TABLE push_history IS '推送历史（防重复）';

-- 10. 知识点掌握度（聚合缓存）
DROP TABLE IF EXISTS kp_mastery CASCADE;
CREATE TABLE kp_mastery (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER REFERENCES users(id) ON DELETE CASCADE,
    knowledge_point_id INTEGER REFERENCES knowledge_points(id) ON DELETE CASCADE,
    attempt_count  INTEGER DEFAULT 0,
    correct_count  INTEGER DEFAULT 0,
    mastery_score  REAL DEFAULT 0,                     -- 0~1
    last_practiced TIMESTAMP,
    UNIQUE (user_id, knowledge_point_id)
);
COMMENT ON TABLE kp_mastery IS '知识点掌握度缓存';

-- 11. AI 调用 token 用量记录（每次 AI 操作一行）
DROP TABLE IF EXISTS ai_token_usage CASCADE;
CREATE TABLE ai_token_usage (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER REFERENCES users(id) ON DELETE CASCADE,
    operation_type   VARCHAR(32)  NOT NULL,            -- qa / explanation / plan / analysis / chat / other
    business_type    VARCHAR(32),                      -- 可选业务维度：question / knowledge / exam / push ...
    business_id      VARCHAR(64),                      -- 关联业务主键（题目 id / 知识点 id / 会话 id 等）
    model            VARCHAR(64),                      -- 调用的模型，如 gpt-4o / deepseek-chat
    prompt_tokens    INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens     INTEGER DEFAULT 0,
    request_id       VARCHAR(128),                     -- 上游 API 返回的请求 id
    status           VARCHAR(16) DEFAULT 'success',     -- success / failed
    error_message    TEXT,
    duration_ms      INTEGER,                          -- 接口耗时（毫秒）
    client_ip        VARCHAR(64),                      -- 调用方 IP（可选）
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_ai_token_user_time    ON ai_token_usage(user_id, created_at DESC);
CREATE INDEX idx_ai_token_operation    ON ai_token_usage(user_id, operation_type);
CREATE INDEX idx_ai_token_business     ON ai_token_usage(business_type, business_id);
CREATE INDEX idx_ai_token_created_at   ON ai_token_usage(created_at DESC);
COMMENT ON TABLE ai_token_usage IS 'AI 调用 token 用量记录（按用户、按次）';

-- 12. 学习计划（按 user 一份，整段 JSON 存储）
DROP TABLE IF EXISTS study_plans CASCADE;
CREATE TABLE study_plans (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    plan       JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE study_plans IS '用户学习计划';

-- 13. 每日任务完成状态
DROP TABLE IF EXISTS daily_task_completions CASCADE;
CREATE TABLE daily_task_completions (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
    task_date    DATE    NOT NULL,
    task_id      VARCHAR(64) NOT NULL,
    status       VARCHAR(16) DEFAULT 'done',  -- done / skipped
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, task_date, task_id)
);
CREATE INDEX idx_dtc_user_date ON daily_task_completions(user_id, task_date DESC);
COMMENT ON TABLE daily_task_completions IS '每日任务完成状态';

-- 14. AI 对话历史
DROP TABLE IF EXISTS chat_messages CASCADE;
CREATE TABLE chat_messages (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
    role       VARCHAR(16) NOT NULL,        -- user / assistant
    content    TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_chat_user_time ON chat_messages(user_id, created_at DESC);

-- 15. Per-question notes (typed text + compact hand-drawn stroke data).
DROP TABLE IF EXISTS question_notes CASCADE;
CREATE TABLE question_notes (
    id                   BIGSERIAL PRIMARY KEY,
    user_id              INTEGER REFERENCES users(id) ON DELETE CASCADE,
    question_external_id VARCHAR(128) NOT NULL,
    text_content         TEXT NOT NULL DEFAULT '',
    drawing              JSONB NOT NULL DEFAULT '{"version":1,"strokes":[]}'::jsonb,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, question_external_id)
);
CREATE INDEX idx_question_notes_user ON question_notes(user_id, updated_at DESC);
COMMENT ON TABLE chat_messages IS 'AI 对话舱历史';

-- Agent runtime observability and durable semantic memory.
\ir agent_upgrade.inc

-- ============================================================
-- 初始化科目数据
-- ============================================================
INSERT INTO subjects (code, name) VALUES
    ('DS', '数据结构'),
    ('OS', '操作系统'),
    ('CN', '计算机网络'),
    ('CO', '计算机组成原理')
ON CONFLICT (code) DO NOTHING;

-- ============================================================
-- 触发器：自动更新 updated_at
-- ============================================================
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_touch ON users;
CREATE TRIGGER trg_users_touch BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- 触发器：ai_token_usage 写入后自动累加 users.total_tokens / total_ai_calls
CREATE OR REPLACE FUNCTION sync_user_ai_usage() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'success' THEN
        UPDATE users
        SET total_tokens    = COALESCE(total_tokens, 0) + COALESCE(NEW.total_tokens, 0),
            total_ai_calls  = COALESCE(total_ai_calls, 0) + 1,
            last_ai_call_at = NEW.created_at
        WHERE id = NEW.user_id;
    ELSE
        UPDATE users
        SET total_ai_calls  = COALESCE(total_ai_calls, 0) + 1,
            last_ai_call_at = NEW.created_at
        WHERE id = NEW.user_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ai_token_usage_sync ON ai_token_usage;
CREATE TRIGGER trg_ai_token_usage_sync AFTER INSERT ON ai_token_usage
    FOR EACH ROW EXECUTE FUNCTION sync_user_ai_usage();
