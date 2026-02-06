"""
Email Command Service

Handles /email slash command operations:
- info: Show Gmail configuration and connection status
- list: List emails with filters (unread, today, count)
- read: Read full email content by ID or list index
- inbox: List recent emails
- search: Search emails with query
- unread: Show unread emails

Uses GmailSkill's underlying service for direct execution (zero AI tokens).
"""

import logging
import re
from typing import Dict, List, Optional, Any
from datetime import datetime

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Cache for last email list results (keyed by agent_id)
# This enables /email read <index> to work with numbered results
_last_list_cache: Dict[int, List[Dict]] = {}


class EmailCommandService:
    """
    Service for executing email slash commands.

    Provides programmatic access to Gmail functionality without AI involvement.
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def _get_gmail_service(self, agent_id: int):
        """
        Get Gmail service for the agent's configured integration.

        Raises ValueError if Gmail is not configured.
        """
        from models import AgentSkillIntegration, AgentSkill
        from hub.google.gmail_service import GmailService

        # Check if Gmail skill is enabled for this agent
        skill = self.db.query(AgentSkill).filter(
            AgentSkill.agent_id == agent_id,
            AgentSkill.skill_type == "gmail",
            AgentSkill.is_enabled == True
        ).first()

        if not skill:
            raise ValueError(
                "Gmail skill not enabled for this agent. "
                "Enable it in the agent settings to use /email commands."
            )

        # Get integration ID from skill integration config
        skill_integration = self.db.query(AgentSkillIntegration).filter(
            AgentSkillIntegration.agent_id == agent_id,
            AgentSkillIntegration.skill_type == "gmail"
        ).first()

        integration_id = None
        if skill_integration:
            integration_id = skill_integration.integration_id

        # Also check skill config
        if not integration_id and skill.config:
            integration_id = skill.config.get('integration_id')

        if not integration_id:
            raise ValueError(
                "No Gmail account connected. Please connect a Gmail account "
                "in the agent's skill integration settings."
            )

        return GmailService(self.db, integration_id)

    async def execute_info(
        self,
        tenant_id: str,
        agent_id: int,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Show Gmail integration status and configuration.

        Returns connected email, authorization date, and capabilities.
        """
        try:
            from models import AgentSkill, AgentSkillIntegration, GmailIntegration

            # Check if Gmail skill is enabled for this agent
            skill = self.db.query(AgentSkill).filter(
                AgentSkill.agent_id == agent_id,
                AgentSkill.skill_type == "gmail",
                AgentSkill.is_enabled == True
            ).first()

            if not skill:
                return {
                    "status": "success",
                    "action": "email_info",
                    "connected": False,
                    "message": (
                        "📧 **Gmail Configuration**\n\n"
                        "**Status:** Not configured\n\n"
                        "Gmail skill is not enabled for this agent.\n"
                        "Enable it in agent settings to use email commands."
                    )
                }

            # Get integration ID from skill integration config
            skill_integration = self.db.query(AgentSkillIntegration).filter(
                AgentSkillIntegration.agent_id == agent_id,
                AgentSkillIntegration.skill_type == "gmail"
            ).first()

            integration_id = None
            if skill_integration:
                integration_id = skill_integration.integration_id

            # Also check skill config
            if not integration_id and skill.config:
                integration_id = skill.config.get('integration_id')

            if not integration_id:
                return {
                    "status": "success",
                    "action": "email_info",
                    "connected": False,
                    "message": (
                        "📧 **Gmail Configuration**\n\n"
                        "**Status:** Skill enabled, no account connected\n\n"
                        "Please connect a Gmail account in agent skill settings."
                    )
                }

            # Get integration details
            gmail_integration = self.db.query(GmailIntegration).filter(
                GmailIntegration.id == integration_id
            ).first()

            if not gmail_integration:
                return {
                    "status": "error",
                    "action": "email_info",
                    "message": f"❌ Gmail integration (ID: {integration_id}) not found."
                }

            # Format authorization date
            auth_date = gmail_integration.authorized_at.strftime("%B %d, %Y at %H:%M") if gmail_integration.authorized_at else "Unknown"

            # Build message
            message = f"""📧 **Gmail Configuration**

**Status:** Connected
**Email:** {gmail_integration.email_address}
**Authorized:** {auth_date}

**Capabilities:**
- Read emails
- Search emails
- List labels
- Send emails (read-only)

**Permissions:**
- Read access
- Write access

Use `/email list` to see recent emails"""

            return {
                "status": "success",
                "action": "email_info",
                "connected": True,
                "email_address": gmail_integration.email_address,
                "authorized_at": str(gmail_integration.authorized_at),
                "message": message
            }

        except Exception as e:
            self.logger.error(f"Error in execute_info: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "email_info",
                "error": str(e),
                "message": f"❌ Failed to get email info: {str(e)}"
            }

    async def execute_list(
        self,
        tenant_id: str,
        agent_id: int,
        filter_type: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        List emails with optional filter.

        Filters:
        - None/empty: Last 10 emails
        - "unread": Only unread emails
        - "<number>": Last N emails (e.g., "20")
        - "today": Today's emails only

        Args:
            filter_type: Filter type (unread, number, today)
        """
        try:
            gmail_service = self._get_gmail_service(agent_id)

            # Parse filter
            count = 10
            query = None
            filter_label = "recent"

            if filter_type:
                filter_type = filter_type.strip().lower()

                if filter_type in ("unread", "nao_lidos"):
                    query = "is:unread"
                    count = 20
                    filter_label = "unread"
                elif filter_type in ("today", "hoje"):
                    # Gmail query for today's emails
                    today = datetime.now().strftime("%Y/%m/%d")
                    query = f"after:{today}"
                    count = 50
                    filter_label = "from today"
                elif filter_type.isdigit():
                    count = min(int(filter_type), 50)
                    filter_label = f"last {count}"

            # Fetch messages
            if query:
                messages = await gmail_service.search_messages(query, max_results=count)
            else:
                messages = await gmail_service.list_messages(max_results=count)

            if not messages:
                return {
                    "status": "success",
                    "action": "email_list",
                    "emails": [],
                    "filter": filter_label,
                    "message": f"📧 **No emails {filter_label}**\n\nYour inbox appears to be empty."
                }

            # Fetch full content for each message
            email_details = []
            for msg in messages[:count]:
                try:
                    content = await gmail_service.get_message_content(msg['id'])
                    email_details.append(content)
                except Exception as e:
                    self.logger.warning(f"Failed to get message {msg['id']}: {e}")
                    continue

            if not email_details:
                return {
                    "status": "success",
                    "action": "email_list",
                    "emails": [],
                    "filter": filter_label,
                    "message": f"📧 **No emails {filter_label}**\n\nCould not fetch email details."
                }

            # Format output
            lines = [f"📧 **Emails ({filter_label}) - {len(email_details)} found**\n"]

            for i, msg in enumerate(email_details, 1):
                from_addr = msg.get('from', 'Unknown')
                subject = msg.get('subject', '(no subject)')
                date_str = msg.get('date', '')
                snippet = msg.get('snippet', '')[:80]

                # Truncate for display
                if len(from_addr) > 40:
                    from_addr = from_addr[:37] + "..."
                if len(subject) > 50:
                    subject = subject[:47] + "..."

                # Check if unread (has UNREAD label)
                is_unread = "UNREAD" in msg.get('labels', [])
                unread_marker = "📬" if is_unread else "📧"

                lines.append(f"{unread_marker} **{i}. {subject}**")
                lines.append(f"   From: {from_addr}")
                if date_str:
                    lines.append(f"   Date: {date_str}")
                if snippet:
                    lines.append(f"   _{snippet}..._")
                lines.append("")

            # Cache results for /email read <index>
            _last_list_cache[agent_id] = email_details

            # Add helpful footer based on filter
            if filter_label == "unread":
                if len(email_details) >= count:
                    lines.append(f"_Showing first {count}. There may be more unread._")
            else:
                lines.append("**Filters:** `/email list unread` | `/email list today` | `/email list 20`")

            lines.append("**Read:** `/email read <number>` to read full email content")

            return {
                "status": "success",
                "action": "email_list",
                "emails": email_details,
                "filter": filter_label,
                "count": len(email_details),
                "message": "\n".join(lines)
            }

        except ValueError as e:
            return {
                "status": "error",
                "action": "email_list",
                "error": str(e),
                "message": f"❌ {str(e)}"
            }
        except Exception as e:
            self.logger.error(f"Error in execute_list: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "email_list",
                "error": str(e),
                "message": f"❌ Failed to list emails: {str(e)}"
            }

    async def execute_read(
        self,
        tenant_id: str,
        agent_id: int,
        identifier: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Read full email content by ID or list index.

        Args:
            identifier: Email list index (1-50) or Gmail message ID

        Examples:
            - "3" - Read email #3 from last /email list
            - "18a1b2c3d4e5f6" - Read by Gmail message ID
        """
        try:
            if not identifier or not identifier.strip():
                return {
                    "status": "error",
                    "action": "email_read",
                    "message": (
                        "❌ Please specify which email to read.\n\n"
                        "**Usage:** `/email read <number or id>`\n\n"
                        "**Examples:**\n"
                        "• `/email read 3` - Read email #3 from last list\n"
                        "• `/email read abc123` - Read by message ID\n\n"
                        "**Tip:** Use `/email list` first, then `/email read <number>`"
                    )
                }

            identifier = identifier.strip()
            gmail_service = self._get_gmail_service(agent_id)
            message_id = None

            # Check if identifier is a list index (1-50)
            if identifier.isdigit():
                index = int(identifier)
                if 1 <= index <= 50:
                    # Look up from cache
                    cached_list = _last_list_cache.get(agent_id)
                    if not cached_list:
                        return {
                            "status": "error",
                            "action": "email_read",
                            "message": (
                                f"❌ No email list cached.\n\n"
                                "Use `/email list` first, then `/email read {index}`"
                            )
                        }
                    if index > len(cached_list):
                        return {
                            "status": "error",
                            "action": "email_read",
                            "message": (
                                f"❌ Email #{index} not found.\n\n"
                                f"Last list had {len(cached_list)} emails. "
                                f"Try `/email read 1` to `/email read {len(cached_list)}`"
                            )
                        }
                    # Get message ID from cached email (index is 1-based)
                    cached_email = cached_list[index - 1]
                    message_id = cached_email.get('id')
                else:
                    # Number too large, treat as message ID
                    message_id = identifier
            else:
                # Not a number, treat as message ID
                message_id = identifier

            if not message_id:
                return {
                    "status": "error",
                    "action": "email_read",
                    "message": "❌ Could not determine message ID."
                }

            # Fetch full email content
            try:
                content = await gmail_service.get_message_content(message_id)
            except Exception as e:
                return {
                    "status": "error",
                    "action": "email_read",
                    "message": f"❌ Email not found or inaccessible: {str(e)}"
                }

            # Format email display
            subject = content.get('subject', '(no subject)')
            from_addr = content.get('from', 'Unknown')
            to_addr = content.get('to', '')
            cc_addr = content.get('cc', '')
            date_str = content.get('date', '')
            body_text = content.get('body_text', '')
            body_html = content.get('body_html', '')
            attachments = content.get('attachments', [])
            labels = content.get('labels', [])

            # Check if unread
            is_unread = "UNREAD" in labels
            status_icon = "📬" if is_unread else "📧"

            # Build message
            lines = [f"{status_icon} **{subject}**\n"]
            lines.append(f"**From:** {from_addr}")
            if to_addr:
                lines.append(f"**To:** {to_addr}")
            if cc_addr:
                lines.append(f"**Cc:** {cc_addr}")
            if date_str:
                lines.append(f"**Date:** {date_str}")

            # Show attachments if any
            if attachments:
                att_list = ", ".join([a.get('filename', 'file') for a in attachments[:5]])
                if len(attachments) > 5:
                    att_list += f" (+{len(attachments) - 5} more)"
                lines.append(f"**Attachments:** {att_list}")

            lines.append("\n---\n")

            # Add body content (prefer text, fall back to stripped HTML)
            body = body_text.strip() if body_text else ""
            if not body and body_html:
                # Strip HTML tags for basic display
                body = re.sub(r'<[^>]+>', '', body_html)
                body = re.sub(r'\s+', ' ', body).strip()

            if body:
                # Truncate if too long
                max_length = 2000
                if len(body) > max_length:
                    body = body[:max_length] + "\n\n_... (truncated, email too long)_"
                lines.append(body)
            else:
                lines.append("_(Email body is empty or not available)_")

            lines.append(f"\n---\n**ID:** `{message_id}`")

            return {
                "status": "success",
                "action": "email_read",
                "email": content,
                "message_id": message_id,
                "message": "\n".join(lines)
            }

        except ValueError as e:
            return {
                "status": "error",
                "action": "email_read",
                "error": str(e),
                "message": f"❌ {str(e)}"
            }
        except Exception as e:
            self.logger.error(f"Error in execute_read: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "email_read",
                "error": str(e),
                "message": f"❌ Failed to read email: {str(e)}"
            }

    async def execute_inbox(
        self,
        tenant_id: str,
        agent_id: int,
        count: int = 10,
        **kwargs
    ) -> Dict[str, Any]:
        """
        List recent emails from inbox.

        Args:
            count: Number of emails to retrieve (default 10, max 50)
        """
        try:
            gmail_service = self._get_gmail_service(agent_id)

            # Limit count
            count = min(count, 50)

            # Get recent messages (only returns IDs)
            messages = await gmail_service.list_messages(max_results=count)

            if not messages:
                return {
                    "status": "success",
                    "action": "email_inbox",
                    "emails": [],
                    "message": "📧 **Inbox is empty**\n\nNo emails found."
                }

            # Fetch full content for each message
            email_details = []
            for msg in messages[:count]:
                try:
                    content = await gmail_service.get_message_content(msg['id'])
                    email_details.append(content)
                except Exception as e:
                    self.logger.warning(f"Failed to get message {msg['id']}: {e}")
                    continue

            if not email_details:
                return {
                    "status": "success",
                    "action": "email_inbox",
                    "emails": [],
                    "message": "📧 **Inbox**\n\nCould not fetch email details."
                }

            # Format message list
            lines = [f"📧 **Recent Emails ({len(email_details)})**\n"]

            for i, msg in enumerate(email_details, 1):
                # Get message details
                from_addr = msg.get('from', 'Unknown')
                subject = msg.get('subject', '(no subject)')
                date_str = msg.get('date', '')
                snippet = msg.get('snippet', '')[:100]

                # Truncate from address if too long
                if len(from_addr) > 40:
                    from_addr = from_addr[:37] + "..."

                # Truncate subject if too long
                if len(subject) > 50:
                    subject = subject[:47] + "..."

                # Check if unread
                is_unread = "UNREAD" in msg.get('labels', [])
                unread_marker = "📬" if is_unread else "📧"

                lines.append(f"{unread_marker} **{i}. {subject}**")
                lines.append(f"   From: {from_addr}")
                if date_str:
                    lines.append(f"   Date: {date_str}")
                if snippet:
                    lines.append(f"   _{snippet}..._")
                lines.append("")

            # Cache results for /email read <index>
            _last_list_cache[agent_id] = email_details

            lines.append("💡 Use `/email search \"query\"` to search for specific emails")
            lines.append("**Read:** `/email read <number>` to read full email content")

            return {
                "status": "success",
                "action": "email_inbox",
                "emails": email_details,
                "count": len(email_details),
                "message": "\n".join(lines)
            }

        except ValueError as e:
            return {
                "status": "error",
                "action": "email_inbox",
                "error": str(e),
                "message": f"❌ {str(e)}"
            }
        except Exception as e:
            self.logger.error(f"Error in execute_inbox: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "email_inbox",
                "error": str(e),
                "message": f"❌ Failed to fetch inbox: {str(e)}"
            }

    async def execute_search(
        self,
        tenant_id: str,
        agent_id: int,
        query: str,
        count: int = 10,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Search emails with Gmail query syntax.

        Args:
            query: Search query (Gmail syntax supported)
            count: Number of results (default 10, max 50)

        Examples:
            - "meeting" - Search all fields for "meeting"
            - "subject:invoice" - Search subject only
            - "from:john@example.com" - Search by sender
            - "has:attachment" - With attachments
            - "newer_than:7d" - Last 7 days
        """
        try:
            if not query or not query.strip():
                return {
                    "status": "error",
                    "action": "email_search",
                    "message": (
                        "❌ Please specify a search query.\n\n"
                        "**Usage:** `/email search \"query\"`\n\n"
                        "**Examples:**\n"
                        "• `/email search \"meeting\"` - Search all fields\n"
                        "• `/email search \"subject:invoice\"` - Subject only\n"
                        "• `/email search \"from:john@example.com\"` - By sender\n"
                        "• `/email search \"has:attachment\"` - With attachments\n"
                        "• `/email search \"newer_than:7d\"` - Last 7 days"
                    )
                }

            gmail_service = self._get_gmail_service(agent_id)

            # Limit count
            count = min(count, 50)

            # Search messages (returns only IDs)
            messages = await gmail_service.search_messages(query.strip(), max_results=count)

            if not messages:
                return {
                    "status": "success",
                    "action": "email_search",
                    "emails": [],
                    "query": query,
                    "message": f"🔍 **No emails found**\n\nSearch: \"{query}\"\n\nTry a different search term."
                }

            # Fetch full content for each message
            email_details = []
            for msg in messages[:count]:
                try:
                    content = await gmail_service.get_message_content(msg['id'])
                    email_details.append(content)
                except Exception as e:
                    self.logger.warning(f"Failed to get message {msg['id']}: {e}")
                    continue

            if not email_details:
                return {
                    "status": "success",
                    "action": "email_search",
                    "emails": [],
                    "query": query,
                    "message": f"🔍 **Search: \"{query}\"**\n\nCould not fetch email details."
                }

            # Format results
            lines = [f"🔍 **Search Results ({len(email_details)})**\n"]
            lines.append(f"Query: `{query}`\n")

            for i, msg in enumerate(email_details, 1):
                from_addr = msg.get('from', 'Unknown')
                subject = msg.get('subject', '(no subject)')
                date_str = msg.get('date', '')
                snippet = msg.get('snippet', '')[:80]

                if len(from_addr) > 40:
                    from_addr = from_addr[:37] + "..."
                if len(subject) > 50:
                    subject = subject[:47] + "..."

                # Check if unread
                is_unread = "UNREAD" in msg.get('labels', [])
                unread_marker = "📬" if is_unread else "📧"

                lines.append(f"{unread_marker} **{i}. {subject}**")
                lines.append(f"   From: {from_addr}")
                if date_str:
                    lines.append(f"   Date: {date_str}")
                if snippet:
                    lines.append(f"   _{snippet}..._")
                lines.append("")

            # Cache results for /email read <index>
            _last_list_cache[agent_id] = email_details

            lines.append("**Read:** `/email read <number>` to read full email content")

            return {
                "status": "success",
                "action": "email_search",
                "emails": email_details,
                "query": query,
                "count": len(email_details),
                "message": "\n".join(lines)
            }

        except ValueError as e:
            return {
                "status": "error",
                "action": "email_search",
                "error": str(e),
                "message": f"❌ {str(e)}"
            }
        except Exception as e:
            self.logger.error(f"Error in execute_search: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "email_search",
                "error": str(e),
                "message": f"❌ Search failed: {str(e)}"
            }

    async def execute_unread(
        self,
        tenant_id: str,
        agent_id: int,
        count: int = 20,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Show unread emails.

        Args:
            count: Maximum number of unread emails to show (default 20)
        """
        try:
            gmail_service = self._get_gmail_service(agent_id)

            # Search for unread messages (returns only IDs)
            messages = await gmail_service.search_messages("is:unread", max_results=count)

            if not messages:
                return {
                    "status": "success",
                    "action": "email_unread",
                    "emails": [],
                    "message": "📧 **No unread emails!** 🎉\n\nYour inbox is all caught up."
                }

            # Fetch full content for each message
            email_details = []
            for msg in messages[:count]:
                try:
                    content = await gmail_service.get_message_content(msg['id'])
                    email_details.append(content)
                except Exception as e:
                    self.logger.warning(f"Failed to get message {msg['id']}: {e}")
                    continue

            if not email_details:
                return {
                    "status": "success",
                    "action": "email_unread",
                    "emails": [],
                    "message": "📬 **Unread Emails**\n\nCould not fetch email details."
                }

            # Format results
            lines = [f"📬 **Unread Emails ({len(email_details)})**\n"]

            for i, msg in enumerate(email_details, 1):
                from_addr = msg.get('from', 'Unknown')
                subject = msg.get('subject', '(no subject)')
                date_str = msg.get('date', '')
                snippet = msg.get('snippet', '')[:80]

                if len(from_addr) > 40:
                    from_addr = from_addr[:37] + "..."
                if len(subject) > 50:
                    subject = subject[:47] + "..."

                lines.append(f"📬 **{i}. {subject}**")
                lines.append(f"   From: {from_addr}")
                if date_str:
                    lines.append(f"   Date: {date_str}")
                if snippet:
                    lines.append(f"   _{snippet}..._")
                lines.append("")

            # Cache results for /email read <index>
            _last_list_cache[agent_id] = email_details

            if len(email_details) >= count:
                lines.append(f"_Showing first {count} unread. There may be more._")

            lines.append("**Read:** `/email read <number>` to read full email content")

            return {
                "status": "success",
                "action": "email_unread",
                "emails": email_details,
                "count": len(email_details),
                "message": "\n".join(lines)
            }

        except ValueError as e:
            return {
                "status": "error",
                "action": "email_unread",
                "error": str(e),
                "message": f"❌ {str(e)}"
            }
        except Exception as e:
            self.logger.error(f"Error in execute_unread: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "email_unread",
                "error": str(e),
                "message": f"❌ Failed to fetch unread emails: {str(e)}"
            }
