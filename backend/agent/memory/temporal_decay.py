"""
Temporal Memory Decay - Item 37
Applies exponential decay to memory relevance scores based on time since last access.
Includes MMR (Maximum Marginal Relevance) reranking for diversity.
"""

import math
import numpy as np
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class DecayConfig:
    """Configuration for temporal decay behavior."""
    enabled: bool = False
    decay_lambda: float = 0.01        # Exponential decay rate (0.01 ~ 69-day half-life)
    archive_threshold: float = 0.05   # Auto-archive below 5%
    mmr_lambda: float = 0.5           # MMR diversity weight (0=max diversity, 1=pure relevance)

    @staticmethod
    def _coalesce(value, default):
        """Return value if not None, else default."""
        return value if value is not None else default

    @staticmethod
    def from_agent(agent) -> 'DecayConfig':
        c = DecayConfig._coalesce
        return DecayConfig(
            enabled=bool(c(getattr(agent, 'memory_decay_enabled', None), False)),
            decay_lambda=c(getattr(agent, 'memory_decay_lambda', None), 0.01),
            archive_threshold=c(getattr(agent, 'memory_decay_archive_threshold', None), 0.05),
            mmr_lambda=c(getattr(agent, 'memory_decay_mmr_lambda', None), 0.5),
        )

    @staticmethod
    def from_config_dict(config: dict) -> 'DecayConfig':
        c = DecayConfig._coalesce
        return DecayConfig(
            enabled=bool(c(config.get('memory_decay_enabled'), False)),
            decay_lambda=c(config.get('memory_decay_lambda'), 0.01),
            archive_threshold=c(config.get('memory_decay_archive_threshold'), 0.05),
            mmr_lambda=c(config.get('memory_decay_mmr_lambda'), 0.5),
        )


def compute_decay_factor(days_since_access: float, decay_lambda: float) -> float:
    """Exponential decay: e^(-lambda * days). Returns [0.0, 1.0]."""
    decay_lambda = max(0.0, decay_lambda)
    if days_since_access <= 0:
        return 1.0
    result = math.exp(-decay_lambda * days_since_access)
    return min(1.0, max(0.0, result))


def apply_decay_to_score(raw_score: float, last_accessed_at: Optional[datetime],
                          now: Optional[datetime], decay_lambda: float) -> float:
    """Multiply raw_score by decay factor. Handles None gracefully."""
    if last_accessed_at is None or now is None:
        return raw_score
    la = last_accessed_at.replace(tzinfo=None) if last_accessed_at.tzinfo else last_accessed_at
    n = now.replace(tzinfo=None) if now.tzinfo else now
    days = max(0, (n - la).total_seconds() / 86400.0)
    return max(0.0, min(1.0, raw_score * compute_decay_factor(days, decay_lambda)))


def apply_decay_to_confidence(confidence: float, last_accessed_at: Optional[datetime],
                               now: Optional[datetime], decay_lambda: float) -> float:
    """For facts: effective_confidence = confidence * decay_factor."""
    return apply_decay_to_score(confidence, last_accessed_at, now, decay_lambda)


def compute_freshness_label(last_accessed_at: Optional[datetime], now: Optional[datetime],
                             decay_lambda: float, archive_threshold: float = 0.05) -> Dict:
    """Returns freshness metadata."""
    if last_accessed_at is None or now is None:
        return {'decay_factor': 1.0, 'freshness': 'fresh', 'days_since_access': 0}

    la = last_accessed_at.replace(tzinfo=None) if last_accessed_at.tzinfo else last_accessed_at
    n = now.replace(tzinfo=None) if now.tzinfo else now
    days = max(0, (n - la).total_seconds() / 86400.0)
    factor = compute_decay_factor(days, decay_lambda)

    if factor > 0.7:
        label = 'fresh'
    elif factor > 0.3:
        label = 'fading'
    elif factor > archive_threshold:
        label = 'stale'
    else:
        label = 'archived'

    return {'decay_factor': round(factor, 4), 'freshness': label, 'days_since_access': round(days, 1)}


def should_archive(decayed_score: float, archive_threshold: float) -> bool:
    """Check if a memory entry should be archived."""
    return decayed_score < archive_threshold


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    a_arr = np.array(a, dtype=np.float32)
    b_arr = np.array(b, dtype=np.float32)
    dot = np.dot(a_arr, b_arr)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def mmr_rerank(
    candidates: List[Dict],
    query_embedding: List[float],
    mmr_lambda: float = 0.5,
    top_k: int = 5
) -> List[Dict]:
    """
    Maximum Marginal Relevance reranking.
    Each candidate must have 'embedding' (list of floats) and 'decayed_score' fields.
    Returns top_k candidates balancing relevance and diversity.
    """
    mmr_lambda = max(0.0, min(1.0, mmr_lambda))
    if not candidates:
        return []
    if len(candidates) <= top_k:
        return sorted(candidates, key=lambda c: c.get('decayed_score', 0), reverse=True)

    selected = []
    remaining = list(candidates)

    # Start with the highest scored candidate
    remaining.sort(key=lambda c: c.get('decayed_score', 0), reverse=True)
    selected.append(remaining.pop(0))

    while len(selected) < top_k and remaining:
        best_score = -float('inf')
        best_idx = 0

        for i, candidate in enumerate(remaining):
            cand_emb = candidate.get('embedding', [])

            if not cand_emb:
                # No embedding available — fall back to decayed_score only
                mmr_score = candidate.get('decayed_score', 0)
            else:
                # Relevance: similarity to query
                relevance = _cosine_similarity(cand_emb, query_embedding)

                # Diversity: max similarity to already selected
                selected_with_emb = [s for s in selected if s.get('embedding')]
                max_sim_to_selected = max(
                    _cosine_similarity(cand_emb, s['embedding'])
                    for s in selected_with_emb
                ) if selected_with_emb else 0.0

                # MMR score
                mmr_score = mmr_lambda * relevance - (1 - mmr_lambda) * max_sim_to_selected

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = i

        selected.append(remaining.pop(best_idx))

    return selected
