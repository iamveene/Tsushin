"""
Skills API Routes for Phase 5.0
Endpoints for managing agent skills (audio transcription, TTS, etc.)

Security: CRIT-009 fix - Added authentication and tenant isolation (2026-02-02)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field
import logging

from agent.skills import get_skill_manager
from models import AgentSkill, Agent
from auth_dependencies import TenantContext, get_tenant_context, require_permission
from models_rbac import User

router = APIRouter()
logger = logging.getLogger(__name__)

# Global engine reference
_engine = None


def set_engine(engine):
    """Set the global engine reference"""
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


# Pydantic models for request/response
class SkillConfigRequest(BaseModel):
    """Request to enable or update a skill"""
    is_enabled: bool = Field(True, description="Enable or disable the skill")
    config: dict = Field(default_factory=dict, description="Skill configuration")


class SkillResponse(BaseModel):
    """Response for skill details"""
    id: int
    agent_id: int
    skill_type: str
    is_enabled: bool
    config: dict
    created_at: str
    updated_at: str


# Helper function for agent ownership verification
def verify_agent_access(db: Session, agent_id: int, ctx: TenantContext) -> Agent:
    """
    Verify agent exists and user has access to it.

    Since AgentSkill doesn't have a tenant_id column, we verify access
    through the Agent relationship.

    Args:
        db: Database session
        agent_id: Agent ID to verify
        ctx: Tenant context with user's tenant info

    Returns:
        Agent object if access is granted

    Raises:
        HTTPException 404 if agent not found
        HTTPException 403 if tenant doesn't match
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this agent")
    return agent


# API Endpoints

@router.get("/skills/available")
async def get_available_skills():
    """
    Get list of all registered skill types.

    Returns:
        List of available skills with metadata:
        - skill_type: Unique identifier
        - skill_name: Human-readable name
        - skill_description: What the skill does
        - config_schema: JSON schema for configuration
        - default_config: Default configuration values
    """
    try:
        skill_manager = get_skill_manager()
        skills = skill_manager.list_available_skills()
        return {
            "skills": skills,
            "count": len(skills)
        }
    except Exception as e:
        logger.error(f"Error listing available skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/skills")
