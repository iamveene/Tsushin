"""
Shared password policy used by auth flows.

BUG-457: Keep setup, signup, password change, and reset rules consistent.
"""

from typing import Optional

MIN_PASSWORD_LENGTH = 8


def password_min_length_message(subject: str = "Password") -> str:
    """Return a consistent minimum-length validation message."""
    return f"{subject} must be at least {MIN_PASSWORD_LENGTH} characters"


def get_password_min_length_error(password: str, subject: str = "Password") -> Optional[str]:
    """Return a validation error string when password is too short."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return password_min_length_message(subject)
    return None
