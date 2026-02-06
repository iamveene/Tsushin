-- Migration: Add Google Flights Integration (SerpApi)
-- Parent table entry (HubIntegration) will be handled by code/ORM

CREATE TABLE IF NOT EXISTS google_flights_integration (
    id INTEGER PRIMARY KEY REFERENCES hub_integration(id),
    api_key_encrypted TEXT NOT NULL,
    default_currency VARCHAR(3) DEFAULT 'USD',
    default_language VARCHAR(5) DEFAULT 'en'
);
