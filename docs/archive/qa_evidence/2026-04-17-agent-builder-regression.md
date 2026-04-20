# Agent Builder UI Regression Summary

Date: 2026-04-17
Scope: `/agents/builder`
Method: browser automation against the live local stack after rebuilding `backend` and `frontend`

## Coverage

- cold load and hard reload behavior
- agent selection and graph synchronization
- persona drag attach and detach behavior
- A2A network visualization toggle
- create-agent modal consistency against the main Studio create flow
- route navigation between Builder and adjacent Studio pages

## Confirmed Findings

### 1. Cold load can leave the canvas blank

After a hard reload, the Builder sidebar hydrates and shows the selected agent metadata, but the React Flow canvas can remain empty for several seconds instead of rendering the graph.

Impact: users land in a partially loaded Builder where the control surface is visible but the main graph is missing.

### 2. Agent selection can lag behind in the graph

Changing the selected agent updates the dropdown immediately and the left sidebar shortly after, but the graph can keep rendering the previously selected agent.

Impact: the user can make changes while looking at the wrong agent graph.

### 3. User Guide overlay does not dismiss reliably

The Builder can remain covered by the User Guide overlay even after `Escape` and close-button interactions.

Impact: the page appears blocked and the overlay interferes with regression testing and normal use.

### 4. A2A network toggle does not render peers

The Builder exposes the `A2A Network` control and the backing API returns enabled permissions, but the graph does not render peer ghost nodes or dashed A2A links.

Impact: cross-agent visibility is incomplete and the A2A network view appears broken.

### 5. Drag-to-detach is advertised but not implemented

Attached palette items display `Double-click or drag to detach`, but drag-off does not detach them. Persona attach by drag works; detach works by double-click.

Impact: the UI promises a drag interaction that currently behaves like a no-op.

### 6. Builder create-agent flow is not shared with the main Studio flow

In this tenant, the visible provider list matched the main Studio create flow because each configured vendor currently has a single instance and a single model. However, the implementations are forked:

- the main Studio flow aggregates models across all configured instances of a vendor
- the Builder modal binds models to the selected/default instance only
- the main Studio flow includes extra handling for providers like OpenRouter

Impact: provider/model support can drift between the two entry points as upgrades land.

## Result

The Agent Builder feature currently has multiple confirmed UI regressions and one confirmed consistency risk in the create-agent flow. The most serious user-facing issues are:

- blank graph on reload
- graph lagging one agent behind the selector
- non-functional A2A visualization

These findings were also documented in the local internal bug tracker during the regression pass.
