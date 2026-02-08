"""
Sentinel Security Profiles — Performance Benchmarks

Benchmarks for profile resolution, cache performance, and full analysis pipeline.
Uses in-memory SQLite with mocked LLM calls.

Performance SLAs:
- Cold cache resolution: < 50ms per call
- Hot cache resolution: < 1ms per call
- Cache invalidation + rebuild: < 50ms
- 50 agents cold total: < 2500ms
- 50 agents hot total: < 50ms
- Full pipeline with mock LLM: < 500ms
"""

import pytest
import time
import json
import sys
import os
from unittest.mock import AsyncMock, patch

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, SentinelProfile, SentinelProfileAssignment
from services.sentinel_service import SentinelService
from services.sentinel_profiles_service import SentinelProfilesService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clear_profile_cache():
    """Clear the class-level profile cache before each test."""
    SentinelProfilesService._profile_cache.clear()
    yield
    SentinelProfilesService._profile_cache.clear()


@pytest.fixture
def db_engine():
    """Create in-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create a database session for testing."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def tenant_id():
    return "bench-tenant"


@pytest.fixture
def system_profiles(db_session):
    """Seed the 4 system profiles."""
    profiles = [
        SentinelProfile(
            id=1, name="Off", slug="off", tenant_id=None,
            is_system=True, is_default=False,
            is_enabled=False, detection_mode="off", aggressiveness_level=0,
            detection_overrides="{}",
        ),
        SentinelProfile(
            id=2, name="Permissive", slug="permissive", tenant_id=None,
            is_system=True, is_default=False,
            is_enabled=True, detection_mode="detect_only", aggressiveness_level=1,
            detection_overrides="{}",
        ),
        SentinelProfile(
            id=3, name="Moderate", slug="moderate", tenant_id=None,
            is_system=True, is_default=True,
            is_enabled=True, detection_mode="block", aggressiveness_level=1,
            detection_overrides="{}",
        ),
        SentinelProfile(
            id=4, name="Aggressive", slug="aggressive", tenant_id=None,
            is_system=True, is_default=False,
            is_enabled=True, detection_mode="block", aggressiveness_level=3,
            detection_overrides="{}",
        ),
    ]
    for p in profiles:
        db_session.add(p)
    db_session.commit()
    return profiles


def _assign(db_session, tenant_id, profile_id, agent_id=None, skill_type=None):
    """Helper to create a profile assignment."""
    a = SentinelProfileAssignment(
        tenant_id=tenant_id, agent_id=agent_id,
        skill_type=skill_type, profile_id=profile_id,
    )
    db_session.add(a)
    db_session.commit()
    return a


def _measure(fn, iterations, clear_cache=False):
    """Run fn() multiple times and return timing stats in milliseconds."""
    times = []
    for _ in range(iterations):
        if clear_cache:
            SentinelProfilesService._profile_cache.clear()
        start = time.perf_counter()
        fn()
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)

    times.sort()
    n = len(times)
    return {
        "avg": sum(times) / n,
        "p50": times[n // 2],
        "p95": times[int(n * 0.95)],
        "max": times[-1],
        "total": sum(times),
    }


# =============================================================================
# Benchmark 1: Cold Cache Resolution
# =============================================================================


class TestColdCacheResolution:
    """Benchmark cold cache profile resolution (DB queries on every call)."""

    def test_cold_cache_system_default_fallback(
        self, db_session, tenant_id, system_profiles
    ):
        """Cold cache: no assignments, falls through to system default (~7 queries)."""
        service = SentinelProfilesService(db_session, tenant_id)

        def resolve():
            config = service.get_effective_config(agent_id=999, skill_type="shell")
            assert config is not None
            assert config.profile_name == "Moderate"

        stats = _measure(resolve, iterations=100, clear_cache=True)

        print(
            f"\n  Cold cache (system default): "
            f"avg={stats['avg']:.2f}ms, p95={stats['p95']:.2f}ms, max={stats['max']:.2f}ms"
        )
        assert stats["avg"] < 50, f"Cold cache avg {stats['avg']:.2f}ms exceeds 50ms SLA"

    def test_cold_cache_skill_level_hit(
        self, db_session, tenant_id, system_profiles
    ):
        """Cold cache: skill-level profile assigned (~2 queries, best case)."""
        agent_id = 500
        _assign(db_session, tenant_id, profile_id=4, agent_id=agent_id, skill_type="shell")

        service = SentinelProfilesService(db_session, tenant_id)

        def resolve():
            config = service.get_effective_config(agent_id=agent_id, skill_type="shell")
            assert config is not None
            assert config.profile_name == "Aggressive"

        stats = _measure(resolve, iterations=100, clear_cache=True)

        print(
            f"\n  Cold cache (skill hit): "
            f"avg={stats['avg']:.2f}ms, p95={stats['p95']:.2f}ms, max={stats['max']:.2f}ms"
        )
        assert stats["avg"] < 50, f"Cold cache avg {stats['avg']:.2f}ms exceeds 50ms SLA"


# =============================================================================
# Benchmark 2: Hot Cache Resolution
# =============================================================================


class TestHotCacheResolution:
    """Benchmark hot cache profile resolution (pure dict lookup, 0 DB queries)."""

    def test_hot_cache_dict_lookup(self, db_session, tenant_id, system_profiles):
        """Hot cache: profile already cached. 0 queries, pure dict lookup."""
        service = SentinelProfilesService(db_session, tenant_id)

        # Warm the cache
        service.get_effective_config(agent_id=1)

        def resolve():
            config = service.get_effective_config(agent_id=1)
            assert config is not None

        stats = _measure(resolve, iterations=10000, clear_cache=False)

        print(
            f"\n  Hot cache (10K iters): "
            f"avg={stats['avg']:.4f}ms, p95={stats['p95']:.4f}ms, max={stats['max']:.4f}ms"
        )
        assert stats["avg"] < 1.0, f"Hot cache avg {stats['avg']:.4f}ms exceeds 1ms SLA"


# =============================================================================
# Benchmark 3: Cache Invalidation + Rebuild
# =============================================================================


class TestCacheInvalidation:
    """Benchmark cache clear + rebuild cycle."""

    def test_invalidation_and_rebuild(self, db_session, tenant_id, system_profiles):
        """Measure: clear cache + single rebuild cost."""
        service = SentinelProfilesService(db_session, tenant_id)

        def invalidate_and_rebuild():
            SentinelProfilesService._profile_cache.clear()
            config = service.get_effective_config(agent_id=1)
            assert config is not None

        # Warm once first
        service.get_effective_config(agent_id=1)

        stats = _measure(invalidate_and_rebuild, iterations=50, clear_cache=False)

        print(
            f"\n  Cache invalidation + rebuild: "
            f"avg={stats['avg']:.2f}ms, p95={stats['p95']:.2f}ms, max={stats['max']:.2f}ms"
        )
        assert stats["avg"] < 50, f"Invalidation+rebuild avg {stats['avg']:.2f}ms exceeds 50ms SLA"


# =============================================================================
# Benchmark 4: Scale Test (50+ agents)
# =============================================================================


class TestScalePerformance:
    """Benchmark profile resolution at scale with many agents."""

    def test_many_agents_resolution(self, db_session, tenant_id, system_profiles):
        """Resolve effective config for 50 agents with varied assignments."""
        agents = []
        for i in range(50):
            agent_id = 1000 + i
            agents.append(agent_id)
            if i % 3 == 0:
                _assign(db_session, tenant_id, profile_id=4, agent_id=agent_id)  # Aggressive
            elif i % 3 == 1:
                _assign(db_session, tenant_id, profile_id=2, agent_id=agent_id)  # Permissive
            # else: no assignment, falls through to system default

        service = SentinelProfilesService(db_session, tenant_id)

        # Cold: resolve all 50
        SentinelProfilesService._profile_cache.clear()
        start = time.perf_counter()
        for agent_id in agents:
            config = service.get_effective_config(agent_id=agent_id)
            assert config is not None
        cold_total = (time.perf_counter() - start) * 1000

        # Hot: resolve all 50 again (cached)
        start = time.perf_counter()
        for agent_id in agents:
            config = service.get_effective_config(agent_id=agent_id)
            assert config is not None
        hot_total = (time.perf_counter() - start) * 1000

        print(
            f"\n  50 agents cold: {cold_total:.2f}ms total ({cold_total / 50:.2f}ms/agent)"
        )
        print(
            f"  50 agents hot:  {hot_total:.2f}ms total ({hot_total / 50:.4f}ms/agent)"
        )

        assert cold_total < 2500, f"50-agent cold {cold_total:.2f}ms exceeds 2500ms SLA"
        assert hot_total < 50, f"50-agent hot {hot_total:.2f}ms exceeds 50ms SLA"


# =============================================================================
# Benchmark 5: Full Analysis Pipeline
# =============================================================================


class TestFullPipelineBenchmark:
    """Benchmark the full analyze_prompt pipeline with mocked LLM."""

    @pytest.mark.asyncio
    async def test_full_pipeline_mocked_llm(
        self, db_session, tenant_id, system_profiles
    ):
        """Full pipeline: get_effective_config + analyze_prompt (mocked LLM)."""
        service = SentinelService(db_session, tenant_id)

        mock_response = {
            "answer": json.dumps({
                "threat_type": "none",
                "score": 0.05,
                "reason": "Normal message",
            })
        }

        with patch.object(service, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response

            times = []
            for _ in range(20):
                SentinelProfilesService._profile_cache.clear()
                start = time.perf_counter()
                result = await service.analyze_prompt(
                    prompt="What time is it?",
                    agent_id=1,
                    source=None,
                )
                elapsed = (time.perf_counter() - start) * 1000
                times.append(elapsed)
                assert result.action == "allowed"

            times.sort()
            avg_ms = sum(times) / len(times)
            p95_ms = times[int(len(times) * 0.95)]

            print(
                f"\n  Full pipeline (mocked LLM, 20 iters): "
                f"avg={avg_ms:.2f}ms, p95={p95_ms:.2f}ms"
            )
            assert avg_ms < 500, f"Full pipeline avg {avg_ms:.2f}ms exceeds 500ms SLA"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
