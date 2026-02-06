"""
Phase 14.4: Project Service
Phase 15: Skill Projects - Updated for tenant-wide access

Handles project management, knowledge bases, and conversations.
Projects are now tenant-scoped (not user-owned) with agent-based access control.
"""

import os
import logging
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ProjectService:
    """
    Service for managing projects in Playground.

    Phase 15 Update: Projects are now tenant-scoped with the following changes:
    - Projects are accessible to all users within a tenant
    - Access control is managed via AgentProjectAccess (which agents can use which projects)
    - creator_id tracks who created the project (for audit)
    - user_id is deprecated but kept for backward compatibility

    Projects provide:
    - Isolated knowledge bases
    - Multiple conversations with history
    - Custom instructions/system prompts
    - Tool configuration
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

    # =========================================================================
    # Project CRUD
    # =========================================================================

    async def create_project(
        self,
        tenant_id: str,
        user_id: int,
        name: str,
        description: Optional[str] = None,
        icon: str = "folder",
        color: str = "blue",
        agent_id: Optional[int] = None,
        system_prompt_override: Optional[str] = None,
        agent_ids: Optional[List[int]] = None,
        # Phase 16: KB Configuration
        kb_chunk_size: int = 500,
        kb_chunk_overlap: int = 50,
        kb_embedding_model: str = "all-MiniLM-L6-v2",
        # Phase 16: Memory Configuration
        enable_semantic_memory: bool = True,
        semantic_memory_results: int = 10,
        semantic_similarity_threshold: float = 0.5,
        enable_factual_memory: bool = True,
        factual_extraction_threshold: int = 5
    ) -> Dict[str, Any]:
        """
        Create a new project.

        Phase 15: Projects are now tenant-scoped. user_id becomes creator_id for audit.
        Phase 16: Added KB and memory configuration parameters.

        Args:
            tenant_id: Tenant identifier
            user_id: User creating the project (stored as creator_id)
            name: Project name
            description: Optional description
            icon: Icon emoji or name
            color: Color theme
            agent_id: Default agent for the project
            system_prompt_override: Custom system prompt
            agent_ids: List of agent IDs to grant access (optional)
            kb_chunk_size: Characters per chunk for KB
            kb_chunk_overlap: Overlap between chunks
            kb_embedding_model: Embedding model for semantic search
            enable_semantic_memory: Enable episodic memory
            semantic_memory_results: Max results from semantic search
            semantic_similarity_threshold: Min similarity score (0.0-1.0)
            enable_factual_memory: Enable factual extraction
            factual_extraction_threshold: Messages before extraction
        """
        from models import Project, Agent, AgentProjectAccess

        try:
            project = Project(
                tenant_id=tenant_id,
                user_id=user_id,  # Deprecated, kept for backward compat
                creator_id=user_id,  # Phase 15: Creator tracking
                name=name,
                description=description,
                icon=icon,
                color=color,
                agent_id=agent_id,
                system_prompt_override=system_prompt_override,
                # Phase 16: KB Configuration
                kb_chunk_size=kb_chunk_size,
                kb_chunk_overlap=kb_chunk_overlap,
                kb_embedding_model=kb_embedding_model,
                # Phase 16: Memory Configuration
                enable_semantic_memory=enable_semantic_memory,
                semantic_memory_results=semantic_memory_results,
                semantic_similarity_threshold=semantic_similarity_threshold,
                enable_factual_memory=enable_factual_memory,
                factual_extraction_threshold=factual_extraction_threshold
            )
            self.db.add(project)
            self.db.flush()  # Get project ID

            # Phase 15: Grant agent access
            if agent_ids:
                # Grant access to specified agents
                for aid in agent_ids:
                    access = AgentProjectAccess(
                        agent_id=aid,
                        project_id=project.id,
                        can_write=True
                    )
                    self.db.add(access)
            else:
                # Grant access to default agent if no agents specified
                default_agent = self.db.query(Agent).filter(
                    Agent.is_default == True,
                    Agent.tenant_id == tenant_id
                ).first()

                if not default_agent:
                    # Fall back to any active agent
                    default_agent = self.db.query(Agent).filter(
                        Agent.is_active == True,
                        Agent.tenant_id == tenant_id
                    ).first()

                if default_agent:
                    access = AgentProjectAccess(
                        agent_id=default_agent.id,
                        project_id=project.id,
                        can_write=True
                    )
                    self.db.add(access)

            # If a specific agent_id is provided, ensure it has access
            if agent_id and (not agent_ids or agent_id not in agent_ids):
                existing = self.db.query(AgentProjectAccess).filter(
                    AgentProjectAccess.agent_id == agent_id,
                    AgentProjectAccess.project_id == project.id
                ).first()
                if not existing:
                    access = AgentProjectAccess(
                        agent_id=agent_id,
                        project_id=project.id,
                        can_write=True
                    )
                    self.db.add(access)

            self.db.commit()
            self.db.refresh(project)

            return {
                "status": "success",
                "project": self._project_to_dict(project)
            }
        except Exception as e:
            self.logger.error(f"Failed to create project: {e}", exc_info=True)
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    async def get_projects(
        self,
        tenant_id: str,
        user_id: int = None,
        include_archived: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all projects in a tenant.

        Phase 15: Projects are now tenant-scoped. All users in tenant can see all projects.
        user_id parameter is kept for backward compatibility but no longer filters results.
        """
        from models import Project, ProjectConversation, ProjectKnowledge

        # Phase 15: Tenant-wide access - all users see all projects in tenant
        query = self.db.query(Project).filter(
            Project.tenant_id == tenant_id
        )

        if not include_archived:
            query = query.filter(Project.is_archived == False)

        projects = query.order_by(Project.updated_at.desc()).all()

        result = []
        for project in projects:
            project_dict = self._project_to_dict(project)

            # Get counts
            project_dict["conversation_count"] = self.db.query(ProjectConversation).filter(
                ProjectConversation.project_id == project.id,
                ProjectConversation.is_archived == False
            ).count()

            project_dict["document_count"] = self.db.query(ProjectKnowledge).filter(
                ProjectKnowledge.project_id == project.id
            ).count()

            result.append(project_dict)

        return result

    async def get_accessible_projects(
        self,
        tenant_id: str,
        agent_id: int,
        include_archived: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Phase 15: Get projects accessible to a specific agent.

        Args:
            tenant_id: Tenant identifier
            agent_id: Agent ID to filter by access
            include_archived: Include archived projects

        Returns:
            List of project dicts that the agent can access
        """
        from models import Project, ProjectConversation, ProjectKnowledge, AgentProjectAccess

        query = self.db.query(Project).join(
            AgentProjectAccess,
            AgentProjectAccess.project_id == Project.id
        ).filter(
            AgentProjectAccess.agent_id == agent_id,
            Project.tenant_id == tenant_id
        )

        if not include_archived:
            query = query.filter(Project.is_archived == False)

        projects = query.order_by(Project.updated_at.desc()).all()

        result = []
        for project in projects:
            project_dict = self._project_to_dict(project)

            project_dict["conversation_count"] = self.db.query(ProjectConversation).filter(
                ProjectConversation.project_id == project.id,
                ProjectConversation.is_archived == False
            ).count()

            project_dict["document_count"] = self.db.query(ProjectKnowledge).filter(
                ProjectKnowledge.project_id == project.id
            ).count()

            result.append(project_dict)

        return result

    async def get_project_by_name(
        self,
        tenant_id: str,
        name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Phase 15: Get a project by name (case-insensitive).

        Used by command handlers to look up projects by name.

        Args:
            tenant_id: Tenant identifier
            name: Project name (case-insensitive match)

        Returns:
            Project dict or None if not found
        """
        from models import Project

        project = self.db.query(Project).filter(
            Project.tenant_id == tenant_id,
            Project.name.ilike(name.strip()),
            Project.is_archived == False
        ).first()

        if not project:
            return None

        return self._project_to_dict(project)

    async def get_project(
        self,
        tenant_id: str,
        user_id: int = None,
        project_id: int = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific project.

        Phase 15: Projects are tenant-scoped. user_id is kept for backward compatibility.
        """
        from models import Project

        # Phase 15: Tenant-wide access
        project = self.db.query(Project).filter(
            Project.id == project_id,
            Project.tenant_id == tenant_id
        ).first()

        if not project:
            return None

        return self._project_to_dict(project)

    async def update_project(
        self,
        tenant_id: str,
        user_id: int = None,
        project_id: int = None,
        updates: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Update a project.

        Phase 15: Projects are tenant-scoped. user_id kept for backward compat.
        """
        from models import Project, AgentProjectAccess

        # Phase 15: Tenant-wide access
        project = self.db.query(Project).filter(
            Project.id == project_id,
            Project.tenant_id == tenant_id
        ).first()

        if not project:
            return {"status": "error", "error": "Project not found"}

        allowed_fields = [
            'name', 'description', 'icon', 'color', 'agent_id',
            'system_prompt_override', 'enabled_tools', 'enabled_sandboxed_tools',
            'is_archived',
            # Phase 16: KB Configuration
            'kb_chunk_size', 'kb_chunk_overlap', 'kb_embedding_model',
            # Phase 16: Memory Configuration
            'enable_semantic_memory', 'semantic_memory_results', 'semantic_similarity_threshold',
            'enable_factual_memory', 'factual_extraction_threshold'
        ]

        updates = updates or {}
        for field, value in updates.items():
            if field in allowed_fields:
                setattr(project, field, value)

        # Phase 15: Handle agent access updates
        if 'agent_ids' in updates:
            agent_ids = updates['agent_ids']

            # Remove existing access
            self.db.query(AgentProjectAccess).filter(
                AgentProjectAccess.project_id == project_id
            ).delete()

            # Add new access
            for aid in agent_ids:
                access = AgentProjectAccess(
                    agent_id=aid,
                    project_id=project_id,
                    can_write=True
                )
                self.db.add(access)

        project.updated_at = datetime.utcnow()
        self.db.commit()

        return {
            "status": "success",
            "project": self._project_to_dict(project)
        }

    async def delete_project(
        self,
        tenant_id: str,
        user_id: int = None,
        project_id: int = None
    ) -> Dict[str, Any]:
        """
        Delete a project and all its data.

        Phase 15: Projects are tenant-scoped. user_id kept for backward compat.
        """
        from models import (
            Project, ProjectKnowledge, ProjectKnowledgeChunk,
            ProjectConversation, AgentProjectAccess, UserProjectSession,
            ProjectSemanticMemory, ProjectFactMemory
        )

        # Phase 15: Tenant-wide access
        project = self.db.query(Project).filter(
            Project.id == project_id,
            Project.tenant_id == tenant_id
        ).first()

        if not project:
            return {"status": "error", "error": "Project not found"}

        try:
            # Delete knowledge chunks
            knowledge_ids = [k.id for k in self.db.query(ProjectKnowledge).filter(
                ProjectKnowledge.project_id == project_id
            ).all()]

            if knowledge_ids:
                self.db.query(ProjectKnowledgeChunk).filter(
                    ProjectKnowledgeChunk.knowledge_id.in_(knowledge_ids)
                ).delete(synchronize_session=False)

            # Delete knowledge documents
            self.db.query(ProjectKnowledge).filter(
                ProjectKnowledge.project_id == project_id
            ).delete()

            # Delete conversations
            self.db.query(ProjectConversation).filter(
                ProjectConversation.project_id == project_id
            ).delete()

            # Phase 15: Delete agent access records
            self.db.query(AgentProjectAccess).filter(
                AgentProjectAccess.project_id == project_id
            ).delete()

            # Phase 15: Clear any active sessions for this project
            self.db.query(UserProjectSession).filter(
                UserProjectSession.project_id == project_id
            ).update({"project_id": None, "conversation_id": None})

            # Phase 16: Delete semantic memories
            self.db.query(ProjectSemanticMemory).filter(
                ProjectSemanticMemory.project_id == project_id
            ).delete()

            # Phase 16: Delete fact memories
            self.db.query(ProjectFactMemory).filter(
                ProjectFactMemory.project_id == project_id
            ).delete()

            # Delete embeddings from ChromaDB
            try:
                await self._delete_project_embeddings(project)
            except Exception as e:
                self.logger.warning(f"Failed to delete embeddings: {e}")

            # Delete project
            self.db.delete(project)
            self.db.commit()

            return {"status": "success", "message": "Project deleted"}

        except Exception as e:
            self.logger.error(f"Failed to delete project: {e}", exc_info=True)
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    # =========================================================================
    # Project Knowledge
    # =========================================================================

    async def upload_project_document(
        self,
        tenant_id: str,
        user_id: int = None,
        project_id: int = None,
        file_data: bytes = None,
        filename: str = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ) -> Dict[str, Any]:
        """
        Upload a document to a project's knowledge base.

        Phase 15: Projects are tenant-scoped. user_id kept for backward compat.
        """
        from models import Project, ProjectKnowledge, ProjectKnowledgeChunk
        from services.playground_document_service import PlaygroundDocumentService

        # Phase 15: Tenant-wide access
        project = self.db.query(Project).filter(
            Project.id == project_id,
            Project.tenant_id == tenant_id
        ).first()

        if not project:
            return {"status": "error", "error": "Project not found"}

        try:
            # Reuse document processing logic
            doc_service = PlaygroundDocumentService(self.db)

            ext = Path(filename).suffix.lower()
            if ext not in doc_service.SUPPORTED_EXTENSIONS:
                return {"status": "error", "error": f"Unsupported file type: {ext}"}

            if len(file_data) > doc_service.MAX_FILE_SIZE:
                return {"status": "error", "error": "File too large"}

            # Save file - use project_id for path (tenant-scoped)
            storage_path = self._get_project_storage_path(tenant_id, project.creator_id or 0, project_id)
            doc_id = str(uuid.uuid4())
            file_path = os.path.join(storage_path, f"{doc_id}{ext}")

            with open(file_path, 'wb') as f:
                f.write(file_data)

            # Create knowledge record
            knowledge = ProjectKnowledge(
                project_id=project_id,
                document_name=filename,
                document_type=doc_service.SUPPORTED_EXTENSIONS[ext],
                file_path=file_path,
                file_size_bytes=len(file_data),
                status="processing"
            )
            self.db.add(knowledge)
            self.db.commit()
            self.db.refresh(knowledge)

            # Process document
            try:
                text = await doc_service._extract_text(file_path, knowledge.document_type)
                chunks = doc_service._chunk_text(text, chunk_size, chunk_overlap)

                # Store chunks
                for i, chunk_text in enumerate(chunks):
                    chunk = ProjectKnowledgeChunk(
                        knowledge_id=knowledge.id,
                        chunk_index=i,
                        content=chunk_text,
                        char_count=len(chunk_text),
                        metadata_json={
                            "document_name": filename,
                            "chunk_index": i,
                            "total_chunks": len(chunks)
                        }
                    )
                    self.db.add(chunk)

                knowledge.num_chunks = len(chunks)
                knowledge.status = "completed"
                knowledge.processed_date = datetime.utcnow()

                # Store embeddings
                await self._store_project_embeddings(project, knowledge, chunks)

            except Exception as e:
                knowledge.status = "failed"
                knowledge.error_message = str(e)

            self.db.commit()

            return {
                "status": "success",
                "document": {
                    "id": knowledge.id,
                    "name": knowledge.document_name,
                    "type": knowledge.document_type,
                    "size_bytes": knowledge.file_size_bytes,
                    "num_chunks": knowledge.num_chunks,
                    "status": knowledge.status,
                    "error": knowledge.error_message
                }
            }

        except Exception as e:
            self.logger.error(f"Document upload failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    async def get_project_documents(
        self,
        tenant_id: str,
        user_id: int = None,
        project_id: int = None
    ) -> List[Dict[str, Any]]:
        """
        Get all documents in a project.

        Phase 15: Projects are tenant-scoped. user_id kept for backward compat.
        """
        from models import Project, ProjectKnowledge

        # Phase 15: Tenant-wide access
        project = self.db.query(Project).filter(
            Project.id == project_id,
            Project.tenant_id == tenant_id
        ).first()

        if not project:
            return []

        docs = self.db.query(ProjectKnowledge).filter(
            ProjectKnowledge.project_id == project_id
        ).order_by(ProjectKnowledge.upload_date.desc()).all()

        return [
            {
                "id": doc.id,
                "name": doc.document_name,
                "type": doc.document_type,
                "size_bytes": doc.file_size_bytes,
                "num_chunks": doc.num_chunks,
                "status": doc.status,
                "error": doc.error_message,
                "upload_date": doc.upload_date.isoformat() if doc.upload_date else None
            }
            for doc in docs
        ]

    async def delete_project_document(
        self,
        tenant_id: str,
        user_id: int = None,
        project_id: int = None,
        doc_id: int = None
    ) -> Dict[str, Any]:
        """
        Delete a document from project.

        Phase 15: Projects are tenant-scoped. user_id kept for backward compat.
        """
        from models import Project, ProjectKnowledge, ProjectKnowledgeChunk

        # Phase 15: Tenant-wide access
        project = self.db.query(Project).filter(
            Project.id == project_id,
            Project.tenant_id == tenant_id
        ).first()

        if not project:
            return {"status": "error", "error": "Project not found"}

        doc = self.db.query(ProjectKnowledge).filter(
            ProjectKnowledge.id == doc_id,
            ProjectKnowledge.project_id == project_id
        ).first()

        if not doc:
            return {"status": "error", "error": "Document not found"}

        try:
            # Delete chunks
            self.db.query(ProjectKnowledgeChunk).filter(
                ProjectKnowledgeChunk.knowledge_id == doc_id
            ).delete()

            # Delete file
            if os.path.exists(doc.file_path):
                os.remove(doc.file_path)

            # Delete embeddings
            await self._delete_document_embeddings(project, doc)

            # Delete record
            self.db.delete(doc)
            self.db.commit()

            return {"status": "success", "message": "Document deleted"}

        except Exception as e:
            self.logger.error(f"Delete failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    # =========================================================================
    # Project Conversations
    # =========================================================================

    async def create_conversation(
        self,
        tenant_id: str,
        user_id: int = None,
        project_id: int = None,
        title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new conversation in project.

        Phase 15: Projects are tenant-scoped. user_id kept for backward compat.
        """
        from models import Project, ProjectConversation

        # Phase 15: Tenant-wide access
        project = self.db.query(Project).filter(
            Project.id == project_id,
            Project.tenant_id == tenant_id
        ).first()

        if not project:
            return {"status": "error", "error": "Project not found"}

        conversation = ProjectConversation(
            project_id=project_id,
            title=title or "New Conversation",
            messages_json=[]
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)

        return {
            "status": "success",
            "conversation": self._conversation_to_dict(conversation)
        }

    async def get_conversations(
        self,
        tenant_id: str,
        user_id: int = None,
        project_id: int = None,
        include_archived: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all conversations in a project.

        Phase 15: Projects are tenant-scoped. user_id kept for backward compat.
        """
        from models import Project, ProjectConversation

        # Phase 15: Tenant-wide access
        project = self.db.query(Project).filter(
            Project.id == project_id,
            Project.tenant_id == tenant_id
        ).first()

        if not project:
            return []

        query = self.db.query(ProjectConversation).filter(
            ProjectConversation.project_id == project_id
        )

        if not include_archived:
            query = query.filter(ProjectConversation.is_archived == False)

        conversations = query.order_by(ProjectConversation.updated_at.desc()).all()

        return [self._conversation_to_dict(c) for c in conversations]

    async def get_conversation(
        self,
        tenant_id: str,
        user_id: int = None,
        project_id: int = None,
        conversation_id: int = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific conversation.

        Phase 15: Projects are tenant-scoped. user_id kept for backward compat.
        """
        from models import Project, ProjectConversation

        # Phase 15: Tenant-wide access
        project = self.db.query(Project).filter(
            Project.id == project_id,
            Project.tenant_id == tenant_id
        ).first()

        if not project:
            return None

        conversation = self.db.query(ProjectConversation).filter(
            ProjectConversation.id == conversation_id,
            ProjectConversation.project_id == project_id
        ).first()

        if not conversation:
            return None

        return self._conversation_to_dict(conversation)

    async def send_message(
        self,
        tenant_id: str,
        user_id: int = None,
        project_id: int = None,
        conversation_id: int = None,
        message: str = None
    ) -> Dict[str, Any]:
        """
        Send a message in a project conversation.

        Phase 15: Projects are tenant-scoped. user_id kept for backward compat.
        """
        from models import Project, ProjectConversation
        from services.playground_service import PlaygroundService

        # Phase 15: Tenant-wide access
        project = self.db.query(Project).filter(
            Project.id == project_id,
            Project.tenant_id == tenant_id
        ).first()

        if not project:
            return {"status": "error", "error": "Project not found"}

        conversation = self.db.query(ProjectConversation).filter(
            ProjectConversation.id == conversation_id,
            ProjectConversation.project_id == project_id
        ).first()

        if not conversation:
            return {"status": "error", "error": "Conversation not found"}

        try:
            # Add user message
            messages = conversation.messages_json or []
            messages.append({
                "role": "user",
                "content": message,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })

            # Search project knowledge for context
            context = await self._search_project_knowledge(project, message)

            # Build enhanced prompt with project context
            enhanced_message = message
            if context:
                context_text = "\n\n".join([c["content"] for c in context[:3]])
                enhanced_message = f"[Relevant context from project documents:\n{context_text}]\n\nUser message: {message}"

            # Use PlaygroundService to get agent response
            playground_service = PlaygroundService(self.db)

            agent_id = project.agent_id
            if not agent_id:
                # Use default agent
                from models import Agent
                default_agent = self.db.query(Agent).filter(
                    Agent.tenant_id == tenant_id,
                    Agent.is_active == True,
                    Agent.is_default == True
                ).first()
                if default_agent:
                    agent_id = default_agent.id

            if not agent_id:
                return {"status": "error", "error": "No agent configured for project"}

            response = await playground_service.send_message(
                user_id=user_id or 0,
                agent_id=agent_id,
                message_text=enhanced_message
            )

            if response.get("status") == "success" and response.get("message"):
                messages.append({
                    "role": "assistant",
                    "content": response["message"],
                    "timestamp": response.get("timestamp", datetime.utcnow().isoformat() + "Z")
                })

            # Update conversation
            conversation.messages_json = messages
            conversation.updated_at = datetime.utcnow()

            # Auto-generate title from first message
            if not conversation.title or conversation.title == "New Conversation":
                conversation.title = message[:50] + ("..." if len(message) > 50 else "")

            self.db.commit()

            return {
                "status": response.get("status", "success"),
                "message": response.get("message"),
                "conversation": self._conversation_to_dict(conversation)
            }

        except Exception as e:
            self.logger.error(f"Send message failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    async def delete_conversation(
        self,
        tenant_id: str,
        user_id: int = None,
        project_id: int = None,
        conversation_id: int = None
    ) -> Dict[str, Any]:
        """
        Delete a conversation.

        Phase 15: Projects are tenant-scoped. user_id kept for backward compat.
        """
        from models import Project, ProjectConversation

        # Phase 15: Tenant-wide access
        project = self.db.query(Project).filter(
            Project.id == project_id,
            Project.tenant_id == tenant_id
        ).first()

        if not project:
            return {"status": "error", "error": "Project not found"}

        conversation = self.db.query(ProjectConversation).filter(
            ProjectConversation.id == conversation_id,
            ProjectConversation.project_id == project_id
        ).first()

        if not conversation:
            return {"status": "error", "error": "Conversation not found"}

        self.db.delete(conversation)
        self.db.commit()

        return {"status": "success", "message": "Conversation deleted"}

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _project_to_dict(self, project) -> Dict[str, Any]:
        """Convert project model to dict with Phase 16 KB and memory configuration."""
        from models import AgentProjectAccess, ProjectFactMemory, ProjectSemanticMemory

        # Get agent IDs with access to this project
        agent_access = self.db.query(AgentProjectAccess).filter(
            AgentProjectAccess.project_id == project.id
        ).all()
        agent_ids = [a.agent_id for a in agent_access]

        # Phase 16: Get memory statistics
        fact_count = self.db.query(ProjectFactMemory).filter(
            ProjectFactMemory.project_id == project.id
        ).count()

        semantic_memory_count = self.db.query(ProjectSemanticMemory).filter(
            ProjectSemanticMemory.project_id == project.id
        ).count()

        return {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "icon": project.icon,
            "color": project.color,
            "agent_id": project.agent_id,
            "creator_id": project.creator_id,  # Phase 15: Creator tracking
            "agent_ids": agent_ids,  # Phase 15: Agents with access
            "system_prompt_override": project.system_prompt_override,
            "enabled_tools": project.enabled_tools or [],
            "enabled_sandboxed_tools": project.enabled_sandboxed_tools or [],
            "is_archived": project.is_archived,
            # Phase 16: KB Configuration
            "kb_chunk_size": project.kb_chunk_size or 500,
            "kb_chunk_overlap": project.kb_chunk_overlap or 50,
            "kb_embedding_model": project.kb_embedding_model or "all-MiniLM-L6-v2",
            # Phase 16: Memory Configuration
            "enable_semantic_memory": project.enable_semantic_memory if project.enable_semantic_memory is not None else True,
            "semantic_memory_results": project.semantic_memory_results or 10,
            "semantic_similarity_threshold": project.semantic_similarity_threshold or 0.5,
            "enable_factual_memory": project.enable_factual_memory if project.enable_factual_memory is not None else True,
            "factual_extraction_threshold": project.factual_extraction_threshold or 5,
            # Phase 16: Memory stats
            "fact_count": fact_count,
            "semantic_memory_count": semantic_memory_count,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None
        }

    def _conversation_to_dict(self, conversation) -> Dict[str, Any]:
        """Convert conversation model to dict."""
        messages = conversation.messages_json or []
        return {
            "id": conversation.id,
            "project_id": conversation.project_id,
            "title": conversation.title,
            "message_count": len(messages),
            "messages": messages,
            "is_archived": conversation.is_archived,
            "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
            "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None
        }

    async def regenerate_document_embeddings(
        self,
        tenant_id: str,
        project_id: int,
        doc_id: int
    ) -> Dict[str, Any]:
        """
        Regenerate embeddings for an existing project document.
        Useful when embeddings are missing or need to be recreated.
        """
        from models import Project, ProjectKnowledge, ProjectKnowledgeChunk

        try:
            # Verify project access
            project = self.db.query(Project).filter(
                Project.id == project_id,
                Project.tenant_id == tenant_id
            ).first()

            if not project:
                return {"status": "error", "error": "Project not found"}

            # Get the knowledge document
            knowledge = self.db.query(ProjectKnowledge).filter(
                ProjectKnowledge.id == doc_id,
                ProjectKnowledge.project_id == project_id
            ).first()

            if not knowledge:
                return {"status": "error", "error": "Document not found"}

            # Get all chunks
            chunks = self.db.query(ProjectKnowledgeChunk).filter(
                ProjectKnowledgeChunk.knowledge_id == doc_id
            ).order_by(ProjectKnowledgeChunk.chunk_index).all()

            if not chunks:
                return {"status": "error", "error": "No chunks found for document"}

            # Extract chunk text
            chunk_texts = [chunk.content for chunk in chunks]

            # Delete old embeddings if they exist
            await self._delete_document_embeddings(project, knowledge)

            # Store new embeddings
            await self._store_project_embeddings(project, knowledge, chunk_texts)

            # Update status
            knowledge.status = "completed"
            self.db.commit()

            return {
                "status": "success",
                "message": f"Regenerated embeddings for {len(chunk_texts)} chunks",
                "document_id": doc_id,
                "chunks_processed": len(chunk_texts)
            }

        except Exception as e:
            self.logger.error(f"Failed to regenerate embeddings: {e}", exc_info=True)
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    def _get_project_storage_path(self, tenant_id: str, user_id: int, project_id: int) -> str:
        """Get storage path for project documents."""
        import settings
        base_path = getattr(settings, 'DATA_DIR', 'data')
        path = os.path.join(base_path, 'projects', tenant_id, str(user_id), str(project_id))
        os.makedirs(path, exist_ok=True)
        return path

    def _get_collection_name(self, project) -> str:
        """Get ChromaDB collection name for project."""
        return f"project_{project.id}"

    async def _store_project_embeddings(self, project, knowledge, chunks: List[str]):
        """
        Store embeddings for project document.

        BUG-001 Fix: Uses shared embedding service with batched processing
        to prevent OOM crashes on large documents.
        """
        try:
            import chromadb
            from agent.memory.embedding_service import get_shared_embedding_service
            import settings

            persist_dir = getattr(settings, 'CHROMA_DIR', 'data/chroma')
            client = chromadb.PersistentClient(path=persist_dir)

            collection_name = self._get_collection_name(project)
            collection = client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )

            # BUG-001 Fix: Use shared service with batched processing
            embedding_service = get_shared_embedding_service("all-MiniLM-L6-v2")
            embeddings = embedding_service.embed_batch_chunked(chunks, batch_size=50)

            # Validate we got embeddings for all chunks
            if len(embeddings) != len(chunks):
                self.logger.warning(
                    f"Embedding count mismatch: {len(embeddings)} embeddings for {len(chunks)} chunks"
                )
                # Only process chunks we have embeddings for
                chunks = chunks[:len(embeddings)]

            ids = [f"{knowledge.id}_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "document_id": knowledge.id,
                    "document_name": knowledge.document_name,
                    "chunk_index": i
                }
                for i in range(len(chunks))
            ]

            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas
            )

            self.logger.info(f"Stored {len(embeddings)} embeddings for document {knowledge.document_name}")

        except Exception as e:
            self.logger.error(f"Failed to store embeddings: {e}", exc_info=True)

    async def _delete_document_embeddings(self, project, doc):
        """Delete embeddings for a document."""
        try:
            import chromadb
            import settings

            persist_dir = getattr(settings, 'CHROMA_DIR', 'data/chroma')
            client = chromadb.PersistentClient(path=persist_dir)

            collection_name = self._get_collection_name(project)
            try:
                collection = client.get_collection(name=collection_name)
                ids = [f"{doc.id}_{i}" for i in range(doc.num_chunks)]
                if ids:
                    collection.delete(ids=ids)
            except Exception:
                pass

        except Exception as e:
            self.logger.warning(f"Failed to delete embeddings: {e}")

    async def _delete_project_embeddings(self, project):
        """Delete all embeddings for a project."""
        try:
            import chromadb
            import settings

            persist_dir = getattr(settings, 'CHROMA_DIR', 'data/chroma')
            client = chromadb.PersistentClient(path=persist_dir)

            collection_name = self._get_collection_name(project)
            try:
                client.delete_collection(name=collection_name)
            except Exception:
                pass

        except Exception as e:
            self.logger.warning(f"Failed to delete project embeddings: {e}")

    async def _search_project_knowledge(
        self,
        project,
        query: str,
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search project knowledge base."""
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
            import settings

            persist_dir = getattr(settings, 'CHROMA_DIR', 'data/chroma')
            client = chromadb.PersistentClient(path=persist_dir)

            collection_name = self._get_collection_name(project)
            try:
                collection = client.get_collection(name=collection_name)
            except Exception:
                return []

            model = SentenceTransformer("all-MiniLM-L6-v2")
            query_embedding = model.encode([query], convert_to_numpy=True).tolist()[0]

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=max_results
            )

            if not results or not results.get('documents'):
                return []

            documents = results.get('documents', [[]])[0]
            metadatas = results.get('metadatas', [[]])[0]
            distances = results.get('distances', [[]])[0]

            return [
                {
                    "content": doc,
                    "metadata": meta,
                    "similarity": 1 - dist
                }
                for doc, meta, dist in zip(documents, metadatas, distances)
            ]

        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            return []
