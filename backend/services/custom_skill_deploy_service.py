"""
Phase 23: Custom Skills — Script Deployment Service

Deploys custom skill scripts to tenant toolbox containers.
Handles SHA-256 hash tracking for incremental deploys and
cleanup when skills are removed.
"""

import hashlib
import logging
import base64
from typing import Dict
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class CustomSkillDeployService:
    """Service for deploying custom skill scripts to tenant containers."""

    @staticmethod
    async def deploy(skill_id: int, tenant_id: str, db: Session) -> Dict:
        """
        Deploy script to container workspace at /workspace/skills/{skill_id}/

        Args:
            skill_id: Custom skill ID
            tenant_id: Tenant ID
            db: Database session

        Returns:
            Dict with success status, content hash, and deployed path
        """
        from models import CustomSkill
        from services.toolbox_container_service import get_toolbox_service

        skill = db.query(CustomSkill).filter(
            CustomSkill.id == skill_id,
            CustomSkill.tenant_id == tenant_id,
        ).first()

        if not skill or not skill.script_content:
            return {"success": False, "error": "Skill not found or no script content"}

        container_service = get_toolbox_service()

        # Ensure container is running
        try:
            container_service.ensure_container_running(tenant_id, db)
        except Exception as e:
            return {"success": False, "error": f"Container not available: {e}"}

        # Create skill directory and write script
        entrypoint = skill.script_entrypoint or "main.py"
        skill_dir = f"/workspace/skills/{skill_id}"

        try:
            # Create directory
            await container_service.execute_command(
                tenant_id, f"mkdir -p {skill_dir}", db=db
            )

            # Write script content via base64 to avoid escaping issues
            encoded = base64.b64encode(skill.script_content.encode()).decode()
            await container_service.execute_command(
                tenant_id,
                f"echo '{encoded}' | base64 -d > {skill_dir}/{entrypoint}",
                db=db,
            )
            await container_service.execute_command(
                tenant_id, f"chmod +x {skill_dir}/{entrypoint}", db=db
            )

            # Update hash
            content_hash = hashlib.sha256(skill.script_content.encode()).hexdigest()
            skill.script_content_hash = content_hash
            db.commit()

            logger.info(
                f"Deployed skill {skill_id} to {skill_dir}/{entrypoint} "
                f"(hash={content_hash[:12]}...)"
            )

            return {
                "success": True,
                "hash": content_hash,
                "path": f"{skill_dir}/{entrypoint}",
            }

        except Exception as e:
            logger.error(f"Failed to deploy skill {skill_id}: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    async def ensure_deployed(skill, tenant_id: str, db: Session) -> bool:
        """
        Check SHA-256 hash and re-deploy if content has changed.

        Args:
            skill: CustomSkill model instance
            tenant_id: Tenant ID
            db: Database session

        Returns:
            True if skill is deployed and up-to-date
        """
        if not skill.script_content:
            return True  # No script content means nothing to deploy

        current_hash = hashlib.sha256(skill.script_content.encode()).hexdigest()
        if skill.script_content_hash != current_hash:
            result = await CustomSkillDeployService.deploy(skill.id, tenant_id, db)
            return result.get("success", False)

        return True

    @staticmethod
    async def remove(skill_id: int, tenant_id: str):
        """
        Remove skill directory from container workspace.

        Args:
            skill_id: Custom skill ID
            tenant_id: Tenant ID
        """
        from services.toolbox_container_service import get_toolbox_service

        container_service = get_toolbox_service()
        try:
            await container_service.execute_command(
                tenant_id, f"rm -rf /workspace/skills/{skill_id}"
            )
            logger.info(f"Removed skill {skill_id} from container for tenant {tenant_id}")
        except Exception as e:
            logger.warning(f"Failed to remove skill {skill_id} from container: {e}")
