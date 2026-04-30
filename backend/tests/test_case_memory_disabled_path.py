"""v0.7.x — case-memory disabled-path tests retired.

The original tests in this file asserted that with
``TSN_CASE_MEMORY_ENABLED=false``, terminal trigger-driven runs did not
enqueue ``case_index`` jobs and the ``find_similar_past_cases`` skill was
not registered.

The global env flag has been removed in v0.7.x — the case-memory
subsystem is always active. Per-trigger opt-in lives on
``TriggerRecapConfig.enabled`` and per-tenant routing lives on
``Agent.vector_store_instance_id``. The disabled-path equivalents are now:

  - ``test_trigger_recap_service.test_build_recap_returns_none_when_config_missing``
  - ``test_trigger_recap_service.test_build_recap_returns_none_when_disabled``

This file is preserved (as an empty test module) so historical references
to it in changelogs and docs continue to resolve.
"""

from __future__ import annotations


def test_disabled_path_module_retired_v07x() -> None:
    # No-op anchor — the disabled-path semantics moved to the per-trigger
    # config row tests. This test exists so the file isn't empty (pytest
    # collects empty test modules but produces a noisy warning).
    assert True
