"""
OAuth2 Token Exchange — Public API v1
Implements the client_credentials grant type for API authentication.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from db import get_db
from services.api_client_service import ApiClientService
from api.v1.schemas import TokenResponse, OAuthErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Per-IP rate limiting for OAuth token endpoint (brute-force protection)
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/api/v1/oauth/token",
    response_model=TokenResponse,
    responses={
        400: {"description": "Unsupported grant type", "model": OAuthErrorResponse},
        401: {"description": "Invalid client credentials", "model": OAuthErrorResponse},
        429: {"description": "Rate limit exceeded (10 requests/minute per IP)"},
    },
)
@limiter.limit("10/minute")
async def token_exchange(
    request: Request,
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Exchange API client credentials for a short-lived JWT access token.

    Accepts the `client_credentials` grant type only. Returns a bearer token
    valid for 1 hour. Rate limited to 10 requests per minute per IP address.
    """
    if grant_type != "client_credentials":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_grant_type",
                "error_description": f"Grant type '{grant_type}' is not supported. Use 'client_credentials'.",
            },
        )

    service = ApiClientService(db)
    client = service.verify_secret(client_id, client_secret)

    if not client:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_client",
                "error_description": "Invalid client_id or client_secret.",
            },
        )

    # Get client IP for audit
    ip_address = request.client.host if request.client else None

    token_response = service.generate_token(client, ip_address=ip_address)
    logger.info(f"Token issued for API client '{client.client_id}' from IP {ip_address}")

    return token_response
