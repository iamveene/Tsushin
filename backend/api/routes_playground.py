"""
Playground API Routes
Handles UI-based chat interactions with agents.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import json as json_lib

from db import get_db

logger = logging.getLogger(__name__)
from auth_dependencies import require_permission, get_current_user_required
from models_rbac import User
from models import Agent, Contact
from services.playground_service import PlaygroundService
from services.project_command_service import ProjectCommandService

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class KBUsageItem(BaseModel):
    """Knowledge Base usage item for a single document chunk"""
    document_name: str
    similarity: float
    chunk_index: int


class PlaygroundChatRequest(BaseModel):
    agent_id: int = Field(..., description="Agent ID to interact with")
    message: str = Field(..., description="User message content")
    thread_id: Optional[int] = Field(None, description="Thread ID for conversation isolation")


class PlaygroundChatResponse(BaseModel):
    status: str
    message: Optional[str] = None
    error: Optional[str] = None
    tool_used: Optional[str] = None
    execution_time: Optional[float] = None
    agent_name: Optional[str] = None
    timestamp: str
    thread_renamed: Optional[bool] = None  # Indicates if thread was auto-renamed
    new_thread_title: Optional[str] = None  # New thread title after auto-rename
    kb_used: Optional[List[KBUsageItem]] = None  # KB usage tracking
    action: Optional[str] = None  # For command actions (e.g., project_entered, project_exited)
    data: Optional[Dict[str, Any]] = None  # For command data (e.g., project info)


class PlaygroundMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: str
    message_id: Optional[str] = None
    is_bookmarked: bool = False
    is_edited: bool = False
    edited_at: Optional[str] = None
    bookmarked_at: Optional[str] = None
    original_content: Optional[str] = None
    kb_used: Optional[List[KBUsageItem]] = None  # KB usage tracking


class PlaygroundHistoryResponse(BaseModel):
    messages: List[PlaygroundMessage]
    agent_name: str


class PlaygroundAgentInfo(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_active: bool


class ClearHistoryResponse(BaseModel):
    success: bool
    message: str


# ============================================================================
# Playground Endpoints
# ============================================================================

@router.get("/api/playground/agents", response_model=List[PlaygroundAgentInfo])
async def get_available_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Get list of agents available for playground interaction.
    Returns all active agents that have playground channel enabled.

    HIGH-011 Fix: Added tenant_id filter to prevent cross-tenant agent enumeration.
    """
    import json

    try:
        # HIGH-011: Get only active agents belonging to user's tenant
        agents = db.query(Agent).filter(
            Agent.is_active == True,
            Agent.tenant_id == current_user.tenant_id
        ).all()

        result = []
        for agent in agents:
            # Phase 10: Check if playground channel is enabled
            enabled_channels = agent.enabled_channels if isinstance(agent.enabled_channels, list) else (
                json.loads(agent.enabled_channels) if agent.enabled_channels else ["playground", "whatsapp"]
            )
            if "playground" not in enabled_channels:
                continue  # Skip agents without playground enabled

            # Get agent name from contact
            contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
            agent_name = contact.friendly_name if contact else f"Agent {agent.id}"

            # Extract description from system prompt (first line)
            description = None
            if agent.system_prompt:
                first_line = agent.system_prompt.split('\n')[0]
                if len(first_line) < 200:
                    description = first_line

            result.append({
                "id": agent.id,
                "name": agent_name,
                "description": description,
                "is_active": agent.is_active
            })

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch agents: {str(e)}")


