"""
Phase 14.4: Project Service
Phase 15: Skill Projects - Updated for tenant-wide access

Handles project management, knowledge bases, and conversations.
Projects are now tenant-scoped (not user-owned) with agent-based access control.
"""

import os
import logging
import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from agent.response_helpers import extract_response_text

logger = logging.getLogger(__name__)

_PROJECT_KB_INDEX_VERSION = 1
_DEFAULT_PROJECT_CHUNK_SIZE = 500
_DEFAULT_PROJECT_CHUNK_OVERLAP = 50
_DEFAULT_PROJECT_TOP_K = 5
_DEFAULT_PROJECT_SIMILARITY_THRESHOLD = 0.3


@dataclass(frozen=True)
class ProjectKnowledgeIndexProfile:
    tenant_id: str
    project_id: int
    embedding_provider_instance_id: Optional[int]
    embedding_provider: str
    embedding_model: str
    embedding_dims: int
    embedding_metric: str
    vector_store_instance_id: Optional[int]
    vector_store_index_id: Optional[int]
    vector_collection_name: str
    vector_namespace: str
    chunk_strategy: str
    chunk_size: int
    chunk_overlap: int
    parser: str
    index_version: int = _PROJECT_KB_INDEX_VERSION

    def grouping_key(self):
        return (
            self.tenant_id,
            self.project_id,
            self.embedding_provider_instance_id,
            self.embedding_provider,
            self.embedding_model,
            self.embedding_dims,
            self.embedding_metric,
            self.vector_store_instance_id,
            self.vector_store_index_id,
            self.vector_collection_name,
            self.vector_namespace,
        )


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
        kb_embedding_provider_instance_id: Optional[int] = None,
        kb_embedding_provider: str = "local",
        kb_embedding_dims: int = 384,
        kb_embedding_metric: str = "cosine",
        kb_vector_store_instance_id: Optional[int] = None,
        kb_chunk_strategy: str = "fixed_text",
        kb_parser: str = "auto",
        kb_search_top_k: int = _DEFAULT_PROJECT_TOP_K,
        kb_similarity_threshold: float = _DEFAULT_PROJECT_SIMILARITY_THRESHOLD,
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

            self.update_project_knowledge_config_sync(
                project_id=project.id,
                tenant_id=tenant_id,
                data={
                    "embedding_provider_instance_id": kb_embedding_provider_instance_id,
                    "embedding_provider": kb_embedding_provider,
                    "embedding_model": kb_embedding_model,
                    "embedding_dims": kb_embedding_dims,
                    "embedding_metric": kb_embedding_metric,
                    "vector_store_instance_id": kb_vector_store_instance_id,
                    "chunk_strategy": kb_chunk_strategy,
                    "chunk_size": kb_chunk_size,
                    "chunk_overlap": kb_chunk_overlap,
                    "parser": kb_parser,
                    "search_top_k": kb_search_top_k,
                    "similarity_threshold": kb_similarity_threshold,
                },
                commit=False,
            )

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

        kb_update_fields = {
            'kb_embedding_provider_instance_id',
            'kb_embedding_provider',
            'kb_embedding_model',
            'kb_embedding_dims',
            'kb_embedding_metric',
            'kb_vector_store_instance_id',
            'kb_chunk_strategy',
            'kb_chunk_size',
            'kb_chunk_overlap',
            'kb_parser',
            'kb_search_top_k',
            'kb_similarity_threshold',
        }
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
        kb_updates = {field[3:]: value for field, value in updates.items() if field in kb_update_fields}
        for field, value in updates.items():
            if field in allowed_fields:
                setattr(project, field, value)

        if kb_updates:
            self.update_project_knowledge_config_sync(
                project_id=project_id,
                tenant_id=tenant_id,
                data=kb_updates,
                commit=False,
            )

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
            # Delete vectors before removing knowledge/chunk rows; vector IDs are derived from chunk IDs.
            try:
                await self._delete_project_embeddings(project)
            except Exception as e:
                self.logger.warning(f"Failed to delete embeddings: {e}")

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

    def _tenant_hash(self, tenant_id: str) -> str:
        import hashlib

        return hashlib.sha1((tenant_id or "system").encode("utf-8")).hexdigest()[:10]

    def _legacy_project_collection_name(self, project_id: int) -> str:
        return f"project_{project_id}"

    def _project_collection_base(self, tenant_id: str, project_id: int, dims: int) -> str:
        return f"project_kb_{self._tenant_hash(tenant_id)}_{project_id}_{dims}"

    def get_project_knowledge_config(self, project_id: int, tenant_id: str):
        from agent.memory.embedding_catalog import LOCAL_DIMS, LOCAL_MODEL
        from models import ProjectKnowledgeConfig

        config = (
            self.db.query(ProjectKnowledgeConfig)
            .filter(
                ProjectKnowledgeConfig.tenant_id == tenant_id,
                ProjectKnowledgeConfig.project_id == project_id,
            )
            .first()
        )
        if config:
            return config

        config = ProjectKnowledgeConfig(
            tenant_id=tenant_id,
            project_id=project_id,
            embedding_provider="local",
            embedding_model=LOCAL_MODEL,
            embedding_dims=LOCAL_DIMS,
            embedding_metric="cosine",
            chunk_strategy="fixed_text",
            chunk_size=_DEFAULT_PROJECT_CHUNK_SIZE,
            chunk_overlap=_DEFAULT_PROJECT_CHUNK_OVERLAP,
            parser="auto",
            search_top_k=_DEFAULT_PROJECT_TOP_K,
            similarity_threshold=_DEFAULT_PROJECT_SIMILARITY_THRESHOLD,
        )
        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config

    def update_project_knowledge_config_sync(
        self,
        *,
        project_id: int,
        tenant_id: str,
        data: Dict[str, Any],
        commit: bool = True,
    ):
        from agent.memory.embedding_catalog import (
            normalize_embedding_provider,
            provider_default_model,
            validate_embedding_contract,
        )
        from models import Project, ProjectKnowledgeConfig, ProviderInstance, VectorStoreInstance

        project = (
            self.db.query(Project)
            .filter(Project.id == project_id, Project.tenant_id == tenant_id)
            .first()
        )
        if not project:
            raise ValueError("Project not found")

        config = (
            self.db.query(ProjectKnowledgeConfig)
            .filter(
                ProjectKnowledgeConfig.tenant_id == tenant_id,
                ProjectKnowledgeConfig.project_id == project_id,
            )
            .first()
        )
        if not config:
            config = ProjectKnowledgeConfig(tenant_id=tenant_id, project_id=project_id)
            self.db.add(config)
            self.db.flush()

        provider = normalize_embedding_provider(data.get("embedding_provider", config.embedding_provider or "local"))
        model = data.get("embedding_model", config.embedding_model) or provider_default_model(provider)
        dims = data.get("embedding_dims", config.embedding_dims or 384)
        normalized = validate_embedding_contract(
            provider=provider,
            model=model,
            dimensions=dims,
            allow_ollama_dynamic=False,
        )

        provider_instance_id = data.get(
            "embedding_provider_instance_id",
            config.embedding_provider_instance_id,
        )
        if normalized["provider"] != "local":
            provider_instance = (
                self.db.query(ProviderInstance)
                .filter(
                    ProviderInstance.id == provider_instance_id,
                    ProviderInstance.tenant_id == tenant_id,
                    ProviderInstance.vendor == normalized["provider"],
                    ProviderInstance.is_active == True,
                )
                .first()
            )
            if not provider_instance:
                raise ValueError("A configured embedding provider instance is required")
        else:
            provider_instance_id = None

        vector_store_instance_id = data.get(
            "vector_store_instance_id",
            config.vector_store_instance_id,
        )
        if vector_store_instance_id is not None:
            instance = (
                self.db.query(VectorStoreInstance)
                .filter(
                    VectorStoreInstance.id == vector_store_instance_id,
                    VectorStoreInstance.tenant_id == tenant_id,
                    VectorStoreInstance.is_active == True,
                )
                .first()
            )
            if not instance:
                raise ValueError("Vector store instance not found")

        chunk_size = int(data.get("chunk_size", config.chunk_size or _DEFAULT_PROJECT_CHUNK_SIZE))
        chunk_overlap = int(data.get("chunk_overlap", config.chunk_overlap or _DEFAULT_PROJECT_CHUNK_OVERLAP))
        if chunk_size < 200 or chunk_size > 8000:
            raise ValueError("chunk_size must be between 200 and 8000")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")

        chunk_strategy = data.get("chunk_strategy", config.chunk_strategy or "fixed_text")
        if chunk_strategy not in {"fixed_text", "json_structure", "csv_rows"}:
            raise ValueError("Invalid chunk_strategy")
        parser = data.get("parser", config.parser or "auto")
        if parser not in {"auto", "txt", "csv", "json", "pdf", "docx"}:
            raise ValueError("Invalid parser")

        config.embedding_provider_instance_id = provider_instance_id
        config.embedding_provider = str(normalized["provider"])
        config.embedding_model = str(normalized["model"])
        config.embedding_dims = int(normalized["dimensions"])
        config.embedding_metric = data.get("embedding_metric", config.embedding_metric or "cosine")
        config.vector_store_instance_id = vector_store_instance_id
        config.vector_store_index_id = None
        config.vector_collection_name = None
        config.vector_namespace = None
        config.chunk_strategy = chunk_strategy
        config.chunk_size = chunk_size
        config.chunk_overlap = chunk_overlap
        config.parser = parser
        config.search_top_k = int(data.get("search_top_k", config.search_top_k or _DEFAULT_PROJECT_TOP_K))
        config.similarity_threshold = float(
            data.get("similarity_threshold", config.similarity_threshold or _DEFAULT_PROJECT_SIMILARITY_THRESHOLD)
        )
        config.updated_at = datetime.utcnow()

        project.kb_chunk_size = chunk_size
        project.kb_chunk_overlap = chunk_overlap
        project.kb_embedding_model = str(normalized["model"])

        profile = self._project_profile_from_config(config, tenant_id=tenant_id, project_id=project_id)
        profile = self._project_profile_with_vector_index(profile)
        config.vector_store_index_id = profile.vector_store_index_id
        config.vector_collection_name = profile.vector_collection_name
        config.vector_namespace = profile.vector_namespace

        if commit:
            self.db.commit()
            self.db.refresh(config)
        return config

    def _project_profile_from_config(
        self,
        config,
        *,
        tenant_id: str,
        project_id: int,
    ) -> ProjectKnowledgeIndexProfile:
        from agent.memory.embedding_catalog import (
            normalize_embedding_provider,
            provider_default_model,
            validate_embedding_contract,
        )

        provider = normalize_embedding_provider(config.embedding_provider)
        normalized = validate_embedding_contract(
            provider=provider,
            model=config.embedding_model or provider_default_model(provider),
            dimensions=config.embedding_dims,
            allow_ollama_dynamic=False,
        )
        dims = int(normalized["dimensions"])
        collection = config.vector_collection_name or self._project_collection_base(tenant_id, project_id, dims)
        namespace = config.vector_namespace or f"project_kb:{tenant_id}:{project_id}:{dims}"
        return ProjectKnowledgeIndexProfile(
            tenant_id=tenant_id,
            project_id=project_id,
            embedding_provider_instance_id=config.embedding_provider_instance_id,
            embedding_provider=str(normalized["provider"]),
            embedding_model=str(normalized["model"]),
            embedding_dims=dims,
            embedding_metric=str(config.embedding_metric or normalized.get("metric") or "cosine"),
            vector_store_instance_id=config.vector_store_instance_id,
            vector_store_index_id=getattr(config, "vector_store_index_id", None),
            vector_collection_name=collection,
            vector_namespace=namespace,
            chunk_strategy=config.chunk_strategy or "fixed_text",
            chunk_size=int(config.chunk_size or _DEFAULT_PROJECT_CHUNK_SIZE),
            chunk_overlap=int(config.chunk_overlap or _DEFAULT_PROJECT_CHUNK_OVERLAP),
            parser=config.parser or "auto",
        )

    def _project_profile_from_knowledge(self, project, knowledge) -> ProjectKnowledgeIndexProfile:
        from agent.memory.embedding_catalog import LOCAL_DIMS, LOCAL_MODEL, normalize_embedding_provider, provider_default_model

        tenant_id = getattr(knowledge, "tenant_id", None) or project.tenant_id
        dims = int(getattr(knowledge, "embedding_dims", None) or LOCAL_DIMS)
        provider = normalize_embedding_provider(getattr(knowledge, "embedding_provider", None))
        model = getattr(knowledge, "embedding_model", None) or (
            provider_default_model(provider) if provider != "ollama" else LOCAL_MODEL
        )
        collection = (
            getattr(knowledge, "vector_collection_name", None)
            or self._legacy_project_collection_name(project.id)
        )
        namespace = (
            getattr(knowledge, "vector_namespace", None)
            or f"project_kb:{tenant_id}:{project.id}:{dims}"
        )
        return ProjectKnowledgeIndexProfile(
            tenant_id=tenant_id,
            project_id=project.id,
            embedding_provider_instance_id=getattr(knowledge, "embedding_provider_instance_id", None),
            embedding_provider=provider,
            embedding_model=model,
            embedding_dims=dims,
            embedding_metric=getattr(knowledge, "embedding_metric", None) or "cosine",
            vector_store_instance_id=getattr(knowledge, "vector_store_instance_id", None),
            vector_store_index_id=getattr(knowledge, "vector_store_index_id", None),
            vector_collection_name=collection,
            vector_namespace=namespace,
            chunk_strategy=getattr(knowledge, "chunk_strategy", None) or "fixed_text",
            chunk_size=int(getattr(knowledge, "chunk_size", None) or _DEFAULT_PROJECT_CHUNK_SIZE),
            chunk_overlap=int(getattr(knowledge, "chunk_overlap", None) or _DEFAULT_PROJECT_CHUNK_OVERLAP),
            parser=getattr(knowledge, "parser", None) or "auto",
            index_version=int(getattr(knowledge, "index_version", None) or 0),
        )

    def _project_profile_with_vector_index(
        self,
        profile: ProjectKnowledgeIndexProfile,
    ) -> ProjectKnowledgeIndexProfile:
        from services.vector_store_index_resolver import VectorStoreIndexResolver

        index = VectorStoreIndexResolver.resolve_or_create(
            self.db,
            tenant_id=profile.tenant_id,
            vector_store_instance_id=profile.vector_store_instance_id,
            purpose="project_kb",
            owner_type="project",
            owner_id=profile.project_id,
            contract={
                "embedding_provider_instance_id": profile.embedding_provider_instance_id,
                "embedding_provider": profile.embedding_provider,
                "embedding_model": profile.embedding_model,
                "embedding_dims": profile.embedding_dims,
                "embedding_metric": profile.embedding_metric,
            },
        )
        return ProjectKnowledgeIndexProfile(
            tenant_id=profile.tenant_id,
            project_id=profile.project_id,
            embedding_provider_instance_id=profile.embedding_provider_instance_id,
            embedding_provider=profile.embedding_provider,
            embedding_model=profile.embedding_model,
            embedding_dims=profile.embedding_dims,
            embedding_metric=profile.embedding_metric,
            vector_store_instance_id=profile.vector_store_instance_id,
            vector_store_index_id=index.id,
            vector_collection_name=index.physical_collection_name,
            vector_namespace=index.physical_namespace,
            chunk_strategy=profile.chunk_strategy,
            chunk_size=profile.chunk_size,
            chunk_overlap=profile.chunk_overlap,
            parser=profile.parser,
            index_version=profile.index_version,
        )

    def _resolve_current_project_profile(self, project) -> ProjectKnowledgeIndexProfile:
        config = self.get_project_knowledge_config(project.id, project.tenant_id)
        profile = self._project_profile_from_config(
            config,
            tenant_id=project.tenant_id,
            project_id=project.id,
        )
        profile = self._project_profile_with_vector_index(profile)
        config.vector_store_index_id = profile.vector_store_index_id
        config.vector_collection_name = profile.vector_collection_name
        config.vector_namespace = profile.vector_namespace
        self.db.flush()
        return profile

    def _snapshot_project_profile(self, knowledge, profile: ProjectKnowledgeIndexProfile) -> None:
        knowledge.tenant_id = profile.tenant_id
        knowledge.embedding_provider_instance_id = profile.embedding_provider_instance_id
        knowledge.embedding_provider = profile.embedding_provider
        knowledge.embedding_model = profile.embedding_model
        knowledge.embedding_dims = profile.embedding_dims
        knowledge.embedding_metric = profile.embedding_metric
        knowledge.vector_store_instance_id = profile.vector_store_instance_id
        knowledge.vector_store_index_id = profile.vector_store_index_id
        knowledge.vector_collection_name = profile.vector_collection_name
        knowledge.vector_namespace = profile.vector_namespace
        knowledge.chunk_strategy = profile.chunk_strategy
        knowledge.chunk_size = profile.chunk_size
        knowledge.chunk_overlap = profile.chunk_overlap
        knowledge.parser = profile.parser
        knowledge.index_version = profile.index_version

    def _project_embedding_credentials(self, profile: ProjectKnowledgeIndexProfile) -> Dict[str, Any]:
        from services.embedding_provider_service import EmbeddingProviderService

        return EmbeddingProviderService.resolve_provider_credentials(
            tenant_id=profile.tenant_id,
            provider=profile.embedding_provider,
            provider_instance_id=profile.embedding_provider_instance_id,
            db=self.db,
        )

    def _project_embedding_provider(self, profile: ProjectKnowledgeIndexProfile):
        from agent.memory.embedding_service import get_shared_embedding_service

        contract = SimpleNamespace(
            provider=profile.embedding_provider,
            model=profile.embedding_model,
            dimensions=profile.embedding_dims,
            metric=profile.embedding_metric,
            vector_store_instance_id=profile.vector_store_instance_id,
        )
        return get_shared_embedding_service(
            contract=contract,
            credentials=self._project_embedding_credentials(profile),
        )

    def _project_vector_id(self, knowledge_id: int, chunk_id: int) -> str:
        return f"project_knowledge_{knowledge_id}_chunk_{chunk_id}"

    def _project_sender_key(self, profile: ProjectKnowledgeIndexProfile) -> str:
        return f"project_kb:{profile.tenant_id}:{profile.project_id}"

    def _project_external_vector_provider(self, profile: ProjectKnowledgeIndexProfile):
        if profile.vector_store_instance_id is None:
            return None
        from models import VectorStoreIndex, VectorStoreInstance

        instance = (
            self.db.query(VectorStoreInstance)
            .filter(
                VectorStoreInstance.id == profile.vector_store_instance_id,
                VectorStoreInstance.tenant_id == profile.tenant_id,
                VectorStoreInstance.is_active == True,
            )
            .first()
        )
        if not instance:
            return None
        vendor = (instance.vendor or "").lower()
        if vendor in {"chroma", "chromadb"}:
            return None

        from agent.memory.providers.registry import VectorStoreRegistry

        if profile.vector_store_index_id:
            index = (
                self.db.query(VectorStoreIndex)
                .filter(
                    VectorStoreIndex.id == profile.vector_store_index_id,
                    VectorStoreIndex.tenant_id == profile.tenant_id,
                    VectorStoreIndex.is_active == True,
                )
                .first()
            )
            if index:
                return VectorStoreRegistry().get_provider_for_index(index, self.db)

        return VectorStoreRegistry().get_provider(
            profile.vector_store_instance_id,
            self.db,
            tenant_id=profile.tenant_id,
            collection_name=profile.vector_collection_name,
            namespace=profile.vector_namespace,
            index_name=profile.vector_collection_name.replace("_", "-"),
            embedding_dims=profile.embedding_dims,
        )

    async def upload_project_document(
        self,
        tenant_id: str,
        user_id: int = None,
        project_id: int = None,
        file_data: bytes = None,
        filename: str = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None
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

            profile = self._resolve_current_project_profile(project)
            if chunk_size is not None:
                profile = ProjectKnowledgeIndexProfile(
                    tenant_id=profile.tenant_id,
                    project_id=profile.project_id,
                    embedding_provider_instance_id=profile.embedding_provider_instance_id,
                    embedding_provider=profile.embedding_provider,
                    embedding_model=profile.embedding_model,
                    embedding_dims=profile.embedding_dims,
                    embedding_metric=profile.embedding_metric,
                    vector_store_instance_id=profile.vector_store_instance_id,
                    vector_store_index_id=profile.vector_store_index_id,
                    vector_collection_name=profile.vector_collection_name,
                    vector_namespace=profile.vector_namespace,
                    chunk_strategy=profile.chunk_strategy,
                    chunk_size=int(chunk_size),
                    chunk_overlap=int(chunk_overlap if chunk_overlap is not None else profile.chunk_overlap),
                    parser=profile.parser,
                    index_version=profile.index_version,
                )

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
            self._snapshot_project_profile(knowledge, profile)
            self.db.add(knowledge)
            self.db.commit()
            self.db.refresh(knowledge)

            # Process document
            processing_committed = False
            try:
                text = await doc_service._extract_text(file_path, knowledge.document_type)
                chunks = doc_service._chunk_text(text, profile.chunk_size, profile.chunk_overlap)

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

                # Persist chunks first so vector metadata can reference stable chunk IDs.
                self.db.commit()
                self.db.refresh(knowledge)

                stored_chunks = self.db.query(ProjectKnowledgeChunk).filter(
                    ProjectKnowledgeChunk.knowledge_id == knowledge.id
                ).order_by(ProjectKnowledgeChunk.chunk_index).all()
                try:
                    await self._store_project_embeddings(project, knowledge, stored_chunks)
                    self.db.commit()
                    self.logger.info(
                        f"Document processed and indexed: {len(stored_chunks)} chunks for {knowledge.document_name}"
                    )
                except Exception as embedding_error:
                    knowledge.status = "failed"
                    knowledge.error_message = str(embedding_error)
                    self.db.commit()
                    self.logger.error(
                        f"Document embedding storage failed: {embedding_error}",
                        exc_info=True,
                    )
                processing_committed = True

            except Exception as e:
                knowledge.status = "failed"
                knowledge.error_message = str(e)
                self.logger.error(f"Document processing failed: {e}", exc_info=True)

            if not processing_committed:
                try:
                    self.db.commit()
                except Exception as commit_error:
                    self.db.rollback()
                    self.logger.error(f"Failed to persist project knowledge status: {commit_error}", exc_info=True)
                    return {"status": "error", "error": str(commit_error)}

            return {
                "status": "success",
                "document": {
                    "id": knowledge.id,
                    "name": knowledge.document_name,
                    "type": knowledge.document_type,
                    "size_bytes": knowledge.file_size_bytes,
                    "num_chunks": knowledge.num_chunks,
                    "status": knowledge.status,
                    "error": knowledge.error_message,
                    "upload_date": knowledge.upload_date.isoformat() if knowledge.upload_date else None,
                    "embedding_provider_instance_id": knowledge.embedding_provider_instance_id,
                    "embedding_provider": knowledge.embedding_provider,
                    "embedding_model": knowledge.embedding_model,
                    "embedding_dims": knowledge.embedding_dims,
                    "embedding_metric": knowledge.embedding_metric,
                    "vector_store_instance_id": knowledge.vector_store_instance_id,
                    "vector_store_index_id": getattr(knowledge, "vector_store_index_id", None),
                    "vector_collection_name": knowledge.vector_collection_name,
                    "vector_namespace": knowledge.vector_namespace,
                    "chunk_strategy": knowledge.chunk_strategy,
                    "chunk_size": knowledge.chunk_size,
                    "chunk_overlap": knowledge.chunk_overlap,
                    "parser": knowledge.parser,
                    "index_version": knowledge.index_version,
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
                "upload_date": doc.upload_date.isoformat() if doc.upload_date else None,
                "embedding_provider_instance_id": getattr(doc, "embedding_provider_instance_id", None),
                "embedding_provider": getattr(doc, "embedding_provider", None),
                "embedding_model": getattr(doc, "embedding_model", None),
                "embedding_dims": getattr(doc, "embedding_dims", None),
                "embedding_metric": getattr(doc, "embedding_metric", None),
                "vector_store_instance_id": getattr(doc, "vector_store_instance_id", None),
                "vector_store_index_id": getattr(doc, "vector_store_index_id", None),
                "vector_collection_name": getattr(doc, "vector_collection_name", None),
                "vector_namespace": getattr(doc, "vector_namespace", None),
                "chunk_strategy": getattr(doc, "chunk_strategy", None),
                "chunk_size": getattr(doc, "chunk_size", None),
                "chunk_overlap": getattr(doc, "chunk_overlap", None),
                "parser": getattr(doc, "parser", None),
                "index_version": getattr(doc, "index_version", None),
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
            # Delete vectors before removing chunk rows; vector IDs are derived from chunk IDs.
            await self._delete_document_embeddings(project, doc)

            # Delete chunks
            self.db.query(ProjectKnowledgeChunk).filter(
                ProjectKnowledgeChunk.knowledge_id == doc_id
            ).delete()

            # Delete file
            if os.path.exists(doc.file_path):
                os.remove(doc.file_path)

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
                message_text=enhanced_message,
                project_id=project_id,  # BUG-446: Pass project context for CombinedKnowledgeService
            )

            # BUG-511: Fall back to tool output when the primary message is empty,
            # mirroring the API v1 chat response handling from BUG-504.
            assistant_text = extract_response_text(response) if isinstance(response, dict) else None

            if response.get("status") == "success" and assistant_text:
                messages.append({
                    "role": "assistant",
                    "content": assistant_text,
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
                "message": assistant_text,
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

        try:
            kb_config = self.get_project_knowledge_config(project.id, project.tenant_id)
        except Exception:
            kb_config = None

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
            "kb_embedding_provider_instance_id": getattr(kb_config, "embedding_provider_instance_id", None) if kb_config else None,
            "kb_embedding_provider": getattr(kb_config, "embedding_provider", "local") if kb_config else "local",
            "kb_embedding_dims": getattr(kb_config, "embedding_dims", 384) if kb_config else 384,
            "kb_embedding_metric": getattr(kb_config, "embedding_metric", "cosine") if kb_config else "cosine",
            "kb_vector_store_instance_id": getattr(kb_config, "vector_store_instance_id", None) if kb_config else None,
            "kb_vector_store_index_id": getattr(kb_config, "vector_store_index_id", None) if kb_config else None,
            "kb_vector_collection_name": getattr(kb_config, "vector_collection_name", None) if kb_config else None,
            "kb_vector_namespace": getattr(kb_config, "vector_namespace", None) if kb_config else None,
            "kb_chunk_strategy": getattr(kb_config, "chunk_strategy", "fixed_text") if kb_config else "fixed_text",
            "kb_parser": getattr(kb_config, "parser", "auto") if kb_config else "auto",
            "kb_search_top_k": getattr(kb_config, "search_top_k", _DEFAULT_PROJECT_TOP_K) if kb_config else _DEFAULT_PROJECT_TOP_K,
            "kb_similarity_threshold": getattr(kb_config, "similarity_threshold", _DEFAULT_PROJECT_SIMILARITY_THRESHOLD) if kb_config else _DEFAULT_PROJECT_SIMILARITY_THRESHOLD,
            "kb_config": self._project_kb_config_to_dict(kb_config) if kb_config else None,
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

    def _project_kb_config_to_dict(self, config) -> Dict[str, Any]:
        return {
            "id": config.id,
            "tenant_id": config.tenant_id,
            "project_id": config.project_id,
            "embedding_provider_instance_id": config.embedding_provider_instance_id,
            "embedding_provider": config.embedding_provider,
            "embedding_model": config.embedding_model,
            "embedding_dims": config.embedding_dims,
            "embedding_metric": config.embedding_metric,
            "vector_store_instance_id": config.vector_store_instance_id,
            "vector_store_index_id": getattr(config, "vector_store_index_id", None),
            "vector_collection_name": config.vector_collection_name,
            "vector_namespace": config.vector_namespace,
            "chunk_strategy": config.chunk_strategy,
            "chunk_size": config.chunk_size,
            "chunk_overlap": config.chunk_overlap,
            "parser": config.parser,
            "search_top_k": config.search_top_k,
            "similarity_threshold": config.similarity_threshold,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
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

            # Delete old embeddings if they exist
            await self._delete_document_embeddings(project, knowledge)

            # Store new embeddings
            if not getattr(knowledge, "embedding_provider", None):
                profile = self._resolve_current_project_profile(project)
                self._snapshot_project_profile(knowledge, profile)
                self.db.flush()
            await self._store_project_embeddings(project, knowledge, chunks)

            # Update status
            knowledge.status = "completed"
            self.db.commit()

            return {
                "status": "success",
                "message": f"Regenerated embeddings for {len(chunks)} chunks",
                "document_id": doc_id,
                "chunks_processed": len(chunks)
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

    async def _store_project_embeddings(self, project, knowledge, chunks: List[Any]):
        """
        Store embeddings for project document.

        BUG-001 Fix: Uses shared embedding service with batched processing
        to prevent OOM crashes on large documents.
        """
        try:
            import settings

            profile = self._project_profile_from_knowledge(project, knowledge)
            chunk_texts = [chunk.content if hasattr(chunk, "content") else str(chunk) for chunk in chunks]
            if not chunk_texts:
                return

            embedding_service = self._project_embedding_provider(profile)
            embeddings = await embedding_service.embed_batch_chunked_async(
                chunk_texts,
                batch_size=32,
                task_type="RETRIEVAL_DOCUMENT",
            )

            # Validate we got embeddings for all chunks
            if len(embeddings) != len(chunk_texts):
                self.logger.warning(
                    f"Embedding count mismatch: {len(embeddings)} embeddings for {len(chunk_texts)} chunks"
                )
                # Only process chunks we have embeddings for
                chunks = chunks[:len(embeddings)]
                chunk_texts = chunk_texts[:len(embeddings)]

            records = []
            for chunk, chunk_text, embedding in zip(chunks, chunk_texts, embeddings):
                if len(embedding) != profile.embedding_dims:
                    raise ValueError(
                        f"Embedding dimension mismatch: expected {profile.embedding_dims}, got {len(embedding)}"
                    )
                chunk_id = getattr(chunk, "id", None)
                chunk_index = getattr(chunk, "chunk_index", 0)
                metadata = {
                    "purpose": "project_kb",
                    "tenant_id": profile.tenant_id,
                    "project_id": profile.project_id,
                    "document_id": knowledge.id,
                    "knowledge_id": knowledge.id,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_index,
                    "document_name": knowledge.document_name,
                    "embedding_provider": profile.embedding_provider,
                    "embedding_model": profile.embedding_model,
                    "embedding_dims": profile.embedding_dims,
                    "vector_store_index_id": profile.vector_store_index_id,
                }
                records.append(
                    {
                        "message_id": self._project_vector_id(knowledge.id, chunk_id or chunk_index),
                        "sender_key": self._project_sender_key(profile),
                        "text": chunk_text,
                        "embedding": embedding,
                        "metadata": metadata,
                    }
                )

            provider = self._project_external_vector_provider(profile)
            if provider is not None:
                await provider.add_batch(records)
            else:
                persist_dir = getattr(settings, 'CHROMA_DIR', 'data/chroma')
                from chroma_client_factory import get_chroma_client

                client = get_chroma_client(persist_dir)
                collection = client.get_or_create_collection(
                    name=profile.vector_collection_name,
                    metadata={
                        "hnsw:space": "cosine",
                        "purpose": "project_kb",
                        "embedding_dimensions": profile.embedding_dims,
                    },
                )
                collection.upsert(
                    ids=[record["message_id"] for record in records],
                    embeddings=[record["embedding"] for record in records],
                    documents=[record["text"] for record in records],
                    metadatas=[
                        {
                            "sender_key": record["sender_key"],
                            "text": record["text"][:1000],
                            **record["metadata"],
                        }
                        for record in records
                    ],
                )

            self.logger.info(f"Stored {len(embeddings)} embeddings for document {knowledge.document_name}")

        except Exception as e:
            self.logger.error(f"Failed to store embeddings: {e}", exc_info=True)
            raise

    async def _delete_document_embeddings(self, project, doc):
        """Delete embeddings for a document."""
        try:
            import settings
            from models import ProjectKnowledgeChunk

            profile = self._project_profile_from_knowledge(project, doc)
            chunks = self.db.query(ProjectKnowledgeChunk).filter(
                ProjectKnowledgeChunk.knowledge_id == doc.id
            ).order_by(ProjectKnowledgeChunk.chunk_index).all()
            provider = self._project_external_vector_provider(profile)
            if provider is not None:
                for chunk in chunks:
                    try:
                        await provider.delete_message(self._project_vector_id(doc.id, chunk.id))
                    except Exception as exc:
                        self.logger.warning("Failed to delete project vector %s: %s", chunk.id, exc)
                return

            persist_dir = getattr(settings, 'CHROMA_DIR', 'data/chroma')
            from chroma_client_factory import get_chroma_client

            client = get_chroma_client(persist_dir)

            try:
                collection = client.get_collection(name=profile.vector_collection_name)
                ids = [self._project_vector_id(doc.id, chunk.id) for chunk in chunks]
                if ids:
                    collection.delete(ids=ids)
                legacy_ids = [f"{doc.id}_{i}" for i in range(doc.num_chunks or 0)]
                if legacy_ids:
                    collection.delete(ids=legacy_ids)
            except Exception:
                pass

        except Exception as e:
            self.logger.warning(f"Failed to delete embeddings: {e}")

    async def _delete_project_embeddings(self, project):
        """Delete all embeddings for a project."""
        try:
            import settings
            from models import ProjectKnowledge

            collections = {
                self._legacy_project_collection_name(project.id),
            }
            docs = self.db.query(ProjectKnowledge).filter(
                ProjectKnowledge.project_id == project.id
            ).all()
            for doc in docs:
                profile = self._project_profile_from_knowledge(project, doc)
                if self._project_external_vector_provider(profile) is not None:
                    await self._delete_document_embeddings(project, doc)
                    continue
                collections.add(profile.vector_collection_name)

            persist_dir = getattr(settings, 'CHROMA_DIR', 'data/chroma')
            from chroma_client_factory import get_chroma_client

            client = get_chroma_client(persist_dir)
            for collection_name in collections:
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
            import settings
            from agent.memory.providers.base import VectorRecord
            from models import ProjectKnowledge, ProjectKnowledgeChunk

            knowledge_rows = (
                self.db.query(ProjectKnowledge)
                .filter(
                    ProjectKnowledge.project_id == project.id,
                    ProjectKnowledge.status == "completed",
                )
                .all()
            )
            if not knowledge_rows:
                return []

            grouped: Dict[Any, ProjectKnowledgeIndexProfile] = {}
            for row in knowledge_rows:
                profile = self._project_profile_from_knowledge(project, row)
                grouped[profile.grouping_key()] = profile

            persist_dir = getattr(settings, 'CHROMA_DIR', 'data/chroma')
            from chroma_client_factory import get_chroma_client

            client = get_chroma_client(persist_dir)
            formatted: List[Dict[str, Any]] = []
            for profile in grouped.values():
                embedder = self._project_embedding_provider(profile)
                query_embedding = await embedder.embed_text_async(
                    query,
                    task_type="RETRIEVAL_QUERY",
                )
                if len(query_embedding) != profile.embedding_dims:
                    self.logger.warning(
                        "Skipping Project KB profile with query dim mismatch expected=%s actual=%s",
                        profile.embedding_dims,
                        len(query_embedding),
                    )
                    continue

                records: List[VectorRecord] = []
                provider = self._project_external_vector_provider(profile)
                if provider is not None:
                    records = await provider.search_similar(
                        query_embedding,
                        limit=max_results,
                        sender_key=self._project_sender_key(profile),
                    )
                else:
                    try:
                        collection = client.get_collection(name=profile.vector_collection_name)
                    except Exception:
                        continue
                    if collection.count() == 0:
                        continue
                    raw = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=max_results,
                    )
                    if raw.get("ids") and raw["ids"][0]:
                        for index in range(len(raw["ids"][0])):
                            meta = raw["metadatas"][0][index] if raw.get("metadatas") else {}
                            records.append(
                                VectorRecord(
                                    message_id=raw["ids"][0][index],
                                    text=raw["documents"][0][index] if raw.get("documents") else "",
                                    distance=raw["distances"][0][index] if raw.get("distances") else 0.0,
                                    sender_key=meta.get("sender_key"),
                                    metadata=meta or {},
                                )
                            )

                for record in records:
                    metadata = record.metadata or {}
                    is_legacy_profile = (
                        profile.index_version == 0
                        or profile.vector_collection_name == self._legacy_project_collection_name(project.id)
                    )
                    if not is_legacy_profile:
                        if metadata.get("purpose") != "project_kb":
                            continue
                        if str(metadata.get("tenant_id") or "") != str(profile.tenant_id):
                            continue
                        if int(metadata.get("project_id") or 0) != project.id:
                            continue
                    chunk_id = metadata.get("chunk_id")
                    if not chunk_id:
                        continue
                    chunk = self.db.query(ProjectKnowledgeChunk).get(int(chunk_id))
                    if not chunk:
                        continue
                    knowledge = self.db.query(ProjectKnowledge).get(chunk.knowledge_id)
                    if not knowledge or knowledge.project_id != project.id:
                        continue
                    similarity = 1.0 / (1.0 + float(record.distance or 0.0))
                    formatted.append(
                        {
                            "content": chunk.content,
                            "metadata": metadata,
                            "similarity": similarity,
                            "document_id": knowledge.id,
                            "document_name": knowledge.document_name,
                            "chunk_id": chunk.id,
                            "chunk_index": chunk.chunk_index,
                        }
                    )

            formatted.sort(key=lambda item: item["similarity"], reverse=True)
            return formatted[:max_results]

        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            return []
