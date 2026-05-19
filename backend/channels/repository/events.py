"""Shared repository trigger event vocabulary."""

from __future__ import annotations

GITHUB_EVENT_MAP: dict[str, str] = {
    "push": "github.push",
    "pull_request": "github.pull_request",
    "issues": "github.issues",
    "issue": "github.issues",
    "issue_comment": "github.issue_comment",
    "release": "github.release",
    "workflow_run": "github.workflow_run",
}

GITLAB_EVENT_MAP: dict[str, str] = {
    "push": "gitlab.push",
    "push hook": "gitlab.push",
    "merge_request": "gitlab.merge_request",
    "merge request hook": "gitlab.merge_request",
    "issue": "gitlab.issue",
    "issues": "gitlab.issue",
    "issue hook": "gitlab.issue",
    "note": "gitlab.note",
    "note hook": "gitlab.note",
    "tag_push": "gitlab.tag_push",
    "tag push hook": "gitlab.tag_push",
    "pipeline": "gitlab.pipeline",
    "pipeline hook": "gitlab.pipeline",
}

EVENT_CLASS_BY_PROVIDER_EVENT: dict[str, str] = {
    "pull_request": "pull_request",
    "merge_request": "pull_request",
    "push": "push",
    "issues": "issue",
    "issue": "issue",
    "issue_comment": "comment",
    "note": "comment",
    "release": "release",
    "tag_push": "release",
    "workflow_run": "pipeline",
    "pipeline": "pipeline",
}


def canonical_event(provider: str, event_type: str) -> str:
    normalized_provider = (provider or "").strip().lower()
    normalized_event = (event_type or "").strip().lower().replace(" ", "_")
    raw_event = (event_type or "").strip().lower()
    if normalized_provider == "github":
        return GITHUB_EVENT_MAP.get(normalized_event, f"github.{normalized_event}")
    if normalized_provider == "gitlab":
        return GITLAB_EVENT_MAP.get(raw_event) or GITLAB_EVENT_MAP.get(normalized_event) or f"gitlab.{normalized_event}"
    return f"{normalized_provider}.{normalized_event}" if normalized_provider else normalized_event


def event_class(provider: str, event_type: str) -> str:
    canonical = canonical_event(provider, event_type)
    provider_event = canonical.split(".", 1)[1] if "." in canonical else canonical
    return EVENT_CLASS_BY_PROVIDER_EVENT.get(provider_event, provider_event)
