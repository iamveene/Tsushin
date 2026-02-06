"""
Phase 7.2: Token Usage Tracker
Centralized service for tracking and analyzing token consumption across agents, models, and operations.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
import logging

from models import TokenUsage, Agent, Contact

logger = logging.getLogger(__name__)


# Pricing per 1M tokens (USD) - Updated February 2026
#
# Note on cost tracking:
# - LLM token costs: Tracked per agent message in AgentRun.token_usage_json
# - Audio costs (Whisper/TTS): Tracked in TokenUsage table with operation_type="audio_transcript" or "tts"
# - Embedding costs: Currently using free local model (all-MiniLM-L6-v2), no cost
# - Local models (Ollama): Free, no API costs
# - TTS costs are per 1M characters (converted to "tokens" for unified tracking)
# - O-series models (o1, o3) use "reasoning tokens" that count as output but aren't visible
#
MODEL_PRICING = {
    # OpenAI - GPT-4o series (latest)
    "gpt-4o": {"prompt": 2.5, "completion": 10.0},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "gpt-4o-2024-11-20": {"prompt": 2.5, "completion": 10.0},
    "gpt-4o-2024-08-06": {"prompt": 2.5, "completion": 10.0},
    "gpt-4o-mini-2024-07-18": {"prompt": 0.15, "completion": 0.60},

    # OpenAI - O-series reasoning models (NEW)
    "o1": {"prompt": 15.0, "completion": 60.0},
    "o1-2024-12-17": {"prompt": 15.0, "completion": 60.0},
    "o1-preview": {"prompt": 15.0, "completion": 60.0},
    "o1-preview-2024-09-12": {"prompt": 15.0, "completion": 60.0},
    "o1-mini": {"prompt": 1.10, "completion": 4.40},
    "o1-mini-2024-09-12": {"prompt": 1.10, "completion": 4.40},
    "o3": {"prompt": 2.0, "completion": 8.0},
    "o3-mini": {"prompt": 1.10, "completion": 4.40},
    "o3-mini-2025-01-31": {"prompt": 1.10, "completion": 4.40},

    # OpenAI - GPT-4 series
    "gpt-4": {"prompt": 30.0, "completion": 60.0},
    "gpt-4-turbo": {"prompt": 10.0, "completion": 30.0},
    "gpt-4-turbo-preview": {"prompt": 10.0, "completion": 30.0},

    # OpenAI - GPT-3.5
    "gpt-3.5-turbo": {"prompt": 0.5, "completion": 1.5},
    "gpt-3.5-turbo-0125": {"prompt": 0.5, "completion": 1.5},

    # OpenAI - Audio Transcription (Whisper)
    # $0.006 per second of audio = $6 per 1M seconds (treated as "tokens" for tracking)
    "whisper-1": {"prompt": 6.0, "completion": 0.0},

    # OpenAI - Text-to-Speech (TTS)
    # Costs are per 1M characters (characters treated as "prompt tokens" for tracking)
    "tts-1": {"prompt": 15.0, "completion": 0.0},  # $0.015 per 1K chars = $15 per 1M chars
    "tts-1-hd": {"prompt": 30.0, "completion": 0.0},  # $0.030 per 1K chars = $30 per 1M chars

    # Anthropic - Claude Opus 4.5 series (NEW - latest flagship)
    "claude-opus-4-5-20251101": {"prompt": 5.0, "completion": 25.0},
    "claude-opus-4-5-latest": {"prompt": 5.0, "completion": 25.0},

    # Anthropic - Claude Sonnet 4 series (NEW)
    "claude-sonnet-4-20250514": {"prompt": 3.0, "completion": 15.0},
    "claude-sonnet-4-latest": {"prompt": 3.0, "completion": 15.0},

    # Anthropic - Claude 3.5 series
    "claude-3-5-sonnet-20241022": {"prompt": 3.0, "completion": 15.0},
    "claude-3-5-sonnet-latest": {"prompt": 3.0, "completion": 15.0},
    "claude-3-5-haiku-20241022": {"prompt": 0.80, "completion": 4.0},

    # Anthropic - Claude Haiku 4.5 (NEW - faster, cheaper)
    "claude-haiku-4-5-20251022": {"prompt": 1.0, "completion": 5.0},
    "claude-haiku-4-5-latest": {"prompt": 1.0, "completion": 5.0},

    # Anthropic - Claude 3 series (legacy)
    "claude-3-opus-20240229": {"prompt": 15.0, "completion": 75.0},
    "claude-3-opus-latest": {"prompt": 15.0, "completion": 75.0},
    "claude-3-sonnet-20240229": {"prompt": 3.0, "completion": 15.0},
    "claude-3-haiku-20240307": {"prompt": 0.25, "completion": 1.25},

    # Google Gemini 2.5 series (UPDATED prices)
    "gemini-2.5-pro": {"prompt": 1.25, "completion": 10.0},  # Updated: output was 5.0
    "gemini-2.5-pro-preview-05-06": {"prompt": 1.25, "completion": 10.0},
    "gemini-2.5-pro-preview-03-25": {"prompt": 1.25, "completion": 10.0},
    "gemini-2.5-flash": {"prompt": 0.30, "completion": 2.50},  # Updated: was 0.075/0.3
    "gemini-2.5-flash-preview-05-20": {"prompt": 0.30, "completion": 2.50},
    "gemini-2.5-flash-lite": {"prompt": 0.10, "completion": 0.40},  # NEW - most affordable

    # Google Gemini 2.0 series
    "gemini-2.0-flash": {"prompt": 0.10, "completion": 0.40},
    "gemini-2.0-flash-exp": {"prompt": 0.0, "completion": 0.0},  # Free tier (legacy)

    # Google Gemini Image Generation (Nano Banana)
    # Pricing: ~$0.02-0.04 per image (represented as per-operation cost)
    "gemini-2.5-flash-image": {"prompt": 20.0, "completion": 0.0},  # Nano Banana - $0.02/image
    "gemini-3-pro-image-preview": {"prompt": 40.0, "completion": 0.0},  # Nano Banana Pro - $0.04/image

    # Google Gemini 1.5 series (legacy)
    "gemini-1.5-pro": {"prompt": 1.25, "completion": 5.0},
    "gemini-1.5-flash": {"prompt": 0.075, "completion": 0.3},
    "gemini-exp-1206": {"prompt": 0.0, "completion": 0.0},  # Free experimental

    # Kokoro TTS (local, free)
    "kokoro": {"prompt": 0.0, "completion": 0.0},

    # ElevenLabs TTS
    # $0.03 per 1K chars = $30 per 1M chars
    "elevenlabs": {"prompt": 30.0, "completion": 0.0},

    # ============================================================
    # OpenRouter models (provider/model format)
    # OpenRouter adds ~5% markup to base provider costs
    # ============================================================

    # OpenRouter - Google Gemini
    "google/gemini-2.5-flash": {"prompt": 0.30, "completion": 2.50},
    "google/gemini-2.5-flash-preview-05-20": {"prompt": 0.30, "completion": 2.50},
    "google/gemini-2.5-pro": {"prompt": 1.25, "completion": 10.0},
    "google/gemini-2.5-pro-preview-05-06": {"prompt": 1.25, "completion": 10.0},
    "google/gemini-2.0-flash": {"prompt": 0.10, "completion": 0.40},
    "google/gemini-2.0-flash-exp:free": {"prompt": 0.0, "completion": 0.0},
    "google/gemini-1.5-flash": {"prompt": 0.075, "completion": 0.3},
    "google/gemini-1.5-pro": {"prompt": 1.25, "completion": 5.0},

    # OpenRouter - Anthropic Claude
    "anthropic/claude-3.5-haiku": {"prompt": 0.80, "completion": 4.0},
    "anthropic/claude-3-5-haiku-20241022": {"prompt": 0.80, "completion": 4.0},
    "anthropic/claude-3.5-sonnet": {"prompt": 3.0, "completion": 15.0},
    "anthropic/claude-3-5-sonnet-20241022": {"prompt": 3.0, "completion": 15.0},
    "anthropic/claude-3-opus": {"prompt": 15.0, "completion": 75.0},

    # OpenRouter - OpenAI
    "openai/gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "openai/gpt-4o-mini-2024-07-18": {"prompt": 0.15, "completion": 0.60},
    "openai/gpt-4o": {"prompt": 2.5, "completion": 10.0},
    "openai/gpt-4o-2024-11-20": {"prompt": 2.5, "completion": 10.0},
    "openai/gpt-4-turbo": {"prompt": 10.0, "completion": 30.0},
    "openai/o1": {"prompt": 15.0, "completion": 60.0},
    "openai/o1-mini": {"prompt": 1.10, "completion": 4.40},
    "openai/o3-mini": {"prompt": 1.10, "completion": 4.40},

    # OpenRouter - Meta Llama (free tier)
    "meta-llama/llama-3.1-8b-instruct:free": {"prompt": 0.0, "completion": 0.0},
    "meta-llama/llama-3.2-3b-instruct:free": {"prompt": 0.0, "completion": 0.0},
    "meta-llama/llama-3.1-70b-instruct:free": {"prompt": 0.0, "completion": 0.0},

    # OpenRouter - DeepSeek
    "deepseek/deepseek-r1:free": {"prompt": 0.0, "completion": 0.0},
    "deepseek/deepseek-chat": {"prompt": 0.14, "completion": 0.28},
    "deepseek/deepseek-r1": {"prompt": 0.55, "completion": 2.19},

    # OpenRouter - Qwen
    "qwen/qwen-2.5-72b-instruct:free": {"prompt": 0.0, "completion": 0.0},
    "qwen/qwen-2.5-coder-32b-instruct:free": {"prompt": 0.0, "completion": 0.0},

    # OpenRouter - Mistral
    "mistralai/mistral-7b-instruct:free": {"prompt": 0.0, "completion": 0.0},
    "mistralai/mixtral-8x7b-instruct:free": {"prompt": 0.0, "completion": 0.0},

    # ============================================================
    # DeepSeek API (direct, not via OpenRouter)
    # ============================================================
    "deepseek-chat": {"prompt": 0.14, "completion": 0.28},
    "deepseek-reasoner": {"prompt": 0.55, "completion": 2.19},

    # Ollama (local, free - no API costs)
    "llama3.2": {"prompt": 0.0, "completion": 0.0},
    "llama3.1": {"prompt": 0.0, "completion": 0.0},
    "llama3": {"prompt": 0.0, "completion": 0.0},
    "mistral": {"prompt": 0.0, "completion": 0.0},
    "mixtral": {"prompt": 0.0, "completion": 0.0},
    "qwen2.5": {"prompt": 0.0, "completion": 0.0},
    "codellama": {"prompt": 0.0, "completion": 0.0},
    "deepseek-r1": {"prompt": 0.0, "completion": 0.0},  # Local reasoning model

    # Embeddings (using free local model by default)
    # If using OpenAI embeddings in the future:
    # "text-embedding-3-small": {"prompt": 0.02, "completion": 0.0},  # $0.02 per 1M tokens
    # "text-embedding-3-large": {"prompt": 0.13, "completion": 0.0},  # $0.13 per 1M tokens
    # "text-embedding-ada-002": {"prompt": 0.10, "completion": 0.0},  # $0.10 per 1M tokens
}


class TokenTracker:
    """Centralized token tracking and analytics service."""

    def __init__(self, db: Session, tenant_id: Optional[str] = None):
        self.db = db
        self.tenant_id = tenant_id
        self._pricing_cache: Dict[str, Dict[str, float]] = {}  # Cache for DB pricing

    def track_usage(
        self,
        operation_type: str,
        model_provider: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        agent_id: Optional[int] = None,
        agent_run_id: Optional[int] = None,
        skill_type: Optional[str] = None,
        sender_key: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> TokenUsage:
        """
        Track token usage for an operation.

        Args:
            operation_type: Type of operation (message_processing, audio_transcript, skill_classification, etc.)
            model_provider: Provider name (openai, anthropic, gemini, ollama)
            model_name: Specific model name
            prompt_tokens: Input tokens consumed
            completion_tokens: Output tokens generated
            agent_id: Agent that performed the operation
            agent_run_id: Associated agent run ID
            skill_type: Skill that used the tokens
            sender_key: User who triggered the operation
            message_id: MCP message ID

        Returns:
            TokenUsage: Created usage record
        """
        total_tokens = prompt_tokens + completion_tokens
        estimated_cost = self._calculate_cost(model_name, prompt_tokens, completion_tokens, model_provider)

        usage = TokenUsage(
            agent_id=agent_id,
            agent_run_id=agent_run_id,
            operation_type=operation_type,
            skill_type=skill_type,
            model_provider=model_provider,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
            sender_key=sender_key,
            message_id=message_id,
        )

        self.db.add(usage)
        self.db.commit()

        logger.info(
            f"Token usage tracked: {operation_type} | {model_provider}/{model_name} | "
            f"Tokens: {total_tokens} (P:{prompt_tokens} C:{completion_tokens}) | "
            f"Cost: ${estimated_cost:.6f}"
        )

        return usage

    def _calculate_cost(self, model_name: str, prompt_tokens: int, completion_tokens: int, model_provider: Optional[str] = None) -> float:
        """
        Calculate estimated cost in USD based on model pricing.

        First checks for tenant-specific pricing in the database,
        then falls back to system default pricing (MODEL_PRICING).
        """
        pricing = self._get_pricing(model_name, model_provider)
        if not pricing:
            logger.debug(f"No pricing data for model: {model_name}, defaulting to $0")
            return 0.0

        prompt_cost = (prompt_tokens / 1_000_000) * pricing.get("prompt", 0)
        completion_cost = (completion_tokens / 1_000_000) * pricing.get("completion", 0)

        return prompt_cost + completion_cost

    def _get_pricing(self, model_name: str, model_provider: Optional[str] = None) -> Optional[Dict[str, float]]:
        """
        Get pricing for a model with intelligent fallback.

        Lookup order:
        1. Exact match in cache/DB/defaults
        2. Strip provider prefix (google/gemini-2.5-flash -> gemini-2.5-flash)
        3. Strip :free suffix and return $0 pricing for free-tier models
        4. Try base model name without version suffix (gpt-4o-2024-08-06 -> gpt-4o)

        Uses caching to avoid repeated lookups.
        """
        cache_key = f"{model_provider or 'unknown'}:{model_name}"

        # Check cache first (covers all previous lookups including fallbacks)
        if cache_key in self._pricing_cache:
            return self._pricing_cache[cache_key]

        # Strategy 1: Try exact match
        pricing = self._lookup_pricing_direct(model_name, model_provider)
        if pricing:
            self._pricing_cache[cache_key] = pricing
            return pricing

        # Strategy 2: Try without provider prefix (OpenRouter format: provider/model)
        if '/' in model_name:
            base_model = model_name.split('/')[-1]
            pricing = self._lookup_pricing_direct(base_model, model_provider)
            if pricing:
                self._pricing_cache[cache_key] = pricing
                logger.debug(f"Fallback pricing for {model_name} -> {base_model}")
                return pricing

        # Strategy 3: Handle :free suffix - these should always be $0
        if ':free' in model_name:
            # Free-tier models should have zero cost regardless of base model pricing
            free_pricing = {"prompt": 0.0, "completion": 0.0}
            self._pricing_cache[cache_key] = free_pricing
            logger.debug(f"Free-tier model detected: {model_name}")
            return free_pricing

        # Strategy 4: Try without date/version suffix (gpt-4o-2024-08-06 -> gpt-4o)
        # Look for patterns like -YYYY-MM-DD or -latest at the end
        import re
        base_name_match = re.sub(r'(-\d{4}-\d{2}-\d{2}|-latest|-preview.*|:\w+)$', '', model_name)
        if base_name_match != model_name:
            pricing = self._lookup_pricing_direct(base_name_match, model_provider)
            if pricing:
                self._pricing_cache[cache_key] = pricing
                logger.debug(f"Version fallback pricing for {model_name} -> {base_name_match}")
                return pricing

        # No pricing found
        logger.debug(f"No pricing data for model: {model_name} (provider: {model_provider})")
        return None

    def _lookup_pricing_direct(self, model_name: str, model_provider: Optional[str] = None) -> Optional[Dict[str, float]]:
        """
        Direct pricing lookup without fallback strategies.
        Checks tenant-specific DB pricing first, then hardcoded defaults.
        """
        # Try tenant-specific pricing from database
        if self.tenant_id and self.db:
            try:
                from models import ModelPricing
                db_pricing = self.db.query(ModelPricing).filter(
                    ModelPricing.tenant_id == self.tenant_id,
                    ModelPricing.model_name == model_name,
                    ModelPricing.is_active == True
                ).first()

                if db_pricing:
                    return {
                        "prompt": db_pricing.input_cost_per_million,
                        "completion": db_pricing.output_cost_per_million
                    }
            except Exception as e:
                logger.debug(f"Could not load DB pricing for {model_name}: {e}")

        # Fall back to hardcoded default pricing
        return MODEL_PRICING.get(model_name)

    def clear_pricing_cache(self):
        """Clear the pricing cache (useful after pricing updates)."""
        self._pricing_cache.clear()

    def get_total_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Get overall token usage statistics.

        Args:
            days: Number of days to look back

        Returns:
            Dict with total_tokens, total_cost, operation_breakdown, model_breakdown
        """
        since = datetime.utcnow() - timedelta(days=days)

        usages = self.db.query(TokenUsage).filter(TokenUsage.created_at >= since).all()

        if not usages:
            return {
                "total_tokens": 0,
                "total_cost": 0.0,
                "total_requests": 0,
                "operation_breakdown": [],
                "model_breakdown": [],
                "daily_trend": [],
            }

        total_tokens = sum(u.total_tokens for u in usages)
        total_cost = sum(u.estimated_cost for u in usages)

        # Operation breakdown
        operation_stats = {}
        for u in usages:
            key = u.operation_type
            if key not in operation_stats:
                operation_stats[key] = {"tokens": 0, "cost": 0.0, "count": 0}
            operation_stats[key]["tokens"] += u.total_tokens
            operation_stats[key]["cost"] += u.estimated_cost
            operation_stats[key]["count"] += 1

        operation_breakdown = [
            {"operation": k, **v}
            for k, v in sorted(operation_stats.items(), key=lambda x: x[1]["cost"], reverse=True)
        ]

        # Model breakdown
        model_stats = {}
        for u in usages:
            key = f"{u.model_provider}/{u.model_name}"
            if key not in model_stats:
                model_stats[key] = {"tokens": 0, "cost": 0.0, "count": 0}
            model_stats[key]["tokens"] += u.total_tokens
            model_stats[key]["cost"] += u.estimated_cost
            model_stats[key]["count"] += 1

        model_breakdown = [
            {"model": k, **v}
            for k, v in sorted(model_stats.items(), key=lambda x: x[1]["cost"], reverse=True)
        ]

        # Daily trend
        daily_stats = {}
        for u in usages:
            day = u.created_at.date().isoformat()
            if day not in daily_stats:
                daily_stats[day] = {"tokens": 0, "cost": 0.0, "count": 0}
            daily_stats[day]["tokens"] += u.total_tokens
            daily_stats[day]["cost"] += u.estimated_cost
            daily_stats[day]["count"] += 1

        daily_trend = [
            {"date": k, **v}
            for k, v in sorted(daily_stats.items())
        ]

        return {
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "total_requests": len(usages),
            "operation_breakdown": operation_breakdown,
            "model_breakdown": model_breakdown,
            "daily_trend": daily_trend,
        }

    def get_agent_stats(self, agent_id: int, days: int = 30) -> Dict[str, Any]:
        """
        Get token usage statistics for a specific agent.

        Args:
            agent_id: Agent ID
            days: Number of days to look back

        Returns:
            Dict with agent-specific statistics
        """
        since = datetime.utcnow() - timedelta(days=days)

        usages = self.db.query(TokenUsage).filter(
            TokenUsage.agent_id == agent_id,
            TokenUsage.created_at >= since
        ).all()

        if not usages:
            return {
                "agent_id": agent_id,
                "total_tokens": 0,
                "total_cost": 0.0,
                "total_requests": 0,
                "skill_breakdown": [],
                "model_breakdown": [],
            }

        total_tokens = sum(u.total_tokens for u in usages)
        total_cost = sum(u.estimated_cost for u in usages)

        # Skill breakdown
        skill_stats = {}
        for u in usages:
            key = u.skill_type or "general"
            if key not in skill_stats:
                skill_stats[key] = {"tokens": 0, "cost": 0.0, "count": 0}
            skill_stats[key]["tokens"] += u.total_tokens
            skill_stats[key]["cost"] += u.estimated_cost
            skill_stats[key]["count"] += 1

        skill_breakdown = [
            {"skill": k, **v}
            for k, v in sorted(skill_stats.items(), key=lambda x: x[1]["cost"], reverse=True)
        ]

        # Model breakdown
        model_stats = {}
        for u in usages:
            key = f"{u.model_provider}/{u.model_name}"
            if key not in model_stats:
                model_stats[key] = {"tokens": 0, "cost": 0.0, "count": 0}
            model_stats[key]["tokens"] += u.total_tokens
            model_stats[key]["cost"] += u.estimated_cost
            model_stats[key]["count"] += 1

        model_breakdown = [
            {"model": k, **v}
            for k, v in sorted(model_stats.items(), key=lambda x: x[1]["cost"], reverse=True)
        ]

        return {
            "agent_id": agent_id,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "total_requests": len(usages),
            "skill_breakdown": skill_breakdown,
            "model_breakdown": model_breakdown,
        }

    def get_all_agents_summary(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get token usage summary for all agents.

        Args:
            days: Number of days to look back

        Returns:
            List of agent summaries sorted by cost
        """
        since = datetime.utcnow() - timedelta(days=days)

        # Query agent usage grouped
        results = self.db.query(
            TokenUsage.agent_id,
            func.sum(TokenUsage.total_tokens).label("total_tokens"),
            func.sum(TokenUsage.estimated_cost).label("total_cost"),
            func.count(TokenUsage.id).label("total_requests"),
        ).filter(
            TokenUsage.created_at >= since,
            TokenUsage.agent_id.isnot(None)
        ).group_by(
            TokenUsage.agent_id
        ).order_by(
            desc("total_cost")
        ).all()

        summaries = []
        for row in results:
            agent = self.db.query(Agent).filter(Agent.id == row.agent_id).first()
            if agent:
                contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
                agent_name = contact.friendly_name if contact else f"Agent {agent.id}"
            else:
                agent_name = f"Agent {row.agent_id}"

            summaries.append({
                "agent_id": row.agent_id,
                "agent_name": agent_name,
                "total_tokens": row.total_tokens,
                "total_cost": float(row.total_cost),
                "total_requests": row.total_requests,
            })

        return summaries

    def get_recent_usage(self, limit: int = 100, agent_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get recent token usage records.

        Args:
            limit: Maximum number of records
            agent_id: Filter by agent (optional)

        Returns:
            List of recent usage records
        """
        query = self.db.query(TokenUsage).order_by(desc(TokenUsage.created_at)).limit(limit)

        if agent_id:
            query = query.filter(TokenUsage.agent_id == agent_id)

        usages = query.all()

        records = []
        for u in usages:
            agent_name = "System"
            if u.agent_id:
                agent = self.db.query(Agent).filter(Agent.id == u.agent_id).first()
                if agent:
                    contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
                    agent_name = contact.friendly_name if contact else f"Agent {agent.id}"

            records.append({
                "id": u.id,
                "timestamp": u.created_at.isoformat(),
                "agent_name": agent_name,
                "operation_type": u.operation_type,
                "skill_type": u.skill_type,
                "model": f"{u.model_provider}/{u.model_name}",
                "total_tokens": u.total_tokens,
                "estimated_cost": u.estimated_cost,
            })

        return records
