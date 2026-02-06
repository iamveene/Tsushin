"""
Knowledge Service - Phase 4.8 Week 3

Service layer for managing semantic knowledge (Layer 3 of memory architecture).
Provides high-level interface for storing, querying, and managing learned facts.

Key features:
- Query facts by user, topic, or key
- Bulk fact operations
- Knowledge statistics and analytics
- Fact validation and merging
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from models import SemanticKnowledge


class KnowledgeService:
    """
    High-level service for managing semantic knowledge.

    Provides:
    - Fact CRUD operations
    - Query interface for facts
    - Knowledge statistics
    - Fact merging and validation
    """

    def __init__(self, db_session: Session):
        """
        Initialize knowledge service.

        Args:
            db_session: Database session
        """
        self.logger = logging.getLogger(__name__)
        self.db = db_session

    def get_user_facts(
        self,
        agent_id: int,
        user_id: str,
        topic: Optional[str] = None,
        min_confidence: float = 0.0
    ) -> List[Dict]:
        """
        Get all facts about a user.

        Args:
            agent_id: Agent ID
            user_id: User identifier
            topic: Optional topic filter
            min_confidence: Minimum confidence threshold

        Returns:
            List of fact dictionaries
        """
        try:
            query = self.db.query(SemanticKnowledge).filter(
                SemanticKnowledge.agent_id == agent_id,
                SemanticKnowledge.user_id == user_id,
                SemanticKnowledge.confidence >= min_confidence
            )

            if topic:
                query = query.filter(SemanticKnowledge.topic == topic)

            facts = query.order_by(
                SemanticKnowledge.updated_at.desc(),
                SemanticKnowledge.topic,
                SemanticKnowledge.key
            ).all()

            return [self._fact_to_dict(f) for f in facts]

        except Exception as e:
            self.logger.error(f"Failed to get user facts: {e}")
            return []

    def get_fact(
        self,
        agent_id: int,
        user_id: str,
        topic: str,
        key: str
    ) -> Optional[Dict]:
        """
        Get a specific fact.

        Args:
            agent_id: Agent ID
            user_id: User identifier
            topic: Fact topic
            key: Fact key

        Returns:
            Fact dictionary or None
        """
        try:
            fact = self.db.query(SemanticKnowledge).filter(
                SemanticKnowledge.agent_id == agent_id,
                SemanticKnowledge.user_id == user_id,
                SemanticKnowledge.topic == topic,
                SemanticKnowledge.key == key
            ).first()

            return self._fact_to_dict(fact) if fact else None

        except Exception as e:
            self.logger.error(f"Failed to get fact: {e}")
            return None

    def store_fact(
        self,
        agent_id: int,
        user_id: str,
        topic: str,
        key: str,
        value: str,
        confidence: float = 1.0
    ) -> bool:
        """
        Store or update a fact.

        Args:
            agent_id: Agent ID
            user_id: User identifier
            topic: Fact topic
            key: Fact key
            value: Fact value
            confidence: Confidence score (0.0-1.0)

        Returns:
            True if successful
        """
        try:
            # Validate confidence
            confidence = max(0.0, min(1.0, confidence))

            # Check if fact exists
            existing = self.db.query(SemanticKnowledge).filter(
                SemanticKnowledge.agent_id == agent_id,
                SemanticKnowledge.user_id == user_id,
                SemanticKnowledge.topic == topic,
                SemanticKnowledge.key == key
            ).first()

            if existing:
                # Update existing fact
                existing.value = value
                existing.confidence = confidence
                existing.updated_at = datetime.utcnow()
                self.logger.debug(f"Updated fact: {topic}.{key} = {value}")
            else:
                # Create new fact
                new_fact = SemanticKnowledge(
                    agent_id=agent_id,
                    user_id=user_id,
                    topic=topic,
                    key=key,
                    value=value,
                    confidence=confidence
                )
                self.db.add(new_fact)
                self.logger.debug(f"Created fact: {topic}.{key} = {value}")

            self.db.commit()
            return True

        except Exception as e:
            self.logger.error(f"Failed to store fact: {e}")
            self.db.rollback()
            return False

    def delete_fact(
        self,
        agent_id: int,
        user_id: str,
        topic: str,
        key: str
    ) -> bool:
        """
        Delete a specific fact.

        Args:
            agent_id: Agent ID
            user_id: User identifier
            topic: Fact topic
            key: Fact key

        Returns:
            True if deleted
        """
        try:
            deleted = self.db.query(SemanticKnowledge).filter(
                SemanticKnowledge.agent_id == agent_id,
                SemanticKnowledge.user_id == user_id,
                SemanticKnowledge.topic == topic,
                SemanticKnowledge.key == key
            ).delete()

            self.db.commit()

            if deleted:
                self.logger.info(f"Deleted fact: {topic}.{key}")
                return True
            else:
                self.logger.warning(f"Fact not found: {topic}.{key}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to delete fact: {e}")
            self.db.rollback()
            return False

    def delete_user_facts(
        self,
        agent_id: int,
        user_id: str,
        topic: Optional[str] = None
    ) -> int:
        """
        Delete all facts for a user.

        Args:
            agent_id: Agent ID
            user_id: User identifier
            topic: Optional topic filter

        Returns:
            Number of facts deleted
        """
        try:
            query = self.db.query(SemanticKnowledge).filter(
                SemanticKnowledge.agent_id == agent_id,
                SemanticKnowledge.user_id == user_id
            )

            if topic:
                query = query.filter(SemanticKnowledge.topic == topic)

            deleted = query.delete()
            self.db.commit()

            self.logger.info(f"Deleted {deleted} facts for user {user_id}")
            return deleted

        except Exception as e:
            self.logger.error(f"Failed to delete user facts: {e}")
            self.db.rollback()
            return 0

    def search_facts(
        self,
        agent_id: int,
        search_query: str,
        user_id: Optional[str] = None,
        topic: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """
        Search facts by key or value content.

        Args:
            agent_id: Agent ID
            search_query: Search term
            user_id: Optional user filter
            topic: Optional topic filter
            limit: Maximum results

        Returns:
            List of matching facts
        """
        try:
            query = self.db.query(SemanticKnowledge).filter(
                SemanticKnowledge.agent_id == agent_id
            )

            if user_id:
                query = query.filter(SemanticKnowledge.user_id == user_id)

            if topic:
                query = query.filter(SemanticKnowledge.topic == topic)

            # Search in key or value
            search_term = f"%{search_query}%"
            query = query.filter(
                or_(
                    SemanticKnowledge.key.ilike(search_term),
                    SemanticKnowledge.value.ilike(search_term)
                )
            )

            facts = query.order_by(
                desc(SemanticKnowledge.confidence)
            ).limit(limit).all()

            return [self._fact_to_dict(f) for f in facts]

        except Exception as e:
            self.logger.error(f"Failed to search facts: {e}")
            return []

    def get_statistics(
        self,
        agent_id: int,
        user_id: Optional[str] = None
    ) -> Dict:
        """
        Get knowledge statistics.

        Args:
            agent_id: Agent ID
            user_id: Optional user filter

        Returns:
            Statistics dictionary
        """
        try:
            query = self.db.query(SemanticKnowledge).filter(
                SemanticKnowledge.agent_id == agent_id
            )

            if user_id:
                query = query.filter(SemanticKnowledge.user_id == user_id)

            all_facts = query.all()

            if not all_facts:
                return {
                    'total_facts': 0,
                    'unique_users': 0,
                    'topics': {},
                    'avg_confidence': 0.0,
                    'recent_facts': 0
                }

            # Calculate statistics
            topics = {}
            confidences = []
            users = set()
            now = datetime.utcnow()
            recent_cutoff = now - timedelta(days=7)
            recent_count = 0

            for fact in all_facts:
                # Topics
                if fact.topic not in topics:
                    topics[fact.topic] = 0
                topics[fact.topic] += 1

                # Confidence
                confidences.append(fact.confidence)

                # Users
                users.add(fact.user_id)

                # Recent facts
                if fact.learned_at and fact.learned_at >= recent_cutoff:
                    recent_count += 1

            return {
                'total_facts': len(all_facts),
                'unique_users': len(users),
                'topics': topics,
                'avg_confidence': sum(confidences) / len(confidences),
                'recent_facts': recent_count
            }

        except Exception as e:
            self.logger.error(f"Failed to get statistics: {e}")
            return {
                'total_facts': 0,
                'unique_users': 0,
                'topics': {},
                'avg_confidence': 0.0,
                'recent_facts': 0,
                'error': str(e)
            }

    def get_topics(self, agent_id: int) -> List[str]:
        """
        Get list of all topics used by this agent.

        Args:
            agent_id: Agent ID

        Returns:
            List of topic names
        """
        try:
            results = self.db.query(SemanticKnowledge.topic).filter(
                SemanticKnowledge.agent_id == agent_id
            ).distinct().all()

            return [r[0] for r in results]

        except Exception as e:
            self.logger.error(f"Failed to get topics: {e}")
            return []

    def _fact_to_dict(self, fact: SemanticKnowledge) -> Dict:
        """
        Convert fact model to dictionary.

        Args:
            fact: SemanticKnowledge model instance

        Returns:
            Dictionary representation
        """
        return {
            'id': fact.id,
            'agent_id': fact.agent_id,
            'user_id': fact.user_id,
            'topic': fact.topic,
            'key': fact.key,
            'value': fact.value,
            'confidence': fact.confidence,
            'learned_at': fact.learned_at.isoformat() if fact.learned_at else None,
            'updated_at': fact.updated_at.isoformat() if fact.updated_at else None
        }

    def format_communication_style_prompt(
        self,
        agent_id: int,
        user_id: str,
        min_confidence: float = 0.7
    ) -> Optional[str]:
        """
        Format communication style facts into a personality adaptation prompt.
        Used by adaptive_personality skill to inject style context into agent.

        Args:
            agent_id: Agent ID
            user_id: User identifier
            min_confidence: Minimum confidence for included facts

        Returns:
            Formatted prompt string or None if no style facts
        """
        try:
            # Get style-related facts
            style_topics = ['communication_style', 'inside_jokes', 'linguistic_patterns']
            style_facts = []

            for topic in style_topics:
                facts = self.get_user_facts(
                    agent_id=agent_id,
                    user_id=user_id,
                    topic=topic,
                    min_confidence=min_confidence
                )
                if facts:
                    style_facts.extend(facts)

            if not style_facts:
                return None

            # Build prompt
            lines = ["=== PERSONALITY ADAPTATION CONTEXT ==="]
            lines.append("Adapt your communication style to match this sender:")
            lines.append("")

            # Group by topic
            by_topic = {}
            for fact in style_facts:
                topic = fact['topic']
                if topic not in by_topic:
                    by_topic[topic] = []
                by_topic[topic].append(fact)

            # Format each topic
            if 'communication_style' in by_topic:
                lines.append("Communication Style:")
                for fact in by_topic['communication_style']:
                    lines.append(f"  • {fact['key']}: {fact['value']}")
                lines.append("")

            if 'inside_jokes' in by_topic:
                lines.append("Inside Jokes & References:")
                for fact in by_topic['inside_jokes']:
                    lines.append(f"  • {fact['value']}")
                lines.append("")

            if 'linguistic_patterns' in by_topic:
                lines.append("Linguistic Patterns:")
                for fact in by_topic['linguistic_patterns']:
                    lines.append(f"  • {fact['key']}: {fact['value']}")
                lines.append("")

            lines.append("Mirror these patterns naturally in your responses when appropriate.")
            lines.append("=" * 50)

            return "\n".join(lines)

        except Exception as e:
            self.logger.error(f"Failed to format communication style prompt: {e}")
            return None
