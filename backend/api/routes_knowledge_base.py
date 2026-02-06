"""
Phase 5.0: Knowledge Base - API Routes
REST API endpoints for managing agent document knowledge base.
"""

import logging
import os
import re
import tempfile
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from models import AgentKnowledge, KnowledgeChunk, Agent
from models_rbac import User
from agent.knowledge.knowledge_service import KnowledgeService
from auth_dependencies import get_current_user_required, get_tenant_context, TenantContext

logger = logging.getLogger(__name__)
router = APIRouter()

# Security constants for file uploads
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB max file size
MAX_FILENAME_LENGTH = 255  # Maximum filename length


def secure_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal and other attacks.

    Removes path separators, null bytes, and other dangerous characters.
    Returns a safe filename suitable for storage.
    """
    if not filename:
        return "document"

    # Remove path components (handles both Unix and Windows paths)
    filename = os.path.basename(filename)

    # Remove null bytes and other control characters
    filename = filename.replace('\x00', '').replace('\r', '').replace('\n', '')

    # Remove or replace dangerous characters
    # Keep only alphanumeric, dash, underscore, dot, and space
    filename = re.sub(r'[^\w\s\-\.]', '_', filename)

    # Remove leading/trailing dots and spaces
    filename = filename.strip('. ')

    # Prevent double extensions that could bypass filters (e.g., file.txt.exe)
    # Split on dots and only keep the last extension
    parts = filename.rsplit('.', 1)
    if len(parts) == 2:
        name, ext = parts
        # Remove any additional dots from the name part
        name = name.replace('.', '_')
        filename = f"{name}.{ext}"

    # Truncate if too long
    if len(filename) > MAX_FILENAME_LENGTH:
        name, ext = os.path.splitext(filename)
        max_name_len = MAX_FILENAME_LENGTH - len(ext)
        filename = name[:max_name_len] + ext

    # If filename is empty after sanitization, use default
    if not filename or filename == '.':
        return "document"

    return filename

# Global engine (set by app.py)
_engine = None

def set_engine(engine):
    global _engine
    _engine = engine

# Dependency to get database session
def get_db():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic Models
class KnowledgeResponse(BaseModel):
    id: int
    agent_id: int
    document_name: str
    document_type: str
    file_size_bytes: int
    num_chunks: int
    status: str
    error_message: str | None
    upload_date: str
    processed_date: str | None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        """Custom ORM converter to handle datetime serialization."""
        data = {
            "id": obj.id,
            "agent_id": obj.agent_id,
            "document_name": obj.document_name,
            "document_type": obj.document_type,
            "file_size_bytes": obj.file_size_bytes,
            "num_chunks": obj.num_chunks,
            "status": obj.status,
            "error_message": obj.error_message,
            "upload_date": obj.upload_date.isoformat() if obj.upload_date else None,
            "processed_date": obj.processed_date.isoformat() if obj.processed_date else None
        }
        return cls(**data)


class KnowledgeChunkResponse(BaseModel):
    id: int
    knowledge_id: int
    chunk_index: int
    content: str
    char_count: int
    metadata_json: dict

    class Config:
        from_attributes = True


class SearchRequest(BaseModel):
    query: str
    max_results: int = 5
    similarity_threshold: float = 0.3


class SearchResult(BaseModel):
    chunk_id: int
    knowledge_id: int
    document_name: str
    content: str
    similarity: float
    chunk_index: int


# API Endpoints

@router.post("/agents/{agent_id}/knowledge-base/upload", response_model=KnowledgeResponse)
async def upload_knowledge(
    agent_id: int,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Upload a document to the agent's knowledge base (requires authentication).

    Supports: TXT, CSV, JSON, PDF, DOCX
    Max file size: 50 MB

    The document will be processed asynchronously in the background.
    """
    # Verify agent exists and user has access (same tenant or global admin)
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not current_user.is_global_admin and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this agent")

    # Sanitize filename to prevent path traversal attacks
    safe_filename = secure_filename(file.filename or "document")

    # Validate file type using sanitized filename
    allowed_extensions = {".txt", ".csv", ".json", ".pdf", ".docx"}
    file_ext = os.path.splitext(safe_filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )

    # Map extension to document type
    ext_to_type = {
        ".txt": "txt",
        ".csv": "csv",
        ".json": "json",
        ".pdf": "pdf",
        ".docx": "docx"
    }
    document_type = ext_to_type[file_ext]

    try:
        # Read file content with size limit check
        content = await file.read()

        # Validate file size (prevent DoS via large uploads)
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024*1024)} MB"
            )

        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        # Upload to knowledge service using sanitized filename
        service = KnowledgeService(db)
        knowledge = service.upload_document(
            agent_id=agent_id,
            file_path=tmp_file_path,
            document_name=safe_filename,
            document_type=document_type
        )

        # Process document in background
        if background_tasks:
            background_tasks.add_task(service.process_document, knowledge.id)
        else:
            # Process immediately if no background tasks available
            service.process_document(knowledge.id)

        # Clean up temporary file
        try:
            os.unlink(tmp_file_path)
        except Exception as e:
            logger.warning(f"Error deleting temp file: {e}")

        return KnowledgeResponse.from_orm(knowledge)

    except Exception as e:
        logger.error(f"Error uploading knowledge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/knowledge-base", response_model=List[KnowledgeResponse])
