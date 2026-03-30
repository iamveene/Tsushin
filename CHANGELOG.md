# Changelog

All notable changes to the Tsushin project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-03-30

### Added
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
