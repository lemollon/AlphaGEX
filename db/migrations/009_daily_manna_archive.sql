-- Migration 009: Daily Manna Archive Tables
-- Persistent storage for Daily Manna devotionals, comments, reflections, and prayer tracking

-- ============================================================================
-- DAILY MANNA ARCHIVE
-- Stores generated devotionals for historical access
-- ============================================================================

CREATE TABLE IF NOT EXISTS daily_manna_archive (
    id SERIAL PRIMARY KEY,
    date DATE UNIQUE NOT NULL,

    -- Devotional content (JSONB for flexibility)
    devotional JSONB NOT NULL,  -- bible_study, morning_prayer, reflection_questions, key_insight, theme
    scriptures JSONB NOT NULL,  -- Array of scripture objects
    news JSONB NOT NULL,        -- Array of news items that day

    -- Metadata
    greeting TEXT,
    news_sources TEXT[],

    -- Timestamps
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    archived_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Indexes for common queries
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_manna_archive_date ON daily_manna_archive(date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_manna_archive_theme ON daily_manna_archive((devotional->>'theme'));

-- ============================================================================
-- COMMUNITY COMMENTS
-- Stores comments on devotionals
-- ============================================================================

CREATE TABLE IF NOT EXISTS daily_manna_comments (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) DEFAULT 'anonymous',
    user_name VARCHAR(50) NOT NULL DEFAULT 'Anonymous',
    comment TEXT NOT NULL,
    date DATE NOT NULL,  -- Which devotional date this comment is for
    likes INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_manna_comments_date ON daily_manna_comments(date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_manna_comments_user ON daily_manna_comments(user_id);

-- ============================================================================
-- PERSONAL REFLECTIONS
-- Stores user reflections/notes on devotionals
-- ============================================================================

CREATE TABLE IF NOT EXISTS daily_manna_reflections (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL DEFAULT 'default_user',
    date DATE NOT NULL,
    reflection TEXT NOT NULL,
    prayer_answered BOOLEAN DEFAULT FALSE,
    favorite BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Allow multiple reflections per user per day
    UNIQUE(user_id, date, created_at)
);

CREATE INDEX IF NOT EXISTS idx_daily_manna_reflections_user ON daily_manna_reflections(user_id);
CREATE INDEX IF NOT EXISTS idx_daily_manna_reflections_date ON daily_manna_reflections(date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_manna_reflections_favorite ON daily_manna_reflections(user_id, favorite) WHERE favorite = TRUE;

-- ============================================================================
-- PRAYER TRACKER
-- Tracks daily prayer habits per user
-- ============================================================================

CREATE TABLE IF NOT EXISTS daily_manna_prayer_tracker (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    date DATE NOT NULL,
    prayed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_daily_manna_prayer_user ON daily_manna_prayer_tracker(user_id);
CREATE INDEX IF NOT EXISTS idx_daily_manna_prayer_date ON daily_manna_prayer_tracker(date DESC);

-- ============================================================================
-- HELPER VIEW: Prayer Stats
-- ============================================================================

CREATE OR REPLACE VIEW daily_manna_prayer_stats AS
SELECT
    user_id,
    COUNT(*) as total_days,
    MAX(date) as last_prayed,
    COUNT(CASE WHEN date >= CURRENT_DATE - INTERVAL '7 days' THEN 1 END) as days_last_week
FROM daily_manna_prayer_tracker
GROUP BY user_id;
