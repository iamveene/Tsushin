-- Fact Memory Cleanup SQL Script
-- Date: 2026-01-11
-- Purpose: Clean up garbage/test facts from semantic_knowledge table
--
-- IMPORTANT: This script will CREATE a backup table first!
--
-- Usage:
--   sqlite3 backend/data/agent.db < backend/data/cleanup_facts.sql

-- ============================================================================
-- STEP 1: CREATE BACKUP TABLE
-- ============================================================================

DROP TABLE IF EXISTS semantic_knowledge_backup_20260111;

CREATE TABLE semantic_knowledge_backup_20260111 AS
SELECT * FROM semantic_knowledge;

SELECT '✅ Backup created: semantic_knowledge_backup_20260111' as status;
SELECT COUNT(*) || ' facts backed up' as backup_count FROM semantic_knowledge_backup_20260111;

-- ============================================================================
-- STEP 2: SHOW BEFORE STATS
-- ============================================================================

SELECT '📊 BEFORE CLEANUP:' as status;
SELECT COUNT(*) || ' total facts' as before_count FROM semantic_knowledge;

SELECT 'Facts by Agent:' as status;
SELECT agent_id, COUNT(*) as count
FROM semantic_knowledge
GROUP BY agent_id
ORDER BY count DESC;

-- ============================================================================
-- STEP 3: REMOVE TEST ARTIFACTS
-- ============================================================================

SELECT '🧹 Removing test artifacts...' as status;

-- Repetition/mirroring test artifacts
DELETE FROM semantic_knowledge WHERE key LIKE '%repetition%';
DELETE FROM semantic_knowledge WHERE key LIKE '%mirroring%' OR key LIKE '%mirror%';
DELETE FROM semantic_knowledge WHERE key LIKE '%echo%';
DELETE FROM semantic_knowledge WHERE value LIKE '%repetition game%';
DELETE FROM semantic_knowledge WHERE value LIKE '%copies the assistant%';
DELETE FROM semantic_knowledge WHERE value LIKE '%mimics%' OR value LIKE '%mimick%';

-- Test behavior markers
DELETE FROM semantic_knowledge WHERE value LIKE '%consecutive times%' AND LENGTH(value) > 150;
DELETE FROM semantic_knowledge WHERE value LIKE '%iteration of%' AND LENGTH(value) > 150;
DELETE FROM semantic_knowledge WHERE key LIKE '%_loop' OR key LIKE '%_game';

-- Overly meta facts
DELETE FROM semantic_knowledge WHERE topic = 'inside_jokes' AND (value LIKE '%testing%' OR value LIKE '%repeatedly%');
DELETE FROM semantic_knowledge WHERE topic = 'communication_style' AND value LIKE '%echoes%';
DELETE FROM semantic_knowledge WHERE value LIKE '%iteration counter%' OR value LIKE '%consecutive repetition%';

SELECT 'Test artifacts removed' as status;

-- ============================================================================
-- STEP 4: TRIM LONG VALUES
-- ============================================================================

SELECT '✂️  Trimming long values (>200 chars)...' as status;

SELECT COUNT(*) || ' facts need trimming' as trim_count
FROM semantic_knowledge
WHERE LENGTH(value) > 200;

UPDATE semantic_knowledge
SET value = SUBSTR(value, 1, 200) || '...',
    updated_at = CURRENT_TIMESTAMP
WHERE LENGTH(value) > 200;

SELECT 'Long values trimmed' as status;

-- ============================================================================
-- STEP 5: REMOVE DUPLICATES
-- ============================================================================

SELECT '🔄 Removing duplicates...' as status;

-- Keep only the most recent fact for each (agent_id, user_id, topic, key) combination
DELETE FROM semantic_knowledge
WHERE id NOT IN (
    SELECT MAX(id)
    FROM semantic_knowledge
    GROUP BY agent_id, user_id, topic, key
);

SELECT 'Duplicates removed' as status;

-- ============================================================================
-- STEP 6: REMOVE INVALID FACTS
-- ============================================================================

SELECT '🚫 Removing invalid facts...' as status;

DELETE FROM semantic_knowledge WHERE value IS NULL OR value = '';
DELETE FROM semantic_knowledge WHERE key IS NULL OR key = '';
DELETE FROM semantic_knowledge WHERE topic IS NULL OR topic = '';
DELETE FROM semantic_knowledge WHERE LENGTH(TRIM(value)) = 0;
DELETE FROM semantic_knowledge WHERE confidence < 0 OR confidence > 1;

SELECT 'Invalid facts removed' as status;

-- ============================================================================
-- STEP 7: SHOW AFTER STATS
-- ============================================================================

SELECT '📊 AFTER CLEANUP:' as status;
SELECT COUNT(*) || ' total facts' as after_count FROM semantic_knowledge;

SELECT 'Facts by Agent:' as status;
SELECT agent_id, COUNT(*) as count
FROM semantic_knowledge
GROUP BY agent_id
ORDER BY count DESC;

SELECT 'Facts by Topic:' as status;
SELECT topic, COUNT(*) as count
FROM semantic_knowledge
GROUP BY topic
ORDER BY count DESC;

-- ============================================================================
-- STEP 8: VACUUM AND OPTIMIZE
-- ============================================================================

VACUUM;
ANALYZE semantic_knowledge;

SELECT '✅ Cleanup complete! Backup table: semantic_knowledge_backup_20260111' as final_status;
