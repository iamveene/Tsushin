-- Migration: Add Amadeus Integration Model
-- Date: 2025-12-30
-- Description: Adds amadeus_integration table for Hub-based flight search provider

-- Create amadeus_integration table (extends hub_integration)
CREATE TABLE IF NOT EXISTS amadeus_integration (
    id INTEGER PRIMARY KEY,

    -- Environment configuration
    environment VARCHAR(20) NOT NULL DEFAULT 'test',  -- 'test' or 'production'

    -- API credentials
    api_key VARCHAR(100) NOT NULL,
    api_secret_encrypted TEXT NOT NULL,

    -- Default settings
    default_currency VARCHAR(3) DEFAULT 'BRL',
    max_results INTEGER DEFAULT 5,

    -- Rate limiting (150 requests/min for Amadeus API)
    requests_last_minute INTEGER DEFAULT 0,
    last_request_window DATETIME,

    -- Token caching
    current_access_token_encrypted TEXT,
    token_expires_at DATETIME,

    -- Foreign key to hub_integration
    FOREIGN KEY (id) REFERENCES hub_integration(id) ON DELETE CASCADE
);

-- The parent hub_integration row will have:
-- - type = 'amadeus'
-- - name = 'Amadeus Flight Search' (or custom name)
-- - is_active = TRUE/FALSE
-- - tenant_id = NULL (system-wide) or tenant ID
-- - health_status = 'unknown', 'healthy', 'degraded', 'unavailable'
-- - last_health_check = timestamp
-- - created_at, updated_at

-- Example insert (to be done via API or migration script):
-- INSERT INTO hub_integration (type, name, is_active, tenant_id, health_status)
-- VALUES ('amadeus', 'Amadeus Flight Search', 1, NULL, 'unknown');
--
-- INSERT INTO amadeus_integration (id, environment, api_key, api_secret_encrypted, default_currency, max_results)
-- VALUES (last_insert_rowid(), 'test', 'YOUR_KEY', 'ENCRYPTED_SECRET', 'BRL', 5);
