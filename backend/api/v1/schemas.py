"""
Shared Schemas — Public API v1
Reusable Pydantic models for envelope responses, error formats,
pagination, and resource listings across all v1 endpoints.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ============================================================================
# Pagination
# ============================================================================

class PaginationMeta(BaseModel):
    """Pagination metadata for list endpoints."""
    total: int = Field(description="Total items matching the query")
    page: int = Field(description="Current page number (1-based)")
    per_page: int = Field(description="Items per page")


# ============================================================================
# Error Responses
# ============================================================================

class ErrorDetail(BaseModel):
    """Standard error response body."""
    code: str = Field(description="Machine-readable error code", example="not_found")
    message: str = Field(description="Human-readable error message")
    status: int = Field(description="HTTP status code", example=404)


class ErrorResponse(BaseModel):
    """Standard error envelope."""
    error: ErrorDetail = Field(description="Error details")
    request_id: Optional[str] = Field(None, description="Request ID for support/debugging")


class RateLimitErrorDetail(BaseModel):
    """Rate limit error body (matches middleware output)."""
    code: str = Field("rate_limit_exceeded", description="Error code")
    message: str = Field(description="Rate limit message with quota details")


class RateLimitErrorResponse(BaseModel):
    """429 Rate Limit Exceeded response."""
    error: RateLimitErrorDetail = Field(description="Rate limit error details")


# ============================================================================
# Success Envelope
# ============================================================================

class StatusResponse(BaseModel):
    """Simple success response for mutations."""
    status: str = Field("success", description="Operation status")
    message: str = Field(description="Human-readable status message")


# ============================================================================
# OAuth
# ============================================================================

class TokenResponse(BaseModel):
    """OAuth2 token exchange response."""
    access_token: str = Field(description="JWT access token")
    token_type: str = Field("bearer", description="Token type (always 'bearer')")
    expires_in: int = Field(description="Token lifetime in seconds", example=3600)
    scope: str = Field(description="Space-separated list of granted scopes")


class OAuthErrorResponse(BaseModel):
    """OAuth2-compliant error response."""
    error: str = Field(description="OAuth2 error code", example="invalid_client")
    error_description: str = Field(description="Human-readable error description")


# ============================================================================
# Resource Listings (routes_resources.py)
# ============================================================================

class SkillInfo(BaseModel):
    """Available skill type."""
    skill_type: str = Field(description="Skill type identifier", example="web_search")
    display_name: str = Field(description="Human-readable name", example="Web Search")
    description: Optional[str] = Field(None, description="Skill description")
    category: Optional[str] = Field(None, description="Skill category", example="search")


class SandboxedToolCommand(BaseModel):
    """Command within a sandboxed tool."""
    id: int = Field(description="Command ID")
    command_name: str = Field(description="Command name", example="quick_scan")
    command_template: Optional[str] = Field(None, description="Command template")
    is_long_running: bool = Field(False, description="Whether this is a long-running command")
    timeout_seconds: Optional[int] = Field(None, description="Command timeout in seconds")
    parameters: List[Dict[str, Any]] = Field(default_factory=list, description="Command parameters")


class SandboxedToolInfo(BaseModel):
    """Sandboxed tool with commands."""
    id: int = Field(description="Tool ID")
    name: str = Field(description="Tool name", example="nmap")
    tool_type: str = Field(description="Tool type", example="command")
    is_enabled: bool = Field(description="Whether the tool is enabled")
    commands: List[SandboxedToolCommand] = Field(default_factory=list, description="Available commands")


class PersonaInfo(BaseModel):
    """Persona summary."""
    id: int = Field(description="Persona ID")
    name: str = Field(description="Persona name", example="Professional Assistant")
    description: Optional[str] = Field(None, description="Persona description")
    role_description: Optional[str] = Field(None, description="Role description")
    is_system: bool = Field(description="Whether this is a system persona")
    tenant_id: Optional[str] = Field(None, description="Owning tenant ID (null for system)")


class SecurityProfileInfo(BaseModel):
    """Sentinel security profile summary."""
    id: int = Field(description="Profile ID")
    name: str = Field(description="Profile name", example="Strict Security")
    slug: str = Field(description="Profile slug", example="strict-security")
    is_system: bool = Field(description="Whether this is a system profile")
    is_default: bool = Field(description="Whether this is the default profile")
    detection_mode: Optional[str] = Field(None, description="Detection mode (block, detect_only, off)")
    aggressiveness_level: Optional[int] = Field(None, description="Aggressiveness level (0=Off, 1=Moderate, 2=Aggressive, 3=Extra)")


class TonePresetInfo(BaseModel):
    """Tone preset summary."""
    id: int = Field(description="Preset ID")
    name: str = Field(description="Preset name", example="Professional")
    description: Optional[str] = Field(None, description="Preset description")
    is_system: bool = Field(description="Whether this is a system preset")


# ============================================================================
# List Response Envelopes
# ============================================================================

class SkillListResponse(BaseModel):
    """Response for skill listing."""
    data: List[SkillInfo] = Field(description="List of available skills")


class ToolListResponse(BaseModel):
    """Response for tool listing."""
    data: List[SandboxedToolInfo] = Field(description="List of sandboxed tools")


class PersonaListResponse(BaseModel):
    """Response for persona listing."""
    data: List[PersonaInfo] = Field(description="List of available personas")


class SecurityProfileListResponse(BaseModel):
    """Response for security profile listing."""
    data: List[SecurityProfileInfo] = Field(description="List of security profiles")


class TonePresetListResponse(BaseModel):
    """Response for tone preset listing."""
    data: List[TonePresetInfo] = Field(description="List of tone presets")


# ============================================================================
# Common Error Response Dicts (for `responses=` parameter)
# ============================================================================

COMMON_RESPONSES = {
    401: {"description": "Authentication required — missing or invalid token/API key"},
    403: {"description": "Insufficient permissions for this operation"},
    429: {"description": "Rate limit exceeded — check X-RateLimit-Limit header", "model": RateLimitErrorResponse},
}

NOT_FOUND_RESPONSE = {
    404: {"description": "Resource not found"},
}

VALIDATION_RESPONSE = {
    422: {"description": "Validation error — invalid request body or query parameters"},
}
