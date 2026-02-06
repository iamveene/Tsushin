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
    ):
        """
        Initialize AI client with database session for API key loading.

        Args:
            provider: AI provider ('anthropic', 'openai', 'gemini', 'ollama', 'openrouter')
            model_name: Model identifier
            db: Database session for loading API keys (optional, falls back to env vars)
            token_tracker: TokenTracker instance for usage tracking (Phase 7.2)
            temperature: Model temperature (0.0-1.0), defaults to 0.7
            max_tokens: Maximum response tokens, defaults to 2048
            tenant_id: Tenant ID for loading tenant-specific API keys
        """
        self.provider = provider.lower()
        self.model_name = model_name
        self.logger = logging.getLogger(__name__)
        self.db = db
        self.token_tracker = token_tracker
        self.tenant_id = tenant_id
        # Model settings - configurable via playground settings
        self.temperature = temperature if temperature is not None else 0.7
        # BUG FIX 2026-01-17: Increased from 2048 to 16384 to prevent truncation of long responses
        # (e.g., flight search results with multiple options). Most modern LLMs support 8K-128K+ tokens.
        self.max_tokens = max_tokens if max_tokens is not None else 16384

        # Get API key from database or environment (skip for Ollama - Phase 5.2)
        # Priority: DB tenant key → DB system key → env var fallback (handled by get_api_key)
        api_key = None
        if db and provider != 'ollama':
            api_key = get_api_key(self.provider, db, tenant_id=tenant_id)

        # Validate API key for cloud providers
        if provider != 'ollama' and not api_key:
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

        # Run blocking call in thread pool to unblock event loop
        response = await asyncio.to_thread(
            self.client.messages.create,
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

        # Gemini combines system and user prompt
        full_prompt = f"{system_prompt}\n\nUser: {user_message}"

        # Safety check: Gemini 2.5 Pro has ~2M token limit (~8M chars)
        # Truncate if prompt is suspiciously large to prevent 500 errors
        MAX_CHARS = 1_000_000  # 1M chars safety limit
        if len(full_prompt) > MAX_CHARS:
            self.logger.warning(f"Prompt too large ({len(full_prompt)} chars), truncating to {MAX_CHARS}")
            full_prompt = full_prompt[:MAX_CHARS] + "\n\n[... context truncated due to size limits ...]"

        # Configure generation with temperature and max_tokens
        generation_config = genai.GenerationConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens
        )

        # Run blocking call in thread pool to unblock event loop
        response = await asyncio.to_thread(
            self.client.generate_content,
            full_prompt,
            generation_config=generation_config
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

        # Gemini token usage: The current SDK (google.generativeai) doesn't expose token counts
        # Token tracking will work for OpenAI, Anthropic, and Ollama models
        # For Gemini, we estimate based on text length as a workaround
        token_usage = {
            "prompt": 0,
            "completion": 0,
            "total": 0
        }

        # Rough estimation for Gemini (since SDK doesn't provide counts)
        # ~4 characters per token on average
        estimated_prompt = len(full_prompt) // 4
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
            if self.provider == "anthropic":
                async for chunk in self._stream_anthropic(system_prompt, user_message):
                    yield chunk
            elif self.provider == "openai":
                async for chunk in self._stream_openai(system_prompt, user_message):
                    yield chunk
            elif self.provider == "gemini":
                async for chunk in self._stream_gemini(system_prompt, user_message):
                    yield chunk
            elif self.provider == "ollama":
                async for chunk in self._stream_ollama(system_prompt, user_message, tools=tools):
                    yield chunk
            elif self.provider == "openrouter":
                # OpenRouter uses OpenAI-compatible streaming API
                async for chunk in self._stream_openai(system_prompt, user_message):
                    yield chunk
            else:
                yield {
                    "type": "error",
                    "error": f"Unsupported provider: {self.provider}"
                }
                return

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
                stream=True
            )

            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        accumulated_text += delta.content
                        yield {"type": "token", "content": delta.content}

            # OpenAI doesn't provide token counts in streaming mode
            # Estimate based on text length (rough approximation: 4 chars per token)
            estimated_prompt = len(system_prompt + user_message) // 4
            estimated_completion = len(accumulated_text) // 4

            yield {
                "type": "done",
                "token_usage": {
                    "prompt": estimated_prompt,
                    "completion": estimated_completion,
                    "total": estimated_prompt + estimated_completion
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
            full_prompt = f"{system_prompt}\n\nUser: {user_message}"

            # Safety check for prompt size
            MAX_CHARS = 1_000_000
            if len(full_prompt) > MAX_CHARS:
                self.logger.warning(f"Prompt too large ({len(full_prompt)} chars), truncating")
                full_prompt = full_prompt[:MAX_CHARS] + "\n\n[... truncated ...]"

            generation_config = genai.GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens
            )

            # Use queue to stream chunks from sync thread to async code
            chunk_queue = queue.Queue()
            done_event = threading.Event()
            error_holder = [None]

            def sync_stream():
                """Synchronous streaming in background thread"""
                try:
                    response = self.client.generate_content(
                        full_prompt,
                        generation_config=generation_config,
                        stream=True
                    )
                    for chunk in response:
                        if chunk.text:
                            chunk_queue.put(chunk.text)
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

            # Estimate token usage (Gemini SDK doesn't expose counts in streaming)
            estimated_prompt = len(full_prompt) // 4
            estimated_completion = len(accumulated_text) // 4

            yield {
                "type": "done",
                "token_usage": {
                    "prompt": estimated_prompt,
                    "completion": estimated_completion,
                    "total": estimated_prompt + estimated_completion
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
