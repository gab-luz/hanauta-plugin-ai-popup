from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class BackendProfile:
    key: str
    label: str
    provider: str
    model: str
    host: str
    icon_name: str
    needs_api_key: bool = False
    launchable: bool = False


@dataclass
class SourceChipData:
    text: str


@dataclass
class ChatItemData:
    role: str
    title: str
    body: str
    meta: str = ""
    created_at: float = field(default_factory=time.time)
    chips: list[SourceChipData] = field(default_factory=list)
    pending: bool = False
    audio_path: str = ""
    audio_waveform: list[int] = field(default_factory=list)


@dataclass
class CharacterCard:
    id: str
    name: str
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_message: str = ""
    message_example: str = ""
    system_prompt: str = ""
    avatar_path: str = ""
    source_path: str = ""
    source_type: str = ""