def list_knowledge(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Get all knowledge documents for an agent (requires authentication)."""
    # Verify agent exists and user has access
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not current_user.is_global_admin and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    service = KnowledgeService(db)
    knowledge_list = service.get_agent_knowledge(agent_id)

    return [KnowledgeResponse.from_orm(k) for k in knowledge_list]


@router.get("/agents/{agent_id}/knowledge-base/stats")
def get_knowledge_stats(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Get statistics about agent's knowledge base (requires authentication)."""
    # Verify agent exists and user has access
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not current_user.is_global_admin and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    service = KnowledgeService(db)
    return service.get_knowledge_stats(agent_id)


@router.get("/agents/{agent_id}/knowledge-base/{knowledge_id}", response_model=KnowledgeResponse)
def get_knowledge_detail(
    agent_id: int,
    knowledge_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Get details of a specific knowledge document (requires authentication)."""
    # Verify agent exists and user has access
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not current_user.is_global_admin and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to agent")

    service = KnowledgeService(db)
    knowledge = service.get_knowledge_by_id(knowledge_id)

    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge not found")

    if knowledge.agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return KnowledgeResponse.from_orm(knowledge)


@router.get("/agents/{agent_id}/knowledge-base/{knowledge_id}/chunks", response_model=List[KnowledgeChunkResponse])
def get_knowledge_chunks(
    agent_id: int,
    knowledge_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Get all chunks for a knowledge document (requires authentication)."""
    # Verify agent exists and user has access
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not current_user.is_global_admin and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to agent")

    service = KnowledgeService(db)
    knowledge = service.get_knowledge_by_id(knowledge_id)

    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge not found")

    if knowledge.agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Access denied")

    chunks = service.get_knowledge_chunks(knowledge_id)
    return [KnowledgeChunkResponse.from_orm(c) for c in chunks]


@router.delete("/agents/{agent_id}/knowledge-base/{knowledge_id}")
def delete_knowledge(
    agent_id: int,
    knowledge_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Delete a knowledge document and all its chunks (requires authentication)."""
    # Verify agent exists and user has access
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not current_user.is_global_admin and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to agent")

    service = KnowledgeService(db)
    knowledge = service.get_knowledge_by_id(knowledge_id)

    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge not found")

    if knowledge.agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Access denied")

    success = service.delete_knowledge(knowledge_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete knowledge")

    return {"message": "Knowledge deleted successfully"}


@router.post("/agents/{agent_id}/knowledge-base/search", response_model=List[SearchResult])
def search_knowledge(
    agent_id: int,
    request: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Search agent's knowledge base using semantic similarity (requires authentication).

    Returns relevant chunks ranked by similarity.
    """
    # Verify agent exists and user has access
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not current_user.is_global_admin and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    service = KnowledgeService(db)
    results = service.search_knowledge(
        agent_id=agent_id,
        query=request.query,
        max_results=request.max_results,
        similarity_threshold=request.similarity_threshold
    )

    return results


@router.post("/agents/{agent_id}/knowledge-base/{knowledge_id}/reprocess")
def reprocess_knowledge(
    agent_id: int,
    knowledge_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """Reprocess a knowledge document (re-chunk and re-embed, requires authentication)."""
    # Verify agent exists and user has access
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not current_user.is_global_admin and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to agent")

    service = KnowledgeService(db)
    knowledge = service.get_knowledge_by_id(knowledge_id)

    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge not found")

    if knowledge.agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete existing chunks
    chunks = service.get_knowledge_chunks(knowledge_id)
    collection_name = f"knowledge_agent_{agent_id}"

    for chunk in chunks:
        try:
            service.vector_store.delete_embedding(
                collection_name=collection_name,
                document_id=f"knowledge_{knowledge.id}_chunk_{chunk.id}"
            )
            db.delete(chunk)
        except Exception as e:
            logger.warning(f"Error deleting chunk {chunk.id}: {e}")

    db.commit()

    # Reset knowledge status
    knowledge.status = "pending"
    knowledge.num_chunks = 0
    knowledge.error_message = None
    db.commit()

    # Reprocess in background
    background_tasks.add_task(service.process_document, knowledge.id)

    return {"message": "Document queued for reprocessing"}
