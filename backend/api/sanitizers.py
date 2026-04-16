"""
HTML sanitization utilities for user-supplied input.
"""

import re


def strip_html_tags(text: str) -> str:
    """
    Remove all HTML tags from a string.

    This is a simple tag-stripping function suitable for plain-text fields
    (names, descriptions) where no HTML is expected or allowed.

    Args:
        text: Input string potentially containing HTML tags.

    Returns:
        String with all HTML tags removed.
    """
    if not text:
        return text
    return re.sub(r'<[^>]*>', '', text)


def sanitize_text_field(text: str) -> str:
    """
    Strip HTML tags and trim whitespace from a text field.

    Args:
        text: Input string potentially containing HTML tags.

    Returns:
        Sanitized and trimmed string, or None if input is None.
    """
    if text is None:
        return None
    return strip_html_tags(text).strip()
