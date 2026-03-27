"""
OAuth2 Token Exchange — Public API v1
Implements the client_credentials grant type for API authentication.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from sqlalchemy.orm import Session

from db import get_db
from services.api_client_service import ApiClientService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/v1/oauth/token")
async def token_exchange(
    request: Request,
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    OAuth2 token exchange endpoint.
    Accepts client_credentials grant type with client_id and client_secret.
    Returns a short-lived JWT access token (1 hour).
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
