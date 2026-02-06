"""
Phase 14.4: Projects API Routes
Phase 15: Skill Projects - Added session management and agent access endpoints

RESTful API for project management, knowledge bases, and conversations.
"""

import os
import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from models_rbac import User
from auth_dependencies import get_current_user_required
from services.project_service import ProjectService
from services.project_command_service import ProjectCommandService

router = APIRouter(tags=["Projects"])

# Security constants for file uploads
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB max file size
MAX_FILENAME_LENGTH = 255


def secure_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal and other attacks.
    """
    if not filename:
        return "document"

    # Remove path components
    filename = os.path.basename(filename)

    # Remove null bytes and control characters
    filename = filename.replace('\x00', '').replace('\r', '').replace('\n', '')

    # Keep only safe characters
    filename = re.sub(r'[^\w\s\-\.]', '_', filename)

    # Remove leading/trailing dots and spaces
    filename = filename.strip('. ')

    # Prevent double extensions
    parts = filename.rsplit('.', 1)
    if len(parts) == 2:
        name, ext = parts
        name = name.replace('.', '_')
        filename = f"{name}.{ext}"

    # Truncate if too long
    if len(filename) > MAX_FILENAME_LENGTH:
        name, ext = os.path.splitext(filename)
        max_name_len = MAX_FILENAME_LENGTH - len(ext)
        filename = name[:max_name_len] + ext

    if not filename or filename == '.':
        return "document"

    return filename


# ============================================================================
# Request/Response Models
# ============================================================================

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon: str = "folder"
    color: str = "blue"
    agent_id: Optional[int] = None
    system_prompt_override: Optional[str] = None
    agent_ids: Optional[List[int]] = None  # Phase 15: Agent access list
    # Phase 16: KB Configuration
    kb_chunk_size: int = 500
    kb_chunk_overlap: int = 50
    kb_embedding_model: str = "all-MiniLM-L6-v2"
    # Phase 16: Memory Configuration
    enable_semantic_memory: bool = True
    semantic_memory_results: int = 10
    semantic_similarity_threshold: float = 0.5
    enable_factual_memory: bool = True
    factual_extraction_threshold: int = 5


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    agent_id: Optional[int] = None
    system_prompt_override: Optional[str] = None
    enabled_tools: Optional[List[str]] = None
    enabled_sandboxed_tools: Optional[List[int]] = None
    is_archived: Optional[bool] = None
    agent_ids: Optional[List[int]] = None  # Phase 15: Agent access list
    # Phase 16: KB Configuration
    kb_chunk_size: Optional[int] = None
    kb_chunk_overlap: Optional[int] = None
    kb_embedding_model: Optional[str] = None
    # Phase 16: Memory Configuration
    enable_semantic_memory: Optional[bool] = None
    semantic_memory_results: Optional[int] = None
    semantic_similarity_threshold: Optional[float] = None
    enable_factual_memory: Optional[bool] = None
    factual_extraction_threshold: Optional[int] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    icon: str
    color: str
    agent_id: Optional[int]
    creator_id: Optional[int] = None  # Phase 15: Creator tracking
    agent_ids: Optional[List[int]] = None  # Phase 15: Agents with access
    system_prompt_override: Optional[str]
    enabled_tools: List[str]
    enabled_sandboxed_tools: List[int]
    is_archived: bool
    conversation_count: Optional[int] = None
    document_count: Optional[int] = None
    # Phase 16: KB Configuration
    kb_chunk_size: int = 500
    kb_chunk_overlap: int = 50
    kb_embedding_model: str = "all-MiniLM-L6-v2"
    # Phase 16: Memory Configuration
    enable_semantic_memory: bool = True
    semantic_memory_results: int = 10
    semantic_similarity_threshold: float = 0.5
    enable_factual_memory: bool = True
    factual_extraction_threshold: int = 5
    # Phase 16: Memory stats
    fact_count: int = 0
    semantic_memory_count: int = 0
    created_at: Optional[str]
    updated_at: Optional[str]


# Phase 15: Session Management Models
class ProjectSessionResponse(BaseModel):
    """Response for project session endpoints."""
    session_id: Optional[int] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    agent_id: int
    channel: str
    conversation_id: Optional[int] = None
    entered_at: Optional[str] = None
    is_in_project: bool = False


class EnterProjectRequest(BaseModel):
    """Request to enter a project."""
    agent_id: int
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    channel: str = "playground"


class ExitProjectRequest(BaseModel):
    """Request to exit current project."""
    agent_id: int
    channel: str = "playground"


class AgentAccessResponse(BaseModel):
    """Response for agent access endpoints."""
    agent_id: int
    agent_name: str
    can_write: bool


class UpdateAgentAccessRequest(BaseModel):
    """Request to update agent access for a project."""
    agent_ids: List[int]


class CommandPatternResponse(BaseModel):
    """Response for command pattern endpoints."""
    id: int
    command_type: str
    language_code: str
    pattern: str
    response_template: Optional[str]
    is_active: bool


class CommandPatternCreate(BaseModel):
    """Request to create a custom command pattern."""
    command_type: str
    language_code: str
    pattern: str
    response_template: Optional[str] = None


class ConversationCreate(BaseModel):
    title: Optional[str] = None


class ConversationMessage(BaseModel):
    role: str
    content: str
    timestamp: str


class ConversationResponse(BaseModel):
    id: int
    project_id: int
    title: Optional[str]
    message_count: int
    messages: List[ConversationMessage]
    is_archived: bool
    created_at: Optional[str]
    updated_at: Optional[str]


class SendMessageRequest(BaseModel):
    message: str


class DocumentResponse(BaseModel):
    id: int
    name: str
    type: str
    size_bytes: int
    num_chunks: int
    status: str
    error: Optional[str] = None
    upload_date: Optional[str] = None


# ============================================================================
# Project CRUD Routes
# ============================================================================

@router.get("/api/projects", response_model=List[ProjectResponse])
async def list_projects(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """List all projects for the current user."""
    service = ProjectService(db)
    projects = await service.get_projects(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        include_archived=include_archived
    )
    return [ProjectResponse(**p) for p in projects]


@router.post("/api/projects", response_model=ProjectResponse)
async def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Create a new project.

    Phase 15: Projects are now tenant-scoped. Optionally specify agent_ids
    to control which agents have access to the project.
    Phase 16: Added KB and memory configuration parameters.
    """
    service = ProjectService(db)
    result = await service.create_project(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        icon=data.icon,
        color=data.color,
        agent_id=data.agent_id,
        system_prompt_override=data.system_prompt_override,
        agent_ids=data.agent_ids,  # Phase 15: Agent access list
        # Phase 16: KB Configuration
        kb_chunk_size=data.kb_chunk_size,
        kb_chunk_overlap=data.kb_chunk_overlap,
        kb_embedding_model=data.kb_embedding_model,
        # Phase 16: Memory Configuration
        enable_semantic_memory=data.enable_semantic_memory,
        semantic_memory_results=data.semantic_memory_results,
        semantic_similarity_threshold=data.semantic_similarity_threshold,
        enable_factual_memory=data.enable_factual_memory,
        factual_extraction_threshold=data.factual_extraction_threshold
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return ProjectResponse(**result["project"])


@router.get("/api/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Get a specific project."""
    service = ProjectService(db)
    project = await service.get_project(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        project_id=project_id
    )

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectResponse(**project)


@router.put("/api/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Update a project."""
    service = ProjectService(db)
    result = await service.update_project(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        project_id=project_id,
        updates=data.dict(exclude_none=True)
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return ProjectResponse(**result["project"])


@router.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Delete a project and all its data."""
    service = ProjectService(db)
    result = await service.delete_project(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        project_id=project_id
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


# ============================================================================
# Project Knowledge Routes
# ============================================================================

@router.post("/api/projects/{project_id}/knowledge/upload", response_model=DocumentResponse)
async def upload_project_document(
    project_id: int,
    file: UploadFile = File(...),
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Upload a document to project knowledge base (requires authentication).

    Max file size: 50 MB
    """
    from models import Project

    service = ProjectService(db)

    try:
        # Get project and verify user has access (same tenant)
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Verify tenant access (unless global admin)
        if not current_user.is_global_admin and project.tenant_id != current_user.tenant_id:
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Read file with size validation
        file_data = await file.read()

        # Validate file size
        if len(file_data) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024*1024)} MB"
            )

        # Sanitize filename to prevent path traversal
        filename = secure_filename(file.filename or "document")

        result = await service.upload_project_document(
            tenant_id=current_user.tenant_id or project.tenant_id,
            user_id=current_user.id,
            project_id=project_id,
            file_data=file_data,
            filename=filename,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("error"))

        return DocumentResponse(**result["document"])

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/projects/{project_id}/knowledge", response_model=List[DocumentResponse])
async def list_project_documents(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """List all documents in project knowledge base."""
    service = ProjectService(db)
    documents = await service.get_project_documents(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        project_id=project_id
    )
    return [DocumentResponse(**d) for d in documents]


@router.get("/api/projects/{project_id}/knowledge/{doc_id}/chunks")
async def get_project_knowledge_chunks(
    project_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Get chunks for a project knowledge document."""
    from models import ProjectKnowledgeChunk

    service = ProjectService(db)

    # Verify project access
    project = await service.get_project(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        project_id=project_id
    )

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get chunks
    chunks = db.query(ProjectKnowledgeChunk).filter(
        ProjectKnowledgeChunk.knowledge_id == doc_id
    ).order_by(ProjectKnowledgeChunk.chunk_index).all()

    return [
        {
            "id": chunk.id,
            "knowledge_id": chunk.knowledge_id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "char_count": chunk.char_count,
            "metadata_json": chunk.metadata_json or {}
        }
        for chunk in chunks
    ]


@router.post("/api/projects/{project_id}/knowledge/{doc_id}/regenerate-embeddings")
async def regenerate_document_embeddings(
    project_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Regenerate embeddings for a project knowledge document."""
    service = ProjectService(db)

    result = await service.regenerate_document_embeddings(
        tenant_id=current_user.tenant_id,
        project_id=project_id,
        doc_id=doc_id
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.delete("/api/projects/{project_id}/knowledge/{doc_id}")
async def delete_project_document(
    project_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Delete a document from project knowledge base."""
    service = ProjectService(db)
    result = await service.delete_project_document(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        project_id=project_id,
        doc_id=doc_id
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


# ============================================================================
# Project Conversation Routes
# ============================================================================

@router.get("/api/projects/{project_id}/conversations", response_model=List[ConversationResponse])
async def list_project_conversations(
    project_id: int,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """List all conversations in a project."""
    service = ProjectService(db)
    conversations = await service.get_conversations(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        project_id=project_id,
        include_archived=include_archived
    )
    return [ConversationResponse(**c) for c in conversations]


@router.post("/api/projects/{project_id}/conversations", response_model=ConversationResponse)
async def create_project_conversation(
    project_id: int,
    data: ConversationCreate = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Create a new conversation in project."""
    service = ProjectService(db)
    result = await service.create_conversation(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        project_id=project_id,
        title=data.title if data else None
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return ConversationResponse(**result["conversation"])


@router.get("/api/projects/{project_id}/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_project_conversation(
    project_id: int,
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Get a specific conversation."""
    service = ProjectService(db)
    conversation = await service.get_conversation(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        project_id=project_id,
        conversation_id=conversation_id
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationResponse(**conversation)


@router.post("/api/projects/{project_id}/conversations/{conversation_id}/chat")
async def send_project_message(
    project_id: int,
    conversation_id: int,
    data: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Send a message in project conversation."""
    service = ProjectService(db)
    result = await service.send_message(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        project_id=project_id,
        conversation_id=conversation_id,
        message=data.message
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.delete("/api/projects/{project_id}/conversations/{conversation_id}")
async def delete_project_conversation(
    project_id: int,
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Delete a conversation."""
    service = ProjectService(db)
    result = await service.delete_conversation(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        project_id=project_id,
        conversation_id=conversation_id
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


# ============================================================================
# Phase 15: Skill Projects - Session Management Routes
# ============================================================================

@router.get("/api/playground/project-session", response_model=ProjectSessionResponse)
async def get_project_session(
    agent_id: int,
    channel: str = "playground",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 15: Get current project session for user.

    Returns the active project session if user is in a project context.
    Optimized with JOIN to reduce query count.
    """
    from models import UserProjectSession, Project
    from sqlalchemy.orm import joinedload

    # Query for ANY session for this user+agent+channel, regardless of thread-specific sender_key format
    # The sender_key can be either "playground_user_4" or "playground_u4_a1_t153" depending on thread context
    # We use LIKE to match both formats and order by updated_at DESC to get the most recent
    sender_key_pattern = f"playground_%{current_user.id}%"

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[PROJECT SESSION] Querying with pattern: {sender_key_pattern}, agent_id: {agent_id}, tenant: {current_user.tenant_id}")

    # Optimized: Single query with JOIN instead of two separate queries
    # Order by updated_at DESC to prioritize the most recently active session
    result = db.query(UserProjectSession, Project).outerjoin(
        Project, UserProjectSession.project_id == Project.id
    ).filter(
        UserProjectSession.tenant_id == current_user.tenant_id,
        UserProjectSession.sender_key.like(sender_key_pattern),
        UserProjectSession.agent_id == agent_id,
        UserProjectSession.channel == channel,
        UserProjectSession.project_id.isnot(None)  # Only get sessions with active projects
    ).order_by(UserProjectSession.updated_at.desc()).first()

    logger.info(f"[PROJECT SESSION] Query result: {result}")
    if result and result[0]:
        logger.info(f"[PROJECT SESSION] Found session: sender_key={result[0].sender_key}, project_id={result[0].project_id}")

    if not result or not result[0] or not result[0].project_id:
        logger.info(f"[PROJECT SESSION] No active project session found")
        return ProjectSessionResponse(
            agent_id=agent_id,
            channel=channel,
            is_in_project=False
        )

    session, project = result

    return ProjectSessionResponse(
        session_id=session.id,
        project_id=session.project_id,
        project_name=project.name if project else None,
        agent_id=session.agent_id,
        channel=session.channel,
        conversation_id=session.conversation_id,
        entered_at=session.entered_at.isoformat() if session.entered_at else None,
        is_in_project=True
    )


@router.post("/api/playground/project-session/enter", response_model=ProjectSessionResponse)
async def enter_project_session(
    data: EnterProjectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 15: Enter a project session.

    Creates or updates the user's project session for the specified agent/channel.
    """
    command_service = ProjectCommandService(db)
    sender_key = f"playground_user_{current_user.id}"

    # Determine project identifier
    project_identifier = data.project_name or str(data.project_id) if data.project_id else None

    if not project_identifier:
        raise HTTPException(status_code=400, detail="Must provide project_id or project_name")

    result = await command_service.execute_enter(
        tenant_id=current_user.tenant_id,
        sender_key=sender_key,
        agent_id=data.agent_id,
        channel=data.channel,
        project_identifier=project_identifier
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return ProjectSessionResponse(
        project_id=result.get("project_id"),
        project_name=result.get("project_name"),
        agent_id=data.agent_id,
        channel=data.channel,
        conversation_id=result.get("conversation_id"),
        is_in_project=True
    )


@router.post("/api/playground/project-session/exit")
async def exit_project_session(
    data: ExitProjectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 15: Exit current project session.

    Clears the user's project session for the specified agent/channel.
    Returns a summary of the conversation if available.
    """
    command_service = ProjectCommandService(db)
    sender_key = f"playground_user_{current_user.id}"

    result = await command_service.execute_exit(
        tenant_id=current_user.tenant_id,
        sender_key=sender_key,
        agent_id=data.agent_id,
        channel=data.channel
    )

    if result.get("status") == "not_in_project":
        return {"status": "success", "message": "Not currently in a project"}

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


# ============================================================================
# Phase 15: Skill Projects - Agent Access Management Routes
# ============================================================================

@router.get("/api/projects/{project_id}/agents", response_model=List[AgentAccessResponse])
async def get_project_agents(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 15: Get agents with access to a project.
    """
    from models import Project, AgentProjectAccess, Agent, Contact

    # Verify project exists in tenant
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.tenant_id == current_user.tenant_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get agent access records
    access_records = db.query(AgentProjectAccess).filter(
        AgentProjectAccess.project_id == project_id
    ).all()

    result = []
    for access in access_records:
        agent = db.query(Agent).filter(Agent.id == access.agent_id).first()
        if agent:
            # Get agent name from contact
            contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
            agent_name = contact.friendly_name if contact else f"Agent {agent.id}"

            result.append(AgentAccessResponse(
                agent_id=agent.id,
                agent_name=agent_name,
                can_write=access.can_write
            ))

    return result


@router.put("/api/projects/{project_id}/agents")
async def update_project_agents(
    project_id: int,
    data: UpdateAgentAccessRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 15: Update agent access for a project.

    Replaces all agent access with the provided list.
    """
    from models import Project, AgentProjectAccess

    # Verify project exists in tenant
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.tenant_id == current_user.tenant_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Remove existing access
    db.query(AgentProjectAccess).filter(
        AgentProjectAccess.project_id == project_id
    ).delete()

    # Add new access records
    for agent_id in data.agent_ids:
        access = AgentProjectAccess(
            agent_id=agent_id,
            project_id=project_id,
            can_write=True
        )
        db.add(access)

    db.commit()

    return {"status": "success", "agent_ids": data.agent_ids}


# ============================================================================
# Phase 15: Skill Projects - Command Pattern Routes
# ============================================================================

@router.get("/api/project-commands", response_model=List[CommandPatternResponse])
async def list_command_patterns(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 15: List command patterns for the tenant.

    Returns tenant-specific patterns, falling back to system defaults.
    """
    from models import ProjectCommandPattern

    patterns = db.query(ProjectCommandPattern).filter(
        ProjectCommandPattern.tenant_id.in_([current_user.tenant_id, "_system"]),
        ProjectCommandPattern.is_active == True
    ).all()

    # Group by command_type+language, preferring tenant-specific
    seen = set()
    result = []

    # Sort to get tenant-specific first
    sorted_patterns = sorted(patterns, key=lambda p: 0 if p.tenant_id == current_user.tenant_id else 1)

    for pattern in sorted_patterns:
        key = f"{pattern.command_type}_{pattern.language_code}"
        if key in seen and pattern.tenant_id == "_system":
            continue

        result.append(CommandPatternResponse(
            id=pattern.id,
            command_type=pattern.command_type,
            language_code=pattern.language_code,
            pattern=pattern.pattern,
            response_template=pattern.response_template,
            is_active=pattern.is_active
        ))
        seen.add(key)

    return result


@router.post("/api/project-commands", response_model=CommandPatternResponse)
async def create_command_pattern(
    data: CommandPatternCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 15: Create a custom command pattern for the tenant.

    Tenant-specific patterns override system defaults.
    """
    from models import ProjectCommandPattern
    import re

    # Validate regex pattern
    try:
        re.compile(data.pattern)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid regex pattern: {e}")

    # Check for existing pattern
    existing = db.query(ProjectCommandPattern).filter(
        ProjectCommandPattern.tenant_id == current_user.tenant_id,
        ProjectCommandPattern.command_type == data.command_type,
        ProjectCommandPattern.language_code == data.language_code
    ).first()

    if existing:
        # Update existing pattern
        existing.pattern = data.pattern
        existing.response_template = data.response_template
        existing.is_active = True
        db.commit()

        # Invalidate cache
        command_service = ProjectCommandService(db)
        command_service.invalidate_cache(current_user.tenant_id)

        return CommandPatternResponse(
            id=existing.id,
            command_type=existing.command_type,
            language_code=existing.language_code,
            pattern=existing.pattern,
            response_template=existing.response_template,
            is_active=existing.is_active
        )

    # Create new pattern
    pattern = ProjectCommandPattern(
        tenant_id=current_user.tenant_id,
        command_type=data.command_type,
        language_code=data.language_code,
        pattern=data.pattern,
        response_template=data.response_template,
        is_active=True
    )
    db.add(pattern)
    db.commit()
    db.refresh(pattern)

    # Invalidate cache
    command_service = ProjectCommandService(db)
    command_service.invalidate_cache(current_user.tenant_id)

    return CommandPatternResponse(
        id=pattern.id,
        command_type=pattern.command_type,
        language_code=pattern.language_code,
        pattern=pattern.pattern,
        response_template=pattern.response_template,
        is_active=pattern.is_active
    )


@router.delete("/api/project-commands/{pattern_id}")
async def delete_command_pattern(
    pattern_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 15: Delete a custom command pattern.

    Can only delete tenant-specific patterns, not system defaults.
    """
    from models import ProjectCommandPattern

    pattern = db.query(ProjectCommandPattern).filter(
        ProjectCommandPattern.id == pattern_id,
        ProjectCommandPattern.tenant_id == current_user.tenant_id
    ).first()

    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found or is a system default")

    db.delete(pattern)
    db.commit()

    # Invalidate cache
    command_service = ProjectCommandService(db)
    command_service.invalidate_cache(current_user.tenant_id)

    return {"status": "success", "message": "Pattern deleted"}


# ============================================================================
# Phase 16: Project Memory Management API
# ============================================================================

class FactCreate(BaseModel):
    """Request to create/update a fact."""
    topic: str
    key: str
    value: str
    sender_key: Optional[str] = None
    confidence: float = 1.0
    source: str = "manual"


class FactResponse(BaseModel):
    """Response for fact endpoints."""
    id: int
    topic: str
    key: str
    value: str
    sender_key: Optional[str]
    confidence: float
    source: str
    created_at: Optional[str]
    updated_at: Optional[str]


class MemoryStatsResponse(BaseModel):
    """Response for memory statistics."""
    semantic_memory_count: int
    fact_count: int
    kb_document_count: int
    conversation_count: int
    unique_users: int
    fact_topics: Dict[str, int]


class SemanticMemoryResponse(BaseModel):
    """Response for semantic memory list."""
    total: int
    memories: List[Dict[str, Any]]


class ClearMemoryResponse(BaseModel):
    """Response for clear memory operations."""
    status: str
    deleted_count: int


@router.get("/api/projects/{project_id}/memory/stats", response_model=MemoryStatsResponse)
async def get_project_memory_stats(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 16: Get comprehensive memory statistics for a project.
    """
    from services.project_memory_service import ProjectMemoryService

    # Verify project access
    service = ProjectService(db)
    project = await service.get_project(current_user.tenant_id, current_user.id, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    memory_service = ProjectMemoryService(db)
    stats = await memory_service.get_memory_stats(project_id)

    return MemoryStatsResponse(**stats)


@router.get("/api/projects/{project_id}/memory/facts", response_model=List[FactResponse])
async def list_project_facts(
    project_id: int,
    topic: Optional[str] = None,
    sender_key: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 16: List facts for a project.
    Optionally filter by topic or sender.
    """
    from services.project_memory_service import ProjectMemoryService

    # Verify project access
    service = ProjectService(db)
    project = await service.get_project(current_user.tenant_id, current_user.id, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    memory_service = ProjectMemoryService(db)
    facts = await memory_service.get_facts(
        project_id=project_id,
        sender_key=sender_key,
        topic=topic,
        include_project_wide=True
    )

    return [FactResponse(**f) for f in facts]


@router.post("/api/projects/{project_id}/memory/facts", response_model=Dict[str, Any])
async def add_project_fact(
    project_id: int,
    data: FactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 16: Add or update a fact for a project.
    """
    from services.project_memory_service import ProjectMemoryService

    # Verify project access
    service = ProjectService(db)
    project = await service.get_project(current_user.tenant_id, current_user.id, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    memory_service = ProjectMemoryService(db)
    result = await memory_service.add_fact(
        project_id=project_id,
        topic=data.topic,
        key=data.key,
        value=data.value,
        sender_key=data.sender_key,
        confidence=data.confidence,
        source=data.source
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.delete("/api/projects/{project_id}/memory/facts/{fact_id}")
async def delete_project_fact(
    project_id: int,
    fact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 16: Delete a specific fact from a project.
    """
    from services.project_memory_service import ProjectMemoryService

    # Verify project access
    service = ProjectService(db)
    project = await service.get_project(current_user.tenant_id, current_user.id, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    memory_service = ProjectMemoryService(db)
    result = await memory_service.delete_fact(fact_id, project_id)

    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("error"))

    return result


@router.delete("/api/projects/{project_id}/memory/facts", response_model=ClearMemoryResponse)
async def clear_project_facts(
    project_id: int,
    topic: Optional[str] = None,
    sender_key: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 16: Clear facts for a project.
    Optionally filter by topic or sender to selectively clear.
    """
    from services.project_memory_service import ProjectMemoryService

    # Verify project access
    service = ProjectService(db)
    project = await service.get_project(current_user.tenant_id, current_user.id, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    memory_service = ProjectMemoryService(db)
    result = await memory_service.clear_facts(
        project_id=project_id,
        sender_key=sender_key,
        topic=topic
    )

    return ClearMemoryResponse(**result)


@router.get("/api/projects/{project_id}/memory/semantic", response_model=SemanticMemoryResponse)
async def list_project_semantic_memory(
    project_id: int,
    sender_key: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 16: List semantic memory (conversation history) for a project.
    """
    from services.project_memory_service import ProjectMemoryService

    # Verify project access
    service = ProjectService(db)
    project = await service.get_project(current_user.tenant_id, current_user.id, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    memory_service = ProjectMemoryService(db)
    result = await memory_service.list_semantic_memory(
        project_id=project_id,
        sender_key=sender_key,
        limit=limit,
        offset=offset
    )

    return SemanticMemoryResponse(**result)


@router.delete("/api/projects/{project_id}/memory/semantic", response_model=ClearMemoryResponse)
async def clear_project_semantic_memory(
    project_id: int,
    sender_key: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 16: Clear semantic memory (conversation history) for a project.
    Optionally filter by sender to only clear specific user's history.
    """
    from services.project_memory_service import ProjectMemoryService

    # Verify project access
    service = ProjectService(db)
    project = await service.get_project(current_user.tenant_id, current_user.id, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    memory_service = ProjectMemoryService(db)
    result = await memory_service.clear_semantic_memory(
        project_id=project_id,
        sender_key=sender_key
    )

    return ClearMemoryResponse(**result)


@router.get("/api/projects/{project_id}/memory/export")
async def export_project_memory(
    project_id: int,
    include_semantic: bool = True,
    include_facts: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 16: Export all project memory as JSON.
    Useful for backup or analysis.
    """
    from services.project_memory_service import ProjectMemoryService

    # Verify project access
    service = ProjectService(db)
    project = await service.get_project(current_user.tenant_id, current_user.id, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    memory_service = ProjectMemoryService(db)
    export_data = await memory_service.export_memory(
        project_id=project_id,
        include_semantic=include_semantic,
        include_facts=include_facts
    )

    return export_data
