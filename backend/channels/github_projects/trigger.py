"""GitHub Projects v2 polling trigger — diff a board's state, notify @Vini on WhatsApp.

Mirrors :class:`channels.jira.trigger.JiraTrigger` (interval polling + dispatch),
but instead of advancing a single cursor it diffs a **per-item snapshot**
(:class:`models.GitHubProjectsItemState`) — detecting a Status *move* needs each
item's previous value. GitHub does NOT emit webhooks for user-owned Projects v2,
so polling the GraphQL API and diffing state is the only way to observe:

  - ``card_added``    — a new item appears on the board
  - ``card_assigned`` — an assignee is added to an item
  - ``card_moved``    — an item's Status single-select changes (from → to)

Each event is composed into a deterministic WhatsApp message (``payload["message"]``)
and dispatched. The bound system-managed Flow's Notification node delivers it via
``{{source.payload.message}}`` — no LLM call per board change.

The diff/compose/dedupe helpers are module-level **pure functions** so they unit
test on plain dicts with no PAT or DB.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Optional

from sqlalchemy.orm import Session

from channels.trigger import Trigger
from channels.types import HealthResult, TriggerEvent
from hub.github.github_projects_service import GitHubProjectsError, GitHubProjectsService
from models import GitHubProjectsChannelInstance, GitHubProjectsItemState
from services.trigger_dispatch_service import TriggerDispatchInput, TriggerDispatchService


logger = logging.getLogger(__name__)

_DEFAULT_POLL_INTERVAL = 300
_EVENT_TYPES = {
    "card_added": "github_projects.card_added",
    "card_assigned": "github_projects.card_assigned",
    "card_moved": "github_projects.card_moved",
}


def _parse_iso(value: Any) -> Optional[datetime]:
    """Parse an ISO8601 string to a naive-UTC datetime (matches the rest of the codebase)."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _format_when(value: Any) -> str:
    dt = _parse_iso(value)
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "recently"


@dataclass(frozen=True)
class BoardEvent:
    """One detected board change (pure data — no GraphQL/DB shape)."""

    kind: str  # card_added | card_assigned | card_moved
    item_node_id: str
    title: Optional[str] = None
    url: Optional[str] = None
    content_type: Optional[str] = None
    status: Optional[str] = None
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    assignee: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(frozen=True)
class GitHubProjectsPollResult:
    """Summary of one GitHub Projects trigger poll."""

    instance_id: int
    tenant_id: str
    status: str
    fetched_count: int = 0
    event_count: int = 0
    dispatched_count: int = 0
    duplicate_count: int = 0
    skipped_count: int = 0
    seeded: bool = False
    reason: Optional[str] = None
    dispatch_statuses: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime = field(default_factory=datetime.utcnow)


# --------------------------------------------------------------------------- pure diff engine

