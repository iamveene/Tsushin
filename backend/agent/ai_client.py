import os
import logging
import asyncio
import json
from typing import Dict, Optional, TYPE_CHECKING
from sqlalchemy.orm import Session
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
import google.generativeai as genai
import httpx  # Phase 5.2: Ollama support
from services.api_key_service import get_api_key

if TYPE_CHECKING:
    from analytics.token_tracker import TokenTracker

class AIClient:
    """Unified AI client supporting Anthropic, OpenAI, and Google Gemini"""

    def __init__(
        self,
        provider: str,
        model_name: str,
        db: Optional[Session] = None,
        token_tracker: Optional["TokenTracker"] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tenant_id: Optional[str] = None,
        provider_instance_id: Optional[int] = None,
    ):
        """
        Initialize AI client with database session for API key loading.

        Args:
            provider: AI provider ('anthropic', 'openai', 'gemini', 'ollama', 'openrouter', 'groq', 'grok', 'deepseek', 'vertex_ai')
            model_name: Model identifier
            db: Database session for loading API keys (optional, falls back to env vars)
            token_tracker: TokenTracker instance for usage tracking (Phase 7.2)
            temperature: Model temperature (0.0-1.0), defaults to 0.7
            max_tokens: Maximum response tokens, defaults to 2048
            tenant_id: Tenant ID for loading tenant-specific API keys
            provider_instance_id: Optional provider instance ID for per-instance API key/URL resolution
        """
        self.provider = provider.lower()
        self.model_name = model_name
        self.logger = logging.getLogger(__name__)
        self.db = db
        self.token_tracker = token_tracker
        self.tenant_id = tenant_id
        if token_tracker is None:
            self.logger.debug(f"AIClient({provider}/{model_name}): no token_tracker — costs will not be tracked")
        # Model settings - configurable via playground settings
        self.temperature = temperature if temperature is not None else 0.7
        # BUG FIX 2026-01-17: Increased from 2048 to 16384 to prevent truncation of long responses
        # (e.g., flight search results with multiple options). Most modern LLMs support 8K-128K+ tokens.
        self.max_tokens = max_tokens if max_tokens is not None else 16384

        # Provider Instance resolution — takes precedence over flat fields
        if provider_instance_id is not None and db is not None:
            from services.provider_instance_service import ProviderInstanceService, VENDOR_DEFAULT_BASE_URLS
            instance = ProviderInstanceService.get_instance(provider_instance_id, tenant_id, db)
            if instance and instance.is_active:
                self.provider = instance.vendor
                api_key = ProviderInstanceService.resolve_api_key(instance, db)
                base_url = instance.base_url or VENDOR_DEFAULT_BASE_URLS.get(instance.vendor)

                # DNS rebinding guard at request time
                if instance.base_url:
                    from utils.ssrf_validator import validate_url, validate_ollama_url, SSRFValidationError
                    try:
                        if instance.vendor == "ollama":
                            validate_ollama_url(instance.base_url)
                        else:
                            validate_url(instance.base_url)
                    except SSRFValidationError as e:
                        self.logger.error(f"SSRF blocked for provider instance {instance.id}: {e}")
                        raise ValueError(f"Provider instance URL blocked: {e}")

                # Initialize client based on vendor type
                if instance.vendor == "anthropic":
                    if not api_key:
                        raise ValueError("Anthropic API key not configured for this instance")
                    self.client = AsyncAnthropic(api_key=api_key)
                elif instance.vendor == "gemini":
                    if not api_key:
                        raise ValueError("Gemini API key not configured for this instance")
                    genai.configure(api_key=api_key)
                    self.client = genai.GenerativeModel(model_name)
                elif instance.vendor == "ollama":
                    self.ollama_base_url = base_url or "http://host.docker.internal:11434"
                    self.client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0))
                    if api_key:
                        self.ollama_api_key = api_key
                elif instance.vendor == "vertex_ai":
                    # Vertex AI instance: api_key stores the PEM private key
                    # Project ID, region, SA email loaded from api_key_service or env vars
                    vertex_private_key = api_key or os.getenv("VERTEX_AI_PRIVATE_KEY", "")
                    vertex_project_id = get_api_key('vertex_ai_project_id', db, tenant_id=tenant_id) or os.getenv("VERTEX_AI_PROJECT_ID", "")
                    vertex_region = get_api_key('vertex_ai_region', db, tenant_id=tenant_id) or os.getenv("VERTEX_AI_REGION", "us-east5")
                    vertex_sa_email = get_api_key('vertex_ai_sa_email', db, tenant_id=tenant_id) or os.getenv("VERTEX_AI_SERVICE_ACCOUNT_EMAIL", "")

                    if not vertex_project_id or not vertex_sa_email or not vertex_private_key:
                        raise ValueError("Vertex AI instance requires project_id, service_account_email, and private_key.")

                    self.vertex_project_id = vertex_project_id
                    self.vertex_region = vertex_region
                    self.vertex_sa_email = vertex_sa_email

                    if model_name.startswith("claude"):
                        self.vertex_publisher = "anthropic"
                    elif model_name.startswith("mistral") or model_name.startswith("codestral"):
                        self.vertex_publisher = "mistralai"
                    else:
                        self.vertex_publisher = "google"

                    from google.oauth2 import service_account as sa_module
                    from google.auth.transport.requests import Request as AuthRequest

                    formatted_key = vertex_private_key.replace('\\n', '\n')
                    credentials_info = {
                        "type": "service_account",
                        "project_id": vertex_project_id,
                        "client_email": vertex_sa_email,
                        "private_key": formatted_key,
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                    self._vertex_credentials = sa_module.Credentials.from_service_account_info(
                        credentials_info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
                    )
                    self._vertex_auth_request = AuthRequest()

                    if self.vertex_publisher == "google":
                        self._vertex_credentials.refresh(self._vertex_auth_request)
                        vi_base_url = f"https://{vertex_region}-aiplatform.googleapis.com/v1/projects/{vertex_project_id}/locations/{vertex_region}/endpoints/openapi"
                        self.client = AsyncOpenAI(api_key=self._vertex_credentials.token, base_url=vi_base_url)
                        if not self.model_name.startswith("google/"):
                            self.model_name = f"google/{self.model_name}"
                    else:
                        self.client = None  # Claude via Vertex uses httpx directly
                else:
                    # All OpenAI-compatible (openai, groq, grok, openrouter, custom)
                    if not api_key:
                        raise ValueError(f"{instance.vendor} API key not configured for this instance")
                    self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

                self.logger.info(f"AIClient initialized via provider instance {instance.id} ({instance.vendor})")
                return  # Skip the flat-field path below

        # Get API key from database or environment (skip for Ollama and Vertex AI - Phase 5.2)
        # Priority: DB tenant key → DB system key → env var fallback (handled by get_api_key)
        api_key = None
        if db and provider not in ('ollama', 'vertex_ai'):
            api_key = get_api_key(self.provider, db, tenant_id=tenant_id)

        # Vertex AI uses its own credential loading (service account, not simple API key)
        # but may store the private key in the api_key table
        if db and provider == 'vertex_ai':
            api_key = get_api_key('vertex_ai', db, tenant_id=tenant_id)  # Optional — private key from DB

        # Validate API key for cloud providers (skip Ollama and Vertex AI which handle their own auth)
        if provider not in ('ollama', 'vertex_ai') and not api_key:
            raise ValueError(
                f"No API key found for provider: {provider}. "
                f"Configure via Hub → API Keys or set environment variable."
            )

        # Initialize async clients (Phase 6.11.1)
        if self.provider == "anthropic":
            self.client = AsyncAnthropic(api_key=api_key)  # Native async support
        elif self.provider == "openai":
            self.client = AsyncOpenAI(api_key=api_key)  # Native async support
        elif self.provider == "gemini":
            genai.configure(api_key=api_key)
            # Using legacy SDK - will use asyncio.to_thread() for async
            self.client = genai.GenerativeModel(model_name)
        elif self.provider == "ollama":
            # Phase 5.2: Ollama HTTP client (API key optional for remote/secured instances)
            # Load from Config table if available, otherwise from env var
            ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
            ollama_api_key = None

            if db:
                from models import Config
                config = db.query(Config).first()
                if config and config.ollama_base_url:
                    ollama_base_url = config.ollama_base_url
                if config and config.ollama_api_key:
                    ollama_api_key = config.ollama_api_key

            self.ollama_base_url = ollama_base_url
            self.ollama_api_key = ollama_api_key

            if self.ollama_base_url:
                from utils.ssrf_validator import validate_ollama_url, SSRFValidationError
                try:
                    self.ollama_base_url = validate_ollama_url(self.ollama_base_url)
                except SSRFValidationError as e:
                    self.logger.error(f"SSRF blocked: Ollama base URL '{self.ollama_base_url}' rejected: {e}. Falling back to default.")
                    self.ollama_base_url = "http://host.docker.internal:11434"

            # Extended timeout for CPU inference (first load can be slow)
            headers = {}
            if ollama_api_key:
                headers["Authorization"] = f"Bearer {ollama_api_key}"

            self.client = httpx.AsyncClient(
                timeout=600.0,  # 600s (10 min) timeout for reasoning models on CPU (deepseek-r1 can be very slow)
                headers=headers if headers else None
            )
            self.logger.info(f"Initialized Ollama client: {self.ollama_base_url}")
        elif self.provider == "openrouter":
            # OpenRouter: Unified API gateway for 100+ models
            # Uses OpenAI-compatible API with custom base URL
            # Model format: provider/model (e.g., google/gemini-2.5-flash, anthropic/claude-3.5-sonnet)
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1"
            )
            self.logger.info(f"Initialized OpenRouter client with model: {model_name}")
        elif self.provider == "groq":
            # Groq: Ultra-fast inference for open models (LLaMA, Mixtral, Gemma)
            # Uses OpenAI-compatible API with custom base URL
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://api.groq.com/openai/v1"
            )
            self.logger.info(f"Initialized Groq client with model: {model_name}")
        elif self.provider == "grok":
            # Grok (xAI): Elon Musk's xAI models
            # Uses OpenAI-compatible API with custom base URL
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://api.x.ai/v1"
            )
            self.logger.info(f"Initialized Grok (xAI) client with model: {model_name}")
        elif self.provider == "deepseek":
            # DeepSeek: Affordable reasoning and chat models
            # Uses OpenAI-compatible API with custom base URL
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com/v1"
            )
            self.logger.info(f"Initialized DeepSeek client with model: {model_name}")
        elif self.provider == "vertex_ai":
            # Vertex AI uses service account credentials, not a simple API key
            # Priority: DB (per-tenant) → env var fallback
            vertex_private_key = api_key or os.getenv("VERTEX_AI_PRIVATE_KEY", "")

            # Load project_id, region, sa_email from DB or env vars
            vertex_project_id = os.getenv("VERTEX_AI_PROJECT_ID", "")
            vertex_region = os.getenv("VERTEX_AI_REGION", "us-east5")
            vertex_sa_email = os.getenv("VERTEX_AI_SERVICE_ACCOUNT_EMAIL", "")

            if db:
                db_project = get_api_key('vertex_ai_project_id', db, tenant_id=tenant_id)
                db_region = get_api_key('vertex_ai_region', db, tenant_id=tenant_id)
                db_sa_email = get_api_key('vertex_ai_sa_email', db, tenant_id=tenant_id)
                if db_project:
                    vertex_project_id = db_project
                if db_region:
                    vertex_region = db_region
                if db_sa_email:
                    vertex_sa_email = db_sa_email

            if not vertex_project_id or not vertex_sa_email or not vertex_private_key:
                raise ValueError(
                    "Vertex AI requires project_id, service_account_email, and private_key. "
                    "Configure via Hub → Integrations or set VERTEX_AI_* environment variables."
                )

            # Store config for use in API calls (private key not stored — only needed for credential init)
            self.vertex_project_id = vertex_project_id
            self.vertex_region = vertex_region
            self.vertex_sa_email = vertex_sa_email

            # Determine publisher from model name
            # Claude models go through Anthropic publisher, everything else through Google
            if model_name.startswith("claude"):
                self.vertex_publisher = "anthropic"
            elif model_name.startswith("mistral") or model_name.startswith("codestral"):
                self.vertex_publisher = "mistralai"
            else:
                self.vertex_publisher = "google"

            # Create OAuth2 credentials for token refresh
            from google.oauth2 import service_account as sa_module
            from google.auth.transport.requests import Request as AuthRequest

            # Format the private key (handle escaped newlines)
            formatted_key = vertex_private_key.replace('\\n', '\n')

            credentials_info = {
                "type": "service_account",
                "project_id": vertex_project_id,
                "client_email": vertex_sa_email,
                "private_key": formatted_key,
                "token_uri": "https://oauth2.googleapis.com/token",
            }

            self._vertex_credentials = sa_module.Credentials.from_service_account_info(
                credentials_info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            self._vertex_auth_request = AuthRequest()

            # For Gemini models, we can use the OpenAI-compatible endpoint
            # For Anthropic models, we need rawPredict with Anthropic format
            if self.vertex_publisher == "google":
                # Use OpenAI-compatible chat completions endpoint
                self._vertex_credentials.refresh(self._vertex_auth_request)
                base_url = f"https://{vertex_region}-aiplatform.googleapis.com/v1/projects/{vertex_project_id}/locations/{vertex_region}/endpoints/openapi"
                self.client = AsyncOpenAI(
                    api_key=self._vertex_credentials.token,
                    base_url=base_url
                )
                # OpenAI-compat endpoint requires google/ prefix for model names
                if not self.model_name.startswith("google/"):
                    self.model_name = f"google/{self.model_name}"
            elif self.vertex_publisher == "anthropic":
                # Claude via Vertex uses httpx directly with rawPredict — no SDK client needed
                self.client = None

            self.logger.info(f"Initialized Vertex AI client: project={vertex_project_id}, region={vertex_region}, publisher={self.vertex_publisher}, model={model_name}")
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        operation_type: str = "message_processing",
        agent_id: Optional[int] = None,
        agent_run_id: Optional[int] = None,
        skill_type: Optional[str] = None,
        sender_key: Optional[str] = None,
        message_id: Optional[str] = None,
        tools: Optional[list] = None,
    ) -> Dict:
        """
        Generate response from AI model.

        Args:
            system_prompt: System instructions
            user_message: User input
            operation_type: Type of operation for tracking (Phase 7.2)
            agent_id: Agent performing operation (Phase 7.2)
            agent_run_id: Associated run ID (Phase 7.2)
            skill_type: Skill using this generation (Phase 7.2)
            sender_key: User who triggered (Phase 7.2)
            message_id: MCP message ID (Phase 7.2)
            tools: Optional list of tools in Ollama format for native tool calling

        Returns dict with: answer, token_usage, error
        """
        # Log LLM provider and model being used (use print to ensure visibility in docker logs)
        print(f"🤖 AIClient.generate(): provider={self.provider}, model={self.model_name}, operation={operation_type}, agent_id={agent_id}")

        try:
            if self.provider == "anthropic":
                result = await self._call_anthropic(system_prompt, user_message)
            elif self.provider == "openai":
                result = await self._call_openai(system_prompt, user_message)
            elif self.provider == "gemini":
                result = await self._call_gemini(system_prompt, user_message)
            elif self.provider == "ollama":
                result = await self._call_ollama(system_prompt, user_message, tools=tools)  # Phase 5.2
            elif self.provider == "openrouter":
                # OpenRouter uses OpenAI-compatible API
                result = await self._call_openai(system_prompt, user_message)
            elif self.provider in ("groq", "grok", "deepseek"):
                # Groq, Grok, and DeepSeek use OpenAI-compatible API
                result = await self._call_openai(system_prompt, user_message)
            elif self.provider == "vertex_ai":
                if self.vertex_publisher == "google":
                    # Gemini via OpenAI-compatible endpoint — refresh token first
                    self._refresh_vertex_token()
                    result = await self._call_openai(system_prompt, user_message)
                elif self.vertex_publisher == "anthropic":
                    result = await self._call_vertex_anthropic(system_prompt, user_message)
                else:
                    result = await self._call_vertex_raw(system_prompt, user_message)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")

            # Phase 7.2: Track token usage if tracker provided and usage available
            if self.token_tracker and result.get("token_usage") and not result.get("error"):
                usage = result["token_usage"]
                if usage.get("total", 0) > 0:  # Only track if we have actual usage
                    try:
                        self.token_tracker.track_usage(
                            operation_type=operation_type,
                            model_provider=self.provider,
                            model_name=self.model_name,
                            prompt_tokens=usage.get("prompt", 0),
                            completion_tokens=usage.get("completion", 0),
                            agent_id=agent_id,
                            agent_run_id=agent_run_id,
                            skill_type=skill_type,
                            sender_key=sender_key,
                            message_id=message_id,
                        )
                    except Exception as track_err:
                        self.logger.warning(f"Failed to track token usage: {track_err}")

            return result

        except Exception as e:
            self.logger.error(f"Error calling {self.provider}: {e}", exc_info=True)
            return {
                "answer": None,
                "token_usage": None,
                "error": str(e)
            }

    async def _call_anthropic(self, system_prompt: str, user_message: str) -> Dict:
        """Call Anthropic Claude API"""
        print(f"  📡 Calling Anthropic API: model={self.model_name}")

        # AsyncAnthropic client — await directly
        response = await self.client.messages.create(
            model=self.model_name,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        answer = response.content[0].text if response.content else ""

        token_usage = {
            "prompt": response.usage.input_tokens,
            "completion": response.usage.output_tokens,
            "total": response.usage.input_tokens + response.usage.output_tokens
        }

        return {
            "answer": answer,
            "token_usage": token_usage,
            "error": None
        }

    async def _call_openai(self, system_prompt: str, user_message: str) -> Dict:
        """Call OpenAI GPT API"""
        provider_name = "OpenRouter" if self.provider == "openrouter" else "OpenAI"
        print(f"  📡 Calling {provider_name} API: model={self.model_name}")

        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature
        )

        answer = response.choices[0].message.content if response.choices else ""

        token_usage = {
            "prompt": response.usage.prompt_tokens,
            "completion": response.usage.completion_tokens,
            "total": response.usage.total_tokens
        } if response.usage else None

        return {
            "answer": answer,
            "token_usage": token_usage,
            "error": None
        }

    async def _call_gemini(self, system_prompt: str, user_message: str) -> Dict:
        """Call Google Gemini API with asyncio.to_thread() (Phase 6.11.1)"""
        print(f"  📡 Calling Gemini API: model={self.model_name}")

        # Safety check: Truncate user message if suspiciously large
        MAX_CHARS = 1_000_000  # 1M chars safety limit
        if len(user_message) > MAX_CHARS:
            self.logger.warning(f"User message too large ({len(user_message)} chars), truncating to {MAX_CHARS}")
            user_message = user_message[:MAX_CHARS] + "\n\n[... context truncated due to size limits ...]"

        # Configure generation with temperature and max_tokens
        generation_config = genai.GenerationConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens
        )

        # BUG-133 fix: Use system_instruction for proper role separation
        # instead of concatenating system+user prompts (prevents prompt injection)
        model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=system_prompt,
            generation_config=generation_config,
        )

        # Run blocking call in thread pool to unblock event loop
        response = await asyncio.to_thread(
            model.generate_content,
            user_message,
            generation_config=generation_config,
        )

        # Handle multi-part responses from Gemini (fix for "response.text quick accessor" error)
        try:
            answer = response.text
        except ValueError:
            # Multi-part response - extract text from all parts
            self.logger.warning("Gemini returned multi-part response, extracting text from parts")
            answer = ""
            if hasattr(response, 'parts') and response.parts:
                answer = "".join(part.text for part in response.parts if hasattr(part, 'text'))
            elif hasattr(response, 'candidates') and response.candidates:
                # Extract from candidates
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and candidate.content:
                        if hasattr(candidate.content, 'parts'):
                            answer += "".join(part.text for part in candidate.content.parts if hasattr(part, 'text'))

            if not answer:
                self.logger.error("Could not extract text from multi-part Gemini response")
                answer = ""

        # Gemini token usage: Try usage_metadata first, fall back to estimation
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
            completion_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0
            total_tokens = getattr(response.usage_metadata, 'total_token_count', 0) or (prompt_tokens + completion_tokens)
            token_usage = {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": total_tokens
            }
            self.logger.info(f"Gemini token usage (actual): {token_usage}")
        else:
            # Fallback: estimate based on text length (~4 chars per token)
            estimated_prompt = (len(system_prompt) + len(user_message)) // 4
            estimated_completion = len(answer) // 4
            token_usage = {
                "prompt": estimated_prompt,
                "completion": estimated_completion,
                "total": estimated_prompt + estimated_completion
            }
            self.logger.info(f"Gemini token usage (estimated): {token_usage}")

        return {
            "answer": answer,
            "token_usage": token_usage,
            "error": None
        }

    async def _call_ollama(self, system_prompt: str, user_message: str, tools: list = None) -> Dict:
        """
        Call Ollama local LLM API (Phase 5.2).

        Uses /api/chat endpoint with OpenAI-compatible message format.
        Supports native Ollama tool calling for compatible models.
        """
        try:
            # Detect model types that need special handling
            model_lower = self.model_name.lower()
            is_reasoning_model = "deepseek-r1" in model_lower or "r1" in model_lower
            is_tool_calling_model = "tool-calling" in model_lower or "tool_calling" in model_lower

            # Tool-calling models need more tokens for tool output
            # Use configured max_tokens if provided, otherwise use model defaults
            if is_tool_calling_model:
                num_predict = self.max_tokens if self.max_tokens > 512 else 512
                num_ctx = 2048
            elif is_reasoning_model:
                num_predict = self.max_tokens if self.max_tokens > 1024 else 1024
                num_ctx = 4096
            else:
                num_predict = self.max_tokens if self.max_tokens > 256 else self.max_tokens
                num_ctx = 1024

            # Build request payload
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "top_p": 0.9,
                    "top_k": 40,
                    "num_predict": num_predict,
                    "num_ctx": num_ctx,
                }
            }

            # Add native tools for tool-calling models if provided
            if tools and is_tool_calling_model:
                payload["tools"] = tools
                self.logger.info(f"Added {len(tools)} native tools to Ollama request")

            self.logger.info(f"Calling Ollama: {self.ollama_base_url}/api/chat with {self.model_name}")
            self.logger.info(f"System prompt length: {len(system_prompt)} chars")
            self.logger.info(f"User message length: {len(user_message)} chars")
            self.logger.info(f"System prompt preview: {system_prompt[:500]}")
            self.logger.info(f"User message preview: {user_message[:500]}")

            # Make API request
            response = await self.client.post(
                f"{self.ollama_base_url}/api/chat",
                json=payload
            )

            # Handle HTTP errors
            if response.status_code != 200:
                error_text = response.text
                self.logger.error(f"Ollama API error: {response.status_code} - {error_text}")

                if response.status_code == 404:
                    return {
                        "answer": None,
                        "token_usage": None,
                        "error": f"Model '{self.model_name}' not found. Pull it first: ollama pull {self.model_name}"
                    }
                elif response.status_code == 500:
                    return {
                        "answer": None,
                        "token_usage": None,
                        "error": "Ollama server error. Check if running: curl http://localhost:11434"
                    }
                else:
                    return {
                        "answer": None,
                        "token_usage": None,
                        "error": f"Ollama API error: {response.status_code}"
                    }

            # Parse response
            response_data = response.json()
            message = response_data.get("message", {})
            content = message.get("content", "")
            thinking = message.get("thinking", "")
            tool_calls = message.get("tool_calls", [])

            # Handle native tool calls from Ollama
            if tool_calls:
                self.logger.info(f"Native Ollama tool calls detected: {len(tool_calls)}")
                # Convert native tool calls to our text format for processing
                tool_call_texts = []
                for tc in tool_calls:
                    func = tc.get("function", {})
                    tool_name = func.get("name", "")
                    args = func.get("arguments", {})

                    # Build text format: ```tool:name\ncommand:...\nparam:...```
                    lines = [f"```tool:{tool_name}"]
                    for key, value in args.items():
                        lines.append(f"{key}:{value}")
                    lines.append("```")
                    tool_call_texts.append("\n".join(lines))

                # Use ONLY the tool calls - ignore any extra content from the model
                # This prevents duplicate/verbose responses when model outputs both tool call AND explanation
                answer = "\n".join(tool_call_texts)
                if content:
                    self.logger.debug(f"Ignoring extra content from Ollama alongside tool calls: {content[:100]}")
                self.logger.info(f"Converted tool calls to text format: {answer[:200]}")
            # Handle reasoning models (e.g., deepseek-r1) that separate thinking from final answer
            elif thinking and not content:
                # Model only output thinking (hit token limit or reasoning-only mode)
                answer = thinking
                self.logger.info("DeepSeek-R1 reasoning model: using thinking output (no final answer)")
            elif thinking and content:
                # Model output both thinking and final answer
                answer = f"{content}"  # Use only final answer, skip thinking for brevity
                self.logger.info("DeepSeek-R1 reasoning model: using final answer (skipping thinking)")
            else:
                # Standard model: only content field
                answer = content

            # Extract token usage
            prompt_tokens = response_data.get("prompt_eval_count", 0)
            completion_tokens = response_data.get("eval_count", 0)
            total_tokens = prompt_tokens + completion_tokens

            token_usage = {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": total_tokens
            }

            return {
                "answer": answer,
                "token_usage": token_usage,
                "error": None
            }

        except httpx.ConnectError:
            return {
                "answer": None,
                "token_usage": None,
                "error": "Cannot connect to Ollama. Ensure it's running: ollama serve"
            }
        except httpx.TimeoutException:
            return {
                "answer": None,
                "token_usage": None,
                "error": f"Timeout. Model '{self.model_name}' may be slow. Try: ollama run {self.model_name}"
            }
        except Exception as e:
            self.logger.error(f"Ollama error: {e}", exc_info=True)
            return {
                "answer": None,
                "token_usage": None,
                "error": str(e)
            }

    async def generate_streaming(
        self,
        system_prompt: str,
        user_message: str,
        operation_type: str = "message_processing",
        agent_id: Optional[int] = None,
        agent_run_id: Optional[int] = None,
        skill_type: Optional[str] = None,
        sender_key: Optional[str] = None,
        message_id: Optional[str] = None,
        tools: Optional[list] = None,
    ):
        """
        Generate streaming response from AI model (Phase 14.9: WebSocket Streaming).

        Yields chunks as they arrive from the LLM provider:
        - {"type": "token", "content": str} - Token chunk
        - {"type": "done", "token_usage": dict, "error": str | None} - Final metadata

        Args:
            Same as generate() method

        Yields:
            Dict with type "token" or "done"
        """
        try:
            # Select provider-specific stream generator
            if self.provider == "anthropic":
                stream_gen = self._stream_anthropic(system_prompt, user_message)
            elif self.provider == "openai":
                stream_gen = self._stream_openai(system_prompt, user_message)
            elif self.provider == "gemini":
                stream_gen = self._stream_gemini(system_prompt, user_message)
            elif self.provider == "ollama":
                stream_gen = self._stream_ollama(system_prompt, user_message, tools=tools)
            elif self.provider == "openrouter":
                # OpenRouter uses OpenAI-compatible streaming API
                stream_gen = self._stream_openai(system_prompt, user_message)
            elif self.provider in ("groq", "grok", "deepseek"):
                # Groq, Grok, and DeepSeek use OpenAI-compatible streaming API
                stream_gen = self._stream_openai(system_prompt, user_message)
            elif self.provider == "vertex_ai":
                if self.vertex_publisher == "google":
                    self._refresh_vertex_token()
                    stream_gen = self._stream_openai(system_prompt, user_message)
                elif self.vertex_publisher == "anthropic":
                    stream_gen = self._stream_vertex_anthropic(system_prompt, user_message)
                else:
                    yield {"type": "error", "error": f"Streaming not supported for Vertex AI publisher: {self.vertex_publisher}"}
                    return
            else:
                yield {
                    "type": "error",
                    "error": f"Unsupported provider: {self.provider}"
                }
                return

            # Yield chunks and intercept "done" to track token usage
            async for chunk in stream_gen:
                if chunk.get("type") == "done" and self.token_tracker:
                    usage = chunk.get("token_usage")
                    if usage and usage.get("total", 0) > 0:
                        try:
                            self.token_tracker.track_usage(
                                operation_type=operation_type,
                                model_provider=self.provider,
                                model_name=self.model_name,
                                prompt_tokens=usage.get("prompt", 0),
                                completion_tokens=usage.get("completion", 0),
                                agent_id=agent_id,
                                agent_run_id=agent_run_id,
                                skill_type=skill_type,
                                sender_key=sender_key,
                                message_id=message_id,
                            )
                        except Exception as track_err:
                            self.logger.warning(f"Failed to track streaming token usage: {track_err}")
                yield chunk

        except Exception as e:
            self.logger.error(f"Error streaming from {self.provider}: {e}", exc_info=True)
            yield {
                "type": "error",
                "error": str(e)
            }

    async def _stream_anthropic(self, system_prompt: str, user_message: str):
        """
        Stream tokens from Anthropic Claude API.

        Note: Anthropic SDK provides native async support via AsyncAnthropic.
        No thread pool needed - properly async from the start.
        """
        try:
            accumulated_text = ""
            input_tokens = 0
            output_tokens = 0

            async with self.client.messages.stream(
                model=self.model_name,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            ) as stream:
                async for text in stream.text_stream:
                    accumulated_text += text
                    yield {"type": "token", "content": text}

                # Get final message with token counts
                message = await stream.get_final_message()
                input_tokens = message.usage.input_tokens
                output_tokens = message.usage.output_tokens

            yield {
                "type": "done",
                "token_usage": {
                    "prompt": input_tokens,
                    "completion": output_tokens,
                    "total": input_tokens + output_tokens
                },
                "error": None
            }
        except Exception as e:
            self.logger.error(f"Anthropic streaming error: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}

    async def _stream_openai(self, system_prompt: str, user_message: str):
        """
        Stream tokens from OpenAI API.

        Note: OpenAI SDK provides native async support via AsyncOpenAI.
        No thread pool needed - properly async from the start.
        """
        try:
            accumulated_text = ""

            stream = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=True,
                stream_options={"include_usage": True}
            )

            usage_data = None
            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        accumulated_text += delta.content
                        yield {"type": "token", "content": delta.content}
                # Capture usage from final chunk (sent with empty choices)
                if hasattr(chunk, 'usage') and chunk.usage:
                    usage_data = chunk.usage

            if usage_data:
                prompt_tokens = usage_data.prompt_tokens
                completion_tokens = usage_data.completion_tokens
            else:
                # Fallback estimation if provider doesn't support stream_options
                prompt_tokens = len(system_prompt + user_message) // 4
                completion_tokens = len(accumulated_text) // 4

            yield {
                "type": "done",
                "token_usage": {
                    "prompt": prompt_tokens,
                    "completion": completion_tokens,
                    "total": prompt_tokens + completion_tokens
                },
                "error": None
            }
        except Exception as e:
            self.logger.error(f"OpenAI streaming error: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}

    async def _stream_gemini(self, system_prompt: str, user_message: str):
        """
        Stream tokens from Google Gemini API.

        IMPORTANT: Google's generativeai SDK is SYNCHRONOUS ONLY (no async support).
        We use ThreadPoolExecutor + Queue to properly stream without blocking the event loop.

        This is different from Anthropic/OpenAI which have native async SDKs.
        Without the thread pool, all tokens would buffer and arrive at once.
        """
        try:
            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            import queue
            import threading

            accumulated_text = ""

            # Safety check for user message size
            MAX_CHARS = 1_000_000
            if len(user_message) > MAX_CHARS:
                self.logger.warning(f"User message too large ({len(user_message)} chars), truncating")
                user_message = user_message[:MAX_CHARS] + "\n\n[... truncated ...]"

            generation_config = genai.GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens
            )

            # BUG-133 fix: Use system_instruction for proper role separation
            # instead of concatenating system+user prompts (prevents prompt injection)
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_prompt,
                generation_config=generation_config,
            )

            # Use queue to stream chunks from sync thread to async code
            chunk_queue = queue.Queue()
            done_event = threading.Event()
            error_holder = [None]
            usage_holder = [None]  # Capture usage_metadata from response

            def sync_stream():
                """Synchronous streaming in background thread"""
                try:
                    response = model.generate_content(
                        user_message,
                        generation_config=generation_config,
                        stream=True
                    )
                    for chunk in response:
                        if chunk.text:
                            chunk_queue.put(chunk.text)
                    # After full iteration, response accumulates usage_metadata
                    if hasattr(response, 'usage_metadata') and response.usage_metadata:
                        usage_holder[0] = response.usage_metadata
                except Exception as e:
                    error_holder[0] = e
                finally:
                    done_event.set()

            # Start sync streaming in thread pool
            loop = asyncio.get_event_loop()
            executor = ThreadPoolExecutor(max_workers=1)
            loop.run_in_executor(executor, sync_stream)

            # Yield chunks as they arrive
            while not done_event.is_set() or not chunk_queue.empty():
                try:
                    # Non-blocking get with timeout to check done_event
                    text_chunk = chunk_queue.get(timeout=0.01)
                    accumulated_text += text_chunk
                    yield {"type": "token", "content": text_chunk}
                except queue.Empty:
                    await asyncio.sleep(0.01)  # Yield control to event loop

            # Check for errors
            if error_holder[0]:
                raise error_holder[0]

            # Use actual usage_metadata if available, otherwise estimate
            if usage_holder[0]:
                prompt_tokens = getattr(usage_holder[0], 'prompt_token_count', 0) or 0
                completion_tokens = getattr(usage_holder[0], 'candidates_token_count', 0) or 0
                total_tokens = getattr(usage_holder[0], 'total_token_count', 0) or (prompt_tokens + completion_tokens)
            else:
                # Fallback estimation
                prompt_tokens = (len(system_prompt) + len(user_message)) // 4
                completion_tokens = len(accumulated_text) // 4
                total_tokens = prompt_tokens + completion_tokens

            yield {
                "type": "done",
                "token_usage": {
                    "prompt": prompt_tokens,
                    "completion": completion_tokens,
                    "total": total_tokens
                },
                "error": None
            }
        except Exception as e:
            self.logger.error(f"Gemini streaming error: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}

    async def _stream_ollama(self, system_prompt: str, user_message: str, tools: list = None):
        """
        Stream tokens from Ollama local LLM API.

        Note: Uses httpx which provides full async support (async with, async for).
        No thread pool needed - properly async from the start.
        """
        try:
            accumulated_text = ""
            model_lower = self.model_name.lower()
            is_reasoning_model = "deepseek-r1" in model_lower or "r1" in model_lower
            is_tool_calling_model = "tool-calling" in model_lower or "tool_calling" in model_lower

            if is_tool_calling_model:
                num_predict = self.max_tokens if self.max_tokens > 512 else 512
                num_ctx = 2048
            elif is_reasoning_model:
                num_predict = self.max_tokens if self.max_tokens > 1024 else 1024
                num_ctx = 4096
            else:
                num_predict = self.max_tokens if self.max_tokens > 256 else self.max_tokens
                num_ctx = 1024

            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "stream": True,  # Enable streaming
                "options": {
                    "temperature": self.temperature,
                    "top_p": 0.9,
                    "top_k": 40,
                    "num_predict": num_predict,
                    "num_ctx": num_ctx,
                }
            }

            if tools and is_tool_calling_model:
                payload["tools"] = tools

            async with self.client.stream(
                "POST",
                f"{self.ollama_base_url}/api/chat",
                json=payload
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    self.logger.error(f"Ollama streaming error: {response.status_code}")
                    yield {"type": "error", "error": f"Ollama error: {response.status_code}"}
                    return

                prompt_tokens = 0
                completion_tokens = 0

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    try:
                        chunk_data = json.loads(line) if isinstance(line, str) else json.loads(line.decode())

                        # Extract token from message content
                        if "message" in chunk_data:
                            content = chunk_data["message"].get("content", "")
                            if content:
                                accumulated_text += content
                                yield {"type": "token", "content": content}

                        # Check if done
                        if chunk_data.get("done", False):
                            prompt_tokens = chunk_data.get("prompt_eval_count", 0)
                            completion_tokens = chunk_data.get("eval_count", 0)
                            break
                    except json.JSONDecodeError:
                        self.logger.warning(f"Failed to parse Ollama chunk: {line}")
                        continue

                yield {
                    "type": "done",
                    "token_usage": {
                        "prompt": prompt_tokens,
                        "completion": completion_tokens,
                        "total": prompt_tokens + completion_tokens
                    },
                    "error": None
                }
        except httpx.ConnectError:
            yield {"type": "error", "error": "Cannot connect to Ollama"}
        except httpx.TimeoutException:
            yield {"type": "error", "error": f"Timeout streaming from Ollama"}
        except Exception as e:
            self.logger.error(f"Ollama streaming error: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}

    # ==================== Vertex AI Methods ====================

    def _refresh_vertex_token(self):
        """Refresh the Vertex AI OAuth2 access token if expired."""
        if not self._vertex_credentials.valid:
            self._vertex_credentials.refresh(self._vertex_auth_request)
            # Update the OpenAI client's API key with the new token
            if hasattr(self, 'client') and isinstance(self.client, AsyncOpenAI):
                self.client.api_key = self._vertex_credentials.token
            self.logger.debug("Refreshed Vertex AI access token")

    async def _call_vertex_anthropic(self, system_prompt: str, user_message: str) -> Dict:
        """Call Anthropic Claude via Vertex AI rawPredict endpoint."""
        print(f"  📡 Calling Vertex AI (Anthropic): model={self.model_name}, region={self.vertex_region}")

        # Refresh OAuth2 token
        if not self._vertex_credentials.valid:
            self._vertex_credentials.refresh(self._vertex_auth_request)

        # Build the rawPredict URL
        url = (
            f"https://{self.vertex_region}-aiplatform.googleapis.com/v1/"
            f"projects/{self.vertex_project_id}/locations/{self.vertex_region}/"
            f"publishers/anthropic/models/{self.model_name}:rawPredict"
        )

        # Anthropic Messages API format with Vertex-specific version
        payload = {
            "anthropic_version": "vertex-2023-10-16",
            "messages": [
                {"role": "user", "content": user_message}
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": system_prompt,
        }

        headers = {
            "Authorization": f"Bearer {self._vertex_credentials.token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code != 200:
                error_body = response.text[:500]
                self.logger.error(f"Vertex AI Anthropic error {response.status_code}: {error_body}")
                response.raise_for_status()
            data = response.json()

        answer = ""
        if data.get("content"):
            for block in data["content"]:
                if block.get("type") == "text":
                    answer += block["text"]

        token_usage = {
            "prompt": data.get("usage", {}).get("input_tokens", 0),
            "completion": data.get("usage", {}).get("output_tokens", 0),
            "total": data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0),
        }

        return {"answer": answer, "token_usage": token_usage, "error": None}

    async def _call_vertex_raw(self, system_prompt: str, user_message: str) -> Dict:
        """Fallback for unsupported Vertex AI publishers (e.g., MistralAI)."""
        raise ValueError(
            f"Vertex AI publisher '{self.vertex_publisher}' is not yet supported for non-streaming calls. "
            f"Use Google or Anthropic models via Vertex AI."
        )

    async def _stream_vertex_anthropic(self, system_prompt: str, user_message: str):
        """Stream tokens from Anthropic Claude via Vertex AI rawPredict with SSE streaming."""
        print(f"  📡 Streaming Vertex AI (Anthropic): model={self.model_name}")

        if not self._vertex_credentials.valid:
            self._vertex_credentials.refresh(self._vertex_auth_request)

        url = (
            f"https://{self.vertex_region}-aiplatform.googleapis.com/v1/"
            f"projects/{self.vertex_project_id}/locations/{self.vertex_region}/"
            f"publishers/anthropic/models/{self.model_name}:streamRawPredict"
        )

        payload = {
            "anthropic_version": "vertex-2023-10-16",
            "messages": [
                {"role": "user", "content": user_message}
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": system_prompt,
            "stream": True,
        }

        headers = {
            "Authorization": f"Bearer {self._vertex_credentials.token}",
            "Content-Type": "application/json",
        }

        total_tokens = {"prompt": 0, "completion": 0}

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]  # Remove "data: " prefix
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            event = json.loads(data_str)
                            event_type = event.get("type", "")

                            if event_type == "content_block_delta":
                                delta = event.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield {"type": "token", "content": delta["text"]}
                            elif event_type == "message_delta":
                                usage = event.get("usage", {})
                                total_tokens["completion"] = usage.get("output_tokens", 0)
                            elif event_type == "message_start":
                                msg_usage = event.get("message", {}).get("usage", {})
                                total_tokens["prompt"] = msg_usage.get("input_tokens", 0)
                        except json.JSONDecodeError:
                            continue

            yield {
                "type": "done",
                "token_usage": {
                    "prompt": total_tokens["prompt"],
                    "completion": total_tokens["completion"],
                    "total": total_tokens["prompt"] + total_tokens["completion"],
                },
                "error": None,
            }
        except Exception as e:
            self.logger.error(f"Vertex AI Anthropic streaming error: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}
