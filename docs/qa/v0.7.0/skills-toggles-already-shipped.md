# V-A: Skills UI Toggles — Already Shipped

The roadmap entry "Wire the Agent Skills UI toggles" was a false positive.
Toggle UI is fully implemented and live.

## Backend evidence

`backend/api/routes_skills.py:291–424` — `PUT /agents/{agent_id}/skills/{skill_type}` accepts a `SkillConfigRequest` with `is_enabled: bool`. Persists to `AgentSkill.is_enabled` (`backend/models.py:801`).

## Frontend evidence

`frontend/components/AgentSkillsManager.tsx`:
- Line 13: imports `ToggleSwitch`.
- Line 269–283: `toggleSkill()` calls `api.updateAgentSkill({ is_enabled: true | false })`.
- Lines 1763, 1907, 2000+ (multiple): renders `<ToggleSwitch>` per skill.
- Line 2349: copy reads "Changes are saved automatically per toggle."

## Action

No code change required. Browser verification is optional. The roadmap entry should be marked complete and the line removed from the next planning doc.
