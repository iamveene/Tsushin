"""
Browser Automation Skill - AI-powered web browser control

Phase 14.5: Browser Automation Skill

Allows agents to control web browsers via natural language commands.
Uses Playwright in container mode for secure, isolated browser automation.

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
import os
import re
import base64
import tempfile
import time
from typing import Dict, Any, Optional, List
import httpx
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
    via Playwright in container mode.

    Features:
    - Natural language to action parsing
    - Multi-step command execution
    - Screenshot capture with auto-upload capability
    - Token tracking for cost monitoring

    Skills-as-Tools (Phase 4):
    - Multiple atomic tools: browser_navigate, browser_click, browser_fill, browser_screenshot, browser_extract
    - Execution mode: hybrid (supports both tool and legacy keyword modes)
    - Mode parameter: 'container' (isolated) or 'host' (authenticated sessions)
    """

    skill_type = "browser_automation"
    skill_name = "Browser Automation"
    skill_description = "Control web browsers, navigate websites, click elements, fill forms, extract content, and capture screenshots"
    execution_mode = "tool"

    def _resolve_tenant_id(self) -> Optional[str]:
        """Resolve tenant_id from agent context for API key lookups."""
        agent_id = getattr(self, '_agent_id', None)
        if agent_id and self._db:
            try:
                from models import Agent
                agent = self._db.query(Agent).filter(Agent.id == agent_id).first()
                if agent:
                    return agent.tenant_id
            except Exception:
                pass
        return None

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

    @staticmethod
    def _captcha_expected_length(params: Dict[str, Any]) -> Optional[int]:
        try:
            length = int(str(params.get("captcha_length") or "").strip())
            return length if 1 <= length <= 12 else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _captcha_guess_lines(text: str, expected_length: Optional[int] = None) -> List[str]:
        """Normalize model output into ordered, plausible CAPTCHA guesses."""
        guesses: List[str] = []
        fallback: List[str] = []
        for line in str(text or "").splitlines():
            cleaned = re.sub(r"[^a-zA-Z0-9]", "", line).strip().lower()
            if expected_length:
                if len(cleaned) == expected_length:
                    guesses.append(cleaned)
                elif 4 <= len(cleaned) <= 8:
                    fallback.append(cleaned)
            elif 4 <= len(cleaned) <= 8:
                guesses.append(cleaned)
        if not guesses:
            cleaned = re.sub(r"[^a-zA-Z0-9]", "", str(text or "")).strip().lower()
            if expected_length and len(cleaned) == expected_length:
                guesses.append(cleaned)
            elif not expected_length and 4 <= len(cleaned) <= 8:
                guesses.append(cleaned)
        if not guesses and not expected_length:
            guesses.extend(fallback)
        return list(dict.fromkeys(guesses))

    async def _capture_captcha_image(self, provider, selector: str) -> tuple[Optional[str], str, Optional[BrowserResult]]:
        """Capture the rendered CAPTCHA image at natural resolution when possible."""
        try:
            capture = await provider.execute_script(
                """
                async () => {
                  const selector = arguments[0];
                  const img = document.querySelector(selector);
                  if (!img) return null;
                  if (!img.complete) {
                    await new Promise((resolve) => {
                      img.addEventListener('load', resolve, { once: true });
                      img.addEventListener('error', resolve, { once: true });
                      setTimeout(resolve, 2500);
                    });
                  }
                  const width = img.naturalWidth || img.width || Math.ceil(img.getBoundingClientRect().width);
                  const height = img.naturalHeight || img.height || Math.ceil(img.getBoundingClientRect().height);
                  if (!width || !height) return null;
                  const canvas = document.createElement('canvas');
                  canvas.width = width;
                  canvas.height = height;
                  const ctx = canvas.getContext('2d');
                  ctx.drawImage(img, 0, 0, width, height);
                  return { dataUrl: canvas.toDataURL('image/png'), width, height };
                }
                """.replace("arguments[0]", json.dumps(selector))
            )
            data = capture.data.get("result") if capture.success else None
            data_url = data.get("dataUrl") if isinstance(data, dict) else None
            if isinstance(data_url, str) and data_url.startswith("data:image/") and "," in data_url:
                header, payload = data_url.split(",", 1)
                suffix = ".jpg" if "jpeg" in header or "jpg" in header else ".png"
                screenshot_dir = os.path.join(tempfile.gettempdir(), "tsushin_screenshots")
                os.makedirs(screenshot_dir, exist_ok=True)
                filename = f"captcha_{int(time.time() * 1000)}{suffix}"
                path = os.path.join(screenshot_dir, filename)
                with open(path, "wb") as fh:
                    fh.write(base64.b64decode(payload))
                return path, "canvas", None
        except Exception as exc:
            logger.debug("CAPTCHA canvas capture failed; falling back to screenshot: %s", exc)

        screenshot = await provider.screenshot(full_page=False, selector=selector)
        if screenshot.success:
            return str(screenshot.data.get("path") or ""), "screenshot", None
        return None, "screenshot", screenshot

    @staticmethod
    def _captcha_image_variants(image_path: str, params: Dict[str, Any]) -> List[str]:
        if str(params.get("preprocess_image", "true")).lower() in {"0", "false", "no"}:
            return [image_path]
        variants = [image_path]
        try:
            from PIL import Image, ImageEnhance, ImageFilter

            img = Image.open(image_path).convert("L")
            img = ImageEnhance.Contrast(img).enhance(2.2)
            img = img.filter(ImageFilter.SHARPEN)
            img = img.resize((max(1, img.width * 3), max(1, img.height * 3)))
            base, _ = os.path.splitext(image_path)
            enhanced_path = f"{base}_enhanced.png"
            img.save(enhanced_path)
            variants.append(enhanced_path)
        except Exception as exc:
            logger.debug("CAPTCHA preprocessing skipped: %s", exc)
        return variants

    async def _captcha_guesses_from_ollama(self, image_path: str, params: Dict[str, Any]) -> List[str]:
        model = (
            params.get("ollama_model")
            or params.get("model")
            or os.getenv("TSUSHIN_CAPTCHA_OLLAMA_MODEL")
            or "gemma4:latest"
        )
        base_url = (
            params.get("ollama_base_url")
            or os.getenv("OLLAMA_BASE_URL")
            or "http://host.docker.internal:11434"
        ).rstrip("/")
        expected_length = self._captcha_expected_length(params)
        length_hint = str(expected_length or "").strip()
        length_rule = (
            f"The code is exactly {length_hint} characters."
            if length_hint.isdigit()
            else "The code is 5 or 6 characters."
        )
        prompt = str(params.get("prompt") or f"""
Read this CAPTCHA image exactly.
Rules:
- {length_rule}
- The code uses lowercase letters a-z and digits 0-9.
- Ignore crossing lines, background noise, and dots.
- Return up to 5 likely readings, one per line.
- Output only the readings, no labels and no commentary.
""").strip()

        with open(image_path, "rb") as fh:
            image_base64 = base64.b64encode(fh.read()).decode("ascii")

        payload = {
            "model": model,
            "prompt": prompt,
            "images": [image_base64],
            "stream": False,
            "options": {
                "temperature": float(params.get("temperature", 0)),
            },
        }
        timeout = float(params.get("solver_timeout_seconds") or params.get("timeout_seconds") or 60)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{base_url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
        return self._captcha_guess_lines(str(data.get("response") or ""), expected_length)

    async def _solve_image_captcha(self, provider, params: Dict[str, Any]) -> BrowserResult:
        selector = params.get("selector") or "img[src*='captcha'], img[alt*='captcha' i], img[id*='captcha' i], img[class*='captcha' i]"
        input_selector = params.get("input_selector") or (
            "input[name*='captcha' i], input[id*='captcha' i], "
            "input[placeholder*='captcha' i], input[placeholder*='imagem' i]"
        )
        submit_selector = params.get("submit_selector") or (
            "button:has-text('Consultar'), button:has-text('Pesquisar'), "
            "button[type='submit'], input[type='submit']"
        )
        success_selector = params.get("success_selector")
        error_text_regex = params.get("error_text_regex") or (
            "incorreto|n[aã]o confere|captcha inv[aá]lido|captcha invalido|inv[aá]lido"
        )
        try:
            max_attempts = max(1, min(10, int(params.get("max_attempts") or 3)))
        except (TypeError, ValueError):
            max_attempts = 3
        try:
            post_submit_wait_ms = max(250, min(15000, int(params.get("post_submit_wait_ms") or 5000)))
        except (TypeError, ValueError):
            post_submit_wait_ms = 5000

        detection = await provider.execute_script(f"() => Boolean(document.querySelector({json.dumps(selector)}))")
        if detection.success and not detection.data.get("result"):
            return BrowserResult(success=True, action="solve_captcha", data={"selector": selector, "captcha_detected": False})

        for attempt in range(1, max_attempts + 1):
            image_path, capture_method, capture_error = await self._capture_captcha_image(provider, selector)
            if not image_path:
                screenshot = capture_error or BrowserResult(
                    success=False,
                    action="screenshot",
                    error="Could not capture CAPTCHA image",
                )
                return BrowserResult(
                    success=False,
                    action="solve_captcha",
                    data={"selector": selector, "captcha_detected": True, "attempt": attempt},
                    error=screenshot.error or "Could not capture CAPTCHA image",
                    error_code=screenshot.error_code,
                    suggestions=screenshot.suggestions,
                )

            try:
                guesses: List[str] = []
                for candidate_path in self._captcha_image_variants(image_path, params):
                    guesses = await self._captcha_guesses_from_ollama(candidate_path, params)
                    if guesses:
                        break
            except Exception as exc:
                from hub.providers.browser_automation_provider import BrowserErrorCode

                return BrowserResult(
                    success=False,
                    action="solve_captcha",
                    data={"selector": selector, "captcha_detected": True, "attempt": attempt, "solver_provider": "ollama"},
                    error=f"CAPTCHA solver failed: {exc}",
                    error_code=BrowserErrorCode.UNKNOWN,
                    suggestions=["Check Ollama availability/model support or configure this step for manual execution."],
                )

            if not guesses:
                await provider.execute_script("() => new Promise(resolve => setTimeout(() => resolve(true), 1000))")
                continue

            for guess in guesses:
                fill_result = await provider.fill(input_selector, guess)
                if not fill_result.success:
                    return BrowserResult(
                        success=False,
                        action="solve_captcha",
                        data={"selector": selector, "captcha_detected": True, "attempt": attempt},
                        error=fill_result.error or "CAPTCHA input not found",
                        error_code=fill_result.error_code,
                        suggestions=fill_result.suggestions,
                    )

                click_result = await provider.click(submit_selector)
                if not click_result.success:
                    return BrowserResult(
                        success=False,
                        action="solve_captcha",
                        data={"selector": selector, "captcha_detected": True, "attempt": attempt},
                        error=click_result.error or "CAPTCHA submit control not found",
                        error_code=click_result.error_code,
                        suggestions=click_result.suggestions,
                    )

                await provider.execute_script(
                    f"() => new Promise(resolve => setTimeout(() => resolve(true), {post_submit_wait_ms}))"
                )
                state = await provider.execute_script(
                    "() => { "
                    "const isVisible = (el) => { "
                    "  if (!el) return false; "
                    "  const style = window.getComputedStyle(el); "
                    "  const rect = el.getBoundingClientRect(); "
                    "  return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0; "
                    "}; "
                    "const firstVisible = (sel) => { "
                    "  if (!sel) return false; "
                    "  try { return Array.from(document.querySelectorAll(sel)).some(isVisible); } catch (_) { return false; } "
                    "}; "
                    f"const captchaVisible = firstVisible({json.dumps(selector)}); "
                    f"const successVisible = firstVisible({json.dumps(success_selector or '')}); "
                    "const text = (document.body && document.body.innerText || '').toLowerCase(); "
                    f"const errorRe = new RegExp({json.dumps(error_text_regex)}, 'i'); "
                    "return { captchaVisible, successVisible, error: errorRe.test(text), url: location.href }; "
                    "}"
                )
                state_data = state.data.get("result") if state.success else {}
                if not isinstance(state_data, dict):
                    state_data = {}
                if state_data.get("successVisible") or not state_data.get("captchaVisible"):
                    return BrowserResult(
                        success=True,
                        action="solve_captcha",
                        data={
                            "selector": selector,
                            "captcha_detected": True,
                            "attempt": attempt,
                            "guesses_tried": guesses.index(guess) + 1,
                            "solver_provider": "ollama",
                            "model": params.get("ollama_model") or params.get("model") or os.getenv("TSUSHIN_CAPTCHA_OLLAMA_MODEL") or "gemma4:latest",
                            "capture_method": capture_method,
                            "url": state_data.get("url"),
                            "success_selector_visible": bool(state_data.get("successVisible")),
                            "captcha_visible": bool(state_data.get("captchaVisible")),
                        },
                    )

                break

        from hub.providers.browser_automation_provider import BrowserErrorCode

        return BrowserResult(
            success=False,
            action="solve_captcha",
            data={"selector": selector, "captcha_detected": True, "attempts": max_attempts, "solver_provider": "ollama"},
            error=f"CAPTCHA was not solved after {max_attempts} attempt(s)",
            error_code=BrowserErrorCode.UNKNOWN,
            suggestions=["Increase max_attempts, adjust selectors, or run this Flow manually if the portal CAPTCHA has changed."],
        )

    def _load_browser_session_profile(
        self,
        tenant_id: Optional[str],
        *,
        integration_id: Optional[int] = None,
        profile_name: Optional[str] = None,
    ) -> tuple[Optional[dict], Optional[dict]]:
        """Return sanitized profile metadata plus decrypted Playwright storage state."""
        if not self._db or not tenant_id or (not integration_id and not profile_name):
            return None, None
        try:
            from services.browser_session_profile_service import load_profile_storage_state

            integration, storage_state = load_profile_storage_state(
                self._db,
                str(tenant_id),
                integration_id=integration_id,
                profile_name=profile_name,
            )
            if not integration:
                return None, None
            return {
                "id": integration.id,
                "profile_name": integration.session_profile_name,
                "provider_type": integration.provider_type,
                "mode": integration.mode,
                "browser_type": integration.browser_type,
                "headless": integration.headless,
                "timeout_seconds": integration.timeout_seconds,
                "viewport_width": integration.viewport_width,
                "viewport_height": integration.viewport_height,
                "session_ttl_seconds": integration.session_ttl_seconds,
                "cdp_url": integration.cdp_url,
            }, storage_state
        except Exception as exc:
            logger.warning("Could not load browser session profile: %s", exc)
            return None, None

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Detect if message contains browser automation intent.

        Uses keyword pre-filter followed by AI classification.

        Args:
            message: Inbound message

        Returns:
            True if message requests browser automation
        """
        config = getattr(self, '_config', {}) or self.get_default_config()
        if not self.is_legacy_enabled(config):
            return False

        # Skip if message has media (audio, image, etc.)
        if message.media_type:
            return False

        text = message.body.lower()
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
            db=self._db
        )

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process browser automation request.

        Steps:
        1. Parse natural language into actions
        2. Execute actions via Playwright provider
        3. Format and return results

        Args:
            message: Inbound message with browser command
            config: Skill configuration

        Returns:
            SkillResult with execution results
        """
        try:
            logger.info(f"BrowserAutomationSkill: Processing message: {message.body[:100]}...")

            # Store context for Sentinel SSRF checks in _execute_action
            self._tenant_id = getattr(message, 'tenant_id', None)
            self._agent_id = getattr(message, 'agent_id', None)
            self._sender_key = getattr(message, 'sender_key', None)

            provider_type = config.get('provider_type', 'playwright')

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
                db=self._db,
                token_tracker=self.token_tracker,
                tenant_id=self._resolve_tenant_id()
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

7. wait_for - Wait for an element
   params: {"selector": "CSS selector", "state": "visible"|"hidden"|"attached"|"detached", "timeout_ms": 10000}

8. wait_for_url - Wait for URL navigation
   params: {"url_contains": "/dashboard", "timeout_ms": 10000}

9. dismiss_modal - Try a best-effort modal/banner dismissal without failing if missing
   params: {"selector": "CSS selector"}

10. solve_captcha - Explicit CAPTCHA boundary
   params: {"selector": "CSS selector"}

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

    async def _sentinel_ssrf_check(self, url: str, tenant_id: str = None, agent_id: int = None, sender_key: str = None) -> bool:
        """
        Run Sentinel browser_ssrf analysis on a URL before navigation.

        This provides LLM-based intent analysis complementing the pattern-based
        SSRF validation in ssrf_validator.py. Catches obfuscated or indirect
        SSRF attempts that pattern matching might miss.

        Args:
            url: URL to check
            tenant_id: Tenant ID for config resolution
            agent_id: Agent ID for agent-specific config
            sender_key: User identifier for audit logging

        Returns:
            True if URL is safe to navigate, False if blocked by Sentinel
        """
        if not self._db:
            return True  # No DB session = can't run Sentinel check

        try:
            from services.sentinel_service import SentinelService
            sentinel = SentinelService(self._db, tenant_id, token_tracker=self.token_tracker)
            result = await sentinel.analyze_browser_url(
                url=url,
                agent_id=agent_id,
                sender_key=sender_key,
                skill_type="browser_automation",
            )

            if result.is_threat_detected and result.action == "blocked":
                # BUG-354 FIX: When Sentinel's LLM is unavailable it returns a
                # fail-closed block with "Security analysis unavailable".  For
                # browser navigation this is too aggressive — allow navigation
                # and let the pattern-based ssrf_validator in PlaywrightProvider
                # still protect against real SSRF.
                if "Security analysis unavailable" in (result.threat_reason or ""):
                    logger.warning(
                        f"Sentinel browser_ssrf LLM unavailable for {url}, "
                        f"allowing navigation (pattern-based SSRF validator still active)"
                    )
                    return True

                logger.warning(
                    f"Sentinel browser_ssrf blocked navigation to {url}: "
                    f"score={result.threat_score}, reason={result.threat_reason}"
                )
                return False

            if result.is_threat_detected:
                # detect_only or warn_only mode — log but allow
                logger.info(
                    f"Sentinel browser_ssrf detected (non-blocking): {url}, "
                    f"score={result.threat_score}, reason={result.threat_reason}"
                )

            return True

        except Exception as e:
            # Fail open: if Sentinel check fails, allow navigation
            # The pattern-based ssrf_validator in PlaywrightProvider still protects
            logger.warning(f"Sentinel browser_ssrf check failed (allowing): {e}")
            return True

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

        def _page_script(script: str) -> str:
            stripped = (script or "").strip()
            if not stripped:
                return "() => null"
            if stripped.startswith(("(", "async ", "function ")):
                return stripped
            return f"() => {{ {stripped} }}"

        async def _quick_dom_click(selector: str) -> Optional[BrowserResult]:
            selector = (selector or "").strip()
            if not selector:
                return None
            try:
                script = (
                    "() => { "
                    f"const el = document.querySelector({json.dumps(selector)}); "
                    "if (!(el instanceof HTMLElement)) return false; "
                    "el.click(); return true; "
                    "}"
                )
                click_result = await provider.execute_script(script)
                if click_result.success and click_result.data.get("result"):
                    return BrowserResult(
                        success=True,
                        action='dismiss_modal',
                        data={"selector": selector, "dismissed": True, "used_quick_dom_click": True},
                    )
            except Exception:
                return None
            return None

        if action_name == 'navigate':
            url = params.get('url', '')
            # Sentinel SSRF pre-check (LLM-based intent analysis)
            if not await self._sentinel_ssrf_check(
                url,
                tenant_id=getattr(self, '_tenant_id', None),
                agent_id=getattr(self, '_agent_id', None),
                sender_key=getattr(self, '_sender_key', None),
            ):
                return BrowserResult(
                    success=False,
                    action='navigate',
                    data={},
                    error="Navigation blocked by security policy"
                )
            return await provider.navigate(
                url=url,
                wait_until=params.get('wait_until', 'load')
            )

        elif action_name == 'click':
            result = await provider.click(
                selector=params.get('selector', '')
            )
            if result.success or not params.get("fallback_selector"):
                return result
            fallback_selector = params.get("fallback_selector")
            fallback_result = await provider.click(selector=fallback_selector)
            if fallback_result.success:
                fallback_result.data = {
                    **(fallback_result.data or {}),
                    "selector": fallback_selector,
                    "primary_selector": params.get("selector", ""),
                    "used_fallback_selector": True,
                }
            return fallback_result

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

        # 35b: Rich action set
        elif action_name == 'scroll':
            return await provider.scroll(
                selector=params.get('selector', 'body'),
                x=params.get('x', 0),
                y=params.get('y', 300),
            )
        elif action_name == 'select_option':
            return await provider.select_option(
                selector=params.get('selector', ''),
                value=params.get('value', ''),
            )
        elif action_name == 'hover':
            return await provider.hover(
                selector=params.get('selector', ''),
            )
        elif action_name == 'wait_for':
            return await provider.wait_for(
                selector=params.get('selector', ''),
                state=params.get('state', 'visible'),
                timeout_ms=params.get('timeout_ms'),
            )
        elif action_name == 'wait_for_url':
            return await provider.wait_for_url(
                url_contains=params.get('url_contains') or params.get('url') or '',
                timeout_ms=params.get('timeout_ms'),
            )
        elif action_name == 'dismiss_modal':
            result = await _quick_dom_click(params.get('selector', ''))
            if result:
                return result
            if params.get("fallback_selector"):
                fallback_result = await _quick_dom_click(params.get("fallback_selector"))
                if fallback_result:
                    fallback_result.data = {
                        **(fallback_result.data or {}),
                        "primary_selector": params.get('selector', ''),
                        "used_fallback_selector": True,
                    }
                    return fallback_result
            if params.get("fallback_script"):
                script_result = await provider.execute_script(_page_script(params.get("fallback_script")))
                if script_result.success:
                    return BrowserResult(success=True, action='dismiss_modal', data={"selector": params.get('selector', ''), "dismissed": True, "used_fallback_script": True, "result": script_result.data.get("result")})
            return BrowserResult(success=True, action='dismiss_modal', data={"selector": params.get('selector', ''), "dismissed": False, "skipped": True})
        elif action_name == 'solve_captcha':
            selector = params.get('selector') or "iframe[src*='captcha'], img[src*='captcha'], [class*='captcha']"
            detection = await provider.execute_script(f"() => Boolean(document.querySelector({json.dumps(selector)}))")
            if detection.success and not detection.data.get("result"):
                return BrowserResult(success=True, action='solve_captcha', data={"selector": selector, "captcha_detected": False})
            solver_provider = str(params.get("solver_provider") or params.get("captcha_solver_provider") or "ollama").strip().lower()
            if solver_provider == "ollama":
                return await self._solve_image_captcha(provider, {**params, "selector": selector})
            from hub.providers.browser_automation_provider import BrowserErrorCode
            return BrowserResult(
                success=False,
                action='solve_captcha',
                data={"selector": selector, "captcha_detected": True, "solver_provider": solver_provider},
                error=f"CAPTCHA solver provider '{solver_provider}' is not configured",
                error_code=BrowserErrorCode.UNKNOWN,
                suggestions=["Set solver_provider=ollama with an Ollama vision model, or replace this step with a manual challenge node before enabling scheduled runs."],
            )
        elif action_name == 'go_back':
            return await provider.go_back()
        elif action_name == 'go_forward':
            return await provider.go_forward()
        elif action_name == 'get_attribute':
            return await provider.get_attribute(
                selector=params.get('selector', ''),
                attribute=params.get('attribute', ''),
            )
        elif action_name == 'get_page_url':
            return await provider.get_page_url()
        elif action_name == 'type_text':
            return await provider.type_text(
                selector=params.get('selector', ''),
                text=params.get('text', params.get('value', '')),
                delay_ms=params.get('delay_ms', 0),
            )

        # 35c: Multi-tab actions
        elif action_name == 'open_tab':
            return await provider.open_tab(url=params.get('url'))
        elif action_name == 'switch_tab':
            return await provider.switch_tab(tab_id=params.get('tab_id', ''))
        elif action_name == 'close_tab':
            return await provider.close_tab(tab_id=params.get('tab_id', ''))
        elif action_name == 'list_tabs':
            return await provider.list_tabs()

        else:
            from hub.providers.browser_automation_provider import BrowserErrorCode
            return BrowserResult(
                success=False,
                action=action_name,
                data={},
                error=f"Unknown action: {action_name}",
                error_code=BrowserErrorCode.UNKNOWN,
                suggestions=[f"Available actions: navigate, click, fill, extract, screenshot, execute_script, scroll, select_option, hover, wait_for, wait_for_url, dismiss_modal, solve_captcha, go_back, go_forward, get_attribute, get_page_url, type_text, open_tab, switch_tab, close_tab, list_tabs"],
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
                # 35f: Structured error feedback
                msg = f"{result.action}: Failed"
                if result.error_code:
                    msg += f" [{result.error_code.value}]"
                msg += f" — {result.error}"
                if result.suggestions:
                    msg += "\n  Suggestions:\n" + "\n".join(f"  - {s}" for s in result.suggestions)
                lines.append(msg)

        return "\n\n".join(lines) if lines else "No actions executed."

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Get default configuration for browser automation skill.

        Returns:
            Default config dict
        """
        return {
            "keywords": [],
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
                    "enum": ["playwright", "cdp"],
                    "description": "playwright=isolated container browser, cdp=connect to Chrome on host (authenticated sessions)",
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
                "requests to extract passwords/sensitive data, commands that "
                "try to bypass security measures, and SSRF attempts targeting "
                "internal IPs, cloud metadata, or Docker/Kubernetes services."
            )
        }

    @classmethod
    def get_sentinel_exemptions(cls) -> list:
        """
        Browser automation does NOT exempt browser_ssrf detection.
        SSRF protection must remain active even when the skill is enabled.
        """
        return []  # No exemptions — SSRF checks stay active

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
                "fill forms, extract content, scroll, hover, wait for elements, manage tabs, "
                "and more. Use 'container' mode for public websites."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "navigate", "screenshot", "click", "fill", "extract", "execute_script",
                            "scroll", "select_option", "hover", "wait_for", "wait_for_url", "dismiss_modal", "solve_captcha",
                            "go_back", "go_forward", "get_attribute", "get_page_url", "type_text",
                            "open_tab", "switch_tab", "close_tab", "list_tabs",
                        ],
                        "description": (
                            "Browser action to perform. Core: navigate, click, fill, extract, screenshot. "
                            "Interaction: scroll, hover, select_option, wait_for, wait_for_url, dismiss_modal, solve_captcha, type_text, execute_script. "
                            "Navigation: go_back, go_forward, get_page_url, get_attribute. "
                            "Tabs: open_tab, switch_tab, close_tab, list_tabs."
                        ),
                    },
                    "url": {
                        "type": "string",
                        "description": "URL for navigate/open_tab actions"
                    },
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for element targeting. Examples: '#login-btn', 'input[name=email]', '.submit-button'"
                    },
                    "value": {
                        "type": "string",
                        "description": "Text value for fill/select_option/type_text actions"
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture full scrollable page (true) or just viewport (false). Default: true",
                        "default": True
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["container", "cdp"],
                        "description": "container=isolated Playwright browser (default), cdp=connect to host Chrome with authenticated sessions",
                        "default": "container"
                    },
                    "wait_until": {
                        "type": "string",
                        "enum": ["load", "domcontentloaded", "networkidle"],
                        "description": "When to consider navigation complete",
                        "default": "load"
                    },
                    "x": {
                        "type": "integer",
                        "description": "Horizontal scroll amount in pixels (for scroll action)",
                        "default": 0
                    },
                    "y": {
                        "type": "integer",
                        "description": "Vertical scroll amount in pixels (for scroll action). Positive=down, negative=up",
                        "default": 300
                    },
                    "state": {
                        "type": "string",
                        "enum": ["visible", "hidden", "attached", "detached"],
                        "description": "Element state to wait for (for wait_for action)",
                        "default": "visible"
                    },
                    "attribute": {
                        "type": "string",
                        "description": "Element attribute name to read (for get_attribute action). Examples: 'href', 'src', 'class', 'data-id'"
                    },
                    "delay_ms": {
                        "type": "integer",
                        "description": "Delay between keystrokes in ms (for type_text action, 0=instant)",
                        "default": 0
                    },
                    "tab_id": {
                        "type": "string",
                        "description": "Tab identifier (for switch_tab/close_tab actions). Use list_tabs to see available IDs"
                    },
                    "script": {
                        "type": "string",
                        "description": "JavaScript code to execute (for execute_script action)"
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Custom timeout in milliseconds (for wait_for / wait_for_url actions)"
                    },
                    "url_contains": {
                        "type": "string",
                        "description": "URL substring to wait for (for wait_for_url action)"
                    },
                },
                "required": ["action"]
            },
            "annotations": {
                "destructive": True,
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
        # Store context for Sentinel SSRF checks
        self._tenant_id = getattr(message, 'tenant_id', None)
        self._agent_id = getattr(message, 'agent_id', None)
        self._sender_key = getattr(message, 'sender_key', None)

        action = arguments.get("action")

        ALL_ACTIONS = [
            "navigate", "screenshot", "click", "fill", "extract", "execute_script",
            "scroll", "select_option", "hover", "wait_for", "wait_for_url", "dismiss_modal", "solve_captcha",
            "go_back", "go_forward", "get_attribute", "get_page_url", "type_text",
            "open_tab", "switch_tab", "close_tab", "list_tabs",
        ]

        if not action:
            return SkillResult(
                success=False,
                output=f"Action is required. Available actions: {', '.join(ALL_ACTIONS)}",
                metadata={"error": "missing_action", "skip_ai": True}
            )

        # Resolve provider: mode argument overrides config
        mode = arguments.get("mode")
        if mode == "cdp":
            provider_type = "cdp"
        elif mode == "container":
            provider_type = "playwright"
        else:
            provider_type = config.get("provider_type", "playwright")

        logger.info(f"BrowserAutomationSkill.execute_tool: action={action}, provider={provider_type}")

        try:
            # Determine if we should use persistent sessions
            # CDP mode defaults to persistent (Chrome is already running)
            use_session = config.get("session_persistence", provider_type == "cdp")
            tenant_id = getattr(message, 'tenant_id', None) or self._resolve_tenant_id() or ''
            profile_integration_id = config.get("browser_session_integration_id")
            try:
                profile_integration_id = int(profile_integration_id) if profile_integration_id else None
            except (TypeError, ValueError):
                profile_integration_id = None
            profile_name = config.get("browser_session_profile_name") or config.get("session_profile_name")
            profile_meta, storage_state = self._load_browser_session_profile(
                tenant_id,
                integration_id=profile_integration_id,
                profile_name=profile_name,
            )
            if profile_meta:
                provider_type = profile_meta.get("provider_type") or provider_type
                use_session = True

            if use_session:
                from hub.providers.browser_session_manager import BrowserSessionManager, BrowserSessionLimitError
                from hub.providers.browser_automation_provider import BrowserConfig as _BrowserConfig
                try:
                    # Build config for session manager
                    session_config = _BrowserConfig(
                        provider_type=provider_type,
                        mode=(profile_meta or {}).get("mode") or config.get("mode", "container"),
                        browser_type=(profile_meta or {}).get("browser_type") or config.get("browser_type", "chromium"),
                        headless=bool((profile_meta or {}).get("headless", config.get("headless", True))),
                        timeout_seconds=(profile_meta or {}).get("timeout_seconds") or config.get("timeout_seconds") or 30,
                        viewport_width=(profile_meta or {}).get("viewport_width") or config.get("viewport_width", 1280),
                        viewport_height=(profile_meta or {}).get("viewport_height") or config.get("viewport_height", 720),
                        cdp_url=(profile_meta or {}).get("cdp_url") or config.get("cdp_url", "http://host.docker.internal:9222"),
                        session_persistence=True,
                        session_ttl_seconds=(profile_meta or {}).get("session_ttl_seconds") or config.get("session_ttl_seconds", 300),
                        tenant_id=str(tenant_id) if tenant_id else None,
                        browser_session_profile_name=(profile_meta or {}).get("profile_name") or profile_name,
                        browser_session_integration_id=(profile_meta or {}).get("id") or profile_integration_id,
                        storage_state=storage_state,
                    )
                    # Resolve provider factory
                    provider_factory = None
                    if provider_type == "cdp":
                        from hub.providers.cdp_provider import CDPProvider
                        provider_factory = CDPProvider

                    session = await BrowserSessionManager.instance().get_or_create(
                        tenant_id=str(tenant_id) if tenant_id else '',
                        agent_id=getattr(message, 'agent_id', 0) or 0,
                        sender_key=getattr(message, 'sender_key', '') or '',
                        config=session_config,
                        ttl_seconds=session_config.session_ttl_seconds,
                        max_sessions=session_config.max_concurrent_sessions,
                        provider_factory=provider_factory,
                    )
                    provider = session.provider
                    should_cleanup = False  # Session manager owns lifecycle
                    logger.info("BrowserAutomationSkill.execute_tool: Using persistent session")
                except BrowserSessionLimitError as e:
                    return SkillResult(
                        success=False,
                        output=f"Cannot open browser: {e}",
                        metadata={"error": "session_limit", "skip_ai": True}
                    )
            else:
                # Stateless: fresh provider per request
                provider = BrowserAutomationRegistry.get_provider(
                    provider_name=provider_type,
                    db=self._db
                )
                should_cleanup = True

            if not provider:
                return SkillResult(
                    success=False,
                    output=f"Browser automation provider '{provider_type}' is not available. "
                           "The system administrator needs to configure it.",
                    metadata={"error": "provider_unavailable", "provider": provider_type, "skip_ai": True}
                )

            screenshot_paths = []

            try:
                await provider.initialize()  # no-op if session already initialized
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
                elif action in ALL_ACTIONS:
                    # 35b/35c: Delegate all other valid actions via _execute_action
                    action_def = {"action": action, "params": arguments}
                    browser_result = await self._execute_action(provider, action_def)
                    if browser_result.success:
                        # Format data for output
                        data_summary = ", ".join(f"{k}={v}" for k, v in browser_result.data.items() if k != "tabs")
                        output = f"{action}: {data_summary}" if data_summary else f"{action}: Success"
                        result = SkillResult(
                            success=True, output=output,
                            metadata={**browser_result.data, "skip_ai": True}
                        )
                    else:
                        # 35f: Include structured error info
                        error_info = browser_result.error or "Unknown error"
                        suggestions_text = ""
                        if browser_result.suggestions:
                            suggestions_text = "\nSuggestions:\n" + "\n".join(f"- {s}" for s in browser_result.suggestions)
                        result = SkillResult(
                            success=False,
                            output=f"{action} failed: {error_info}{suggestions_text}",
                            metadata={
                                "error": error_info,
                                "error_code": browser_result.error_code.value if browser_result.error_code else None,
                                "suggestions": browser_result.suggestions,
                                "skip_ai": True,
                            }
                        )
                else:
                    result = SkillResult(
                        success=False,
                        output=f"Unknown action: {action}. Available: {', '.join(ALL_ACTIONS)}",
                        metadata={"error": "invalid_action", "skip_ai": True}
                    )

            finally:
                if should_cleanup:
                    await provider.cleanup()
                    logger.info("BrowserAutomationSkill.execute_tool: Provider cleaned up")
                else:
                    logger.info("BrowserAutomationSkill.execute_tool: Session kept alive")

            # Add common metadata
            if result.metadata:
                result.metadata["provider"] = provider_type
                result.metadata["action"] = action
            else:
                result.metadata = {
                    "provider": provider_type,
                    "action": action,
                    "skip_ai": True
                }
            if profile_meta:
                result.metadata["browser_session_profile_name"] = profile_meta.get("profile_name")
                result.metadata["browser_session_integration_id"] = profile_meta.get("id")
                result.metadata["browser_session_storage_state"] = "loaded" if storage_state else "missing"

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

        # Sentinel SSRF pre-check (LLM-based intent analysis)
        if not await self._sentinel_ssrf_check(
            url,
            tenant_id=getattr(self, '_tenant_id', None),
            agent_id=getattr(self, '_agent_id', None),
            sender_key=getattr(self, '_sender_key', None),
        ):
            return SkillResult(
                success=False,
                output="Navigation blocked by security policy",
                metadata={"error": "ssrf_blocked", "skip_ai": True}
            )

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
        used_fallback_selector = False
        primary_error = result.error

        if not result.success and arguments.get("fallback_selector"):
            fallback_selector = arguments.get("fallback_selector")
            fallback_result = await provider.click(selector=fallback_selector)
            if fallback_result.success:
                selector = fallback_selector
                result = fallback_result
                used_fallback_selector = True

        if result.success:
            return SkillResult(
                success=True,
                output=f"Clicked element: {selector}",
                metadata={
                    "selector": selector,
                    "primary_error": primary_error if used_fallback_selector else None,
                    "used_fallback_selector": used_fallback_selector,
                    "skip_ai": True,
                }
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
