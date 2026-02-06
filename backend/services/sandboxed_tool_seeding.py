"""
Tsushin Sandboxed Tool Seeding Service

Creates default sandboxed tools during installation by reading YAML manifests.
Seeds tools from backend/tools/manifests/ directory.

Tools seeded:
- nuclei - Vulnerability scanner
- nmap - Network scanner
- dig - DNS lookup
- httpx - HTTP probing
- whois_lookup - Domain info
- katana - Web crawler
- subfinder - Subdomain discovery
- webhook - HTTP requests via curl
- sqlmap - SQL injection testing

Usage:
    from services.sandboxed_tool_seeding import seed_sandboxed_tools
    tools = seed_sandboxed_tools(tenant_id, db)
"""

import os
import yaml
from pathlib import Path
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from models import SandboxedTool, SandboxedToolCommand, SandboxedToolParameter, AgentSandboxedTool, Agent, AgentSkill
from services.tool_discovery_service import TIMEOUT_CATEGORIES

logger = logging.getLogger(__name__)

# Path to manifests directory (relative to backend/)
MANIFESTS_DIR = Path(__file__).parent.parent / "tools" / "manifests"

# Tools to seed (in order)
DEFAULT_TOOLS = [
    "nuclei",
    "nmap",
    "dig",
    "httpx",
    "whois_lookup",
    "katana",
    "subfinder",
    "webhook",
    "sqlmap"
]


