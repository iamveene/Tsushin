"""
Authentication Utilities
Phase 7.6.3 - JWT and Password Hashing

Provides JWT token generation/validation and password hashing utilities.
"""

import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

logger = logging.getLogger(__name__)

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 32:
    JWT_SECRET_KEY = secrets.token_urlsafe(32)
    logger.critical(
        "JWT_SECRET_KEY is not set or too short! Using ephemeral key — "
        "sessions will be lost on restart. Set JWT_SECRET_KEY in .env (min 32 chars)."
    )
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Password hashing configuration (using Argon2 - more secure than bcrypt)
password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """
    Hash a password using Argon2

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password from database

    Returns:
        True if password matches, False otherwise
    """
    try:
        password_hasher.verify(hashed_password, plain_password)
        return True
    except VerifyMismatchError:
        return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token

    Args:
        data: Dictionary of claims to encode in the token
        expires_delta: Optional expiration time delta

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow()
    })

    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT access token

    Args:
        token: JWT token string

    Returns:
        Dictionary of claims if valid, None if invalid/expired
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        # Token has expired
        return None
    except Exception:
        # Token is invalid (catches InvalidSignatureError, DecodeError, etc.)
        return None


def generate_reset_token() -> str:
    """
    Generate a secure random token for password reset

    Returns:
        Random token string
    """
    return secrets.token_urlsafe(32)


def generate_invitation_token() -> str:
    """
    Generate a secure random token for user invitation

    Returns:
        Random token string
    """
    return secrets.token_urlsafe(32)
