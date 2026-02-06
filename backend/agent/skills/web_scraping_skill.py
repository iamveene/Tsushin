"""
Web Scraping Skill - Extract content from web pages

Allows agents to scrape and extract information from web pages.
Migrated from API Tools to Skills system for better configuration management.
"""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from .base import BaseSkill, InboundMessage, SkillResult


logger = logging.getLogger(__name__)


class WebScrapingSkill(BaseSkill):
    """
    Web scraping skill for extracting content from web pages.

    Provides safe, rate-limited web scraping with robots.txt compliance.
    No API key required - uses standard HTTP requests.

    Skills-as-Tools (Phase 2):
    - Tool name: scrape_webpage
    - Execution mode: hybrid (supports both tool and legacy keyword modes)
    """

    skill_type = "web_scraping"
    skill_name = "Web Scraping"
    skill_description = "Extract content from web pages"
    execution_mode = "hybrid"  # Support both tool and legacy modes

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize web scraping skill.

        Args:
            db: Database session (not required for scraping but kept for consistency)
        """
        super().__init__()
        self._db = db

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Detect if message contains web scraping intent.

        Looks for scraping-related keywords and URLs.

        Args:
            message: Inbound message

        Returns:
            True if message is about web scraping
        """
        # Skills-as-Tools: If in tool-only mode, don't handle via keywords
        config = getattr(self, '_config', {}) or self.get_default_config()
        if not self.is_legacy_enabled(config):
            return False

        text = message.body.lower()
        keywords = config.get('keywords', self.get_default_config()['keywords'])
        use_ai_fallback = config.get('use_ai_fallback', True)

        # Quick check: must contain a URL
        import re
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        has_url = bool(re.search(url_pattern, message.body))

        if not has_url:
            # No URL, check if there's scraping intent without URL
            logger.debug(f"WebScrapingSkill: No URL found in message")
            return False

        # Step 1: Keyword pre-filter
        has_keywords = self._keyword_matches(message.body, keywords)

        if not has_keywords:
            # URL present but no scraping keywords - might still be relevant
            # Be conservative and let AI decide
            if use_ai_fallback:
                result = await self._ai_classify(message.body, config)
                logger.info(f"WebScrapingSkill: AI classification (URL present, no keywords): {result}")
                return result
            return False

        logger.info(f"WebScrapingSkill: Keywords matched in '{text[:50]}...'")

        # Step 2: AI fallback (optional, for intent verification)
        if use_ai_fallback:
            result = await self._ai_classify(message.body, config)
            logger.info(f"WebScrapingSkill: AI classification result={result}")
            return result

        return True

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process web scraping request.

        Steps:
        1. Extract URL from message
        2. Scrape the web page
        3. Format and return content

        Args:
            message: Inbound message with URL to scrape
            config: Skill configuration

        Returns:
            SkillResult with scraped content
        """
        try:
            logger.info(f"WebScrapingSkill: Processing message: {message.body}")

            # Initialize scraper tool
            from agent.tools.scraper_tool import ScraperTool
            scraper = ScraperTool()

            # Extract URL from message
            url = self._extract_url(message.body)

            if not url:
                return SkillResult(
                    success=False,
                    output="❌ Could not find a valid URL in your message. Please include a complete URL (e.g., https://example.com).",
                    metadata={'error': 'url_extraction_failed'}
                )

            # Validate URL format
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return SkillResult(
                    success=False,
                    output=f"❌ Invalid URL format: {url}. Please provide a complete URL starting with http:// or https://",
                    metadata={'error': 'invalid_url'}
                )

            # Scrape the page
            scrape_result = scraper.fetch_url(url)

            if 'error' in scrape_result:
                return SkillResult(
                    success=False,
                    output=f"❌ Failed to scrape {url}: {scrape_result['error']}",
                    metadata={'error': scrape_result['error'], 'url': url}
                )

            # Determine output format based on config
            output_format = config.get('output_format', 'summary')

            if output_format == 'full':
                formatted_output = scraper.format_scrape_result(scrape_result)
            elif output_format == 'structured':
                # Get structured data too
                from agent.tools.scraper_tool import ScraperTool
                structured = scraper.extract_structured_data(scrape_result.get('text', ''))
                formatted_output = self._format_structured_output(scrape_result, structured)
            else:  # summary (default)
                formatted_output = self._format_summary(scrape_result)

            return SkillResult(
                success=True,
                output=formatted_output,
                metadata={
                    'url': url,
                    'title': scrape_result.get('title', ''),
                    'text_length': scrape_result.get('text_length', 0),
                    'status_code': scrape_result.get('status_code')
                }
            )

        except Exception as e:
            logger.error(f"WebScrapingSkill error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Error scraping web page: {str(e)}",
                metadata={'error': str(e)}
            )

    def _extract_url(self, message: str) -> Optional[str]:
        """
        Extract URL from message.

        Args:
            message: Message text

        Returns:
            URL string or None
        """
        import re

        # Match URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        match = re.search(url_pattern, message)

        if match:
            url = match.group(0)
            # Clean up trailing punctuation that might be part of the sentence
            url = url.rstrip('.,;:!?)')
            return url

        return None

    def _format_summary(self, scrape_result: Dict) -> str:
        """
        Format scraping result as a summary.

        Args:
            scrape_result: Result from scraper

        Returns:
            Formatted summary string
        """
        title = scrape_result.get('title', 'Untitled')
        description = scrape_result.get('description', '')
        text = scrape_result.get('text', '')[:1500]  # Limit preview
        url = scrape_result.get('url', '')

        output = f"""🌐 **{title}**

