"""
Tool Discovery Service
Phase: Custom Tools Improvements

Discovers and syncs tool manifests from YAML files to the database.
Supports automatic tool registration via manifest files in backend/tools/manifests/.
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

import yaml
from sqlalchemy.orm import Session

from models import SandboxedTool, SandboxedToolCommand, SandboxedToolParameter

logger = logging.getLogger(__name__)


# Timeout category mappings (seconds)
TIMEOUT_CATEGORIES = {
    "quick": 30,       # DNS lookups, simple HTTP requests, whois
    "standard": 120,   # Port scans, basic crawls
    "long": 300,       # Deep crawls, comprehensive scans
    "extended": 600,   # Vulnerability scanning, full audits
}

# Default manifest directory
DEFAULT_MANIFEST_DIR = Path(__file__).parent.parent / "tools" / "manifests"


class ToolManifestError(Exception):
    """Raised when a tool manifest is invalid."""
    pass


class ToolDiscoveryService:
    """
    Service for discovering and syncing tool manifests to the database.

    Usage:
        service = ToolDiscoveryService(db_session)
        results = service.sync_all_tools()
        # or for a specific tenant:
        results = service.sync_all_tools(tenant_id="tenant123")
    """

    def __init__(self, db: Session, manifest_dir: Optional[Path] = None):
        """
        Initialize the discovery service.

        Args:
            db: SQLAlchemy database session
            manifest_dir: Optional custom path to manifests directory
        """
        self.db = db
        self.manifest_dir = manifest_dir or DEFAULT_MANIFEST_DIR
        logger.info(f"ToolDiscoveryService initialized with manifest_dir: {self.manifest_dir}")

    def discover_manifests(self) -> List[Path]:
        """
        Discover all YAML manifest files in the manifests directory.

        Returns:
            List of paths to manifest files (excludes _schema.yaml)
        """
        if not self.manifest_dir.exists():
            logger.warning(f"Manifest directory does not exist: {self.manifest_dir}")
            return []

        manifests = []
        for file_path in self.manifest_dir.glob("*.yaml"):
            # Skip schema documentation file
            if file_path.name.startswith("_"):
                continue
            manifests.append(file_path)

        logger.info(f"Discovered {len(manifests)} tool manifests")
        return sorted(manifests)

    def load_manifest(self, file_path: Path) -> Dict[str, Any]:
        """
        Load and parse a YAML manifest file.

        Args:
            file_path: Path to the manifest file

        Returns:
            Parsed manifest as dictionary

        Raises:
            ToolManifestError: If file cannot be read or parsed
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                manifest = yaml.safe_load(f)

            if not manifest:
                raise ToolManifestError(f"Empty manifest: {file_path}")

            return manifest

        except yaml.YAMLError as e:
            raise ToolManifestError(f"Invalid YAML in {file_path}: {e}")
        except IOError as e:
            raise ToolManifestError(f"Cannot read {file_path}: {e}")

    def validate_manifest(self, manifest: Dict[str, Any], file_path: Path) -> None:
        """
        Validate a manifest against the expected schema.

        Args:
            manifest: Parsed manifest dictionary
            file_path: Path for error reporting

        Raises:
            ToolManifestError: If manifest is invalid
        """
        required_fields = ["name", "description", "tool_type", "system_prompt", "commands"]

        for field in required_fields:
            if field not in manifest:
                raise ToolManifestError(f"Missing required field '{field}' in {file_path}")

        # Validate tool_type
        valid_types = ["command", "python_internal", "webhook", "http"]
        if manifest["tool_type"] not in valid_types:
            raise ToolManifestError(
                f"Invalid tool_type '{manifest['tool_type']}' in {file_path}. "
                f"Must be one of: {valid_types}"
            )

        # Validate commands
        if not isinstance(manifest["commands"], list) or len(manifest["commands"]) == 0:
            raise ToolManifestError(f"'commands' must be a non-empty list in {file_path}")

        for i, cmd in enumerate(manifest["commands"]):
            if "name" not in cmd:
                raise ToolManifestError(f"Command {i} missing 'name' in {file_path}")
            if "template" not in cmd:
                raise ToolManifestError(f"Command '{cmd.get('name')}' missing 'template' in {file_path}")

    def get_timeout_seconds(self, timeout_category: str) -> int:
        """
        Convert timeout category to seconds.

        Args:
            timeout_category: Category name (quick, standard, long, extended)

        Returns:
            Timeout in seconds
        """
        return TIMEOUT_CATEGORIES.get(timeout_category, TIMEOUT_CATEGORIES["standard"])

    def sync_tool(
        self,
        manifest: Dict[str, Any],
        tenant_id: Optional[str] = None
    ) -> Tuple[str, SandboxedTool]:
        """
        Sync a single tool manifest to the database.

        Args:
            manifest: Parsed and validated manifest
            tenant_id: Optional tenant ID for multi-tenancy

        Returns:
            Tuple of (action, tool) where action is 'created', 'updated', or 'unchanged'
        """
        tool_name = manifest["name"]

        # Find existing tool
        query = self.db.query(SandboxedTool).filter(SandboxedTool.name == tool_name)
        if tenant_id:
            query = query.filter(SandboxedTool.tenant_id == tenant_id)
        else:
            query = query.filter(SandboxedTool.tenant_id.is_(None))

        existing_tool = query.first()

        if existing_tool:
            # Update existing tool
            action = self._update_tool(existing_tool, manifest)
            tool = existing_tool
        else:
            # Create new tool
            tool = self._create_tool(manifest, tenant_id)
            action = "created"

        return action, tool

    def _create_tool(
        self,
        manifest: Dict[str, Any],
        tenant_id: Optional[str] = None
    ) -> SandboxedTool:
        """Create a new tool from manifest."""
        tool = SandboxedTool(
            tenant_id=tenant_id,
            name=manifest["name"],
            tool_type=manifest["tool_type"],
            system_prompt=manifest["system_prompt"],
            workspace_dir=f"./data/workspace/{manifest['name']}",  # Legacy field
            execution_mode="container" if manifest["tool_type"] == "command" else "local",
            is_enabled=manifest.get("enabled", True),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        self.db.add(tool)
        self.db.flush()  # Get tool.id

        # Create commands
        for cmd_manifest in manifest["commands"]:
            self._create_command(tool.id, cmd_manifest)

        logger.info(f"Created tool '{manifest['name']}' with {len(manifest['commands'])} commands")
        return tool

    def _update_tool(
        self,
        tool: SandboxedTool,
        manifest: Dict[str, Any]
    ) -> str:
        """Update existing tool from manifest. Returns 'updated' or 'unchanged'."""
        changes = False

        # Check for changes in tool fields
        if tool.system_prompt != manifest["system_prompt"]:
            tool.system_prompt = manifest["system_prompt"]
            changes = True

        if tool.tool_type != manifest["tool_type"]:
            tool.tool_type = manifest["tool_type"]
            changes = True

        new_enabled = manifest.get("enabled", True)
        if tool.is_enabled != new_enabled:
            tool.is_enabled = new_enabled
            changes = True

        # Sync commands
        commands_changed = self._sync_commands(tool.id, manifest["commands"])

        if changes or commands_changed:
            tool.updated_at = datetime.utcnow()
            logger.info(f"Updated tool '{manifest['name']}'")
            return "updated"

        return "unchanged"

    def _sync_commands(self, tool_id: int, cmd_manifests: List[Dict]) -> bool:
        """
        Sync commands for a tool. Returns True if any changes were made.
        """
        changes = False

        # Get existing commands
        existing_commands = {
            cmd.command_name: cmd
            for cmd in self.db.query(SandboxedToolCommand).filter_by(tool_id=tool_id).all()
        }

        manifest_command_names = set()

        for cmd_manifest in cmd_manifests:
            cmd_name = cmd_manifest["name"]
            manifest_command_names.add(cmd_name)

            if cmd_name in existing_commands:
                # Update existing command
                cmd = existing_commands[cmd_name]
                cmd_changes = self._update_command(cmd, cmd_manifest)
                if cmd_changes:
                    changes = True
            else:
                # Create new command
                self._create_command(tool_id, cmd_manifest)
                changes = True

        # Remove commands no longer in manifest
        for cmd_name, cmd in existing_commands.items():
            if cmd_name not in manifest_command_names:
                # Delete associated parameters first
                self.db.query(SandboxedToolParameter).filter_by(command_id=cmd.id).delete()
                self.db.delete(cmd)
                changes = True
                logger.info(f"Removed command '{cmd_name}' no longer in manifest")

        return changes

    def _create_command(self, tool_id: int, cmd_manifest: Dict) -> SandboxedToolCommand:
        """Create a new command from manifest."""
        timeout_category = cmd_manifest.get("timeout_category", "standard")
        timeout_seconds = self.get_timeout_seconds(timeout_category)

        command = SandboxedToolCommand(
            tool_id=tool_id,
            command_name=cmd_manifest["name"],
            command_template=cmd_manifest["template"],
            is_long_running=cmd_manifest.get("long_running", False),
            timeout_seconds=timeout_seconds,
            created_at=datetime.utcnow()
        )
        self.db.add(command)
        self.db.flush()  # Get command.id

        # Create parameters
        for param_manifest in cmd_manifest.get("parameters", []):
            self._create_parameter(command.id, param_manifest)

        return command

    def _update_command(self, command: SandboxedToolCommand, cmd_manifest: Dict) -> bool:
        """Update existing command. Returns True if changed."""
        changes = False

        new_template = cmd_manifest["template"]
        if command.command_template != new_template:
            command.command_template = new_template
            changes = True

        timeout_category = cmd_manifest.get("timeout_category", "standard")
        new_timeout = self.get_timeout_seconds(timeout_category)
        if command.timeout_seconds != new_timeout:
            command.timeout_seconds = new_timeout
            changes = True

        new_long_running = cmd_manifest.get("long_running", False)
        if command.is_long_running != new_long_running:
            command.is_long_running = new_long_running
            changes = True

        # Sync parameters
        params_changed = self._sync_parameters(command.id, cmd_manifest.get("parameters", []))

        return changes or params_changed

    def _sync_parameters(self, command_id: int, param_manifests: List[Dict]) -> bool:
        """Sync parameters for a command. Returns True if any changes."""
        changes = False

        # Get existing parameters
        existing_params = {
            p.parameter_name: p
            for p in self.db.query(SandboxedToolParameter).filter_by(command_id=command_id).all()
        }

        manifest_param_names = set()

        for param_manifest in param_manifests:
            param_name = param_manifest["name"]
            manifest_param_names.add(param_name)

            if param_name in existing_params:
                # Update existing parameter
                param = existing_params[param_name]
                param_changes = self._update_parameter(param, param_manifest)
                if param_changes:
                    changes = True
            else:
                # Create new parameter
                self._create_parameter(command_id, param_manifest)
                changes = True

        # Remove parameters no longer in manifest
        for param_name, param in existing_params.items():
            if param_name not in manifest_param_names:
                self.db.delete(param)
                changes = True

        return changes

    def _create_parameter(self, command_id: int, param_manifest: Dict) -> SandboxedToolParameter:
        """Create a new parameter from manifest."""
        parameter = SandboxedToolParameter(
            command_id=command_id,
            parameter_name=param_manifest["name"],
            is_mandatory=param_manifest.get("required", False),
            default_value=param_manifest.get("default"),
            description=param_manifest.get("description"),
            created_at=datetime.utcnow()
        )
        self.db.add(parameter)
        return parameter

    def _update_parameter(self, param: SandboxedToolParameter, param_manifest: Dict) -> bool:
        """Update existing parameter. Returns True if changed."""
        changes = False

        new_mandatory = param_manifest.get("required", False)
        if param.is_mandatory != new_mandatory:
            param.is_mandatory = new_mandatory
            changes = True

        new_default = param_manifest.get("default")
        if param.default_value != new_default:
            param.default_value = new_default
            changes = True

        new_description = param_manifest.get("description")
        if param.description != new_description:
            param.description = new_description
            changes = True

        return changes

    def sync_all_tools(
        self,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Discover and sync all tool manifests to the database.

        Args:
            tenant_id: Optional tenant ID for multi-tenancy

        Returns:
            Summary dict with created, updated, unchanged, and errors lists
        """
        results = {
            "created": [],
            "updated": [],
            "unchanged": [],
            "errors": [],
            "total_manifests": 0,
            "sync_time": datetime.utcnow().isoformat() + "Z"
        }

        manifests = self.discover_manifests()
        results["total_manifests"] = len(manifests)

        for manifest_path in manifests:
            try:
                manifest = self.load_manifest(manifest_path)
                self.validate_manifest(manifest, manifest_path)

                action, tool = self.sync_tool(manifest, tenant_id)

                tool_info = {
                    "name": tool.name,
                    "id": tool.id,
                    "file": manifest_path.name
                }

                if action == "created":
                    results["created"].append(tool_info)
                elif action == "updated":
                    results["updated"].append(tool_info)
                else:
                    results["unchanged"].append(tool_info)

            except ToolManifestError as e:
                logger.error(f"Manifest error: {e}")
                results["errors"].append({
                    "file": manifest_path.name,
                    "error": str(e)
                })
            except Exception as e:
                logger.error(f"Unexpected error syncing {manifest_path}: {e}", exc_info=True)
                results["errors"].append({
                    "file": manifest_path.name,
                    "error": f"Unexpected error: {e}"
                })

        # Commit all changes
        self.db.commit()

        logger.info(
            f"Tool sync complete: {len(results['created'])} created, "
            f"{len(results['updated'])} updated, "
            f"{len(results['unchanged'])} unchanged, "
            f"{len(results['errors'])} errors"
        )

        return results

    def get_tool_info(self, tool_name: str, tenant_id: Optional[str] = None) -> Optional[Dict]:
        """
        Get detailed information about a tool including its commands and parameters.

        Args:
            tool_name: Name of the tool
            tenant_id: Optional tenant ID

        Returns:
            Tool info dict or None if not found
        """
        query = self.db.query(SandboxedTool).filter(SandboxedTool.name == tool_name)
        if tenant_id:
            query = query.filter(SandboxedTool.tenant_id == tenant_id)
        else:
            query = query.filter(SandboxedTool.tenant_id.is_(None))

        tool = query.first()
        if not tool:
            return None

        commands = []
        for cmd in self.db.query(SandboxedToolCommand).filter_by(tool_id=tool.id).all():
            params = [
                {
                    "name": p.parameter_name,
                    "required": p.is_mandatory,
                    "default": p.default_value,
                    "description": p.description
                }
                for p in self.db.query(SandboxedToolParameter).filter_by(command_id=cmd.id).all()
            ]
            commands.append({
                "name": cmd.command_name,
                "template": cmd.command_template,
                "timeout_seconds": cmd.timeout_seconds,
                "parameters": params
            })

        return {
            "id": tool.id,
            "name": tool.name,
            "tool_type": tool.tool_type,
            "is_enabled": tool.is_enabled,
            "system_prompt": tool.system_prompt,
            "commands": commands,
            "created_at": tool.created_at.isoformat() if tool.created_at else None,
            "updated_at": tool.updated_at.isoformat() if tool.updated_at else None
        }


def get_tool_discovery_service(db: Session) -> ToolDiscoveryService:
    """Factory function to get a ToolDiscoveryService instance."""
    return ToolDiscoveryService(db)
