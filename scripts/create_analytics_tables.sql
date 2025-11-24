-- ============================================================================
-- Analytics & Monitoring Tables for Supabase
-- ============================================================================

-- Table: analytics_events
-- เก็บ event ทั้งหมดของระบบ
CREATE TABLE IF NOT EXISTS analytics_events (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL, -- 'image_analysis', 'question', 'product_recommendation', 'error'
    
    -- Image analysis fields
    disease_name TEXT,
    pest_type TEXT,
    confidence TEXT,
    severity TEXT,
    
    -- Question fields
    question_text TEXT,
    intent TEXT,
    
    -- Product recommendation fields
    product_name TEXT,
    
    -- Error fields
    error_type TEXT,
    error_message TEXT,
    stack_trace TEXT,
    
    -- Performance metrics
    response_time_ms FLOAT,
    
    -- Timestamp
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes separately
CREATE INDEX IF NOT EXISTS idx_analytics_events_user_id ON analytics_events(user_id);
CREATE INDEX IF NOT EXISTS idx_analytics_events_event_type ON analytics_events(event_type);
CREATE INDEX IF NOT EXISTS idx_analytics_events_created_at ON analytics_events(created_at);
CREATE INDEX IF NOT EXISTS idx_analytics_events_disease_name ON analytics_events(disease_name);
CREATE INDEX IF NOT EXISTS idx_analytics_events_product_name ON analytics_events(product_name);

-- Table: analytics_alerts
-- เก็บ alert ที่เกิดขึ้น
CREATE TABLE IF NOT EXISTS analytics_alerts (
    id BIGSERIAL PRIMARY KEY,
    alert_type TEXT NOT NULL, -- 'high_error_rate', 'slow_response', 'high_error_count'
    message TEXT NOT NULL,
    severity TEXT NOT NULL, -- 'info', 'warning', 'critical'
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes separately
CREATE INDEX IF NOT EXISTS idx_analytics_alerts_created_at ON analytics_alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_analytics_alerts_severity ON analytics_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_analytics_alerts_resolved ON analytics_alerts(resolved);

-- ============================================================================
-- Useful Views for Dashboard
-- ============================================================================

-- View: Daily Statistics
CREATE OR REPLACE VIEW analytics_daily_stats AS
SELECT 
    DATE(created_at) as date,
    COUNT(DISTINCT user_id) as unique_users,
    COUNT(*) FILTER (WHERE event_type = 'image_analysis') as images_analyzed,
    COUNT(*) FILTER (WHERE event_type = 'question') as questions_asked,
    COUNT(*) FILTER (WHERE event_type = 'error') as errors,
    AVG(response_time_ms) FILTER (WHERE response_time_ms IS NOT NULL) as avg_response_time_ms
FROM analytics_events
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- View: Top Diseases (Last 7 Days)
CREATE OR REPLACE VIEW analytics_top_diseases AS
SELECT 
    disease_name,
    COUNT(*) as count
FROM analytics_events
WHERE event_type = 'image_analysis'
    AND disease_name IS NOT NULL
    AND created_at >= NOW() - INTERVAL '7 days'
GROUP BY disease_name
ORDER BY count DESC
LIMIT 20;

-- View: Top Products (Last 7 Days)
CREATE OR REPLACE VIEW analytics_top_products AS
SELECT 
    product_name,
    COUNT(*) as count
FROM analytics_events
WHERE event_type = 'product_recommendation'
    AND product_name IS NOT NULL
    AND created_at >= NOW() - INTERVAL '7 days'
GROUP BY product_name
ORDER BY count DESC
LIMIT 20;

-- View: Hourly Activity (Today)
CREATE OR REPLACE VIEW analytics_hourly_activity AS
SELECT 
    EXTRACT(HOUR FROM created_at) as hour,
    COUNT(*) as request_count
FROM analytics_events
WHERE DATE(created_at) = CURRENT_DATE
GROUP BY EXTRACT(HOUR FROM created_at)
ORDER BY hour;

-- View: Error Summary (Last 24 Hours)
CREATE OR REPLACE VIEW analytics_error_summary AS
SELECT 
    error_type,
    COUNT(*) as count,
    MAX(created_at) as last_occurrence
FROM analytics_events
WHERE event_type = 'error'
    AND created_at >= NOW() - INTERVAL '24 hours'
GROUP BY error_type
ORDER BY count DESC;

-- ============================================================================
-- Functions for Analytics
-- ============================================================================

-- Function: Get Dashboard Stats
CREATE OR REPLACE FUNCTION get_dashboard_stats(days_back INTEGER DEFAULT 1)
RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    SELECT json_build_object(
        'overview', (
            SELECT json_build_object(
                'unique_users', COUNT(DISTINCT user_id),
                'images_analyzed', COUNT(*) FILTER (WHERE event_type = 'image_analysis'),
                'questions_asked', COUNT(*) FILTER (WHERE event_type = 'question'),
                'errors', COUNT(*) FILTER (WHERE event_type = 'error')
            )
            FROM analytics_events
            WHERE created_at >= NOW() - (days_back || ' days')::INTERVAL
        ),
        'performance', (
            SELECT json_build_object(
                'avg_response_time_ms', ROUND(AVG(response_time_ms)::NUMERIC, 2),
                'error_rate_percent', ROUND(
                    (COUNT(*) FILTER (WHERE event_type = 'error')::FLOAT / 
                     NULLIF(COUNT(*) FILTER (WHERE event_type IN ('image_analysis', 'question')), 0) * 100)::NUMERIC, 
                    2
                )
            )
            FROM analytics_events
            WHERE created_at >= NOW() - (days_back || ' days')::INTERVAL
        )
    ) INTO result;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Cleanup Old Data (Optional - Run Periodically)
-- ============================================================================

-- Delete events older than 30 days
CREATE OR REPLACE FUNCTION cleanup_old_analytics()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM analytics_events
    WHERE created_at < NOW() - INTERVAL '30 days';
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Grant Permissions (if needed)
-- ============================================================================

-- Grant access to anon and authenticated users
GRANT SELECT ON analytics_events TO anon, authenticated;
GRANT INSERT ON analytics_events TO anon, authenticated;
GRANT SELECT ON analytics_alerts TO anon, authenticated;
GRANT INSERT ON analytics_alerts TO anon, authenticated;

-- Grant access to views
GRANT SELECT ON analytics_daily_stats TO anon, authenticated;
GRANT SELECT ON analytics_top_diseases TO anon, authenticated;
GRANT SELECT ON analytics_top_products TO anon, authenticated;
GRANT SELECT ON analytics_hourly_activity TO anon, authenticated;
GRANT SELECT ON analytics_error_summary TO anon, authenticated;

-- ============================================================================
-- Comments
-- ============================================================================

COMMENT ON TABLE analytics_events IS 'Store all system events for analytics';
COMMENT ON TABLE analytics_alerts IS 'Store system alerts and warnings';
COMMENT ON VIEW analytics_daily_stats IS 'Daily statistics summary';
COMMENT ON VIEW analytics_top_diseases IS 'Most detected diseases in last 7 days';
COMMENT ON VIEW analytics_top_products IS 'Most recommended products in last 7 days';
COMMENT ON VIEW analytics_hourly_activity IS 'Hourly request distribution for today';
COMMENT ON VIEW analytics_error_summary IS 'Error summary for last 24 hours';
