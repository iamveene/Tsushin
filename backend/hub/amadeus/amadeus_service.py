"""
Amadeus Flight Search Service
Hub integration for Amadeus API with OAuth2 client credentials flow.
"""

import requests
import logging
import os
from typing import Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from models import AmadeusIntegration
from hub.base import HubIntegrationBase
from hub.security import TokenEncryption


logger = logging.getLogger(__name__)


class AmadeusService(HubIntegrationBase):
    """
    Amadeus Flight Search API service.
    Manages OAuth2 client credentials authentication and flight search operations.
    """

    def __init__(self, integration: AmadeusIntegration, db: Session):
        """
        Initialize Amadeus service with Hub integration.

        Args:
            integration: AmadeusIntegration instance with API credentials
            db: Database session
        """
        super().__init__(db, integration.id)
        self.integration = integration
        self.db = db
        self.logger = logging.getLogger(f"{__name__}.{integration.id}")

        # Determine base URL based on environment
        if integration.environment == "production":
            self.base_url = "https://api.amadeus.com"
        else:
            self.base_url = "https://test.api.amadeus.com"

        # Get Amadeus-specific encryption key from database (MED-001 security fix)
        from services.encryption_key_service import get_amadeus_encryption_key
        encryption_key = get_amadeus_encryption_key(db)
        if not encryption_key:
            self.logger.error("AMADEUS_ENCRYPTION_KEY not configured in database or environment")
            raise ValueError("AMADEUS_ENCRYPTION_KEY not configured")

        self.token_encryption = TokenEncryption(encryption_key.encode())

    async def initialize(self) -> bool:
        """
        Initialize connection and get access token.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            token = await self.get_access_token()
            if token:
                self.logger.info(f"Amadeus service initialized (env: {self.integration.environment})")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize Amadeus service: {e}")
            return False

    async def get_access_token(self) -> Optional[str]:
        """
        Get OAuth2 access token from Amadeus API.
        Uses client credentials flow with token caching.

        Returns:
            Access token or None if authentication fails
        """
        # Check if we have a valid cached token
        if self.integration.current_access_token_encrypted and self.integration.token_expires_at:
            if datetime.utcnow() < self.integration.token_expires_at:
                # Decrypt and return cached token
                try:
                    token = self.token_encryption.decrypt(
                        self.integration.current_access_token_encrypted,
                        f"amadeus_{self.integration.id}"
                    )
                    return token
                except Exception as e:
                    self.logger.warning(f"Failed to decrypt cached token: {e}")

        # Request new token
        url = f"{self.base_url}/v1/security/oauth2/token"

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        # Decrypt API secret
        try:
            api_secret = self.token_encryption.decrypt(
                self.integration.api_secret_encrypted,
                f"amadeus_{self.integration.id}"
            )
        except Exception as e:
            self.logger.error(f"Failed to decrypt API secret: {e}")
            return None

        data = {
            "grant_type": "client_credentials",
            "client_id": self.integration.api_key,
            "client_secret": api_secret
        }

        try:
            response = requests.post(url, headers=headers, data=data, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            access_token = token_data.get('access_token')

            if not access_token:
                self.logger.error("No access token in response")
                return None

            # Cache token in database
            expires_in = token_data.get('expires_in', 1799)  # 30 min default
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 60)  # 1 min buffer

            # Encrypt and store token
            encrypted_token = self.token_encryption.encrypt(
                access_token,
                f"amadeus_{self.integration.id}"
            )

            self.integration.current_access_token_encrypted = encrypted_token
            self.integration.token_expires_at = expires_at
            self.db.commit()

            self.logger.info("Successfully obtained Amadeus access token")
            return access_token

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Amadeus authentication failed: {e}")
            return None

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        adults: int = 1,
        children: int = 0,
        infants: int = 0,
        travel_class: Optional[str] = None,
        currency: Optional[str] = None,
        max_results: Optional[int] = None,
        prefer_direct: bool = False
    ) -> Dict:
        """
        Search for flight offers using Amadeus API.

        Args:
            origin: Origin airport IATA code (e.g., "GRU")
            destination: Destination airport IATA code (e.g., "JFK")
            departure_date: Departure date in YYYY-MM-DD format
            return_date: Return date for round-trip (optional)
            adults: Number of adult passengers (1-9)
            children: Number of children (0-9)
            infants: Number of infants (0-9)
            travel_class: Travel class (ECONOMY, PREMIUM_ECONOMY, BUSINESS, FIRST)
            currency: Currency code (default from integration)
            max_results: Maximum results (default from integration)
            prefer_direct: Prefer non-stop flights

        Returns:
            API response dict or error dict
        """
        # Get access token
        token = await self.get_access_token()
        if not token:
            return {
                "error": "authentication_failed",
                "message": "Could not authenticate with Amadeus API"
            }

        # Rate limiting check
        await self._check_rate_limit()

        url = f"{self.base_url}/v2/shopping/flight-offers"

        headers = {
            "Authorization": f"Bearer {token}"
        }

        # Use defaults from integration if not provided
        currency = currency or self.integration.default_currency
        max_results = max_results or self.integration.max_results

        params = {
            "originLocationCode": origin.upper(),
            "destinationLocationCode": destination.upper(),
            "departureDate": departure_date,
            "adults": adults,
            "max": max_results,
            "currencyCode": currency.upper()
        }

        # Optional parameters
        if return_date:
            params["returnDate"] = return_date

        if children > 0:
            params["children"] = children

        if infants > 0:
            params["infants"] = infants

        if travel_class:
            params["travelClass"] = travel_class

        if prefer_direct:
            params["nonStop"] = "true"

        try:
            self.logger.info(
                f"Searching flights: {origin} → {destination}, "
                f"departure: {departure_date}, adults: {adults}"
            )

            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()

            # Track request for rate limiting
            await self._track_request()

            return response.json()

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Flight search failed: {e}")
            error_detail = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                except:
                    error_detail = e.response.text

            return {
                "error": "search_failed",
                "message": str(e),
                "detail": error_detail
            }

    async def _check_rate_limit(self):
        """Check if rate limit allows request (150 req/min for Amadeus)"""
        now = datetime.utcnow()

        # Reset counter if we're in a new minute window
        if not self.integration.last_request_window or \
           (now - self.integration.last_request_window).seconds >= 60:
            self.integration.requests_last_minute = 0
            self.integration.last_request_window = now
            self.db.commit()

        # Check limit
        if self.integration.requests_last_minute >= 150:
            raise Exception("Rate limit exceeded (150 requests per minute)")

    async def _track_request(self):
        """Track request for rate limiting"""
        self.integration.requests_last_minute += 1
        self.db.commit()

    async def health_check(self) -> Dict:
        """
        Check Amadeus API connectivity and token validity.

        Returns:
            Health status dict
        """
        try:
            token = await self.get_access_token()
            if token:
                return {
                    "status": "healthy",
                    "message": f"Connected to Amadeus {self.integration.environment} API",
                    "details": {
                        "environment": self.integration.environment,
                        "rate_limit": f"{self.integration.requests_last_minute}/150 per minute"
                    }
                }
            else:
                return {
                    "status": "unavailable",
                    "message": "Failed to authenticate with Amadeus API",
                    "details": {}
                }
        except Exception as e:
            return {
                "status": "degraded",
                "message": f"Health check failed: {str(e)}",
                "details": {}
            }

    async def validate_credentials(self) -> bool:
        """
        Validate that API credentials are correctly configured.

        Returns:
            True if credentials are valid, False otherwise
        """
        try:
            token = await self.get_access_token()
            return token is not None
        except Exception as e:
            self.logger.error(f"Credential validation failed: {e}")
            return False

    # Implement HubIntegrationBase abstract methods

    async def check_health(self) -> Dict:
        """
        Check health of Amadeus integration.
        Implements HubIntegrationBase.check_health().
        """
        return await self.health_check()

    async def refresh_tokens(self) -> bool:
        """
        Refresh OAuth2 access token.
        Implements HubIntegrationBase.refresh_tokens().

        For Amadeus, uses client credentials flow which generates
        new tokens on demand rather than refreshing existing ones.
        """
        try:
            token = await self.get_access_token()
            return token is not None
        except Exception as e:
            self.logger.error(f"Token refresh failed: {e}")
            return False

    async def revoke_access(self) -> None:
        """
        Revoke Amadeus access.
        Implements HubIntegrationBase.revoke_access().

        Amadeus uses client credentials flow, so we just clear cached tokens.
        """
        self.integration.current_access_token_encrypted = None
        self.integration.token_expires_at = None
        self.integration.is_active = False
        self.db.commit()
        self.logger.info("Amadeus access revoked")

    def get_metrics(self) -> Dict:
        """
        Get integration metrics.
        Implements HubIntegrationBase.get_metrics().
        """
        return {
            "requests_last_minute": self.integration.requests_last_minute,
            "token_valid": self.integration.token_expires_at > datetime.utcnow() if self.integration.token_expires_at else False,
            "environment": self.integration.environment,
            "default_currency": self.integration.default_currency
        }
