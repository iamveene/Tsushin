"""
Shared Memory Pool - Phase 4.8 Week 4

Cross-agent knowledge sharing with permission-based access control.
Allows agents to share facts and knowledge with other agents in a controlled manner.

Key features:
- Permission-based access (public, specific agents, private)
- Topic-based organization
- Confidence-based filtering
- Audit trail for shared knowledge
- Vector search across shared memories
"""

import logging
from typing import Dict, List, Optional, Set
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from models import SharedMemory, Agent


class SharedMemoryPool:
    """
    Manages cross-agent shared knowledge with permission-based access.

    Access Levels:
    - public: All agents can access
    - restricted: Only specified agents can access
    - private: Only the sharing agent can access (for future sharing)

    Knowledge Types:
    - facts: Verified facts about users/world
    - context: General context that may be useful
    - insights: Derived insights from conversations
    """

    def __init__(self, db_session: Session):
        """
        Initialize shared memory pool.

        Args:
            db_session: Database session
        """
        self.logger = logging.getLogger(__name__)
        self.db = db_session

    def share_knowledge(
        self,
        agent_id: int,
        content: str,
        topic: Optional[str] = None,
        access_level: str = "public",
        accessible_to: Optional[List[int]] = None,
        metadata: Optional[Dict] = None,
        tenant_id: Optional[str] = None
    ) -> bool:
        """
        Share knowledge to the pool.

        Args:
            agent_id: Agent sharing the knowledge
            content: Knowledge content
            topic: Optional topic/category
            access_level: "public", "restricted", or "private"
            accessible_to: List of agent IDs (for restricted access)
            metadata: Additional metadata (source, confidence, etc.)
            tenant_id: Tenant ID for multi-tenancy (CRIT-010 security fix)

        Returns:
            True if successful
        """
        try:
            # Validate access level
            if access_level not in ["public", "restricted", "private"]:
                self.logger.error(f"Invalid access level: {access_level}")
                return False

            # Validate agent exists
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                self.logger.error(f"Agent {agent_id} not found")
                return False

            # CRIT-010: Use agent's tenant_id if not provided
            if tenant_id is None:
                tenant_id = agent.tenant_id

            # Prepare accessible_to list
            if access_level == "restricted" and accessible_to is None:
                self.logger.warning("Restricted access requires accessible_to list")
                accessible_to = []
            elif access_level != "restricted":
                accessible_to = []  # Ignore for public/private

            # Create shared memory entry with tenant_id
            shared = SharedMemory(
                content=content,
                topic=topic,
                shared_by_agent=agent_id,
                accessible_to=accessible_to,
                meta_data=metadata or {},
                tenant_id=tenant_id
            )

            # Add access level to metadata
            shared.meta_data["access_level"] = access_level

            self.db.add(shared)
            self.db.commit()

            self.logger.info(
                f"Agent {agent_id} shared knowledge: {content[:50]}... "
                f"(access: {access_level})"
            )

            return True

        except Exception as e:
            self.logger.error(f"Failed to share knowledge: {e}")
            self.db.rollback()
            return False

    def get_accessible_knowledge(
        self,
        agent_id: int,
        topic: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 20,
        tenant_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Get knowledge accessible to a specific agent.

        Args:
            agent_id: Agent requesting knowledge
            topic: Optional topic filter
            min_confidence: Minimum confidence threshold
            limit: Maximum results
            tenant_id: Tenant ID for multi-tenancy filter (CRIT-010 security fix)

        Returns:
            List of knowledge items
        """
        try:
            # Build query for accessible knowledge
            query = self.db.query(SharedMemory)

            # CRIT-010: Apply tenant isolation filter
            if tenant_id:
                query = query.filter(SharedMemory.tenant_id == tenant_id)

            # Access control:
            # 1. Public knowledge (accessible_to is empty - will filter access_level after query)
            # 2. Knowledge shared by this agent
            # 3. Knowledge where agent is in accessible_to list
            # Note: SQLite doesn't support JSON field access in WHERE clauses like PostgreSQL
            # so we filter access_level="public" in Python after the query
            query = query.filter(
                or_(
                    SharedMemory.accessible_to == [],
                    SharedMemory.shared_by_agent == agent_id,
                    SharedMemory.accessible_to.contains([agent_id])
                )
            )

            # Apply topic filter
            if topic:
                query = query.filter(SharedMemory.topic == topic)

            # Apply confidence filter (if in metadata)
            # Note: We can't directly filter JSON in SQLite, so we'll filter after

            # Order by most recent
            query = query.order_by(desc(SharedMemory.created_at))

            # Execute query
            results = query.limit(limit * 2).all()  # Get extra for filtering

            # Convert to dict and apply confidence + access_level filters
            knowledge = []
            for item in results:
                # Check access level for items with empty accessible_to (public knowledge)
                if item.accessible_to == []:
                    access_level = item.meta_data.get("access_level", "private")
                    # Only include if access_level is "public" OR it's shared by this agent
                    if access_level != "public" and item.shared_by_agent != agent_id:
                        continue

                # Check confidence
                confidence = item.meta_data.get("confidence", 1.0)
                if confidence >= min_confidence:
                    knowledge.append(self._to_dict(item))

                if len(knowledge) >= limit:
                    break

            self.logger.info(
                f"Retrieved {len(knowledge)} knowledge items for agent {agent_id}"
            )

            return knowledge

        except Exception as e:
            self.logger.error(f"Failed to get accessible knowledge: {e}")
            return []

    def search_shared_knowledge(
        self,
        agent_id: int,
        query: str,
        topic: Optional[str] = None,
        limit: int = 10,
        tenant_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Search shared knowledge accessible to an agent.

        Args:
            agent_id: Agent requesting search
            query: Search query
            topic: Optional topic filter
            limit: Maximum results
            tenant_id: Tenant ID for multi-tenancy filter (CRIT-010 security fix)

        Returns:
            List of matching knowledge items
        """
        try:
            # Get accessible knowledge first (with tenant filter)
            accessible = self.get_accessible_knowledge(
                agent_id=agent_id,
                topic=topic,
                limit=100,  # Get more for searching
                tenant_id=tenant_id
            )

            # Filter by search query (simple text matching)
            search_term = query.lower()
            matches = []

            for item in accessible:
                content = item["content"].lower()
                topic_str = (item.get("topic") or "").lower()

                if search_term in content or search_term in topic_str:
                    matches.append(item)

                if len(matches) >= limit:
                    break

            self.logger.info(
                f"Search found {len(matches)} matches for query: {query}"
            )

            return matches

        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            return []

    def update_shared_knowledge(
        self,
        knowledge_id: int,
        agent_id: int,
        content: Optional[str] = None,
        topic: Optional[str] = None,
        accessible_to: Optional[List[int]] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Update shared knowledge (only by sharing agent).

        Args:
            knowledge_id: Knowledge ID
            agent_id: Agent requesting update
            content: New content (optional)
            topic: New topic (optional)
            accessible_to: New access list (optional)
            metadata: New metadata (optional)

        Returns:
            True if successful
        """
        try:
            # Find knowledge
            knowledge = self.db.query(SharedMemory).filter(
                SharedMemory.id == knowledge_id
            ).first()

            if not knowledge:
                self.logger.warning(f"Knowledge {knowledge_id} not found")
                return False

            # Verify ownership
            if knowledge.shared_by_agent != agent_id:
                self.logger.warning(
                    f"Agent {agent_id} cannot update knowledge {knowledge_id} "
                    f"(owned by agent {knowledge.shared_by_agent})"
                )
                return False

            # Update fields
            if content is not None:
                knowledge.content = content
            if topic is not None:
                knowledge.topic = topic
            if accessible_to is not None:
                knowledge.accessible_to = accessible_to
            if metadata is not None:
                knowledge.meta_data.update(metadata)

            knowledge.updated_at = datetime.utcnow()

            self.db.commit()

            self.logger.info(f"Updated shared knowledge {knowledge_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to update knowledge: {e}")
            self.db.rollback()
            return False

    def delete_shared_knowledge(
        self,
        knowledge_id: int,
        agent_id: int
    ) -> bool:
        """
        Delete shared knowledge (only by sharing agent).

        Args:
            knowledge_id: Knowledge ID
            agent_id: Agent requesting deletion

        Returns:
            True if successful
        """
        try:
            # Find knowledge
            knowledge = self.db.query(SharedMemory).filter(
                SharedMemory.id == knowledge_id
            ).first()

            if not knowledge:
                self.logger.warning(f"Knowledge {knowledge_id} not found")
                return False

            # Verify ownership
            if knowledge.shared_by_agent != agent_id:
                self.logger.warning(
                    f"Agent {agent_id} cannot delete knowledge {knowledge_id}"
                )
                return False

            self.db.delete(knowledge)
            self.db.commit()

            self.logger.info(f"Deleted shared knowledge {knowledge_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to delete knowledge: {e}")
            self.db.rollback()
            return False

    def get_statistics(self, agent_id: Optional[int] = None, tenant_id: Optional[str] = None) -> Dict:
        """
        Get shared memory statistics.

        Args:
            agent_id: Optional agent filter
            tenant_id: Tenant ID for multi-tenancy filter (CRIT-010 security fix)

        Returns:
            Statistics dictionary
        """
        try:
            query = self.db.query(SharedMemory)

            # CRIT-010: Apply tenant isolation filter
            if tenant_id:
                query = query.filter(SharedMemory.tenant_id == tenant_id)

            if agent_id:
                # Stats for specific agent (what they shared)
                query = query.filter(SharedMemory.shared_by_agent == agent_id)

            all_knowledge = query.all()

            if not all_knowledge:
                return {
                    "total_shared": 0,
                    "by_topic": {},
                    "by_access_level": {},
                    "sharing_agents": 0
                }

            # Calculate statistics
            topics = {}
            access_levels = {}
            sharing_agents = set()

            for item in all_knowledge:
                # Topics
                topic = item.topic or "uncategorized"
                topics[topic] = topics.get(topic, 0) + 1

                # Access levels
                access_level = item.meta_data.get("access_level", "unknown")
                access_levels[access_level] = access_levels.get(access_level, 0) + 1

                # Sharing agents
                sharing_agents.add(item.shared_by_agent)

            return {
                "total_shared": len(all_knowledge),
                "by_topic": topics,
                "by_access_level": access_levels,
                "sharing_agents": len(sharing_agents)
            }

        except Exception as e:
            self.logger.error(f"Failed to get statistics: {e}")
            return {
                "total_shared": 0,
                "by_topic": {},
                "by_access_level": {},
                "sharing_agents": 0,
                "error": str(e)
            }

    def get_topics(self, agent_id: Optional[int] = None, tenant_id: Optional[str] = None) -> List[str]:
        """
        Get list of all topics in shared memory.

        Args:
            agent_id: Optional agent filter (accessible topics only)
            tenant_id: Tenant ID for multi-tenancy filter (CRIT-010 security fix)

        Returns:
            List of topic names
        """
        try:
            if agent_id:
                # Get accessible knowledge topics (with tenant filter)
                accessible = self.get_accessible_knowledge(
                    agent_id=agent_id,
                    limit=1000,
                    tenant_id=tenant_id
                )
                topics = set(
                    item.get("topic") for item in accessible
                    if item.get("topic")
                )
            else:
                # Get all topics (with tenant filter)
                query = self.db.query(SharedMemory.topic).filter(
                    SharedMemory.topic.isnot(None)
                )
                # CRIT-010: Apply tenant isolation filter
                if tenant_id:
                    query = query.filter(SharedMemory.tenant_id == tenant_id)
                results = query.distinct().all()
                topics = set(r[0] for r in results)

            return sorted(list(topics))

        except Exception as e:
            self.logger.error(f"Failed to get topics: {e}")
            return []

    def _to_dict(self, item: SharedMemory) -> Dict:
        """
        Convert SharedMemory model to dictionary.

        Args:
            item: SharedMemory model instance

        Returns:
            Dictionary representation
        """
        return {
            "id": item.id,
            "content": item.content,
            "topic": item.topic,
            "shared_by_agent": item.shared_by_agent,
            "accessible_to": item.accessible_to,
            "metadata": item.meta_data,
            "access_level": item.meta_data.get("access_level", "unknown"),
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None
        }
