# WS-2: Analytics Dashboard Frontend — Implementation Blueprint

## 1. Patterns and Conventions Found

**Charting library:** `recharts ^3.7.0` is already in `frontend/package.json:24`. No new dependency needed.

**Settings navigation:** There is no sidebar layout file. The settings hub is a flat card-grid in `frontend/app/settings/page.tsx`. Navigation entries are objects in the `settingsSections` array (lines 126–243). The Analytics card must be inserted there.

**Established page pattern** (from `frontend/app/settings/audit-logs/page.tsx`):
- `'use client'` at top
- Local TypeScript interfaces for each response shape
- `useAuth` + `hasPermission` guard (renders access-denied block if lacking permission)
- Header row with title, subtitle, optional action button (export)
- Back-to-settings `<Link>`
- Stats bar: 3-column card grid
- Filter bar in `bg-tsushin-surface border border-white/10 rounded-lg p-4`
- `useCallback` fetch functions, `useEffect` triggers
- Loading / empty / error states with consistent styling
- Load-more pagination

**Backend endpoint discovery** (from `routes_analytics.py`):

| Endpoint | Key query params | Returns |
|---|---|---|
| `GET /api/analytics/token-usage/summary` | `days` (int, 1–365, default 30) | `total_tokens`, `total_cost`, `total_requests`, `operation_breakdown[]`, `model_breakdown[]`, `daily_trend[]` |
| `GET /api/analytics/token-usage/by-agent` | `days` (int, default 30) | `{ agents: AgentSummary[], days }` |
| `GET /api/analytics/token-usage/agent/{agent_id}` | `days` (int, default 30) | `agent_id`, `total_tokens`, `total_cost`, `total_requests`, `skill_breakdown[]`, `model_breakdown[]` |
| `GET /api/analytics/token-usage/recent` | `limit` (1–500, default 100), `agent_id?` | `{ records: RecentRecord[], count }` |

**Important:** The summary endpoint uses a `days` integer, NOT `from_date`/`to_date` date strings. The date-range filter UX must translate preset choices into the `days` parameter. Backend constraint is `ge=1, le=365`.

---

## 2. Architecture Decision: Option A — Single-Page Dashboard with Tabs

**Chosen: Option A.** Rationale: all data comes from four lightweight endpoints that return quickly. URL-shareability is not a stated requirement; by-agent drill-down is a secondary view. Tabbed sub-routes (Option B) would duplicate the days-filter state across routes. Single page with React state tabs is consistent with how audit-logs handles multiple concerns in one component.

**Tab layout:**
1. **Overview** — 3 summary cards + Daily Trend area chart
2. **By Operation** — horizontal bar chart of `operation_breakdown`, table below
3. **By Model** — horizontal bar chart of `model_breakdown`, table below
4. **By Agent** — sortable table from `by-agent`; clicking a row opens an inline drawer with `agent/{id}` skill + model breakdown
5. **Recent** — paginated table of `recent` records with optional agent filter

---

## 3. TypeScript Interfaces (exact shapes from routes_analytics.py)

```typescript
interface OperationBreakdownItem { operation: string; tokens: number; cost: number; count: number }
interface ModelBreakdownItem { model: string; tokens: number; cost: number; count: number }
interface DailyTrendItem { date: string; tokens: number; cost: number; count: number }

interface TokenUsageSummary {
  total_tokens: number
  total_cost: number
  total_requests: number
  operation_breakdown: OperationBreakdownItem[]
  model_breakdown: ModelBreakdownItem[]
  daily_trend: DailyTrendItem[]
}

interface AgentUsageSummary {
  agent_id: number
  agent_name: string
  total_tokens: number
  total_cost: number
  total_requests: number
}
interface TokenUsageByAgentResponse { agents: AgentUsageSummary[]; days: number }

interface SkillBreakdownItem { skill: string; tokens: number; cost: number; count: number }
interface AgentTokenUsageDetail {
  agent_id: number
  total_tokens: number
  total_cost: number
  total_requests: number
  skill_breakdown: SkillBreakdownItem[]
  model_breakdown: ModelBreakdownItem[]
}

interface RecentRecord {
  id: number
  timestamp: string
  agent_name: string
  operation_type: string
  skill_type: string | null
  model: string
  total_tokens: number
  estimated_cost: number
}
interface RecentTokenUsageResponse { records: RecentRecord[]; count: number }
```

