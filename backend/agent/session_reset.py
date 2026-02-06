import re


RESET_PATTERNS = [
    r"há mais algo",
    r"anything else",
    r"posso ajudar com mais",
    r"can I help with anything else",
    r"deseja (consultar|verificar) outr",
    r"would you like to",
    r"voltando ao menu",
    r"returning to menu",
    r"mais alguma (coisa|dúvida|pergunta)",
    r"any other (question|request)",
    r"alguma outra coisa",
    r"need anything else",
    r"avaliação do serviço",
    r"obrigad[ao] por ligar",
    r"obrigad[ao] por entrar em contato",
]


def should_attempt_session_reset(message: str) -> bool:
    if not message:
        return False

    message_lower = message.lower()
    return any(re.search(pattern, message_lower, re.IGNORECASE) for pattern in RESET_PATTERNS)


def reset_message_for_attempt(attempt: int) -> str:
    if attempt <= 0:
        return "menu"
    return "0"
