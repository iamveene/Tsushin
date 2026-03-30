# Tsushin Roadmap

## Released

### v0.5.0-beta (February 2026)
- Multi-agent architecture with agent routing
- Skills-as-Tools system (MCP-compliant)
- 16 built-in skills: web search, weather, flights, audio transcription, TTS, image generation, browser automation, shell, Gmail, flows, and more
- WhatsApp channel via MCP bridge
- Telegram channel integration (Phase 10)
- Playground web interface with WebSocket streaming
- 4-layer memory system with semantic search
- Knowledge base with document ingestion
- RBAC with multi-tenant support
- Watcher dashboard with analytics
- Conversation search (full-text + semantic)
- Thread management with auto-rename
- Project context system
- Sentinel security system

### v0.6.0 (March 2026)
- **Image generation for Playground and Telegram channels**: The image generation and editing skill (powered by Google Gemini) is now available on all three channels: WhatsApp, Playground, and Telegram. Previously this was limited to WhatsApp only.
  - Playground: Generated images are rendered inline in chat messages with click-to-open in a new tab
  - Telegram: Generated images are sent as photos via the Telegram Bot API
  - Image serving endpoint for Playground (`/api/playground/images/{id}`)
  - WebSocket streaming support for image delivery
  - Full test coverage for the image generation pipeline

## Planned

### v0.7.0
- Enhanced image editing workflows
- Multi-image generation (batch mode)
- Image history and gallery view in Playground
- Voice-to-image pipeline (describe image via audio)

### v0.8.0
- Video generation capabilities
- Advanced flow orchestration
- Plugin marketplace for community skills

### v1.0.0
- Production-ready release
- Comprehensive API documentation
- Performance benchmarks and optimization
- Enterprise deployment guide
