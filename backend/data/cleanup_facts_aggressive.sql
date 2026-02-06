-- Aggressive Fact Cleanup - Remove remaining garbage
-- Date: 2026-01-11
-- Purpose: Second pass to remove more subtle garbage facts

-- Backup already exists from previous cleanup

SELECT '🧹 AGGRESSIVE CLEANUP - Removing remaining garbage...' as status;

-- ============================================================================
-- Remove meta-conversational facts (facts about the conversation itself)
-- ============================================================================

DELETE FROM semantic_knowledge
WHERE value LIKE '%the assistant%'
  AND (value LIKE '%messages%' OR value LIKE '%conversation%')
  AND LENGTH(value) > 100;

DELETE FROM semantic_knowledge
WHERE value LIKE '%repeatedly sends%'
   OR value LIKE '%copies and pastes%'
   OR value LIKE '%replicates%'
   OR value LIKE '%mimicry%';

DELETE FROM semantic_knowledge
WHERE key LIKE '%formality_mimicry%'
   OR key LIKE '%message_structure%'
   OR key LIKE '%persistent_interaction%';

-- ============================================================================
-- Remove overly detailed instruction facts (keep only concise ones)
-- ============================================================================

DELETE FROM semantic_knowledge
WHERE topic = 'instructions'
  AND key LIKE '%assistant_%'
  AND LENGTH(value) > 150;

-- ============================================================================
-- Remove historical facts that are just test artifacts
-- ============================================================================

DELETE FROM semantic_knowledge
WHERE topic = 'history'
  AND value LIKE '%assistant characterized%';

DELETE FROM semantic_knowledge
WHERE topic = 'goals'
  AND value LIKE '%test%'
  AND value LIKE '%assistant%';

-- ============================================================================
-- Show results
-- ============================================================================

SELECT '✅ Aggressive cleanup complete' as status;
SELECT COUNT(*) || ' total facts remaining' as final_count FROM semantic_knowledge;

SELECT 'Facts by Agent (Top 10):' as status;
SELECT agent_id, COUNT(*) as count
FROM semantic_knowledge
GROUP BY agent_id
ORDER BY count DESC
LIMIT 10;

VACUUM;