async def get_agent_skills(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get all skills for an agent (enabled and disabled).

    Requires agents.read permission and tenant access to the agent.

    Args:
        agent_id: Agent ID

    Returns:
        List of agent's skills with configuration
    """
    try:
        # Verify agent exists and user has access
        verify_agent_access(db, agent_id, ctx)

        skill_manager = get_skill_manager()
        skills = await skill_manager.get_agent_skills(db, agent_id)

        return {
            "agent_id": agent_id,
            "skills": [
                {
                    "id": skill.id,
                    "skill_type": skill.skill_type,
                    "is_enabled": skill.is_enabled,
                    "config": skill.config or {},
                    "created_at": skill.created_at.isoformat() if skill.created_at else None,
                    "updated_at": skill.updated_at.isoformat() if skill.updated_at else None
                }
                for skill in skills
            ],
            "count": len(skills)
        }
    except Exception as e:
        logger.error(f"Error getting skills for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/skills/{skill_type}")
async def get_skill_config(
    agent_id: int,
    skill_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get configuration for a specific skill.

    Requires agents.read permission and tenant access to the agent.

    Args:
        agent_id: Agent ID
        skill_type: Skill type identifier

    Returns:
        Skill configuration
    """
    try:
        # Verify agent exists and user has access
        verify_agent_access(db, agent_id, ctx)

        skill = db.query(AgentSkill)\
            .filter(AgentSkill.agent_id == agent_id)\
            .filter(AgentSkill.skill_type == skill_type)\
            .first()

        if not skill:
            raise HTTPException(
                status_code=404,
                detail=f"Skill '{skill_type}' not found for agent {agent_id}"
            )

        return {
            "id": skill.id,
            "agent_id": skill.agent_id,
            "skill_type": skill.skill_type,
            "is_enabled": skill.is_enabled,
            "config": skill.config or {},
            "created_at": skill.created_at.isoformat() if skill.created_at else None,
            "updated_at": skill.updated_at.isoformat() if skill.updated_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting skill config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/agents/{agent_id}/skills/{skill_type}")
async def update_skill(
    agent_id: int,
    skill_type: str,
    request: SkillConfigRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Enable or update a skill for an agent.

    Requires agents.write permission and tenant access to the agent.

    Args:
        agent_id: Agent ID
        skill_type: Skill type identifier
        request: Skill configuration

    Returns:
        Updated skill configuration
    """
    try:
        # Verify agent exists and user has access
        verify_agent_access(db, agent_id, ctx)

        skill_manager = get_skill_manager()

        # Check if skill type is registered
        if skill_type not in skill_manager.registry:
            raise HTTPException(
                status_code=400,
                detail=f"Skill type '{skill_type}' is not registered. "
                       f"Available: {list(skill_manager.registry.keys())}"
            )

        # Check if skill already exists
        existing = db.query(AgentSkill)\
            .filter(AgentSkill.agent_id == agent_id)\
            .filter(AgentSkill.skill_type == skill_type)\
            .first()

        if existing:
            # Update existing
            existing.is_enabled = request.is_enabled
            existing.config = request.config
            db.commit()
            db.refresh(existing)

            logger.info(
                f"Updated skill '{skill_type}' for agent {agent_id} "
                f"(enabled={request.is_enabled})"
            )

            return {
                "id": existing.id,
                "agent_id": existing.agent_id,
                "skill_type": existing.skill_type,
                "is_enabled": existing.is_enabled,
                "config": existing.config or {},
                "created_at": existing.created_at.isoformat() if existing.created_at else None,
                "updated_at": existing.updated_at.isoformat() if existing.updated_at else None
            }

        # Create new
        skill = await skill_manager.enable_skill(
            db,
            agent_id,
            skill_type,
            request.config
        )

        logger.info(f"Created skill '{skill_type}' for agent {agent_id}")

        return {
            "id": skill.id,
            "agent_id": skill.agent_id,
            "skill_type": skill.skill_type,
            "is_enabled": skill.is_enabled,
            "config": skill.config or {},
            "created_at": skill.created_at.isoformat() if skill.created_at else None,
            "updated_at": skill.updated_at.isoformat() if skill.updated_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_id}/skills/{skill_type}")
async def disable_skill(
    agent_id: int,
    skill_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Disable a skill for an agent.

    This doesn't delete the skill record, just sets is_enabled=False
    so configuration is preserved.

    Requires agents.write permission and tenant access to the agent.

    Args:
        agent_id: Agent ID
        skill_type: Skill type identifier

    Returns:
        Success message
    """
    try:
        # Verify agent exists and user has access
        verify_agent_access(db, agent_id, ctx)

        skill_manager = get_skill_manager()
        success = await skill_manager.disable_skill(db, agent_id, skill_type)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Skill '{skill_type}' not found for agent {agent_id}"
            )

        logger.info(f"Disabled skill '{skill_type}' for agent {agent_id}")

        return {
            "success": True,
            "message": f"Skill '{skill_type}' disabled for agent {agent_id}",
            "agent_id": agent_id,
            "skill_type": skill_type
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/skills/{skill_type}/test")
async def test_skill(
    agent_id: int,
    skill_type: str,
    test_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Test a skill with sample data (for debugging).

    Requires agents.write permission and tenant access to the agent.

    Args:
        agent_id: Agent ID
        skill_type: Skill type identifier
        test_data: Test message data

    Returns:
        Skill execution result
    """
    try:
        # Verify agent exists and user has access
        verify_agent_access(db, agent_id, ctx)

        skill_manager = get_skill_manager()

        # Check if skill is registered
        if skill_type not in skill_manager.registry:
            raise HTTPException(
                status_code=400,
                detail=f"Skill type '{skill_type}' is not registered"
            )

        # Get skill config
        config = await skill_manager.get_skill_config(db, agent_id, skill_type)
        if config is None:
            raise HTTPException(
                status_code=404,
                detail=f"Skill '{skill_type}' not enabled for agent {agent_id}"
            )

        # Create test message
        from agent.skills import InboundMessage
        from datetime import datetime

        test_message = InboundMessage(
            id=test_data.get("id", "test-001"),
            sender=test_data.get("sender", "test@user"),
            sender_key=test_data.get("sender_key", "test@user"),
            body=test_data.get("body", "Test message"),
            chat_id=test_data.get("chat_id", "test-chat"),
            chat_name=test_data.get("chat_name", "Test Chat"),
            is_group=test_data.get("is_group", False),
            timestamp=datetime.utcnow(),
            media_type=test_data.get("media_type"),
            media_url=test_data.get("media_url"),
            media_path=test_data.get("media_path"),
            channel="test"  # Skills-as-Tools: skill testing endpoint
        )

        # Get skill instance
        skill_class = skill_manager.registry[skill_type]
        skill_instance = skill_class()

        # Check if can handle
        can_handle = await skill_instance.can_handle(test_message)

        if not can_handle:
            return {
                "success": False,
                "message": f"Skill '{skill_type}' cannot handle this message type",
                "can_handle": False
            }

        # Execute skill
        result = await skill_instance.process(test_message, config)

        return {
            "success": result.success,
            "output": result.output,
            "metadata": result.metadata,
            "processed_content": result.processed_content,
            "can_handle": True
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
