"""
Phase 16: Project Memory Service

Handles project-level memory management:
- Semantic Memory: Conversation history with embeddings for semantic search
- Factual Memory: Learned facts with CRUD operations
- Integration with ChromaDB for vector storage
"""

import os
import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ProjectMemoryService:
    """
    Service for managing project-level memory.

    Provides granular control over:
    - Semantic memory (episodic/conversation history with embeddings)
    - Factual memory (learned facts about project context)
    - Bulk operations (clear, export)
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)
        self._chroma_client = None
        self._embedding_model = None

    # =========================================================================
    # ChromaDB Integration
    # =========================================================================

    def _get_chroma_client(self):
        """Lazy-load ChromaDB client."""
        if self._chroma_client is None:
            try:
                import chromadb
                from chromadb.config import Settings

                chroma_dir = os.environ.get("TSN_CHROMA_DIR", "/app/data/chroma")
                self._chroma_client = chromadb.PersistentClient(
                    path=chroma_dir,
                    settings=Settings(anonymized_telemetry=False)
                )
            except Exception as e:
                self.logger.error(f"Failed to initialize ChromaDB: {e}")
                raise
        return self._chroma_client

    def _get_embedding_model(self, model_name: str = "all-MiniLM-L6-v2"):
        """Get embedding model for semantic search."""
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer(model_name)
            except Exception as e:
                self.logger.error(f"Failed to load embedding model: {e}")
                raise
        return self._embedding_model

    def _get_project_collection(self, project_id: int, create_if_missing: bool = True):
        """Get or create ChromaDB collection for a project's semantic memory."""
        client = self._get_chroma_client()
        collection_name = f"project_{project_id}_memory"

        try:
            if create_if_missing:
                return client.get_or_create_collection(
                    name=collection_name,
                    metadata={"project_id": str(project_id), "type": "semantic_memory"}
                )
            else:
                return client.get_collection(name=collection_name)
        except Exception as e:
            if not create_if_missing:
                return None
            raise

    # =========================================================================
    # Semantic Memory CRUD
    # =========================================================================

    async def add_semantic_memory(
        self,
        project_id: int,
        sender_key: str,
        content: str,
        role: str,
        metadata: Optional[Dict] = None,
        store_embedding: bool = True
    ) -> Dict[str, Any]:
        """
        Add a message to project's semantic memory.

        Args:
            project_id: Project ID
            sender_key: User identifier
            content: Message content
            role: "user" or "assistant"
            metadata: Additional metadata
            store_embedding: Whether to store in ChromaDB
        """
        from models import ProjectSemanticMemory, Project

        try:
            # Get project config for embedding model
            project = self.db.query(Project).filter(Project.id == project_id).first()
            if not project:
                return {"status": "error", "error": "Project not found"}

            if not project.enable_semantic_memory:
                return {"status": "skipped", "reason": "Semantic memory disabled"}

            embedding_id = None
            if store_embedding:
                try:
                    # Generate embedding
                    model = self._get_embedding_model(project.kb_embedding_model or "all-MiniLM-L6-v2")
                    embedding = model.encode(content).tolist()

                    # Store in ChromaDB
                    collection = self._get_project_collection(project_id)
                    embedding_id = f"sem_{project_id}_{uuid.uuid4().hex[:8]}"

                    collection.add(
                        ids=[embedding_id],
                        embeddings=[embedding],
                        documents=[content],
                        metadatas=[{
                            "sender_key": sender_key,
                            "role": role,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            **(metadata or {})
                        }]
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to store embedding: {e}")

            # Store in database
            memory = ProjectSemanticMemory(
                project_id=project_id,
                sender_key=sender_key,
                content=content,
                role=role,
                embedding_id=embedding_id,
                metadata_json=metadata or {}
            )
            self.db.add(memory)
            self.db.commit()
            self.db.refresh(memory)

            return {
                "status": "success",
                "memory_id": memory.id,
                "embedding_id": embedding_id
            }
        except Exception as e:
            self.logger.error(f"Failed to add semantic memory: {e}", exc_info=True)
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    async def search_semantic_memory(
        self,
        project_id: int,
        query: str,
        sender_key: Optional[str] = None,
        limit: int = 10,
        min_similarity: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Search project's semantic memory using embeddings.

        Args:
            project_id: Project ID
            query: Search query
            sender_key: Optional filter by user
            limit: Max results
            min_similarity: Minimum similarity threshold (0.0-1.0)
        """
        from models import Project

        try:
            project = self.db.query(Project).filter(Project.id == project_id).first()
            if not project:
                return []

            # Use project-specific settings
            limit = min(limit, project.semantic_memory_results or 10)
            min_similarity = project.semantic_similarity_threshold or min_similarity

            collection = self._get_project_collection(project_id, create_if_missing=False)
            if collection is None:
                return []

            # Generate query embedding
            model = self._get_embedding_model(project.kb_embedding_model or "all-MiniLM-L6-v2")
            query_embedding = model.encode(query).tolist()

            # Build where clause
            where = None
            if sender_key:
                where = {"sender_key": sender_key}

            # Search ChromaDB
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where=where,
                include=["documents", "metadatas", "distances"]
            )

            if not results["documents"] or not results["documents"][0]:
                return []

            memories = []
            for i, doc in enumerate(results["documents"][0]):
                # Convert distance to similarity (ChromaDB uses L2 distance)
                distance = results["distances"][0][i] if results["distances"] else 0
                similarity = 1 / (1 + distance)  # Convert to 0-1 range

                if similarity >= min_similarity:
                    memories.append({
                        "content": doc,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "similarity": round(similarity, 3),
                        "embedding_id": results["ids"][0][i] if results["ids"] else None
                    })

            return memories
        except Exception as e:
            self.logger.error(f"Failed to search semantic memory: {e}", exc_info=True)
            return []

    async def list_semantic_memory(
        self,
        project_id: int,
        sender_key: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """List semantic memory records from database."""
        from models import ProjectSemanticMemory

        query = self.db.query(ProjectSemanticMemory).filter(
            ProjectSemanticMemory.project_id == project_id
        )

        if sender_key:
            query = query.filter(ProjectSemanticMemory.sender_key == sender_key)

        total = query.count()
        memories = query.order_by(
            ProjectSemanticMemory.timestamp.desc()
        ).offset(offset).limit(limit).all()

        return {
            "total": total,
            "memories": [
                {
                    "id": m.id,
                    "sender_key": m.sender_key,
                    "content": m.content,
                    "role": m.role,
                    "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                    "metadata": m.metadata_json
                }
                for m in memories
            ]
        }

    async def clear_semantic_memory(
        self,
        project_id: int,
        sender_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Clear semantic memory for a project.

        Args:
            project_id: Project ID
            sender_key: If provided, only clear memories for this user
        """
        from models import ProjectSemanticMemory

        try:
            # Clear from database
            query = self.db.query(ProjectSemanticMemory).filter(
                ProjectSemanticMemory.project_id == project_id
            )

            if sender_key:
                query = query.filter(ProjectSemanticMemory.sender_key == sender_key)

            # Get embedding IDs for ChromaDB cleanup
            memories = query.all()
            embedding_ids = [m.embedding_id for m in memories if m.embedding_id]
            deleted_count = query.delete()
            self.db.commit()

            # Clear from ChromaDB
            if embedding_ids:
                try:
                    collection = self._get_project_collection(project_id, create_if_missing=False)
                    if collection:
                        collection.delete(ids=embedding_ids)
                except Exception as e:
                    self.logger.warning(f"Failed to clear ChromaDB embeddings: {e}")

            return {
                "status": "success",
                "deleted_count": deleted_count
            }
        except Exception as e:
            self.logger.error(f"Failed to clear semantic memory: {e}", exc_info=True)
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    # =========================================================================
    # Factual Memory CRUD
    # =========================================================================

    async def add_fact(
        self,
        project_id: int,
        topic: str,
        key: str,
        value: str,
        sender_key: Optional[str] = None,
        confidence: float = 1.0,
        source: str = "manual"
    ) -> Dict[str, Any]:
        """
        Add or update a fact in project memory.

        Args:
            project_id: Project ID
            topic: Fact category (e.g., "company_info", "preferences")
            key: Fact key (e.g., "company_name", "favorite_color")
            value: Fact value
            sender_key: If provided, fact is user-specific
            confidence: Confidence score (0.0-1.0)
            source: "manual" | "conversation" | "document"
        """
        from models import ProjectFactMemory, Project

        try:
            project = self.db.query(Project).filter(Project.id == project_id).first()
            if not project:
                return {"status": "error", "error": "Project not found"}

            if not project.enable_factual_memory:
                return {"status": "skipped", "reason": "Factual memory disabled"}

            # Check if fact exists (upsert)
            existing = self.db.query(ProjectFactMemory).filter(
                ProjectFactMemory.project_id == project_id,
                ProjectFactMemory.topic == topic,
                ProjectFactMemory.key == key,
                ProjectFactMemory.sender_key == sender_key
            ).first()

            if existing:
                existing.value = value
                existing.confidence = confidence
                existing.source = source
                existing.updated_at = datetime.utcnow()
                self.db.commit()
                return {
                    "status": "success",
                    "fact_id": existing.id,
                    "action": "updated"
                }

            fact = ProjectFactMemory(
                project_id=project_id,
                sender_key=sender_key,
                topic=topic,
                key=key,
                value=value,
                confidence=confidence,
                source=source
            )
            self.db.add(fact)
            self.db.commit()
            self.db.refresh(fact)

            return {
                "status": "success",
                "fact_id": fact.id,
                "action": "created"
            }
        except Exception as e:
            self.logger.error(f"Failed to add fact: {e}", exc_info=True)
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    async def get_facts(
        self,
        project_id: int,
        sender_key: Optional[str] = None,
        topic: Optional[str] = None,
        include_project_wide: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get facts from project memory.

        Args:
            project_id: Project ID
            sender_key: If provided, get user-specific facts
            topic: If provided, filter by topic
            include_project_wide: Include facts with sender_key=None
        """
        from models import ProjectFactMemory
        from sqlalchemy import or_

        query = self.db.query(ProjectFactMemory).filter(
            ProjectFactMemory.project_id == project_id
        )

        # Filter by sender
        if sender_key:
            if include_project_wide:
                query = query.filter(or_(
                    ProjectFactMemory.sender_key == sender_key,
                    ProjectFactMemory.sender_key.is_(None)
                ))
            else:
                query = query.filter(ProjectFactMemory.sender_key == sender_key)
        elif not include_project_wide:
            query = query.filter(ProjectFactMemory.sender_key.is_(None))

        if topic:
            query = query.filter(ProjectFactMemory.topic == topic)

        facts = query.order_by(ProjectFactMemory.topic, ProjectFactMemory.key).all()

        return [
            {
                "id": f.id,
                "topic": f.topic,
                "key": f.key,
                "value": f.value,
                "sender_key": f.sender_key,
                "confidence": f.confidence,
                "source": f.source,
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "updated_at": f.updated_at.isoformat() if f.updated_at else None
            }
            for f in facts
        ]

    async def delete_fact(self, fact_id: int, project_id: int) -> Dict[str, Any]:
        """Delete a specific fact."""
        from models import ProjectFactMemory

        try:
            fact = self.db.query(ProjectFactMemory).filter(
                ProjectFactMemory.id == fact_id,
                ProjectFactMemory.project_id == project_id
            ).first()

            if not fact:
                return {"status": "error", "error": "Fact not found"}

            self.db.delete(fact)
            self.db.commit()

            return {"status": "success", "deleted_id": fact_id}
        except Exception as e:
            self.logger.error(f"Failed to delete fact: {e}", exc_info=True)
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    async def clear_facts(
        self,
        project_id: int,
        sender_key: Optional[str] = None,
        topic: Optional[str] = None
    ) -> Dict[str, Any]:
        """Clear facts from project memory."""
        from models import ProjectFactMemory

        try:
            query = self.db.query(ProjectFactMemory).filter(
                ProjectFactMemory.project_id == project_id
            )

            if sender_key:
                query = query.filter(ProjectFactMemory.sender_key == sender_key)

            if topic:
                query = query.filter(ProjectFactMemory.topic == topic)

            deleted_count = query.delete()
            self.db.commit()

            return {
                "status": "success",
                "deleted_count": deleted_count
            }
        except Exception as e:
            self.logger.error(f"Failed to clear facts: {e}", exc_info=True)
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    # =========================================================================
    # Memory Statistics & Export
    # =========================================================================

    async def get_memory_stats(self, project_id: int) -> Dict[str, Any]:
        """Get comprehensive memory statistics for a project."""
        from models import ProjectSemanticMemory, ProjectFactMemory, ProjectKnowledge, ProjectConversation
        from sqlalchemy import func

        semantic_count = self.db.query(ProjectSemanticMemory).filter(
            ProjectSemanticMemory.project_id == project_id
        ).count()

        fact_count = self.db.query(ProjectFactMemory).filter(
            ProjectFactMemory.project_id == project_id
        ).count()

        kb_count = self.db.query(ProjectKnowledge).filter(
            ProjectKnowledge.project_id == project_id
        ).count()

        conversation_count = self.db.query(ProjectConversation).filter(
            ProjectConversation.project_id == project_id,
            ProjectConversation.is_archived == False
        ).count()

        # Get unique senders in semantic memory
        unique_senders = self.db.query(
            func.count(func.distinct(ProjectSemanticMemory.sender_key))
        ).filter(
            ProjectSemanticMemory.project_id == project_id
        ).scalar() or 0

        # Get fact topics
        fact_topics = self.db.query(
            ProjectFactMemory.topic,
            func.count(ProjectFactMemory.id)
        ).filter(
            ProjectFactMemory.project_id == project_id
        ).group_by(ProjectFactMemory.topic).all()

        return {
            "semantic_memory_count": semantic_count,
            "fact_count": fact_count,
            "kb_document_count": kb_count,
            "conversation_count": conversation_count,
            "unique_users": unique_senders,
            "fact_topics": {topic: count for topic, count in fact_topics}
        }

    async def export_memory(
        self,
        project_id: int,
        include_semantic: bool = True,
        include_facts: bool = True
    ) -> Dict[str, Any]:
        """Export all project memory as JSON."""
        result = {
            "project_id": project_id,
            "exported_at": datetime.utcnow().isoformat() + "Z"
        }

        if include_semantic:
            semantic_data = await self.list_semantic_memory(project_id, limit=10000)
            result["semantic_memory"] = semantic_data["memories"]

        if include_facts:
            result["facts"] = await self.get_facts(project_id)

        return result

    # =========================================================================
    # Combined Memory Retrieval (for AI context)
    # =========================================================================

    async def get_context_for_query(
        self,
        project_id: int,
        query: str,
        sender_key: str,
        include_facts: bool = True,
        include_semantic: bool = True,
        max_semantic_results: int = 5
    ) -> Dict[str, Any]:
        """
        Get combined context for a user query.
        Used when processing messages to build AI context.

        Returns facts and relevant semantic memories for the project.
        """
        context = {
            "project_id": project_id,
            "facts": [],
            "semantic_memories": []
        }

        if include_facts:
            context["facts"] = await self.get_facts(
                project_id,
                sender_key=sender_key,
                include_project_wide=True
            )

        if include_semantic:
            context["semantic_memories"] = await self.search_semantic_memory(
                project_id,
                query=query,
                limit=max_semantic_results
            )

        return context
