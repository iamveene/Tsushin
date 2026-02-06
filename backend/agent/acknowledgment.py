import re


STATUS_PATTERNS = [
    r"\bem trânsito\b",
    r"\bentregue\b",
    r"\bstatus\b",
    r"\bsua entrega\b",
    r"\bprevis[aã]o\b",
    r"\bprevist[ao]\b",
]

DATE_PATTERNS = [
    r"\b202\d-\d{2}-\d{2}\b",
    r"\b\d{2}/\d{2}/202\d\b",
]

REQUEST_PATTERNS = [
    r"\bpor favor\b",
    r"\bme informe\b",
    r"\bdigite\b",
    r"\binforme\b",
    r"\bpreciso\b",
    r"\bforneça\b",
]


def should_acknowledge_status(message: str) -> bool:
    if not message:
        return False

    message_lower = message.lower()

    if any(re.search(pattern, message_lower) for pattern in REQUEST_PATTERNS):
        return False

    has_status = any(re.search(pattern, message_lower) for pattern in STATUS_PATTERNS)
    has_date = any(re.search(pattern, message_lower) for pattern in DATE_PATTERNS)

    return has_status and has_date