def load_manifest(tool_name: str) -> Optional[dict]:
    """
    Load a tool manifest YAML file.

    Args:
        tool_name: Name of the tool (without .yaml extension)

    Returns:
        Parsed manifest dict or None if not found
    """
    manifest_path = MANIFESTS_DIR / f"{tool_name}.yaml"

    if not manifest_path.exists():
        logger.warning(f"Manifest not found: {manifest_path}")
        return None

    try:
        with open(manifest_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load manifest {manifest_path}: {e}")
        return None


def seed_sandboxed_tools(
    tenant_id: str,
    db: Session,
    tools_to_seed: Optional[List[str]] = None
) -> List[dict]:
    """
    Seed sandboxed tools from manifests for a tenant.

    Args:
        tenant_id: Tenant ID to assign tools to
        db: Database session
        tools_to_seed: Optional list of tool names to seed (defaults to all)

    Returns:
        List of dictionaries with created tool details
    """
    created_tools = []
    tools_list = tools_to_seed or DEFAULT_TOOLS

    try:
        for tool_name in tools_list:
            # Load manifest
            manifest = load_manifest(tool_name)
            if not manifest:
                logger.warning(f"Skipping tool '{tool_name}': manifest not found")
                continue

            # Check if tool already exists for this tenant
            existing = db.query(SandboxedTool).filter(
                SandboxedTool.name == manifest["name"],
                SandboxedTool.tenant_id == tenant_id
            ).first()

            if existing:
                logger.info(f"Tool '{manifest['name']}' already exists for tenant, skipping")
                continue

            # Create SandboxedTool
            tool = SandboxedTool(
                tenant_id=tenant_id,
                name=manifest["name"],
                tool_type=manifest.get("tool_type", "command"),
                system_prompt=manifest.get("system_prompt", ""),
                workspace_dir=f"./data/workspace/{manifest['name']}",  # Legacy field
                execution_mode="container",
                is_enabled=manifest.get("enabled", True)
            )
            db.add(tool)
            db.flush()  # Get tool.id without committing

            # Create commands and parameters
            commands_created = 0
            params_created = 0

            for cmd_config in manifest.get("commands", []):
                # Map timeout category to seconds (use canonical values from discovery service)
                timeout = TIMEOUT_CATEGORIES.get(cmd_config.get("timeout_category", "standard"), 120)

                command = SandboxedToolCommand(
                    tool_id=tool.id,
                    command_name=cmd_config["name"],
                    command_template=cmd_config["template"],
                    is_long_running=cmd_config.get("long_running", False),
                    timeout_seconds=timeout
                )
                db.add(command)
                db.flush()  # Get command.id
                commands_created += 1

                # Create parameters
                for param_config in cmd_config.get("parameters", []):
                    param = SandboxedToolParameter(
                        command_id=command.id,
                        parameter_name=param_config["name"],
                        is_mandatory=param_config.get("required", False),
                        default_value=str(param_config.get("default", "")) if param_config.get("default") else None,
                        description=param_config.get("description", "")
                    )
                    db.add(param)
                    params_created += 1

            # Auto-assign tool to all agents in the tenant
            agents = db.query(Agent).filter(Agent.tenant_id == tenant_id).all()
            for agent in agents:
                agent_tool = AgentSandboxedTool(
                    agent_id=agent.id,
                    sandboxed_tool_id=tool.id,
                    is_enabled=True
                )
                db.add(agent_tool)

                # Ensure sandboxed_tools skill is enabled for this agent
                existing_skill = db.query(AgentSkill).filter(
                    AgentSkill.agent_id == agent.id,
                    AgentSkill.skill_type == 'sandboxed_tools'
                ).first()
                if not existing_skill:
                    skill = AgentSkill(
                        agent_id=agent.id,
                        skill_type='sandboxed_tools',
                        is_enabled=True,
                        config={}
                    )
                    db.add(skill)

            db.commit()

            created_tools.append({
                "name": tool.name,
                "tool_id": tool.id,
                "tool_type": tool.tool_type,
                "commands_count": commands_created,
                "parameters_count": params_created,
                "agents_assigned": len(agents)
            })

            logger.info(f"✓ Created tool '{tool.name}' (ID: {tool.id}) with {commands_created} commands")

        logger.info(f"Successfully seeded {len(created_tools)} sandboxed tools for tenant {tenant_id}")
        return created_tools

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed sandboxed tools: {e}", exc_info=True)
        raise


def update_existing_tools(
    tenant_id: str,
    db: Session,
    tools_to_update: Optional[List[str]] = None
) -> List[dict]:
    """
    Update existing sandboxed tools from manifests for a tenant.
    Updates system_prompt, command templates, and parameters to match
    current manifest definitions.

    Args:
        tenant_id: Tenant ID
        db: Database session
        tools_to_update: Optional list of tool names (defaults to all)

    Returns:
        List of dictionaries with updated tool details
    """
    updated_tools = []
    tools_list = tools_to_update or DEFAULT_TOOLS

    try:
        for tool_name in tools_list:
            manifest = load_manifest(tool_name)
            if not manifest:
                continue

            existing = db.query(SandboxedTool).filter(
                SandboxedTool.name == manifest["name"],
                SandboxedTool.tenant_id == tenant_id
            ).first()

            if not existing:
                continue

            # Update system_prompt if changed
            new_prompt = manifest.get("system_prompt", "")
            if existing.system_prompt != new_prompt:
                existing.system_prompt = new_prompt
                logger.info(f"Updated system_prompt for tool '{tool_name}'")

            # Update commands and parameters
            for cmd_config in manifest.get("commands", []):
                # Map timeout category to seconds (use canonical values from discovery service)
                timeout = TIMEOUT_CATEGORIES.get(cmd_config.get("timeout_category", "standard"), 120)

                existing_cmd = db.query(SandboxedToolCommand).filter(
                    SandboxedToolCommand.tool_id == existing.id,
                    SandboxedToolCommand.command_name == cmd_config["name"]
                ).first()

                if existing_cmd:
                    # Update existing command
                    if existing_cmd.command_template != cmd_config["template"]:
                        existing_cmd.command_template = cmd_config["template"]
                        logger.info(f"Updated template for {tool_name}.{cmd_config['name']}")
                    existing_cmd.timeout_seconds = timeout
                    existing_cmd.is_long_running = cmd_config.get("long_running", False)
                else:
                    # Create new command
                    existing_cmd = SandboxedToolCommand(
                        tool_id=existing.id,
                        command_name=cmd_config["name"],
                        command_template=cmd_config["template"],
                        is_long_running=cmd_config.get("long_running", False),
                        timeout_seconds=timeout
                    )
                    db.add(existing_cmd)
                    db.flush()

                # Sync parameters
                for param_config in cmd_config.get("parameters", []):
                    existing_param = db.query(SandboxedToolParameter).filter(
                        SandboxedToolParameter.command_id == existing_cmd.id,
                        SandboxedToolParameter.parameter_name == param_config["name"]
                    ).first()

                    if existing_param:
                        existing_param.is_mandatory = param_config.get("required", False)
                        existing_param.default_value = str(param_config.get("default", "")) if param_config.get("default") else None
                        existing_param.description = param_config.get("description", "")
                    else:
                        param = SandboxedToolParameter(
                            command_id=existing_cmd.id,
                            parameter_name=param_config["name"],
                            is_mandatory=param_config.get("required", False),
                            default_value=str(param_config.get("default", "")) if param_config.get("default") else None,
                            description=param_config.get("description", "")
                        )
                        db.add(param)

            db.commit()
            updated_tools.append({"name": tool_name, "tool_id": existing.id})
            logger.info(f"Updated tool '{tool_name}' (ID: {existing.id})")

        return updated_tools

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update existing tools: {e}", exc_info=True)
        raise


def check_existing_tools(tenant_id: str, db: Session) -> List[str]:
    """
    Check which default tools already exist for a tenant.

    Args:
        tenant_id: Tenant ID to check
        db: Database session

    Returns:
        List of tool names that already exist
    """
    existing_tools = db.query(SandboxedTool.name).filter(
        SandboxedTool.tenant_id == tenant_id,
        SandboxedTool.name.in_(DEFAULT_TOOLS)
    ).all()

    return [tool.name for tool in existing_tools]


def get_available_manifests() -> List[dict]:
    """
    List all available tool manifests.

    Returns:
        List of manifest summaries
    """
    manifests = []

    for tool_name in DEFAULT_TOOLS:
        manifest = load_manifest(tool_name)
        if manifest:
            manifests.append({
                "name": manifest["name"],
                "description": manifest.get("description", ""),
                "category": manifest.get("category", "general"),
                "tool_type": manifest.get("tool_type", "command"),
                "commands_count": len(manifest.get("commands", []))
            })

    return manifests


def ensure_sandboxed_tools_skill(db: Session) -> int:
    """
    Migration: Ensure all agents that have sandboxed tool assignments also have
    the 'sandboxed_tools' skill enabled, so the master toggle doesn't break
    existing functionality.

    Returns:
        Number of AgentSkill records created
    """
    try:
        # Find agents that have sandboxed tool assignments but no sandboxed_tools skill
        from sqlalchemy import distinct
        agents_with_tools = db.query(distinct(AgentSandboxedTool.agent_id)).all()
        agent_ids_with_tools = {row[0] for row in agents_with_tools}

        if not agent_ids_with_tools:
            return 0

        # Find which of these already have the skill
        agents_with_skill = db.query(AgentSkill.agent_id).filter(
            AgentSkill.agent_id.in_(agent_ids_with_tools),
            AgentSkill.skill_type == 'sandboxed_tools'
        ).all()
        agent_ids_with_skill = {row[0] for row in agents_with_skill}

        # Create skill for agents that don't have it yet
        missing = agent_ids_with_tools - agent_ids_with_skill
        created = 0
        for agent_id in missing:
            skill = AgentSkill(
                agent_id=agent_id,
                skill_type='sandboxed_tools',
                is_enabled=True,
                config={}
            )
            db.add(skill)
            created += 1

        if created > 0:
            db.commit()
            logger.info(f"Migration: Created sandboxed_tools skill for {created} agents")

        return created

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to migrate sandboxed_tools skill: {e}", exc_info=True)
        return 0


def delete_seeded_tools(tenant_id: str, db: Session) -> int:
    """
    Delete all seeded default tools for a tenant (use with caution!).

    Args:
        tenant_id: Tenant ID
        db: Database session

    Returns:
        Number of tools deleted
    """
    try:
        tools = db.query(SandboxedTool).filter(
            SandboxedTool.tenant_id == tenant_id,
            SandboxedTool.name.in_(DEFAULT_TOOLS)
        ).all()

        count = 0
        for tool in tools:
            db.delete(tool)
            count += 1

        db.commit()
        logger.info(f"Deleted {count} seeded tools for tenant {tenant_id}")
        return count

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete seeded tools: {e}", exc_info=True)
        raise


# CLI interface for testing
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from db import get_engine
    from sqlalchemy.orm import sessionmaker

    print("\n" + "=" * 60)
    print("Tsushin Sandboxed Tool Seeding Service - Test Mode")
    print("=" * 60)

    # List available manifests
    print("\nAvailable manifests:")
    for manifest in get_available_manifests():
        print(f"  - {manifest['name']}: {manifest['description']} ({manifest['commands_count']} commands)")

    tenant_id = input("\nEnter tenant ID: ").strip()

    if not tenant_id:
        print("Error: Tenant ID is required")
        sys.exit(1)

    # Initialize database
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Check existing tools
        existing = check_existing_tools(tenant_id, db)
        if existing:
            print(f"\n⚠️  Existing tools found: {', '.join(existing)}")
            confirm = input("Continue and skip existing? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("Aborted")
                sys.exit(0)

        # Seed tools
        print("\nSeeding sandboxed tools...")
        tools = seed_sandboxed_tools(tenant_id, db)

        print("\n" + "=" * 60)
        print(f"SUCCESS: Created {len(tools)} tools")
        print("=" * 60)

        for tool in tools:
            print(f"\n✓ {tool['name']}")
            print(f"  Tool ID: {tool['tool_id']}")
            print(f"  Type: {tool['tool_type']}")
            print(f"  Commands: {tool['commands_count']}")
            print(f"  Parameters: {tool['parameters_count']}")
            print(f"  Agents assigned: {tool['agents_assigned']}")

        print("\n" + "=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()
