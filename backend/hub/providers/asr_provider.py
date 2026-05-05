"""
ASR Provider - Abstract base class for speech-to-text providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Any
import logging


@dataclass
class ASRRequest:
    audio_path: str
    model: str
    language: Optional[str] = None
    tenant_id: Optional[str] = None
    agent_id: Optional[int] = None
    sender_key: Optional[str] = None
    message_id: Optional[str] = None


@dataclass
class ASRResponse:
    success: bool
    provider: str
    text: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class ASRProvider(ABC):
    def __init__(self, db=None, token_tracker=None, tenant_id=None):
        self.db = db
        self.token_tracker = token_tracker
        self.tenant_id = tenant_id
        self.provider_name = self.get_provider_name()
        self.logger = logging.getLogger(f"{__name__}.{self.provider_name}")

    @abstractmethod
    def get_provider_name(self) -> str:
        pass

    @abstractmethod
    async def transcribe(self, request: ASRRequest) -> ASRResponse:
        pass
