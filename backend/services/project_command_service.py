"""
Phase 15: Skill Projects - Project Command Service

Handles project command detection and execution for cross-channel project interaction.
Supports multilingual commands (PT, EN) for entering/exiting projects, listing projects,
and uploading documents via text commands.

Command Flow:
1. Incoming message checked against all active patterns for tenant
2. Patterns matched in order: enter → exit → upload → list → help
3. If match found, execute command handler
4. If no match and user is in project, process as project conversation
5. If no match and not in project, process as standard agent conversation
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ProjectCommandService:
    """
    Service for detecting and executing project commands.

    Supports multilingual command patterns with configurable templates.
    Manages user project sessions across channels (WhatsApp, Playground, Telegram).
    """

    # Command type priorities (order of matching)
    # BUG-003 Fix: Added "info" command type
    COMMAND_PRIORITIES = ["enter", "exit", "upload", "list", "info", "help"]

    # BUG-003 Fix: Built-in patterns for commands not in database
    BUILTIN_PATTERNS = {
        "info": [
            (r"^/project\s+info$", {"language_code": "en", "response_template": None, "pattern_str": r"^/project\s+info$"}),
            (r"^/projeto\s+info$", {"language_code": "pt", "response_template": None, "pattern_str": r"^/projeto\s+info$"}),
        ]
    }

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

        # Cache compiled patterns per tenant (invalidated on pattern changes)
        self._pattern_cache: Dict[str, Dict[str, List[Tuple[re.Pattern, Dict]]]] = {}

    def _get_patterns(self, tenant_id: str) -> Dict[str, List[Tuple[re.Pattern, Dict]]]:
        """
        Get compiled regex patterns for a tenant.
        Falls back to system patterns (_system) if tenant has no custom patterns.
        BUG-003 Fix: Also includes built-in patterns for commands like /project info.

        Returns:
            Dict mapping command_type to list of (compiled_pattern, pattern_info)
        """
        from models import ProjectCommandPattern

        # Check cache first
        if tenant_id in self._pattern_cache:
            return self._pattern_cache[tenant_id]

        # Load patterns from database (tenant-specific + system defaults)
        patterns = self.db.query(ProjectCommandPattern).filter(
            ProjectCommandPattern.tenant_id.in_([tenant_id, "_system"]),
            ProjectCommandPattern.is_active == True
        ).all()

        # Group by command_type, preferring tenant-specific over system
        pattern_dict: Dict[str, List[Tuple[re.Pattern, Dict]]] = {}
        seen_keys = set()

        # Sort to put tenant-specific first
        sorted_patterns = sorted(patterns, key=lambda p: 0 if p.tenant_id == tenant_id else 1)

        for pattern in sorted_patterns:
            key = f"{pattern.command_type}_{pattern.language_code}"

            # Skip if we already have a tenant-specific version
            if key in seen_keys and pattern.tenant_id == "_system":
                continue

            try:
                compiled = re.compile(pattern.pattern)

                if pattern.command_type not in pattern_dict:
                    pattern_dict[pattern.command_type] = []

                pattern_dict[pattern.command_type].append((
                    compiled,
                    {
                        "language_code": pattern.language_code,
                        "response_template": pattern.response_template,
                        "pattern_str": pattern.pattern
                    }
                ))

                seen_keys.add(key)

            except re.error as e:
                self.logger.error(f"Invalid regex pattern '{pattern.pattern}': {e}")

        # BUG-003 Fix: Add built-in patterns as fallbacks
        for command_type, builtin_patterns in self.BUILTIN_PATTERNS.items():
            if command_type not in pattern_dict:
                pattern_dict[command_type] = []

            for pattern_str, pattern_info in builtin_patterns:
                key = f"{command_type}_{pattern_info['language_code']}"
                if key not in seen_keys:
                    try:
                        compiled = re.compile(pattern_str, re.IGNORECASE)
                        pattern_dict[command_type].append((compiled, pattern_info))
                        seen_keys.add(key)
                    except re.error as e:
                        self.logger.error(f"Invalid builtin pattern '{pattern_str}': {e}")

        # Cache for this tenant
        self._pattern_cache[tenant_id] = pattern_dict
        return pattern_dict

    def invalidate_cache(self, tenant_id: Optional[str] = None):
        """
        Invalidate pattern cache.
        Call this when patterns are updated.

        Args:
            tenant_id: Specific tenant to invalidate, or None for all
        """
        if tenant_id:
            self._pattern_cache.pop(tenant_id, None)
        else:
            self._pattern_cache.clear()

    async def detect_command(
        self,
        tenant_id: str,
        message_text: str
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Detect if message is a project command.

        Args:
            tenant_id: Tenant identifier
            message_text: Raw message text

        Returns:
            Tuple of (command_type, extracted_data) or None if not a command
        """
        if not message_text or len(message_text) > 200:
            # Quick early exit for empty or very long messages
            return None

        patterns = self._get_patterns(tenant_id)

        for command_type in self.COMMAND_PRIORITIES:
            type_patterns = patterns.get(command_type, [])

            for compiled_pattern, pattern_info in type_patterns:
                match = compiled_pattern.match(message_text.strip())

                if match:
                    self.logger.info(f"Matched command: {command_type} (pattern: {pattern_info['pattern_str']})")

                    extracted = {
                        "command_type": command_type,
                        "language_code": pattern_info["language_code"],
                        "response_template": pattern_info["response_template"],
                        "groups": match.groups(),
                        "raw_match": match.group(0)
                    }

                    # Extract specific data based on command type
                    if command_type == "enter" and len(match.groups()) >= 2:
                        extracted["project_name"] = match.group(2).strip()

                    return command_type, extracted

        return None

    async def get_session(
        self,
        tenant_id: str,
        sender_key: str,
        agent_id: int,
        channel: str
    ) -> Optional[Any]:
        """
        Get current project session for a user.

        Args:
            tenant_id: Tenant identifier
            sender_key: Normalized sender identity
            agent_id: Agent ID
            channel: Channel identifier (whatsapp, playground, telegram)

        Returns:
            UserProjectSession if user is in a project, None otherwise
        """
        from models import UserProjectSession

        session = self.db.query(UserProjectSession).filter(
            UserProjectSession.tenant_id == tenant_id,
            UserProjectSession.sender_key == sender_key,
            UserProjectSession.agent_id == agent_id,
            UserProjectSession.channel == channel,
            UserProjectSession.project_id.isnot(None)
        ).first()

        return session

    async def execute_enter(
        self,
        tenant_id: str,
        sender_key: str,
        agent_id: int,
        channel: str,
        project_identifier: str,
        response_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Enter a project context.

        Creates or updates a UserProjectSession for this user/agent/channel.
        Creates a new ProjectConversation for this session.

        Args:
            tenant_id: Tenant identifier
            sender_key: Normalized sender identity
            agent_id: Agent ID
            channel: Channel identifier
            project_identifier: Project name or ID
            response_template: Optional response template

        Returns:
            Dict with status, message, project info
        """
        from models import (
            Project, UserProjectSession, ProjectConversation,
            AgentProjectAccess, ProjectKnowledge
        )

        try:
            # 1. Look up project by name (case-insensitive)
            project = self.db.query(Project).filter(
                Project.tenant_id == tenant_id,
                Project.name.ilike(project_identifier.strip()),
                Project.is_archived == False
            ).first()

            if not project:
                # Try by ID if it's a number
                try:
                    project_id = int(project_identifier)
                    project = self.db.query(Project).filter(
                        Project.id == project_id,
                        Project.tenant_id == tenant_id,
                        Project.is_archived == False
                    ).first()
                except ValueError:
                    pass

            if not project:
                return {
                    "status": "error",
                    "error": f"Project '{project_identifier}' not found",
                    "message": f"❌ Project '{project_identifier}' not found. Use 'list projects' to see available projects."
                }

            # 2. Verify agent has access to this project
            access = self.db.query(AgentProjectAccess).filter(
                AgentProjectAccess.agent_id == agent_id,
                AgentProjectAccess.project_id == project.id
            ).first()

            if not access:
                return {
                    "status": "error",
                    "error": "Agent does not have access to this project",
                    "message": f"❌ This agent doesn't have access to project '{project.name}'."
                }

            # 3. Check if user is already in a project
            existing_session = self.db.query(UserProjectSession).filter(
                UserProjectSession.tenant_id == tenant_id,
                UserProjectSession.sender_key == sender_key,
                UserProjectSession.agent_id == agent_id,
                UserProjectSession.channel == channel
            ).first()

            if existing_session and existing_session.project_id:
                # Check if trying to enter the same project
                if existing_session.project_id == project.id:
                    return {
                        "status": "already_in_project",
                        "message": f"📁 You're already in project '{project.name}'.",
                        "project_id": project.id,
                        "project_name": project.name
                    }
                else:
                    # Need to exit current project first
                    current_project = self.db.query(Project).filter(
                        Project.id == existing_session.project_id
                    ).first()
                    return {
                        "status": "error",
                        "error": "Already in another project",
                        "message": f"❌ You're currently in project '{current_project.name if current_project else 'unknown'}'. Exit first with 'exit project'."
                    }

            # 4. Create or get conversation for this session
            conversation = ProjectConversation(
                project_id=project.id,
                title=f"Chat via {channel} - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                messages_json=[]
            )
            self.db.add(conversation)
            self.db.flush()

            # 5. Create or update session
            if existing_session:
                existing_session.project_id = project.id
                existing_session.conversation_id = conversation.id
                existing_session.entered_at = datetime.utcnow()
                existing_session.updated_at = datetime.utcnow()
                session = existing_session
            else:
                session = UserProjectSession(
                    tenant_id=tenant_id,
                    sender_key=sender_key,
                    agent_id=agent_id,
                    project_id=project.id,
                    channel=channel,
                    conversation_id=conversation.id
                )
                self.db.add(session)

            # Phase 3: Ensure session is committed and verify persistence
            self.db.commit()
            self.db.refresh(session)  # Ensure we have the latest data
            self.logger.info(f"[KB FIX] Session committed: id={session.id}, project_id={session.project_id}, agent_id={session.agent_id}, sender_key={session.sender_key}")

            # 6. Get project stats
            doc_count = self.db.query(ProjectKnowledge).filter(
                ProjectKnowledge.project_id == project.id
            ).count()

            # 7. Format response
            template = response_template or '📁 Now working in project "{project_name}". Ask questions or send files to add documents.'
            message = template.format(
                project_name=project.name,
                doc_count=doc_count
            )

            # Add stats if available
            if doc_count > 0:
                message += f"\n📊 {doc_count} document{'s' if doc_count != 1 else ''} in knowledge base."

            self.logger.info(f"User {sender_key} entered project {project.id} ({project.name}) via {channel}")

            return {
                "status": "success",
                "message": message,
                "project_id": project.id,
                "project_name": project.name,
                "conversation_id": conversation.id,
                "doc_count": doc_count
            }

        except Exception as e:
            self.logger.error(f"Failed to enter project: {e}", exc_info=True)
            self.db.rollback()
            return {
                "status": "error",
                "error": str(e),
                "message": "❌ Failed to enter project. Please try again."
            }

    async def execute_exit(
        self,
        tenant_id: str,
        sender_key: str,
        agent_id: int,
        channel: str,
        response_template: Optional[str] = None,
        ai_client: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Exit current project context with summary.

        Clears the UserProjectSession.project_id and generates a conversation summary.

        Args:
            tenant_id: Tenant identifier
            sender_key: Normalized sender identity
            agent_id: Agent ID
            channel: Channel identifier
            response_template: Optional response template
            ai_client: Optional AI client for generating summaries

        Returns:
            Dict with status, message, summary
        """
        from models import Project, UserProjectSession, ProjectConversation

        try:
            # 1. Get current session
            session = self.db.query(UserProjectSession).filter(
                UserProjectSession.tenant_id == tenant_id,
                UserProjectSession.sender_key == sender_key,
                UserProjectSession.agent_id == agent_id,
                UserProjectSession.channel == channel
            ).first()

            if not session or not session.project_id:
                return {
                    "status": "not_in_project",
                    "message": "📭 You're not currently in any project."
                }

            # 2. Get project info
            project = self.db.query(Project).filter(
                Project.id == session.project_id
            ).first()

            project_name = project.name if project else "Unknown"

            # 3. Get conversation for summary
            conversation = None
            summary = ""
            message_count = 0

            if session.conversation_id:
                conversation = self.db.query(ProjectConversation).filter(
                    ProjectConversation.id == session.conversation_id
                ).first()

                if conversation and conversation.messages_json:
                    messages = conversation.messages_json
                    message_count = len(messages)

                    # Generate simple summary (or use AI if available)
                    if message_count > 0:
                        summary = f"📊 {message_count} message{'s' if message_count != 1 else ''} exchanged."

                        # TODO: Use ai_client to generate a more detailed summary if available
                        # if ai_client and message_count > 2:
                        #     summary = await self._generate_summary(ai_client, messages, project_name)

            # 4. Clear session (keep the record, just clear project_id)
            session.project_id = None
            session.conversation_id = None
            session.updated_at = datetime.utcnow()

            self.db.commit()

            # 5. Format response
            template = response_template or '✅ Left project "{project_name}". {summary}'
            message = template.format(
                project_name=project_name,
                summary=summary
            )

            self.logger.info(f"User {sender_key} exited project {project_name} via {channel}")

            return {
                "status": "success",
                "message": message,
                "project_name": project_name,
                "messages_exchanged": message_count
            }

        except Exception as e:
            self.logger.error(f"Failed to exit project: {e}", exc_info=True)
            self.db.rollback()
            return {
                "status": "error",
                "error": str(e),
                "message": "❌ Failed to exit project. Please try again."
            }

    async def execute_list(
        self,
        tenant_id: str,
        sender_key: str,
        agent_id: int,
        response_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List available projects for the user/agent.

        Args:
            tenant_id: Tenant identifier
            sender_key: Normalized sender identity
            agent_id: Agent ID
            response_template: Optional response template

        Returns:
            Dict with status, message, projects list
        """
        from models import Project, AgentProjectAccess, ProjectKnowledge

        try:
            # Get projects accessible to this agent
            accessible_projects = self.db.query(Project).join(
                AgentProjectAccess,
                AgentProjectAccess.project_id == Project.id
            ).filter(
                AgentProjectAccess.agent_id == agent_id,
                Project.tenant_id == tenant_id,
                Project.is_archived == False
            ).all()

            if not accessible_projects:
                return {
                    "status": "success",
                    "message": "📭 No projects available. Create a project in the Playground first.",
                    "projects": []
                }

            # Build project list with stats
            project_list = []
            project_lines = []

            for project in accessible_projects:
                doc_count = self.db.query(ProjectKnowledge).filter(
                    ProjectKnowledge.project_id == project.id
                ).count()

                project_info = {
                    "id": project.id,
                    "name": project.name,
                    "description": project.description,
                    "icon": project.icon,
                    "doc_count": doc_count
                }
                project_list.append(project_info)

                # Format line for display
                icon = project.icon or "📁"
                line = f"• {icon} {project.name}"
                if doc_count > 0:
                    line += f" ({doc_count} docs)"
                project_lines.append(line)

            # Format response
            template = response_template or "📋 Your projects:\n{project_list}"
            message = template.format(
                project_list="\n".join(project_lines)
            )

            return {
                "status": "success",
                "message": message,
                "projects": project_list
            }

        except Exception as e:
            self.logger.error(f"Failed to list projects: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "message": "❌ Failed to list projects. Please try again."
            }

    async def execute_info(
        self,
        tenant_id: str,
        sender_key: str,
        agent_id: int,
        channel: str,
        response_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        BUG-003 Fix: Show info about the current project the user is in.

        Args:
            tenant_id: Tenant identifier
            sender_key: Normalized sender identity
            agent_id: Agent ID
            channel: Channel identifier
            response_template: Optional response template

        Returns:
            Dict with status, message, project info
        """
        from models import Project, UserProjectSession, ProjectKnowledge, ProjectFactMemory
        from services.project_memory_service import ProjectMemoryService

        try:
            # Check if user is in a project
            session = self.db.query(UserProjectSession).filter(
                UserProjectSession.tenant_id == tenant_id,
                UserProjectSession.sender_key == sender_key,
                UserProjectSession.agent_id == agent_id,
                UserProjectSession.channel == channel
            ).first()

            if not session or not session.project_id:
                return {
                    "status": "success",
                    "message": "ℹ️ You are not currently in any project.\n\nUse `/list` to see available projects and `/enter [project_name]` to join one."
                }

            # Get project details
            project = self.db.query(Project).filter(Project.id == session.project_id).first()

            if not project:
                return {
                    "status": "error",
                    "message": "❌ Project not found. The project may have been deleted."
                }

            # Get project stats
            memory_service = ProjectMemoryService(self.db)
            stats = await memory_service.get_memory_stats(project.id)

            # Format project info message
            icon = project.icon or "📁"
            message = f"""{icon} **Project: {project.name}**
{project.description or 'No description'}

📊 **Statistics:**
• Documents: {stats.get('kb_document_count', 0)}
• Facts: {stats.get('fact_count', 0)}
• Conversations: {stats.get('conversation_count', 0)}
• Memory entries: {stats.get('semantic_memory_count', 0)}"""

            # Add memory settings
            settings = []
            if project.enable_semantic_memory:
                settings.append("Semantic Memory ✓")
            if project.enable_factual_memory:
                settings.append("Factual Memory ✓")
            if settings:
                message += f"\n\n⚙️ **Memory Settings:** {', '.join(settings)}"

            return {
                "status": "success",
                "message": message,
                "project": {
                    "id": project.id,
                    "name": project.name,
                    "description": project.description,
                    "icon": project.icon,
                    **stats
                }
            }

        except Exception as e:
            self.logger.error(f"Failed to get project info: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "message": "❌ Failed to get project info. Please try again."
            }

    async def execute_help(
        self,
        response_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Show help message for project commands.

        Args:
            response_template: Optional response template

        Returns:
            Dict with status, message
        """
        template = response_template or """📚 Project Commands:
• "enter project [name]" - Enter a project
• "exit project" - Leave current project
• "list projects" - See your projects
• "add to project" - Add document (send with file)
• "project help" - Show this help"""

        return {
            "status": "success",
            "message": template
        }

    async def handle_upload_command(
        self,
        tenant_id: str,
        sender_key: str,
        agent_id: int,
        channel: str,
        file_data: bytes,
        filename: str,
        response_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle document upload command when user is in a project.

        This is typically called when a media attachment is received
        while the user is in a project context.

        Args:
            tenant_id: Tenant identifier
            sender_key: Normalized sender identity
            agent_id: Agent ID
            channel: Channel identifier
            file_data: Raw file bytes
            filename: Original filename
            response_template: Optional response template

        Returns:
            Dict with status, message, upload result
        """
        from models import UserProjectSession
        from services.project_service import ProjectService

        try:
            # Get current session
            session = await self.get_session(tenant_id, sender_key, agent_id, channel)

            if not session or not session.project_id:
                return {
                    "status": "not_in_project",
                    "message": "📭 You're not in a project. Enter a project first with 'enter project [name]'."
                }

            # Use ProjectService to upload the document
            project_service = ProjectService(self.db)

            # Get user_id from sender_key or use a default
            # For WhatsApp users, we may not have a user_id
            # This will be handled by the service using creator_id
            result = await project_service.upload_project_document(
                tenant_id=tenant_id,
                user_id=0,  # Will use project access check instead
                project_id=session.project_id,
                file_data=file_data,
                filename=filename
            )

            if result.get("status") == "success":
                doc = result.get("document", {})
                template = response_template or '📎 Document "{filename}" added to project ({chunks} chunks processed).'
                message = template.format(
                    filename=doc.get("name", filename),
                    chunks=doc.get("num_chunks", 0)
                )

                return {
                    "status": "success",
                    "message": message,
                    "document": doc
                }
            else:
                return {
                    "status": "error",
                    "error": result.get("error", "Upload failed"),
                    "message": f"❌ Failed to upload '{filename}': {result.get('error', 'Unknown error')}"
                }

        except Exception as e:
            self.logger.error(f"Failed to upload document: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "message": "❌ Failed to upload document. Please try again."
            }

    async def get_project_context(
        self,
        project_id: int,
        query: str,
        max_results: int = 5
    ) -> str:
        """
        Get relevant context from project knowledge base.

        Args:
            project_id: Project ID
            query: Query string for semantic search
            max_results: Maximum number of results

        Returns:
            Formatted context string
        """
        from models import Project
        from services.project_service import ProjectService

        try:
            project = self.db.query(Project).filter(Project.id == project_id).first()
            if not project:
                return ""

            project_service = ProjectService(self.db)
            results = await project_service._search_project_knowledge(project, query, max_results)

            if not results:
                return ""

            # Format context
            context_parts = [f"[PROJECT CONTEXT: {project.name}]"]
            for i, result in enumerate(results, 1):
                content = result.get("content", "")
                metadata = result.get("metadata", {})
                doc_name = metadata.get("document_name", "Unknown")
                context_parts.append(f"[{i}. From '{doc_name}']:\n{content}")

            return "\n\n".join(context_parts)

        except Exception as e:
            self.logger.error(f"Failed to get project context: {e}")
            return ""
