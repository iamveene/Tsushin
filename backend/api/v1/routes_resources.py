"""
Resource Listing — Public API v1
Read-only endpoints for listing available skills, tools, personas,
security profiles, and tone presets.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from models import (
    AgentSkill, SandboxedTool, SandboxedToolCommand, SandboxedToolParameter,
    Persona, TonePreset, SentinelProfile,
)
from api.api_auth import ApiCaller, require_api_permission

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/v1/skills")
async def list_skills(
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.read")),
):
    """
    List available skill types in the system.
    Returns metadata about each skill type registered in the SkillManager.
    """
    try:
        from agent.skills import get_skill_manager
        skill_manager = get_skill_manager()
        skills = []
        for skill_type, skill_class in skill_manager.registry.items():
            skills.append({
                "skill_type": skill_type,
                "display_name": getattr(skill_class, "display_name", skill_type.replace("_", " ").title()),
                "description": getattr(skill_class, "description", ""),
                "category": getattr(skill_class, "category", "general"),
            })
        return {"data": skills}
    except Exception as e:
        logger.warning(f"Could not load SkillManager: {e}")
        # Fallback: list unique skill types from DB
        skill_types = db.query(AgentSkill.skill_type).distinct().all()
        return {
            "data": [
                {"skill_type": st[0], "display_name": st[0].replace("_", " ").title()}
                for st in skill_types
            ],
        }


@router.get("/api/v1/tools")
async def list_tools(
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.read")),
):
    """List sandboxed tools available in the tenant."""
    tools = db.query(SandboxedTool).filter(
        SandboxedTool.tenant_id == caller.tenant_id,
        SandboxedTool.is_enabled == True,
    ).all()

    result = []
    for tool in tools:
        commands = db.query(SandboxedToolCommand).filter(
            SandboxedToolCommand.tool_id == tool.id
        ).all()

        cmd_list = []
        for cmd in commands:
            params = db.query(SandboxedToolParameter).filter(
                SandboxedToolParameter.command_id == cmd.id
            ).all()
            cmd_list.append({
                "id": cmd.id,
                "command_name": cmd.command_name,
                "command_template": cmd.command_template,
                "is_long_running": cmd.is_long_running,
                "timeout_seconds": cmd.timeout_seconds,
                "parameters": [
                    {
                        "name": p.parameter_name,
                        "is_mandatory": p.is_mandatory,
                        "default_value": p.default_value,
                        "description": p.description,
                    }
                    for p in params
                ],
            })

        result.append({
            "id": tool.id,
            "name": tool.name,
            "tool_type": tool.tool_type,
            "is_enabled": tool.is_enabled,
            "commands": cmd_list,
        })

    return {"data": result}


@router.get("/api/v1/personas")
async def list_personas(
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.read")),
):
    """List available personas (tenant-specific + system)."""
    from sqlalchemy import or_

    personas = db.query(Persona).filter(
        or_(
            Persona.tenant_id == caller.tenant_id,
            Persona.is_system == True,
            Persona.tenant_id.is_(None),
        ),
        Persona.is_active == True,
    ).all()

    return {
        "data": [
            {
                "id": p.id,
                "name": p.name,
                "description": getattr(p, "description", None),
                "role_description": getattr(p, "role_description", None),
                "is_system": p.is_system,
                "tenant_id": p.tenant_id,
            }
            for p in personas
        ],
    }


@router.get("/api/v1/security-profiles")
async def list_security_profiles(
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("org.settings.read")),
):
    """List available Sentinel security profiles."""
    from sqlalchemy import or_

    profiles = db.query(SentinelProfile).filter(
        or_(
            SentinelProfile.tenant_id == caller.tenant_id,
            SentinelProfile.is_system == True,
            SentinelProfile.tenant_id.is_(None),
        ),
    ).all()

    return {
        "data": [
            {
                "id": p.id,
                "name": p.name,
                "slug": p.slug,
                "is_system": p.is_system,
                "is_default": p.is_default,
                "detection_mode": p.detection_mode,
                "aggressiveness_level": p.aggressiveness_level,
            }
            for p in profiles
        ],
    }


@router.get("/api/v1/tone-presets")
async def list_tone_presets(
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.read")),
):
    """List available tone presets."""
    from sqlalchemy import or_

    presets = db.query(TonePreset).filter(
        or_(
            TonePreset.tenant_id == caller.tenant_id,
            TonePreset.is_system == True,
            TonePreset.tenant_id.is_(None),
        ),
    ).all()

    return {
        "data": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "is_system": p.is_system,
            }
            for p in presets
        ],
    }
