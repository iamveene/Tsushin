# /fire_remediation -- Process Test Results into Bug Tracker

Process regression test results and update BUGS.md accordingly.

## Execution Steps

### Step 1: Read Current State

Read the current BUGS.md file:

```bash
cat /Users/vinicios/code/tsushin/BUGS.md
```

Parse the current counts: Open, In Progress, Resolved.

### Step 2: Process Failures

For each FAIL result from the regression test:

1. **Check if already tracked:** Search BUGS.md for the same area/endpoint/page
2. **If new bug:** Add to "Open Issues" section with this format:
   ```
   ### BUG-<NNN>: <Short description>
   - **Status:** Open
   - **Severity:** Critical / High / Medium / Low
   - **Area:** <area> (auth, agents, playground, flows, hub, settings, system, watcher, whatsapp)
   - **Layer:** Frontend / Backend / Database / Integration
   - **Found:** <date>
   - **Details:** <what failed and how>
   - **Steps to reproduce:**
     1. <step>
     2. <step>
   - **Expected:** <what should happen>
   - **Actual:** <what actually happened>
   ```
3. **If existing bug:** Update the entry (add a note with new occurrence date, update severity if warranted)

Severity guidelines:
- **Critical:** Login broken, data loss, service crash, security vulnerability
- **High:** Core feature broken (can't create agents, playground won't load, flows don't execute)
- **Medium:** Feature partially broken (UI glitch, slow response, non-critical API error)
- **Low:** Cosmetic issue, minor UX problem, non-blocking warning

### Step 3: Process Fixes

For each PASS result that previously had a matching FAIL in BUGS.md:

1. Move the bug entry from "Open Issues" to "Closed Issues"
2. Update the status:
   ```
   - **Status:** Resolved
   - **Resolved:** <date>
   - **Resolution:** <brief description of what fixed it>
   ```

### Step 4: Update Counts

Recount all entries and update the header line:

```
**Open:** <N> | **In Progress:** <N> | **Resolved:** <N>
```

### Step 5: Write Updated BUGS.md

Write the complete updated file to `/Users/vinicios/code/tsushin/BUGS.md`.

### Step 6: Output Summary

Print a summary:

```
=== REMEDIATION SUMMARY ===
New bugs filed: <N>
Bugs resolved: <N>
Bugs updated: <N>
Total open: <N>
Total resolved: <N>

New issues:
  - BUG-<NNN>: <description> [<severity>]

Resolved issues:
  - BUG-<NNN>: <description>
===
```

## Bug Numbering

- Start at BUG-001
- Always increment from the highest existing number
- Never reuse a bug number, even after resolution

## Notes

- BUGS.md is gitignored -- it is a working document, not committed to the repository
- The file lives at `/Users/vinicios/code/tsushin/BUGS.md`
- If the file does not exist, create it with the initial template before proceeding
