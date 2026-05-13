"""
Productivity Service Catalog — single source of truth for productivity
integrations (calendar / email / tasks / knowledge-base) surfaced by the
Hub > Productivity tab and its guided wizard.

Historically the Hub Productivity tab rendered a hard-coded grid of cards
("Google Integration", "Asana — Not Connected", "Google Calendar — Not
Connected") regardless of whether the tenant had configured them. That
pattern drove two complaints:

  * empty placeholders take screen space for services the user hasn't
    chosen to use;
  * every new service required a parallel frontend edit.

v0.7 switches the tab to a guided wizard modelled on ``ProviderWizard``.
The wizard needs to know what services exist and which ones the current
tenant has already configured. This module supplies that list; the
endpoint in ``api.routes_hub_productivity`` annotates each entry with
``tenant_has_configured`` so the UI can render only configured cards and
reserve the "+ Add Productivity Integration" CTA for everything else.

If you add a new productivity integration:
  1. Add a ``ProductivityServiceInfo`` entry below.
  2. Update the fallback array in ``ProductivityWizard.tsx``.
  3. ``backend/tests/test_wizard_drift.py`` asserts the two stay in sync.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List


@dataclass(frozen=True)
class ProductivityServiceInfo:
    """Wizard-facing metadata for a single productivity service."""

    id: str                 # Stable service id (e.g. "google_calendar")
    display_name: str       # Human label for the wizard card
    description: str        # One-sentence summary
    category: str           # "calendar" | "email" | "tasks" | "knowledge_base"
    vendor: str             # "google" | "asana" | "notion" | ...
    requires_oauth: bool    # True if setup needs an OAuth grant
    oauth_provider: str     # "google" | "asana" | "" — drives credential step reuse
    integration_type: str   # Matches ``HubIntegration.type`` for configured-check
    icon_hint: str          # UI maps this to an icon
    status: str             # "available" | "beta" | "coming_soon"

    def to_dict(self) -> dict:
        return asdict(self)


# Ordering drives the wizard card layout. Group by category so the step-2
# picker reads naturally (calendar -> email -> tasks).
PRODUCTIVITY_CATALOG: List[ProductivityServiceInfo] = [
    ProductivityServiceInfo(
        id="google_calendar",
        display_name="Google Calendar",
        description="Create, update, and query calendar events from agents.",
        category="calendar",
        vendor="google",
        requires_oauth=True,
        oauth_provider="google",
        integration_type="calendar",
        icon_hint="calendar",
        status="available",
    ),
    ProductivityServiceInfo(
        id="gmail",
        display_name="Gmail",
        description="Read, search, and route emails through agents.",
        category="email",
        vendor="google",
        requires_oauth=True,
        oauth_provider="google",
        integration_type="gmail",
        icon_hint="gmail",
        status="available",
    ),
    ProductivityServiceInfo(
        id="asana",
        display_name="Asana",
        description="Create and manage tasks across Asana workspaces.",
        category="tasks",
        vendor="asana",
        requires_oauth=True,
        oauth_provider="asana",
        integration_type="asana",
        icon_hint="asana",
        status="available",
    ),
]


def get_productivity_catalog() -> List[ProductivityServiceInfo]:
    """Return the static productivity catalog (stable ordering)."""
    return list(PRODUCTIVITY_CATALOG)