📍 URL: {url}

"""

        if description:
            output += f"📝 *{description}*\n\n"

        output += f"""📄 **Content Preview:**
{text}

{"..." if len(scrape_result.get('text', '')) > 1500 else ""}
📊 Total length: {scrape_result.get('text_length', 0)} characters"""

        return output

    def _format_structured_output(self, scrape_result: Dict, structured: Dict) -> str:
        """
        Format scraping result with structured data.

        Args:
            scrape_result: Main result from scraper
            structured: Structured data (headings, links, images)

        Returns:
            Formatted string with structured data
        """
        title = scrape_result.get('title', 'Untitled')
        url = scrape_result.get('url', '')

        output = f"""🌐 **{title}**
📍 URL: {url}

"""

        # Headings
        headings = structured.get('headings', [])
        if headings:
            output += "📋 **Headings:**\n"
            for h in headings[:10]:
                prefix = "  " * (h['level'] - 1)
                output += f"{prefix}• {h['text']}\n"
            output += "\n"

        # Links
        links = structured.get('links', [])
        if links:
            output += f"🔗 **Links:** ({len(links)} total)\n"
            for link in links[:5]:
                text = link['text'][:50] if link['text'] else link['href'][:50]
                output += f"  • {text}\n"
            if len(links) > 5:
                output += f"  ... and {len(links) - 5} more\n"
            output += "\n"

        # Content preview
        text = scrape_result.get('text', '')[:800]
        output += f"""📄 **Content Preview:**
{text}
{"..." if len(scrape_result.get('text', '')) > 800 else ""}"""

        return output

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Get default configuration for web scraping skill.

        Returns:
            Default config dict
        """
        return {
            "keywords": [
                # English
                "scrape", "extract", "fetch", "read page", "get content",
                "what does this page say", "summarize this page", "read this url",
                # Portuguese
                "extrair", "ler página", "buscar conteúdo", "resumir página",
                "o que diz essa página", "conteúdo da página"
            ],
            "use_ai_fallback": True,
            "ai_model": "gemini-2.5-flash",
            "output_format": "summary"  # 'summary', 'full', 'structured'
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
                    "description": "Keywords that trigger web scraping"
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
                "output_format": {
                    "type": "string",
                    "enum": ["summary", "full", "structured"],
                    "description": "Output format: summary (default), full, or structured (with headings/links)",
                    "default": "summary"
                },
                "execution_mode": {
                    "type": "string",
                    "enum": ["tool", "legacy", "hybrid"],
                    "description": "Execution mode: tool (AI decides), legacy (keywords only), hybrid (both)",
                    "default": "hybrid"
                }
            }
        }

    # =========================================================================
    # SKILLS-AS-TOOLS: MCP TOOL DEFINITION (Phase 2)
    # =========================================================================

    @classmethod
    def get_mcp_tool_definition(cls) -> Dict[str, Any]:
        """
        Return MCP-compliant tool definition for web scraping.

        MCP Spec: https://modelcontextprotocol.io/docs/concepts/tools
        """
        return {
            "name": "scrape_webpage",
            "title": "Web Page Scraper",
            "description": (
                "Extract content from a web page. Use when user provides a URL and wants to "
                "read, extract, or summarize information from that webpage."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to scrape (must start with http:// or https://)"
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["summary", "full", "structured"],
                        "description": "Output format: 'summary' (default, truncated preview), 'full' (complete text), or 'structured' (with headings/links)",
                        "default": "summary"
                    }
                },
                "required": ["url"]
            },
            "annotations": {
                "destructive": False,
                "idempotent": True,
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
        Execute web scraping as a tool call.

        Called by the agent's tool execution loop when AI invokes the tool.

        Args:
            arguments: Parsed arguments from LLM tool call
                - url: The URL to scrape (required)
                - output_format: 'summary', 'full', or 'structured' (optional)
            message: Original inbound message (for context)
            config: Skill configuration

        Returns:
            SkillResult with scraped content
        """
        url = arguments.get("url")
        output_format = arguments.get("output_format", config.get("output_format", "summary"))

        if not url:
            return SkillResult(
                success=False,
                output="URL is required",
                metadata={"error": "missing_url"}
            )

        try:
            logger.info(f"WebScrapingSkill.execute_tool: url='{url}', format={output_format}")

            # Validate URL format
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return SkillResult(
                    success=False,
                    output=f"Invalid URL format: {url}. URL must start with http:// or https://",
                    metadata={"error": "invalid_url"}
                )

            # Initialize scraper tool
            from agent.tools.scraper_tool import ScraperTool
            scraper = ScraperTool()

            # Scrape the page
            scrape_result = scraper.fetch_url(url)

            if "error" in scrape_result:
                return SkillResult(
                    success=False,
                    output=f"Failed to scrape {url}: {scrape_result['error']}",
                    metadata={"error": scrape_result["error"], "url": url}
                )

            # Format output based on format parameter
            if output_format == "full":
                formatted_output = scraper.format_scrape_result(scrape_result)
            elif output_format == "structured":
                structured = scraper.extract_structured_data(scrape_result.get("text", ""))
                formatted_output = self._format_structured_output(scrape_result, structured)
            else:  # summary (default)
                formatted_output = self._format_summary(scrape_result)

            return SkillResult(
                success=True,
                output=formatted_output,
                metadata={
                    "url": url,
                    "title": scrape_result.get("title", ""),
                    "text_length": scrape_result.get("text_length", 0),
                    "status_code": scrape_result.get("status_code"),
                    "output_format": output_format
                }
            )

        except Exception as e:
            logger.error(f"WebScrapingSkill.execute_tool error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Error scraping web page: {str(e)}",
                metadata={"error": str(e)}
            )

    @classmethod
    def get_sentinel_context(cls) -> Dict[str, Any]:
        """
        Get security context for Sentinel analysis.

        Phase 20: Skill-aware Sentinel security system.
        Provides context about expected web scraping behaviors
        so legitimate commands aren't blocked.

        Returns:
            Sentinel context dict with expected intents and patterns
        """
        return {
            "expected_intents": [
                "Scrape content from web pages",
                "Extract data from URLs",
                "Fetch website content",
                "Read articles from the web",
                "Get information from websites"
            ],
            "expected_patterns": [
                "scrape", "extract", "fetch", "get content", "read page",
                "http://", "https://", "website", "page", "url",
                "article", "content", "text", "information"
            ],
            "risk_notes": (
                "URL scraping is expected for this skill. "
                "Still flag: credential pages, login forms, internal/private URLs, "
                "mass data harvesting attempts, or requests to scrape sensitive data."
            )
        }
