# Changelog

All notable changes to the Tsushin project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.1] - 2026-03-30

### Added
- **SSRF Protection for Browser Automation (Security)**: Comprehensive Server-Side Request Forgery protection for the browser automation skill.
  - New `browser_ssrf` Sentinel detection type with LLM-based intent analysis at 3 aggressiveness levels
  - DNS-resolution-based URL validation blocks private IPs, cloud metadata (169.254.169.254), Docker/Kubernetes internals, CGNAT ranges, and loopback addresses
  - Per-tenant URL allowlist/blocklist support in BrowserConfig — tenants can restrict browser navigation to approved domains only
  - Sentinel `analyze_browser_url()` pre-navigation check integrated into the browser automation skill pipeline
  - Browser SSRF toggle in Sentinel settings UI (critical severity, enabled by default)
  - Updated unified classification prompts to include `browser_ssrf` in all aggressiveness levels
  - Automatic DB migration adds `detect_browser_ssrf` and `browser_ssrf_prompt` columns for existing installations
  - Fresh installs seed `browser_ssrf` detection enabled by default

## [0.6.0] - 2026-03-30

### Added
- **Agent-to-Agent Communication (Item 39)**: Agents within the same tenant can now communicate directly. New `agent_communication` skill exposes 3 actions: `ask` (sync Q&A), `list_agents` (discover capabilities), and `delegate` (full handoff). Includes permission management, rate limiting, loop detection, Sentinel `agent_escalation` detection, and full audit logging. New "Communication" tab in Agent Studio with session log, permissions CRUD, and statistics dashboard.
- **Image generation for Playground channel**: Generated images from the `generate_image` tool are now rendered inline in Playground chat messages. Images can be clicked to open in a new tab.
- **Image generation for Telegram channel**: Generated images are sent as photos via the Telegram Bot API with optional captions.
- **Image serving endpoint**: New `GET /api/playground/images/{image_id}` endpoint serves generated images to the Playground frontend, following the same pattern as the existing audio serving endpoint.
- **WebSocket image delivery**: Image URLs are propagated through the WebSocket streaming pipeline so images appear in real-time during streamed responses.
- **Image generation tests**: Comprehensive test suite covering ImageSkill configuration, tool execution, PlaygroundService image caching, and TelegramSender photo delivery.
- **Test infrastructure**: Added `tests/` directory with `conftest.py` for mocking heavy ML dependencies in unit tests.
- `ROADMAP.md` for tracking planned features and releases.
- `CHANGELOG.md` for documenting changes across releases.

### Changed
- **ImageSkill default config**: `enabled_channels` now includes `"telegram"` in addition to `"whatsapp"` and `"playground"`.
- **TelegramSender**: Added `send_photo()` method for sending images via the Telegram Bot API.
- **Router `_send_message()`**: Telegram channel now supports `media_path` parameter for sending photos alongside text messages.
- **PlaygroundService**: Skill results and agent service results now propagate `media_paths` as cached `image_url` values in both regular and streaming response paths.
- **PlaygroundWebSocketService**: `done` events now include `image_url` field when images are generated.
- **PlaygroundChatResponse**: Added `image_url` field to the API response model.
- **PlaygroundMessage**: Added `image_url` field to the message model (both backend and frontend).
- **ExpertMode component**: Message bubbles now render generated images with responsive sizing and click-to-open behavior.

## [0.5.0-beta] - 2026-02-01

### Added
- Initial beta release
- Multi-agent architecture with intelligent routing
- Skills-as-Tools system with MCP compliance
- 16 built-in skills
- WhatsApp channel via MCP bridge
- Telegram channel integration
- Playground web interface with WebSocket streaming
- 4-layer memory system
- Knowledge base with document ingestion
- RBAC with multi-tenant support
- Watcher dashboard with analytics
- Sentinel security system
