"""
Gmail Skill - Email Reading for Agents

Allows agents to read and search emails from connected Gmail accounts.
Supports per-agent integration selection (multiple Gmail accounts per tenant).

Features:
- List recent emails
- Search emails with Gmail query syntax
- Get specific email content
- Thread viewing

Note: Read-only access. Sending emails is not supported.

Sub-capabilities:
- list_emails: View recent messages in inbox
- search_emails: Search with Gmail query syntax
- read_email: Get full email content
- list_threads: View email threads
"""

from .base import BaseSkill, InboundMessage, SkillResult
from typing import Dict, Any, Optional
import logging
import re

logger = logging.getLogger(__name__)


class GmailSkill(BaseSkill):
    """
    Gmail reading skill for agents.

    Allows agents to access emails from connected Gmail accounts.
    Each agent can be configured to use a specific Gmail integration.

    Skills-as-Tools (Phase 3):
    - Tool name: gmail_operation
    - Execution mode: hybrid (supports both tool and legacy keyword modes)
    - Actions: list, search, read

    Example:
        Agent "Support Bot" uses support@company.com
        Agent "Sales Assistant" uses sales@company.com
    """

    skill_type = "gmail"
    skill_name = "Gmail"
    skill_description = "Read and search emails from connected Gmail accounts"
    execution_mode = "hybrid"  # Support both tool and legacy modes

    # Keywords that trigger this skill
    EMAIL_KEYWORDS = [
        # Portuguese
        "email", "e-mail", "emails", "mensagem", "mensagens",
        "inbox", "caixa de entrada", "correio",
        # English
        "mail", "inbox", "message", "messages",
        # Actions
        "ler", "leia", "mostrar", "ver", "listar",
        "read", "show", "list", "check", "search"
    ]

    def __init__(self):
        """Initialize Gmail skill."""
        super().__init__()
        self._gmail_service = None
        self._integration_id: Optional[int] = None

    def set_db_session(self, db):
        """Override to reset service cache."""
        super().set_db_session(db)
        self._gmail_service = None

    def _get_gmail_service(self, config: Dict[str, Any] = None):
        """
        Get Gmail service for the configured integration.

        Reads integration_id from skill config or AgentSkillIntegration.
        """
        if self._gmail_service is not None:
            return self._gmail_service

        config = config or getattr(self, '_config', {}) or {}

        # Get integration ID from config
        integration_id = config.get('integration_id')

        # Try to load from AgentSkillIntegration if not in config
        if not integration_id:
            agent_id = getattr(self, '_agent_id', None)
            if agent_id and self._db_session:
                try:
                    from models import AgentSkillIntegration

                    # AgentSkillIntegration is scoped by agent_id (tenant isolation
                    # is enforced at the Agent level upstream)
                    skill_config = self._db_session.query(AgentSkillIntegration).filter(
                        AgentSkillIntegration.agent_id == agent_id,
                        AgentSkillIntegration.skill_type == 'gmail',
                    ).first()

                    if skill_config:
                        integration_id = skill_config.integration_id
                except Exception as e:
                    logger.warning(f"GmailSkill: Error loading skill integration: {e}")

        if not integration_id:
            raise ValueError(
                "Gmail integration not configured. Please select a Gmail account "
                "in the agent's skill settings."
            )

        from hub.google.gmail_service import GmailService
        self._gmail_service = GmailService(self._db_session, integration_id)
        self._integration_id = integration_id

        return self._gmail_service

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Determine if this message should be handled by Gmail skill.

        Uses keyword matching + AI classification.
        """
        config = getattr(self, '_config', {}) or self.get_default_config()

        # Skills-as-Tools: If in tool-only mode, don't handle via keywords
        if not self.is_legacy_enabled(config):
            return False

        capabilities = config.get('capabilities', {})
        body_lower = message.body.lower()

        # Check if skill is enabled
        if not config.get('enabled', True):
            return False

        # Get keywords from config or defaults
        keywords = config.get('keywords', self.EMAIL_KEYWORDS)

        # Keyword pre-filter
        if not any(kw in body_lower for kw in keywords):
            logger.debug(f"GmailSkill: No keyword match in '{message.body[:50]}...'")
            return False

        logger.info(f"GmailSkill: Keywords matched in '{message.body[:50]}...'")

        # Check if any capability is enabled
        has_enabled_capability = any(
            cap.get('enabled', True) if isinstance(cap, dict) else True
            for cap in capabilities.values()
        ) if capabilities else True

        if not has_enabled_capability:
            logger.info("GmailSkill: All capabilities disabled")
            return False

        # Use AI fallback if enabled
        use_ai = config.get('use_ai_fallback', True)
        if use_ai:
            result = await self._ai_classify(message.body, config)
            logger.info(f"GmailSkill: AI classification result={result}")
            return result

        return True

    async def _ai_classify(self, message: str, config: Dict[str, Any]) -> bool:
        """
        Override AI classification with Gmail-specific examples.

        Provides specific examples for email operations to improve accuracy.
        """
        from agent.skills.ai_classifier import get_classifier

        classifier = get_classifier()
        ai_model = config.get("ai_model", "gemini-2.5-flash")

        # Gmail-specific examples
        custom_examples = {
            "yes": [
                "Show me my emails",
                "List my inbox",
                "Show recent emails",
                "Check my email",
                "What emails do I have?",
                "Read my latest messages",
                "Search emails from John",
                "Find emails about meeting",
                "Ver meus emails",
                "Mostrar minha caixa de entrada",
                "Listar emails recentes",
                "Procurar emails sobre projeto",
                "Ler minhas mensagens",
                "Buscar emails do trabalho",
                "Show me my latest emails in the inbox",
                "What's in my inbox?",
                "Any new emails?",
                "Do I have new messages?",
            ],
            "no": [
                "What is email?",
                "How do I send an email?",
                "Can you write an email for me?",
                "Help me compose a message",
                "Set a reminder",
                "Schedule a meeting",
                "What time is it?",
                "Tell me about yourself",
                "Create a task",
            ]
        }

        return await classifier.classify_intent(
            message=message,
            skill_name=self.skill_name,
            skill_description=self.skill_description,
            model=ai_model,
            custom_examples=custom_examples,
            db=self._db_session
        )

    async def _detect_gmail_intent(self, text: str) -> str:
        """
        Detect Gmail operation intent.

        Returns: 'list', 'search', 'read', 'unknown'
        """
        # Normalize: convert e-mail to email, remove extra spaces
        text_lower = text.lower().replace('e-mail', 'email').replace('-', ' ')

        # Read specific email patterns - MUST BE CHECKED FIRST
        # These patterns indicate user wants to see content of a specific email
        read_patterns = [
            # Portuguese - specific email content
            r'conteúdo.*email',
            r'conteudo.*email',
            r'ler\s+(o\s+)?email',
            r'abrir\s+(o\s+)?email',
            r'mostrar\s+(o\s+)?email',
            r'ver\s+(o\s+)?(conteúdo|conteudo)',
            r'último\s+email',
            r'ultimo\s+email',
            r'email\s+mais\s+recente',
            r'(primeiro|último|ultimo)\s+(email|mensagem)',
            r'qual\s+(é\s+)?meu\s+(último|ultimo)\s+email',
            r'mostrar?\s+(o\s+)?(último|ultimo)',
            # English - specific email content
            r'read\s+(the\s+)?(latest|last|recent)\s+email',
            r'open\s+(the\s+)?(latest|last|recent)\s+email',
            r'show\s+(the\s+)?content',
            r'show\s+(me\s+)?(the\s+)?(latest|last|most\s+recent)\s+email',
            r'(latest|last|most\s+recent)\s+email\s+content',
            r'what\s+(is|does)\s+(my\s+)?(latest|last)\s+email\s+(say|contain)',
        ]

        for pattern in read_patterns:
            if re.search(pattern, text_lower):
                logger.info(f"GmailSkill: Intent 'read' matched pattern: {pattern}")
                return 'read'

        # Search patterns
        search_patterns = [
            r'buscar?\s+email',
            r'procurar?\s+email',
            r'search.*email',
            r'find.*email',
            r'email.*de\s+(\w+)',
            r'email.*from\s+(\w+)',
            r'email.*sobre\s+(\w+)',
            r'email.*about\s+(\w+)',
        ]

        for pattern in search_patterns:
            if re.search(pattern, text_lower):
                return 'search'

        # List patterns (default for general email requests)
        list_patterns = [
            r'listar?\s+email',
            r'ver\s+email',
            r'meus\s+email',
            r'inbox',
            r'caixa\s+de\s+entrada',
            r'list.*email',
            r'my\s+email',
            r'check.*email',
            r'show\s+(me\s+)?(my\s+)?emails',  # plural = list
            r'quais\s+(são\s+)?(meus\s+)?emails',
        ]

        for pattern in list_patterns:
            if re.search(pattern, text_lower):
                return 'list'

        # Default to list
        return 'list'

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process the email-related request.

        Routes to appropriate handler based on intent.
        """
        try:
            # Get Gmail service (validates integration)
            gmail_service = self._get_gmail_service(config)

            # Detect intent
            intent = await self._detect_gmail_intent(message.body)
            logger.info(f"GmailSkill: Detected intent: {intent}")

            if intent == 'list':
                return await self._handle_list_emails(message, config, gmail_service)
            elif intent == 'search':
                return await self._handle_search_emails(message, config, gmail_service)
            elif intent == 'read':
                return await self._handle_read_email(message, config, gmail_service)
            else:
                return SkillResult(
                    success=False,
                    output="❌ Could not understand. Try:\n• 'List emails'\n• 'Search email from [person]'\n• 'Read email'",
                    metadata={'error': 'unknown_intent', 'skip_ai': True}
                )

        except ValueError as e:
            logger.error(f"GmailSkill: Configuration error: {e}")
            return SkillResult(
                success=False,
                output=f"❌ Gmail not configured: {str(e)}",
                metadata={'error': 'not_configured', 'skip_ai': True}
            )
        except Exception as e:
            logger.error(f"GmailSkill: Error processing: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Error accessing Gmail: {str(e)}",
                metadata={'error': str(e)}
            )

    async def _handle_list_emails(
        self,
        message: InboundMessage,
        config: Dict[str, Any],
        gmail_service
    ) -> SkillResult:
        """Handle list emails request."""
        max_results = config.get('default_max_results', 10)

        # Check if there are any filters (date, sender, subject) in the message
        query, filters = self._build_email_query(message.body)

        if query:
            # If filters exist, use search instead of list
            logger.info(f"GmailSkill: Listing with filters: {query}")
            messages = await gmail_service.search_messages(query, max_results=max_results)
        else:
            # No filters, get all recent messages
            logger.info(f"GmailSkill: Listing {max_results} recent emails (no filters)")
            messages = await gmail_service.list_messages(max_results=max_results)

        if not messages:
            # Build descriptive message based on filters
            if filters:
                filter_desc = []
                if filters.get('subject'):
                    filter_desc.append(f"subject '{filters['subject']}'")
                if filters.get('sender'):
                    filter_desc.append(f"from '{filters['sender']}'")
                if filters.get('date'):
                    filter_desc.append("today")
                filter_str = ', '.join(filter_desc)
                message_text = f"📧 No emails found ({filter_str})."
            else:
                message_text = "📧 No emails found in inbox."

            return SkillResult(
                success=True,
                output=message_text,
                metadata={'skip_ai': True, 'count': 0, 'filters': filters}
            )

        # Get details for each message
        email_summaries = []
        for msg in messages[:max_results]:
            try:
                content = await gmail_service.get_message_content(msg['id'])
                email_summaries.append({
                    'id': msg['id'],
                    'from': content['from'],
                    'subject': content['subject'],
                    'date': content['date'],
                    'snippet': content['snippet'][:100] if content.get('snippet') else ''
                })
            except Exception as e:
                logger.warning(f"Error getting message {msg['id']}: {e}")

        # Build header based on filters
        if filters:
            filter_desc = []
            if filters.get('subject'):
                filter_desc.append(f"subject '{filters['subject']}'")
            if filters.get('sender'):
                filter_desc.append(f"from '{filters['sender']}'")
            if filters.get('date'):
                filter_desc.append("today")
            filter_str = ' - ' + ', '.join(filter_desc) if filter_desc else ''
            header = f"📧 {len(email_summaries)} emails{filter_str}:\n"
        else:
            header = f"📧 Latest {len(email_summaries)} emails:\n"

        # Format output
        lines = [header]

        for i, email in enumerate(email_summaries, 1):
            from_addr = email['from'].split('<')[0].strip() if '<' in email['from'] else email['from']
            lines.append(f"{i}. **{email['subject'][:50]}...**")
            lines.append(f"   From: {from_addr}")
            lines.append(f"   {email['snippet'][:80]}...")
            lines.append("")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            processed_content="\n".join(lines),
            metadata={'skip_ai': True, 'count': len(email_summaries), 'emails': email_summaries}
        )

    async def _handle_search_emails(
        self,
        message: InboundMessage,
        config: Dict[str, Any],
        gmail_service
    ) -> SkillResult:
        """Handle search emails request."""
        # Use the unified query builder that extracts ALL filters (subject, sender, date)
        query, filters = self._build_email_query(message.body)

        # If no filters extracted, use the whole message as query
        if not query:
            text = message.body.lower()
            # Remove common words
            query = re.sub(r'\b(buscar?|procurar?|search|find|email|emails|e-mail|meus|my|de|from)\b', '', text)
            query = query.strip()

        logger.info(f"GmailSkill: Searching with query: {query}, filters: {filters}")

        max_results = config.get('default_max_results', 10)
        messages = await gmail_service.search_messages(query, max_results=max_results)

        if not messages:
            # Build descriptive error message
            filter_desc = []
            if filters.get('subject'):
                filter_desc.append(f"subject '{filters['subject']}'")
            if filters.get('sender'):
                filter_desc.append(f"from '{filters['sender']}'")
            if filters.get('date'):
                filter_desc.append("specified date")

            filter_str = ', '.join(filter_desc) if filter_desc else f"'{query}'"

            return SkillResult(
                success=True,
                output=f"📧 No emails found for: {filter_str}",
                metadata={'skip_ai': True, 'count': 0, 'query': query, 'filters': filters}
            )

        # Get details
        email_summaries = []
        for msg in messages[:max_results]:
            try:
                content = await gmail_service.get_message_content(msg['id'])
                email_summaries.append({
                    'id': msg['id'],
                    'from': content['from'],
                    'subject': content['subject'],
                    'date': content['date'],
                    'snippet': content['snippet'][:100] if content.get('snippet') else ''
                })
            except Exception as e:
                logger.warning(f"Error getting message {msg['id']}: {e}")

        # Build result description
        filter_desc = []
        if filters.get('subject'):
            filter_desc.append(f"subject '{filters['subject']}'")
        if filters.get('sender'):
            filter_desc.append(f"from '{filters['sender']}'")
        if filters.get('date'):
            filter_desc.append("today")

        filter_str = ', '.join(filter_desc) if filter_desc else query

        # Format output
        lines = [f"📧 {len(email_summaries)} emails found ({filter_str}):\n"]

        for i, email in enumerate(email_summaries, 1):
            from_addr = email['from'].split('<')[0].strip() if '<' in email['from'] else email['from']
            lines.append(f"{i}. **{email['subject'][:50]}**")
            lines.append(f"   From: {from_addr}")
            lines.append(f"   {email['snippet'][:80]}...")
            lines.append("")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            processed_content="\n".join(lines),
            metadata={'skip_ai': True, 'count': len(email_summaries), 'query': query, 'emails': email_summaries}
        )

    def _extract_subject_filter(self, text: str) -> Optional[str]:
        """
        Extract subject filter from user message.

        Supports patterns like:
        - "email com assunto X"
        - "email com o assunto X"
        - "email with subject X"
        - Subject in quotes: "assunto 'NETXAR Template'" or 'assunto "NETXAR Template"'
        """
        # Patterns to extract subject (with quoted values first)
        patterns = [
            # Portuguese - quoted values
            r'(?:assunto|subject)\s*[:\s]*["\']([^"\']+)["\']',
            r'com\s+(?:o\s+)?(?:assunto|subject)\s*[:\s]*["\']([^"\']+)["\']',
            # English - quoted values
            r'(?:with\s+)?subject\s*[:\s]*["\']([^"\']+)["\']',
            # Portuguese - unquoted (capture until common stop words)
            r'(?:assunto|subject)\s*[:\s]*([^\s,?!]+(?:\s+[^\s,?!]+)*?)(?:\s+(?:no|na|do|da|de|em|para|$)|\?|$)',
            r'com\s+(?:o\s+)?(?:assunto|subject)\s*[:\s]*([^\s,?!]+(?:\s+[^\s,?!]+)*?)(?:\s+(?:no|na|do|da|de|em|para|$)|\?|$)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                subject = match.group(1).strip()
                # Clean up common trailing words
                subject = re.sub(r'\s*(no|na|do|da|de|em|para)\s*$', '', subject, flags=re.IGNORECASE)
                if subject:
                    logger.info(f"GmailSkill: Extracted subject filter: '{subject}'")
                    return subject

        return None

    def _extract_sender_filter(self, text: str) -> Optional[str]:
        """
        Extract sender filter from user message.

        Supports patterns like:
        - "email de fulano@email.com"
        - "email from john@example.com"
        - "email do João"
        - "email da Maria"
        - "email de jenny.feliz@netxar.com"

        Note: Excludes date keywords to avoid false matches.
        """
        # Date keywords to exclude from sender matching
        date_keywords = ['hoje', 'today', 'ontem', 'yesterday', 'esta semana', 'this week']

        # Check if this looks like a date filter, not a sender filter
        text_lower = text.lower()
        for date_kw in date_keywords:
            if re.search(rf'\b(de|do|da|from)\s+{date_kw}\b', text_lower):
                logger.info(f"GmailSkill: Skipping sender extraction - detected date keyword '{date_kw}'")
                return None

        patterns = [
            # Email address patterns (most specific first)
            r'(?:de|do|da|from)\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            # Quoted sender name
            r'(?:de|do|da|from)\s+["\']([^"\']+)["\']',
            # Name patterns (capture until common stop words or punctuation)
            r'(?:de|do|da|from)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s.]+?)(?:\s+(?:com|with|sobre|about|no|na|do|da|em|para)|\?|$)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                sender = match.group(1).strip()
                # Only clean up trailing words if NOT an email address
                # (avoid removing .com from email addresses!)
                if '@' not in sender:
                    sender = re.sub(r'\s+(com|with|sobre|about|no|na|do|da|em|para)\s*$', '', sender, flags=re.IGNORECASE)
                if sender and len(sender) > 1:
                    logger.info(f"GmailSkill: Extracted sender filter: '{sender}'")
                    return sender

        return None

    def _extract_date_filter(self, text: str) -> Optional[str]:
        """
        Extract date filter from user message and return Gmail query format.

        Supports patterns like:
        - "email de hoje" / "today's email" → after:YYYY/MM/DD
        - "email de ontem" / "yesterday" → after:YYYY/MM/DD before:YYYY/MM/DD
        - "email de dezembro 14, 2025" / "december 14, 2025"
        - "email de 14/12/2025" or "14-12-2025"

        Returns Gmail date query string or None.
        """
        from datetime import datetime, timedelta

        text_lower = text.lower()
        today = datetime.now()

        # Today patterns
        if any(kw in text_lower for kw in ['hoje', 'today', 'de hoje', "today's"]):
            date_str = today.strftime('%Y/%m/%d')
            logger.info(f"GmailSkill: Extracted date filter: today → after:{date_str}")
            return f'after:{date_str}'

        # Yesterday patterns
        if any(kw in text_lower for kw in ['ontem', 'yesterday']):
            yesterday = today - timedelta(days=1)
            after_str = yesterday.strftime('%Y/%m/%d')
            before_str = today.strftime('%Y/%m/%d')
            logger.info(f"GmailSkill: Extracted date filter: yesterday → after:{after_str} before:{before_str}")
            return f'after:{after_str} before:{before_str}'

        # This week patterns
        if any(kw in text_lower for kw in ['esta semana', 'this week', 'dessa semana']):
            # Start of week (Monday)
            start_of_week = today - timedelta(days=today.weekday())
            date_str = start_of_week.strftime('%Y/%m/%d')
            logger.info(f"GmailSkill: Extracted date filter: this week → after:{date_str}")
            return f'after:{date_str}'

        # Specific date patterns: DD/MM/YYYY or DD-MM-YYYY
        date_match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', text)
        if date_match:
            day, month, year = date_match.groups()
            try:
                specific_date = datetime(int(year), int(month), int(day))
                next_day = specific_date + timedelta(days=1)
                after_str = specific_date.strftime('%Y/%m/%d')
                before_str = next_day.strftime('%Y/%m/%d')
                logger.info(f"GmailSkill: Extracted date filter: {day}/{month}/{year} → after:{after_str} before:{before_str}")
                return f'after:{after_str} before:{before_str}'
            except ValueError:
                pass

        # Month name patterns (Portuguese and English)
        month_names = {
            'janeiro': 1, 'january': 1, 'jan': 1,
            'fevereiro': 2, 'february': 2, 'feb': 2,
            'março': 3, 'march': 3, 'mar': 3,
            'abril': 4, 'april': 4, 'apr': 4,
            'maio': 5, 'may': 5,
            'junho': 6, 'june': 6, 'jun': 6,
            'julho': 7, 'july': 7, 'jul': 7,
            'agosto': 8, 'august': 8, 'aug': 8,
            'setembro': 9, 'september': 9, 'sep': 9, 'sept': 9,
            'outubro': 10, 'october': 10, 'oct': 10,
            'novembro': 11, 'november': 11, 'nov': 11,
            'dezembro': 12, 'december': 12, 'dec': 12,
        }

        # Pattern: "month day, year" or "day de month de year"
        for month_name, month_num in month_names.items():
            # English: "december 14, 2025" or "december 14 2025"
            match = re.search(rf'{month_name}\s+(\d{{1,2}})[,\s]+(\d{{4}})', text_lower)
            if match:
                day, year = match.groups()
                try:
                    specific_date = datetime(int(year), month_num, int(day))
                    next_day = specific_date + timedelta(days=1)
                    after_str = specific_date.strftime('%Y/%m/%d')
                    before_str = next_day.strftime('%Y/%m/%d')
                    logger.info(f"GmailSkill: Extracted date filter: {month_name} {day}, {year} → after:{after_str} before:{before_str}")
                    return f'after:{after_str} before:{before_str}'
                except ValueError:
                    pass

            # Portuguese: "14 de dezembro de 2025"
            match = re.search(rf'(\d{{1,2}})\s+de\s+{month_name}(?:\s+de)?\s+(\d{{4}})', text_lower)
            if match:
                day, year = match.groups()
                try:
                    specific_date = datetime(int(year), month_num, int(day))
                    next_day = specific_date + timedelta(days=1)
                    after_str = specific_date.strftime('%Y/%m/%d')
                    before_str = next_day.strftime('%Y/%m/%d')
                    logger.info(f"GmailSkill: Extracted date filter: {day} de {month_name} de {year} → after:{after_str} before:{before_str}")
                    return f'after:{after_str} before:{before_str}'
                except ValueError:
                    pass

        return None

    def _build_email_query(self, text: str) -> tuple[Optional[str], dict]:
        """
        Build Gmail search query from user message by extracting all filters.

        Returns:
            Tuple of (query_string or None, metadata dict with extracted filters)
        """
        filters = {}
        query_parts = []

        # Extract subject filter
        subject = self._extract_subject_filter(text)
        if subject:
            filters['subject'] = subject
            query_parts.append(f'subject:"{subject}"')

        # Extract sender filter
        sender = self._extract_sender_filter(text)
        if sender:
            filters['sender'] = sender
            query_parts.append(f'from:{sender}')

        # Extract date filter
        date_query = self._extract_date_filter(text)
        if date_query:
            filters['date'] = date_query
            query_parts.append(date_query)

        if query_parts:
            query = ' '.join(query_parts)
            logger.info(f"GmailSkill: Built query: {query}")
            return query, filters

        return None, filters

    async def _handle_read_email(
        self,
        message: InboundMessage,
        config: Dict[str, Any],
        gmail_service
    ) -> SkillResult:
        """Handle read specific email request."""
        # Build search query from all available filters
        query, filters = self._build_email_query(message.body)

        if query:
            # Search for emails with the specified filters
            logger.info(f"GmailSkill: Searching for email with query: {query}")
            messages = await gmail_service.search_messages(query, max_results=1)

            if not messages:
                # Build descriptive error message
                filter_desc = []
                if filters.get('subject'):
                    filter_desc.append(f"subject '{filters['subject']}'")
                if filters.get('sender'):
                    filter_desc.append(f"from '{filters['sender']}'")
                if filters.get('date'):
                    filter_desc.append(f"date '{filters['date']}'")

                filter_str = ', '.join(filter_desc) if filter_desc else 'the specified filters'

                return SkillResult(
                    success=True,
                    output=f"📧 No email found with {filter_str}.",
                    metadata={'skip_ai': True, 'filters': filters}
                )
        else:
            # No filters, get the most recent email
            messages = await gmail_service.list_messages(max_results=1)

            if not messages:
                return SkillResult(
                    success=True,
                    output="📧 No email to read.",
                    metadata={'skip_ai': True}
                )

        content = await gmail_service.get_message_content(messages[0]['id'])

        # Format email content
        from_addr = content['from']
        subject = content['subject']
        date = content['date']
        body = content['body_text'] or content['snippet']

        # Truncate body if too long
        if len(body) > 1000:
            body = body[:1000] + "..."

        output = f"""📧 **{subject}**

**From:** {from_addr}
**Date:** {date}

---

{body}
"""

        return SkillResult(
            success=True,
            output=output,
            processed_content=output,
            metadata={'skip_ai': False, 'email': content}  # Let AI summarize if needed
        )

    # =========================================================================
    # SKILLS-AS-TOOLS: MCP TOOL DEFINITION (Phase 3)
    # =========================================================================

    @classmethod
    def get_mcp_tool_definition(cls) -> Dict[str, Any]:
        """
        Return MCP-compliant tool definition for Gmail operations.

        MCP Spec: https://modelcontextprotocol.io/docs/concepts/tools
        """
        return {
            "name": "gmail_operation",
            "title": "Gmail Operations",
            "description": (
                "Interact with Gmail inbox - list, search, or read emails. "
                "Use when user asks about their emails, inbox, or wants to check messages."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "search", "read"],
                        "description": "Action to perform: 'list' (recent emails), 'search' (find specific emails), 'read' (get email content)"
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query for 'search' action. Supports Gmail query syntax (e.g., 'from:john@example.com', 'subject:meeting')"
                    },
                    "sender": {
                        "type": "string",
                        "description": "Filter by sender email or name (for search/list actions)"
                    },
                    "subject": {
                        "type": "string",
                        "description": "Filter by subject text (for search/list actions)"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of emails to return",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50
                    }
                },
                "required": ["action"]
            },
            "annotations": {
                "destructive": False,
                "idempotent": True,
                "audience": ["user"]
            }
        }

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """
        Execute Gmail operation as a tool call.

        Called by the agent's tool execution loop when AI invokes the tool.

        Args:
            arguments: Parsed arguments from LLM tool call
                - action: 'list', 'search', or 'read' (required)
                - query: Search query string (for search action)
                - sender: Filter by sender email/name
                - subject: Filter by subject
                - max_results: Max emails to return (default: 10)
            message: Original inbound message (for context)
            config: Skill configuration

        Returns:
            SkillResult with email data
        """
        action = arguments.get("action")
        query = arguments.get("query", "")
        sender = arguments.get("sender")
        subject_filter = arguments.get("subject")
        max_results = arguments.get("max_results", config.get("default_max_results", 10))

        if not action:
            return SkillResult(
                success=False,
                output="Action is required. Use 'list', 'search', or 'read'.",
                metadata={"error": "missing_action"}
            )

        if action not in ["list", "search", "read"]:
            return SkillResult(
                success=False,
                output=f"Invalid action '{action}'. Use 'list', 'search', or 'read'.",
                metadata={"error": "invalid_action"}
            )

        try:
            logger.info(f"GmailSkill.execute_tool: action={action}, query={query}, sender={sender}")

            # Get Gmail service (validates integration)
            gmail_service = self._get_gmail_service(config)

            # Build query from filters
            query_parts = []
            if query:
                query_parts.append(query)
            if sender:
                query_parts.append(f"from:{sender}")
            if subject_filter:
                query_parts.append(f'subject:"{subject_filter}"')

            full_query = " ".join(query_parts) if query_parts else None

            if action == "list":
                return await self._execute_list(gmail_service, full_query, max_results)
            elif action == "search":
                if not full_query:
                    return SkillResult(
                        success=False,
                        output="Search requires a query, sender, or subject filter.",
                        metadata={"error": "missing_search_criteria"}
                    )
                return await self._execute_search(gmail_service, full_query, max_results)
            elif action == "read":
                return await self._execute_read(gmail_service, full_query)

        except ValueError as e:
            logger.error(f"GmailSkill.execute_tool: Configuration error: {e}")
            return SkillResult(
                success=False,
                output=f"Gmail not configured: {str(e)}",
                metadata={"error": "not_configured"}
            )
        except Exception as e:
            logger.error(f"GmailSkill.execute_tool error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Error accessing Gmail: {str(e)}",
                metadata={"error": str(e)}
            )

    async def _execute_list(self, gmail_service, query: Optional[str], max_results: int) -> SkillResult:
        """Execute list emails operation for tool mode."""
        if query:
            messages = await gmail_service.search_messages(query, max_results=max_results)
        else:
            messages = await gmail_service.list_messages(max_results=max_results)

        if not messages:
            return SkillResult(
                success=True,
                output="No emails found in inbox.",
                metadata={"count": 0}
            )

        # Get details for each message
        email_summaries = []
        for msg in messages[:max_results]:
            try:
                content = await gmail_service.get_message_content(msg['id'])
                email_summaries.append({
                    'id': msg['id'],
                    'from': content['from'],
                    'subject': content['subject'],
                    'date': content['date'],
                    'snippet': content['snippet'][:100] if content.get('snippet') else ''
                })
            except Exception as e:
                logger.warning(f"Error getting message {msg['id']}: {e}")

        # Format output
        lines = [f"📧 {len(email_summaries)} emails:\n"]
        for i, email in enumerate(email_summaries, 1):
            from_addr = email['from'].split('<')[0].strip() if '<' in email['from'] else email['from']
            lines.append(f"{i}. **{email['subject'][:50]}**")
            lines.append(f"   From: {from_addr}")
            lines.append(f"   {email['snippet'][:80]}...")
            lines.append("")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            metadata={"count": len(email_summaries), "emails": email_summaries}
        )

    async def _execute_search(self, gmail_service, query: str, max_results: int) -> SkillResult:
        """Execute search emails operation for tool mode."""
        messages = await gmail_service.search_messages(query, max_results=max_results)

        if not messages:
            return SkillResult(
                success=True,
                output=f"No emails found for: {query}",
                metadata={"count": 0, "query": query}
            )

        # Get details
        email_summaries = []
        for msg in messages[:max_results]:
            try:
                content = await gmail_service.get_message_content(msg['id'])
                email_summaries.append({
                    'id': msg['id'],
                    'from': content['from'],
                    'subject': content['subject'],
                    'date': content['date'],
                    'snippet': content['snippet'][:100] if content.get('snippet') else ''
                })
            except Exception as e:
                logger.warning(f"Error getting message {msg['id']}: {e}")

        # Format output
        lines = [f"📧 {len(email_summaries)} emails found:\n"]
        for i, email in enumerate(email_summaries, 1):
            from_addr = email['from'].split('<')[0].strip() if '<' in email['from'] else email['from']
            lines.append(f"{i}. **{email['subject'][:50]}**")
            lines.append(f"   From: {from_addr}")
            lines.append(f"   {email['snippet'][:80]}...")
            lines.append("")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            metadata={"count": len(email_summaries), "query": query, "emails": email_summaries}
        )

    async def _execute_read(self, gmail_service, query: Optional[str]) -> SkillResult:
        """Execute read email operation for tool mode."""
        if query:
            messages = await gmail_service.search_messages(query, max_results=1)
        else:
            messages = await gmail_service.list_messages(max_results=1)

        if not messages:
            return SkillResult(
                success=True,
                output="No email found to read.",
                metadata={}
            )

        content = await gmail_service.get_message_content(messages[0]['id'])

        # Format email content
        from_addr = content['from']
        subject = content['subject']
        date = content['date']
        body = content['body_text'] or content['snippet']

        # Truncate body if too long
        if len(body) > 1000:
            body = body[:1000] + "..."

        output = f"""📧 **{subject}**

**From:** {from_addr}
**Date:** {date}

---

{body}
"""

        return SkillResult(
            success=True,
            output=output,
            metadata={"email": content}
        )

    @classmethod
    def get_sentinel_context(cls) -> Dict[str, Any]:
        """
        Get security context for Sentinel analysis.

        Phase 20: Skill-aware Sentinel security system.
        Provides context about expected Gmail operations
        so legitimate commands aren't blocked.

        Returns:
            Sentinel context dict with expected intents and patterns
        """
        return {
            "expected_intents": [
                "Read emails from inbox",
                "Search for specific emails",
                "List recent messages",
                "Check email from specific sender"
            ],
            "expected_patterns": [
                "email", "inbox", "mail", "messages",
                "list", "search", "read", "check",
                "from:", "subject:", "gmail"
            ],
            "risk_notes": "Read-only access. Monitor for mass data exfiltration patterns.",
            "risk_level": "low",
            "deviation_signatures": {
                "data_exfiltration": {
                    "volume_threshold": {"calls_per_hour": 50, "unique_queries": 20},
                    "description": "Unusual volume of email queries may indicate data harvesting"
                }
            }
        }

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "execution_mode": "hybrid",
            "enabled": True,
            "keywords": cls.EMAIL_KEYWORDS,
            "use_ai_fallback": True,
            "ai_model": "gemini-2.5-flash",
            "integration_id": None,  # Must be configured per-agent
            "default_max_results": 10,
            "capabilities": {
                "list_emails": {
                    "enabled": True,
                    "label": "List Emails",
                    "description": "View recent messages in inbox"
                },
                "search_emails": {
                    "enabled": True,
                    "label": "Search Emails",
                    "description": "Search with Gmail query syntax"
                },
                "read_email": {
                    "enabled": True,
                    "label": "Read Email",
                    "description": "Get full email content"
                }
            }
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for configuration UI."""
        base_schema = super().get_config_schema()

        base_schema["properties"]["execution_mode"] = {
            "type": "string",
            "enum": ["tool", "legacy", "hybrid"],
            "title": "Execution Mode",
            "description": "Execution mode: tool (LLM decides), legacy (keywords), hybrid (both)",
            "default": "hybrid"
        }

        base_schema["properties"]["integration_id"] = {
            "type": ["integer", "null"],
            "title": "Gmail Account",
            "description": "Select which Gmail account to use for this agent",
            "default": None
        }

        base_schema["properties"]["default_max_results"] = {
            "type": "integer",
            "title": "Default Max Results",
            "description": "Maximum emails to return in list/search",
            "default": 10,
            "minimum": 1,
            "maximum": 50
        }

        base_schema["properties"]["capabilities"] = {
            "type": "object",
            "title": "Capabilities",
            "properties": {
                "list_emails": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean", "default": True}
                    }
                },
                "search_emails": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean", "default": True}
                    }
                },
                "read_email": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean", "default": True}
                    }
                }
            }
        }

        return base_schema
