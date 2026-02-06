"""
Browser Automation Skill - AI-powered web browser control

Phase 14.5: Browser Automation Skill

Allows agents to control web browsers via natural language commands.
Supports both container mode (isolated) and host mode (authenticated sessions).

Actions supported:
- Navigate to URLs
- Click elements
- Fill forms
- Extract text content
- Take screenshots
- Execute JavaScript
"""

import logging
import json
import re
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .base import BaseSkill, InboundMessage, SkillResult
from hub.providers.browser_automation_registry import BrowserAutomationRegistry
from hub.providers.browser_automation_provider import (
    BrowserConfig,
    BrowserResult,
    BrowserAutomationError,
    SecurityError
)


logger = logging.getLogger(__name__)


class BrowserAutomationSkill(BaseSkill):
    """
    Browser Automation skill for AI-powered web interaction.

    Parses natural language commands into browser actions and executes them
    via the configured provider (Playwright for container mode, MCP Browser for host mode).

    Features:
    - Natural language to action parsing
    - Multi-step command execution
    - Screenshot capture with auto-upload capability
    - Host mode authorization (whitelist-based)
    - Token tracking for cost monitoring

    Skills-as-Tools (Phase 4):
    - Multiple atomic tools: browser_navigate, browser_click, browser_fill, browser_screenshot, browser_extract
    - Execution mode: hybrid (supports both tool and legacy keyword modes)
    - Mode parameter: 'container' (isolated) or 'host' (authenticated sessions)
    """

    skill_type = "browser_automation"
    skill_name = "Browser Automation"
    skill_description = "Control web browsers, navigate websites, click elements, fill forms, extract content, and capture screenshots"
    execution_mode = "hybrid"  # Support both tool and legacy modes

    def __init__(self, db: Optional[Session] = None, token_tracker=None):
        """
        Initialize browser automation skill.

        Args:
            db: Database session for configuration loading
            token_tracker: Optional token tracker for AI usage monitoring
        """
        super().__init__()
        self._db = db
        self.token_tracker = token_tracker

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Detect if message contains browser automation intent.

        Uses keyword pre-filter followed by AI classification.

        Args:
            message: Inbound message

        Returns:
            True if message requests browser automation
        """
        # Skip if message has media (audio, image, etc.)
        if message.media_type:
            return False

        text = message.body.lower()

        # Get configuration
        config = getattr(self, '_config', {}) or self.get_default_config()
        keywords = config.get('keywords', self.get_default_config()['keywords'])
        use_ai_fallback = config.get('use_ai_fallback', True)

        # Step 1: Keyword pre-filter
        has_keywords = self._keyword_matches(message.body, keywords)

        if not has_keywords:
            logger.debug(f"BrowserAutomationSkill: No keyword match in '{text[:50]}...'")
            return False

        logger.info(f"BrowserAutomationSkill: Keywords matched in '{text[:50]}...'")

        # Step 2: AI fallback (for intent verification)
        if use_ai_fallback:
            result = await self._ai_classify_browser(message.body, config)
            logger.info(f"BrowserAutomationSkill: AI classification result={result}")
            return result

        return True

    async def _ai_classify_browser(self, message: str, config: Dict[str, Any]) -> bool:
        """
        Browser automation specific AI classification with custom examples.

        Provides explicit YES/NO examples for browser automation commands,
        including URLs without scheme (example.com) and with scheme (https://example.com).
        """
        from agent.skills.ai_classifier import get_classifier

        classifier = get_classifier()

        # Browser automation specific examples
        custom_examples = {
            'yes': [
                "take a screenshot of example.com",
                "screenshot google.com",
                "navigate to https://example.com",
                "go to example.com",
                "open google.com and take a screenshot",
                "browse to facebook.com",
                "capture the page example.com",
                "extract text from example.com",
                "click on the login button on example.com",
                "captura de tela do site google.com",
                "navegar para example.com",
                "abrir o site facebook.com",
            ],
            'no': [
                "what is example.com about?",
                "tell me about google",
                "who owns facebook?",
                "is example.com a real website?",
                "what's the weather today?",
                "send a message to John",
                "translate this text",
                "how are you?",
            ]
        }

        ai_model = config.get("ai_model") if config.get("ai_model") else None

        return await classifier.classify_intent(
            message=message,
            skill_name=self.skill_name,
            skill_description=self.skill_description,
            model=ai_model,
            custom_examples=custom_examples,
            db=self._db_session
        )

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process browser automation request.

        Steps:
        1. Check host mode authorization (if applicable)
        2. Parse natural language into actions
        3. Execute actions via provider
        4. Format and return results

        Args:
            message: Inbound message with browser command
            config: Skill configuration

        Returns:
            SkillResult with execution results
        """
        try:
            logger.info(f"BrowserAutomationSkill: Processing message: {message.body[:100]}...")

            # Get mode and provider settings
            mode = config.get('mode', 'container')
            provider_type = config.get('provider_type', 'playwright')

            # TODO: Re-enable when host mode is implemented
            # Host mode authorization check
            # if mode == 'host':
            #     allowed_users = config.get('allowed_user_keys', [])
            #     if allowed_users and message.sender_key not in allowed_users:
            #         logger.warning(
            #             f"BrowserAutomationSkill: Unauthorized host mode access attempt "
            #             f"by {message.sender_key}"
            #         )
            #         return SkillResult(
            #             success=False,
            #             output="You don't have permission to use host browser mode. "
            #                    "Contact the admin to be added to the whitelist.",
            #             metadata={'error': 'unauthorized', 'mode': 'host'}
            #         )
            #     logger.info(f"BrowserAutomationSkill: Host mode access granted to {message.sender_key}")

            # Parse natural language into actions
            actions = await self._parse_intent(message.body, config)

            if not actions:
                return SkillResult(
                    success=False,
                    output="Could not understand the browser command. "
                           "Try: 'navigate to example.com', 'take a screenshot', or 'extract text from google.com'",
                    metadata={'error': 'parse_failed'}
                )

            logger.info(f"BrowserAutomationSkill: Parsed {len(actions)} action(s): {[a['action'] for a in actions]}")

            # Get provider
            provider = BrowserAutomationRegistry.get_provider(
                provider_name=provider_type,
                db=self._db
            )

            if not provider:
                return SkillResult(
                    success=False,
                    output=f"Browser automation provider '{provider_type}' is not available. "
                           "The system administrator needs to configure it.",
                    metadata={'error': 'provider_unavailable', 'provider': provider_type}
                )

            # Execute actions
            results = []
            screenshot_paths = []
            auto_extracted = False

            try:
                await provider.initialize()
                logger.info("BrowserAutomationSkill: Provider initialized")

                for action_def in actions:
                    try:
                        result = await self._execute_action(provider, action_def)
                        results.append(result)

                        # Track screenshot paths for media upload
                        if result.action == 'screenshot' and result.success:
                            path = result.data.get('path')
                            if path:
                                screenshot_paths.append(path)

                    except SecurityError as e:
                        logger.warning(f"BrowserAutomationSkill: Security error: {e}")
                        results.append(BrowserResult(
                            success=False,
                            action=action_def['action'],
                            data={},
                            error=f"Blocked for security: {str(e)}"
                        ))
                        break  # Stop on security errors

                    except Exception as e:
                        logger.error(f"BrowserAutomationSkill: Action error: {e}")
                        results.append(BrowserResult(
                            success=False,
                            action=action_def['action'],
                            data={},
                            error=str(e)
                        ))
                        # Continue with other actions unless configured to stop

                # Auto-extract page content after navigate-only commands
                if (len(actions) == 1
                        and actions[0].get('action') == 'navigate'
                        and results and results[0].success):
                    try:
                        extract_result = await self._execute_action(
                            provider, {'action': 'extract', 'params': {'selector': 'body'}}
                        )
                        if extract_result.success:
                            results.append(extract_result)
                            auto_extracted = True
                    except Exception as e:
                        logger.warning(f"Auto-extract after navigate failed: {e}")

            finally:
                await provider.cleanup()
                logger.info("BrowserAutomationSkill: Provider cleaned up")

            # Format output
            output = self._format_results(results)
            success = all(r.success for r in results)

            metadata = {
                'provider': provider_type,
                'mode': mode,
                'actions_executed': len(results),
                'actions_succeeded': sum(1 for r in results if r.success),
                'screenshot_paths': screenshot_paths,
                'skip_ai': not auto_extracted  # Let AI summarize when page content was extracted
            }

            return SkillResult(
                success=success,
                output=output,
                metadata=metadata,
                media_paths=screenshot_paths if screenshot_paths else None
            )

        except Exception as e:
            logger.error(f"BrowserAutomationSkill error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Browser automation failed: {str(e)}",
                metadata={'error': str(e)}
            )

    async def _parse_intent(self, text: str, config: Dict[str, Any]) -> Optional[List[Dict]]:
        """
        Parse natural language into browser actions using AI.

        Args:
            text: Natural language command
            config: Skill configuration

        Returns:
            List of action dictionaries or None if parsing fails
        """
        try:
            from agent.ai_client import AIClient

            # Create AI client for parsing
            ai_client = AIClient(
                provider=config.get('model_provider', 'gemini'),
                model_name=config.get('model_name', 'gemini-2.5-flash'),
                db=self._db
            )

            system_prompt = """You are a browser automation command parser. Convert natural language into structured browser actions.

Available actions:
1. navigate - Go to a URL
   params: {"url": "full URL with https://", "wait_until": "load"|"domcontentloaded"|"networkidle"}

2. click - Click an element
   params: {"selector": "CSS selector"}

3. fill - Fill a form field
   params: {"selector": "CSS selector", "value": "text to enter"}

4. extract - Extract text content
   params: {"selector": "CSS selector (optional, default: body)"}

5. screenshot - Capture the page
   params: {"full_page": true|false, "selector": "optional CSS selector"}

6. execute_script - Run JavaScript
   params: {"script": "JavaScript code"}

Return ONLY a JSON array of actions, no other text."""

            user_prompt = f"""Parse this browser command into actions:

"{text}"

Examples:
- "go to google.com" → [{{"action": "navigate", "params": {{"url": "https://google.com"}}}}]
- "take a screenshot of example.com" → [{{"action": "navigate", "params": {{"url": "https://example.com"}}}}, {{"action": "screenshot", "params": {{"full_page": true}}}}]
- "search for 'test' on google" → [{{"action": "navigate", "params": {{"url": "https://google.com"}}}}, {{"action": "fill", "params": {{"selector": "input[name='q']", "value": "test"}}}}, {{"action": "click", "params": {{"selector": "input[type='submit']"}}}}]
- "extract the title from example.com" → [{{"action": "navigate", "params": {{"url": "https://example.com"}}}}, {{"action": "extract", "params": {{"selector": "h1"}}}}]

Return JSON array only:"""

            response = await ai_client.generate(system_prompt, user_prompt)

            # Track token usage
            if self.token_tracker and response.get('usage'):
                usage = response['usage']
                self.token_tracker.track_usage(
                    operation_type="browser_automation_parse",
                    model_provider=config.get('model_provider', 'gemini'),
                    model_name=config.get('model_name', 'gemini-2.5-flash'),
                    prompt_tokens=usage.get('prompt_tokens', 0),
                    completion_tokens=usage.get('completion_tokens', 0),
                    skill_type=self.skill_type
                )

            if response.get('error'):
                logger.error(f"AI parse error: {response['error']}")
                return self._simple_parse(text)

            # Extract JSON from response
            answer = response.get('answer', '')

            # Try to find JSON array in response
            json_match = re.search(r'\[[\s\S]*\]', answer)
            if json_match:
                try:
                    actions = json.loads(json_match.group())
                    if isinstance(actions, list) and len(actions) > 0:
                        # Validate and normalize URLs
                        for action in actions:
                            if action.get('action') == 'navigate':
                                url = action.get('params', {}).get('url', '')
                                if url and not url.startswith(('http://', 'https://')):
                                    action['params']['url'] = 'https://' + url
                        logger.info(f"Parsed actions: {actions}")
                        return actions
                except json.JSONDecodeError:
                    pass

            # Fallback to simple parsing
            return self._simple_parse(text)

        except Exception as e:
            logger.error(f"Intent parsing failed: {e}", exc_info=True)
            return self._simple_parse(text)

    def _simple_parse(self, text: str) -> Optional[List[Dict]]:
        """
        Simple fallback parser for common commands without AI.

        Args:
            text: Command text

        Returns:
            List of actions or None
        """
        text_lower = text.lower()
        actions = []

        # Detect URL in text
        url_pattern = r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+(?:\.[a-zA-Z]{2,})+)(?:/[^\s]*)?'
        url_match = re.search(url_pattern, text)

        # Screenshot commands
        if any(word in text_lower for word in ['screenshot', 'capture', 'captura', 'print']):
            if url_match:
                url = url_match.group()
                if not url.startswith('http'):
                    url = 'https://' + url
                actions.append({
                    'action': 'navigate',
                    'params': {'url': url}
                })
            actions.append({
                'action': 'screenshot',
                'params': {'full_page': True}
            })
            return actions if actions else None

        # Navigate commands
        if any(word in text_lower for word in ['navigate', 'go to', 'open', 'visit', 'ir para', 'abrir', 'acessar']):
            if url_match:
                url = url_match.group()
                if not url.startswith('http'):
                    url = 'https://' + url
                return [{
                    'action': 'navigate',
                    'params': {'url': url}
                }]

        # Extract commands
        if any(word in text_lower for word in ['extract', 'get text', 'extrair', 'pegar texto']):
            if url_match:
                url = url_match.group()
                if not url.startswith('http'):
                    url = 'https://' + url
                actions.append({
                    'action': 'navigate',
                    'params': {'url': url}
                })
            actions.append({
                'action': 'extract',
                'params': {'selector': 'body'}
            })
            return actions if actions else None

        return None

    async def _execute_action(self, provider, action_def: Dict) -> BrowserResult:
        """
        Execute a single browser action.

        Args:
            provider: Browser automation provider instance
            action_def: Action definition dict with 'action' and 'params'

        Returns:
            BrowserResult from the action
        """
        action_name = action_def.get('action', '')
        params = action_def.get('params', {})

        logger.info(f"Executing action: {action_name} with params: {params}")

        if action_name == 'navigate':
            return await provider.navigate(
                url=params.get('url', ''),
                wait_until=params.get('wait_until', 'load')
            )

        elif action_name == 'click':
            return await provider.click(
                selector=params.get('selector', '')
            )

        elif action_name == 'fill':
            return await provider.fill(
                selector=params.get('selector', ''),
                value=params.get('value', '')
            )

        elif action_name == 'extract':
            return await provider.extract(
                selector=params.get('selector', 'body')
            )

        elif action_name == 'screenshot':
            return await provider.screenshot(
                full_page=params.get('full_page', True),
                selector=params.get('selector')
            )

        elif action_name == 'execute_script':
            return await provider.execute_script(
                script=params.get('script', '')
            )

        else:
            return BrowserResult(
                success=False,
                action=action_name,
                data={},
                error=f"Unknown action: {action_name}"
            )

    def _format_results(self, results: List[BrowserResult]) -> str:
        """
        Format results for human-readable output.

        Args:
            results: List of BrowserResult objects

        Returns:
            Formatted string output
        """
        lines = []

        for result in results:
            if result.success:
                if result.action == 'navigate':
                    title = result.data.get('title', 'Page')
                    url = result.data.get('url', '')
                    lines.append(f"Navigated to: {title}\n{url}")

                elif result.action == 'click':
                    selector = result.data.get('selector', '')
                    lines.append(f"Clicked: {selector}")

                elif result.action == 'fill':
                    selector = result.data.get('selector', '')
                    value_len = result.data.get('value_length', 0)
                    lines.append(f"Filled {selector} ({value_len} chars)")

                elif result.action == 'extract':
                    text = result.data.get('text', '')
                    # Truncate long text
                    if len(text) > 3000:
                        text = text[:3000] + "..."
                    lines.append(f"Extracted:\n{text}")

                elif result.action == 'screenshot':
                    path = result.data.get('path', '')
                    size = result.data.get('size_bytes', 0)
                    lines.append(f"Screenshot saved ({size} bytes)")

                elif result.action == 'execute_script':
                    script_result = result.data.get('result', '')
                    lines.append(f"Script result: {script_result}")

                else:
                    lines.append(f"{result.action}: Success")

            else:
                lines.append(f"{result.action}: Failed - {result.error}")

        return "\n\n".join(lines) if lines else "No actions executed."

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Get default configuration for browser automation skill.

        Returns:
            Default config dict
        """
        return {
            "keywords": [
                # English
                "browser", "browse", "navigate", "screenshot", "webpage", "website",
                "web page", "go to",
                # Portuguese
                "navegador", "navegar", "captura de tela", "pagina", "site",
                "acessar"
            ],
            "use_ai_fallback": True,
            "ai_model": "gemini-2.5-flash",
            "provider_type": "playwright",
            "timeout_seconds": 30,
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for skill configuration.

        Returns:
            Config schema dict
        """
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords that trigger browser automation"
                },
                "use_ai_fallback": {
                    "type": "boolean",
                    "description": "Use AI to verify intent after keyword match",
                    "default": True
                },
                "ai_model": {
                    "type": "string",
                    "description": "AI model for intent classification",
                    "default": "gemini-2.5-flash"
                },
                "provider_type": {
                    "type": "string",
                    "enum": ["playwright", "mcp_browser"],
                    "description": "Browser automation provider",
                    "default": "playwright"
                },
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 5,
                    "maximum": 300,
                    "description": "Timeout for browser actions in seconds",
                    "default": 30
                },
            }
        }

    @classmethod
    def get_sentinel_context(cls) -> Dict[str, Any]:
        """
        Get security context for Sentinel analysis.

        Phase 20: Skill-aware Sentinel security system.
        Provides context about expected browser automation behaviors
        so legitimate commands aren't blocked.

        Returns:
            Sentinel context dict with expected intents and patterns
        """
        return {
            "expected_intents": [
                "Navigate to URLs and websites",
                "Take screenshots of web pages",
                "Click elements on web pages",
                "Fill forms on websites",
                "Extract text content from web pages",
                "Execute JavaScript on pages",
                "Open and browse websites"
            ],
            "expected_patterns": [
                "go to", "navigate to", "open", "visit", "browse",
                "screenshot", "capture", "take a picture",
                "click", "fill", "type", "extract", "scrape",
                "http://", "https://", ".com", ".org", ".net", ".br",
                "website", "webpage", "page", "site", "url"
            ],
            "risk_notes": (
                "URL mentions and screenshot requests are expected for browser automation. "
                "Still flag: credential harvesting pages, phishing domains, "
                "requests to extract passwords/sensitive data, or commands that "
                "try to bypass security measures."
            )
        }

    # =========================================================================
    # SKILLS-AS-TOOLS: MCP TOOL DEFINITIONS (Phase 4)
    # =========================================================================

    @classmethod
    def get_mcp_tool_definition(cls) -> Dict[str, Any]:
        """
        Return MCP-compliant tool definition for browser automation.

        Uses single tool with action parameter (similar to Gmail pattern)
        to keep tool count manageable while supporting all browser operations.

        MCP Spec: https://modelcontextprotocol.io/docs/concepts/tools
        """
        return {
            "name": "browser_control",
            "title": "Browser Control",
            "description": (
                "Control a web browser to navigate websites, take screenshots, click elements, "
                "fill forms, and extract content. Use 'container' mode for public websites, "
                "'host' mode for sites requiring your logged-in browser session (requires authorization)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["navigate", "screenshot", "click", "fill", "extract"],
                        "description": "Browser action to perform"
                    },
                    "url": {
                        "type": "string",
                        "description": "URL to navigate to (required for 'navigate' action)"
                    },
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for element targeting (for click/fill/extract/screenshot). Examples: '#login-btn', 'input[name=email]', '.submit-button'"
                    },
                    "value": {
                        "type": "string",
                        "description": "Text value to fill (required for 'fill' action)"
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture full scrollable page (true) or just viewport (false). Default: true",
                        "default": True
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["container", "host"],
                        "description": "container=isolated browser (default), host=user's authenticated browser (requires whitelist)",
                        "default": "container"
                    },
                    "wait_until": {
                        "type": "string",
                        "enum": ["load", "domcontentloaded", "networkidle"],
                        "description": "When to consider navigation complete (for navigate action)",
                        "default": "load"
                    }
                },
                "required": ["action"]
            },
            "annotations": {
                "destructive": True,  # Can modify page state
                "idempotent": False,
                "audience": ["user", "assistant"]
            }
        }

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """
        Execute browser automation as a tool call.

        Called by the agent's tool execution loop when AI invokes the tool.

        Args:
            arguments: Parsed arguments from LLM tool call
                - action: 'navigate', 'screenshot', 'click', 'fill', 'extract' (required)
                - url: URL for navigate action
                - selector: CSS selector for element targeting
                - value: Text for fill action
                - full_page: Boolean for screenshot action
                - mode: 'container' or 'host'
                - wait_until: Navigation wait condition
            message: Original inbound message (for context)
            config: Skill configuration

        Returns:
            SkillResult with browser operation result
        """
        action = arguments.get("action")

        if not action:
            return SkillResult(
                success=False,
                output="Action is required. Use 'navigate', 'screenshot', 'click', 'fill', or 'extract'.",
                metadata={"error": "missing_action", "skip_ai": True}
            )

        # Get mode from arguments or config
        mode = arguments.get("mode", config.get("mode", "container"))
        provider_type = config.get("provider_type", "playwright")

        # Host mode authorization check
        if mode == "host":
            allowed_users = config.get("allowed_user_keys", [])
            if allowed_users and message.sender_key not in allowed_users:
                logger.warning(
                    f"BrowserAutomationSkill.execute_tool: Unauthorized host mode access attempt "
                    f"by {message.sender_key}"
                )
                return SkillResult(
                    success=False,
                    output="You don't have permission to use host browser mode. "
                           "Contact the admin to be added to the whitelist.",
                    metadata={"error": "unauthorized", "mode": "host", "skip_ai": True}
                )
            logger.info(f"BrowserAutomationSkill.execute_tool: Host mode access granted to {message.sender_key}")

        logger.info(f"BrowserAutomationSkill.execute_tool: action={action}, mode={mode}, provider={provider_type}")

        try:
            # Get provider
            provider = BrowserAutomationRegistry.get_provider(
                provider_name=provider_type,
                db=self._db
            )

            if not provider:
                return SkillResult(
                    success=False,
                    output=f"Browser automation provider '{provider_type}' is not available. "
                           "The system administrator needs to configure it.",
                    metadata={"error": "provider_unavailable", "provider": provider_type, "skip_ai": True}
                )

            screenshot_paths = []

            try:
                await provider.initialize()
                logger.info("BrowserAutomationSkill.execute_tool: Provider initialized")

                # Execute the requested action
                if action == "navigate":
                    result = await self._execute_tool_navigate(provider, arguments)
                    # Auto-extract page content after successful navigation
                    if result.success:
                        try:
                            extract_result = await provider.extract("body")
                            if extract_result.success:
                                raw_text = extract_result.data.get("text", "")
                                page_content = raw_text[:3000] if raw_text else ""
                                if page_content:
                                    result = SkillResult(
                                        success=True,
                                        output=f"{result.output}\n\nPage content:\n{page_content}",
                                        metadata={**(result.metadata or {}), "skip_ai": False}
                                    )
                        except Exception as e:
                            logger.warning(f"Auto-extract after navigate failed: {e}")
                elif action == "screenshot":
                    result = await self._execute_tool_screenshot(provider, arguments)
                    if result.success and result.media_paths:
                        screenshot_paths = result.media_paths
                elif action == "click":
                    result = await self._execute_tool_click(provider, arguments)
                elif action == "fill":
                    result = await self._execute_tool_fill(provider, arguments)
                elif action == "extract":
                    result = await self._execute_tool_extract(provider, arguments)
                else:
                    result = SkillResult(
                        success=False,
                        output=f"Unknown action: {action}. Use 'navigate', 'screenshot', 'click', 'fill', or 'extract'.",
                        metadata={"error": "invalid_action", "skip_ai": True}
                    )

            finally:
                await provider.cleanup()
                logger.info("BrowserAutomationSkill.execute_tool: Provider cleaned up")

            # Add common metadata
            if result.metadata:
                result.metadata["provider"] = provider_type
                result.metadata["mode"] = mode
                result.metadata["action"] = action
            else:
                result.metadata = {
                    "provider": provider_type,
                    "mode": mode,
                    "action": action,
                    "skip_ai": True
                }

            return result

        except SecurityError as e:
            logger.warning(f"BrowserAutomationSkill.execute_tool: Security error: {e}")
            return SkillResult(
                success=False,
                output=f"Blocked for security: {str(e)}",
                metadata={"error": "security_blocked", "skip_ai": True}
            )

        except Exception as e:
            logger.error(f"BrowserAutomationSkill.execute_tool error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Browser automation failed: {str(e)}",
                metadata={"error": str(e), "skip_ai": True}
            )

    async def _execute_tool_navigate(self, provider, arguments: Dict[str, Any]) -> SkillResult:
        """Execute navigate action for tool mode."""
        url = arguments.get("url")
        if not url:
            return SkillResult(
                success=False,
                output="URL is required for navigate action.",
                metadata={"error": "missing_url", "skip_ai": True}
            )

        # Normalize URL
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        wait_until = arguments.get("wait_until", "load")

        result = await provider.navigate(url=url, wait_until=wait_until)

        if result.success:
            title = result.data.get("title", "Page")
            final_url = result.data.get("url", url)
            return SkillResult(
                success=True,
                output=f"Navigated to: {title}\n{final_url}",
                metadata={"url": final_url, "title": title, "skip_ai": True}
            )
        else:
            return SkillResult(
                success=False,
                output=f"Failed to navigate: {result.error}",
                metadata={"error": result.error, "skip_ai": True}
            )

    async def _execute_tool_screenshot(self, provider, arguments: Dict[str, Any]) -> SkillResult:
        """Execute screenshot action for tool mode."""
        full_page = arguments.get("full_page", True)
        selector = arguments.get("selector")

        result = await provider.screenshot(full_page=full_page, selector=selector)

        if result.success:
            path = result.data.get("path", "")
            size = result.data.get("size_bytes", 0)
            return SkillResult(
                success=True,
                output=f"Screenshot captured ({size} bytes)",
                metadata={"screenshot_path": path, "size_bytes": size, "skip_ai": True},
                media_paths=[path] if path else None
            )
        else:
            return SkillResult(
                success=False,
                output=f"Failed to capture screenshot: {result.error}",
                metadata={"error": result.error, "skip_ai": True}
            )

    async def _execute_tool_click(self, provider, arguments: Dict[str, Any]) -> SkillResult:
        """Execute click action for tool mode."""
        selector = arguments.get("selector")
        if not selector:
            return SkillResult(
                success=False,
                output="Selector is required for click action. Example: '#login-btn' or 'button.submit'",
                metadata={"error": "missing_selector", "skip_ai": True}
            )

        result = await provider.click(selector=selector)

        if result.success:
            return SkillResult(
                success=True,
                output=f"Clicked element: {selector}",
                metadata={"selector": selector, "skip_ai": True}
            )
        else:
            return SkillResult(
                success=False,
                output=f"Failed to click: {result.error}",
                metadata={"error": result.error, "skip_ai": True}
            )

    async def _execute_tool_fill(self, provider, arguments: Dict[str, Any]) -> SkillResult:
        """Execute fill action for tool mode."""
        selector = arguments.get("selector")
        value = arguments.get("value")

        if not selector:
            return SkillResult(
                success=False,
                output="Selector is required for fill action. Example: 'input[name=email]'",
                metadata={"error": "missing_selector", "skip_ai": True}
            )

        if not value:
            return SkillResult(
                success=False,
                output="Value is required for fill action.",
                metadata={"error": "missing_value", "skip_ai": True}
            )

        result = await provider.fill(selector=selector, value=value)

        if result.success:
            return SkillResult(
                success=True,
                output=f"Filled {selector} with {len(value)} characters",
                metadata={"selector": selector, "value_length": len(value), "skip_ai": True}
            )
        else:
            return SkillResult(
                success=False,
                output=f"Failed to fill: {result.error}",
                metadata={"error": result.error, "skip_ai": True}
            )

    async def _execute_tool_extract(self, provider, arguments: Dict[str, Any]) -> SkillResult:
        """Execute extract action for tool mode."""
        selector = arguments.get("selector", "body")

        result = await provider.extract(selector=selector)

        if result.success:
            text = result.data.get("text", "")
            # Truncate long text
            display_text = text[:1000] + "..." if len(text) > 1000 else text
            return SkillResult(
                success=True,
                output=f"Extracted text ({len(text)} chars):\n{display_text}",
                metadata={"selector": selector, "text_length": len(text), "text": text, "skip_ai": True}
            )
        else:
            return SkillResult(
                success=False,
                output=f"Failed to extract: {result.error}",
                metadata={"error": result.error, "skip_ai": True}
            )