@router.post("/api/playground/chat", response_model=PlaygroundChatResponse)
async def send_chat_message(
    request: PlaygroundChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Send a message to an agent and get a response.
    Messages are stored in agent memory for consistency with WhatsApp.
    Supports project commands (/list, /enter, /exit, /help) when integrated with Skill Projects.
    """
    try:
        # Phase 15: Check for project commands first
        # Create a sender_key for the Playground user
        sender_key = f"playground_user_{current_user.id}"

        # HIGH-011: Get agent with tenant validation to prevent cross-tenant access
        agent = db.query(Agent).filter(
            Agent.id == request.agent_id,
            Agent.tenant_id == current_user.tenant_id
        ).first()
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {request.agent_id} not found")

        tenant_id = agent.tenant_id

        # Get agent name from contact
        agent_contact = db.query(Contact).filter(Contact.id == agent.contact_id).first() if agent.contact_id else None
        agent_name = agent_contact.friendly_name if agent_contact else f"Agent {agent.id}"

        # Initialize ProjectCommandService (doesn't need memory manager for command detection)
        command_service = ProjectCommandService(db)

        # Check if this is a project command
        command_detection = await command_service.detect_command(tenant_id, request.message)

        if command_detection:
            command_type, command_data = command_detection
            response_template = command_data.get("response_template")

            # Dispatch to appropriate execute method
            if command_type == "list":
                result = await command_service.execute_list(
                    tenant_id=tenant_id,
                    sender_key=sender_key,
                    agent_id=request.agent_id,
                    response_template=response_template
                )
                return PlaygroundChatResponse(
                    status="success",
                    message=result.get("response", "No projects found."),
                    agent_name=agent_name,
                    timestamp=datetime.utcnow().isoformat() + "Z"
                )
            elif command_type == "help":
                result = await command_service.execute_help(
                    response_template=response_template
                )
                return PlaygroundChatResponse(
                    status="success",
                    message=result.get("response", "Available commands: /list, /enter, /exit, /help"),
                    agent_name=agent_name,
                    timestamp=datetime.utcnow().isoformat() + "Z"
                )
            elif command_type == "enter":
                # Extract project identifier from the command
                groups = command_data.get("groups", ())
                project_identifier = groups[0] if groups else None
                if project_identifier:
                    result = await command_service.execute_enter(
                        tenant_id=tenant_id,
                        sender_key=sender_key,
                        agent_id=request.agent_id,
                        channel="playground",
                        project_identifier=project_identifier,
                        response_template=response_template
                    )
                    return PlaygroundChatResponse(
                        status="success",
                        message=result.get("message", "Entering project."),
                        agent_name=agent_name,
                        timestamp=datetime.utcnow().isoformat() + "Z",
                        action="project_entered",
                        data={
                            "project_id": result.get("project_id"),
                            "project_name": result.get("project_name")
                        }
                    )
            elif command_type == "exit":
                result = await command_service.execute_exit(
                    tenant_id=tenant_id,
                    sender_key=sender_key,
                    agent_id=request.agent_id,
                    channel="playground",
                    response_template=response_template
                )
                return PlaygroundChatResponse(
                    status="success",
                    message=result.get("message", "Exiting project."),
                    agent_name=agent_name,
                    timestamp=datetime.utcnow().isoformat() + "Z",
                    action="project_exited"
                )
            # BUG-003 Fix: Add /project info command handler
            elif command_type == "info":
                result = await command_service.execute_info(
                    tenant_id=tenant_id,
                    sender_key=sender_key,
                    agent_id=request.agent_id,
                    channel="playground",
                    response_template=response_template
                )
                return PlaygroundChatResponse(
                    status="success",
                    message=result.get("message", "No project info available."),
                    agent_name=agent_name,
                    timestamp=datetime.utcnow().isoformat() + "Z"
                )

        # Not a project command, proceed with normal message handling
        # Initialize playground service
        service = PlaygroundService(db)

        # Send message through service with thread isolation
        result = await service.send_message(
            user_id=current_user.id,
            agent_id=request.agent_id,
            message_text=request.message,
            thread_id=request.thread_id  # Phase 14.1: Thread-specific messaging
        )

        # Auto-rename thread based on first message
        thread_renamed = False
        new_thread_title = None

        if request.thread_id and result.get("status") == "success":
            from services.playground_thread_service import PlaygroundThreadService
            from models import ConversationThread, Memory

            # Check if this is the first user message
            thread = db.query(ConversationThread).filter(
                ConversationThread.id == request.thread_id
            ).first()

            if thread:
                # FIX: Count messages from Memory table (where they're actually stored)
                # NOT from thread.conversation_history (which is always empty)
                memory_sender_key = f"sender_{thread.recipient}"
                memory = db.query(Memory).filter(
                    Memory.agent_id == request.agent_id,
                    Memory.sender_key == memory_sender_key
                ).first()

                message_count = len(memory.messages_json) if memory and memory.messages_json else 0
                logger.info(f"[Auto-rename] Thread {request.thread_id}: memory_key={memory_sender_key}, message_count={message_count}")

                # Only auto-rename after first exchange (2 messages: user + assistant)
                if message_count <= 2:
                    thread_service = PlaygroundThreadService(db)
                    rename_result = await thread_service.auto_rename_thread_from_message(
                        thread_id=request.thread_id,
                        first_message=request.message
                    )

                    if rename_result.get("status") == "success":
                        thread_renamed = True
                        new_thread_title = rename_result.get("new_title")
                        logger.info(f"[Auto-rename] Thread {request.thread_id} renamed to: {new_thread_title}")
                else:
                    logger.info(f"[Auto-rename] Thread {request.thread_id} skipped: already has {message_count} messages")

        # Add auto-rename info to response
        result["thread_renamed"] = thread_renamed
        result["new_thread_title"] = new_thread_title

        return PlaygroundChatResponse(**result)

    except Exception as e:
        return PlaygroundChatResponse(
            status="error",
            error=str(e),
            timestamp=datetime.utcnow().isoformat() + "Z"
        )


@router.get("/api/playground/history/{agent_id}", response_model=PlaygroundHistoryResponse)
async def get_conversation_history(
    agent_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Get conversation history between current user and specified agent.

    HIGH-011 Fix: Added tenant validation to prevent cross-tenant history access.
    """
    try:
        # HIGH-011: Verify agent exists AND belongs to user's tenant
        agent = db.query(Agent).filter(
            Agent.id == agent_id,
            Agent.tenant_id == current_user.tenant_id
        ).first()
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        # Get agent name
        contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
        agent_name = contact.friendly_name if contact else f"Agent {agent_id}"

        # Initialize playground service
        service = PlaygroundService(db)

        # Get conversation history
        messages = await service.get_conversation_history(
            user_id=current_user.id,
            agent_id=agent_id,
            limit=limit
        )

        return PlaygroundHistoryResponse(
            messages=[PlaygroundMessage(**msg) for msg in messages],
            agent_name=agent_name
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")


@router.delete("/api/playground/history/{agent_id}", response_model=ClearHistoryResponse)
async def clear_conversation_history(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Clear conversation history between current user and specified agent.

    HIGH-011 Fix: Added tenant validation to prevent cross-tenant history deletion.
    """
    try:
        # HIGH-011: Verify agent exists AND belongs to user's tenant
        agent = db.query(Agent).filter(
            Agent.id == agent_id,
            Agent.tenant_id == current_user.tenant_id
        ).first()
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        # Initialize playground service
        service = PlaygroundService(db)

        # Clear conversation history
        result = await service.clear_conversation_history(
            user_id=current_user.id,
            agent_id=agent_id
        )

        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to clear history"))

        return ClearHistoryResponse(
            success=True,
            message="Conversation history cleared successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear history: {str(e)}")


class PlaygroundAudioResponse(BaseModel):
    status: str
    transcript: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    response_mode: Optional[str] = None
    audio_url: Optional[str] = None
    audio_duration: Optional[float] = None
    timestamp: str


class AudioCapabilitiesResponse(BaseModel):
    has_transcript: bool
    has_tts: bool
    transcript_mode: str


@router.post("/api/playground/audio", response_model=PlaygroundAudioResponse)
async def upload_audio(
    audio: UploadFile = File(...),
    agent_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Upload audio for transcription and agent response.

    Phase 14.0: Audio Messages on Playground UI
    HIGH-011 Fix: Added tenant validation to prevent cross-tenant audio processing.

    - Transcribes audio using Whisper API
    - Sends transcript to agent for response
    - Returns TTS audio if agent has audio_tts skill
    """
    if agent_id is None:
        return PlaygroundAudioResponse(
            status="error",
            error="agent_id is required",
            timestamp=datetime.utcnow().isoformat() + "Z"
        )

    try:
        # HIGH-011: Verify agent exists AND belongs to user's tenant
        agent = db.query(Agent).filter(
            Agent.id == agent_id,
            Agent.tenant_id == current_user.tenant_id
        ).first()
        if not agent:
            return PlaygroundAudioResponse(
                status="error",
                error=f"Agent {agent_id} not found",
                timestamp=datetime.utcnow().isoformat() + "Z"
            )
        # Read audio data
        audio_data = await audio.read()

        if not audio_data:
            return PlaygroundAudioResponse(
                status="error",
                error="No audio data received",
                timestamp=datetime.utcnow().isoformat() + "Z"
            )

        # Determine audio format from content type or filename
        content_type = audio.content_type or ""
        filename = audio.filename or ""

        # Map content types to formats
        format_map = {
            "audio/webm": "webm",
            "audio/ogg": "ogg",
            "audio/mpeg": "mp3",
            "audio/mp3": "mp3",
            "audio/wav": "wav",
            "audio/x-wav": "wav",
            "audio/m4a": "m4a",
            "audio/x-m4a": "m4a",
            "audio/flac": "flac",
        }

        audio_format = format_map.get(content_type.lower(), "webm")

        # Fallback to extension if content type not recognized
        if audio_format == "webm" and filename:
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if ext in ["ogg", "mp3", "wav", "m4a", "flac", "webm"]:
                audio_format = ext

        # Initialize playground service
        service = PlaygroundService(db)

        # Process audio
        result = await service.process_audio(
            user_id=current_user.id,
            agent_id=agent_id,
            audio_data=audio_data,
            audio_format=audio_format
        )

        return PlaygroundAudioResponse(**result)

    except Exception as e:
        return PlaygroundAudioResponse(
            status="error",
            error=str(e),
            timestamp=datetime.utcnow().isoformat() + "Z"
        )


@router.get("/api/playground/audio/{audio_id}")
async def get_audio_file(
    audio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Serve TTS audio file by ID.

    Phase 14.1: TTS Audio Responses
    """
    from fastapi.responses import FileResponse
    import os

    service = PlaygroundService(db)
    audio_path = service.get_audio_path(audio_id)

    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    # Determine content type from extension
    ext = audio_path.rsplit(".", 1)[-1].lower() if "." in audio_path else "mp3"
    content_types = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "opus": "audio/opus",
        "webm": "audio/webm",
        "m4a": "audio/m4a",
        "flac": "audio/flac",
    }
    content_type = content_types.get(ext, "audio/mpeg")

    return FileResponse(
        audio_path,
        media_type=content_type,
        filename=f"response.{ext}"
    )


@router.get("/api/playground/agents/{agent_id}/audio-capabilities", response_model=AudioCapabilitiesResponse)
async def get_agent_audio_capabilities(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Check agent's audio capabilities (transcript, TTS).

    Phase 14.0: Used by frontend to determine if mic button should be enabled.
    HIGH-011 Fix: Added tenant validation to prevent cross-tenant capability checks.
    """
    # HIGH-011: Verify agent exists AND belongs to user's tenant
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == current_user.tenant_id
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    service = PlaygroundService(db)
    result = await service.check_agent_audio_capabilities(agent_id)
    return AudioCapabilitiesResponse(**result)


# ============================================================================
# Phase 14.2: Document Attachments API
# ============================================================================

class DocumentInfo(BaseModel):
    id: int
    name: str
    type: str
    size_bytes: int
    num_chunks: int
    status: str
    error: Optional[str] = None
    upload_date: Optional[str] = None


class DocumentUploadResponse(BaseModel):
    status: str
    document: Optional[DocumentInfo] = None
    error: Optional[str] = None


class DocumentListResponse(BaseModel):
    documents: List[DocumentInfo]


class DocumentSearchResult(BaseModel):
    content: str
    metadata: dict
    similarity: float


@router.post("/api/playground/documents", response_model=DocumentUploadResponse)
async def upload_playground_document(
    file: UploadFile = File(...),
    agent_id: int = None,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Upload a document for the current Playground conversation.

    Phase 14.2: Document Attachments

    Supported formats: PDF, TXT, CSV, JSON, XLSX, DOCX, MD, RTF
    """
    from services.playground_document_service import PlaygroundDocumentService

    if agent_id is None:
        return DocumentUploadResponse(status="error", error="agent_id is required")

    try:
        file_data = await file.read()
        filename = file.filename or "document"

        service = PlaygroundDocumentService(db)
        result = await service.upload_document(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            agent_id=agent_id,
            file_data=file_data,
            filename=filename,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

        if result.get("status") == "success":
            return DocumentUploadResponse(
                status="success",
                document=DocumentInfo(**result["document"])
            )
        else:
            return DocumentUploadResponse(
                status="error",
                error=result.get("error")
            )

    except Exception as e:
        return DocumentUploadResponse(status="error", error=str(e))


@router.get("/api/playground/documents", response_model=DocumentListResponse)
async def list_playground_documents(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    List all documents for the current conversation.

    Phase 14.2: Document Attachments
    """
    from services.playground_document_service import PlaygroundDocumentService

    service = PlaygroundDocumentService(db)
    documents = await service.get_documents(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        agent_id=agent_id
    )

    return DocumentListResponse(documents=[DocumentInfo(**d) for d in documents])


@router.delete("/api/playground/documents/{doc_id}")
async def delete_playground_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Delete a specific document.

    Phase 14.2: Document Attachments
    """
    from services.playground_document_service import PlaygroundDocumentService

    service = PlaygroundDocumentService(db)
    result = await service.delete_document(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        doc_id=doc_id
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("error"))

    return result


@router.delete("/api/playground/documents")
async def clear_playground_documents(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Clear all documents for the current conversation.

    Phase 14.2: Document Attachments
    """
    from services.playground_document_service import PlaygroundDocumentService

    service = PlaygroundDocumentService(db)
    result = await service.clear_all_documents(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        agent_id=agent_id
    )

    return result


@router.post("/api/playground/documents/search")
async def search_playground_documents(
    agent_id: int,
    query: str,
    max_results: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Search documents using semantic search.

    Phase 14.2: Document Attachments
    """
    from services.playground_document_service import PlaygroundDocumentService

    service = PlaygroundDocumentService(db)
    results = await service.search_documents(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        agent_id=agent_id,
        query=query,
        max_results=max_results
    )

    return {"results": results}


# ============================================================================
# Phase 14.3: Playground Settings API
# ============================================================================

class PlaygroundSettingsSchema(BaseModel):
    documentProcessing: Optional[dict] = None
    audioSettings: Optional[dict] = None
    # BUG-007 Fix: Add modelSettings for per-agent model configuration
    modelSettings: Optional[Dict[str, Dict[str, Any]]] = None  # {agentId: {temperature, maxTokens, streamResponse}}
    audioSettings: Optional[dict] = None


@router.get("/api/playground/settings")
async def get_playground_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Get user's playground settings.

    Phase 14.3: Playground Settings
    """
    from models import PlaygroundUserSettings

    settings = db.query(PlaygroundUserSettings).filter(
        PlaygroundUserSettings.tenant_id == current_user.tenant_id,
        PlaygroundUserSettings.user_id == current_user.id
    ).first()

    if not settings:
        # Return defaults
        return {
            "documentProcessing": {
                "embeddingModel": "all-MiniLM-L6-v2",
                "chunkSize": 500,
                "chunkOverlap": 50,
                "maxDocuments": 10
            },
            "audioSettings": {
                "ttsProvider": "kokoro",
                "ttsVoice": "pf_dora",
                "autoPlayResponses": False
            }
        }

    return settings.settings_json


@router.put("/api/playground/settings")
async def update_playground_settings(
    settings: PlaygroundSettingsSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Update user's playground settings.

    Phase 14.3: Playground Settings
    """
    from models import PlaygroundUserSettings

    existing = db.query(PlaygroundUserSettings).filter(
        PlaygroundUserSettings.tenant_id == current_user.tenant_id,
        PlaygroundUserSettings.user_id == current_user.id
    ).first()

    settings_dict = settings.dict(exclude_none=True)

    if existing:
        # Merge with existing settings
        current_settings = existing.settings_json or {}
        for key, value in settings_dict.items():
            if value is not None:
                current_settings[key] = value
        existing.settings_json = current_settings
        existing.updated_at = datetime.utcnow()
    else:
        # Create new settings
        new_settings = PlaygroundUserSettings(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            settings_json=settings_dict
        )
        db.add(new_settings)

    db.commit()

    # Return updated settings
    if existing:
        return existing.settings_json
    else:
        db.refresh(new_settings)
        return new_settings.settings_json


@router.get("/api/playground/embedding-models")
async def get_available_embedding_models(
    current_user: User = Depends(get_current_user_required)
):
    """
    Get available embedding models.

    Phase 14.3: Playground Settings
    """
    return {
        "models": [
            # Local/Open Source Models (sentence-transformers)
            {
                "id": "all-MiniLM-L6-v2",
                "name": "MiniLM L6 v2",
                "description": "Fast, efficient local model for general use",
                "dimensions": 384,
                "provider": "local"
            },
            {
                "id": "all-mpnet-base-v2",
                "name": "MPNet Base v2",
                "description": "Higher quality local model, slower than MiniLM",
                "dimensions": 768,
                "provider": "local"
            },
            {
                "id": "paraphrase-multilingual-MiniLM-L12-v2",
                "name": "Multilingual MiniLM",
                "description": "Multilingual support (PT/EN/ES), local model",
                "dimensions": 384,
                "provider": "local"
            },
            # OpenAI Models
            {
                "id": "text-embedding-3-small",
                "name": "OpenAI text-embedding-3-small",
                "description": "OpenAI's fast embedding model (requires API key)",
                "dimensions": 1536,
                "provider": "openai",
                "requires_api_key": True
            },
            {
                "id": "text-embedding-3-large",
                "name": "OpenAI text-embedding-3-large",
                "description": "OpenAI's best embedding model (requires API key)",
                "dimensions": 3072,
                "provider": "openai",
                "requires_api_key": True
            },
            {
                "id": "text-embedding-ada-002",
                "name": "OpenAI Ada 002",
                "description": "OpenAI's legacy embedding model (requires API key)",
                "dimensions": 1536,
                "provider": "openai",
                "requires_api_key": True
            },
            # Google Gemini Models
            {
                "id": "text-embedding-004",
                "name": "Gemini text-embedding-004",
                "description": "Google's latest embedding model (requires API key)",
                "dimensions": 768,
                "provider": "gemini",
                "requires_api_key": True
            },
            {
                "id": "embedding-001",
                "name": "Gemini embedding-001",
                "description": "Google's stable embedding model (requires API key)",
                "dimensions": 768,
                "provider": "gemini",
                "requires_api_key": True
            }
        ]
    }


# ============================================================================
# Cockpit Mode - Memory Inspector Endpoints
# ============================================================================

class MemoryLayerResponse(BaseModel):
    """Memory layer data for cockpit inspector."""
    working_memory: List[Dict[str, Any]] = []
    semantic_results: List[Dict[str, Any]] = []
    facts: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {}


class ToolExecutionHistoryItem(BaseModel):
    """Tool execution history item."""
    id: int
    tool_name: str
    command_name: str
    parameters: Dict[str, Any]
    result: Optional[str] = None
    status: str
    execution_time_ms: Optional[int] = None
    created_at: str


class DebugInfoResponse(BaseModel):
    """Debug info for cockpit panel."""
    recent_tool_calls: List[ToolExecutionHistoryItem] = []
    token_usage: Dict[str, Any] = {}
    estimated_cost: float = 0.0  # Estimated cost in USD based on token usage
    last_reasoning: Optional[str] = None
    model_info: Dict[str, Any] = {}


@router.get("/api/playground/memory/{agent_id}", response_model=MemoryLayerResponse)
async def get_memory_layers(
    agent_id: int,
    sender_key: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Get memory layers for cockpit memory inspector.

    BUG-005 Fix: Properly resolves sender_key and queries semantic memory from ChromaDB.

    Returns working memory, semantic memory results, and learned facts
    for the specified agent and sender.
    """
    from models import Memory, Agent, UserContactMapping, UserProjectSession
    from agent.memory.knowledge_service import KnowledgeService

    # Verify agent exists and user has access
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == current_user.tenant_id
    ).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # BUG-PLAYGROUND-003 Fix: Improved sender_key resolution for playground
    # When a specific sender_key is provided (from thread.recipient), use it FIRST
    # This allows Memory Inspector to show thread-specific memory instead of shared contact memory
    possible_keys = []

    # BUG-PLAYGROUND-003: User-provided sender_key takes FIRST priority
    # This enables thread-isolated memory viewing in Memory Inspector
    if sender_key:
        # Try both with and without sender_ prefix
        possible_keys.append(f"sender_{sender_key}")
        possible_keys.append(sender_key)

    # Try to find if user has a contact mapping - used for shared/contact-based memory
    mapping = db.query(UserContactMapping).filter(
        UserContactMapping.user_id == current_user.id
    ).first()
    if mapping:
        contact = db.query(Contact).filter(Contact.id == mapping.contact_id).first()
        if contact:
            # Contact-based memory (shared across threads)
            possible_keys.append(f"contact_{contact.id}")
            # WhatsApp formats
            if contact.phone_number:
                possible_keys.append(f"sender_{contact.phone_number}@s.whatsapp.net")
                possible_keys.append(f"sender_{contact.phone_number}")
                possible_keys.append(contact.phone_number)
            if contact.whatsapp_id:
                possible_keys.append(f"sender_{contact.whatsapp_id}")
                possible_keys.append(contact.whatsapp_id)

    # Playground-specific formats (fallback)
    possible_keys.append(f"sender_playground_user_{current_user.id}")
    possible_keys.append(f"playground_user_{current_user.id}")
    possible_keys.append(f"contact_{current_user.id}")

    # Layer 1: Working Memory (recent messages)
    # BUG-005 Fix: Try all possible sender_key formats
    working_memory = []
    memory_record = None
    resolved_sender_key = possible_keys[0]

    for key in possible_keys:
        memory_record = db.query(Memory).filter(
            Memory.agent_id == agent_id,
            Memory.sender_key == key
        ).first()
        if memory_record:
            resolved_sender_key = key
            break

    sender_key = resolved_sender_key

    if memory_record and memory_record.messages_json:
        working_memory = memory_record.messages_json[-20:]  # Last 20 messages

    # Layer 2: Semantic Memory - BUG-005 Fix: Actually query ChromaDB
    semantic_results = []
    try:
        # Only query if we have recent messages to use as query context
        if working_memory and agent.enable_semantic_search:
            from agent.memory.vector_store_manager import get_vector_store
            import settings

            # Get vector store for this agent
            persist_dir = getattr(settings, 'CHROMA_PERSIST_DIR', 'data/chroma')
            chroma_path = f"{persist_dir}/agent_{agent_id}"

            vector_store = get_vector_store(persist_directory=chroma_path)
            last_message = working_memory[-1].get("content", "") if working_memory else ""

            if last_message and vector_store:
                results = vector_store.search_similar(
                    query_text=last_message,
                    sender_key=sender_key,
                    limit=10
                )

                for result in results:
                    # Calculate similarity from distance
                    distance = result.get('distance', 1.0)
                    similarity = 1 / (1 + distance)

                    semantic_results.append({
                        "content": result.get("text", ""),
                        "similarity": round(similarity, 3),
                        "message_id": result.get("message_id", ""),
                        "role": result.get("role", "user")
                    })
    except Exception as e:
        logger.warning(f"Could not query semantic memory: {e}")

    # Layer 3: Learned Facts
    facts = []
    project_id = None  # Track project_id for fact management

    try:
        knowledge_service = KnowledgeService(db)
        # get_user_facts returns a list of fact dicts with topic, key, value, confidence, id
        user_facts = knowledge_service.get_user_facts(
            agent_id=agent_id,
            user_id=sender_key
        )
        for fact in user_facts:
            facts.append({
                "id": fact.get("id"),
                "topic": fact.get("topic", "unknown"),
                "key": fact.get("key", ""),
                "value": fact.get("value", ""),
                "fact_type": "user",
                "confidence": fact.get("confidence", 1.0),
                "source": "learned"
            })
        logger.info(f"Found {len(facts)} user facts for sender_key={sender_key}, agent_id={agent_id}")
    except Exception as e:
        logger.warning(f"Could not load facts: {e}")
        pass  # Facts may not exist yet

    # BUG-005 Fix: Also check for project facts if user is in a project
    try:
        project_session = db.query(UserProjectSession).filter(
            UserProjectSession.tenant_id == current_user.tenant_id,
            UserProjectSession.sender_key == sender_key,
            UserProjectSession.agent_id == agent_id,
            UserProjectSession.channel == "playground"
        ).first()

        if project_session and project_session.project_id:
            project_id = project_session.project_id
            from models import ProjectFactMemory
            project_facts = db.query(ProjectFactMemory).filter(
                ProjectFactMemory.project_id == project_session.project_id
            ).all()

            for pf in project_facts:
                facts.append({
                    "id": pf.id,
                    "topic": f"[Project] {pf.topic}",
                    "key": pf.key,
                    "value": pf.value,
                    "fact_type": "project",
                    "project_id": pf.project_id,
                    "confidence": pf.confidence if hasattr(pf, 'confidence') else 1.0,
                    "source": pf.source if hasattr(pf, 'source') else "project"
                })
            logger.info(f"Found {len(project_facts)} project facts for project_id={project_session.project_id}")
    except Exception as e:
        logger.warning(f"Could not load project facts: {e}")
        pass  # Project facts may not exist

    # Stats
    stats = {
        "working_memory_count": len(working_memory),
        "semantic_count": len(semantic_results),
        "facts_count": len(facts),
        "sender_key": sender_key,
        "project_id": project_id  # Include project context for fact management
    }

    return MemoryLayerResponse(
        working_memory=working_memory,
        semantic_results=semantic_results,
        facts=facts,
        stats=stats
    )


@router.get("/api/playground/debug/{agent_id}", response_model=DebugInfoResponse)
async def get_debug_info(
    agent_id: int,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Get debug information for cockpit debug panel.

    Returns recent tool calls, token usage, and model info.
    """
    from models import Agent, AgentRun
    from sqlalchemy import text
    import json

    # Verify agent exists
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == current_user.tenant_id
    ).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get recent tool executions from sandboxed_tool_executions table
    # This contains the actual tool calls made by agents
    # Note: Tool executions may have been created before multi-tenancy was implemented,
    # so we include records where tenant_id matches OR is null/default
    tool_calls = []
    try:
        tool_exec_query = text("""
            SELECT
                e.id,
                t.name as tool_name,
                c.command_name,
                e.rendered_command,
                e.status,
                e.output,
                e.execution_time_ms,
                e.created_at
            FROM sandboxed_tool_executions e
            JOIN sandboxed_tools t ON e.tool_id = t.id
            JOIN sandboxed_tool_commands c ON e.command_id = c.id
            WHERE (e.tenant_id = :tenant_id OR e.tenant_id IS NULL OR e.tenant_id = '' OR e.tenant_id = 'default')
            ORDER BY e.created_at DESC
            LIMIT :limit
        """)

        result = db.execute(tool_exec_query, {
            "tenant_id": current_user.tenant_id,
            "limit": limit
        })

        for row in result:
            tool_calls.append(ToolExecutionHistoryItem(
                id=row.id,
                tool_name=row.tool_name,
                command_name=row.command_name or "",
                parameters={"command": row.rendered_command} if row.rendered_command else {},
                result=row.output[:500] if row.output else None,
                status=row.status or "unknown",
                execution_time_ms=row.execution_time_ms,
                created_at=row.created_at if isinstance(row.created_at, str) else row.created_at.isoformat() if row.created_at else ""
            ))
    except Exception as e:
        logger.warning(f"Could not load tool executions: {e}")

    # Get token usage from recent agent runs
    # Parse token_usage_json field which contains {"prompt": X, "completion": Y, "total": Z}
    total_input = 0
    total_output = 0
    total_tokens = 0

    try:
        recent_runs = db.query(AgentRun).join(
            Agent, AgentRun.agent_id == Agent.id
        ).filter(
            AgentRun.agent_id == agent_id,
            Agent.tenant_id == current_user.tenant_id
        ).order_by(AgentRun.created_at.desc()).limit(20).all()

        for run in recent_runs:
            if run.token_usage_json:
                try:
                    # token_usage_json may already be a dict or a JSON string
                    if isinstance(run.token_usage_json, str):
                        usage = json.loads(run.token_usage_json)
                    else:
                        usage = run.token_usage_json

                    total_input += usage.get("prompt", 0) or usage.get("input", 0) or 0
                    total_output += usage.get("completion", 0) or usage.get("output", 0) or 0
                    total_tokens += usage.get("total", 0) or 0
                except (json.JSONDecodeError, TypeError):
                    pass
    except Exception as e:
        logger.warning(f"Could not load token usage: {e}")

    # Calculate estimated cost based on model pricing
    from analytics.token_tracker import MODEL_PRICING

    model_name = agent.model_name or "unknown"
    estimated_cost = 0.0

    pricing = MODEL_PRICING.get(model_name)
    if pricing:
        # Pricing is per 1M tokens
        prompt_cost = (total_input / 1_000_000) * pricing.get("prompt", 0)
        completion_cost = (total_output / 1_000_000) * pricing.get("completion", 0)
        estimated_cost = prompt_cost + completion_cost
    else:
        logger.debug(f"No pricing data for model: {model_name}")

    # Model info
    model_info = {
        "provider": agent.model_provider or "unknown",
        "model": agent.model_name or "unknown",
        "memory_size": agent.memory_size or 10,
        "semantic_search": agent.enable_semantic_search or False
    }

    return DebugInfoResponse(
        recent_tool_calls=tool_calls,
        token_usage={
            "input": total_input,
            "output": total_output,
            "total": total_tokens
        },
        estimated_cost=round(estimated_cost, 6),  # Round to 6 decimal places for precision
        last_reasoning=None,
        model_info=model_info
    )


class AvailableToolResponse(BaseModel):
    """Available tool for sandbox."""
    id: int
    name: str
    tool_type: str
    description: Optional[str] = None
    commands: List[Dict[str, Any]] = []


@router.get("/api/playground/tools/{agent_id}", response_model=List[AvailableToolResponse])
async def get_available_tools(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Get available tools for tool sandbox.

    Returns both built-in tools and custom tools assigned to the agent.
    """
    from models import Agent, SandboxedTool, SandboxedToolCommand, SandboxedToolParameter, AgentSandboxedTool

    # Verify agent exists
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == current_user.tenant_id
    ).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    tools = []

    # Built-in tools
    builtin_tools = [
        {"id": -1, "name": "search", "tool_type": "built_in", "description": "Web search using configured provider", "commands": [
            {"name": "search", "description": "Search the web", "parameters": [{"name": "query", "type": "string", "required": True}]}
        ]},
        {"id": -2, "name": "weather", "tool_type": "built_in", "description": "Get weather information", "commands": [
            {"name": "current", "description": "Get current weather", "parameters": [{"name": "location", "type": "string", "required": True}]}
        ]},
        {"id": -3, "name": "scraper", "tool_type": "built_in", "description": "Scrape web pages", "commands": [
            {"name": "scrape", "description": "Extract content from URL", "parameters": [{"name": "url", "type": "string", "required": True}]}
        ]},
    ]

    # Built-in tools removed - now handled by Skills system
    # web_search, weather, web_scraping are now skills configured via AgentSkill table

    # Sandboxed tools assigned to agent
    agent_tools = db.query(AgentSandboxedTool).filter(
        AgentSandboxedTool.agent_id == agent_id,
        AgentSandboxedTool.is_enabled == True
    ).all()

    for at in agent_tools:
        sandboxed_tool = db.query(SandboxedTool).filter(
            SandboxedTool.id == at.sandboxed_tool_id,
            SandboxedTool.is_enabled == True
        ).first()

        if sandboxed_tool:
            # Get commands for this tool
            commands = db.query(SandboxedToolCommand).filter(
                SandboxedToolCommand.tool_id == sandboxed_tool.id
            ).all()

            cmd_list = []
            for cmd in commands:
                params = db.query(SandboxedToolParameter).filter(
                    SandboxedToolParameter.command_id == cmd.id
                ).all()
                cmd_list.append({
                    "id": cmd.id,
                    "name": cmd.command_name,
                    # SandboxedToolCommand doesn't have description - use template as fallback
                    "description": cmd.command_template or f"Execute {cmd.command_name}",
                    "parameters": [
                        {"name": p.parameter_name, "type": "string", "required": p.is_mandatory, "description": p.description or ""}
                        for p in params
                    ]
                })

            tools.append(AvailableToolResponse(
                id=sandboxed_tool.id,
                name=sandboxed_tool.name,
                tool_type=sandboxed_tool.tool_type,
                description=sandboxed_tool.system_prompt,
                commands=cmd_list
            ))

    return tools


# ============================================================================
# Phase 14.1: Thread Management API
# ============================================================================

class ThreadCreateRequest(BaseModel):
    agent_id: int
    title: Optional[str] = None
    folder: Optional[str] = None


class ThreadUpdateRequest(BaseModel):
    title: Optional[str] = None
    folder: Optional[str] = None
    is_archived: Optional[bool] = None


class ThreadResponse(BaseModel):
    id: int
    title: Optional[str]
    folder: Optional[str]
    status: str
    is_archived: bool
    agent_id: int
    recipient: Optional[str] = None  # BUG-PLAYGROUND-003: Required for Memory Inspector sender_key
    message_count: int = 0
    last_message_preview: Optional[str] = None
    created_at: Optional[str]
    updated_at: Optional[str]


class ThreadListResponse(BaseModel):
    threads: List[ThreadResponse]


@router.get("/api/playground/threads", response_model=ThreadListResponse)
async def list_threads(
    agent_id: Optional[int] = None,
    include_archived: bool = False,
    folder: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    List all conversation threads for the current user.

    Phase 14.1: Thread Management
    """
    from services.playground_thread_service import PlaygroundThreadService

    service = PlaygroundThreadService(db)
    threads = await service.list_threads(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        agent_id=agent_id,
        include_archived=include_archived,
        folder=folder
    )

    return ThreadListResponse(threads=[ThreadResponse(**t) for t in threads])


@router.post("/api/playground/threads", response_model=ThreadResponse)
async def create_thread(
    request: ThreadCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Create a new conversation thread.

    Phase 14.1: Thread Management
    """
    from services.playground_thread_service import PlaygroundThreadService

    service = PlaygroundThreadService(db)
    result = await service.create_thread(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        agent_id=request.agent_id,
        title=request.title,
        folder=request.folder
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return ThreadResponse(**result["thread"])


@router.get("/api/playground/threads/{thread_id}")
async def get_thread(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Get thread details including messages.

    Phase 14.1: Thread Management
    """
    from services.playground_thread_service import PlaygroundThreadService

    service = PlaygroundThreadService(db)
    thread = await service.get_thread(
        thread_id=thread_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id
    )

    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    return thread


@router.put("/api/playground/threads/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: int,
    request: ThreadUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Update thread metadata (title, folder, archived status).

    Phase 14.1: Thread Management
    """
    from services.playground_thread_service import PlaygroundThreadService

    service = PlaygroundThreadService(db)
    result = await service.update_thread(
        thread_id=thread_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        title=request.title,
        folder=request.folder,
        is_archived=request.is_archived
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return ThreadResponse(**result["thread"], message_count=0, last_message_preview=None)


@router.delete("/api/playground/threads/{thread_id}")
async def delete_thread(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Delete a conversation thread and its associated memory.

    Phase 14.1: Thread Management
    """
    from services.playground_thread_service import PlaygroundThreadService

    service = PlaygroundThreadService(db)
    result = await service.delete_thread(
        thread_id=thread_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/api/playground/threads/{thread_id}/export")
async def export_thread(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Export thread as JSON.

    Phase 14.1: Thread Management
    """
    from services.playground_thread_service import PlaygroundThreadService
    from fastapi.responses import JSONResponse

    service = PlaygroundThreadService(db)
    export_data = await service.export_thread(
        thread_id=thread_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id
    )

    if not export_data:
        raise HTTPException(status_code=404, detail="Thread not found")

    return JSONResponse(content=export_data)


# ============================================================================
# Phase 14.2: Message Operations API
# ============================================================================

class MessageEditRequest(BaseModel):
    message_id: str
    new_content: str
    regenerate: bool = True


class MessageRegenerateRequest(BaseModel):
    message_id: str


class MessageDeleteRequest(BaseModel):
    message_id: str
    delete_subsequent: bool = True


class MessageBookmarkRequest(BaseModel):
    message_id: str
    bookmarked: bool


class MessageBranchRequest(BaseModel):
    message_id: str
    new_thread_title: Optional[str] = None


@router.put("/api/playground/messages/edit")
async def edit_message(
    agent_id: int,
    thread_id: int,
    request: MessageEditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Edit a user message and optionally regenerate the response.

    Phase 14.2: Message Operations
    """
    from services.playground_message_service import PlaygroundMessageService

    service = PlaygroundMessageService(db)

    print(f"[DEBUG] Edit request: agent_id={agent_id}, thread_id={thread_id}, message_id={request.message_id}")
    logger.warning(f"[EDIT API] Received request: agent_id={agent_id}, thread_id={thread_id}, message_id={request.message_id}")

    result = await service.edit_message(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        agent_id=agent_id,
        thread_id=thread_id,
        message_id=request.message_id,
        new_content=request.new_content,
        regenerate=request.regenerate
    )

    if result.get("status") == "error":
        logger.error(f"Edit failed: {result.get('error')}")
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/api/playground/messages/regenerate")
async def regenerate_message(
    agent_id: int,
    thread_id: int,
    request: MessageRegenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Regenerate an assistant response.

    Phase 14.2: Message Operations
    """
    from services.playground_message_service import PlaygroundMessageService

    service = PlaygroundMessageService(db)

    print(f"[DEBUG REGENERATE] Query params: agent_id={agent_id}, thread_id={thread_id}")
    logger.warning(f"[REGENERATE API] agent_id={agent_id}, thread_id={thread_id}, message_id={request.message_id}")

    result = await service.regenerate_response(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        agent_id=agent_id,
        thread_id=thread_id,
        message_id=request.message_id
    )

    if result.get("status") == "error":
        print(f"[DEBUG REGENERATE] Service returned error: {result.get('error')}")
        logger.error(f"Regenerate failed: {result.get('error')}")
        raise HTTPException(status_code=400, detail=result.get("error"))

    print(f"[DEBUG REGENERATE] Success!")
    return result


@router.delete("/api/playground/messages/delete")
async def delete_message(
    agent_id: int,
    thread_id: int,
    request: MessageDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Delete a message (and optionally subsequent messages).

    Phase 14.2: Message Operations
    """
    from services.playground_message_service import PlaygroundMessageService

    service = PlaygroundMessageService(db)
    result = await service.delete_message(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        agent_id=agent_id,
        thread_id=thread_id,
        message_id=request.message_id,
        delete_subsequent=request.delete_subsequent
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.put("/api/playground/messages/bookmark")
async def bookmark_message(
    agent_id: int,
    thread_id: int,
    request: MessageBookmarkRequest,
    raw_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Toggle bookmark on a message.

    Phase 14.2: Message Operations
    """
    try:
        # Log request details
        body = await raw_request.body()
        print(f"[DEBUG BOOKMARK] Query params: agent_id={agent_id}, thread_id={thread_id}")
        print(f"[DEBUG BOOKMARK] Request body: {body.decode('utf-8')}")
        print(f"[DEBUG BOOKMARK] Parsed request: message_id={request.message_id}, bookmarked={request.bookmarked}")
        logger.warning(f"[BOOKMARK API] agent_id={agent_id}, thread_id={thread_id}, message_id={request.message_id}, bookmarked={request.bookmarked}")

        from services.playground_message_service import PlaygroundMessageService

        service = PlaygroundMessageService(db)

        result = await service.bookmark_message(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            agent_id=agent_id,
            thread_id=thread_id,
            message_id=request.message_id,
            bookmarked=request.bookmarked
        )

        if result.get("status") == "error":
            print(f"[DEBUG BOOKMARK] Service returned error: {result.get('error')}")
            logger.error(f"Bookmark failed: {result.get('error')}")
            raise HTTPException(status_code=400, detail=result.get("error"))

        print(f"[DEBUG BOOKMARK] Success!")
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"[DEBUG BOOKMARK] Unexpected error: {e}")
        logger.error(f"Bookmark unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/playground/messages/branch")
async def branch_conversation(
    agent_id: int,
    thread_id: int,
    request: MessageBranchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Create a new conversation branch from a specific message.

    Phase 14.2: Message Operations
    """
    from services.playground_message_service import PlaygroundMessageService

    service = PlaygroundMessageService(db)
    result = await service.branch_conversation(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        agent_id=agent_id,
        thread_id=thread_id,
        message_id=request.message_id,
        new_thread_title=request.new_thread_title
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/api/playground/messages/copy")
async def copy_message(
    agent_id: int,
    thread_id: int,
    message_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Get message content for copying.

    Phase 14.2: Message Operations
    """
    from services.playground_message_service import PlaygroundMessageService

    service = PlaygroundMessageService(db)
    result = await service.copy_message(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        agent_id=agent_id,
        thread_id=thread_id,
        message_id=message_id
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result



# ============================================================================
# Phase 14.5: Conversation Search API
# ============================================================================

@router.get("/api/playground/search")
async def search_conversations(
    q: str,
    agent_id: Optional[int] = None,
    thread_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Full-text search across playground conversations.

    Phase 14.5: Conversation Search

    Args:
        q: Search query
        agent_id: Optional agent filter
        thread_id: Optional thread filter
        date_from: Optional start date (ISO format)
        date_to: Optional end date (ISO format)
        role: Optional role filter ('user' or 'assistant')
        limit: Max results (default 20)
        offset: Pagination offset
    """
    from services.conversation_search_service import ConversationSearchService

    service = ConversationSearchService(db)
    result = service.search_full_text(
        query=q,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        agent_id=agent_id,
        thread_id=thread_id,
        date_from=date_from,
        date_to=date_to,
        role=role,
        limit=limit,
        offset=offset
    )

    return result


@router.get("/api/playground/search/semantic")
async def search_conversations_semantic(
    q: str,
    agent_id: Optional[int] = None,
    limit: int = 10,
    min_similarity: float = 0.5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Semantic search across playground conversations.

    Phase 14.5: Conversation Search

    Args:
        q: Search query
        agent_id: Optional agent filter
        limit: Max results (default 10)
        min_similarity: Minimum similarity threshold (0.0-1.0)
    """
    from services.conversation_search_service import ConversationSearchService

    service = ConversationSearchService(db)
    result = service.search_semantic(
        query=q,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        agent_id=agent_id,
        limit=limit,
        min_similarity=min_similarity
    )

    return result


@router.get("/api/playground/search/combined")
async def search_conversations_combined(
    q: str,
    agent_id: Optional[int] = None,
    thread_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Combined/hybrid search (full-text + semantic).

    Phase 14.5: Conversation Search
    """
    from services.conversation_search_service import ConversationSearchService

    service = ConversationSearchService(db)
    result = service.search_combined(
        query=q,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        agent_id=agent_id,
        thread_id=thread_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit
    )

    return result


@router.get("/api/playground/search/suggestions")
async def get_search_suggestions(
    q: str,
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Get search suggestions based on partial query.

    Phase 14.5: Conversation Search
    """
    from services.conversation_search_service import ConversationSearchService

    service = ConversationSearchService(db)
    suggestions = service.get_search_suggestions(
        query=q,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        limit=limit
    )

    return {"suggestions": suggestions}


# ============================================================================
# Phase 14.6: Knowledge Extraction API
# ============================================================================

class ExtractKnowledgeRequest(BaseModel):
    agent_id: int


@router.post("/api/playground/threads/{thread_id}/extract-knowledge")
async def extract_thread_knowledge(
    thread_id: int,
    request: ExtractKnowledgeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Extract knowledge (tags, insights, related threads) from a conversation thread.

    Phase 14.6: Knowledge Extraction
    """
    from services.conversation_knowledge_service import ConversationKnowledgeService

    service = ConversationKnowledgeService(db)
    result = await service.extract_knowledge(
        thread_id=thread_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        agent_id=request.agent_id
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/api/playground/threads/{thread_id}/knowledge")
async def get_thread_knowledge(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Get extracted knowledge for a thread.

    Phase 14.6: Knowledge Extraction
    """
    from services.conversation_knowledge_service import ConversationKnowledgeService

    service = ConversationKnowledgeService(db)
    result = service.get_thread_knowledge(
        thread_id=thread_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/api/playground/tags")
async def list_tags(
    thread_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    List all tags for user's threads.

    Phase 14.6: Knowledge Extraction
    """
    from models import ConversationTag

    query = db.query(ConversationTag).filter(
        ConversationTag.tenant_id == current_user.tenant_id,
        ConversationTag.user_id == current_user.id
    )

    if thread_id:
        query = query.filter(ConversationTag.thread_id == thread_id)

    tags = query.all()

    return {
        "tags": [{
            "id": t.id,
            "thread_id": t.thread_id,
            "tag": t.tag,
            "color": t.color,
            "source": t.source,
            "created_at": t.created_at.isoformat() if t.created_at else None
        } for t in tags]
    }


class UpdateTagRequest(BaseModel):
    tag: Optional[str] = None
    color: Optional[str] = None


@router.put("/api/playground/tags/{tag_id}")
async def update_tag(
    tag_id: int,
    request: UpdateTagRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Update a tag.

    Phase 14.6: Knowledge Extraction
    """
    from services.conversation_knowledge_service import ConversationKnowledgeService

    service = ConversationKnowledgeService(db)
    result = service.update_tag(
        tag_id=tag_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        new_tag=request.tag,
        new_color=request.color
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.delete("/api/playground/tags/{tag_id}")
async def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Delete a tag.

    Phase 14.6: Knowledge Extraction
    """
    from services.conversation_knowledge_service import ConversationKnowledgeService

    service = ConversationKnowledgeService(db)
    result = service.delete_tag(
        tag_id=tag_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("error"))

    return result


@router.get("/api/playground/threads/{thread_id}/insights")
async def get_thread_insights(
    thread_id: int,
    insight_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Get insights for a thread.

    Phase 14.6: Knowledge Extraction
    """
    from models import ConversationInsight

    query = db.query(ConversationInsight).filter(
        ConversationInsight.thread_id == thread_id,
        ConversationInsight.tenant_id == current_user.tenant_id,
        ConversationInsight.user_id == current_user.id
    )

    if insight_type:
        query = query.filter(ConversationInsight.insight_type == insight_type)

    insights = query.all()

    return {
        "insights": [{
            "id": i.id,
            "insight_text": i.insight_text,
            "insight_type": i.insight_type,
            "confidence": i.confidence,
            "created_at": i.created_at.isoformat() if i.created_at else None
        } for i in insights]
    }


@router.put("/api/playground/insights/{insight_id}")
async def update_insight(
    insight_id: int,
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Update an insight.

    Phase 14.6: Knowledge Management
    Request body: { insight_text?, insight_type?, confidence? }
    """
    from services.conversation_knowledge_service import ConversationKnowledgeService

    service = ConversationKnowledgeService(db)
    result = service.update_insight(
        insight_id=insight_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        new_text=request.get('insight_text'),
        new_type=request.get('insight_type'),
        new_confidence=request.get('confidence')
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.delete("/api/playground/insights/{insight_id}")
async def delete_insight(
    insight_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Delete an insight.

    Phase 14.6: Knowledge Management
    """
    from services.conversation_knowledge_service import ConversationKnowledgeService

    service = ConversationKnowledgeService(db)
    result = service.delete_insight(
        insight_id=insight_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("error"))

    return result


@router.delete("/api/playground/links/{link_id}")
async def delete_conversation_link(
    link_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Remove a conversation thread relationship.

    Phase 14.6: Knowledge Management
    """
    from services.conversation_knowledge_service import ConversationKnowledgeService

    service = ConversationKnowledgeService(db)
    result = service.delete_conversation_link(
        link_id=link_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("error"))

    return result


@router.get("/api/playground/threads/{thread_id}/related")
async def get_related_threads(
    thread_id: int,
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Get related conversation threads.

    Phase 14.6: Knowledge Extraction
    """
    from models import ConversationLink, ConversationThread

    links = db.query(ConversationLink, ConversationThread).join(
        ConversationThread,
        ConversationLink.target_thread_id == ConversationThread.id
    ).filter(
        ConversationLink.source_thread_id == thread_id,
        ConversationLink.tenant_id == current_user.tenant_id
    ).limit(limit).all()

    return {
        "related_threads": [{
            "thread_id": link.target_thread_id,
            "thread_title": thread.title,
            "confidence": link.confidence,
            "relationship_type": link.relationship_type,
            "created_at": link.created_at.isoformat() if link.created_at else None
        } for link, thread in links]
    }


@router.get("/api/playground/threads/{thread_id}/export-knowledge")
async def export_thread_knowledge(
    thread_id: int,
    format: str = "json",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Export thread knowledge as JSON or Markdown.

    Phase 14.6: Knowledge Extraction
    """
    from services.conversation_knowledge_service import ConversationKnowledgeService

    service = ConversationKnowledgeService(db)
    result = service.export_knowledge(
        thread_id=thread_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        format=format
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result