def build_snapshot(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Normalize fetched items into ``{item_node_id: {...}}`` (active items only).

    Archived items are dropped so archiving simply removes an item from the
    working set (no spurious event).
    """
    snapshot: dict[str, dict[str, Any]] = {}
    for item in items or []:
        node_id = item.get("item_node_id")
        if not node_id or item.get("is_archived"):
            continue
        snapshot[node_id] = {
            "status": item.get("status_value"),
            "assignees": sorted({a for a in (item.get("assignees") or []) if a}),
            "title": item.get("title"),
            "url": item.get("url"),
            "content_type": item.get("content_type"),
            "updated_at": item.get("updated_at"),
        }
    return snapshot


def compute_board_events(
    stored: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
    *,
    is_first_poll: bool,
) -> list[BoardEvent]:
    """Pure diff of two snapshots → ordered list of :class:`BoardEvent`.

    **First poll seeds silently** (returns ``[]``) so an initial sync never
    backfills the whole board as "new cards".
    """
    if is_first_poll:
        return []

    events: list[BoardEvent] = []
    for node_id, cur in current.items():
        prev = stored.get(node_id)
        if prev is None:
            # Brand-new card: emit only card_added (don't also fire card_assigned
            # for assignees it was created with — that would double-notify).
            events.append(
                BoardEvent(
                    kind="card_added",
                    item_node_id=node_id,
                    title=cur.get("title"),
                    url=cur.get("url"),
                    content_type=cur.get("content_type"),
                    status=cur.get("status"),
                    updated_at=cur.get("updated_at"),
                )
            )
            continue

        if (cur.get("status") or None) != (prev.get("status") or None):
            events.append(
                BoardEvent(
                    kind="card_moved",
                    item_node_id=node_id,
                    title=cur.get("title"),
                    url=cur.get("url"),
                    content_type=cur.get("content_type"),
                    from_status=prev.get("status"),
                    to_status=cur.get("status"),
                    status=cur.get("status"),
                    updated_at=cur.get("updated_at"),
                )
            )

        prev_assignees = set(prev.get("assignees") or [])
        for login in cur.get("assignees") or []:
            if login not in prev_assignees:
                events.append(
                    BoardEvent(
                        kind="card_assigned",
                        item_node_id=node_id,
                        title=cur.get("title"),
                        url=cur.get("url"),
                        content_type=cur.get("content_type"),
                        assignee=login,
                        status=cur.get("status"),
                        updated_at=cur.get("updated_at"),
                    )
                )
    return events


def compose_message(event: BoardEvent, board_name: str) -> str:
    """Deterministic WhatsApp text for an event (no LLM)."""
    board = board_name or "the board"
    title = event.title or "(untitled)"
    url = f" {event.url}" if event.url else ""
    if event.kind == "card_added":
        status = event.status or "no status"
        return f'🆕 New card on {board}: "{title}" (in {status}).{url}'
    if event.kind == "card_assigned":
        who = event.assignee or "someone"
        return f'👤 "{title}" assigned to {who} on {board}.{url}'
    if event.kind == "card_moved":
        frm = event.from_status or "—"
        to = event.to_status or "—"
        return f'🔀 "{title}" moved {frm} → {to} on {board} at {_format_when(event.updated_at)}.{url}'
    return f'Update on {board}: "{title}".{url}'


def dedupe_key(event: BoardEvent) -> str:
    """Stable per-event dedupe key (claimed once in ``ChannelEventDedupe``)."""
    if event.kind == "card_added":
        return f"gh_proj_added:{event.item_node_id}"
    if event.kind == "card_assigned":
        return f"gh_proj_assigned:{event.item_node_id}:{event.assignee}"
    if event.kind == "card_moved":
        return f"gh_proj_moved:{event.item_node_id}:{event.from_status}->{event.to_status}:{event.updated_at}"
    return f"gh_proj_event:{event.item_node_id}:{event.kind}"


# --------------------------------------------------------------------------- trigger

class GitHubProjectsTrigger(Trigger):
    """Poll a GitHub Projects v2 board, diff state, dispatch board-event notifications."""

    channel_type: ClassVar[str] = "github_projects"
    delivery_mode: ClassVar[str] = "poll"
    supports_threads: ClassVar[bool] = False
    supports_reactions: ClassVar[bool] = False
    supports_rich_formatting: ClassVar[bool] = False
    supports_media: ClassVar[bool] = False
    text_chunk_limit: ClassVar[int] = 16000

    def __init__(
        self,
        db_session: Session,
        instance_id: int,
        log: logging.Logger,
        dispatcher: Optional[TriggerDispatchService] = None,
    ) -> None:
        self.db = db_session
        self.instance_id = instance_id
        self.logger = log
        self.dispatcher = dispatcher or TriggerDispatchService(db_session)

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def poll_or_receive(self) -> list[TriggerEvent]:
        """Scheduler-driven polling uses ``poll_active``; nothing to return here."""
        return []

    async def emit_wake_event(self, event: TriggerEvent) -> None:
        """Forward an already-normalized TriggerEvent through the dispatcher (parity with Jira)."""
        self.dispatcher.dispatch(
            TriggerDispatchInput(
                trigger_type=event.trigger_type,
                instance_id=event.instance_id,
                event_type=event.event_type,
                dedupe_key=event.dedupe_key,
                payload=event.payload,
                occurred_at=event.occurred_at,
                importance=event.importance,
                explicit_agent_id=event.matched_agent_id,
            )
        )

    def validate_recipient(self, recipient: str) -> bool:
        return True

    async def health_check(self) -> HealthResult:
        instance = self._load_instance()
        if instance is None:
            return HealthResult(healthy=False, status="error", detail="GitHub Projects trigger not found")
        if not instance.is_active or instance.status == "paused":
            return HealthResult(healthy=False, status="paused", detail="GitHub Projects trigger paused")
        return HealthResult(
            healthy=(instance.health_status == "healthy"),
            status=instance.health_status or "unknown",
            detail=instance.health_status_reason,
        )

    def _load_instance(self) -> Optional[GitHubProjectsChannelInstance]:
        return (
            self.db.query(GitHubProjectsChannelInstance)
            .filter_by(id=self.instance_id)
            .first()
        )

    def _event_to_dispatch_input(
        self, event: BoardEvent, instance: GitHubProjectsChannelInstance, board_name: str
    ) -> TriggerDispatchInput:
        message = compose_message(event, board_name)
        payload = {
            # The Notification node renders {{source.payload.message}} verbatim.
            "message": message,
            "notification_state": event.kind,
            "board": board_name,
            "item_node_id": event.item_node_id,
            "content_type": event.content_type,
            "title": event.title,
            "url": event.url,
            "status": event.status,
            "from_status": event.from_status,
            "to_status": event.to_status,
            "assignee": event.assignee,
            "when": _format_when(event.updated_at) if event.kind == "card_moved" else None,
            "project_owner": instance.project_owner,
            "project_number": instance.project_number,
        }
        return TriggerDispatchInput(
            trigger_type=self.channel_type,
            instance_id=instance.id,
            event_type=_EVENT_TYPES.get(event.kind, "github_projects.event"),
            dedupe_key=dedupe_key(event),
            payload=payload,
            occurred_at=_parse_iso(event.updated_at) or datetime.utcnow(),
            importance="normal",
            explicit_agent_id=instance.default_agent_id,
            sender_key=event.assignee or instance.project_owner,
            source_id=event.item_node_id,
        )

    @classmethod
    async def poll_active(
        cls,
        db: Session,
        *,
        dispatcher_factory: Optional[type[TriggerDispatchService]] = None,
        force: bool = False,
    ) -> list[GitHubProjectsPollResult]:
        """Poll every due active GitHub Projects trigger."""
        rows = (
            db.query(GitHubProjectsChannelInstance)
            .filter(
                GitHubProjectsChannelInstance.is_active == True,  # noqa: E712
                GitHubProjectsChannelInstance.status == "active",
            )
            .order_by(GitHubProjectsChannelInstance.id.asc())
            .all()
        )
        results: list[GitHubProjectsPollResult] = []
        for instance in rows:
            if not force and not cls._is_due(instance):
                results.append(
                    GitHubProjectsPollResult(
                        instance_id=instance.id,
                        tenant_id=instance.tenant_id,
                        status="skipped",
                        reason="poll_interval_not_elapsed",
                    )
                )
                continue
            results.append(
                await cls.poll_instance(db, instance, dispatcher_factory=dispatcher_factory, force=True)
            )
        return results

    @classmethod
    async def poll_instance(
        cls,
        db: Session,
        instance: GitHubProjectsChannelInstance,
        *,
        dispatcher_factory: Optional[type[TriggerDispatchService]] = None,
        force: bool = False,
    ) -> GitHubProjectsPollResult:
        """Poll one board: resolve → fetch → diff → dispatch → upsert snapshot."""
        if not instance.is_active or instance.status != "active":
            return GitHubProjectsPollResult(
                instance_id=instance.id, tenant_id=instance.tenant_id,
                status="skipped", reason="inactive_instance",
            )
        if not force and not cls._is_due(instance):
            return GitHubProjectsPollResult(
                instance_id=instance.id, tenant_id=instance.tenant_id,
                status="skipped", reason="poll_interval_not_elapsed",
            )

        started_at = datetime.utcnow()
        try:
            service = GitHubProjectsService(db, instance.tenant_id, instance.github_integration_id)

            # Resolve + cache the project node id / title on first need.
            if not instance.project_node_id:
                project = await service.read_project(instance.project_owner, instance.project_number)
                instance.project_node_id = project.get("id")
                title = project.get("title")
                if title:
                    instance.project_name = str(title)[:255]

            items = await service.fetch_board_items(instance.project_node_id)
            current = build_snapshot(items)
            stored = cls._load_stored_snapshot(db, instance.id)
            is_first_poll = instance.seeded_at is None
            events = compute_board_events(stored, current, is_first_poll=is_first_poll)
            board_name = instance.project_name or f"{instance.project_owner}/projects/{instance.project_number}"

            dispatcher = (dispatcher_factory or TriggerDispatchService)(db)
            adapter = cls(db, instance.id, logging.getLogger(__name__), dispatcher)
            dispatch_statuses: list[str] = []
            for event in events:
                result = dispatcher.dispatch(adapter._event_to_dispatch_input(event, instance, board_name))
                dispatch_statuses.append(result.status)

            cls._sync_snapshot(db, instance.id, current)

            instance.last_health_check = started_at
            instance.health_status = "healthy"
            instance.health_status_reason = None
            if is_first_poll:
                instance.seeded_at = started_at
            if any(s == "dispatched" for s in dispatch_statuses):
                instance.last_activity_at = started_at
            db.add(instance)
            db.commit()

            return GitHubProjectsPollResult(
                instance_id=instance.id,
                tenant_id=instance.tenant_id,
                status="ok",
                fetched_count=len(current),
                event_count=len(events),
                dispatched_count=sum(1 for s in dispatch_statuses if s == "dispatched"),
                duplicate_count=sum(1 for s in dispatch_statuses if s == "duplicate"),
                skipped_count=sum(1 for s in dispatch_statuses if s not in {"dispatched", "duplicate"}),
                seeded=is_first_poll,
                dispatch_statuses=dispatch_statuses,
            )
        except Exception as exc:  # noqa: BLE001 — surface as unhealthy, never crash the poll loop
            reason = (
                f"github_projects_poll_failed:{str(exc)[:300]}"
                if isinstance(exc, GitHubProjectsError)
                else f"github_projects_poll_failed:{type(exc).__name__}"
            )
            logging.getLogger(__name__).warning(
                "GitHub Projects trigger %s poll failed: %s", instance.id, type(exc).__name__
            )
            return cls._mark_unhealthy(db, instance, reason=reason, status="error")

    @staticmethod
    def _is_due(instance: GitHubProjectsChannelInstance) -> bool:
        if instance.last_health_check is None:
            return True
        elapsed = (datetime.utcnow() - instance.last_health_check).total_seconds()
        return elapsed >= int(instance.poll_interval_seconds or _DEFAULT_POLL_INTERVAL)

    @staticmethod
    def _load_stored_snapshot(db: Session, instance_id: int) -> dict[str, dict[str, Any]]:
        rows = db.query(GitHubProjectsItemState).filter_by(instance_id=instance_id).all()
        snapshot: dict[str, dict[str, Any]] = {}
        for row in rows:
            snapshot[row.item_node_id] = {
                "status": row.status_value,
                "assignees": sorted(row.assignees_json or []),
                "title": row.title,
                "url": row.url,
                "content_type": row.content_type,
                "updated_at": row.last_updated_at.isoformat() if row.last_updated_at else None,
            }
        return snapshot

    @staticmethod
    def _sync_snapshot(db: Session, instance_id: int, current: dict[str, dict[str, Any]]) -> None:
        """Upsert rows for items in ``current``; delete rows for items that left the board."""
        rows = db.query(GitHubProjectsItemState).filter_by(instance_id=instance_id).all()
        by_id = {r.item_node_id: r for r in rows}
        seen: set[str] = set()
        for node_id, snap in current.items():
            seen.add(node_id)
            row = by_id.get(node_id)
            if row is None:
                row = GitHubProjectsItemState(instance_id=instance_id, item_node_id=node_id)
                db.add(row)
            row.content_type = snap.get("content_type")
            row.title = snap.get("title")
            row.url = snap.get("url")
            row.status_value = snap.get("status")
            row.assignees_json = list(snap.get("assignees") or [])
            row.last_updated_at = _parse_iso(snap.get("updated_at"))
        for node_id, row in by_id.items():
            if node_id not in seen:
                db.delete(row)

    @staticmethod
    def _mark_unhealthy(
        db: Session,
        instance: GitHubProjectsChannelInstance,
        *,
        reason: str,
        status: str,
    ) -> GitHubProjectsPollResult:
        db.rollback()
        instance.last_health_check = datetime.utcnow()
        instance.health_status = "unhealthy"
        instance.health_status_reason = reason[:500]
        db.add(instance)
        db.commit()
        return GitHubProjectsPollResult(
            instance_id=instance.id,
            tenant_id=instance.tenant_id,
            status=status,
            reason=reason,
        )