---

## 4. Date-Range Filter UX

Backend only accepts `days: int`, so UI presents four preset buttons: `[ 7d ] [ 30d ] [ 90d ] [ 365d ]`. Default 30d. Each button sets a `days` state integer that flows into all four API calls simultaneously. No arbitrary custom range — the `ge=1, le=365` constraint makes custom input unnecessary.

---

## 5. Component Design

### Files to Create

- `frontend/app/settings/analytics/page.tsx` — orchestrator. Holds `activeTab`, `days`, `summary`, `byAgent`, `agentDetail`, `recent`, loading/error states. Permission: `analytics.read`.
- `frontend/components/analytics/SummaryCards.tsx` — 3-column card grid: Total Tokens, Estimated Cost, Total Requests. Skeleton when loading.
- `frontend/components/analytics/DailyTrendChart.tsx` — recharts `<AreaChart>` with `tokens` and `cost` areas, dual Y-axis. `<ResponsiveContainer width="100%" height={220}>`.
- `frontend/components/analytics/BreakdownBarChart.tsx` — generic horizontal bar chart for operation/model breakdowns. Props: `data: Array<{label, tokens, cost, count}>`, `title`. Below the chart, compact table with three numeric columns.
- `frontend/components/analytics/ByAgentTable.tsx` — sortable table; row click expands inline detail drawer with skill + model breakdowns.
- `frontend/components/analytics/RecentTable.tsx` — 7-column table: Timestamp, Agent, Operation, Skill, Model, Tokens, Cost.

### Files to Modify

**`frontend/lib/client.ts`** — add four methods following the `getAuditEvents` pattern:

```typescript
async getTokenUsageSummary(days: number = 30): Promise<TokenUsageSummary>
async getTokenUsageByAgent(days: number = 30): Promise<TokenUsageByAgentResponse>
async getTokenUsageForAgent(agentId: number, days: number = 30): Promise<AgentTokenUsageDetail>
async getRecentTokenUsage(limit: number = 100, agentId?: number): Promise<RecentTokenUsageResponse>
```

**`frontend/app/settings/page.tsx`** — insert after Audit Logs entry (~line 180):

```typescript
{
  title: 'Analytics',
  description: 'Token consumption, cost breakdown, and usage trends by agent and model',
  icon: icons.pricing,
  href: '/settings/analytics',
  permission: 'analytics.read',
}
```

---

## 6. Data Flow

```
page.tsx mounts
  ├─ fetchSummary(days)  → GET /api/analytics/token-usage/summary?days=N
  ├─ fetchByAgent(days)  → GET /api/analytics/token-usage/by-agent?days=N
  └─ fetchRecent()       → GET /api/analytics/token-usage/recent?limit=100

User changes days pill → all three re-fire
User clicks agent row  → fetchAgentDetail(agentId, days) → GET /api/analytics/token-usage/agent/{id}?days=N
User changes tab       → no fetch; pure render switch
```

---

## 7. Build Sequence

1. Add 4 TypeScript interfaces + 4 client methods to `lib/client.ts`.
2. Create 5 leaf components in `frontend/components/analytics/`.
3. Create `frontend/app/settings/analytics/page.tsx` composing them.
4. Wire Analytics card into `settingsSections` in `frontend/app/settings/page.tsx`.
5. Rebuild frontend: `docker-compose build --no-cache frontend && docker-compose up -d frontend`.
6. QA pass + docs update.

---

## 8. Validation Seams (QA Checklist)

1. **Zero console errors** — Navigate to `https://localhost/settings/analytics`. Network shows 200 on all four endpoints; Console clean.
2. **Summary consistency** — Total Requests on summary cards matches sum of `count` across `operation_breakdown`. Total Cost matches sum of `cost`.
3. **Charts render** — Daily Trend area chart renders one point per day; empty-state when `daily_trend` is `[]`. Operations/Models bar charts show at least one bar when usage exists.
4. **Days-picker narrows results** — Switch 30d→7d: summary numbers decrease or stay equal. Network tab shows `?days=7`.
5. **Per-agent drill-down** — Click agent row → inline drawer expands with skill + model breakdown. Network tab shows `/agent/{id}?days=N`.
6. **Cross-tenant isolation** — Log in as `test@example.com` vs `testadmin@example.com`. Tenant owner sees only their own agent usage; global admin sees aggregate. Confirm with manual count comparison.
