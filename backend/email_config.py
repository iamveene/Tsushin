"""Allow .local email domains for dev environments."""
import email_validator

_blocked = {"local"}
email_validator.SPECIAL_USE_DOMAIN_NAMES = [
    d for d in email_validator.SPECIAL_USE_DOMAIN_NAMES if d not in _blocked
]
